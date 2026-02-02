import yfinance as yf
import requests
import time
from datetime import datetime
import pytz

# ======================
# CONFIG
# ======================
import os

BOT_TOKEN = os.getenv("8395308259:AAE5Jo6PabYbWvdteRHojoBSTR0mdyHA7QM")
CHAT_ID = os.getenv("661470370")


SYMBOL = "CL=F"
TZ = pytz.timezone("Asia/Kolkata")

# Inventory expectations (can be edited weekly)
EXPECTED_EIA = -2.0   # million barrels
EXPECTED_API = -1.5  # million barrels

VOLATILITY_THRESHOLD = 0.6  # % move in 5 minutes

# ======================
# TELEGRAM
# ======================
def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ======================
# PRICE FETCH
# ======================
def get_price():
    data = yf.Ticker(SYMBOL).history(period="1d", interval="1m")
    return round(data["Close"].iloc[-1], 2)

# ======================
# VOLATILITY CHECK
# ======================
def check_volatility(p1, p2):
    return round(((p2 - p1) / p1) * 100, 2)

# ======================
# BIAS ENGINE
# ======================
def bias_engine(expected, actual):
    if actual < expected:
        return "📈 Bullish Surprise (Supply Tightening)"
    elif actual > expected:
        return "📉 Bearish Surprise (Supply Increase)"
    else:
        return "⚖️ Neutral / Noise"

# ======================
# EVENT HANDLER
# ======================
def run_event(event_name, expected):
    now = datetime.now(TZ).strftime("%d %b %Y | %I:%M %p IST")

    pre_price = get_price()
    send(f"🛢️ {event_name} Triggered\nTime: {now}\nPre-Event Price: {pre_price}")

    time.sleep(300)  # 5 min
    price_5m = get_price()
    vol = check_volatility(pre_price, price_5m)

    if abs(vol) >= VOLATILITY_THRESHOLD:
        send(f"⚠️ Volatility Spike Detected\nMove: {vol}% in 5 min")

    time.sleep(600)  # 15 min total
    price_15m = get_price()

    # Simulated actual value (replace with real API later)
    actual_inventory = round(expected + (vol * -1), 2)

    bias = bias_engine(expected, actual_inventory)

    send(
        f"📊 {event_name} Reaction (IST)\n\n"
        f"Expected: {expected}M\n"
        f"Actual: {actual_inventory}M\n\n"
        f"Pre: {pre_price}\n"
        f"5m: {price_5m}\n"
        f"15m: {price_15m}\n\n"
        f"Bias: {bias}"
    )

# ======================
# SCHEDULER LOOP
# ======================
def scheduler():
    send("🚀 Crude Master Bot LIVE (IST)")

    while True:
        now = datetime.now(TZ)

        # API – Tuesday 8:00 PM IST
        if now.weekday() == 1 and now.hour == 20 and now.minute == 0:
            run_event("API Inventory", EXPECTED_API)
            time.sleep(3600)

        # EIA – Wednesday 8:00 PM IST
        if now.weekday() == 2 and now.hour == 20 and now.minute == 0:
            run_event("EIA Inventory", EXPECTED_EIA)
            time.sleep(3600)

        time.sleep(30)

# ======================
# RUN
# ======================
if __name__ == "__main__":
    scheduler()
