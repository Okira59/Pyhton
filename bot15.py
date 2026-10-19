"""XAU/USD (altın) 15 dakikalık AL/SAT sinyal botu.

Her kapanan 15dk mumda 6 göstergeye bakar (EMA, Bollinger, RSI, StochRSI,
MACD, Hacim). Her gösterge +1 (AL), -1 (SAT) ya da 0 (nötr) oy verir; oyların
toplamına göre HER mumda AL ya da SAT sinyali üretilir.
"""
import argparse
import json
import os

import pandas as pd

from bot import TF_15M, _arrow, _closed_only, _download, send_telegram
from indicators import bollinger, ema, macd, rsi, stoch_rsi

# ---------------------------------------------------------------- AYARLAR ---
EMA_FAST, EMA_SLOW = 9, 21
BB_PERIOD, BB_STD = 20, 2.0
RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD = 14, 70, 30
STOCH_RSI, STOCH_PERIOD, STOCH_K, STOCH_D = 14, 14, 3, 3
STOCH_OVERBOUGHT, STOCH_OVERSOLD = 80, 20
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
VOLUME_PERIOD = 20

TP_PIPS = float(os.getenv("TP_PIPS", "10"))
PIP_SIZE = float(os.getenv("PIP_SIZE", "1.0"))  # altında 1 pip = 1 $

STATE_FILE = os.getenv("STATE_FILE", "state15.json")
MAX_SIGNAL_AGE = pd.Timedelta(minutes=30)  # bundan eski mumlar bildirilmez
# ----------------------------------------------------------------------------

INDICATORS = ["EMA", "BOLLINGER", "RSI", "STOCHRSI", "MACD", "HACIM"]


def fetch_data() -> pd.DataFrame:
    return _closed_only(_download("15m", "60d", with_volume=True), TF_15M)


def add_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c, o, v = df["Close"], df["Open"], df["Volume"]

    df["ema_fast"], df["ema_slow"] = ema(c, EMA_FAST), ema(c, EMA_SLOW)
    df["bb_up"], df["bb_mid"], df["bb_low"] = bollinger(c, BB_PERIOD, BB_STD)
    df["rsi"] = rsi(c, RSI_PERIOD)
    df["k"], df["d"] = stoch_rsi(c, STOCH_RSI, STOCH_PERIOD, STOCH_K, STOCH_D)
    df["macd"], df["macd_sig"], df["macd_hist"] = macd(c, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    df["vol_avg"] = v.rolling(VOLUME_PERIOD).mean()

    def direction(bull, bear):
        return bull.astype(int) - bear.astype(int)

    # EMA: EMA9 > EMA21 -> yükseliş
    df["EMA"] = direction(df.ema_fast > df.ema_slow, df.ema_fast < df.ema_slow)
    # Bollinger: alt banda dokunma -> dönüş (AL), üst banda dokunma -> dönüş (SAT),
    # aksi halde orta bandın üstü/altı
    df["BOLLINGER"] = direction(
        (c <= df.bb_low) | ((c > df.bb_mid) & (c < df.bb_up)),
        (c >= df.bb_up) | ((c < df.bb_mid) & (c > df.bb_low)))
    # RSI: 50 üstü yükseliş, ama aşırı alım (>70) SAT, aşırı satım (<30) AL
    df["RSI"] = direction(
        (df.rsi < RSI_OVERSOLD) | ((df.rsi > 50) & (df.rsi < RSI_OVERBOUGHT)),
        (df.rsi > RSI_OVERBOUGHT) | ((df.rsi < 50) & (df.rsi > RSI_OVERSOLD)))
    # StochRSI: %K > %D -> AL, %K < %D -> SAT (aşırı bölgelerde nötr)
    df["STOCHRSI"] = direction((df.k > df.d) & (df.k < STOCH_OVERBOUGHT),
                               (df.k < df.d) & (df.k > STOCH_OVERSOLD))
    # MACD: MACD çizgisi sinyal çizgisinin üstünde -> AL, altında -> SAT
    df["MACD"] = direction(df.macd > df.macd_sig, df.macd < df.macd_sig)
    # Hacim: ortalamanın üstünde hacimle yeşil mum -> AL, kırmızı mum -> SAT
    high_vol = v > df.vol_avg
    df["HACIM"] = direction(high_vol & (c > o), high_vol & (c < o))

    df["score"] = df[INDICATORS].sum(axis=1)
    # Her mumda mutlaka AL/SAT: eşitlikte trend (EMA) yönü, o da yoksa MACD
    tie = df["EMA"].where(df["EMA"] != 0, df["MACD"]).replace(0, 1)
    df["signal"] = df["score"].apply(lambda s: 1 if s > 0 else -1 if s < 0 else 0)
    df.loc[df["signal"] == 0, "signal"] = tie
    df["close_time"] = df.index + TF_15M
    return df


def _strength(score: int) -> str:
    a = abs(score)
    return "Güçlü" if a >= 4 else "Orta" if a >= 2 else "Zayıf"


def format_report(row: pd.Series) -> str:
    sig = int(row["signal"])
    head = "🟢 AL" if sig == 1 else "🔴 SAT"
    agree = int((row[INDICATORS] == sig).sum())
    target = row["Close"] + sig * TP_PIPS * PIP_SIZE
    lines = [
        f"{head}  |  XAU/USD 15dk  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
        f"Fiyat: {row['Close']:.2f}   Güç: {agree}/{len(INDICATORS)} ({_strength(row['score'])})",
        f"Kâr al hedefi (+{TP_PIPS:g} pip): {target:.2f}",
        "",
    ]
    for ind in INDICATORS:
        lines.append(f"{ind:<10} {_arrow(row[ind])}")
    return "\n".join(lines)


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def check_and_notify(send: bool = True):
    data = add_signals(fetch_data())
    row = data.iloc[-1]
    report = format_report(row)
    print(report + "\n")
    if not send:
        return
    state = _load_state()
    last_sent = state.get("last_sent")
    is_new = last_sent is None or row["close_time"] > pd.Timestamp(last_sent)
    is_fresh = pd.Timestamp.now(tz="UTC") - row["close_time"] <= MAX_SIGNAL_AGE
    if is_new and is_fresh:
        send_telegram(report)
        print("Telegram'a gönderildi.")
        state["last_sent"] = row["close_time"].isoformat()
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)


def show_history(n: int = 40):
    data = add_signals(fetch_data()).dropna(subset=["vol_avg", "k"])
    fwd = data["Close"].shift(-1) - data["Close"]
    hit = (fwd * data["signal"] > 0)
    print(f"Son {len(data)} mumda bir sonraki mumun yönünü doğru bilme oranı: {hit.mean():.1%}\n")
    for _, r in data.tail(n).iterrows():
        print(f"{r['close_time']:%m-%d %H:%M}  {_arrow(r['signal'])}  {int(r['score']):+d}  @ {r['Close']:.2f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Altın 15dk AL/SAT sinyal botu")
    p.add_argument("--notify", action="store_true", help="Son mumun sinyalini Telegram'a gönder")
    p.add_argument("--history", action="store_true", help="Son sinyalleri listele")
    args = p.parse_args()
    if args.notify:
        check_and_notify()
    elif args.history:
        show_history()
    else:
        check_and_notify(send=False)
