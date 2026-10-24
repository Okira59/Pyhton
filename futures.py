"""Bitget Futures XAUUSDT (altın) 10x simülasyon botu.

5dk, 15dk, 30dk, 45dk, 1s ve 4s grafiklerde EMA, Bollinger, RSI, StochRSI, MACD ve
Hacim göstergelerinin yönünü puanlar. 5dk'da güçlü sinyal + üst zaman dilimlerinde
onay olunca 10x LONG/SHORT işlem açılmış sayılır. Kaldıraçlı kâr %30'a ya da zarar
%20'ye ulaşınca işlem kapatılır. Gerçek emir gönderilmez; yalnızca Telegram bildirimi.
"""
import argparse
import json
import os

import pandas as pd

import dashboard
from bot import _bitget, _closed_only, send_telegram, status_due
from indicators import bollinger, ema, macd, rsi, stoch_rsi

# ---------------------------------------------------------------- AYARLAR ---
SYMBOL = "XAUUSDT"
TIMEFRAMES = {"5dk": 5, "15dk": 15, "30dk": 30, "45dk": 45, "1s": 60, "4s": 240}
HIGHER = [n for n in TIMEFRAMES if n != "5dk"]
EMA_FAST, EMA_SLOW = 9, 21
BB_PERIOD, BB_STD = 20, 2.0
RSI_PERIOD = 14
STOCH_HIGH, STOCH_LOW = 80, 20
VOLUME_PERIOD = 20

MIN_SCORE_5M = int(os.getenv("MIN_SCORE_5M", "5"))         # 5dk'da 6 göstergeden en az bu kadarı aynı yönde
MIN_SCORE_HIGHER = int(os.getenv("MIN_SCORE_HIGHER", "4"))  # üst zaman diliminde onay puanı
MIN_HIGHER_TFS = int(os.getenv("MIN_HIGHER_TFS", "4"))      # 5 üst zaman diliminden en az bu kadarı onaylamalı

LEVERAGE = float(os.getenv("LEVERAGE", "10"))
TP_ROE = float(os.getenv("TP_ROE", "30"))  # kaldıraçlı kâr % (10x'te fiyat %3)
SL_ROE = float(os.getenv("SL_ROE", "20"))  # kaldıraçlı zarar % (10x'te fiyat %2)
DAYS = int(os.getenv("FUTURES_DAYS", "60"))

STATE_FILE = os.getenv("STATE_FILE", "futures_state.json")
MAX_EVENT_AGE = pd.Timedelta(minutes=30)
# ----------------------------------------------------------------------------

CHECKS = ["EMA", "BOLLINGER", "RSI", "STOCHRSI", "MACD", "HACIM"]
TF_5M = pd.Timedelta(minutes=5)
AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


def _resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 5:
        return df
    origin = "epoch" if minutes == 240 else "start_day"
    return df.resample(f"{minutes}min", origin=origin).agg(AGG).dropna()


def directions(df: pd.DataFrame) -> pd.DataFrame:
    """Her mum için gösterge yönleri: +1 = yükseliş (LONG), -1 = düşüş (SHORT), 0 = nötr."""
    c, o, v = df.Close, df.Open, df.Volume
    e_fast, e_slow = ema(c, EMA_FAST), ema(c, EMA_SLOW)
    up, mid, low = bollinger(c, BB_PERIOD, BB_STD)
    r = rsi(c, RSI_PERIOD)
    k, d = stoch_rsi(c)
    m, sig, _ = macd(c)
    vol_hi = v > v.rolling(VOLUME_PERIOD).mean()

    def dirn(bull, bear):
        return bull.astype(int) - bear.astype(int)

    out = pd.DataFrame({
        "EMA": dirn((e_fast > e_slow) & (c > e_fast), (e_fast < e_slow) & (c < e_fast)),
        "BOLLINGER": dirn((c > mid) & (c < up), (c < mid) & (c > low)),
        "RSI": dirn((r > 50) & (r < 70), (r < 50) & (r > 30)),
        "STOCHRSI": dirn((k > d) & (k < STOCH_HIGH), (k < d) & (k > STOCH_LOW)),
        "MACD": dirn(m > sig, m < sig),
        "HACIM": dirn(vol_hi & (c > o), vol_hi & (c < o)),
    }, index=df.index)
    out["score"] = out[CHECKS].sum(axis=1)
    return out


