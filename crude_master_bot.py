import os
import time
import requests
import yfinance as yf
import pytz
import feedparser
from datetime import datetime, timedelta

# ======================
# ENV CONFIG (MANDATORY)
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
EIA_API_KEY = os.getenv("EIA_API_KEY")

if not BOT_TOKEN or not CHAT_ID or not EIA_API_KEY:
    raise RuntimeError("❌ Missing ENV variables (BOT_TOKEN / CHAT_ID / EIA_API_KEY)")

# ======================
# SETTINGS
# ======================

SYMBOL = "CL=F"
TZ = pytz.timezone("Asia/Kolkata")

VOLATILITY_THRESHOLD = 0.6
EXPECTED_EIA = -2.0
EXPECTED_API = -1.5

NEWS_URL = "https://feeds.reuters.com/reuters/energyNews"
NEWS_KEYWORDS = [
    "oil", "pipeline", "refinery", "opec",
    "sanctions", "middle east", "attack",
    "export", "war", "supply"
]

last_news_time = datetime.now(TZ) - timedelta(hours=1)

# ======================
# TELEGRAM
# ======================

def send(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# ======================
# PRICE FUNCTIONS
# ======================

def get_price():
    data = yf.Ticker(SYMBOL).history(period="1d", interval="1m")
    return round(data["Close"].iloc[-1], 2)

def pct_change(a, b):
    return round(((b - a) / a) * 100, 2)

# ======================
# BIAS ENGINE
# ======================

def bias_engine(expected, actual):
    if actual < expected:
        return "📈 Bullish (Supply Tightening)"
    elif actual > expected:
        return "📉 Bearish (Supply Increase)"
    return "⚖️ Neutral"

# ======================
# EIA DATA (REAL)
# ======================

def fetch_eia_actual():
    url = (
        "https://api.eia.gov/v2/petroleum/stocks/data/"
        f"?api_key={EIA_API_KEY}"
        "&frequency=weekly"
        "&data[0]=value"
        "&facets[series]=WCESTUS1"
        "&sort[0][column]=period"
        "&sort[0][direction]=desc"
        "&length=1"
    )
    r = requests.get(url, timeout=10).json()
    return round(r["response"]["data"][0]["value"], 2)

# ======================
# INVENTORY EVENT
# ======================

def run_inventory(event, expected):
    try:
        now = datetime.now(TZ).strftime("%d %b %Y | %I:%M %p IST")
        pre = get_price()

        send(f"🛢️ {event} RELEASE\nTime: {now}\nPre Price: {pre}")

        time.sleep(300)
        p5 = get_price()
        vol = pct_change(pre, p5)

        if abs(vol) >= VOLATILITY_THRESHOLD:
            send(f"⚠️ Volatility Spike\nMove: {vol}% (5 min)")

        time.sleep(300)
        p15 = get_price()

        actual = fetch_eia_actual() if event == "EIA Inventory" else expected
        bias = bias_engine(expected, actual)

        send(
            f"📊 {event} SUMMARY\n\n"
            f"Expected: {expected}M\n"
            f"Actual: {actual}M\n\n"
            f"Pre: {pre}\n5m: {p5}\n15m: {p15}\n\n"
            f"Bias: {bias}"
        )

    except Exception as e:
        send(f"❌ {event} error: {e}")

# ======================
# NEWS MONITOR
# ======================

def check_news():
    global last_news_time

    try:
        feed = feedparser.parse(NEWS_URL)

        for entry in feed.entries[:5]:
            published = datetime(*entry.published_parsed[:6], tzinfo=pytz.UTC).astimezone(TZ)

            if published > last_news_time:
                headline = entry.title.lower()

                if any(k in headline for k in NEWS_KEYWORDS):
                    send(f"🚨 GEO / EMERGENCY NEWS\n\n{entry.title}")
                    last_news_time = published

    except Exception as e:
        print("News error:", e)

# ======================
# SCHEDULER
# ======================

def scheduler():
    send("🚀 Crude Master Bot LIVE (IST)")

    while True:
        now = datetime.now(TZ)

        # API – Tuesday 8 PM IST
        if now.weekday() == 1 and now.hour == 20 and now.minute == 0:
            run_inventory("API Inventory", EXPECTED_API)
            time.sleep(3600)

        # EIA – Wednesday 8 PM IST
        if now.weekday() == 2 and now.hour == 20 and now.minute == 0:
            run_inventory("EIA Inventory", EXPECTED_EIA)
            time.sleep(3600)

        # OPEC Reminder
        if now.weekday() == 0 and now.hour == 17 and now.minute == 0:
            send("⏰ OPEC EVENT TODAY – Expect crude volatility")

        check_news()
        time.sleep(30)

# ======================
# RUN
# ======================

if __name__ == "__main__":
    scheduler()
