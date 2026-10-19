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

import dashboard
from indicators import bollinger, ema, macd, stoch_rsi

# ---------------------------------------------------------------- AYARLAR ---
# Veri kaynağı: Bitget TradFi XAUUSD (varsayılan), Bitget vadeli XAUUSDT ya da Yahoo GC=F
DATA_SOURCE = os.getenv("DATA_SOURCE", "tradfi")
SYMBOL = os.getenv("SYMBOL", {"tradfi": "XAUUSD", "bitget": "XAUUSDT"}.get(DATA_SOURCE, "GC=F"))
SOURCE_LABEL = {"tradfi": "Bitget TradFi", "bitget": "Bitget Vadeli", "yahoo": "Yahoo"}.get(DATA_SOURCE, DATA_SOURCE)
VOLUME_SYMBOL = "XAUUSDT"  # TradFi hacim vermediği için hacim Bitget vadeliden alınır
BITGET_MAX_DAYS = 120
SKIP_WEEKEND = os.getenv("SKIP_WEEKEND", "1") == "1"  # forex kapalıyken (Cuma 21:00-Pazar 22:00 UTC) mumları at

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


_BITGET_URL = "https://api.bitget.com/api/v2/mix/market/history-candles"
_BITGET_GRAN = {"15m": ("15m", 15), "1h": ("1H", 60)}
_TRADFI_URL = "https://www.bitget.com/v1/kline/getMoreKlineDataV2"
_TRADFI_BID = "5"  # Bitget TradFi grafiğindeki varsayılan fiyat tipi (bid)


def _get_json(url: str, params: dict) -> dict:
    """GET + istek sınırı (429) aşılırsa bekleyip tekrar dene."""
    for attempt in range(6):
        r = requests.get(url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 429:
            break
        time.sleep(1 + attempt)
    r.raise_for_status()
    time.sleep(0.15)
    return r.json()


def _paginate(fetch_page, start: pd.Timestamp, end_ms: int) -> list:
    """endTime'ı geriye kaydırarak sayfa sayfa mum topla."""
    rows = []
    while True:
        batch = fetch_page(end_ms)
        if not batch:
            break
        rows += batch
        first = int(batch[0][0])
        if first <= start.timestamp() * 1000 or first >= end_ms:
            break
        end_ms = first
    return rows


def _to_frame(rows: list, start: pd.Timestamp) -> pd.DataFrame:
    df = pd.DataFrame([r_[:6] for r_ in rows],
                      columns=["ts", "Open", "High", "Low", "Close", "Volume"]).astype(float)
    df.index = pd.to_datetime(df.pop("ts").astype("int64"), unit="ms", utc=True)
    df = df[~df.index.duplicated()].sort_index()
    if SKIP_WEEKEND:
        wd, hr = df.index.weekday, df.index.hour
        weekend = ((wd == 4) & (hr >= 21)) | (wd == 5) | ((wd == 6) & (hr < 22))
        df = df[~weekend]
    return df[df.index >= start]


def _window(days: int, minutes: int):
    now = pd.Timestamp.now(tz="UTC")
    return now - pd.Timedelta(days=min(days, BITGET_MAX_DAYS)), int(now.timestamp() * 1000) + minutes * 60_000


def _bitget(interval: str, days: int, symbol: str = SYMBOL) -> pd.DataFrame:
    """Bitget USDT vadeli mum verisi (sayfa başına 200 mum)."""
    gran, minutes = _BITGET_GRAN[interval]
    start, end_ms = _window(days, minutes)
    rows = _paginate(lambda e: _get_json(_BITGET_URL, {
        "symbol": symbol, "productType": "USDT-FUTURES", "granularity": gran,
        "limit": 200, "endTime": e}).get("data") or [], start, end_ms)
    if not rows:
        raise RuntimeError(f"Bitget {symbol} için veri alınamadı ({interval}).")
    return _to_frame(rows, start)


def _tradfi_page(interval: str, end_ms: int) -> list:
    d = _get_json(_TRADFI_URL, {"symbolId": SYMBOL, "kLineStep": interval,
                                "kLineType": _TRADFI_BID, "endTime": end_ms})
    if d.get("code") != "00000":
        raise RuntimeError(f"Bitget TradFi hatası: {d.get('code')} {d.get('msg')}")
    return d.get("data") or []


def _tradfi(interval: str, days: int) -> pd.DataFrame:
    """Bitget TradFi (MT5) mum verisi (sayfa başına 1000 mum, hacim yok)."""
    start, end_ms = _window(days, _BITGET_GRAN[interval][1])
    rows = _paginate(lambda e: _tradfi_page(interval, e), start, end_ms)
    if not rows:
        raise RuntimeError(f"Bitget TradFi {SYMBOL} için veri alınamadı ({interval}).")
    return _to_frame(rows, start)


def _download(interval: str, period: str, with_volume: bool = False) -> pd.DataFrame:
    cols = ["Open", "High", "Low", "Close"] + (["Volume"] if with_volume else [])
    days = int(period.rstrip("d"))
    if DATA_SOURCE == "tradfi":
        df = _tradfi(interval, days)
        if with_volume:
            vol = _bitget(interval, days, VOLUME_SYMBOL)["Volume"]
            df["Volume"] = vol.reindex(df.index).fillna(0.0)
        return df[cols].dropna()
    if DATA_SOURCE == "bitget":
        return _bitget(interval, days)[cols].dropna()
    df = yf.download(SYMBOL, interval=interval, period=period,
                     progress=False, auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"{SYMBOL} için veri alınamadı ({interval}).")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index, utc=True)
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
        f"XAU/USD ({SYMBOL} {SOURCE_LABEL})  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
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
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        if not r.ok:
            print(f"Telegram hatası: {r.status_code} {r.json().get('description', '')}")
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


