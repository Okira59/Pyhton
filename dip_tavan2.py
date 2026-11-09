"""XAU/USD (altın) Dip-Tavan 2 botu: sadece Lorentzian Classification ve SuperTrend AI.

5dk, 15dk ve 1s grafiklerin hepsinde iki gösterge de yükselişteyse 🟢 AL, düşüşteyse 🔴 SAT.
Kâr/zarar kuralı Dip-Tavan ile aynı (dip_tavan.process_events): -SL_PIPS zarar durdur,
kademeli iz süren stop, kademeli zarar koruma, ters sinyal işlemi çevirir.
"""
import argparse
import json
import os

import pandas as pd

import dashboard
import dip_tavan as dt
from bot import SOURCE_LABEL, SYMBOL, _closed_only, _download, position_line, send_telegram, status_due
from indicators import lorentzian, supertrend_ai

# ---------------------------------------------------------------- AYARLAR ---
TIMEFRAMES = {"5dk": 5, "15dk": 15, "1s": 60}  # hepsinde iki gösterge aynı yönde olmalı
TF_5M = pd.Timedelta(minutes=5)
HISTORY_DAYS = int(os.getenv("HISTORY_DAYS", "120"))
STATE_FILE = os.getenv("STATE_FILE", "dip_tavan2_state.json")
LABEL = "Dip-Tavan 2"
MAX_EVENT_AGE = pd.Timedelta(hours=1)
# ----------------------------------------------------------------------------

CHECKS = ["LORENTZIAN", "SUPERTREND"]
NAMES = {"LORENTZIAN": "Lorentzian", "SUPERTREND": "SuperTrend AI"}


def _resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 5:
        return df
    return df.resample(f"{minutes}min", origin="start_day").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()


def directions(df: pd.DataFrame) -> pd.DataFrame:
    """+1 = yükseliş, -1 = düşüş. Lorentzian, verinin başlangıcına bağlı kalmasın diye relative=True."""
    lor, _, _ = lorentzian(df, relative=True)
    st, line, _ = supertrend_ai(df)
    out = pd.DataFrame({"LORENTZIAN": lor.astype(int), "SUPERTREND": st.astype(int)}, index=df.index)
    out["score"] = out[CHECKS].sum(axis=1)
    out["st_line"] = line
    return out


def build(raw: pd.DataFrame) -> pd.DataFrame:
    base = raw.copy()
    base["close_time"] = base.index + TF_5M
    for name, minutes in TIMEFRAMES.items():
        tf = pd.Timedelta(minutes=minutes)
        s = directions(_closed_only(_resample(raw, minutes), tf)).add_suffix(f"_{name}")
        s["close_time"] = s.index + tf
        base = pd.merge_asof(base.sort_values("close_time"), s.sort_values("close_time"),
                             on="close_time", direction="backward")
    base.index = base["close_time"]
    base = base.dropna(subset=[f"score_{n}" for n in TIMEFRAMES])
    full = len(CHECKS)
    long_ = pd.concat([base[f"score_{n}"] == full for n in TIMEFRAMES], axis=1).all(axis=1)
    short = pd.concat([base[f"score_{n}"] == -full for n in TIMEFRAMES], axis=1).all(axis=1)
    sig = long_.astype(int) - short.astype(int)
    base["signal"] = sig
    base["new_signal"] = sig.where((sig != 0) & (sig != sig.shift()), 0)
    return base


def fetch() -> pd.DataFrame:
    return build(_closed_only(_download("5m", f"{HISTORY_DAYS}d"), TF_5M))


def _arrow(v) -> str:
    return "🟢" if v == 1 else "🔴" if v == -1 else "⚪"


def _open_text(row: pd.Series, direction: int) -> str:
    head = "🟢🟢 DİP-TAVAN 2 – AL SİNYALİ 🟢🟢" if direction == 1 else "🔴🔴 DİP-TAVAN 2 – SAT SİNYALİ 🔴🔴"
    c = float(row["Close"])
    sl = dt._sl(direction, c)
    lines = [head, f"XAU/USD ({SOURCE_LABEL})  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
             f"Giriş fiyatı: {c:.2f}",
             f"Zarar durdur (-{dt.SL_PIPS:g} pip): {sl:.2f}",
             f"Sabit kâr al yok: kâr +{dt.TRAIL_START:g} pip olunca iz süren stop {dt.TRAIL_GAP:g} pip geriden başlar, "
             f"kâr arttıkça mesafe daralır (en az {dt.TRAIL_MIN:g}).",
             f"Zarar -{dt.LOSS_START:g} pip olursa: fiyat dipten {dt.LOSS_GAP:g} pip toparlanınca kapat; "
             f"zarar derinleştikçe mesafe daralır (en az {dt.LOSS_MIN:g}).",
             f"🛑 Girişte zarar durdur emri koyun: {sl:.2f}", ""]
    for name in TIMEFRAMES:
        lines.append(f"{name:<5} " + "  ".join(f"{_arrow(row[f'{c}_{name}'])} {NAMES[c]}" for c in CHECKS))
    return "\n".join(lines)


