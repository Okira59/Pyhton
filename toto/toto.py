"""Spor Toto 15 maçlık haftalık program analizi ve kupon önerileri.

Veri:
- Program, halkın tercih yüzdeleri ve sonuçlar: iddaa Spor Toto servisi (sportotov2.iddaa.com)
- Oranlar: Bet365 + William Hill (Flashscore üzerinden) + iddaa (maça ~36 saat kala bültene girer)
- Sakat / cezalı / şüpheli oyuncular: Flashscore "Missing players"
- Stadyum şehri: Flashscore maç bilgisi -> hava tahmini: Open-Meteo
- Form: son 5 maç ve aralarındaki son maçlar (Flashscore H2H)
Model: üç sitenin marjı arındırılmış 1/X/2 olasılıklarının ortalaması, geçmiş Spor Toto haftalarında
(51 hafta, 734 maç) bulunan kalibrasyonla düzeltilir (favori biraz güçlendirilir, beraberlik biraz artırılır).
Sakatlık ve hava etkisi aynı testte tahmini iyileştirmedi (oranlar bunları zaten içeriyor), bu yüzden
modele eklenmez; her maçta uyarı olarak gösterilir.
Kuponlar: her kolon bütçesi için 15/15 tutma olasılığını en yükselten tek/çift/üçlü dağılımı (tam DP).
Çıktı: docs/toto/data/toto.json, docs/toto/data/gecmis.json
"""
import json
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "..", "gol"))
import fs_collect as F  # noqa: E402
from kupon import _sim  # noqa: E402

TR = timezone(timedelta(hours=3))
DOCS = os.path.join(BASE, "..", "docs", "toto", "data")
OUT = os.path.join(DOCS, "toto.json")
HIST = os.path.join(DOCS, "gecmis.json")
STATE = os.path.join(BASE, "data", "state.json")
GEO = os.path.join(BASE, "data", "geo.json")
TOTO = "https://sportotov2.iddaa.com"
SB = "https://sportsbookv2.iddaa.com/sportsbook"
LS = "https://2.ds.lsapp.eu/pq_graphql"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
BOOKS = {16: "bet365", 15: "williamhill"}
GEOS = [("GB", "GB34"), ("IE", "IEL"), ("CA", "CAON")]  # Türkiye ligi oranları GB'de kapalı
OUTC = ["1", "0", "2"]          # Spor Toto: 0 = beraberlik
COLUMN_PRICE = 10               # TL (iddaa varsayılanı)
MAX_COLUMN = 2500
BUDGETS = [1, 24, 96, 288, 576, 1152, 2304]
CAL = json.load(open(os.path.join(BASE, "calib.json")))  # {"a": güç, "d": beraberlik log kaydırması}

TRN = {"Münih": "Munich", "Türkiye": "Turkey", "Fransa": "France", "İtalya": "Italy", "Almanya": "Germany", "İspanya": "Spain",
       "İngiltere": "England", "Hollanda": "Netherlands", "Polonya": "Poland", "Varsova": "Warsaw", "Lizbon": "Lisbon",
       "Bulgaristan": "Bulgaria", "Avustralya": "Australia", "Kanada": "Canada", "Bosna Hersek": "Bosnia", "Brezilya": "Brazil",
       "Arjantin": "Argentina", "Portekiz": "Portugal", "Belçika": "Belgium", "Hırvatistan": "Croatia", "İsviçre": "Switzerland",
       "Japonya": "Japan", "Meksika": "Mexico", "Fas": "Morocco", "Kolombiya": "Colombia", "İskoçya": "Scotland", "Galler": "Wales",
       "Norveç": "Norway", "İsveç": "Sweden", "Danimarka": "Denmark", "Avusturya": "Austria", "Macaristan": "Hungary",
       "Romanya": "Romania", "Sırbistan": "Serbia", "Yunanistan": "Greece", "Çekya": "Czech", "Ukrayna": "Ukraine",
       "Gürcistan": "Georgia", "Slovakya": "Slovakia", "Slovenya": "Slovenia", "Güney Kore": "South Korea", "Mısır": "Egypt",
       "Gana": "Ghana", "Ekvador": "Ecuador", "Suudi Arabistan": "Saudi Arabia", "İran": "Iran", "Katar": "Qatar", "Tunus": "Tunisia",
       "Cezayir": "Algeria", "Fildişi": "Ivory Coast", "Yeni Zelanda": "New Zealand", "Ürdün": "Jordan", "Özbekistan": "Uzbekistan",
       "Kosta Rika": "Costa Rica", "Güney Afrika": "South Africa", "Kuzey İrlanda": "Northern Ireland", "İrlanda": "Ireland",
       "Arnavutluk": "Albania", "Kosova": "Kosovo", "Karadağ": "Montenegro", "Lüksemburg": "Luxembourg", "İzlanda": "Iceland",
       "Finlandiya": "Finland", "Kıbrıs": "Cyprus", "Litvanya": "Lithuania", "Letonya": "Latvia", "Estonya": "Estonia",
       "Rusya": "Russia", "Ermenistan": "Armenia", "Azerbaycan": "Azerbaijan", "Kazakistan": "Kazakhstan", "Cebelitarık": "Gibraltar",
       "ABD": "USA", "Kuzey Makedonya": "North Macedonia", "Yeşil Burun": "Cape Verde", "Kongo": "Congo"}
