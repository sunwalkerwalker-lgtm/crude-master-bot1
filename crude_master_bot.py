import yfinance as yf
import requests
import time
import pytz
import feedparser
import os
import pandas as pd
from datetime import datetime, timedelta

# ======================
# ENV CHECK
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

EXPECTED_API = -1.5
EXPECTED_EIA = -2.0

VOL_5M_THRESHOLD = 0.5
VOL_1H_THRESHOLD = 1.0

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

NEWS_URL = "https://feeds.reuters.com/reuters/energyNews"

NEWS_KEYWORDS = [
    "oil", "OPEC", "pipeline", "refinery",
    "sanctions", "Middle East", "attack",
    "export", "war", "supply", "strike"
]

# ======================
# TELEGRAM
# ======================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ======================
# PRICE DATA
# ======================

def get_price(interval="1m", period="1d"):
    return yf.Ticker(SYMBOL).history(interval=interval, period=period)

def pct(p1, p2):
    return round(((p2 - p1) / p1) * 100, 2)

# ======================
# RSI CALCULATION
# ======================

def calculate_rsi(data, period=14):
    delta = data.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

# ======================
# SESSION ALERTS
# ======================

def session_alerts(now):
    if now.hour == 6 and now.minute == 0:
        send("🌏 ASIA SESSION OPEN\nLow liquidity → false breakouts possible")

    if now.hour == 13 and now.minute == 30:
        send("🇪🇺 EUROPE SESSION OPEN\nWatch trend continuation")

    if now.hour == 18 and now.minute == 30:
        send("🇺🇸 US SESSION OPEN\n⚠️ High volatility window")

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
            f"⚠️ 1H VOLATILITY ALERT\n\n"
            f"Move: {move}%\n"
            f"Price: {round(last,2)}\n\n"
            f"Possible Reasons:\n"
            f"• Session liquidity shift\n"
            f"• Stop hunt\n"
            f"• Headline driven move"
        )
        last_1h_alert = now

# ======================
# RSI ALERTS
# ======================

last_rsi_alert = None

def check_rsi():
    global last_rsi_alert

    data = get_price(interval="15m", period="3d")
    rsi = calculate_rsi(data["Close"])

    price = data["Close"].iloc[-1]
    now = datetime.now(TZ)

    if rsi >= RSI_OVERBOUGHT and last_rsi_alert != "OB":
        send(
            f"📉 RSI OVERBOUGHT ALERT\n\n"
            f"RSI: {round(rsi,1)}\n"
            f"Price: {round(price,2)}\n\n"
            f"⚠️ Pullback / consolidation risk"
        )
        last_rsi_alert = "OB"

    elif rsi <= RSI_OVERSOLD and last_rsi_alert != "OS":
        send(
            f"📈 RSI OVERSOLD ALERT\n\n"
            f"RSI: {round(rsi,1)}\n"
            f"Price: {round(price,2)}\n\n"
            f"⚠️ Short covering bounce possible"
        )
        last_rsi_alert = "OS"

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

def bias(expected, actual):
    if actual < expected:
        return "📈 Bullish (Supply Tightening)"
    elif actual > expected:
        return "📉 Bearish (Supply Build)"
    return "⚖️ Neutral"

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
        f"Watchlist:\n"
        f"• Inventory data\n"
        f"• OPEC headlines\n"
        f"• US session volatility\n"
        f"• RSI extremes"
    )

# ======================
# MAIN LOOP
# ======================

def main():
    send("🚀 Crude Master Bot LIVE (IST)")

    last_brief_day = None

    while True:
        try:
            now = datetime.now(TZ)

            session_alerts(now)
            check_1h_volatility()
            check_rsi()
            check_news()

            if now.hour == 9 and now.minute == 0 and last_brief_day != now.date():
                daily_brief()
                last_brief_day = now.date()

            if now.weekday() == 2 and now.hour == 19 and now.minute == 30:
                send("⏰ EIA INVENTORY IN 30 MIN\nRisk management advised")

            time.sleep(30)

        except Exception as e:
            send(f"⚠️ BOT ERROR\n{str(e)}")
            time.sleep(60)

# ======================
# RUN
# ======================

if __name__ == "__main__":
    main()
