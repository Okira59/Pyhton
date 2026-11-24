"""Dip-Tavan 3: Dip-Tavan göstergeleriyle kesişme noktasında LONG/SHORT, 0.03 lot sanal takip.

Giriş: Dip-Tavan'ın dip (tavan) koşulu son SETUP_BARS 15dk mum içinde oluştuysa, 15dk mum
kapanışı EMA9'u yukarı (aşağı) kestiği anda LONG (SHORT) açılır. Ters yönde kesişme işlemi çevirir.
Çıkış (1dk mumlarla izlenir): -SL_PIPS pip zarar durdur; kâr +LOCK_PIPS pip olunca stop +LOCK_PIPS'e
kilitlenir (ne olursa olsun bu kâr korunur), sonra kademeli iz süren stop: stop = zirve - mesafe,
mesafe = max(TRAIL_MIN, TRAIL_GAP - TRAIL_STEP * (zirve - LOCK_PIPS)), hiçbir zaman +LOCK_PIPS'in altına inmez.
Gerçek işlem açmaz, Telegram'a mesaj göndermez; panel verisini docs/data/dip_tavan3.json'a yazar.
"""
import json
import os

import pandas as pd

import dashboard
import dip_tavan as dt
from bot import SOURCE_LABEL, SYMBOL, TF_15M, _closed_only, _download
from indicators import ema

# ---------------------------------------------------------------- AYARLAR ---
LOT = float(os.getenv("LOT", "0.03"))
OZ_PER_LOT = 100                     # 1 lot XAUUSD = 100 ons → 0.03 lot = pip başına $3
PIP_SIZE = dt.PIP_SIZE               # altında 1 pip = 1 $
SL_PIPS = float(os.getenv("SL_PIPS", "5"))
LOCK_PIPS = float(os.getenv("LOCK_PIPS", "7"))
TRAIL_GAP = float(os.getenv("TRAIL_GAP", "5"))
TRAIL_STEP = float(os.getenv("TRAIL_STEP", "0.25"))
TRAIL_MIN = float(os.getenv("TRAIL_MIN", "2"))
SPREAD_PIPS = float(os.getenv("SPREAD_PIPS", "0.3"))
CROSS_EMA = 9
SETUP_BARS = 6                       # dip/tavan koşulu son 6 mumda (1,5 saat) oluşmuş olmalı
STATE_FILE = os.getenv("STATE_FILE", "dip_tavan3_state.json")
TF_1M = pd.Timedelta(minutes=1)
# ----------------------------------------------------------------------------


def signals(base: pd.DataFrame) -> pd.Series:
    """15dk kapanış zamanına göre +1 (LONG) / -1 (SHORT) / 0."""
    higher = [n for n in dt.TIMEFRAMES if n != "15dk"]

    def setup(key):
        ok = (base[f"{key}_15dk"] >= dt.MIN_SCORE_15M) & base[f"{key}_list_15dk"].map(lambda x: dt.REQUIRED_15M in x) & \
            (base[[f"{key}_{n}" for n in higher]].ge(dt.MIN_SCORE_HIGHER).sum(axis=1) >= 2)
        return ok.rolling(SETUP_BARS, min_periods=1).max() > 0

    c = base["Close"]
    e = ema(c, CROSS_EMA)
    up = (c > e) & (c.shift() <= e.shift())
    dn = (c < e) & (c.shift() >= e.shift())
    return (up & setup("dip")).astype(int) - (dn & setup("top")).astype(int)


def usd(pips: float) -> float:
    return round(float(pips - SPREAD_PIPS) * PIP_SIZE * LOT * OZ_PER_LOT, 2)


def trail_gap(peak: float) -> float:
    return max(TRAIL_MIN, TRAIL_GAP - TRAIL_STEP * (peak - LOCK_PIPS))