WMO = {0: "Açık", 1: "Az bulutlu", 2: "Parçalı bulutlu", 3: "Kapalı", 45: "Sis", 48: "Sis", 51: "Çisenti", 53: "Çisenti", 55: "Çisenti",
       61: "Hafif yağmur", 63: "Yağmur", 65: "Şiddetli yağmur", 66: "Dondurucu yağmur", 67: "Dondurucu yağmur", 71: "Hafif kar",
       73: "Kar", 75: "Yoğun kar", 77: "Kar", 80: "Sağanak", 81: "Sağanak", 82: "Şiddetli sağanak", 85: "Kar sağanağı",
       86: "Kar sağanağı", 95: "Gök gürültülü fırtına", 96: "Dolu", 99: "Dolu"}

S = requests.Session()


def jget(url, params=None, tries=3, headers=None):
    for i in range(tries):
        try:
            r = S.get(url, params=params, headers=headers or UA, timeout=25)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.5 * (i + 1))
    return None


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def tr2en(s):
    for a, b in sorted(TRN.items(), key=lambda x: -len(x[0])):
        s = s.replace(a, b)
    return s


def split_name(n):
    for sep in (" - ", "-"):
        if sep in n:
            h, a = n.split(sep, 1)
            return h.strip(), a.strip()
    return n, ""


def ts_of(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=TR).timestamp())


# ---------------------------------------------------------------- model
def fair3(o):
    """o: [1, X, 2] oranları -> marjsız olasılıklar."""
    if not o or any(not x or x <= 1 for x in o):
        return None
    inv = [1 / x for x in o]
    s = sum(inv)
    return [x / s for x in inv]


def calibrate(p, a=None, d=None):
    a = CAL["a"] if a is None else a
    d = CAL["d"] if d is None else d
    z = [a * math.log(max(x, 1e-6)) for x in p]
    z[1] += d
    m = max(z)
    e = [math.exp(x - m) for x in z]
    s = sum(e)
    return [x / s for x in e]


def consensus(srcs):
    ps = [fair3(v) for v in srcs.values()]
    ps = [p for p in ps if p]
    if not ps:
        return None
    return [sum(p[i] for p in ps) / len(ps) for i in range(3)]


def optimize(P, n_cols):
    """P: her maç için [p1, p0, p2]. Kolon sayısı <= n_cols olacak şekilde 15/15 olasılığını en yükselten seçimler.
    Dönüş: (seçimler [[indeksler]], kolon sayısı, olasılık)."""
    maxd = int(math.log2(n_cols)) if n_cols >= 2 else 0
    maxt = int(math.log(n_cols, 3) + 1e-9) if n_cols >= 3 else 0
    opts = []
    for p in P:
        order = sorted(range(3), key=lambda i: -p[i])
        opts.append([(0, 0, [order[0]], p[order[0]]), (1, 0, order[:2], p[order[0]] + p[order[1]]), (0, 1, order, 1.0)])
    dp = {(0, 0): (0.0, [])}
    for o in opts:
        nd = {}
        for (d, t), (v, sel) in dp.items():
            for dd, dt, s, q in o:
                k = (d + dd, t + dt)
                if k[0] > maxd or k[1] > maxt or 2 ** k[0] * 3 ** k[1] > n_cols:
                    continue
                val = v + math.log(max(q, 1e-12))
                if k not in nd or val > nd[k][0]:
                    nd[k] = (val, sel + [s])
        dp = nd
    (d, t), (v, sel) = max(dp.items(), key=lambda kv: kv[1][0])
    return sel, 2 ** d * 3 ** t, math.exp(v)


