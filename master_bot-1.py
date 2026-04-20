import os
import time
import requests
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════════
#  CLIENT REGISTRY — Add new client here, nothing else to change
# ══════════════════════════════════════════════════════════════════
CLIENTS = {

    "lovelytaste": {
        "type":           "restaurant",
        "name":           "Lovely Taste Restaurant",
        "fonnte_token":   os.environ.get("LOVELY_FONNTE", "8mY6hQVX7SYLyX4gQjpc"),
        "admin_phone":    os.environ.get("LOVELY_PHONE",  "916205131181"),
        "website":        "https://lovelytaste.netlify.app",
        "timing_start":   "10:00",
        "timing_end":     "22:00",
        "db":             "supabase",
        "supabase_url":   os.environ.get("LOVELY_SB_URL", "https://gltnufmbzubdcsbienes.supabase.co"),
        "supabase_key":   os.environ.get("LOVELY_SB_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdsdG51Zm1ienViZGNzYmllbmVzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5MTE0ODQsImV4cCI6MjA5MTQ4NzQ4NH0.2MA-fXdQPwgON9cD_aTByR4vYg5vmPp5PNBFlYTJVC4"),
    },

    "medisoft": {
        "type":           "pharmacy",
        "name":           "MediSoft Pharmacy",
        "fonnte_token":   os.environ.get("MEDISOFT_FONNTE", "W4ZDb6dcnTGCAacJwRjp"),
        "admin_phone":    os.environ.get("MEDISOFT_PHONE",  "918407853708"),
        "website":        "https://medisoft.netlify.app",
        "timing_start":   "08:00",
        "timing_end":     "22:00",
        "db":             "firebase",
        "firebase_project": "medisoft-e12bf",
    },

    # ── ADD NEW CLIENT BELOW ──────────────────────────────────────
    # "newclient": {
    #     "type":         "pharmacy" or "restaurant",
    #     "name":         "Client Name",
    #     "fonnte_token": "their_fonnte_token",
    #     "admin_phone":  "91XXXXXXXXXX",
    #     "website":      "https://their-site.netlify.app",
    #     "timing_start": "09:00",
    #     "timing_end":   "21:00",
    #     "db":           "firebase",
    #     "firebase_project": "their-project-id",
    # },

}

# ══════════════════════════════════════════════════════════════════
#  SESSION MANAGEMENT (per client, 10 min timeout)
# ══════════════════════════════════════════════════════════════════
sessions = {}   # { "clientid:phone": {"step":..., "t":...} }

def get_session(client_id, phone):
    key = f"{client_id}:{phone}"
    now = time.time()
    if key in sessions:
        if now - sessions[key].get("t", 0) > 600:
            del sessions[key]
            return {}
        return sessions[key]
    return {}

def set_session(client_id, phone, data):
    key = f"{client_id}:{phone}"
    sessions[key] = {**data, "t": time.time()}

# ══════════════════════════════════════════════════════════════════
#  DATABASE HELPERS
# ══════════════════════════════════════════════════════════════════

# ── Supabase ──
def sb_headers(client):
    key = client["supabase_key"]
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def sb_get_config(client):
    try:
        res = requests.get(
            f"{client['supabase_url']}/rest/v1/bot_config?id=eq.1&select=*",
            headers=sb_headers(client), timeout=5
        )
        data = res.json()
        return data[0] if data else {}
    except Exception as e:
        print(f"[SB ERROR] {e}")
        return {}

def sb_get_menu(client):
    try:
        res = requests.get(
            f"{client['supabase_url']}/rest/v1/menu_items?available=eq.true&select=*&order=category",
            headers=sb_headers(client), timeout=5
        )
        return res.json() or []
    except Exception as e:
        print(f"[SB MENU ERROR] {e}")
        return []

# ── Firebase ──
def fb_base(client):
    proj = client["firebase_project"]
    return f"https://firestore.googleapis.com/v1/projects/{proj}/databases/(default)/documents"

def fb_get_settings(client):
    try:
        res = requests.get(f"{fb_base(client)}/settings/bot", timeout=5)
        fields = res.json().get("fields", {})
        return {
            "botEnabled": fields.get("botEnabled", {}).get("booleanValue", True),
            "autoReply":  fields.get("autoReply",  {}).get("booleanValue", True),
        }
    except Exception as e:
        print(f"[FB ERROR] {e}")
        return {"botEnabled": True, "autoReply": True}

