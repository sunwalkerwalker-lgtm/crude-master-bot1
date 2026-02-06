import yfinance as yf
import requests
import time
import pytz
import feedparser
import os
import numpy as np
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
RSI_PERIOD = 14

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
# STATE MEMORY
# ======================

last_session_alert = {"asia": None, "europe": None, "us": None}
last_false_breakout = datetime.now(TZ) - timedelta(hours=2)
last_trend_alert = datetime.now(TZ) - timedelta(hours=2)
last_1h_vol_alert = datetime.now(TZ) - timedelta(hours=2)
last_news_time = datetime.now(TZ) - timedelta(hours=1)

# ======================
# PRICE HELPERS
# ======================

def get_price(interval="1h", period="2d"):
    return yf.Ticker(SYMBOL).history(interval=interval, period=period)

def pct(p1, p2):
    return round(((p2 - p1) / p1) * 100, 2)

# ======================
# RSI CALC
# ======================

def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ======================
# SESSION ALERTS
# ======================

def session_alerts(now):
    today = now.date()

    if now.hour == 6 and now.minute == 0 and last_session_alert["asia"] != today:
        send("🌏 ASIA SESSION OPEN\nLow liquidity → false breakouts possible")
        last_session_alert["asia"] = today

    if now.hour == 13 and now.minute == 30 and last_session_alert["europe"] != today:
        send("🇪🇺 EUROPE SESSION OPEN\nTrend continuation / reversal zone")
        last_session_alert["europe"] = today

    if now.hour == 18 and now.minute == 30 and last_session_alert["us"] != today:
        send("🇺🇸 US SESSION OPEN\n⚠️ High volatility + stop hunts")
        last_session_alert["us"] = today

# ======================
# 1H VOLATILITY
# ======================

def check_1h_volatility():
    global last_1h_vol_alert

    data = get_price()
    if len(data) < 2:
        return

    prev = data["Close"].iloc[-2]
    last = data["Close"].iloc[-1]
    move = pct(prev, last)

    now = datetime.now(TZ)

    if abs(move) >= VOL_1H_THRESHOLD and (now - last_1h_vol_alert).seconds > 3600:
        send(
            f"⚠️ ABNORMAL 1H MOVE\n\n"
            f"Move: {move}%\n"
            f"Price: {round(last,2)}\n\n"
            f"Likely Cause:\n"
            f"• Liquidity grab\n"
            f"• News reaction\n"
            f"• Inventory positioning"
        )
        last_1h_vol_alert = now

# ======================
# FALSE BREAKOUT DETECTION
# ======================

def false_breakout_detection():
    global last_false_breakout

    data = get_price(period="3d")
    if len(data) < 20:
        return

    now = datetime.now(TZ)
    if (now - last_false_breakout).seconds < 3600:
        return

    recent_high = data["High"].iloc[-20:-1].max()
    recent_low = data["Low"].iloc[-20:-1].min()

    last_close = data["Close"].iloc[-1]
    last_high = data["High"].iloc[-1]
    last_low = data["Low"].iloc[-1]

    if last_high > recent_high and last_close < recent_high:
        send(
            f"🚨 FALSE BREAKOUT (UPSIDE)\n\n"
            f"Liquidity grab above resistance\n"
            f"Price rejected back into range\n\n"
            f"Level: {round(recent_high,2)}"
        )
        last_false_breakout = now

    elif last_low < recent_low and last_close > recent_low:
        send(
            f"🚨 FALSE BREAKOUT (DOWNSIDE)\n\n"
            f"Stop hunt below support\n"
            f"Price reclaimed range\n\n"
            f"Level: {round(recent_low,2)}"
        )
        last_false_breakout = now

# ======================
# TREND REVERSAL ALERT
# ======================

def trend_reversal_alert():
    global last_trend_alert

    data = get_price(period="5d")
    if len(data) < 30:
        return

    now = datetime.now(TZ)
    if (now - last_trend_alert).seconds < 3600:
        return

    close = data["Close"]
    rsi = calculate_rsi(close, RSI_PERIOD)

    last_rsi = rsi.iloc[-1]
    prev_rsi = rsi.iloc[-2]

    # Bullish reversal
    if prev_rsi < 30 and last_rsi > 32:
        send(
            f"🔄 TREND REVERSAL SIGNAL\n\n"
            f"Bullish momentum shift\n"
            f"RSI: {round(last_rsi,1)}\n\n"
            f"Watch for higher lows"
        )
        last_trend_alert = now

    # Bearish reversal
    elif prev_rsi > 70 and last_rsi < 68:
        send(
            f"🔄 TREND REVERSAL SIGNAL\n\n"
            f"Bearish momentum shift\n"
            f"RSI: {round(last_rsi,1)}\n\n"
            f"Watch for lower highs"
        )
        last_trend_alert = now

# ======================
# NEWS SCANNER
# ======================

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
        f"Focus Today:\n"
        f"• Inventory positioning\n"
        f"• False breakouts\n"
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
        false_breakout_detection()
        trend_reversal_alert()
        check_news()

        if now.hour == 9 and now.minute == 0 and last_brief_day != now.date():
            daily_brief()
            last_brief_day = now.date()

        time.sleep(30)

# ======================
# RUN
# ======================

if __name__ == "__main__":
    main()
