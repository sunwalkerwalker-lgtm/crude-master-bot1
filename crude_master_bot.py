import yfinance as yf
import requests
import time
import pytz
import feedparser
import os
from datetime import datetime, timedelta

# ======================
# ENV VALIDATION
# ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
EIA_API_KEY = os.getenv("EIA_API_KEY")

if not BOT_TOKEN or not CHAT_ID or not EIA_API_KEY:
    raise RuntimeError("❌ Missing ENV variables (BOT_TOKEN / CHAT_ID / EIA_API_KEY)")

# ======================
# CONFIG
# ======================
SYMBOL = "CL=F"
TZ = pytz.timezone("Asia/Kolkata")

EXPECTED_EIA = -2.0
EXPECTED_API = -1.5

VOLATILITY_THRESHOLD = 0.6
NEWS_CHECK_INTERVAL = 300

# ======================
# TELEGRAM
# ======================
def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ======================
# PRICE ENGINE
# ======================
def get_price():
    data = yf.Ticker(SYMBOL).history(period="1d", interval="1m")
    return round(data["Close"].iloc[-1], 2)

def pct_change(p1, p2):
    return round(((p2 - p1) / p1) * 100, 2)

# ======================
# BIAS ENGINE
# ======================
def bias_engine(expected, actual):
    if actual < expected:
        return "📈 Bullish (Supply Tightening)"
    elif actual > expected:
        return "📉 Bearish (Supply Increase)"
    else:
        return "⚖️ Neutral"

# ======================
# EIA ACTUAL DATA
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

# ======================
# INVENTORY EVENT
# ======================
def run_inventory(event, expected):
    now = datetime.now(TZ).strftime("%d %b %Y | %I:%M %p IST")

    pre = get_price()
    send(f"🛢️ {event} RELEASE\nTime: {now}\nPre Price: {pre}")

    time.sleep(300)
    p5 = get_price()
    vol = pct_change(pre, p5)

    if abs(vol) >= VOLATILITY_THRESHOLD:
        send(f"⚠️ Volatility Spike\nMove: {vol}% (5 min)")

    time.sleep(600)
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

# ======================
# DAILY MARKET BRIEF
# ======================
last_brief_date = None

def daily_market_brief(now):
    global last_brief_date

    if now.hour == 9 and now.minute == 0:
        if last_brief_date != now.date():
            price = get_price()
            send(
                f"🛢️ CRUDE MARKET BRIEF (IST)\n\n"
                f"WTI Price: {price}\n"
                f"Key Focus:\n"
                f"• Inventory expectations\n"
                f"• OPEC headlines\n"
                f"• US session volatility"
            )
            last_brief_date = now.date()

# ======================
# SCHEDULED ALERTS
# ======================
alert_guard = set()

def scheduled_alerts(now):
    key = f"{now.date()}-{now.hour}-{now.minute}"
    if key in alert_guard:
        return

    # API Reminder
    if now.weekday() == 1 and now.hour == 19 and now.minute == 30:
        send("⏰ API INVENTORY IN 30 MIN\nExpect volatility")
        alert_guard.add(key)

    # EIA Reminder
    if now.weekday() == 2 and now.hour == 19 and now.minute == 30:
        send("⏰ EIA INVENTORY IN 30 MIN\nRisk management advised")
        alert_guard.add(key)

    # OPEC Watch
    if now.weekday() == 0 and now.hour == 10 and now.minute == 0:
        send("🛢️ OPEC WATCH TODAY\nStatements can move crude anytime")
        alert_guard.add(key)

    # US Session Open
    if now.hour == 18 and now.minute == 30:
        send("🇺🇸 US SESSION OPEN\nLiquidity + Directional moves possible")
        alert_guard.add(key)

# ======================
# GEO NEWS
# ======================
NEWS_URL = "https://feeds.reuters.com/reuters/energyNews"
KEYWORDS = [
    "oil", "pipeline", "refinery", "OPEC",
    "sanctions", "export", "war", "attack",
    "supply", "Middle East"
]

last_news_time = datetime.now(TZ) - timedelta(hours=1)

def check_news():
    global last_news_time
    feed = feedparser.parse(NEWS_URL)

    for entry in feed.entries[:5]:
        published = datetime(*entry.published_parsed[:6], tzinfo=pytz.UTC).astimezone(TZ)
        if published > last_news_time:
            headline = entry.title.lower()
            if any(k.lower() in headline for k in KEYWORDS):
                send(f"🚨 CRUDE RISK ALERT\n\n{entry.title}")
                last_news_time = published

# ======================
# MAIN LOOP
# ======================
def main():
    send("🚀 Crude Master Bot LIVE (IST)")

    while True:
        now = datetime.now(TZ)

        daily_market_brief(now)
        scheduled_alerts(now)
        check_news()

        # Inventory Releases
        if now.weekday() == 1 and now.hour == 20 and now.minute == 0:
            run_inventory("API Inventory", EXPECTED_API)
            time.sleep(3600)

        if now.weekday() == 2 and now.hour == 20 and now.minute == 0:
            run_inventory("EIA Inventory", EXPECTED_EIA)
            time.sleep(3600)

        time.sleep(30)

# ======================
# RUN
# ======================
if __name__ == "__main__":
    main()
