import sys, os, itertools, pandas as pd
d = sys.argv[1]; tf = sys.argv[2]; split = pd.Timestamp(sys.argv[3], tz="UTC")
os.chdir(d); sys.path.insert(0, ".")
import bt
rows = []
for (rb, rs), sl, tp in itertools.product([(30,70),(35,65),(40,60),(50,50)], [1.0,1.5,2.0], [1.5,2.0,3.0,4.0]):
    bt.P.update(dict(tf=tf, rb=rb, rs=rs, sl=sl, tp=tp, spread=1.0))
    a, ta = bt.run(["XAUUSD"], 0.05, end=split)
    b, tb = bt.run(["XAUUSD"], 0.05, start=split)
    rows.append(dict(rsi=f"{rb}/{rs}", sl=sl, tp=tp, n1=a["trades"], win1=a["win"], pnl1=a["pnl"], dd1=a["maxdd"],
                     n2=b["trades"], win2=b["win"], pnl2=b["pnl"], dd2=b["maxdd"]))
df = pd.DataFrame(rows).sort_values("pnl1", ascending=False)
df.to_csv(f"grid_{tf}.csv", index=False); print(df.head(15).to_string()); print("pozitif her iki yarı:", ((df.pnl1>0)&(df.pnl2>0)).sum(), "/", len(df))