def hit_dist(P, sel):
    """Doğru tahmin sayısı dağılımı (Poisson-binom)."""
    dist = [1.0]
    for p, s in zip(P, sel):
        q = sum(p[i] for i in s)
        nd = [0.0] * (len(dist) + 1)
        for k, x in enumerate(dist):
            nd[k] += x * (1 - q)
            nd[k + 1] += x * q
        dist = nd
    return dist


def coupons(P):
    out = []
    n = len(P)
    for b in BUDGETS:
        sel, cols, p15 = optimize(P, b)
        dist = hit_dist(P, sel)
        out.append({"butce": b, "kolon": cols, "tutar": cols * COLUMN_PRICE, "sec": ["".join(OUTC[i] for i in sorted(s, key=lambda i: OUTC[i])) for s in sel],
                    "p15": p15, "p14": sum(dist[n - 1:]), "p13": sum(dist[n - 2:]), "p12": sum(dist[n - 3:]),
                    "beklenen": sum(k * x for k, x in enumerate(dist))})
    return out


# ---------------------------------------------------------------- veri
def fs_day(day):
    r = F.get(f"{F.FEED}f_1_{day}_3_en_1", F.FEED_HDR)
    out = []
    if not r:
        return out
    for rec in r.text.split("¬~"):
        f = {}
        for kv in rec.split("¬"):
            if "÷" in kv:
                k, v = kv.split("÷", 1)
                f.setdefault(k, v)
        if "AA" in f and f.get("AD"):
            out.append({"id": f["AA"], "ts": int(f["AD"]), "h": f.get("AE", ""), "a": f.get("AF", ""), "ja": f.get("JA"), "jb": f.get("JB")})
    return out