def fb_add(client, collection, data):
    try:
        fields = {}
        for k, v in data.items():
            if isinstance(v, bool):
                fields[k] = {"booleanValue": v}
            elif isinstance(v, (int, float)):
                fields[k] = {"doubleValue": float(v)}
            else:
                fields[k] = {"stringValue": str(v)}
        fields["createdAt"] = {"timestampValue": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
        requests.post(f"{fb_base(client)}/{collection}", json={"fields": fields}, timeout=5)
    except Exception as e:
        print(f"[FB ADD ERROR] {e}")

# ── Cache (per client) ──
_cache = {}  # { "clientid_config": (data, timestamp), "clientid_menu": (data, timestamp) }

def cached(key, fetcher, ttl=300):
    now = time.time()
    if key in _cache and (now - _cache[key][1]) < ttl:
        return _cache[key][0]
    data = fetcher()
    _cache[key] = (data, now)
    return data

# ══════════════════════════════════════════════════════════════════
#  WORKING HOURS CHECK
# ══════════════════════════════════════════════════════════════════
def is_open(client, config=None):
    try:
        start_str = (config or {}).get("working_hours_start") or client.get("timing_start", "08:00")
        end_str   = (config or {}).get("working_hours_end")   or client.get("timing_end",   "22:00")
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        now = datetime.now()
        return now.replace(hour=sh, minute=sm, second=0) <= now <= now.replace(hour=eh, minute=em, second=0)
    except:
        return True

# ══════════════════════════════════════════════════════════════════
#  INTENT DETECTION
# ══════════════════════════════════════════════════════════════════
ORDER_KW    = ["order","medicine","dawai","dawa","khaana","food","order karna","chahiye","buy","1"]
MENU_KW     = ["menu","list","kya hai","kya milta","item","2"]
REMINDER_KW = ["reminder","remind","refill","yaad","bhool","2","reminder chahiye","refill reminder"]
LOCATION_KW = ["location","address","kahan","kaha","timing","time","3","open","shop"]
CONTACT_KW  = ["contact","call","baat","phone","number","4","support","staff"]

def detect_intent(msg, client_type):
    m = msg.lower()
    for kw in ORDER_KW:
        if kw in m: return "order"
    if client_type == "restaurant":
        for kw in MENU_KW:
            if kw in m: return "menu"
    if client_type == "pharmacy":
        for kw in REMINDER_KW:
            if kw in m: return "reminder"
    for kw in LOCATION_KW:
        if kw in m: return "location"
    for kw in CONTACT_KW:
        if kw in m: return "contact"
    return None

# ══════════════════════════════════════════════════════════════════
#  MESSAGE BUILDERS
# ══════════════════════════════════════════════════════════════════
GREETINGS = ["hi","hello","hlo","hii","hey","namaskar","namaste","hy","helo",
             "start","help","0","back","wapas","reset"]

def welcome(client, client_type):
    name = client["name"]
    if client_type == "restaurant":
        return (f"🍽️ *{name}*\nNamaskar! Swagat hai aapka 🙏\n\n"
                f"Aap kya karna chahte hain?\n\n"
                f"*1️⃣* 🛒 Order karna hai\n"
                f"*2️⃣* 📋 Menu dekhna hai\n"
                f"*3️⃣* 📍 Location & Timing\n"
                f"*4️⃣* 📞 Humse baat karein\n\n"
                f"Number ya seedha batayein 😊")
    else:
        return (f"💊 *{name}*\nNamaskar! Swagat hai aapka 🙏\n\n"
                f"Aap kya karna chahte hain?\n\n"
                f"*1️⃣* 🛒 Medicine Order karna hai\n"
                f"*2️⃣* ⏰ Refill Reminder set karna hai\n"
                f"*3️⃣* 📍 Location & Timing\n"
                f"*4️⃣* 📞 Humse baat karein\n\n"
                f"Number ya seedha batayein 😊")

def order_reply(client):
    url = client["website"]
    t = client["type"]
    if t == "restaurant":
        return (f"🛒 *ONLINE ORDER*\n\nWebsite se order karein:\n👉 *{url}*\n\n"
                f"✅ Poora menu dekhein\n✅ Cart mein add karein\n"
                f"✅ WhatsApp pe confirmation milega!\n\nKoi dikkat ho toh *4* bhejein 😊")
    else:
        return (f"🛒 *MEDICINE ORDER*\n\nWebsite se order karein:\n👉 *{url}*\n\n"
                f"✅ Medicine naam aur quantity fill karein\n✅ Delivery address dein\n"
                f"✅ WhatsApp pe confirmation milega!\n\nYa seedha medicine list yahan bhej dein 😊\n\nWapas ke liye *0* bhejein")

def menu_reply(client, client_id):
    url = client["website"]
    items = cached(f"{client_id}_menu", lambda: sb_get_menu(client))
    if not items:
        return f"📋 *MENU*\n\nMenu website pe dekho 👉 *{url}*\n\nWapas ke liye *0* bhejein"
    cat_order  = ["Starters","Main Course","Rice & Biryani","Breads","Desserts","Beverages"]
    cat_emojis = {"Starters":"🥗","Main Course":"🍛","Rice & Biryani":"🍚","Breads":"🫓","Desserts":"🍮","Beverages":"🥭"}
    cats = {}
    for item in items:
        c = item.get("category","Other")
        cats.setdefault(c, []).append(item)
    msg = "📋 *HAMARA MENU*\n"
    for cat in cat_order:
        if cat not in cats: continue
        msg += f"\n*{cat_emojis.get(cat,'🍽️')} {cat}*\n"
        for item in cats[cat]:
            msg += f"{item.get('emoji','•')} {item.get('name','')} — ₹{item.get('price',0)}\n"
    msg += f"\n👉 Order: *{url}*\n\nWapas ke liye *0* bhejein"
    return msg

def reminder_reply():
    return ("⏰ *REFILL REMINDER*\n\nApna naam aur medicine bhejein:\n\n"
            "*Format:*\nNaam: Ravi Kumar\nMedicine: Metformin 500mg\nKitne din mein khatam hoti hai: 30\n\n"
            "Hum automatically reminder set kar denge ✅\n\nWapas ke liye *0* bhejein")

def location_reply(client, config=None):
    url   = client["website"]
    start = (config or {}).get("working_hours_start") or client.get("timing_start","08:00")
    end   = (config or {}).get("working_hours_end")   or client.get("timing_end",  "22:00")
    icon  = "🍽️" if client["type"] == "restaurant" else "💊"
    return (f"📍 *{client['name']}*\n\n🏠 *Address:* Patna, Bihar\n"
            f"⏰ *Timing:* {start} – {end} (Daily)\n🌐 *Website:* {url}\n\n"
            f"👉 Online order: *{url}*\n\nWapas ke liye *0* bhejein")

def contact_reply(client, config=None):
    url   = client["website"]
    phone = client["admin_phone"][-10:]
    start = (config or {}).get("working_hours_start") or client.get("timing_start","08:00")
    end   = (config or {}).get("working_hours_end")   or client.get("timing_end",  "22:00")
    return (f"📞 *CONTACT US*\n\n📱 *WhatsApp / Call:* +91 {phone}\n"
            f"🌐 *Website:* {url}\n⏰ *Available:* {start} – {end}\n\n"
            f"Hum madad ke liye hamesha taiyaar hain! 🙏\n\nWapas ke liye *0* bhejein")

def unknown_reply(client_type):
    if client_type == "restaurant":
        return ("Maafi chahte hain 😅\n\nKripya batayein:\n"
                "*1* — 🛒 Order\n*2* — 📋 Menu\n*3* — 📍 Location\n*4* — 📞 Contact")
    else:
        return ("Maafi chahte hain 😅\n\nKripya batayein:\n"
                "*1* — 🛒 Medicine Order\n*2* — ⏰ Refill Reminder\n*3* — 📍 Location\n*4* — 📞 Contact")

# ══════════════════════════════════════════════════════════════════
#  REMINDER SAVE (Firebase pharmacy only)
# ══════════════════════════════════════════════════════════════════
def parse_reminder(phone, message, client):
    lines = message.strip().split("\n")
    data  = {"phone": phone, "status": "active", "source": "whatsapp", "template": "reorder"}
    for line in lines:
        if ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip().lower(), v.strip()
            if "naam" in k or "name" in k:   data["name"] = v
            elif "medicine" in k:             data["medicine"] = v
            elif "din" in k or "day" in k:
                try:    data["reminder_days"] = int(''.join(filter(str.isdigit, v))) or 30
                except: data["reminder_days"] = 30
    if "name" in data and "medicine" in data:
        fb_add(client, "reminders", data)
        return True
    return False

# ══════════════════════════════════════════════════════════════════
#  SEND MESSAGE
# ══════════════════════════════════════════════════════════════════
def send_msg(client, to, message):
    try:
        resp = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": client["fonnte_token"], "Content-Type": "application/json"},
            json={"target": to, "message": message, "countryCode": "91"},
            timeout=10
        )
        print(f"[SENT {client['name']} → {to}] {resp.status_code}")
    except Exception as e:
        print(f"[ERROR send_msg] {e}")

