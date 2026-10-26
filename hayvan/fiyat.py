"""Edirne Ticaret Borsası canlı hayvan salon fiyatlarını çekip docs/hayvan/data/fiyat.json'a ekler."""
import json, os, time
import requests

URL = "https://online.etb.org.tr/api/v1/Alpha.WebPanel/OnlineKullaniciBulten/GetOnlineBultenSonIslemlerCH"
OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "hayvan", "data", "fiyat.json")
KODLAR = {"1102002": "Kuzu", "1102004": "Süt Kuzusu", "1102001": "Koyun", "1102006": "Toklu",
          "1102003": "Keçi", "1102005": "Oğlak", "1102007": "Marya"}


def main():
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    rows = [x for x in r.json() if x.get("UrunKodu") in KODLAR]
    try:
        d = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        d = {"gecmis": []}
    seen = {(h["kod"], h["tarih"]) for h in d["gecmis"]}
    son = {}
    for x in rows:
        rec = {"kod": x["UrunKodu"], "urun": KODLAR[x["UrunKodu"]], "tarih": x["Tarih"],
               "min": x["MinFiyat"], "max": x["MaxFiyat"], "ort": round(x["OrtFiyat"], 2),
               "hayvan": x["Adet"], "islem": x["IslemAdet"], "kg": x["IslemMiktari"]}
        son[rec["kod"]] = rec
        key = (rec["kod"], rec["tarih"])
        if key in seen:
            d["gecmis"] = [rec if (h["kod"], h["tarih"]) == key else h for h in d["gecmis"]]
        else:
            d["gecmis"].append(rec)
    d["gecmis"].sort(key=lambda h: (h["tarih"], h["kod"]))
    d["son"] = son
    d["guncelleme"] = int(time.time())
    with open(OUT, "w", encoding="utf-8") as f:
        f.write('{"guncelleme":%d,\n"son":%s,\n"gecmis":[\n%s\n]}\n' % (
            d["guncelleme"], json.dumps(son, ensure_ascii=False),
            ",\n".join(json.dumps(h, ensure_ascii=False) for h in d["gecmis"])))
    for k in ("1102002", "1102004"):
        s = son.get(k)
        print(KODLAR[k], s and f"{s['tarih']} ort {s['ort']} TL/kg ({s['min']}-{s['max']})")


if __name__ == "__main__":
    main()