def match_fs(ev, fs):
    by = {}
    for x in fs:
        by.setdefault(x["ts"] // 900, []).append(x)
    for e in ev:
        h, a = map(tr2en, split_name(e["eventName"]))
        best, bs = None, 0
        for s in range(e["ts"] // 900 - 2, e["ts"] // 900 + 3):
            for x in by.get(s, []):
                sc = _sim(h, x["h"]) + _sim(a, x["a"])
                if sc > bs:
                    best, bs = x, sc
        if best and bs >= 1.0:
            e["fs"] = best


def iddaa_odds(ev):
    lst = []
    for t in (0, 1):
        d = jget(f"{SB}/events", {"st": 1, "type": t, "version": 0})
        lst += (d or {}).get("data", {}).get("events", [])
    cand = [{"i": x.get("i"), "h": x.get("hn", ""), "a": x.get("an", ""), "ts": x.get("d", 0), "m": x.get("m", [])} for x in lst]
    for e in ev:
        h, a = split_name(e["eventName"])
        best, bs = None, 0
        for x in cand:
            if abs(x["ts"] - e["ts"]) > 1800:
                continue
            sc = _sim(h, x["h"]) + _sim(a, x["a"])
            if sc > bs:
                best, bs = x, sc
        if best and bs >= 1.0:
            ms = best["m"]
            if not any(m.get("t") == 1 and m.get("st") == 1 for m in ms):
                ms = ((jget(f"{SB}/event/{best['i']}") or {}).get("data") or {}).get("m") or []
            for m in ms:
                if m.get("t") == 1 and m.get("st") == 1:
                    o = {x["n"]: x["odd"] for x in m.get("o", [])}
                    if all(k in o for k in "102"):
                        e["iddaa"] = [o["1"], o["0"], o["2"]]


def fs_odds(m):
    """Bet365 ve William Hill 1X2 (kapanış/güncel + açılış) ve birleşik tüm marketler (skor modeli için)."""
    books, first = {}, None
    for geo, sub in GEOS:
        js = jget(F.ODDS_URL, {"_hash": "oce", "eventId": m["id"], "projectId": 2, "geoIpCode": geo, "geoIpSubdivisionCode": sub})
        first = first or js
        _books(js, m, books)
        if len(books) == len(BOOKS):
            break
    if not books and first:
        o = _others(first, m)
        if o:
            books["diger"] = o
    return books, F.parse_odds(first, m.get("ja"), m.get("jb")) if first else {}


def _others(js, m):
    """Bet365/William Hill yoksa Flashscore'daki diğer sitelerin 1X2 ortalaması (yedek)."""
    rows = []
    try:
        for b in js["data"]["findOddsByEventId"]["odds"]:
            if b.get("bettingType") != "HOME_DRAW_AWAY" or b.get("bettingScope") != "FULL_TIME":
                continue
            o = {}
            for it in b["odds"]:
                pid = it.get("eventParticipantId")
                side = "1" if pid == m.get("ja") else "2" if pid == m.get("jb") else "0" if pid is None else None
                if side:
                    o[side] = F.fnum(it.get("value"))
            if all(o.get(k) for k in OUTC):
                rows.append([o[k] for k in OUTC])
    except (KeyError, TypeError):
        return None
    if not rows:
        return None
    return {"o": [round(sum(r[i] for r in rows) / len(rows), 2) for i in range(3)], "n": len(rows)}


def _books(js, m, books):
    try:
        for b in js["data"]["findOddsByEventId"]["odds"]:
            name = BOOKS.get(b.get("bookmakerId"))
            if not name or name in books or b.get("bettingType") != "HOME_DRAW_AWAY" or b.get("bettingScope") != "FULL_TIME":
                continue
            cur, op = {}, {}
            for it in b["odds"]:
                pid = it.get("eventParticipantId")
                side = "1" if pid == m.get("ja") else "2" if pid == m.get("jb") else "0" if pid is None else None
                if side:
                    cur[side], op[side] = F.fnum(it.get("value")), F.fnum(it.get("opening"))
            if all(cur.get(k) for k in OUTC):
                books[name] = {"o": [cur[k] for k in OUTC], "open": [op.get(k) for k in OUTC]}
    except (KeyError, TypeError):
        pass


def missing(m):
    js = jget(LS, {"_hash": "dmpe2", "eventId": m["id"], "projectId": 2})
    out = {}
    try:
        for p in js["data"]["findEventById"]["eventParticipants"]:
            side = "h" if p["type"]["side"] == "HOME" else "a"
            lu = p["lineup"] or {}
            imp = {x["id"]: x["importance"] for x in ((lu.get("playerImportance") or {}).get("importances") or [])}
            out[side] = [{"id": x["player"].get("participantId"), "n": x["player"]["name"], "r": x["reason"]} for x in lu.get("missingPlayers") or []] + \
                        [{"id": x["player"].get("participantId"), "n": x["player"]["name"], "r": x["reason"], "s": 1} for x in lu.get("unsureMissingPlayers") or []]
            seen = set()
            out[side] = [x for x in out[side] if not (x["id"] in seen or seen.add(x["id"]))]
            for x in out[side]:
                if x["id"] in imp:
                    x["onem"] = imp[x["id"]]
    except (KeyError, TypeError):
        return None
    return out


def info(m):
    r = F.get(F.FEED + f"df_sui_1_{m['id']}", F.FEED_HDR)
    out = {}
    if r:
        f = r.text.split("¬")
        for i, kv in enumerate(f[:-1]):
            if kv in ("MIT÷VEN", "MIT÷TWN") and f[i + 1].startswith("MIV÷"):
                out["stad" if kv.endswith("VEN") else "sehir"] = f[i + 1][4:]
    return out


def form(m):
    r = F.get(F.FEED + f"df_hh_1_{m['id']}", F.FEED_HDR)
    if not r:
        return None
    out, sec, n = {"h": [], "a": [], "h2h": []}, None, 0
    for rec in r.text.split("¬~"):
        f = {}
        for kv in rec.split("¬"):
            if "÷" in kv:
                k, v = kv.split("÷", 1)
                f.setdefault(k, v)
        if "KA" in f:
            n += 1
            if n > 1:
                break
            continue
        if "KB" in f:
            t = f["KB"]
            sec = "h2h" if t.startswith("Head") else ("h" if not out["h"] and sec is None else "a")
            continue
        if "KC" in f and sec and len(out[sec]) < 5:
            out[sec].append({"t": int(f["KC"]), "ev": f.get("KJ", "").lstrip("*"), "dep": f.get("KK", "").lstrip("*"), "s": f.get("KL", ""), "r": f.get("WIS", "")})
    return out


def geocode(city, cache):
    if city in cache:
        return cache[city]
    j = jget("https://geocoding-api.open-meteo.com/v1/search", {"name": re.split(r"[,(]", city)[0].strip(), "count": 1})
    x = ((j or {}).get("results") or [None])[0]
    cache[city] = [x["latitude"], x["longitude"]] if x else None
    return cache[city]


def weather(ll, ts):
    if not ll or ts - time.time() > 15 * 86400:
        return None
    j = jget("https://api.open-meteo.com/v1/forecast", {"latitude": ll[0], "longitude": ll[1], "timezone": "UTC", "forecast_days": 16,
                                                        "hourly": "temperature_2m,precipitation,precipitation_probability,wind_speed_10m,weather_code"})
    try:
        h = j["hourly"]
        key = time.strftime("%Y-%m-%dT%H:00", time.gmtime(ts + 1800))
        i = h["time"].index(key)
        return {"t": h["temperature_2m"][i], "yagis": h["precipitation"][i], "yagis_ol": h["precipitation_probability"][i],
                "ruzgar": h["wind_speed_10m"][i], "durum": WMO.get(h["weather_code"][i], "")}
    except (KeyError, TypeError, ValueError):
        return None


def score_top(odds):
    try:
        import skor
        r = skor.predict(odds)
        return skor.top(r[0]["ft"], 5) if r else None
    except Exception:
        return None


def notes(e):
    out = []
    mp = e.get("eksik") or {}
    for side, nm in (("h", "Ev sahibi"), ("a", "Deplasman")):
        lst = mp.get(side) or []
        kesin = [x for x in lst if not x.get("s")]
        ceza = [x for x in kesin if re.search(r"card|suspen|red", x["r"], re.I)]
        kilit = [x["n"] for x in kesin if x.get("seviye") == "Kilit oyuncu"]
        if kilit:
            out.append(f"{nm}: {len(kilit)} kilit oyuncu yok ({', '.join(kilit[:4])})")
        elif len(kesin) >= 4:
            out.append(f"{nm}: {len(kesin)} eksik oyuncu")
        if ceza:
            out.append(f"{nm}: {len(ceza)} cezalı")
    w = e.get("hava")
    if w:
        if (w.get("yagis") or 0) >= 1 or (w.get("yagis_ol") or 0) >= 70:
            out.append(f"Yağış bekleniyor ({w['durum']})")
        if (w.get("ruzgar") or 0) >= 30:
            out.append(f"Kuvvetli rüzgar ({w['ruzgar']:.0f} km/s)")
        if w.get("t") is not None and (w["t"] <= 2 or w["t"] >= 30):
            out.append(f"Aşırı sıcaklık ({w['t']:.0f}°C)")
    b = (e.get("oran") or {}).get("bet365")
    if b and all(b.get("open") or [None]):
        p0, p1 = fair3(b["open"]), fair3(b["o"])
        if p0 and p1:
            for i, nm in enumerate(["1", "0", "2"]):
                if p1[i] - p0[i] >= 0.06:
                    out.append(f"Oran hareketi: {nm} lehine (%{p0[i]*100:.0f} → %{p1[i]*100:.0f})")
    if not e.get("oran"):
        out.append("Oran bulunamadı: olasılık halkın tercihinden (güvenilirliği düşük)")
    elif list(e["oran"]) == ["diger"]:
        out.append(f"Bet365/William Hill/iddaa oranı henüz yok: diğer {e['oran']['diger']['n']} sitenin ortalaması")
    return out


def analyse(prog):
    ev = [dict(x, ts=ts_of(x["eventDate"])) for x in prog["events"]]
    now = time.time()
    days = sorted({max(0, min(7, int((datetime.fromtimestamp(e["ts"], TR).date() - datetime.fromtimestamp(now, TR).date()).days))) for e in ev})
    fs = []
    for d in sorted(set(days) | {max(0, d - 1) for d in days} | {min(7, d + 1) for d in days}):
        fs += fs_day(d)
    match_fs(ev, fs)
    iddaa_odds(ev)
    geo = load(GEO, {})
    hasfs = [e for e in ev if "fs" in e]
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda e: (fs_odds(e["fs"]), missing(e["fs"]), info(e["fs"]), form(e["fs"])), hasfs))
    for e, ((books, allodds), mp, inf, fm) in zip(hasfs, res):
        e["oran"] = books
        e["eksik"], e["bilgi"], e["form"] = mp, inf, fm
        e["skor"] = score_top(allodds) if allodds else None
        if inf.get("sehir"):
            e["hava"] = weather(geocode(inf["sehir"], geo), e["ts"])
    save(GEO, geo)
    squad_stats(hasfs)
    previews(ev)
    rows = []
    for e in ev:
        srcs = {k: v["o"] for k, v in (e.get("oran") or {}).items()}
        if e.get("iddaa"):
            srcs["iddaa"] = e["iddaa"]
            e.setdefault("oran", {})["iddaa"] = {"o": e["iddaa"]}
        base = consensus(srcs)
        halk = [e.get("homePercentage"), e.get("drawPercentage"), e.get("awayPercentage")]
        if base:
            p = calibrate(base)
        elif all(x is not None for x in halk) and sum(halk):
            p = [x / sum(halk) for x in halk]
        else:
            p = [0.42, 0.27, 0.31]
        h, a = split_name(e["eventName"])
        r = {"no": e["eventNo"], "ev": h, "dep": a, "lig": e["competitionName"], "ts": e["ts"], "p": [round(x, 4) for x in p],
             "piyasa": [round(x, 4) for x in base] if base else None, "halk": halk, "oran": e.get("oran") or {},
             "eksik": e.get("eksik"), "bilgi": e.get("bilgi"), "hava": e.get("hava"), "form": e.get("form"), "skor": e.get("skor"),
             "fs": (e.get("fs") or {}).get("id"), "yorum": e.get("yorum"), "sonuc": e.get("result"), "kazanan": e.get("winner")}
        r["notlar"] = notes(r)
        rows.append(r)
    return rows


