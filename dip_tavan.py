"""XAU/USD (altın) dip/tavan botu.

15dk, 30dk, 45dk ve 1s grafiklerde EMA, Bollinger, RSI, StochRSI, MACD ve Hacim
göstergeleriyle dip (🟢 AL) ve tavan (🔴 SAT) noktalarını arar. Sabit kâr al yok:
-SL_PIPS zarar durdur, kâr TRAIL_START pip olunca stop zirvenin TRAIL_GAP pip
gerisinden takip eder; ters yönde yeni sinyal işlemi kapatıp çevirir.
"""
import argparse
import json
import os

import pandas as pd

import dashboard
from bot import SOURCE_LABEL, SYMBOL, TF_15M, _closed_only, _download, position_line, send_telegram, status_due
from indicators import bollinger, ema, macd_dema, rsi, stoch_buy, stoch_rsi, stoch_sell

# ---------------------------------------------------------------- AYARLAR ---
TIMEFRAMES = {"15dk": 15, "30dk": 30, "45dk": 45, "1s": 60}
EMA_FAST, EMA_SLOW = 9, 21
BB_PERIOD, BB_STD = 20, 2.0
RSI_PERIOD, RSI_LOW, RSI_HIGH = 14, 35, 65
VOLUME_PERIOD, VOLUME_SPIKE = 20, 1.5
LOOKBACK = 5            # dip/tavan koşulları son 5 mum içinde aranır
MIN_SCORE_15M = 3       # 15dk'da 6 göstergeden en az 3'ü dip/tavan demeli
REQUIRED_15M = "STOCHRSI"  # ...ve bunlardan biri StochRSI (son 5 mumda tam 0 / 100) olmalı
MIN_SCORE_HIGHER = 1    # 30dk/45dk/1s'den en az ikisinde en az 1 gösterge onaylamalı

SL_PIPS = float(os.getenv("SL_PIPS", "25"))  # zarar durdur
TRAIL_START = float(os.getenv("TRAIL_START", "20"))  # bu kâra ulaşınca iz süren stop başlar
TRAIL_GAP = float(os.getenv("TRAIL_GAP", "10"))      # zirve kârın bu kadar gerisinden takip
PIP_SIZE = float(os.getenv("PIP_SIZE", "1.0"))  # altında 1 pip = 1 $

STATE_FILE = os.getenv("STATE_FILE", "dip_tavan_state.json")
MAX_EVENT_AGE = pd.Timedelta(hours=1)  # bundan eski olaylar bildirilmez
# ----------------------------------------------------------------------------

CHECKS = ["EMA", "BOLLINGER", "RSI", "STOCHRSI", "MACD", "HACIM"]


def _resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 15:
        return df
    return df.resample(f"{minutes}min", origin="start_day").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()