def build(m5: pd.DataFrame, min5=None, minh=None, ntf=None) -> pd.DataFrame:
    min5 = MIN_SCORE_5M if min5 is None else min5
    minh = MIN_SCORE_HIGHER if minh is None else minh
    ntf = MIN_HIGHER_TFS if ntf is None else ntf
    base = m5.copy()
    base["close_time"] = base.index + TF_5M
    for name, minutes in TIMEFRAMES.items():
        tf = pd.Timedelta(minutes=minutes)
        s = directions(_closed_only(_resample(m5, minutes), tf)).add_suffix(f"_{name}")
        s["close_time"] = s.index + tf
        base = pd.merge_asof(base.sort_values("close_time"), s.sort_values("close_time"),
                             on="close_time", direction="backward")
    base.index = base["close_time"]
    base = base.dropna(subset=[f"score_{n}" for n in TIMEFRAMES])
    hs = base[[f"score_{n}" for n in HIGHER]]
    long_ = (base["score_5dk"] >= min5) & (hs.ge(minh).sum(axis=1) >= ntf)
    short = (base["score_5dk"] <= -min5) & (hs.le(-minh).sum(axis=1) >= ntf)
    sig = long_.astype(int) - short.astype(int)
    base["signal"] = sig
    base["new_signal"] = sig.where((sig != 0) & (sig != sig.shift()), 0)
    return base


