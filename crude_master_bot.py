import os
import time
from datetime import datetime
import requests

# ==============================
# ENVIRONMENT VARIABLES
# ==============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==============================
# INVENTORY DATA (UPDATE WEEKLY)
# ==============================
PREVIOUS_INVENTORY = 455.2   # Million Barrels (last week)
CURRENT_INVENTORY = 452.1    # Million Barrels (this week)

# ==============================
# TELEGRAM FUNCTION
# ==============================
def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    requests.post(url, json=payload)

# ==============================
# INVENTORY ANALYSIS
# ==============================
def analyze_inventory():
    change = CURRENT_INVENTORY - PREVIOUS_INVENTORY

    if change < 0:
        return (
            "🛢️ EIA CRUDE INVENTORY REPORT\n\n"
            f"Result: DRAW 🟢\n"
            f"Change: {abs(change):.2f} Million Barrels\n"
            "Bias: BULLISH"
        )
    elif change > 0:
        return (
            "🛢️ EIA CRUDE INVENTORY REPORT\n\n"
            f"Result: BUILD 🔴\n"
            f"Change: +{change:.2f} Million Barrels\n"
            "Bias: BEARISH"
        )
    else:
        return (
            "🛢️ EIA CRUDE INVENTORY REPORT\n\n"
            "Result: NO CHANGE ⚪"
        )

# ==============================
# BOT START MESSAGE
# ==============================
send_message("🚀 Crude Master Bot LIVE (IST)")

# ==============================
# MAIN LOOP
# ==============================
try:
    while True:
        now = datetime.now()

        # --------------------------
        # MARKET OPEN ALERT
        # --------------------------
        if now.hour == 9 and now.minute == 0:
            send_message("📈 Crude Market OPEN (IST)")
            time.sleep(60)

        # --------------------------
        # EIA INVENTORY ALERT
        # Wednesday 8:00 PM IST
        # --------------------------
        if now.weekday() == 2 and now.hour == 20 and now.minute == 0:
            inventory_msg = analyze_inventory()
            send_message(inventory_msg)
            time.sleep(60)

        # --------------------------
        # MARKET CLOSE ALERT
        # --------------------------
        if now.hour == 23 and now.minute == 30:
            send_message("📉 Crude Market CLOSE (IST)")
            time.sleep(60)

        time.sleep(30)

except Exception as e:
    send_message(f"❌ Crude Master Bot CRASHED\nError: {str(e)}")
