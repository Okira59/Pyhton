import bt, json
MAJ = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD"]
ALL = MAJ + ["EURJPY","GBPJPY","EURGBP","AUDJPY","EURCHF","USDTRY","USDZAR","USDMXN","XAUUSD"]
V = [("Mevcut H1 RSI40/60 SL1.5 TP3", {}),
     ("Mevcut, spread 0", dict(spread=0)),
     ("H1 SL1.5 TP1.5", dict(tp=1.5)),
     ("H1 SL2 TP2", dict(sl=2, tp=2)),
     ("H1 RSI30/70", dict(rb=30, rs=70)),
     ("H1 RSI50", dict(rb=50, rs=50)),
     ("H4 RSI40/60 SL1.5 TP3", dict(tf="4h")),
     ("H4 RSI30/70 SL1.5 TP3", dict(tf="4h", rb=30, rs=70)),
     ("H4 SL2 TP2", dict(tf="4h", sl=2, tp=2))]
for name, kw in V:
    bt.P.update(dict(tf="h", rb=40, rs=60, sl=1.5, tp=3.0, spread=1.0)); bt.P.update(kw)
    for setn, syms in [("MAJ", MAJ), ("ALL", ALL)]:
        r, _ = bt.run(syms, 0.1, lock=False)
        print(f"{name:32s} {setn}: işlem {r['trades']:4d} kazanç% {r['win']:5.1f} net {r['pnl']:9.2f} maxDD {r['maxdd']:8.2f}", flush=True)