# ══════════════════════════════════════════════════════════════════
#  PROCESS MESSAGE (per client)
# ══════════════════════════════════════════════════════════════════
def process(client_id, phone, message):
    client = CLIENTS[client_id]
    ctype  = client["type"]
    msg    = message.strip().lower()

    # Check bot settings
    if client["db"] == "firebase":
        settings = cached(f"{client_id}_settings", lambda: fb_get_settings(client), ttl=60)
        if not settings.get("botEnabled", True): return None
        if not settings.get("autoReply",  True): return None
    elif client["db"] == "supabase":
        config = cached(f"{client_id}_config", lambda: sb_get_config(client))
        if not config.get("is_active", True):
            return config.get("offline_message", "Abhi hum available nahi hain.")
        if not is_open(client, config):
            return config.get("offline_message", "Abhi hum available nahi hain.")
    else:
        config = {}

    session = get_session(client_id, phone)
    step    = session.get("step", "main")

    # Greeting / reset
    if not session or msg in GREETINGS:
        set_session(client_id, phone, {"step": "main"})
        return welcome(client, ctype)

    # Reminder input step (pharmacy only)
    if step == "reminder_wait":
        if msg in GREETINGS or msg == "0":
            set_session(client_id, phone, {"step": "main"})
            return welcome(client, ctype)
        saved = parse_reminder(phone, message, client)
        if saved:
            set_session(client_id, phone, {"step": "main"})
            send_msg(client, client["admin_phone"][-10:],
                     f"⏰ *New Reminder*\nPhone: {phone}\n{message}")
            return "✅ Reminder set ho gaya!\n\nHum aapko samay par remind kar denge 💊\n\nWapas ke liye *0* bhejein"
        return ("Format samajh nahi aaya 😅\n\n"
                "Naam: Aapka Naam\nMedicine: Medicine naam\nKitne din mein khatam hoti hai: 30\n\n"
                "Wapas ke liye *0* bhejein")

    # Intent detection
    intent = detect_intent(msg, ctype)

    if intent == "order":
        set_session(client_id, phone, {"step": "order"})
        return order_reply(client)

    if intent == "menu" and ctype == "restaurant":
        set_session(client_id, phone, {"step": "menu"})
        return menu_reply(client, client_id)

    if intent == "reminder" and ctype == "pharmacy":
        set_session(client_id, phone, {"step": "reminder_wait"})
        return reminder_reply()

    if intent == "location":
        cfg = cached(f"{client_id}_config", lambda: sb_get_config(client)) if client["db"] == "supabase" else {}
        set_session(client_id, phone, {"step": "location"})
        return location_reply(client, cfg)

    if intent == "contact":
        cfg = cached(f"{client_id}_config", lambda: sb_get_config(client)) if client["db"] == "supabase" else {}
        set_session(client_id, phone, {"step": "contact"})
        return contact_reply(client, cfg)

    # Nothing matched
    set_session(client_id, phone, {"step": "main"})
    return unknown_reply(ctype)

