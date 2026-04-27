import os
import time
import requests
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════════
#  CLIENT REGISTRY — 3 Clients
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
        "location":       "Patna, Bihar",
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
        "location":       "Patna, Bihar",
        "db":             "firebase",
        "firebase_project": "medisoft-e12bf",
    },

    "royaldarbar": {
        "type":           "restaurant",
        "name":           "Royal Darbar Restaurant & Resort",
        "fonnte_token":   os.environ.get("ROYAL_FONNTE", "bixhuKjh9aJb87X2DCKT"),
        "admin_phone":    os.environ.get("ROYAL_PHONE",  "918434928777"),
        "website":        os.environ.get("ROYAL_WEBSITE", "https://royal-darbar.netlify.app"),
        "timing_start":   "10:00",
        "timing_end":     "23:00",
        "location":       "Matiara Tok, Sarai, Bihar",
        "db":             "firebase",
        "firebase_project": "royal-darbar-1",
    },

}

# ══════════════════════════════════════════════════════════════════
#  SESSION MANAGEMENT (per client, 10 min timeout)
# ══════════════════════════════════════════════════════════════════
sessions = {}

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
#  CACHE
# ══════════════════════════════════════════════════════════════════
_cache = {}

def cached(key, fetcher, ttl=300):
    now = time.time()
    if key in _cache and (now - _cache[key][1]) < ttl:
        return _cache[key][0]
    data = fetcher()
    _cache[key] = (data, now)
    return data

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
    except:
        return {}

def sb_get_menu(client):
    try:
        res = requests.get(
            f"{client['supabase_url']}/rest/v1/menu_items?available=eq.true&select=*&order=category",
            headers=sb_headers(client), timeout=5
        )
        return res.json() or []
    except:
        return []

# ── Firebase ──
def fb_base(client):
    proj = client["firebase_project"]
    return f"https://firestore.googleapis.com/v1/projects/{proj}/databases/(default)/documents"

def fb_val(field):
    if not field: return None
    for t in ["stringValue","booleanValue","integerValue","doubleValue"]:
        if t in field: return field[t]
    return None

def fb_get_menu(client):
    try:
        res = requests.get(f"{fb_base(client)}/menu", timeout=8)
        docs = res.json().get("documents", [])
        menu = []
        for doc in docs:
            fields = doc.get("fields", {})
            menu.append({
                "id":       doc["name"].split("/")[-1],
                "name":     fb_val(fields.get("name")),
                "price":    fb_val(fields.get("price")),
                "category": fb_val(fields.get("category")),
                "emoji":    fb_val(fields.get("emoji")),
            })
        return menu
    except:
        return []

# ══════════════════════════════════════════════════════════════════
#  MESSAGING — FIXED: use data= not json= for Fonnte
# ══════════════════════════════════════════════════════════════════
def send_msg(client, phone, text):
    try:
        phone = str(phone).replace("+","").replace(" ","").replace("-","")
        url = "https://api.fonnte.com/send"
        payload = {
            "target":      phone,
            "message":     text,
            "countryCode": "91"
        }
        headers = {"Authorization": client["fonnte_token"]}
        r = requests.post(url, data=payload, headers=headers, timeout=10)
        print(f"[FONNTE] {phone} → {r.status_code} | {r.text[:100]}")
    except Exception as e:
        print(f"[SEND ERROR] {e}")

# ══════════════════════════════════════════════════════════════════
#  INTENT DETECTION
# ══════════════════════════════════════════════════════════════════
def detect_intent(msg, ctype):
    m = msg.lower().strip()
    if m == "1" or "order" in m:                          return "order"
    if m == "2" or "menu" in m:                           return "menu"
    if m == "3" or "table" in m or "booking" in m:        return "table"
    if m == "4" or "event" in m:                          return "event"
    if m == "5" or "track" in m:                          return "track"
    if m == "6" or "location" in m or "address" in m:     return "location"
    if m == "7" or "contact" in m:                        return "contact"
    if ctype == "pharmacy" and ("reminder" in m or "remind" in m): return "reminder"
    return None