# ---------------------------------------------------------------- kadro istatistikleri
KADRO = os.path.join(BASE, "data", "kadro.json")
YORUM = os.path.join(BASE, "data", "yorum.json")


def recs(text):
    for rec in text.split("¬~"):
        f = {}
        for kv in rec.split("¬"):
            if "÷" in kv:
                k, v = kv.split("÷", 1)
                f.setdefault(k, v)
        yield f


def team_matches(m, ts):
    """Her iki takımın bu sezon oynadığı resmi maçlar: {"h": [(eventId, "1"/"2")], "a": [...]}."""
    r = F.get(F.FEED + f"df_hh_1_{m['id']}", F.FEED_HDR)
    out = {"h": [], "a": []}
    if not r:
        return out
    d = datetime.fromtimestamp(ts, TR)
    start = datetime(d.year if d.month >= 7 else d.year - 1, 7, 1, tzinfo=TR).timestamp()
    tab = sec = None
    nlast = 0
    for f in recs(r.text):
        if "KA" in f:
            tab = f["KA"]
        if "KB" in f:
            sec = None
            if tab == "Overall" and f["KB"].startswith("Last matches"):
                sec = "ha"[nlast] if nlast < 2 else None
                nlast += 1
        if "KC" in f and sec and f.get("KP") and f["KP"] != m["id"]:
            t = int(f["KC"])
            if start <= t < ts - 3600 and "Friendly" not in f.get("KF", "") and len(out[sec]) < 30:
                out[sec].append((f["KP"], "1" if f.get("KS") == "home" else "2"))
    return out


