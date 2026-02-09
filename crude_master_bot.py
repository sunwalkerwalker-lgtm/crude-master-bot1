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

VOL_1H_THRESHOLD = 1.2
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

NEWS_URL = "https://feeds.reuters.com/reuters/energyNews"

NEWS_KEYWORDS = [
    "oil", "OPEC", "pipeline", "refinery", "sanctions",
    "Middle East", "attack", "export", "war", "supply"
]

# ======================
# STATE (ANTI-SPAM)
# ======================

state = {
    "asia_alerted": False,
    "eu_alerted": False,
    "us_alerted": False,
    "last_1h_vol": None,
    "last_rsi_alert": None,
    "false_level": None,
    "false_break_time": None,
    "last_news_time": datetime.now(TZ) - timedelta(hours=2),
}

# ======================
# TELEGRAM
# ======================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ======================
# DATA HELPERS
# ======================

def get_data(interval="1m", period="2d"):
    return yf.Ticker(SYMBOL).history(interval=interval, period=period)

def pct(a, b):
    return round(((b - a) / a) * 100, 2)

# ======================
# RSI
# ======================

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ======================
# SESSION ALERTS (ONCE)
# ======================

def session_alerts(now):
    if now.hour == 6 and not state["asia_alerted"]:
        send("🌏 ASIA SESSION OPEN\nLow liquidity → fake moves possible")
        state["asia_alerted"] = True

    if now.hour == 13 and not state["eu_alerted"]:
        send("🇪🇺 EUROPE SESSION OPEN\nTrend continuation / reversals")
        state["eu_alerted"] = True

    if now.hour == 18 and not state["us_alerted"]:
        send("🇺🇸 US SESSION OPEN\n⚠️ High volatility & stop hunts")
        state["us_alerted"] = True

    if now.hour == 0:
        state["asia_alerted"] = state["eu_alerted"] = state["us_alerted"] = False

# ======================
# 1H VOLATILITY (WHY YOU MISSED MOVE)
# ======================

def check_1h_vol():
    data = get_data(interval="1h", period="3d")
    if len(data) < 2:
        return

    prev = data["Close"].iloc[-2]
    last = data["Close"].iloc[-1]
    move = pct(prev, last)

    now = datetime.now(TZ)

    if abs(move) >= VOL_1H_THRESHOLD:
        if not state["last_1h_vol"] or now - state["last_1h_vol"] > timedelta(hours=1):
            send(
                f"⚠️ ABNORMAL 1H MOVE\n\n"
                f"Move: {move}%\n"
                f"WTI: {round(last,2)}\n\n"
                f"Cause likely:\n"
                f"• Macro repricing\n"
                f"• Session liquidity\n"
                f"• Headline risk"
            )
            state["last_1h_vol"] = now

# ======================
# RSI ALERTS
# ======================

def rsi_alert():
    data = get_data(interval="15m", period="2d")
    close = data["Close"]
    rsi = compute_rsi(close).iloc[-1]

    now = datetime.now(TZ)

    if rsi >= RSI_OVERBOUGHT:
        if not state["last_rsi_alert"] or now - state["last_rsi_alert"] > timedelta(hours=2):
            send(f"📈 RSI OVERBOUGHT\nRSI: {round(rsi,2)}\nRisk of pullback")
            state["last_rsi_alert"] = now

    if rsi <= RSI_OVERSOLD:
        if not state["last_rsi_alert"] or now - state["last_rsi_alert"] > timedelta(hours=2):
            send(f"📉 RSI OVERSOLD\nRSI: {round(rsi,2)}\nBounce possible")
            state["last_rsi_alert"] = now

# ======================
# FALSE BREAKOUT (FIXED)
# ======================

def false_breakout():
    data = get_data(interval="5m", period="2d")
    prev_high = data["High"].iloc[-50:-1].max()
    candle = data.iloc[-2]  # closed candle

    now = datetime.now(TZ)

    if state["false_break_time"] and now - state["false_break_time"] < timedelta(minutes=30):
        return

    if candle["High"] > prev_high and candle["Close"] < prev_high:
        send(
            f"⚠️ FALSE BREAKOUT CONFIRMED\n"
            f"Liquidity sweep above {round(prev_high,2)}\n"
            f"Rejection candle closed below"
        )
        state["false_break_time"] = now

# ======================
# EIA DATA
# ======================

def fetch_eia():
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
# INVENTORY EVENTS
# ======================

def inventory(name, expected, is_eia=False):
    pre = get_data()["Close"].iloc[-1]
    send(f"🛢️ {name} RELEASE\nPre Price: {round(pre,2)}")

    time.sleep(900)

    post = get_data()["Close"].iloc[-1]
    actual = fetch_eia() if is_eia else expected

    bias = "📈 Bullish" if actual < expected else "📉 Bearish"

    send(
        f"📊 {name} SUMMARY\n\n"
        f"Expected: {expected}M\n"
        f"Actual: {actual}M\n\n"
        f"Pre: {round(pre,2)}\n"
        f"Post: {round(post,2)}\n\n"
        f"{bias}"
    )

# ======================
# NEWS
# ======================

def check_news():
    feed = feedparser.parse(NEWS_URL)

    for e in feed.entries[:5]:
        published = datetime(*e.published_parsed[:6], tzinfo=pytz.UTC).astimezone(TZ)
        if published > state["last_news_time"]:
            if any(k in e.title.lower() for k in NEWS_KEYWORDS):
                send(f"🚨 ENERGY HEADLINE\n\n{e.title}")
                state["last_news_time"] = published

# ======================
# MAIN LOOP
# ======================

def main():
    send("🚀 Crude Master Bot LIVE (IST)")

    while True:
        now = datetime.now(TZ)

        session_alerts(now)
        check_1h_vol()
        rsi_alert()
        false_breakout()
        check_news()

        if now.weekday() == 1 and now.hour == 20 and now.minute == 0:
            inventory("API Inventory", EXPECTED_API)
            time.sleep(3600)

        if now.weekday() == 2 and now.hour == 20 and now.minute == 0:
            inventory("EIA Inventory", EXPECTED_EIA, True)
            time.sleep(3600)

        time.sleep(30)

# ======================
# RUN
# ======================

if __name__ == "__main__":
    main()