# ══════════════════════════════════════════════════════════════════
#  REPLY FUNCTIONS
# ══════════════════════════════════════════════════════════════════
def welcome_reply(client):
    ctype = client["type"]
    name  = client["name"]
    if ctype == "restaurant":
        return (f"🍽️ *{name}* mein aapka swagat hai!\n\n"
                "1️⃣ Order karo\n"
                "2️⃣ Menu dekho\n"
                "3️⃣ Table Booking\n"
                "4️⃣ Event Booking\n"
                "5️⃣ Order Track karo\n"
                "6️⃣ Address & Timing\n"
                "7️⃣ Contact\n\n"
                "Koi bhi number bhejo! 😊")
    else:
        return (f"💊 *{name}* mein aapka swagat hai!\n\n"
                "1️⃣ Order karo\n"
                "2️⃣ Products dekho\n"
                "3️⃣ Reminder set karo\n"
                "6️⃣ Address & Timing\n"
                "7️⃣ Contact\n\n"
                "Koi bhi number bhejo! 😊")

def menu_reply(client, client_id):
    if client["db"] == "supabase":
        items = cached(f"{client_id}_menu", lambda: sb_get_menu(client), ttl=300)
    else:
        items = cached(f"{client_id}_menu", lambda: fb_get_menu(client), ttl=300)

    if not items:
        return "Menu abhi update ho raha hai! Thodi der baad try karo 😊\n\n*0* bhejo wapas jaane ke liye"

    by_cat = {}
    for item in items:
        cat = item.get("category") or "Other"
        by_cat.setdefault(cat, []).append(item)

    text = f"📋 *{client['name']} — Menu*\n\n"
    for cat, its in by_cat.items():
        text += f"*{cat}*\n"
        for it in its:
            emoji = it.get("emoji") or "🍽️"
            name  = it.get("name", "?")
            price = it.get("price", "?")
            text += f"{emoji} {name} — ₹{price}\n"
        text += "\n"
    text += "Order ke liye *1* bhejo\n*0* bhejo wapas jaane ke liye"
    return text

def order_reply(client):
    return (f"🛒 *Order karo*\n\n"
            f"Website visit karo:\n{client['website']}\n\n"
            f"Ya seedha order details yahan bhejo!\n\n"
            f"*0* bhejo wapas jaane ke liye")

def location_reply(client):
    loc = client.get("location", "Address update ho raha hai")
    return (f"📍 *Address*\n\n{loc}\n\n"
            f"⏰ *Timing*: {client['timing_start']} - {client['timing_end']}\n\n"
            f"🌐 {client['website']}\n\n"
            f"*0* bhejo wapas jaane ke liye")

def contact_reply(client):
    return (f"📞 *Contact*\n\n"
            f"📱 {client['admin_phone']}\n"
            f"🌐 {client['website']}\n\n"
            f"*0* bhejo wapas jaane ke liye")