def lineup(eid):
    """Maçta oynayan oyuncular: {"1": [[id, ilk11 mi, puan]], "2": [...]}."""
    r = F.get(F.FEED + f"df_li_1_{eid}", F.FEED_HDR)
    if not r or "LP÷" not in r.text:
        return None
    out = {"1": [], "2": []}
    grp = side = None
    for f in recs(r.text):
        if "LB" in f:
            grp = f["LB"]
        if "LC" in f:
            side = f["LC"]
        if "LP" in f and side in out and grp in ("Starting Lineups", "Substitutes"):
            st = grp == "Starting Lineups"
            rt = F.fnum(f.get("LPR"))
            if st or rt:
                out[side].append([f["LP"], 1 if st else 0, rt])
    return out if out["1"] or out["2"] else None


def squad_stats(ev):
    """Eksik oyuncular için: takımın bu sezonki maçlarında kaç maç oynadı, kaçında ilk 11, ortalama puan."""
    cache = load(KADRO, {})
    tm = {}
    with ThreadPoolExecutor(6) as ex:
        for e, t in zip(ev, ex.map(lambda e: team_matches(e["fs"], e["ts"]), ev)):
            tm[e["eventNo"]] = t
    need = {eid for t in tm.values() for lst in t.values() for eid, _ in lst if eid not in cache}
    with ThreadPoolExecutor(8) as ex:
        for eid, lu in zip(need, ex.map(lineup, need)):
            cache[eid] = lu
    used = {eid for t in tm.values() for lst in t.values() for eid, _ in lst}
    save(KADRO, {k: v for k, v in cache.items() if k in used})
    for e in ev:
        mp = e.get("eksik") or {}
        for side in ("h", "a"):
            games = [(cache.get(eid) or {}).get(sd) for eid, sd in tm[e["eventNo"]][side]]
            games = [g for g in games if g]
            if not games or not mp.get(side):
                continue
            for p in mp[side]:
                rows = [x for g in games for x in g if x[0] == p.get("id")]
                rts = [x[2] for x in rows if x[2]]
                p.update({"mac": len(games), "oyn": len(rows), "ilk11": sum(x[1] for x in rows),
                          "puan": round(sum(rts) / len(rts), 2) if rts else None})
                rate = p["ilk11"] / len(games)
                p["seviye"] = "Bu sezon oynamadı" if not p["oyn"] else "Kilit oyuncu" if rate >= 0.7 else "Önemli" if rate >= 0.4 else "Rotasyon" if p["oyn"] / len(games) >= 0.25 else "Az oynuyor"
            mp[side].sort(key=lambda p: (-p.get("ilk11", 0), -p.get("oyn", 0)))


