"""Web paneli (docs/index.html) için botların durumunu JSON olarak yazar."""
import json
import os
from datetime import datetime, timezone

import pandas as pd

OUT_DIR = os.getenv("DASHBOARD_DIR", os.path.join("docs", "data"))
N_CANDLES = 200


def ts(t) -> int:
    return int(pd.Timestamp(t).timestamp())


def candles(df: pd.DataFrame, open_times) -> list:
    tail = df.tail(N_CANDLES)
    times = list(open_times)[-len(tail):]
    return [[ts(t), round(float(r.Open), 2), round(float(r.High), 2),
             round(float(r.Low), 2), round(float(r.Close), 2)]
            for t, r in zip(times, tail.itertuples())]


def events_to_list(events) -> list:
    return [{"t": ts(e[0]), "kind": e[1], **e[3]} for e in events]


def stats(history: list) -> dict:
    closed = [e["pct"] for e in history if e["kind"] == "KAPAT"]
    wins = sum(p >= 0 for p in closed)
    return {"closed": len(closed), "wins": wins, "losses": len(closed) - wins,
            "total_pct": round(sum(closed), 3)}


def write(name: str, payload: dict):
    os.makedirs(OUT_DIR, exist_ok=True)
    payload["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(os.path.join(OUT_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
