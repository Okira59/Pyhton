"""Dip-Tavan 2: Dip-Tavan sinyallerini $300'lık sanal hesapta bileşik lotla takip eder.

Gerçek işlem açmaz, Telegram'a mesaj göndermez. dip_tavan.py'nin yazdığı panel verisindeki
AL/SAT/KAPAT olaylarını okur, her işleme o anki kasaya göre lot verir ve kasayı kaydeder.
"""
import json
import math
import os

import pandas as pd

import dashboard

SOURCE_FILE = os.getenv("SOURCE_FILE", os.path.join("docs", "data", "dip_tavan.json"))
STATE_FILE = os.getenv("STATE_FILE", "dip_tavan2_state.json")
START_BALANCE = float(os.getenv("START_BALANCE", "300"))
LOT_STEP_USD = float(os.getenv("LOT_STEP_USD", "300"))   # her $300 kasa için
LOT_LOW = float(os.getenv("LOT_LOW", "0.01"))            # kasa < $1000: her $300 için 0.01 lot
LOT_HIGH = float(os.getenv("LOT_HIGH", "0.02"))          # kasa ≥ $1000: her $300 için 0.02 lot
HIGH_FROM = float(os.getenv("HIGH_FROM", "1000"))
SPREAD_PIPS = float(os.getenv("SPREAD_PIPS", "0.3"))     # işlem başı maliyet
OZ_PER_LOT = 100                                         # 1 lot XAUUSD = 100 ons → 0.01 lot = pip başına $1


def lot_for(balance: float) -> float:
    if balance <= 0:
        return 0.0
    per = LOT_HIGH if balance >= HIGH_FROM else LOT_LOW
    return round(max(1, math.floor(balance / LOT_STEP_USD)) * per, 2)


def pnl_usd(pips: float, lot: float, pip_size: float) -> float:
    return round((pips - SPREAD_PIPS) * pip_size * lot * OZ_PER_LOT, 2)


def replay(history: list, balance: float, after: int, open_=None, pip_size: float = 1.0):
    """after'dan sonraki olayları sırayla işler; (kapanan işlemler, açık işlem, kasa, son olay zamanı)."""
    trades, last = [], after
    for e in history:
        if e["t"] <= after:
            continue
        last = max(last, e["t"])
        if e["kind"] == "SINYAL" and open_ is None and balance > 0:
            open_ = {"t": e["t"], "dir": e["dir"], "entry": e["price"], "lot": lot_for(balance)}
        elif e["kind"] == "KAPAT" and open_ is not None and e["dir"] == open_["dir"]:
            p = pnl_usd(e["pips"], open_["lot"], pip_size)
            balance = round(balance + p, 2)
            trades.append({**open_, "close_t": e["t"], "exit": e["exit"], "pips": e["pips"],
                           "reason": e.get("reason", ""), "pnl": p, "balance": balance})
            open_ = None
    return trades, open_, balance, last


def summary(trades: list, start_t: int) -> dict:
    eq, peak, dd, months = START_BALANCE, START_BALANCE, 0.0, {}
    for t in trades:
        m = pd.Timestamp(t["close_t"], unit="s", tz="UTC").strftime("%Y-%m")
        months.setdefault(m, {"month": m, "start": eq})
        eq = t["balance"]
        months[m]["end"] = eq
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    wins = sum(t["pnl"] >= 0 for t in trades)
    for v in months.values():
        v["pct"] = round((v["end"] / v["start"] - 1) * 100, 1) if v["start"] > 0 else 0.0
    return {"start_t": start_t, "closed": len(trades), "wins": wins, "losses": len(trades) - wins,
            "balance": round(eq, 2), "max_dd_pct": round(dd * 100, 1),
            "net_pct": round((eq / START_BALANCE - 1) * 100, 1), "months": list(months.values()),
            "curve": [[start_t, START_BALANCE]] + [[t["close_t"], t["balance"]] for t in trades]}


def run():
    src = json.load(open(SOURCE_FILE, encoding="utf-8"))
    history, pip = src["history"], src.get("pip_size", 1.0)
    if os.path.exists(STATE_FILE):
        state = json.load(open(STATE_FILE, encoding="utf-8"))
    else:  # takip bu andan itibaren başlar
        state = {"start_t": src["close_time"], "last_t": src["close_time"], "balance": START_BALANCE,
                 "open": None, "trades": []}
    new, state["open"], state["balance"], state["last_t"] = replay(
        history, state["balance"], state["last_t"], state["open"], pip)
    state["trades"] += new
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)

    o = state["open"]
    if o:
        live = src.get("position") or {}
        o = {**o, "time": pd.Timestamp(o["t"], unit="s", tz="UTC").isoformat(),
             "pnl": pnl_usd(o["dir"] * (src["price"] - o["entry"]) / pip, o["lot"], pip)}
        if live.get("dir") == o["dir"] and abs(live.get("entry", 0) - o["entry"]) < 0.01:
            o.update({k: live[k] for k in ("sl", "trail", "lx") if k in live})
    acc = summary(state["trades"], state["start_t"])
    acc["equity"] = round(state["balance"] + (o["pnl"] if o else 0), 2)

    first = history[0]["t"] - 1 if history else 0
    ref_trades, _, _, _ = replay(history, START_BALANCE, first, None, pip)
    ref = summary(ref_trades, first + 1)
    ref["end_t"] = src["close_time"]

    dashboard.write("dip_tavan2", {
        "symbol": src["symbol"], "source": src["source"], "close_time": src["close_time"], "price": src["price"],
        "pip_size": pip, "sl_pips": src.get("sl_pips"),
        "rule": {"start_balance": START_BALANCE, "lot_step_usd": LOT_STEP_USD, "lot_low": LOT_LOW,
                 "lot_high": LOT_HIGH, "high_from": HIGH_FROM, "spread_pips": SPREAD_PIPS},
        "balance": state["balance"], "next_lot": lot_for(state["balance"]), "position": o,
        "account": acc, "trades": state["trades"][-200:],
        "ref": ref, "ref_trades": ref_trades,
    })
    print(f"Dip-Tavan 2: kasa ${state['balance']:.2f}, {len(new)} yeni kapanan işlem, açık: {bool(o)}; "
          f"son 60 gün olsaydı ${ref['balance']:.2f}")


if __name__ == "__main__":
    run()
