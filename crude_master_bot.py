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

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

NEWS_URL = "https://feeds.reuters.com/reuters/energyNews"

NEWS_KEYWORDS = [
    "oil", "OPEC", "pipeline", "refinery", "sanctions",
    "Middle East", "attack", "export", "war", "supply",
    "fed", "rates", "inflation"
]

# ======================
# STATE MEMORY
# ======================

last_session_alert = None
last_1h_alert = datetime.now(TZ) - timedelta(hours=2)
last_news_time = datetime.now(TZ) - timedelta(hours=1)
last_risk_alert = None

# ======================
# TELEGRAM
# ======================

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ======================
# DATA HELPERS
# ======================

def get_data(interval, period):
    return yf.Ticker(SYMBOL).history(interval=interval, period=period)

def pct(a, b):
    return round(((b - a) / a) * 100, 2)

# ======================
# TECHNICALS
# ======================

def calculate_rsi(data, period=14):
    delta = data.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ======================
# SESSION ALERTS (NO DUPES)
# ======================

def session_alerts(now):
    global last_session_alert

    session = None
    if now.hour == 6 and now.minute == 0:
        session = "🌏 ASIA SESSION OPEN"
    elif now.hour == 13 and now.minute == 30:
        session = "🇪🇺 EUROPE SESSION OPEN"
    elif now.hour == 18 and now.minute == 30:
        session = "🇺🇸 US SESSION OPEN"

    if session and session != last_session_alert:
        send(f"{session}\nLiquidity conditions changing ⚠️")
        last_session_alert = session

# ======================
# VOLATILITY ENGINE
# ======================

def check_volatility():
    global last_1h_alert

    data = get_data("1h", "2d")
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
            f"Possible Causes:\n"
            f"• Macro headline\n"
            f"• Liquidity sweep\n"
            f"• Event positioning"
        )
        last_1h_alert = now

# ======================
# RSI + TREND + REVERSAL
# ======================

def check_technicals():
    data = get_data("5m", "1d")
    close = data["Close"]

    rsi = calculate_rsi(close).iloc[-1]

    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    price = close.iloc[-1]

    # RSI
    if rsi > RSI_OVERBOUGHT:
        send(f"🔴 RSI OVERBOUGHT\nRSI: {round(rsi,1)}")
    elif rsi < RSI_OVERSOLD:
        send(f"🟢 RSI OVERSOLD\nRSI: {round(rsi,1)}")

    # Trend Reversal
    if price > ema20 and ema20 > ema50:
        send("📈 TREND SHIFT BULLISH\nStructure flipped up")
    elif price < ema20 and ema20 < ema50:
        send("📉 TREND SHIFT BEARISH\nStructure flipped down")

# ======================
# FALSE BREAKOUT
# ======================

def false_breakout():
    data = get_data("5m", "1d")
    high = data["High"].iloc[-2]
    last = data["Close"].iloc[-1]

    if last < high:
        send(
            "⚠️ FALSE BREAKOUT DETECTED\n"
            "Price rejected after liquidity grab"
        )

# ======================
# RISK OFF WARNING
# ======================

def risk_off_alert():
    global last_risk_alert

    vix = yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1]
    now = datetime.now(TZ)

    if vix > 20 and last_risk_alert != now.date():
        send(
            "🚨 RISK OFF ENVIRONMENT\n\n"
            "• Volatility rising\n"
            "• Algo driven moves likely\n"
            "• Protect positions"
        )
        last_risk_alert = now.date()

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
    price = get_data("1m", "1d")["Close"].iloc[-1]
    send(
        f"🛢️ CRUDE MARKET BRIEF\n\n"
        f"WTI: {round(price,2)}\n\n"
        f"Focus Today:\n"
        f"• US session liquidity\n"
        f"• Inventory positioning\n"
        f"• Headline risk"
    )

# ======================
# MAIN LOOP
# ======================

def main():
    send("🚀 Crude Master Bot LIVE")

    last_brief = None

    while True:
        now = datetime.now(TZ)

        session_alerts(now)
        check_volatility()
        check_technicals()
        false_breakout()
        risk_off_alert()
        check_news()

        if now.hour == 9 and now.minute == 0 and last_brief != now.date():
            daily_brief()
            last_brief = now.date()

        time.sleep(60)

# ======================
# RUN
# ======================

if __name__ == "__main__":
    main()
