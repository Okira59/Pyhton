import pandas as pd, numpy as np, sys, json
SPREAD = {"XAUUSD":0.30,"USDJPY":0.015,"EURJPY":0.02,"GBPJPY":0.03,"AUDJPY":0.02,"EURGBP":0.00015,"EURCHF":0.0002,
          "USDTRY":0.03,"USDZAR":0.02,"USDMXN":0.01}
CONTRACT = {"XAUUSD":100}
P = dict(tf="h", rb=40, rs=60, sl=1.5, tp=3.0, spread=1.0)
def load(s):
    df = pd.read_csv(f"{s}.csv", parse_dates=["t"])
    df["t"] = df.t.dt.floor(P["tf"]); df = df.groupby("t").agg(o=("o","first"),h=("h","max"),l=("l","min"),c=("c","last")).iloc[:-1]
    df["ef"] = df.c.ewm(span=50, adjust=False).mean(); df["es"] = df.c.ewm(span=200, adjust=False).mean()
    d = df.c.diff(); up = d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    df["rsi"] = 100 - 100/(1+up/dn)
    tr = pd.concat([df.h-df.l, (df.h-df.c.shift()).abs(), (df.l-df.c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df = df.iloc[220:]
    df["sig"] = 0
    p = df.shift(1); pp = df.shift(2)   # bar 1 = previous closed, bar 2 = the one before
    df.loc[(p.ef > p.es) & (pp.rsi < P["rb"]) & (p.rsi >= P["rb"]), "sig"] = 1
    df.loc[(p.ef < p.es) & (pp.rsi > P["rs"]) & (p.rsi <= P["rs"]), "sig"] = -1
    df["atr1"] = p.atr
    return df

def run(symbols, lots, dmin=100, dmax=200, lock=True, start=None):
    data = {s: load(s) for s in symbols}
    if start is None: start = max(d.index[0] for d in data.values())
    for s in data: data[s] = data[s][data[s].index >= start]
    closes = pd.DataFrame({s: d.c for s, d in data.items()}).ffill()
    times = sorted(set().union(*[d.index for d in data.values()]))
    def conv(s, t):   # quote currency -> USD
        q = s[3:]
        if q == "USD": return 1.0
        if s.startswith("USD"): return 1.0 / closes.at[t, s]
        if q == "JPY": return 1.0 / closes.at[t, "USDJPY"]
        if q == "GBP": return closes.at[t, "GBPUSD"]
        if q == "CHF": return 1.0 / closes.at[t, "USDCHF"]
        raise ValueError(s)
    pos = None; trades = []; state = 0; day = None; closed_day = 0.0; daily = {}; lockdays = 0; maxopen = 0
    def close(t, price, why):
        nonlocal pos, closed_day
        units = lots * CONTRACT.get(pos["s"], 100000)
        pnl = units * (price - pos["e"]) * pos["d"] * conv(pos["s"], t)
        trades.append(dict(t=t, s=pos["s"], d=pos["d"], pnl=pnl, why=why)); closed_day += pnl; pos = None
    for t in times:
        dkey = (t + pd.Timedelta(hours=2)).date()     # broker server day (UTC+2)
        if dkey != day:
            if day is not None: daily[day] = daily.get(day, 0) + closed_day
            day = dkey; closed_day = 0.0
            if state == 1 and pos is None: state = 0   # backtest assumption: user presses BAŞLAT at next day start
        # entries at bar open
        for s, d in data.items():
            if t not in d.index: continue
            r = d.loc[t]
            if state == 0 and pos is None and r.sig != 0 and r.atr1 > 0:
                sp = P["spread"] * SPREAD.get(s, 0.00015 if "JPY" not in s else 0.015)
                e = r.o + sp if r.sig > 0 else r.o
                dist_sl, dist_tp = P["sl"] * r.atr1, P["tp"] * r.atr1
                pos = dict(s=s, d=int(r.sig), e=e, sl=e - r.sig*dist_sl, tp=e + r.sig*dist_tp, sp=sp)
        maxopen = max(maxopen, 1 if pos else 0)
        if pos is None or t not in data[pos["s"]].index: continue
        r = data[pos["s"]].loc[t]; s = pos["s"]; dr = pos["d"]; sp = pos["sp"]
        units = lots * CONTRACT.get(s, 100000); cv = conv(s, t)
        # exit price side: buy exits on bid (bar data), sell exits on ask (bar + spread)
        worst = r.l if dr > 0 else r.h + sp
        best  = r.h if dr > 0 else r.l + sp
        fl = lambda p: units * (p - pos["e"]) * dr * cv
        lvl = lambda X: pos["e"] + dr * (X - closed_day) / (units * cv)
        # adverse leg first (conservative)
        if (worst - pos["sl"]) * dr <= 0: close(t, pos["sl"], "SL"); continue
        if lock and state == 1 and closed_day + fl(worst) < dmin: close(t, lvl(dmin), "KILIT100"); continue
        # favorable leg
        if lock and state == 0 and closed_day + fl(best) >= dmin:
            state = 1; lockdays += 1
        if lock and state == 1 and closed_day + fl(best) >= dmax:
            p200 = lvl(dmax)
            if (pos["tp"] - p200) * dr < 0: close(t, pos["tp"], "TP")
            else: close(t, p200, "KILIT200")
            continue
        if (best - pos["tp"]) * dr >= 0:
            close(t, pos["tp"], "TP")
            if lock and state == 0 and closed_day >= dmin: state = 1; lockdays += 1
    daily[day] = daily.get(day, 0) + closed_day
    tr = pd.DataFrame(trades); dd = pd.Series(daily)
    eq = tr.pnl.cumsum() if len(tr) else pd.Series([0])
    return dict(start=str(start.date()), trades=len(tr), win=round((tr.pnl > 0).mean()*100, 1) if len(tr) else 0,
                pnl=round(tr.pnl.sum(), 2), maxdd=round((eq.cummax() - eq).max(), 2), lockdays=lockdays,
                bestday=round(dd.max(), 2), worstday=round(dd.min(), 2), maxopen=maxopen,
                why=tr.why.value_counts().to_dict() if len(tr) else {}), tr

if __name__ == "__main__":
    MAJ = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD"]
    ALL = MAJ + ["EURJPY","GBPJPY","EURGBP","AUDJPY","EURCHF","USDTRY","USDZAR","USDMXN","XAUUSD"]
    out = []
    for name, syms in [("7 majör (2024-02→2026-11)", MAJ), ("16 sembol + altın (2025-06→2026-11)", ALL)]:
        for lots in [0.01, 0.1, 0.5, 1.0]:
            for lock in [True, False]:
                res, tr = run(syms, lots, lock=lock)
                res.update(set=name, lots=lots, lock=lock); out.append(res); print(json.dumps(res, ensure_ascii=False, default=str))
    pd.DataFrame(out).to_csv("results.csv", index=False)