def dip_top_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Her mum için kaç göstergenin dip / tavan dediğini sayar (0-6)."""
    c, o, h, l, v = df.Close, df.Open, df.High, df.Low, df.Volume
    e_fast, e_slow = ema(c, EMA_FAST), ema(c, EMA_SLOW)
    up, _, low = bollinger(c, BB_PERIOD, BB_STD)
    r = rsi(c, RSI_PERIOD)
    k, _ = stoch_rsi(c)
    _, _, hist = macd_dema(c)
    vol_spike = (v > VOLUME_SPIKE * v.rolling(VOLUME_PERIOD).mean()).rolling(LOOKBACK).max() > 0
    w = LOOKBACK

    dip = pd.DataFrame({
        "BOLLINGER": (l <= low).rolling(w).max() > 0,               # alt banda dokundu
        "RSI": (r.rolling(w).min() < RSI_LOW) & (r > r.shift()),     # aşırı satımdan dönüyor
        "STOCHRSI": stoch_buy(k).rolling(w).max() > 0,                # %K tam 0,00'a indi
        "MACD": (hist < 0) & (hist > hist.shift()),                  # düşüş momentumu zayıflıyor
        "EMA": (c > e_fast) & (e_fast < e_slow),                     # düşüş trendinde EMA9 geri alındı
        "HACIM": vol_spike,                                          # hacim patlaması
    })
    top = pd.DataFrame({
        "BOLLINGER": (h >= up).rolling(w).max() > 0,
        "RSI": (r.rolling(w).max() > RSI_HIGH) & (r < r.shift()),
        "STOCHRSI": stoch_sell(k).rolling(w).max() > 0,               # %K tam 100,00'a çıktı
        "MACD": (hist > 0) & (hist < hist.shift()),
        "EMA": (c < e_fast) & (e_fast > e_slow),
        "HACIM": vol_spike,
    })
    out = pd.DataFrame(index=df.index)
    out["dip"] = dip.sum(axis=1)
    out["top"] = top.sum(axis=1)
    out["dip_list"] = dip.apply(lambda r_: [n for n in CHECKS if r_[n]], axis=1)
    out["top_list"] = top.apply(lambda r_: [n for n in CHECKS if r_[n]], axis=1)
    return out


def build(raw: pd.DataFrame) -> pd.DataFrame:
    base = raw.copy()
    base["close_time"] = base.index + TF_15M
    for name, minutes in TIMEFRAMES.items():
        tf = pd.Timedelta(minutes=minutes)
        s = dip_top_scores(_closed_only(_resample(raw, minutes), tf)).add_suffix(f"_{name}")
        s["close_time"] = s.index + tf
        base = pd.merge_asof(base.sort_values("close_time"), s.sort_values("close_time"),
                             on="close_time", direction="backward")
    base.index = base["close_time"]
    base = base.dropna(subset=[f"dip_{n}" for n in TIMEFRAMES])

    higher = [n for n in TIMEFRAMES if n != "15dk"]
    dip = (base["dip_15dk"] >= MIN_SCORE_15M) & base["dip_list_15dk"].map(lambda x: REQUIRED_15M in x) & \
        (base[[f"dip_{n}" for n in higher]].ge(MIN_SCORE_HIGHER).sum(axis=1) >= 2)
    top = (base["top_15dk"] >= MIN_SCORE_15M) & base["top_list_15dk"].map(lambda x: REQUIRED_15M in x) & \
        (base[[f"top_{n}" for n in higher]].ge(MIN_SCORE_HIGHER).sum(axis=1) >= 2)
    sig = dip.astype(int) - top.astype(int)
    base["new_signal"] = sig.where((sig != 0) & (sig != sig.shift()), 0)
    return base


def fetch() -> pd.DataFrame:
    return build(_closed_only(_download("15m", "60d", with_volume=True), TF_15M))


def _open_text(row: pd.Series, direction: int) -> str:
    key = "dip" if direction == 1 else "top"
    head = "🟢🟢 DİP – AL SİNYALİ 🟢🟢" if direction == 1 else "🔴🔴 TAVAN – SAT SİNYALİ 🔴🔴"
    c = float(row["Close"])
    lines = [head, f"XAU/USD ({SOURCE_LABEL})  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
             f"Giriş fiyatı: {c:.2f}",
             f"Zarar durdur (-{SL_PIPS:g} pip = -${SL_PIPS * PIP_SIZE:g}): {_sl(direction, c):.2f}",
             f"Sabit kâr al yok: kâr +{TRAIL_START:g} pip ({c + direction * TRAIL_START * PIP_SIZE:.2f}) olunca "
             f"iz süren stop devreye girer, zirvenin {TRAIL_GAP:g} pip gerisinden takip eder.",
             f"🛑 Girişte zarar durdur emri koyun: {_sl(direction, c):.2f}", ""]
    for name in TIMEFRAMES:
        lst = row[f"{key}_list_{name}"]
        lines.append(f"{name:<5} {len(lst)}/6  {', '.join(lst) if lst else '-'}")
    return "\n".join(lines)


def _sl(direction: int, entry: float) -> float:
    return entry - direction * SL_PIPS * PIP_SIZE


def _close_text(pos: dict, row: pd.Series, exit_price: float, reason: str) -> str:
    pct = pos["dir"] * (exit_price - pos["entry"]) / pos["entry"] * 100
    pips = pos["dir"] * (exit_price - pos["entry"]) / PIP_SIZE
    icon = "✅" if pct >= 0 else "❌"
    side = "AL" if pos["dir"] == 1 else "SAT"
    return (f"{icon} İŞLEMİ KAPAT ({side})  |  {row['close_time']:%Y-%m-%d %H:%M} UTC\n"
            f"Sebep: {reason}\n"
            f"Giriş: {pos['entry']:.2f}  →  Çıkış: {exit_price:.2f}\n"
            f"{'Kâr' if pct >= 0 else 'Zarar'}: {pct:+.2f}%  ({pips:+.1f} pip = {pips * PIP_SIZE:+.2f}$)")


def _close(pos: dict, row: pd.Series, price: float, reason: str) -> tuple:
    pct = pos["dir"] * (price - pos["entry"]) / pos["entry"] * 100
    pips = pos["dir"] * (price - pos["entry"]) / PIP_SIZE
    return (row["close_time"], "KAPAT", _close_text(pos, row, price, reason),
            {"dir": pos["dir"], "entry": round(pos["entry"], 2), "exit": round(price, 2),
             "pct": round(pct, 3), "pips": round(pips, 1), "reason": reason})


def process_events(data: pd.DataFrame, state: dict, since=None) -> list:
    """Mumları sırayla işler: zarar durdur / iz süren stop / ters sinyal (KAPAT), iz süren
    stop başlangıcı (TAKIP) ve yeni AL/SAT olayları; (zaman, tür, mesaj, bilgi) listesi döner."""
    events = []
    rows = data if since is None else data[data["close_time"] > since]
    for _, row in rows.iterrows():
        t, pos, sig = row["close_time"], state.get("position"), int(row["new_signal"])
        if pos and "sl" not in pos:  # eski (sabit kâr al) kayıt
            pos.update(sl=_sl(pos["dir"], pos["entry"]), peak=0.0, trail=False)
        if pos and t > pd.Timestamp(pos["time"]):
            d, e = pos["dir"], pos["entry"]
            hi, lo = (row["High"], row["Low"]) if d == 1 else (row["Low"], row["High"])
            if d * (lo - pos["sl"]) <= 0:  # aynı mumda önce stop varsayılır (temkinli)
                reason = (f"iz süren stop (zirve +{pos['peak']:.1f} pip)" if pos["trail"]
                          else f"-{SL_PIPS:g} pip zarar durdur")
                events.append(_close(pos, row, pos["sl"], reason))
                state["position"] = pos = None
            else:
                pos["peak"] = max(pos["peak"], d * (hi - e) / PIP_SIZE)
                if pos["peak"] >= TRAIL_START:
                    pos["sl"] = e + d * max(d * (pos["sl"] - e) / PIP_SIZE, pos["peak"] - TRAIL_GAP) * PIP_SIZE
                    if not pos["trail"]:
                        pos["trail"] = True
                        events.append((t, "TAKIP",
                                       f"🔒 İZ SÜREN STOP DEVREDE (Dip-Tavan)  |  {t:%Y-%m-%d %H:%M} UTC\n"
                                       f"{'AL' if d == 1 else 'SAT'} @ {e:.2f} · kâr +{pos['peak']:.1f} pip\n"
                                       f"Yeni stop: {pos['sl']:.2f} (en az {d * (pos['sl'] - e) / PIP_SIZE:+.1f} pip kilitli)", {}))
        if sig and pos and pos["dir"] != sig:
            events.append(_close(pos, row, float(row["Close"]), "ters yönde yeni sinyal"))
            state["position"] = pos = None
        if sig and not pos:
            c = float(row["Close"])
            events.append((t, "SINYAL", _open_text(row, sig), {"dir": sig, "price": round(c, 2)}))
            state["position"] = {"dir": sig, "entry": c, "sl": _sl(sig, c), "peak": 0.0,
                                 "trail": False, "time": t.isoformat()}
    return events


def _status_text(row: pd.Series, pos) -> str:
    lines = ["🕐 SAATLİK DURUM – Dip/Tavan",
             f"XAU/USD ({SOURCE_LABEL})  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
             f"Fiyat: {row['Close']:.2f}", "",
             f"{'':<5} {'🟢 dip':<7} {'🔴 tavan':<8}"]
    for n in TIMEFRAMES:
        lines.append(f"{n:<5} {int(row[f'dip_{n}'])}/6     {int(row[f'top_{n}'])}/6")
    lines += ["", f"Sinyal için 15dk'da StochRSI dahil en az {MIN_SCORE_15M}/6 gerekli.",
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
        print(f"  {n:<5} dip {int(last[f'dip_{n}'])}/6   tavan {int(last[f'top_{n}'])}/6")

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
    history = [e for e in dashboard.events_to_list(process_events(data, {})) if e["kind"] != "TAKIP"]
    dashboard.write("dip_tavan", {
        "symbol": SYMBOL,
        "source": SOURCE_LABEL,
        "close_time": dashboard.ts(last["close_time"]),
        "price": round(float(last["Close"]), 2),
        "scores": {n: {"dip": int(last[f"dip_{n}"]), "top": int(last[f"top_{n}"]),
                       "dip_list": list(last[f"dip_list_{n}"]),
                       "top_list": list(last[f"top_list_{n}"])}
                   for n in TIMEFRAMES},
        "min_score_15m": MIN_SCORE_15M,
        "min_score_higher": MIN_SCORE_HIGHER,
        "lookback": LOOKBACK,
        "required_15m": REQUIRED_15M,
        "sl_pips": SL_PIPS,
        "trail_start": TRAIL_START,
        "trail_gap": TRAIL_GAP,
        "pip_size": PIP_SIZE,
        "position": state.get("position"),
        "history": history,
        "stats": dashboard.stats(history),
        "candles": dashboard.candles(data, data.index - TF_15M),
        "osc": dashboard.oscillators(data["Close"], data.index - TF_15M),
    })


def show_history():
    data = fetch()
    events = process_events(data, {})
    closed = [i["pct"] for _, k, _, i in events if k == "KAPAT"]
    pips = [i["pips"] for _, k, _, i in events if k == "KAPAT"]
    for t, kind, _, info in events:
        pct = info.get("pct")
        if kind == "SINYAL":
            d = int(data.loc[t, "new_signal"])
            print(f"{t:%m-%d %H:%M}  {'🟢 AL ' if d == 1 else '🔴 SAT'} @ {data.loc[t, 'Close']:.2f}")
        elif kind == "KAPAT":
            print(f"{t:%m-%d %H:%M}  {'✅' if pct >= 0 else '❌'} KAPAT {pct:+.2f}% ({info['pips']:+.1f} pip) · {info['reason']}")
    if closed:
        wins = sum(p >= 0 for p in closed)
        print(f"\nToplam {sum(pips):+.1f} pip")
        print(f"{len(closed)} kapanan işlem: {wins} kârlı, {len(closed) - wins} zararlı, "
              f"toplam {sum(closed):+.2f}%, ortalama {sum(closed) / len(closed):+.3f}%")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Altın dip/tavan sinyal botu")
    p.add_argument("--notify", action="store_true", help="Yeni olayları Telegram'a gönder")
    p.add_argument("--test", action="store_true", help="Telegram'a deneme mesajı gönder")
    p.add_argument("--history", action="store_true", help="Son 60 günün sinyallerini ve sonuçlarını listele")
    args = p.parse_args()
    if args.test:
        send_telegram("✅ Dip-Tavan botu bağlandı. Bu bir deneme mesajıdır.\n"
                      "🟢 = AL (dip)   🔴 = SAT (tavan)")
    if args.history:
        show_history()
    else:
        check_and_notify(send=args.notify)