def process_events(data: pd.DataFrame, state: dict, since=None) -> list:
    return dt.process_events(data, state, since=since, open_text=_open_text, label=LABEL)


def _status_text(row: pd.Series, pos) -> str:
    lines = [f"🕐 SAATLİK DURUM – {LABEL}",
             f"XAU/USD ({SOURCE_LABEL})  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
             f"Fiyat: {row['Close']:.2f}", ""]
    for n in TIMEFRAMES:
        lines.append(f"{n:<5} " + "  ".join(f"{_arrow(row[f'{c}_{n}'])} {NAMES[c]}" for c in CHECKS))
    lines += ["", f"Sinyal için {', '.join(TIMEFRAMES)}'te iki gösterge aynı yönde olmalı.",
              position_line(pos, float(row["Close"]))]
    return "\n".join(lines)


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def check_and_notify(send: bool = True):
    state = _load_state()
    data = fetch()
    last = data.iloc[-1]
    print(f"Son mum: {last['close_time']:%Y-%m-%d %H:%M} UTC  fiyat {last['Close']:.2f}")
    for n in TIMEFRAMES:
        print(f"  {n:<5} " + "  ".join(f"{c} {int(last[f'{c}_{n}']):+d}" for c in CHECKS))
    since = state.get("last_processed")
    if since is not None:
        now = pd.Timestamp.now(tz="UTC")
        for t, kind, text, _ in process_events(data, state, since=pd.Timestamp(since)):
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
    start = last["close_time"] - pd.Timedelta(days=60)
    history = [e for e in dashboard.events_to_list(process_events(data, {}))
               if e["kind"] != "TAKIP" and e["t"] >= dashboard.ts(start)]
    tail = data.tail(dashboard.N_CANDLES)
    dashboard.write("dip_tavan2", {
        "symbol": SYMBOL,
        "source": SOURCE_LABEL,
        "bar_label": "5dk",
        "bar_sec": 300,
        "close_time": dashboard.ts(last["close_time"]),
        "price": round(float(last["Close"]), 2),
        "checks": CHECKS,
        "required_tfs": list(TIMEFRAMES),
        "dirs": {n: {c: int(last[f"{c}_{n}"]) for c in CHECKS} for n in TIMEFRAMES},
        "sl_pips": dt.SL_PIPS, "trail_start": dt.TRAIL_START, "trail_gap": dt.TRAIL_GAP,
        "trail_step": dt.TRAIL_STEP, "trail_min": dt.TRAIL_MIN, "loss_start": dt.LOSS_START,
        "loss_gap": dt.LOSS_GAP, "loss_step": dt.LOSS_STEP, "loss_min": dt.LOSS_MIN,
        "pip_size": dt.PIP_SIZE,
        "position": state.get("position"),
        "history": history,
        "stats": dashboard.stats(history),
        "candles": dashboard.candles(data, data.index - TF_5M),
        "st_line": [[dashboard.ts(t - TF_5M), round(float(v), 2), int(d)]
                    for t, v, d in zip(tail.index, tail["st_line_5dk"], tail["SUPERTREND_5dk"])],
    })


def show_history():
    data = fetch()
    pips = []
    for t, kind, _, info in process_events(data, {}):
        if kind == "SINYAL":
            print(f"{t:%m-%d %H:%M}  {'🟢 AL ' if info['dir'] == 1 else '🔴 SAT'} @ {info['price']:.2f}")
        elif kind == "KAPAT":
            pips.append(info["pips"])
            print(f"{t:%m-%d %H:%M}  {'✅' if info['pips'] >= 0 else '❌'} KAPAT {info['pips']:+.1f} pip · {info['reason']}")
    if pips:
        print(f"\n{len(pips)} işlem, {sum(p >= 0 for p in pips)} kârlı, toplam {sum(pips):+.1f} pip")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Altın Dip-Tavan 2 (Lorentzian + SuperTrend AI) botu")
    p.add_argument("--notify", action="store_true", help="Yeni olayları Telegram'a gönder")
    p.add_argument("--test", action="store_true", help="Telegram'a deneme mesajı gönder")
    p.add_argument("--history", action="store_true", help="Geçmiş sinyalleri ve sonuçları listele")
    args = p.parse_args()
    if args.test:
        send_telegram(f"✅ {LABEL} botu bağlandı (Lorentzian + SuperTrend AI). Bu bir deneme mesajıdır.")
    if args.history:
        show_history()
    else:
        check_and_notify(send=args.notify)
