"""Futures botunun Bitget'te emir açıp kapatan kısmı (varsayılan: demo hesap).

Gerekli ortam değişkenleri: BITGET_API_KEY, BITGET_API_SECRET, BITGET_PASSPHRASE.
BITGET_TRADE=1 ile açılır. BITGET_DEMO=0 verilmedikçe tüm istekler demo hesaba gider
(Bitget'in istediği "paptrading: 1" başlığıyla).
"""
import base64
import hashlib
import hmac
import json
import math
import os
import time

import pandas as pd
import requests

BASE = "https://api.bitget.com"
PRODUCT = "USDT-FUTURES"
COIN = "USDT"
KEYS = ("BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_PASSPHRASE")
DEMO = os.getenv("BITGET_DEMO", "1") != "0"
OPEN_MAX_AGE = pd.Timedelta(minutes=int(os.getenv("BITGET_OPEN_MAX_AGE_MIN", "10")))  # daha eski sinyallerde emir açılmaz


class BitgetError(Exception):
    pass


def enabled() -> bool:
    return os.getenv("BITGET_TRADE", "0") == "1" and all(os.getenv(k) for k in KEYS)


def mode_name() -> str:
    return "DEMO" if DEMO else "GERÇEK"


def _request(method: str, path: str, params: dict = None, body: dict = None, auth: bool = True):
    query = ("?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))) if params else ""
    payload = json.dumps(body, separators=(",", ":")) if body else ""
    headers = {"Content-Type": "application/json", "locale": "en-US"}
    if DEMO:
        headers["paptrading"] = "1"
    if auth:
        ts = str(int(time.time() * 1000))
        mac = hmac.new(os.environ["BITGET_API_SECRET"].encode(), (ts + method + path + query + payload).encode(),
                       hashlib.sha256)
        headers.update({"ACCESS-KEY": os.environ["BITGET_API_KEY"], "ACCESS-SIGN": base64.b64encode(mac.digest()).decode(),
                        "ACCESS-TIMESTAMP": ts, "ACCESS-PASSPHRASE": os.environ["BITGET_PASSPHRASE"]})
    r = requests.request(method, BASE + path + query, data=payload or None, headers=headers, timeout=15)
    try:
        j = r.json()
    except ValueError:
        raise BitgetError(f"HTTP {r.status_code}")
    if str(j.get("code")) != "00000":
        raise BitgetError(f"{j.get('code')} {j.get('msg')}")
    return j.get("data")


def contracts() -> dict:
    data = _request("GET", "/api/v2/mix/market/contracts", {"productType": PRODUCT}, auth=False)
    return {c["symbol"]: c for c in data if c.get("symbolStatus", "normal") == "normal"}


def account(symbol: str = "BTCUSDT") -> dict:
    return _request("GET", "/api/v2/mix/account/account",
                    {"symbol": symbol, "productType": PRODUCT, "marginCoin": COIN})


def positions() -> dict:
    data = _request("GET", "/api/v2/mix/position/all-position", {"productType": PRODUCT, "marginCoin": COIN}) or []
    return {p["symbol"]: p for p in data if float(p.get("total") or 0) > 0}


def _floor_step(x: float, step: float, places: int) -> float:
    return round(math.floor(x / step + 1e-9) * step, places)


def order_size(info: dict, price: float, margin: float, leverage: float):
    places = int(info["volumePlace"])
    size = _floor_step(margin * leverage / price, float(info["sizeMultiplier"]), places)
    if size < float(info["minTradeNum"]) or size * price < float(info.get("minTradeUSDT") or 0):
        return None
    return f"{size:.{places}f}"


def fmt_price(info: dict, price: float) -> str:
    places = int(info["pricePlace"])
    step = float(info.get("priceEndStep") or 1) / 10 ** places
    return f"{round(round(price / step) * step, places):.{places}f}"


def _hold(d: int, hedge: bool) -> str:
    if hedge:
        return "long" if d == 1 else "short"
    return "buy" if d == 1 else "sell"


def open_position(sym: str, d: int, sl: float, margin: float, leverage: float, info: dict, price: float,
                  hedge: bool) -> dict:
    size = order_size(info, price, margin, leverage)
    if size is None:
        raise BitgetError("işlem büyüklüğü coinin en küçük emir miktarının altında")
    if leverage > float(info.get("maxLever") or leverage):
        raise BitgetError(f"coin en fazla {info['maxLever']}x kaldıraç destekliyor")
    try:
        _request("POST", "/api/v2/mix/account/set-margin-mode",
                 body={"symbol": sym, "productType": PRODUCT, "marginCoin": COIN, "marginMode": "isolated"})
    except BitgetError as e:  # mod zaten isolated ise hata dönebilir
        print(f"{sym}: marj modu ayarlanamadı ({e})")
    lev = {"symbol": sym, "productType": PRODUCT, "marginCoin": COIN, "leverage": f"{leverage:g}"}
    if hedge:
        lev["holdSide"] = _hold(d, True)
    _request("POST", "/api/v2/mix/account/set-leverage", body=lev)
    body = {"symbol": sym, "productType": PRODUCT, "marginMode": "isolated", "marginCoin": COIN, "size": size,
            "side": "buy" if d == 1 else "sell", "orderType": "market", "presetStopLossPrice": fmt_price(info, sl),
            "clientOid": f"okira{int(time.time() * 1000)}{sym[:8]}"}
    if hedge:
        body["tradeSide"] = "open"
    data = _request("POST", "/api/v2/mix/order/place-order", body=body)
    return {"oid": (data or {}).get("orderId"), "size": size}


def _pos_loss_orders(sym: str) -> list:
    data = _request("GET", "/api/v2/mix/order/orders-plan-pending",
                    {"symbol": sym, "productType": PRODUCT, "planType": "profit_loss"}) or {}
    return [o for o in data.get("entrustedList") or [] if o.get("planType") == "pos_loss"]


def set_stop(sym: str, d: int, sl: float, info: dict, hedge: bool):
    """Pozisyonun zarar durdur/iz süren stop seviyesini borsada günceller."""
    price = fmt_price(info, sl)
    existing = _pos_loss_orders(sym)
    if existing:
        _request("POST", "/api/v2/mix/order/modify-tpsl-order",
                 body={"orderId": existing[0]["orderId"], "symbol": sym, "productType": PRODUCT, "marginCoin": COIN,
                       "triggerPrice": price, "triggerType": "mark_price", "size": ""})
    else:
        _request("POST", "/api/v2/mix/order/place-tpsl-order",
                 body={"symbol": sym, "productType": PRODUCT, "marginCoin": COIN, "planType": "pos_loss",
                       "triggerPrice": price, "triggerType": "mark_price", "holdSide": _hold(d, hedge)})


def close_position(sym: str, d: int, hedge: bool):
    body = {"symbol": sym, "productType": PRODUCT}
    if hedge:
        body["holdSide"] = _hold(d, True)
    _request("POST", "/api/v2/mix/order/close-positions", body=body)


def sync(state: dict, now: pd.Timestamp, margin: float, leverage: float, max_open: int, notify) -> None:
    """Botun (simülasyon) pozisyonlarını Bitget'e yansıtır: yeni işlemi açar, stopu günceller, kapananı kapatır."""
    ex = state.setdefault("exchange", {})
    sims = state["positions"]
    tag = f"[Bitget {mode_name()}]"
    info = contracts()
    live = positions()
    hedge = account().get("posMode") == "hedge_mode"

    # 1) bot kapattıysa borsada da kapat; borsada stop tetiklendiyse kaydı sil
    for sym in list(ex):
        e, p = ex[sym], sims.get(sym)
        if p is None or p["time"] != e["time"]:
            if sym in live:
                try:
                    close_position(sym, e["dir"], hedge)
                    notify(f"{tag} {sym} pozisyonu kapatıldı.")
                except BitgetError as err:
                    notify(f"⚠️ {tag} {sym} pozisyonu KAPATILAMADI: {err}. Lütfen Bitget'ten kontrol edin.")
                    continue
            ex.pop(sym)
        elif sym not in live:
            ex.pop(sym)
            p["ex_skip"] = "borsada kapandı"
            notify(f"{tag} {sym} pozisyonu Bitget'te kapanmış (stop tetiklendi).")

    # 2) yeni açılan işlemler
    for sym, p in sims.items():
        if sym in ex or p.get("ex_skip"):
            continue
        if now - pd.Timestamp(p["time"]) > OPEN_MAX_AGE:
            p["ex_skip"] = "eski sinyal"
            continue
        if sym in live:
            p["ex_skip"] = "borsada zaten pozisyon var"
            notify(f"⚠️ {tag} {sym}: Bitget'te zaten açık pozisyon var, yeni emir açılmadı.")
            continue
        if len(ex) >= max_open:
            p["ex_skip"] = "limit dolu"
            continue
        if sym not in info:
            p["ex_skip"] = "coin borsada yok"
            notify(f"⚠️ {tag} {sym} bu hesapta işlem görmüyor, emir açılmadı.")
            continue
        try:
            r = open_position(sym, p["dir"], p["sl"], margin, leverage, info[sym], p["entry"], hedge)
        except BitgetError as err:
            p["ex_skip"] = str(err)[:120]
            notify(f"⚠️ {tag} {sym} emri açılamadı: {err}")
            continue
        ex[sym] = {"time": p["time"], "dir": p["dir"], "sl": p["sl"], "size": r["size"], "oid": r["oid"]}
        notify(f"{tag} {sym} {'LONG' if p['dir'] == 1 else 'SHORT'} açıldı: {r['size']} adet, "
               f"{leverage:g}x izole, zarar durdur {fmt_price(info[sym], p['sl'])}")

    # 3) iz süren stop değiştiyse borsadaki stopu güncelle
    for sym, e in ex.items():
        p = sims[sym]
        if abs(p["sl"] - e["sl"]) <= 1e-12 or sym not in info:
            continue
        try:
            set_stop(sym, e["dir"], p["sl"], info[sym], hedge)
            e["sl"] = p["sl"]
        except BitgetError as err:
            print(f"{tag} {sym}: stop güncellenemedi ({err})")
            if not e.get("sl_warned"):
                e["sl_warned"] = True
                notify(f"⚠️ {tag} {sym} stopu güncellenemedi: {err}. Bot stopu her 5 dakikada kendisi kontrol edip "
                       f"gerekirse pozisyonu kapatacak.")


def self_test(order: bool = False) -> None:
    """Bağlantı testi: bakiye ve pozisyonları yazar. order=True ise (yalnızca demo) küçük bir BTC işlemi açıp kapatır."""
    missing = [k for k in KEYS if not os.getenv(k)]
    if missing:
        raise SystemExit(f"GitHub Secrets'ta eksik: {', '.join(missing)}")
    print(f"Bitget {mode_name()} bağlantı testi")
    acc = account()
    print(f"Pozisyon modu: {acc.get('posMode')}, kullanılabilir: {acc.get('available')} {COIN}, "
          f"toplam: {acc.get('accountEquity')} {COIN}")
    live = positions()
    print(f"Açık pozisyon: {len(live)} {sorted(live)}")
    if not order:
        return
    if not DEMO:
        raise SystemExit("Deneme emri yalnızca demo hesapta açılır.")
    info = contracts()["BTCUSDT"]
    hedge = acc.get("posMode") == "hedge_mode"
    price = float(_request("GET", "/api/v2/mix/market/ticker", {"symbol": "BTCUSDT", "productType": PRODUCT},
                           auth=False)[0]["lastPr"])
    r = open_position("BTCUSDT", 1, price * 0.98, 20, 10, info, price, hedge)
    print(f"Deneme LONG açıldı: {r}")
    time.sleep(2)
    set_stop("BTCUSDT", 1, price * 0.985, info, hedge)
    print(f"Stop güncellendi: {[o.get('triggerPrice') for o in _pos_loss_orders('BTCUSDT')]}")
    close_position("BTCUSDT", 1, hedge)
    time.sleep(2)
    print(f"Kapatıldı. Açık pozisyon: {sorted(positions())}")