# ---------------------------------------------------------------- yorumcular (Sports Mole) + Türkçe çeviri
SM = "https://www.sportsmole.co.uk"


def _gtx(text):
    r = S.post("https://translate.google.com/translate_a/single", params={"client": "gtx", "sl": "en", "tl": "tr", "dt": "t"},
               data={"q": text}, headers=UA, timeout=25)
    return "".join(x[0] for x in r.json()[0] if x[0])


def _chrome(text):
    r = S.post("https://clients5.google.com/translate_a/t", params={"client": "dict-chrome-ex", "sl": "en", "tl": "tr"},
               data={"q": text}, headers=UA, timeout=25)
    x = r.json()[0]
    return x if isinstance(x, str) else x[0]


def translate(text):
    """İngilizce -> Türkçe (Google; olmazsa yedek uç). Başarısızsa None."""
    for fn in (_gtx, _chrome):
        for i in range(2):
            try:
                out = fn(text)
                if out:
                    return out
            except (requests.RequestException, ValueError, TypeError, IndexError, KeyError):
                pass
            time.sleep(2 + 3 * i)
    return None


def sm_article(url):
    import html as H
    try:
        t = S.get(url, headers=UA, timeout=25).text
    except requests.RequestException:
        return None
    yazar = re.search(r'"author"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', t)
    tarih = re.search(r'datePublished"\s*:\s*"([^"]+)', t)
    secs, cur = {}, None
    for tag, body in re.findall(r"<(h2|p)[^>]*>(.*?)</\1>", t, re.S):
        txt = H.unescape(re.sub(r"<[^>]+>", "", body)).replace("\xa0", " ").strip()
        if tag == "h2":
            cur = "onizleme" if txt.startswith("Match preview") else "kadro" if txt.startswith("Team News") else \
                  "tahmin" if txt.startswith("We say") else None
            if cur == "tahmin":
                secs["skor"] = txt.replace("We say:", "").strip()
            continue
        if cur and len(txt) > 30:
            secs.setdefault(cur, []).append(txt)
    if not secs.get("onizleme"):
        return None
    kadro = [p for p in secs.get("kadro", []) if not re.fullmatch(r"[^.]*;[^.]*", p)]  # tahmini 11'ler hariç
    return {"kaynak": "Sports Mole", "url": url, "yazar": yazar.group(1) if yazar else None, "tarih": tarih.group(1) if tarih else None,
            "skor": secs.get("skor"), "en": {"onizleme": secs["onizleme"][:4], "kadro": kadro[:4], "tahmin": secs.get("tahmin", [])[:2]}}


