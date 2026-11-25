import json, time, urllib.request, pandas as pd
UA={"User-Agent":"Mozilla/5.0"}
def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
yh = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD","EURJPY","GBPJPY","EURGBP","AUDJPY","EURCHF","USDTRY","USDZAR","USDMXN"]
for s in yh:
    d = get(f"https://query2.finance.yahoo.com/v8/finance/chart/{s}=X?interval=1h&range=730d")["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    df = pd.DataFrame({"t": pd.to_datetime(d["timestamp"], unit="s", utc=True), "o": q["open"], "h": q["high"], "l": q["low"], "c": q["close"]}).dropna()
    df.to_csv(f"{s}.csv", index=False); print(s, len(df), df.t.iloc[0], df.t.iloc[-1]); time.sleep(1)
# gold from Bitget TradFi (MT5 CFD feed)
rows=[]; end=int(time.time()*1000)
for _ in range(20):
    d = get(f"https://www.bitget.com/v1/kline/getMoreKlineDataV2?symbolId=XAUUSD&kLineStep=1h&kLineType=5&endTime={end}")
    data = d.get("data") or []
    if isinstance(data, dict): data = data.get("dataList") or data.get("list") or []
    if not data: break
    rows += data; first = min(int(r[0]) for r in data)
    if first >= end: break
    end = first - 1
    time.sleep(0.3)
df = pd.DataFrame([r[:5] for r in rows], columns=["t","o","h","l","c"]).astype(float).drop_duplicates("t").sort_values("t")
df["t"] = pd.to_datetime(df.t.astype("int64"), unit="ms", utc=True)
df.to_csv("XAUUSD.csv", index=False); print("XAUUSD", len(df), df.t.iloc[0], df.t.iloc[-1])
