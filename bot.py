"""XAU/USD (altın) için çoklu zaman dilimli AL/SAT sinyal botu.

Sinyal mantığı: 15dk ve 4s grafiklerde Bollinger, EMA, MACD ve StochRSI
göstergelerinin HEPSİ aynı yönü gösterdiğinde AL veya SAT sinyali üretilir.
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

from indicators import bollinger, ema, macd, stoch_rsi

# ---------------------------------------------------------------- AYARLAR ---
SYMBOL = os.getenv("SYMBOL", "GC=F")  # Yahoo'da altın vadeli (spot XAU/USD'ye çok yakın)

EMA_FAST, EMA_SLOW = 20, 50
BB_PERIOD, BB_STD = 20, 2.0
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
STOCH_RSI, STOCH_PERIOD, STOCH_K, STOCH_D = 14, 14, 3, 3
STOCH_OVERBOUGHT, STOCH_OVERSOLD = 80, 20

# Kâr al: sinyalden sonra fiyat bu kadar pip kâra ulaşınca "KAPAT" sinyali
TP_PIPS = float(os.getenv("TP_PIPS", "10"))
PIP_SIZE = float(os.getenv("PIP_SIZE", "1.0"))  # altında 1 pip = 1 $ (10 pip = 10 $)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_FILE = os.getenv("STATE_FILE", "state.json")
MAX_SIGNAL_AGE = pd.Timedelta(hours=2)  # bundan eski sinyaller bildirilmez
# ----------------------------------------------------------------------------

INDICATORS = ["EMA", "BOLLINGER", "MACD", "STOCHRSI"]
TF_15M = pd.Timedelta(minutes=15)
TF_4H = pd.Timedelta(hours=4)


def _download(interval: str, period: str, with_volume: bool = False) -> pd.DataFrame:
    df = yf.download(SYMBOL, interval=interval, period=period,
                     progress=False, auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"{SYMBOL} için veri alınamadı ({interval}).")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index, utc=True)
    cols = ["Open", "High", "Low", "Close"] + (["Volume"] if with_volume else [])
    return df[cols].dropna()


def _closed_only(df: pd.DataFrame, tf: pd.Timedelta) -> pd.DataFrame:
    """Henüz kapanmamış son mumu at (index = mumun açılış zamanı)."""
    now = pd.Timestamp.now(tz="UTC")
    return df[df.index + tf <= now]


def fetch_data():
    m15 = _closed_only(_download("15m", "60d"), TF_15M)
    h1 = _download("1h", "730d")
    h4 = h1.resample("4h", origin="epoch").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    h4 = _closed_only(h4, TF_4H)
    return m15, h4


def add_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Her mum için gösterge yönlerini hesaplar: +1 = AL, -1 = SAT, 0 = nötr."""
    df = df.copy()
    c = df["Close"]

    df["ema_fast"] = ema(c, EMA_FAST)
    df["ema_slow"] = ema(c, EMA_SLOW)
    df["bb_up"], df["bb_mid"], df["bb_low"] = bollinger(c, BB_PERIOD, BB_STD)
    df["macd"], df["macd_sig"], _ = macd(c, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    df["k"], df["d"] = stoch_rsi(c, STOCH_RSI, STOCH_PERIOD, STOCH_K, STOCH_D)

    def direction(bull, bear):
        return bull.astype(int) - bear.astype(int)

    # EMA: hızlı EMA yavaşın üstünde ve fiyat hızlı EMA'nın üstünde -> yükseliş
    df["EMA"] = direction((df.ema_fast > df.ema_slow) & (c > df.ema_fast),
                          (df.ema_fast < df.ema_slow) & (c < df.ema_fast))
    # Bollinger: fiyat orta bandın üstünde ama üst bandı aşmamış -> yükseliş
    df["BOLLINGER"] = direction((c > df.bb_mid) & (c < df.bb_up),
                                (c < df.bb_mid) & (c > df.bb_low))
    # MACD: MACD çizgisi sinyal çizgisinin üstünde -> yükseliş
    df["MACD"] = direction(df.macd > df.macd_sig, df.macd < df.macd_sig)
    # StochRSI: %K > %D ve aşırı alım bölgesinde değil -> yükseliş
    df["STOCHRSI"] = direction((df.k > df.d) & (df.k < STOCH_OVERBOUGHT),
                               (df.k < df.d) & (df.k > STOCH_OVERSOLD))

    df["score"] = df[INDICATORS].sum(axis=1)
    return df


def combine(m15: pd.DataFrame, h4: pd.DataFrame) -> pd.DataFrame:
    """Her 15dk mumuna, o an KAPANMIŞ en son 4s mumunun durumunu ekler."""
    a = add_signals(m15)
    b = add_signals(h4)[INDICATORS + ["score"]].add_prefix("h4_")
    a["close_time"] = a.index + TF_15M
    b["close_time"] = b.index + TF_4H
    merged = pd.merge_asof(a.sort_values("close_time"), b.sort_values("close_time"),
                           on="close_time", direction="backward")
    merged.index = a.index

    n = len(INDICATORS)
    buy = (merged["score"] == n) & (merged["h4_score"] == n)
    sell = (merged["score"] == -n) & (merged["h4_score"] == -n)
    merged["signal"] = 0
    merged.loc[buy, "signal"] = 1
    merged.loc[sell, "signal"] = -1
    # Yalnızca yeni oluşan sinyaller (önceki mumda aynı sinyal yoksa)
    merged["new_signal"] = merged["signal"].where(
        merged["signal"] != merged["signal"].shift(1), 0)
    return merged


def _arrow(v):
    return {1: "AL  ▲", -1: "SAT ▼"}.get(int(v), "nötr -")


def format_report(row: pd.Series) -> str:
    sig = {1: "🟢 AL SİNYALİ", -1: "🔴 SAT SİNYALİ"}.get(int(row["signal"]), "⚪ Sinyal yok")
    lines = [
        f"XAU/USD ({SYMBOL})  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
        f"Fiyat: {row['Close']:.2f}",
        f"{'Gösterge':<10} {'15dk':<8} {'4s':<8}",
    ]
    for ind in INDICATORS:
        lines.append(f"{ind:<10} {_arrow(row[ind]):<8} {_arrow(row['h4_' + ind]):<8}")
    lines.append(f"Sonuç: {sig}")
    return "\n".join(lines)


def send_telegram(text: str):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except requests.RequestException as e:
        print(f"Telegram hatası: {e}")


def check_once(notify_only_new: bool = False):
    data = combine(*fetch_data())
    last = data.iloc[-1]
    report = format_report(last)
    print(report + "\n")
    if last["new_signal"] != 0 or (not notify_only_new and last["signal"] != 0):
        send_telegram(report)
    return last


def run_loop():
    print("Bot çalışıyor. Her 15dk mum kapanışında kontrol edilecek (Ctrl+C ile çıkış).\n")
    while True:
        try:
            check_and_notify(require_telegram=False)
        except Exception as e:  # ağ hatalarında botun durmaması için
            print(f"Hata: {e}")
        now = datetime.now(timezone.utc).timestamp()
        wait = 900 - (now % 900) + 30  # mum kapanışından 30 sn sonra
        time.sleep(wait)


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _target(direction: int, entry: float) -> float:
    return entry + direction * TP_PIPS * PIP_SIZE


def _open_text(row: pd.Series) -> str:
    target = _target(int(row["new_signal"]), row["Close"])
    return f"{format_report(row)}\nKâr al hedefi (+{TP_PIPS:g} pip): {target:.2f}"


def _close_text(pos: dict, row: pd.Series) -> str:
    side = "AL" if pos["dir"] == 1 else "SAT"
    return (f"🎯 İŞLEMİ KAPAT  |  {row['close_time']:%Y-%m-%d %H:%M} UTC\n"
            f"{side} işlemi +{TP_PIPS:g} pip kâra ulaştı.\n"
            f"Giriş: {pos['entry']:.2f}  →  Hedef: {pos['target']:.2f}\n"
            f"Güncel fiyat: {row['Close']:.2f}")


def process_events(data: pd.DataFrame, state: dict, since=None) -> list:
    """Mumları kronolojik işler: kâr al (KAPAT) ve yeni AL/SAT olayları üretir.

    state["position"] açık işlemi tutar. Dönen liste: (zaman, tür, mesaj).
    """
    events = []
    rows = data if since is None else data[data["close_time"] > since]
    for _, row in rows.iterrows():
        pos = state.get("position")
        if pos and row["close_time"] > pd.Timestamp(pos["time"]):
            hit = (row["High"] >= pos["target"]) if pos["dir"] == 1 else (row["Low"] <= pos["target"])
            if hit:
                events.append((row["close_time"], "KAPAT", _close_text(pos, row)))
                state["position"] = None
        if row["new_signal"] != 0:
            events.append((row["close_time"], "SINYAL", _open_text(row)))
            state["position"] = {
                "dir": int(row["new_signal"]),
                "entry": float(row["Close"]),
                "target": float(_target(int(row["new_signal"]), row["Close"])),
                "time": row["close_time"].isoformat(),
            }
    return events


def check_and_notify(require_telegram: bool = True):
    """Zamanlanmış (ör. GitHub Actions) tek seferlik çalışma.

    Son kontrolden bu yana oluşan yeni AL/SAT ve KAPAT sinyallerini bulur,
    Telegram'a gönderir ve tekrar gönderilmemesi için state dosyasına kaydeder.
    """
    if require_telegram and not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        raise SystemExit("TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID tanımlı olmalı.")
    state = _load_state()
    data = combine(*fetch_data())
    print(format_report(data.iloc[-1]) + "\n")

    last = state.get("last_processed")
    if last is None:  # ilk çalışma: geçmişi bildirmeden sadece işaretle
        state["last_processed"] = data["close_time"].iloc[-1].isoformat()
    else:
        now = pd.Timestamp.now(tz="UTC")
        for t, kind, text in process_events(data, state, since=pd.Timestamp(last)):
            if now - t <= MAX_SIGNAL_AGE:
                send_telegram(text)
                print(f"Gönderildi ({kind}):\n{text}\n")
        state["last_processed"] = data["close_time"].iloc[-1].isoformat()
    state.pop("last_signal_time", None)

    # GitHub, 60 gün aktivite olmayan repolarda zamanlanmış işleri durdurur;
    # ayda bir state dosyasının değişmesi repoyu aktif tutar.
    state["heartbeat"] = datetime.now(timezone.utc).strftime("%Y-%m")
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def show_history():
    data = combine(*fetch_data())
    events = process_events(data, {})
    n_sig = sum(k == "SINYAL" for _, k, _ in events)
    n_tp = sum(k == "KAPAT" for _, k, _ in events)
    print(f"Son {len(data)} adet 15dk mumda {n_sig} sinyal, {n_tp} kâr al (+{TP_PIPS:g} pip) bulundu:\n")
    for t, kind, text in events:
        if kind == "SINYAL":
            row = data[data["close_time"] == t].iloc[0]
            print(f"{t:%Y-%m-%d %H:%M} UTC  {_arrow(row['new_signal'])}  @ {row['Close']:.2f}")
        else:
            print(f"{t:%Y-%m-%d %H:%M} UTC  🎯 KAPAT (+{TP_PIPS:g} pip)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Altın (XAU/USD) AL/SAT sinyal botu")
    p.add_argument("--loop", action="store_true", help="Sürekli çalış, her 15dk kontrol et")
    p.add_argument("--history", action="store_true", help="Son 60 gündeki sinyalleri listele")
    p.add_argument("--notify", action="store_true",
                   help="Tek seferlik kontrol; yeni sinyal varsa Telegram'a gönder (GitHub Actions için)")
    args = p.parse_args()
    if args.notify:
        check_and_notify()
    elif args.history:
        show_history()
    elif args.loop:
        run_loop()
    else:
        check_once()