# ══════════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ══════════════════════════════════════════════════════════════════
@app.route("/webhook/<client_id>", methods=["POST"])
def webhook(client_id):
    if client_id not in CLIENTS:
        return jsonify({"status": "unknown client"}), 404
    try:
        data    = request.json or {}
        sender  = data.get("sender") or data.get("from", "")
        message = data.get("message") or data.get("text", "")
        if not sender or not message:
            return jsonify({"status": "ignored"}), 200
        client = CLIENTS[client_id]
        admin  = client["admin_phone"].replace("+","").replace(" ","")
        if sender.replace("+","").replace(" ","") == admin:
            return jsonify({"status": "self"}), 200
        reply = process(client_id, sender, message)
        if reply:
            time.sleep(0.5)
            send_msg(client, sender, reply)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"[ERROR webhook/{client_id}] {e}")
        return jsonify({"status": "error", "msg": str(e)}), 500

@app.route("/", methods=["GET"])
def home():
    clients_info = "".join(
        f"<li><b>{cid}</b> ({c['name']}) — <code>/webhook/{cid}</code></li>"
        for cid, c in CLIENTS.items()
    )
    return f"<h2>🤖 Next Gen Web — Multi Bot</h2><ul>{clients_info}</ul>"

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":   "running",
        "clients":  list(CLIENTS.keys()),
        "sessions": len(sessions)
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