def status_due(state: dict, close_time: pd.Timestamp) -> bool:
    """Saatlik durum mesajı zamanı geldi mi? (her saatin ilk kontrolü, piyasa açıkken)"""
    hour = close_time.floor("h").isoformat()
    if state.get("last_status") == hour:
        return False
    if pd.Timestamp.now(tz="UTC") - close_time > pd.Timedelta(minutes=45):
        return False  # veri eski: piyasa kapalı
    state["last_status"] = hour
    return True


def position_line(pos, price: float) -> str:
    if not pos:
        return "Açık işlem: yok"
    pct = pos["dir"] * (price - pos["entry"]) / pos["entry"] * 100
    pips = pos["dir"] * (price - pos["entry"]) / PIP_SIZE
    side = "🟢 AL" if pos["dir"] == 1 else "🔴 SAT"
    return (f"Açık işlem: {side} @ {pos['entry']:.2f}\n"
            f"Anlık {'kâr' if pct >= 0 else 'zarar'}: {pct:+.2f}%  ({pips:+.1f} pip)")


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

    state["position"] açık işlemi tutar. Dönen liste: (zaman, tür, mesaj, bilgi).
    """
    events = []
    rows = data if since is None else data[data["close_time"] > since]
    for _, row in rows.iterrows():
        pos = state.get("position")
        if pos and row["close_time"] > pd.Timestamp(pos["time"]):
            hit = (row["High"] >= pos["target"]) if pos["dir"] == 1 else (row["Low"] <= pos["target"])
            if hit:
                pct = TP_PIPS * PIP_SIZE / pos["entry"] * 100
                events.append((row["close_time"], "KAPAT", _close_text(pos, row),
                               {"dir": pos["dir"], "entry": round(pos["entry"], 2),
                                "exit": round(pos["target"], 2), "pct": round(pct, 3)}))
                state["position"] = None
        if row["new_signal"] != 0:
            events.append((row["close_time"], "SINYAL", _open_text(row),
                           {"dir": int(row["new_signal"]), "price": round(float(row["Close"]), 2)}))
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
        for t, kind, text, _ in process_events(data, state, since=pd.Timestamp(last)):
            if now - t <= MAX_SIGNAL_AGE:
                send_telegram(text)
                print(f"Gönderildi ({kind}):\n{text}\n")
        state["last_processed"] = data["close_time"].iloc[-1].isoformat()
    state.pop("last_signal_time", None)

    last_row = data.iloc[-1]
    if status_due(state, last_row["close_time"]):
        send_telegram(f"🕐 SAATLİK DURUM\n{format_report(last_row)}\n"
                      f"{position_line(state.get('position'), float(last_row['Close']))}")

    # GitHub, 60 gün aktivite olmayan repolarda zamanlanmış işleri durdurur;
    # ayda bir state dosyasının değişmesi repoyu aktif tutar.
    state["heartbeat"] = datetime.now(timezone.utc).strftime("%Y-%m")
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    try:
        export_dashboard(data, state)
    except Exception as e:  # panel hatası bildirimleri engellemesin
        print(f"Panel verisi yazılamadı: {e}")


def export_dashboard(data: pd.DataFrame, state: dict):
    last = data.iloc[-1]
    history = dashboard.events_to_list(process_events(data, {}))
    dashboard.write("sinyal", {
        "symbol": SYMBOL,
        "source": SOURCE_LABEL,
        "close_time": dashboard.ts(last["close_time"]),
        "price": round(float(last["Close"]), 2),
        "indicators": {ind: {"15dk": int(last[ind]), "4s": int(last["h4_" + ind])}
                       for ind in INDICATORS},
        "signal": int(last["signal"]),
        "tp_pips": TP_PIPS,
        "pip_size": PIP_SIZE,
        "position": state.get("position"),
        "history": history,
        "stats": dashboard.stats(history),
        "candles": dashboard.candles(data, data.index),
    })


def show_history():
    data = combine(*fetch_data())
    events = process_events(data, {})
    n_sig = sum(e[1] == "SINYAL" for e in events)
    n_tp = sum(e[1] == "KAPAT" for e in events)
    print(f"Son {len(data)} adet 15dk mumda {n_sig} sinyal, {n_tp} kâr al (+{TP_PIPS:g} pip) bulundu:\n")
    for t, kind, _, _ in events:
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
