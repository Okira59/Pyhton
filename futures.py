"""Bitget USDT vadeli (futures) 10x simülasyon botu – hacmi en yüksek coinler.

Her çalışmada 24s hacmi en yüksek TOP_N coini (ve açık işlemi olan coinleri) tarar.
5dk, 15dk, 30dk, 45dk, 1s ve 4s grafiklerde EMA, Bollinger, RSI, StochRSI, MACD ve
Hacim göstergelerinin yönünü puanlar. 5dk'da güçlü sinyal + üst zaman dilimlerinde
onay olunca 10x LONG/SHORT işlem açılmış sayılır (coin başına tek işlem). Kaldıraçlı
kâr %30'a ya da zarar %20'ye ulaşınca işlem kapatılır. Her işlem isolated $20
teminatla açılır; aynı anda en fazla 5 işlem açık olur (doluyken sinyal bildirilir, işlem açılmaz). 7/24 çalışır (hafta sonu dahil).
Gerçek emir gönderilmez; yalnızca Telegram bildirimi ve panel.
"""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

import bot
import dashboard
from bot import _closed_only, send_telegram, status_due
from indicators import bollinger, ema, macd, rsi, stoch_rsi

# ---------------------------------------------------------------- AYARLAR ---
TOP_N = int(os.getenv("TOP_N", "100"))
WORKERS = 5
TIMEFRAMES = {"5dk": 5, "15dk": 15, "30dk": 30, "45dk": 45, "1s": 60, "4s": 240}
GRAN = {"5dk": "5m", "15dk": "15m", "30dk": "30m", "1s": "1H", "4s": "4H"}  # 45dk = 15dk'dan
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
MARGIN_USD = float(os.getenv("MARGIN_USD", "20"))  # işlem başına isolated teminat ($)
MAX_OPEN = int(os.getenv("MAX_OPEN", "5"))  # aynı anda en fazla açık işlem

STATE_FILE = os.getenv("STATE_FILE", "futures_state.json")
MAX_EVENT_AGE = pd.Timedelta(minutes=30)
MAX_HISTORY = 300
# ----------------------------------------------------------------------------

API = "https://api.bitget.com/api/v2/mix/market/"
CHECKS = ["EMA", "BOLLINGER", "RSI", "STOCHRSI", "MACD", "HACIM"]
TF_5M = pd.Timedelta(minutes=5)
AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


def _get(endpoint: str, params: dict):
    for attempt in range(6):
        try:
            r = requests.get(API + endpoint, params=params, timeout=15)
        except requests.RequestException:
            time.sleep(1 + attempt)
            continue
        if r.status_code == 429:
            time.sleep(1 + attempt)
            continue
        r.raise_for_status()
        time.sleep(0.1)
        return r.json().get("data") or []
    raise RuntimeError(f"Bitget isteği başarısız: {endpoint} {params}")


def top_symbols(n: int = TOP_N) -> list:
    """24s USDT hacmine göre en büyük n vadeli kontrat: [(sembol, hacim_milyon_usdt)]."""
    d = sorted(_get("tickers", {"productType": "USDT-FUTURES"}), key=lambda x: -float(x.get("usdtVolume") or 0))
    return [(x["symbol"], round(float(x.get("usdtVolume") or 0) / 1e6, 1)) for x in d[:n]]


def price_places() -> dict:
    return {c["symbol"]: int(c.get("pricePlace") or 2) for c in _get("contracts", {"productType": "USDT-FUTURES"})}


def _resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 5:
        return df
    origin = "epoch" if minutes == 240 else "start_day"
    return df.resample(f"{minutes}min", origin=origin).agg(AGG).dropna()


def _candles(symbol: str, gran: str, minutes: int) -> pd.DataFrame:
    rows = _get("candles", {"symbol": symbol, "productType": "USDT-FUTURES", "granularity": gran, "limit": 1000})
    df = pd.DataFrame([r_[:6] for r_ in rows], columns=["ts", "Open", "High", "Low", "Close", "Volume"]).astype(float)
    df.index = pd.to_datetime(df.pop("ts").astype("int64"), unit="ms", utc=True)
    return _closed_only(df[~df.index.duplicated()].sort_index(), pd.Timedelta(minutes=minutes))