def _stop_reason(pos: dict) -> str:
    if not pos["lock"]:
        return f"-{SL_PIPS:g} pip zarar durdur"
    locked = pos["dir"] * (pos["sl"] - pos["entry"]) / PIP_SIZE
    kind = f"+{LOCK_PIPS:g} pip kilit" if locked < LOCK_PIPS + 0.05 else "iz süren stop"
    return f"{kind} (zirve +{pos['peak']:.1f} pip)"


def _close(pos: dict, t, px: float, reason: str) -> dict:
    px = float(px)
    pips = round(pos["dir"] * (px - pos["entry"]) / PIP_SIZE, 1)
    return {"t": dashboard.ts(t), "kind": "KAPAT", "dir": pos["dir"], "entry": round(pos["entry"], 2),
            "exit": round(px, 2), "pips": pips, "usd": usd(pips), "open_t": pos["t"],
            "pct": round(pos["dir"] * (px - pos["entry"]) / pos["entry"] * 100, 3), "reason": reason}


def _trail(pos: dict, px: float) -> bool:
    d, e = pos["dir"], pos["entry"]
    pos["peak"] = max(pos["peak"], d * (px - e) / PIP_SIZE)
    if pos["peak"] < LOCK_PIPS:
        return False
    pos["lock"] = True
    want = max(LOCK_PIPS, pos["peak"] - trail_gap(pos["peak"]))
    pos["sl"] = e + d * max(d * (pos["sl"] - e) / PIP_SIZE, want) * PIP_SIZE
    return True


