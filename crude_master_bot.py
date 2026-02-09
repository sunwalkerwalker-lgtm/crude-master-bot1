import os
import time
import requests
from datetime import datetime, timedelta
import pytz
import yfinance as yf
import pandas as pd

# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing BOT_TOKEN or CHAT_ID")

# ================== CONFIG ==================
SYMBOL = "CL=F"
INTERVAL = "5m"
PERIOD = "3d"
CHECK_EVERY = 60
TZ = pytz.timezone("Asia/Kolkata")

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# ================== STATE MEMORY ==================
state = {
    "asia_sent": False,
    "europe_sent": False,
    "us_sent": False,
    "false_breakout": False,
    "false_level": None,
    "rsi_zone": None,
    "trend": None,
    "date": None
}

# ================== TELEGRAM ==================
def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ================== DATA ==================
def get_data():
    df = yf.download(SYMBOL, interval=INTERVAL, period=PERIOD, progress=False)
    df.dropna(inplace=True)
    return df

# ================== RSI ==================
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ================== SESSION ALERTS ==================
def session_alerts():
    now = datetime.now(TZ).time()

    if now >= datetime.strptime("06:00", "%H:%M").time() and not state["asia_sent"]:
        send("🌏 Asia Session Open — Liquidity build phase")
        state["asia_sent"] = True

    if now >= datetime.strptime("13:30", "%H:%M").time() and not state["europe_sent"]:
        send("🇪🇺 Europe Session Open — Volatility expansion")
        state["europe_sent"] = True

    if now >= datetime.strptime("19:00", "%H:%M").time() and not state["us_sent"]:
        send("🇺🇸 US Session Open — Directional moves likely")
        state["us_sent"] = True

# ================== FALSE BREAKOUT ==================
def false_breakout(df):
    prev_high = df["High"][:-50].max()
    last_close = df["Close"].iloc[-1]
    last_high = df["High"].iloc[-1]

    if state["false_breakout"]:
        if last_close > state["false_level"]:
            state["false_breakout"] = False
        return

    if last_high > prev_high and last_close < prev_high:
        send(
            f"⚠️ False Breakout Detected\n"
            f"Swept: {round(prev_high,2)}\n"
            f"Rejection confirmed"
        )
        state["false_breakout"] = True
        state["false_level"] = prev_high

# ================== TREND REVERSAL ==================
def trend_reversal(df):
    ema20 = df["Close"].ewm(span=20).mean()
    ema50 = df["Close"].ewm(span=50).mean()

    trend = "bull" if ema20.iloc[-1] > ema50.iloc[-1] else "bear"

    if state["trend"] and trend != state["trend"]:
        send(
            f"🔁 Trend Reversal Alert\n"
            f"New Trend: {trend.upper()}"
        )

    state["trend"] = trend

# ================== RSI ALERT ==================
def rsi_alert(df):
    rsi = compute_rsi(df["Close"]).iloc[-1]

    if rsi > RSI_OVERBOUGHT and state["rsi_zone"] != "overbought":
        send(f"📈 RSI Overbought ({round(rsi,1)})")
        state["rsi_zone"] = "overbought"

    elif rsi < RSI_OVERSOLD and state["rsi_zone"] != "oversold":
        send(f"📉 RSI Oversold ({round(rsi,1)})")
        state["rsi_zone"] = "oversold"

    elif RSI_OVERSOLD < rsi < RSI_OVERBOUGHT:
        state["rsi_zone"] = None

# ================== RISK OFF ==================
def risk_off():
    vix = yf.download("^VIX", period="1d", progress=False)["Close"].iloc[-1]
    dxy = yf.download("DX-Y.NYB", period="1d", progress=False)["Close"].iloc[-1]

    if vix > 20 and dxy > 105:
        send("🚨 RISK OFF WARNING\nVIX & DXY rising — Crude volatility risk")

# ================== DAILY RESET ==================
def daily_reset():
    today = datetime.now(TZ).date()
    if state["date"] != today:
        for k in state:
            state[k] = False if isinstance(state[k], bool) else None
        state["date"] = today

# ================== MAIN ==================
if __name__ == "__main__":
    send("🚀 Crude Master Bot Started")
    while True:
        try:
            daily_reset()
            df = get_data()
            session_alerts()
            false_breakout(df)
            trend_reversal(df)
            rsi_alert(df)
            risk_off()
            time.sleep(CHECK_EVERY)
        except Exception as e:
            send(f"⚠️ Bot Error: {e}")
            time.sleep(30)