def fetch_frames(symbol: str) -> dict:
    """Canlı tarama: her zaman dilimi Bitget'ten ayrı çekilir (son 1000 mum)."""
    fr = {n: _candles(symbol, g, TIMEFRAMES[n]) for n, g in GRAN.items()}
    fr["45dk"] = _closed_only(_resample(fr["15dk"], 45), pd.Timedelta(minutes=45))
    return fr


def frames_from_5m(m5: pd.DataFrame) -> dict:
    """Geçmiş testi: tüm zaman dilimleri 5dk mumlardan üretilir."""
    return {n: _closed_only(_resample(m5, m), pd.Timedelta(minutes=m)) for n, m in TIMEFRAMES.items()}


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


def build(frames: dict, min5=None, minh=None, ntf=None) -> pd.DataFrame:
    min5 = MIN_SCORE_5M if min5 is None else min5
    minh = MIN_SCORE_HIGHER if minh is None else minh
    ntf = MIN_HIGHER_TFS if ntf is None else ntf
    base = frames["5dk"].copy()
    base["close_time"] = base.index + TF_5M
    for name, minutes in TIMEFRAMES.items():
        s = directions(frames[name]).add_suffix(f"_{name}")
        s["close_time"] = s.index + pd.Timedelta(minutes=minutes)
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


def levels(direction: int, entry: float):
    return (entry * (1 + direction * TP_ROE / LEVERAGE / 100),
            entry * (1 - direction * SL_ROE / LEVERAGE / 100))


def roe(direction: int, entry: float, price: float) -> float:
    return direction * (price - entry) / entry * 100 * LEVERAGE


def usd(r: float, margin: float = MARGIN_USD) -> float:
    return margin * r / 100


def _side(d: int) -> str:
    return "🟢 LONG" if d == 1 else "🔴 SHORT"


def _coin(sym: str) -> str:
    return sym[:-4] if sym.endswith("USDT") else sym


def _open_text(sym: str, dp: int, row: pd.Series, d: int) -> str:
    tp, sl = levels(d, row["Close"])
    lines = [f"{'🟢🟢' if d == 1 else '🔴🔴'} FUTURES – {_coin(sym)} {'LONG' if d == 1 else 'SHORT'} AÇ ({LEVERAGE:g}x)",
             f"Bitget {sym}  |  {row['close_time']:%Y-%m-%d %H:%M} UTC",
             f"Isolated · teminat ${MARGIN_USD:g} · pozisyon ${MARGIN_USD * LEVERAGE:g}",
             f"Giriş fiyatı: {row['Close']:.{dp}f}",
             f"Kâr al (+%{TP_ROE:g} = +${usd(TP_ROE):.2f}): {tp:.{dp}f}",
             f"Zarar durdur (-%{SL_ROE:g} = -${usd(SL_ROE):.2f}): {sl:.{dp}f}", ""]
    for n in TIMEFRAMES:
        agree = [c for c in CHECKS if int(row[f"{c}_{n}"]) == d]
        lines.append(f"{n:<5} {int(row[f'score_{n}']):+d}/6  {', '.join(agree) if agree else '-'}")
    return "\n".join(lines)


def _close_text(sym: str, dp: int, pos: dict, row: pd.Series, exit_price: float, reason: str) -> str:
    r = roe(pos["dir"], pos["entry"], exit_price)
    return (f"{'✅' if r >= 0 else '❌'} FUTURES – {_coin(sym)} İŞLEMİ KAPAT ({_side(pos['dir'])} {LEVERAGE:g}x)\n"
            f"Bitget {sym}  |  {row['close_time']:%Y-%m-%d %H:%M} UTC\n"
            f"Sebep: {reason}\n"
            f"Giriş: {pos['entry']:.{dp}f}  →  Çıkış: {exit_price:.{dp}f}\n"
            f"{'Kâr' if r >= 0 else 'Zarar'}: {r:+.2f}% ({LEVERAGE:g}x)  =  {usd(r, pos.get('margin', MARGIN_USD)):+.2f}$"
            f"  ·  fiyat {r / LEVERAGE:+.2f}%")


