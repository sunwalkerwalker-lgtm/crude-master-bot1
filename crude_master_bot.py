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

if not BOT_TOKEN or not CHAT_ID or not EIA_API_KEY:
    raise RuntimeError("❌ Missing ENV variables")

# ======================
# CONFIG
# ======================

SYMBOL = "CL=F"
TZ = pytz.timezone("Asia/Kolkata")

EXPECTED_API = -1.5
EXPECTED_EIA = -2.0

VOL_5M_THRESHOLD = 0.6
VOL_1H_THRESHOLD = 1.2

NEWS_URL = "https://feeds.reuters.com/reuters/energyNews"

NEWS_KEYWORDS = [
    "oil", "OPEC", "pipeline", "refinery", "sanctions",
    "Middle East", "attack", "export", "war", "supply"
]

# ======================
# TELEGRAM
# ======================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ======================
# PRICE HELPERS
# ======================

def get_price(interval="1m", period="1d"):
    return yf.Ticker(SYMBOL).history(interval=interval, period=period)

def pct(p1, p2):
    return round(((p2 - p1) / p1) * 100, 2)

# ======================
# SESSION ALERTS
# ======================

def session_alerts(now):
    if now.hour == 6 and now.minute == 0:
        send("🌏 ASIA SESSION OPEN\nLow liquidity → false moves possible")

    if now.hour == 13 and now.minute == 30:
        send("🇪🇺 EUROPE SESSION OPEN\nTrend continuation / reversals")

    if now.hour == 18 and now.minute == 30:
        send("🇺🇸 US SESSION OPEN\n⚠️ High liquidity + stop hunts")

# ======================
# VOLATILITY ENGINE
# ======================

last_1h_alert = datetime.now(TZ) - timedelta(hours=2)

def check_1h_volatility():
    global last_1h_alert

    data = get_price(interval="1h", period="2d")
    if len(data) < 2:
        return

    prev = data["Close"].iloc[-2]
    last = data["Close"].iloc[-1]
    move = pct(prev, last)

    now = datetime.now(TZ)

    if abs(move) >= VOL_1H_THRESHOLD and (now - last_1h_alert).seconds > 3600:
        send(
            f"⚠️ ABNORMAL 1H MOVE\n\n"
            f"Move: {move}%\n"
            f"Price: {round(last,2)}\n\n"
            f"Likely Causes:\n"
            f"• Session liquidity\n"
            f"• Stop run\n"
            f"• Headline risk"
        )
        last_1h_alert = now

# ======================
# EIA DATA
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
    r = requests.get(url).json()
    return round(r["response"]["data"][0]["value"], 2)

def bias(expected, actual):
    if actual < expected:
        return "📈 Bullish (Supply Tightening)"
    elif actual > expected:
        return "📉 Bearish (Supply Build)"
    return "⚖️ Neutral"

# ======================
# INVENTORY EVENTS
# ======================

def inventory_event(name, expected, is_eia=False):
    pre = get_price()["Close"].iloc[-1]
    send(f"🛢️ {name} RELEASE\nPre Price: {round(pre,2)}")

    time.sleep(900)

    post = get_price()["Close"].iloc[-1]
    actual = fetch_eia_actual() if is_eia else expected

    send(
        f"📊 {name} SUMMARY\n\n"
        f"Expected: {expected}M\n"
        f"Actual: {actual}M\n\n"
        f"Pre: {round(pre,2)}\n"
        f"Post: {round(post,2)}\n\n"
        f"Bias: {bias(expected, actual)}"
    )

# ======================
# NEWS SCANNER
# ======================

last_news_time = datetime.now(TZ) - timedelta(hours=1)

def check_news():
    global last_news_time
    feed = feedparser.parse(NEWS_URL)

    for e in feed.entries[:5]:
        published = datetime(*e.published_parsed[:6], tzinfo=pytz.UTC).astimezone(TZ)

        if published > last_news_time:
            if any(k.lower() in e.title.lower() for k in NEWS_KEYWORDS):
                send(f"🚨 ENERGY HEADLINE\n\n{e.title}")
                last_news_time = published

# ======================
# DAILY BRIEF
# ======================

def daily_brief():
    price = get_price()["Close"].iloc[-1]
    send(
        f"🛢️ CRUDE MARKET BRIEF (IST)\n\n"
        f"WTI: {round(price,2)}\n\n"
        f"Key Focus:\n"
        f"• Inventory expectations\n"
        f"• OPEC headlines\n"
        f"• US session volatility"
    )

# ======================
# MAIN LOOP
# ======================

def main():
    send("🚀 Crude Master Bot LIVE (IST)")

    last_brief_day = None

    while True:
        now = datetime.now(TZ)

        session_alerts(now)
        check_1h_volatility()
        check_news()

        # Daily brief at 9 AM IST
        if now.hour == 9 and now.minute == 0 and last_brief_day != now.date():
            daily_brief()
            last_brief_day = now.date()

        # Inventory warnings
        if now.weekday() == 2 and now.hour == 19 and now.minute == 30:
            send("⏰ EIA INVENTORY IN 30 MIN\nRisk management advised")

        # API inventory
        if now.weekday() == 1 and now.hour == 20 and now.minute == 0:
            inventory_event("API Inventory", EXPECTED_API)
            time.sleep(3600)

        # EIA inventory
        if now.weekday() == 2 and now.hour == 20 and now.minute == 0:
            inventory_event("EIA Inventory", EXPECTED_EIA, True)
            time.sleep(3600)

        time.sleep(30)

# ======================
# RUN
# ======================

if __name__ == "__main__":
    main()