def simulate(base: pd.DataFrame, sig: pd.Series, m1: pd.DataFrame):
    """Sinyalleri 15dk kapanışında açar, stopları 1dk mumlarla izler; (olaylar, açık işlem) döner."""
    events, pos = [], None
    sig = sig[sig != 0]
    st, sv, si = list(sig.index), [int(v) for v in sig.values], 0
    close = base["Close"]
    O, H, L, C = (m1[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    T = m1.index
    for i in range(T.searchsorted(st[0]) if st else len(T), len(T)):
        while si < len(st) and st[si] <= T[i]:
            s, t = sv[si], st[si]
            px = float(close.loc[t])
            si += 1
            if pos and pos["dir"] != s:
                events.append(_close(pos, t, px, "ters yönde kesişme"))
                pos = None
            if not pos:
                events.append({"t": dashboard.ts(t), "kind": "SINYAL", "dir": s, "price": round(px, 2)})
                pos = {"t": dashboard.ts(t), "dir": s, "entry": px, "sl": px - s * SL_PIPS * PIP_SIZE,
                       "peak": 0.0, "lock": False}
        if not pos:
            continue
        d, e, t_end = pos["dir"], pos["entry"], T[i] + TF_1M
        hi, lo = (H[i], L[i]) if d == 1 else (L[i], H[i])
        _trail(pos, O[i])  # dakikanın ilk fiyatı açılış: kilit/iz önce ona göre güncellenir
        if d * (lo - pos["sl"]) <= 0:  # aynı dakikada önce stop varsayılır
            px = pos["sl"] if d * (O[i] - pos["sl"]) > 0 else O[i]
            events.append(_close(pos, t_end, px, _stop_reason(pos)))
            pos = None
            continue
        if _trail(pos, hi):
            if d * (C[i] - pos["sl"]) <= 0:
                events.append(_close(pos, t_end, pos["sl"], _stop_reason(pos)))
                pos = None
    if pos:
        pos = {**pos, "entry": round(pos["entry"], 2), "sl": round(pos["sl"], 2), "peak": round(pos["peak"], 1)}
    return events, pos


def trades_of(events: list) -> list:
    return [e for e in events if e["kind"] == "KAPAT"]


def periods(trades: list, freq: str) -> list:
    out = {}
    for t in trades:
        ts = pd.Timestamp(t["t"], unit="s", tz="UTC").tz_convert("Europe/Istanbul")
        start = ts.normalize() - pd.Timedelta(days=ts.weekday() if freq == "W" else 0)
        k = start.strftime("%Y-%m-%d")
        p = out.setdefault(k, {"start_day": k, "trades": 0, "wins": 0, "usd": 0.0, "pips": 0.0})
        p["trades"] += 1
        p["wins"] += t["usd"] >= 0
        p["usd"] = round(p["usd"] + t["usd"], 2)
        p["pips"] = round(p["pips"] + t["pips"], 1)
    return list(out.values())


def summary(trades: list, start_t: int) -> dict:
    eq, peak, dd, curve = 0.0, 0.0, 0.0, [[start_t, 0.0]]
    for t in trades:
        eq = round(eq + t["usd"], 2)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
        curve.append([t["t"], eq])
    wins = sum(t["usd"] >= 0 for t in trades)
    return {"start_t": start_t, "closed": len(trades), "wins": wins, "losses": len(trades) - wins,
            "usd": eq, "pips": round(sum(t["pips"] for t in trades), 1), "max_dd": round(dd, 2),
            "locked": sum("kilit" in t["reason"] or "iz süren" in t["reason"] for t in trades),
            "stopped": sum("zarar durdur" in t["reason"] for t in trades),
            "days": periods(trades, "D"), "weeks": periods(trades, "W"), "curve": curve}


def run():
    base = dt.fetch()
    m1 = _closed_only(_download("1m", "60d"), TF_1M)
    m1 = m1[m1.index >= base.index[0]]
    last = base.iloc[-1]
    close_t = dashboard.ts(last["close_time"])
    events, pos = simulate(base, signals(base), m1)

    try:
        state = json.load(open(STATE_FILE, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {"start_t": close_t, "events": []}  # canlı takip bu andan itibaren başlar
    start = state["start_t"]
    kept = state["events"]
    last_t = max([e["t"] for e in kept], default=start)
    # kaydedilmiş olaylar sabit kalır; yalnızca sonrası eklenir (takip başlangıcından önce açılanlar sayılmaz)
    kept += [e for e in events if e["t"] > last_t and e.get("open_t", e["t"]) >= start]
    state["events"] = kept
    live_pos = pos if pos and pos["t"] >= start else None
    state["position"] = live_pos
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)

    price = float(m1["Close"].iloc[-1]) if len(m1) else float(last["Close"])
    if live_pos:
        live_pos = {**live_pos, "pips": round(live_pos["dir"] * (price - live_pos["entry"]) / PIP_SIZE, 1)}
        live_pos["usd"] = usd(live_pos["pips"])
    first_t = dashboard.ts(base.index[0])
    ref_trades = trades_of(events)
    ref = summary(ref_trades, first_t)
    ref["end_t"] = close_t
    acc = summary(trades_of(kept), start)
    acc["equity"] = round(acc["usd"] + (live_pos["usd"] if live_pos else 0), 2)

    dashboard.write("dip_tavan3", {
        "symbol": SYMBOL, "source": SOURCE_LABEL, "close_time": close_t, "price": round(price, 2),
        "pip_size": PIP_SIZE,
        "rule": {"lot": LOT, "usd_per_pip": round(LOT * OZ_PER_LOT * PIP_SIZE, 2), "spread_pips": SPREAD_PIPS,
                 "sl": SL_PIPS, "lock": LOCK_PIPS, "trail_gap": TRAIL_GAP, "trail_step": TRAIL_STEP,
                 "trail_min": TRAIL_MIN, "cross_ema": CROSS_EMA, "setup_bars": SETUP_BARS,
                 "min_15m": dt.MIN_SCORE_15M, "lookback": dt.LOOKBACK},
        "position": live_pos, "account": acc, "history": kept[-300:],
        "ref": ref, "ref_trades": ref_trades, "ref_open": pos,
        "candles": dashboard.candles(base, base.index - TF_15M),
    })
    print(f"Dip-Tavan 3: canlı {acc['closed']} işlem {acc['usd']:+.2f}$, açık: {bool(live_pos)}; "
          f"son 60 gün {ref['closed']} işlem {ref['usd']:+.2f}$ (0.03 lot)")


if __name__ == "__main__":
    run()
