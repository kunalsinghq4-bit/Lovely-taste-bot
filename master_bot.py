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

    "royaldarbar": {
        "type":           "restaurant",
        "name":           "Royal Darbar Restaurant & Resort",
        "fonnte_token":   os.environ.get("ROYAL_FONNTE", "bixhuKjh9aJb87X2DCKT"),
        "admin_phone":    os.environ.get("ROYAL_PHONE",  "916205131181"),
        "website":        os.environ.get("ROYAL_WEBSITE", "https://royal-darbar.netlify.app"),
        "timing_start":   os.environ.get("ROYAL_START", "10:00"),
        "timing_end":     os.environ.get("ROYAL_END", "23:00"),
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
                "id": doc["name"].split("/")[-1],
                "name": fb_val(fields.get("name")),
                "price": fb_val(fields.get("price")),
                "category": fb_val(fields.get("category")),
                "emoji": fb_val(fields.get("emoji")),
            })
        return menu
    except:
        return []

# ══════════════════════════════════════════════════════════════════
#  MESSAGING
# ══════════════════════════════════════════════════════════════════
def send_msg(client, phone, text):
    try:
        url = "https://api.fonnte.com/send"
        payload = {"target": phone, "message": text}
        headers = {"Authorization": client["fonnte_token"]}
        requests.post(url, json=payload, headers=headers, timeout=5)
    except:
        pass

# ══════════════════════════════════════════════════════════════════
#  INTENT DETECTION
# ══════════════════════════════════════════════════════════════════
def detect_intent(msg, ctype):
    msg_lower = msg.lower()
    if any(w in msg_lower for w in ["1", "order"]):
        return "order"
    if any(w in msg_lower for w in ["2", "menu"]):
        return "menu"
    if any(w in msg_lower for w in ["3", "table", "booking"]):
        return "table"
    if any(w in msg_lower for w in ["4", "event"]):
        return "event"
    if any(w in msg_lower for w in ["5", "track"]):
        return "track"
    if any(w in msg_lower for w in ["6", "location", "address"]):
        return "location"
    if any(w in msg_lower for w in ["7", "contact", "phone"]):
        return "contact"
    return None

# ══════════════════════════════════════════════════════════════════
#  REPLY FUNCTIONS
# ══════════════════════════════════════════════════════════════════
def menu_reply(client, client_id):
    if client["db"] == "supabase":
        items = cached(f"{client_id}_menu", lambda: sb_get_menu(client), ttl=300)
    else:
        items = cached(f"{client_id}_menu", lambda: fb_get_menu(client), ttl=300)
    
    if not items:
        return f"Menu update mein hai! Baad mein try karna 😊\n\nWapas ke liye *0* bhejein"
    
    text = f"📋 *{client['name']} — Menu*\n\n"
    for item in items:
        emoji = item.get("emoji", "🍽️")
        name = item.get("name", "?")
        price = item.get("price", "?")
        text += f"{emoji} {name} — ₹{price}\n"
    
    text += "\nOrder karne ke liye *1* bhejein\nWapas ke liye *0* bhejein"
    return text

def order_reply(client):
    return f"🛒 *Order Online*\n\nWebsite: {client['website']}\n\nWapas ke liye *0* bhejein"

def table_reply():
    return "📅 *Table Booking*\n\nApna naam likho:\n(Iska baad hum phone puchenge)"

def event_reply():
    return "🎉 *Event Booking*\n\nEvent type likho (Wedding/Birthday/Corporate):"

def track_reply():
    return "📦 *Order Tracking*\n\nApna Order ID likho:"

def location_reply(client):
    loc = client.get("location", "Address update mein hai")
    return f"📍 *Location*\n\n{loc}\n\n⏰ {client['timing_start']} - {client['timing_end']}\n\nWapas ke liye *0* bhejein"

def contact_reply(client):
    return f"📞 *Contact*\n\n📱 {client['admin_phone']}\n🌐 {client['website']}\n\nWapas ke liye *0* bhejein"

def welcome_reply(ctype):
    if ctype == "restaurant":
        return ("🍽️ *Welcome!*\n\n1️⃣ Order करो\n2️⃣ Menu देखो\n3️⃣ Table Booking\n4️⃣ Event Booking\n5️⃣ Order Track करो\n6️⃣ Address\n7️⃣ Contact\n\nKoई भी नंबर भेजो!")
    return ("💊 *Welcome!*\n\n1️⃣ Order करो\n2️⃣ Products\n6️⃣ Address\n7️⃣ Contact\n\nKoई भी नंबर भेजो!")

def unknown_reply(ctype):
    return "Sorry, didn't understand! 😅\nSend *0* for menu"

# ══════════════════════════════════════════════════════════════════
#  MAIN PROCESSOR
# ══════════════════════════════════════════════════════════════════
def process(client_id, phone, msg):
    client = CLIENTS[client_id]
    ctype = client["type"]
    sess = get_session(client_id, phone)
    step = sess.get("step", "main")
    
    msg = msg.strip()
    
    if step == "main" or msg == "0":
        set_session(client_id, phone, {"step": "main"})
        return welcome_reply(ctype)
    
    # Booking flow
    if step == "table":
        if "name" not in sess:
            set_session(client_id, phone, {"step": "table", "name": msg})
            return "Phone number likho:"
        if "phone" not in sess:
            set_session(client_id, phone, {**sess, "phone": msg})
            return "Date likho (DD-MM-YYYY):"
        if "date" not in sess:
            set_session(client_id, phone, {**sess, "date": msg})
            return "Time likho (HH:MM):"
        # Confirm
        set_session(client_id, phone, {"step": "main"})
        send_msg(client, client["admin_phone"], f"New booking from {sess['name']}: {sess['phone']}")
        return "✅ Booking request submitted!\n\nWapas ke liye *0* bhejein"
    
    # Intent detection
    intent = detect_intent(msg, ctype)
    
    if intent == "order":
        return order_reply(client)
    if intent == "menu":
        return menu_reply(client, client_id)
    if intent == "table":
        set_session(client_id, phone, {"step": "table"})
        return table_reply()
    if intent == "event":
        return event_reply()
    if intent == "track":
        return track_reply()
    if intent == "location":
        return location_reply(client)
    if intent == "contact":
        return contact_reply(client)
    
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
        reply = process(client_id, sender, message)
        if reply:
            time.sleep(0.5)
            send_msg(client, sender, reply)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error"}), 500

@app.route("/", methods=["GET"])
def home():
    clients = "".join(f"<li><b>{cid}</b> — /webhook/{cid}</li>" for cid in CLIENTS.keys())
    return f"<h2>🤖 Next Gen Web — Master Bot (3 Clients)</h2><ul>{clients}</ul>"

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running", "clients": list(CLIENTS.keys()), "sessions": len(sessions)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