def fetch_5m(days: int = DAYS) -> pd.DataFrame:
    df = _bitget("5m", days, SYMBOL)[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return _closed_only(df, TF_5M)


def levels(direction: int, entry: float):
    return (entry * (1 + direction * TP_ROE / LEVERAGE / 100),
            entry * (1 - direction * SL_ROE / LEVERAGE / 100))


def roe(direction: int, entry: float, price: float) -> float:
    return direction * (price - entry) / entry * 100 * LEVERAGE


def _side(d: int) -> str:
    return "🟢 LONG" if d == 1 else "🔴 SHORT"


def _score_lines(row: pd.Series, direction: int) -> list:
    lines = []
    for n in TIMEFRAMES:
        sc = int(row[f"score_{n}"])
        agree = [c for c in CHECKS if int(row[f"{c}_{n}"]) == direction]
        lines.append(f"{n:<5} {sc:+d}/6  {', '.join(agree) if agree else '-'}")
    return lines


def _open_text(row: pd.Series, d: int) -> str:
    tp, sl = levels(d, row["Close"])
    head = "🟢🟢 FUTURES – LONG AÇ 🟢🟢" if d == 1 else "🔴🔴 FUTURES – SHORT AÇ 🔴🔴"
    return "\n".join([head, f"Bitget {SYMBOL}  |  {LEVERAGE:g}x  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
                      f"Giriş fiyatı: {row['Close']:.2f}",
                      f"Kâr al (+%{TP_ROE:g}): {tp:.2f}",
                      f"Zarar durdur (-%{SL_ROE:g}): {sl:.2f}", ""] + _score_lines(row, d))


def _close_text(pos: dict, row: pd.Series, exit_price: float, reason: str) -> str:
    r = roe(pos["dir"], pos["entry"], exit_price)
    pct = r / LEVERAGE
    return (f"{'✅' if r >= 0 else '❌'} FUTURES – İŞLEMİ KAPAT ({_side(pos['dir'])} {LEVERAGE:g}x)  |  "
            f"{row['close_time']:%Y-%m-%d %H:%M} UTC\n"
            f"Sebep: {reason}\n"
            f"Giriş: {pos['entry']:.2f}  →  Çıkış: {exit_price:.2f}\n"
            f"{'Kâr' if r >= 0 else 'Zarar'}: {r:+.2f}% ({LEVERAGE:g}x)  ·  fiyat {pct:+.2f}%")


def process_events(data: pd.DataFrame, state: dict, since=None) -> list:
    """Mumları sırayla işler; tek seferde tek işlem. (zaman, tür, mesaj, bilgi) listesi döner."""
    events = []
    rows = data if since is None else data[data["close_time"] > since]
    for _, row in rows.iterrows():
        pos = state.get("position")
        if pos and row["close_time"] > pd.Timestamp(pos["time"]):
            tp, sl = pos["tp"], pos["sl"]
            stopped = row["Low"] <= sl if pos["dir"] == 1 else row["High"] >= sl
            hit = row["High"] >= tp if pos["dir"] == 1 else row["Low"] <= tp
            exit_price = reason = None
            if stopped:  # aynı mumda ikisi de olduysa temkinli: zarar say
                exit_price, reason = sl, f"-%{SL_ROE:g} zarar durdur"
            elif hit:
                exit_price, reason = tp, f"+%{TP_ROE:g} kâr hedefine ulaşıldı"
            if exit_price is not None:
                events.append((row["close_time"], "KAPAT", _close_text(pos, row, exit_price, reason),
                               {"dir": pos["dir"], "entry": round(pos["entry"], 2), "exit": round(exit_price, 2),
                                "pct": round(roe(pos["dir"], pos["entry"], exit_price), 2), "reason": reason}))
                state["position"] = pos = None
        sig = int(row["new_signal"])
        if sig != 0 and not pos:
            entry = float(row["Close"])
            tp, sl = levels(sig, entry)
            events.append((row["close_time"], "SINYAL", _open_text(row, sig), {"dir": sig, "price": round(entry, 2)}))
            state["position"] = {"dir": sig, "entry": entry, "tp": tp, "sl": sl,
                                 "time": row["close_time"].isoformat()}
    return events


def _status_text(row: pd.Series, pos) -> str:
    lines = ["🕐 SAATLİK DURUM – Futures", f"Bitget {SYMBOL}  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
             f"Fiyat: {row['Close']:.2f}", "", "Puan (+6 = güçlü LONG, -6 = güçlü SHORT):"]
    lines += [f"{n:<5} {int(row[f'score_{n}']):+d}/6" for n in TIMEFRAMES]
    lines.append("")
    if pos:
        r = roe(pos["dir"], pos["entry"], float(row["Close"]))
        lines.append(f"Açık işlem: {_side(pos['dir'])} {LEVERAGE:g}x @ {pos['entry']:.2f}\n"
                     f"Anlık {'kâr' if r >= 0 else 'zarar'}: {r:+.2f}%")
    else:
        lines.append("Açık işlem: yok")
    return "\n".join(lines)


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def check_and_notify(send: bool = True):
    state = _load_state()
    data = build(fetch_5m())
    last = data.iloc[-1]
    print(f"Son 5dk mum: {last['close_time']:%Y-%m-%d %H:%M} UTC  fiyat {last['Close']:.2f}")
    for n in TIMEFRAMES:
        print(f"  {n:<5} puan {int(last[f'score_{n}']):+d}/6")

    since = state.get("last_processed")
    if since is not None:
        now = pd.Timestamp.now(tz="UTC")
        for t, _, text, _ in process_events(data, state, since=pd.Timestamp(since)):
            print(f"\n{text}")
            if send and now - t <= MAX_EVENT_AGE:
                send_telegram(text)
    state["last_processed"] = last["close_time"].isoformat()
    if send and status_due(state, last["close_time"]):
        send_telegram(_status_text(last, state.get("position")))
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    try:
        export_dashboard(data, state)
    except Exception as e:  # panel hatası bildirimleri engellemesin
        print(f"Panel verisi yazılamadı: {e}")


def export_dashboard(data: pd.DataFrame, state: dict):
    last = data.iloc[-1]
    history = dashboard.events_to_list(process_events(data, {}))
    dashboard.write("futures", {
        "symbol": SYMBOL,
        "source": "Bitget Futures",
        "close_time": dashboard.ts(last["close_time"]),
        "price": round(float(last["Close"]), 2),
        "scores": {n: {"score": int(last[f"score_{n}"]),
                       "ind": {c: int(last[f"{c}_{n}"]) for c in CHECKS}} for n in TIMEFRAMES},
        "signal": int(last["signal"]),
        "min_score_5m": MIN_SCORE_5M,
        "min_score_higher": MIN_SCORE_HIGHER,
        "min_higher_tfs": MIN_HIGHER_TFS,
        "leverage": LEVERAGE,
        "tp_roe": TP_ROE,
        "sl_roe": SL_ROE,
        "position": state.get("position"),
        "history": history,
        "stats": dashboard.stats(history),
        "days": DAYS,
    })


def show_history():
    data = build(fetch_5m())
    events = process_events(data, {})
    for t, kind, _, info in events:
        if kind == "SINYAL":
            print(f"{t:%m-%d %H:%M}  {_side(info['dir'])} @ {info['price']:.2f}")
        else:
            print(f"{t:%m-%d %H:%M}  {'✅' if info['pct'] >= 0 else '❌'} KAPAT {info['pct']:+.2f}% ({info['reason']})")
    s = dashboard.stats(dashboard.events_to_list(events))
    print(f"\n{s['closed']} kapanan işlem: {s['wins']} kârlı, {s['losses']} zararlı, toplam {s['total_pct']:+.2f}% ({LEVERAGE:g}x)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Bitget Futures XAUUSDT 10x sinyal botu (simülasyon)")
    p.add_argument("--notify", action="store_true", help="Yeni olayları Telegram'a gönder")
    p.add_argument("--test", action="store_true", help="Telegram'a deneme mesajı gönder")
    p.add_argument("--history", action="store_true", help="Geçmiş işlemleri listele")
    args = p.parse_args()
    if args.test:
        send_telegram("✅ Futures botu bağlandı. Bu bir deneme mesajıdır.\n🟢 = LONG   🔴 = SHORT  (10x, simülasyon)")
    if args.history:
        show_history()
    else:
        check_and_notify(send=args.notify)