def process_events(sym: str, dp: int, data: pd.DataFrame, cs: dict, since=None, can_open=lambda: True) -> list:
    """Bir coinin mumlarını sırayla işler (coin başına tek işlem). (zaman, tür, mesaj, bilgi) listesi döner."""
    events = []
    rows = data if since is None else data[data["close_time"] > since]
    for _, row in rows.iterrows():
        pos = cs.get("position")
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
                events.append((row["close_time"], "KAPAT", _close_text(sym, dp, pos, row, exit_price, reason),
                               {"sym": sym, "dp": dp, "dir": pos["dir"], "entry": pos["entry"], "exit": exit_price,
                                "pct": round(roe(pos["dir"], pos["entry"], exit_price), 2), "reason": reason,
                                "usd": round(usd(roe(pos["dir"], pos["entry"], exit_price), pos.get("margin", MARGIN_USD)), 2)}))
                cs["position"] = pos = None
        sig = int(row["new_signal"])
        if sig != 0 and not pos and not can_open():
            events.append((row["close_time"], "LIMIT",
                           f"⚠️ LİMİT DOLU ({MAX_OPEN}/{MAX_OPEN} işlem açık) – bu işlem AÇILMADI\n\n"
                           + _open_text(sym, dp, row, sig).replace(" AÇ (", " SİNYALİ (")
                           + "\n\n👉 Kontrol edin, girmek isteyen varsa girebilir.",
                           {"sym": sym, "dp": dp, "dir": sig, "price": float(row["Close"])}))
        elif sig != 0 and not pos:
            entry = float(row["Close"])
            tp, sl = levels(sig, entry)
            events.append((row["close_time"], "SINYAL", _open_text(sym, dp, row, sig),
                           {"sym": sym, "dp": dp, "dir": sig, "price": entry}))
            cs["position"] = {"dir": sig, "entry": entry, "tp": tp, "sl": sl, "dp": dp,
                              "margin": MARGIN_USD, "time": row["close_time"].isoformat()}
    return events


def _scan_one(sym: str):
    try:
        return build(fetch_frames(sym))
    except Exception as e:  # yeni listelenen/az verili coinleri atla
        print(f"{sym}: atlandı ({e})")
        return None


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        st = {}
    st.setdefault("positions", {})
    st.setdefault("last", {})
    st.setdefault("history", [])
    return st


def _status_text(results: dict, state: dict) -> str:
    pos = state["positions"]
    lines = ["🕐 SAATLİK DURUM – Futures", f"Taranan coin: {len(results)}  |  açık işlem: {len(pos)}/{MAX_OPEN}", ""]
    for sym, p in list(pos.items())[:40]:
        data = results.get(sym)
        if data is None:
            continue
        r = roe(p["dir"], p["entry"], float(data["Close"].iloc[-1]))
        lines.append(f"{_side(p['dir'])} {_coin(sym):<8} {r:+.1f}%  {usd(r, p.get('margin', MARGIN_USD)):+.2f}$")
    if not pos:
        lines.append("Açık işlem yok.")
    return "\n".join(lines)


def check_and_notify(send: bool = True):
    state = _load_state()
    top = top_symbols()
    places = price_places()
    # açık işlemi olan coinler önce işlenir: kapanışlar yeni işlemlere yer açsın
    symbols = list(state["positions"]) + [s for s, _ in top if s not in state["positions"]]
    with ThreadPoolExecutor(WORKERS) as ex:
        results = {s: d for s, d in zip(symbols, ex.map(_scan_one, symbols)) if d is not None and len(d)}
    print(f"{len(results)}/{len(symbols)} coin tarandı.")

    now = pd.Timestamp.now(tz="UTC")
    for sym, data in results.items():
        dp = places.get(sym, 2)
        last_t = data["close_time"].iloc[-1]
        since = state["last"].get(sym)
        if since is not None:
            cs = {"position": state["positions"].get(sym)}
            can_open = lambda: len([s for s in state["positions"] if s != sym]) < MAX_OPEN
            for t, kind, text, info in process_events(sym, dp, data, cs, since=pd.Timestamp(since), can_open=can_open):
                print(f"\n{text}")
                if kind != "LIMIT":
                    state["history"].append({"t": dashboard.ts(t), "kind": kind, **info})
                if send and now - t <= MAX_EVENT_AGE:
                    send_telegram(text)
            if cs["position"]:
                state["positions"][sym] = cs["position"]
            else:
                state["positions"].pop(sym, None)
        state["last"][sym] = last_t.isoformat()
    state["history"] = state["history"][-MAX_HISTORY:]
    ref = results.get("BTCUSDT")
    if send and ref is not None and status_due(state, ref["close_time"].iloc[-1]):
        send_telegram(_status_text(results, state))
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1)
    try:
        export_dashboard(results, top, places, state)
    except Exception as e:  # panel hatası bildirimleri engellemesin
        print(f"Panel verisi yazılamadı: {e}")


