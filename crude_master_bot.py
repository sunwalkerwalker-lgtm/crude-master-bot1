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
    raise RuntimeError("❌ Missing ENV variables")

# ======================
# CONFIG
# ======================
SYMBOL = "CL=F"
TZ = pytz.timezone("Asia/Kolkata")

EXPECTED_API = -1.5
EXPECTED_EIA = -2.0

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
VOL_1H_THRESHOLD = 1.3   # catches NFP-type candles

NEWS_URL = "https://feeds.reuters.com/reuters/energyNews"
NEWS_KEYWORDS = [
    "oil", "OPEC", "pipeline", "refinery", "sanctions",
    "Middle East", "attack", "export", "war", "supply"
]

# ======================
# STATE (ANTI-SPAM)
# ======================
state = {
    "asia": False,
    "eu": False,
    "us": False,
    "last_rsi": None,
    "last_1h": None,
    "false_break": None,
    "last_news": datetime.now(TZ) - timedelta(hours=2),
    "macro_lock": False
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
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))

# ======================
# SESSION ALERTS
# ======================
def session_alerts(now):
    if now.hour == 6 and not state["asia"]:
        send("🌏 ASIA SESSION OPEN\nLow liquidity → fake moves possible")
        state["asia"] = True

    if now.hour == 13 and not state["eu"]:
        send("🇪🇺 EUROPE SESSION OPEN\nTrend continuation / reversals")
        state["eu"] = True

    if now.hour == 18 and not state["us"]:
        send("🇺🇸 US SESSION OPEN\n⚠️ High volatility window")
        state["us"] = True

    if now.hour == 0:
        state["asia"] = state["eu"] = state["us"] = False

# ======================
# RSI ALERT
# ======================
def rsi_alert():
    data = get_data("15m", "3d")
    r = rsi(data["Close"]).iloc[-1]
    now = datetime.now(TZ)

    if r >= RSI_OVERBOUGHT:
        if not state["last_rsi"] or now - state["last_rsi"] > timedelta(hours=2):
            send(f"📈 RSI OVERBOUGHT\nRSI: {round(r,2)}\nUpside exhaustion risk")
            state["last_rsi"] = now

    if r <= RSI_OVERSOLD:
        if not state["last_rsi"] or now - state["last_rsi"] > timedelta(hours=2):
            send(f"📉 RSI OVERSOLD\nRSI: {round(r,2)}\nBounce potential")
            state["last_rsi"] = now

# ======================
# 1H VOLATILITY (MACRO SHOCK)
# ======================
def check_1h_vol():
    data = get_data("1h", "3d")
    prev = data["Close"].iloc[-2]
    last = data["Close"].iloc[-1]
    move = pct(prev, last)

    now = datetime.now(TZ)

    if abs(move) >= VOL_1H_THRESHOLD:
        if not state["last_1h"] or now - state["last_1h"] > timedelta(hours=1):
            send(
                f"🚨 MACRO SHOCK DETECTED\n\n"
                f"1H Move: {move}%\nWTI: {round(last,2)}\n\n"
                f"Risk-Off Conditions\n"
                f"Likely Macro Event (Jobs / CPI / FOMC)"
            )
            state["macro_lock"] = True
            state["last_1h"] = now

# ======================
# FALSE BREAKOUT (CONTROLLED)
# ======================
def false_breakout():
    data = get_data("5m", "2d")
    level = data["High"].iloc[-50:-1].max()
    candle = data.iloc[-2]

    now = datetime.now(TZ)

    if state["false_break"] and now - state["false_break"] < timedelta(minutes=45):
        return

    if candle["High"] > level and candle["Close"] < level:
        send(
            f"⚠️ FALSE BREAKOUT\n"
            f"Liquidity sweep above {round(level,2)}\n"
            f"Price rejected"
        )
        state["false_break"] = now

# ======================
# EIA ACTUAL DATA
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
        f"Expected: {expected}M\nActual: {actual}M\n\n"
        f"Pre: {round(pre,2)}\nPost: {round(post,2)}\n\n"
        f"{bias}"
    )

# ======================
# NEWS
# ======================
def check_news():
    feed = feedparser.parse(NEWS_URL)
    for e in feed.entries[:5]:
        published = datetime(*e.published_parsed[:6], tzinfo=pytz.UTC).astimezone(TZ)
        if published > state["last_news"]:
            if any(k in e.title.lower() for k in NEWS_KEYWORDS):
                send(f"🚨 ENERGY HEADLINE\n\n{e.title}")
                state["last_news"] = published

# ======================
# DAILY MACRO BRIEF
# ======================
def daily_brief():
    price = get_data()["Close"].iloc[-1]
    send(
        f"🛢️ DAILY CRUDE BRIEF (IST)\n\n"
        f"WTI: {round(price,2)}\n\n"
        f"Focus Today:\n"
        f"• US Macro Data\n"
        f"• Risk sentiment\n"
        f"• Inventory expectations"
    )

# ======================
# MAIN LOOP
# ======================
def main():
    send("🚀 Crude Master Bot LIVE (IST)")
    last_brief = None

    while True:
        now = datetime.now(TZ)

        session_alerts(now)
        rsi_alert()
        false_breakout()
        check_1h_vol()
        check_news()

        if now.hour == 9 and now.minute == 0 and last_brief != now.date():
            daily_brief()
            last_brief = now.date()

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