# ══════════════════════════════════════════════════════════════════
#  MAIN PROCESSOR — FIXED: proper step logic
# ══════════════════════════════════════════════════════════════════
def process(client_id, phone, msg):
    client = CLIENTS[client_id]
    ctype  = client["type"]
    sess   = get_session(client_id, phone)
    step   = sess.get("step", "main")
    msg    = msg.strip()

    # 0 always resets to main menu
    if msg == "0":
        set_session(client_id, phone, {"step": "main"})
        return welcome_reply(client)

    # ── Table booking flow ──
    if step == "table":
        if "name" not in sess:
            set_session(client_id, phone, {"step": "table", "name": msg})
            return "📱 Apna phone number bhejo:"
        if "phone" not in sess:
            set_session(client_id, phone, {**sess, "phone": msg})
            return "📅 Date bhejo (DD-MM-YYYY):"
        if "date" not in sess:
            set_session(client_id, phone, {**sess, "date": msg})
            return "⏰ Time bhejo (HH:MM):"
        if "time" not in sess:
            set_session(client_id, phone, {**sess, "time": msg})
            return "👥 Kitne guests aayenge?"
        # Final step
        guests = msg
        admin_msg = (f"🆕 *Table Booking*\n"
                     f"Naam: {sess['name']}\n"
                     f"Phone: {sess['phone']}\n"
                     f"Date: {sess['date']}\n"
                     f"Time: {sess['time']}\n"
                     f"Guests: {guests}")
        send_msg(client, client["admin_phone"], admin_msg)
        set_session(client_id, phone, {"step": "main"})
        return "✅ Booking request submit ho gayi!\n\nHum jald contact karenge 🎉\n\n*0* bhejo wapas jaane ke liye"

    # ── Event booking flow ──
    if step == "event":
        if "etype" not in sess:
            set_session(client_id, phone, {"step": "event", "etype": msg})
            return "👥 Kitne guests honge?"
        if "guests" not in sess:
            set_session(client_id, phone, {**sess, "guests": msg})
            return "💰 Approximate budget kya hai?"
        budget = msg
        admin_msg = (f"🎉 *Event Inquiry*\n"
                     f"Type: {sess['etype']}\n"
                     f"Guests: {sess['guests']}\n"
                     f"Budget: {budget}")
        send_msg(client, client["admin_phone"], admin_msg)
        set_session(client_id, phone, {"step": "main"})
        return "✅ Event inquiry submit ho gayi!\n\nHum jald contact karenge 🎊\n\n*0* bhejo wapas jaane ke liye"

    # ── Reminder flow (pharmacy) ──
    if step == "reminder_wait":
        set_session(client_id, phone, {"step": "main"})
        return "✅ Reminder note kar liya!\n\n*0* bhejo wapas jaane ke liye"

    # ── Intent detection (main step) ──
    intent = detect_intent(msg, ctype)

    if intent == "order":
        set_session(client_id, phone, {"step": "order"})
        return order_reply(client)

    if intent == "menu":
        set_session(client_id, phone, {"step": "menu"})
        return menu_reply(client, client_id)

    if intent == "table" and ctype == "restaurant":
        set_session(client_id, phone, {"step": "table"})
        return "📅 *Table Booking*\n\nApna naam bhejo:"

    if intent == "event" and ctype == "restaurant":
        set_session(client_id, phone, {"step": "event"})
        return "🎉 *Event Booking*\n\nEvent type bhejo (Wedding/Birthday/Corporate):"

    if intent == "track":
        return f"📦 *Order Track karo*\n\nWebsite par jakar track karo:\n{client['website']}\n\n*0* bhejo wapas jaane ke liye"

    if intent == "location":
        set_session(client_id, phone, {"step": "location"})
        return location_reply(client)

    if intent == "contact":
        set_session(client_id, phone, {"step": "contact"})
        return contact_reply(client)

    if intent == "reminder" and ctype == "pharmacy":
        set_session(client_id, phone, {"step": "reminder_wait"})
        return "💊 *Reminder*\n\nMedicine ka naam aur time bhejo:"

    # No intent matched - show welcome
    set_session(client_id, phone, {"step": "main"})
    return welcome_reply(client)

# ══════════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ══════════════════════════════════════════════════════════════════
@app.route("/webhook/<client_id>", methods=["POST"])
def webhook(client_id):
    if client_id not in CLIENTS:
        return jsonify({"status": "unknown client"}), 404
    try:
        data    = request.json or {}
        print(f"[WEBHOOK/{client_id}] Raw: {data}")

        sender  = (data.get("sender") or data.get("from") or "").strip()
        message = (data.get("message") or data.get("text") or "").strip()

        if not sender or not message:
            return jsonify({"status": "ignored"}), 200

        client      = CLIENTS[client_id]
        admin_clean  = client["admin_phone"].replace("+","").replace(" ","")
        sender_clean = sender.replace("+","").replace(" ","")

        if sender_clean == admin_clean:
            return jsonify({"status": "self"}), 200

        print(f"[WEBHOOK/{client_id}] From: {sender} | Msg: {message}")

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
        f"<li><b>{cid}</b> ({c['name']}) — /webhook/{cid}</li>"
        for cid, c in CLIENTS.items()
    )
    return f"<h2>🤖 Next Gen Web — Master Bot (3 Clients)</h2><ul>{clients_info}</ul><p>✅ Running</p>"

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