def export_dashboard(results: dict, top: list, places: dict, state: dict):
    ch = lambda v: "+" if v > 0 else "-" if v < 0 else "0"
    coins = []
    for sym, vol in top:
        data = results.get(sym)
        if data is None:
            continue
        last = data.iloc[-1]
        coins.append({"s": sym, "p": float(last["Close"]), "dp": places.get(sym, 2), "vol": vol,
                      "sig": int(last["signal"]), "t": dashboard.ts(last["close_time"]),
                      "sc": [int(last[f"score_{n}"]) for n in TIMEFRAMES],
                      "ind": ["".join(ch(int(last[f"{c}_{n}"])) for c in CHECKS) for n in TIMEFRAMES]})
    prices = {s: float(d["Close"].iloc[-1]) for s, d in results.items()}
    dashboard.write("futures", {
        "source": "Bitget Futures",
        "timeframes": list(TIMEFRAMES),
        "checks": CHECKS,
        "coins": coins,
        "prices": prices,
        "min_score_5m": MIN_SCORE_5M,
        "min_score_higher": MIN_SCORE_HIGHER,
        "min_higher_tfs": MIN_HIGHER_TFS,
        "leverage": LEVERAGE,
        "tp_roe": TP_ROE,
        "sl_roe": SL_ROE,
        "margin_usd": MARGIN_USD,
        "max_open": MAX_OPEN,
        "positions": state["positions"],
        "history": state["history"],
        "stats": {**dashboard.stats(state["history"]),
                  "total_usd": round(sum(e.get("usd", usd(e["pct"])) for e in state["history"] if e["kind"] == "KAPAT"), 2)},
    })


def show_history(sym: str, days: int):
    bot.SKIP_WEEKEND = False
    m5 = bot._bitget("5m", days, sym)[["Open", "High", "Low", "Close", "Volume"]].dropna()
    data = build(frames_from_5m(_closed_only(m5, TF_5M)))
    events = process_events(sym, 4, data, {})
    for t, kind, _, info in events:
        if kind == "SINYAL":
            print(f"{t:%m-%d %H:%M}  {_side(info['dir'])} @ {info['price']:g}")
        else:
            print(f"{t:%m-%d %H:%M}  {'✅' if info['pct'] >= 0 else '❌'} KAPAT {info['pct']:+.2f}% ({info['reason']})")
    s = dashboard.stats(dashboard.events_to_list(events))
    print(f"\n{sym}: {s['closed']} kapanan işlem, {s['wins']} kârlı, {s['losses']} zararlı, "
          f"toplam {s['total_pct']:+.2f}% ({LEVERAGE:g}x)")
    return s


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Bitget Futures 10x sinyal botu (simülasyon, en hacimli coinler)")
    p.add_argument("--notify", action="store_true", help="Yeni olayları Telegram'a gönder")
    p.add_argument("--test", action="store_true", help="Telegram'a deneme mesajı gönder")
    p.add_argument("--history", metavar="SEMBOL", help="Bir coinin geçmiş testini göster (ör. BTCUSDT)")
    p.add_argument("--days", type=int, default=60)
    args = p.parse_args()
    if args.test:
        send_telegram(f"✅ Futures botu bağlandı. Hacmi en yüksek {TOP_N} coin 7/24 taranıyor.\n"
                      "🟢 = LONG   🔴 = SHORT  (10x, simülasyon)")
    if args.history:
        show_history(args.history, args.days)
    else:
        check_and_notify(send=args.notify)
