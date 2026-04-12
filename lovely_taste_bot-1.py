import os
import json
import time
import requests
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

FONNTE_TOKEN     = os.environ.get("FONNTE_TOKEN", "8mY6hQVX7SYLyX4gQjpc")
SUPABASE_URL     = os.environ.get("SUPABASE_URL", "https://gltnufmbzubdcsbienes.supabase.co")
SUPABASE_KEY     = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdsdG51Zm1ienViZGNzYmllbmVzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5MTE0ODQsImV4cCI6MjA5MTQ4NzQ4NH0.2MA-fXdQPwgON9cD_aTByR4vYg5vmPp5PNBFlYTJVC4")
RESTAURANT_NAME  = "Lovely Taste Restaurant"
RESTAURANT_PHONE = os.environ.get("RESTAURANT_PHONE", "916205131181")

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

_config_cache = {}
_config_cache_time = 0

def get_bot_config():
    global _config_cache, _config_cache_time
    now = time.time()
    if _config_cache and (now - _config_cache_time) < 300:
        return _config_cache
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/bot_config?id=eq.1&select=*", headers=SB_HEADERS, timeout=5)
        data = res.json()
        if data:
            _config_cache = data[0]
            _config_cache_time = now
            return _config_cache
    except Exception as e:
        print(f"[ERROR] get_bot_config: {e}")
    return {
        "is_active": True,
        "offline_message": "Abhi hum available nahi hain. Baad mein try karein.",
        "website_url": "https://lovelytaste.netlify.app",
        "working_hours_start": "10:00",
        "working_hours_end": "22:00",
    }

_menu_cache = []
_menu_cache_time = 0

def get_menu():
    global _menu_cache, _menu_cache_time
    now = time.time()
    if _menu_cache and (now - _menu_cache_time) < 300:
        return _menu_cache
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/menu_items?available=eq.true&select=*&order=category", headers=SB_HEADERS, timeout=5)
        data = res.json()
        if data:
            _menu_cache = data
            _menu_cache_time = now
            return _menu_cache
    except Exception as e:
        print(f"[ERROR] get_menu: {e}")
    return []

def upsert_customer(phone):
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/customers",
            headers={**SB_HEADERS, "Prefer": "resolution=merge-duplicates"},
            json={"phone": phone, "last_seen": datetime.utcnow().isoformat(), "provider": "whatsapp"},
            timeout=5
        )
    except Exception as e:
        print(f"[ERROR] upsert_customer: {e}")

def is_working_hours(config):
    try:
        start_h, start_m = map(int, config["working_hours_start"].split(":"))
        end_h, end_m = map(int, config["working_hours_end"].split(":"))
        now = datetime.now()
        start = now.replace(hour=start_h, minute=start_m, second=0)
        end = now.replace(hour=end_h, minute=end_m, second=0)
        return start <= now <= end
    except:
        return True

sessions = {}

def get_session(phone):
    now = time.time()
    if phone in sessions:
        if now - sessions[phone].get("t", 0) > 600:
            del sessions[phone]
            return {}
        return sessions[phone]
    return {}

def set_session(phone, data):
    sessions[phone] = {**data, "t": time.time()}

def clear_session(phone):
    sessions.pop(phone, None)

def welcome_msg(config):
    if config.get("welcome_message"):
        return config["welcome_message"]
    return f"""🍽️ *{RESTAURANT_NAME}*
Namaskar! Swagat hai aapka 🙏

Aap kya karna chahte hain?

*1️⃣* 🛒 Order karna hai
*2️⃣* 📋 Menu dekhna hai
*3️⃣* 📍 Location & Timing
*4️⃣* 📞 Humse baat karein

Sirf number bhejein — *1, 2, 3 ya 4*"""

def order_msg(config):
    url = config.get("website_url", "https://lovelytaste.netlify.app")
    return f"""🛒 *ONLINE ORDER*

Aap hamare website se order kar sakte hain:

👉 *{url}*

Website par aap:
✅ Poora menu dekh sakte hain
✅ Cart mein item add kar sakte hain
✅ Delivery / Pickup / Dine-in choose kar sakte hain
✅ Order place karne ke baad WhatsApp pe confirmation milega!

Koi dikkat ho toh *4* bhejein 😊"""

