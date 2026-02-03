import yfinance as yf
import requests
import time
import pytz
import feedparser
import os
from datetime import datetime, timedelta

# ======================
# ENV CHECK
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
EIA_API_KEY = os.getenv("EIA_API_KEY")

if not all([BOT_TOKEN, CHAT_ID, EIA_API_KEY]):
    raise RuntimeError("❌ Missing ENV variables (BOT_TOKEN / CHAT_ID / EIA_API_KEY)")

# ======================
# CONFIG
# ======================

SYMBOL = "CL=F"
TZ = pytz.timezone("Asia/Kolkata")

EXPECTED_EIA = -2.0
EXPECTED_API = -1.5

VOLATILITY_THRESHOLD = 0.6
BRIEF_HOUR = 9
BRIEF_MINUTE = 0

NEWS_URL = "https://feeds.reuters.com/reuters/energyNews"

KEYWORDS = [
    "oil", "pipeline", "refinery", "opec",
    "sanction", "attack", "war", "export"
]

last_news_time = datetime.now(TZ) - timedelta(hours=2)
last_brief_date = None

# ======================
# TELEGRAM
# ======================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ======================
# PRICE FUNCTIONS
# ======================

def get_price(interval="1m", period="1d"):
    data = yf.Ticker(SYMBOL).history(period=period, interval=interval)
    return round(data["Close"].iloc[-1], 2)

def pct_change(p1, p2):
    return round(((p2 - p1) / p1) * 100, 2)

# ======================
# DAILY MARKET BRIEF
# ======================

def crude_market_brief():
    global last_brief_date

    today = datetime.now(TZ).date()
    if last_brief_date == today:
        return

    now = datetime.now(TZ)

    price_now = get_price()
    price_6h_ago = yf.Ticker(SYMBOL).history(
        period="1d", interval="5m"
    )["Close"].iloc[-72]

    session_move = pct_change(price_6h_ago, price_now)

    if session_move > 0.3:
        bias = "Bullish"
    elif session_move < -0.3:
        bias = "Bearish"
    else:
        bias = "Neutral"

    vol_risk = "LOW"
    if abs(session_move) > VOLATILITY_THRESHOLD:
        vol_risk = "HIGH"

    message = (
        f"🛢️ Crude Oil – Daily Market Brief (IST)\n\n"
        f"WTI Price: {price_now}\n"
        f"Asia Session: {session_move}%\n"
        f"Overnight Bias: {bias}\n\n"
        f"Inventory Bias:\n"
        f"• API Expectation: {EXPECTED_API}M\n"
        f"• EIA Expectation: {EXPECTED_EIA}M\n\n"
        f"Volatility Risk: {vol_risk}\n"
        f"Geo Risk: Monitor headlines\n\n"
        f"🧠 Plan:\n"
        f"• Trade with bias, not emotions\n"
        f"• Reduce size near news events\n"
        f"• Respect volatility zones"
    )

    send(message)
    last_brief_date = today

# ======================
# GEO NEWS (STRICT)
# ======================

def check_news():
    global last_news_time

    feed = feedparser.parse(NEWS_URL)

    for entry in feed.entries[:5]:
        published = datetime(*entry.published_parsed[:6], tzinfo=pytz.UTC).astimezone(TZ)

        if published > last_news_time:
            headline = entry.title.lower()
            if any(k in headline for k in KEYWORDS):
                send(
                    f"🚨 CRUDE RISK ALERT\n\n{entry.title}\n\n⚠️ Possible price impact"
                )
                last_news_time = published

# ======================
# MAIN LOOP
# ======================

def main():
    send("🚀 Crude Master Bot LIVE (IST)")

    while True:
        now = datetime.now(TZ)

        if now.hour == BRIEF_HOUR and now.minute == BRIEF_MINUTE:
            crude_market_brief()
            time.sleep(60)

        check_news()
        time.sleep(30)

# ======================
# RUN
# ======================

if __name__ == "__main__":
    main()