def previews(ev):
    cache = load(YORUM, {})
    try:
        t = S.get(f"{SM}/football/preview/", headers=UA, timeout=25).text
        links = sorted(set(re.findall(r'href="(/football/[^"]+/preview/([a-z0-9-]+)-vs-([a-z0-9-]+)-prediction[^"]*\.html)"', t)))
    except requests.RequestException:
        links = []
    for e in ev:
        h, a = map(tr2en, split_name(e["eventName"]))
        best, bs = None, 0
        for url, x, y in links:
            sc = _sim(h, x.replace("-", " ")) + _sim(a, y.replace("-", " "))
            if sc > bs:
                best, bs = url, sc
        key = str(e["eventNo"]) + "|" + e["eventName"]
        if best and bs >= 1.2 and (cache.get(key) or {}).get("url") != SM + best:
            art = sm_article(SM + best)
            if art:
                tr = {}
                for k, ps in art["en"].items():
                    x = translate("\n".join(ps)) if ps else ""
                    if x is None:
                        tr = None
                        break
                    tr[k] = [p for p in x.split("\n") if p.strip()]
                if tr is not None:
                    skor = translate(art["skor"]) if art["skor"] else None
                    cache[key] = {k: v for k, v in art.items() if k != "en"} | {"tr": tr, "skor_tr": skor}
        if key in cache:
            e["yorum"] = [cache[key]]
    names = {str(e["eventNo"]) + "|" + e["eventName"] for e in ev}
    save(YORUM, {k: v for k, v in cache.items() if k in names})


# ---------------------------------------------------------------- sonuçlar / geçmiş
def count_hits(sec, rows):
    n = done = 0
    for s, r in zip(sec, rows):
        if r.get("kazanan") in OUTC:
            done += 1
            n += r["kazanan"] in s
    return n, done


def apply_results(cur, res):
    by = {e["eventNo"]: e for e in res.get("events", [])}
    for r in cur["maclar"]:
        x = by.get(r["no"])
        if x and x.get("winner") in OUTC:
            r["sonuc"], r["kazanan"] = x.get("result"), x["winner"]
    for k in cur["kuponlar"]:
        k["dogru"], k["biten"] = count_hits(k["sec"], cur["maclar"])
    cur["ikramiye"] = res.get("dividends")


def main():
    now = time.time()
    state = load(STATE, {})
    hist = load(HIST, {"haftalar": []})
    cur = load(OUT, None)
    prog = (jget(f"{TOTO}/SporToto") or {}).get("data")
    if not prog:
        print("Spor Toto programı alınamadı")
        return
    cyc = prog["gameCycleNo"]
    # yeni hafta çıktıysa eski haftayı geçmişe taşı; sonuçları bekleyen haftaları güncelle
    if cur and cur["hafta"] != cyc:
        hist["haftalar"] = [h for h in hist["haftalar"] if h["hafta"] != cur["hafta"]] + [cur]
        cur = None
    for h in hist["haftalar"][-4:]:
        if not all(r.get("kazanan") in OUTC for r in h["maclar"]) and now - ts_of(h["bitis"]) < 10 * 86400:
            res = (jget(f"{TOTO}/SporToto/result", {"gameCycleNo": h["hafta"]}) or {}).get("data")
            if res:
                apply_results(h, res)
    hist["haftalar"] = hist["haftalar"][-52:]
    save(HIST, hist)
    deadline = ts_of(prog["payinEndDate"])
    locked = now > deadline
    if cur and cur["hafta"] == cyc and locked:
        res = (jget(f"{TOTO}/SporToto/result", {"gameCycleNo": cyc}) or {}).get("data")
        if res:
            apply_results(cur, res)
        cur["kilit"] = True
        cur["guncelleme"] = int(now)
        if all(r.get("kazanan") in OUTC for r in cur["maclar"]):
            hist["haftalar"] = [h for h in hist["haftalar"] if h["hafta"] != cyc] + [cur]
            save(HIST, hist)
        save(OUT, cur)
        save(STATE, state)
        print("Kupon kilitli (son oynama geçti); sonuçlar güncellendi")
        return
    rows = analyse(prog)
    cur = {"hafta": cyc, "ad": prog.get("programName"), "baslangic": prog["payinBeginDate"], "bitis": prog["payinEndDate"],
           "guncelleme": int(now), "kilit": False, "kolon_fiyat": COLUMN_PRICE, "kalibrasyon": CAL,
           "maclar": rows, "kuponlar": coupons([r["p"] for r in rows])}
    for k in cur["kuponlar"]:
        k["dogru"], k["biten"] = count_hits(k["sec"], rows)
    save(OUT, cur)
    save(STATE, state)
    ok = sum(1 for r in rows if r["piyasa"])
    print(f"{cyc}. hafta: {len(rows)} maç, {ok} maçta oran, {sum(1 for r in rows if r['fs'])} Flashscore eşleşmesi")
    for k in cur["kuponlar"]:
        print(f"  {k['kolon']:>5} kolon: {' '.join(k['sec'])}  P15=%{k['p15']*100:.4f} P12+=%{k['p12']*100:.1f}")


if __name__ == "__main__":
    main()