def menu_msg(config):
    url = config.get("website_url", "https://lovelytaste.netlify.app")
    items = get_menu()
    if not items:
        return f"📋 *HAMARA MENU*\n\nMenu abhi load nahi ho pa raha.\nDirect website pe dekho 👉 *{url}*\n\nWapas ke liye *0* bhejein"

    categories = {}
    for item in items:
        cat = item.get("category", "Other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    cat_order = ["Starters", "Main Course", "Rice & Biryani", "Breads", "Desserts", "Beverages"]
    cat_emojis = {"Starters": "🥗", "Main Course": "🍛", "Rice & Biryani": "🍚", "Breads": "🫓", "Desserts": "🍮", "Beverages": "🥭"}

    msg = "📋 *HAMARA MENU*\n"
    for cat in cat_order:
        if cat not in categories:
            continue
        emoji = cat_emojis.get(cat, "🍽️")
        msg += f"\n*{emoji} {cat}*\n"
        for item in categories[cat]:
            msg += f"{item.get('emoji','•')} {item.get('name','')} — ₹{item.get('price',0)}\n"

    msg += f"\n👉 Order karne ke liye: *{url}*\n\nWapas main menu ke liye *0* bhejein"
    return msg

def location_msg(config):
    url = config.get("website_url", "https://lovelytaste.netlify.app")
    start = config.get("working_hours_start", "10:00")
    end = config.get("working_hours_end", "22:00")
    return f"""📍 *{RESTAURANT_NAME}*

🏠 *Address:* Patna, Bihar
⏰ *Timing:* {start} – {end} (Daily)
🌐 *Website:* {url}

👉 Online order: *{url}*

Wapas ke liye *0* bhejein"""

def contact_msg(config):
    url = config.get("website_url", "https://lovelytaste.netlify.app")
    start = config.get("working_hours_start", "10:00")
    end = config.get("working_hours_end", "22:00")
    return f"""📞 *CONTACT US*

📱 *WhatsApp / Call:* +91 {RESTAURANT_PHONE[-10:]}
🌐 *Website:* {url}
⏰ *Available:* {start} – {end}

Hum madad ke liye hamesha taiyaar hain! 🙏

Wapas ke liye *0* bhejein"""

def unknown_msg():
    return """Maafi chahte hain, yeh samajh nahi aaya 😅

Kripya inme se ek number bhejein:
*1* — 🛒 Order karna hai
*2* — 📋 Menu dekhna hai
*3* — 📍 Location & Timing
*4* — 📞 Humse baat karein"""

GREETINGS = ["hi","hello","hlo","hii","hey","namaskar","namaste","hy","helo","start","menu","order","help","0","back","wapas","reset"]

def process_message(phone, message):
    msg = message.strip().lower()
    config = get_bot_config()

    if not config.get("is_active", True):
        return config.get("offline_message", "Abhi hum available nahi hain.")

    if not is_working_hours(config):
        return config.get("offline_message", "Abhi hum available nahi hain.")

    session = get_session(phone)
    upsert_customer(phone)

    if not session or msg in GREETINGS:
        set_session(phone, {"step": "main"})
        return welcome_msg(config)

    if msg == "1":
        set_session(phone, {"step": "order"})
        return order_msg(config)
    if msg == "2":
        set_session(phone, {"step": "menu"})
        return menu_msg(config)
    if msg == "3":
        set_session(phone, {"step": "location"})
        return location_msg(config)
    if msg == "4":
        set_session(phone, {"step": "contact"})
        return contact_msg(config)

    set_session(phone, {"step": "main"})
    return welcome_msg(config)

def send_message(to, message):
    try:
        resp = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": FONNTE_TOKEN, "Content-Type": "application/json"},
            json={"target": to, "message": message, "countryCode": "91"},
            timeout=10
        )
        print(f"[SENT → {to}] {resp.json()}")
    except Exception as e:
        print(f"[ERROR] send_message: {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json or {}
        sender = data.get("sender") or data.get("from", "")
        message = data.get("message") or data.get("text", "")
        if not sender or not message:
            return jsonify({"status": "ignored"}), 200
        if sender == RESTAURANT_PHONE:
            return jsonify({"status": "self"}), 200
        reply = process_message(sender, message)
        if reply:
            time.sleep(0.5)
            send_message(sender, reply)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"[ERROR] webhook: {e}")
        return jsonify({"status": "error", "msg": str(e)}), 500

@app.route("/", methods=["GET"])
def home():
    return f"<h2>🍽️ {RESTAURANT_NAME} — WhatsApp Bot</h2><p>Webhook: /webhook</p>"

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running", "bot": RESTAURANT_NAME, "sessions": len(sessions)})

@app.route("/refresh-cache", methods=["POST"])
def refresh_cache():
    global _config_cache_time, _menu_cache_time
    _config_cache_time = 0
    _menu_cache_time = 0
    return jsonify({"status": "cache refreshed"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
