"""Put every day's prices into one table: a row per price key (productId:printing), a column per day, in cents (0 = no
price that day). Writes prices.i32 (row-major int32), keys.json, days.json and meta.json (type and set of each product,
from the locally built site data).
usage: python3 tools/backtest/matrix.py <first day> <last day>"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
BT = _os.environ.get("BT_DIR") or _os.path.join(ROOT, "bt-work")            # working folder (not in git): days/, prices.i32, sig/
DATA = _os.environ.get("DATA_DIR") or _os.path.join(ROOT, "data")           # the data branch's data/ folder
import gzip, json, os, sys
from datetime import date, timedelta
import numpy as np

SNAP = os.path.join(DATA, "snapshots")
SITE = os.path.join(ROOT, "site", "data")                              # the locally built site data (python3 pipeline/run.py --rebuild)
a, b = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2])
days = [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]

def load(day):
    for p in (os.path.join(BT, "days", f"{day}.json.gz"), os.path.join(SNAP, f"{day}.json.gz")):
        if os.path.exists(p):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                return json.load(f)
    return None

keys, missing = {}, []
CAP = 240000                                  # rows set aside; the table is cut to the keys found
M = np.zeros((CAP, len(days)), dtype=np.int32)
for j, day in enumerate(days):
    snap = load(day)
    if snap is None:
        missing.append(day); continue
    idx = np.empty(len(snap), dtype=np.int64); val = np.empty(len(snap), dtype=np.int64)
    for n, (k, v) in enumerate(snap.items()):
        i = keys.get(k)
        if i is None:
            i = keys[k] = len(keys)
        idx[n] = i; val[n] = v
    assert len(keys) <= CAP, "more keys than rows set aside"
    M[idx, j] = np.clip(val, 0, 2**31 - 1)
    del snap
    if j % 100 == 0: print(j, day, len(keys), flush=True)
M = M[:len(keys)]
M.tofile(os.path.join(BT, "prices.i32"))
klist = [None] * len(keys)
for k, i in keys.items(): klist[i] = k
json.dump(klist, open(os.path.join(BT, "keys.json"), "w"))
json.dump(days, open(os.path.join(BT, "days.json"), "w"))
# product id -> type ("c" card, "s" sealed), set id, set release day, game: from the site data built from the Nov 14 prices
meta = {}
for fn in os.listdir(os.path.join(SITE, "set")):
    s = json.load(open(os.path.join(SITE, "set", fn)))
    for it in s["items"]:
        meta[str(it["id"])] = [it["t"], s["id"], s.get("pub") or "", s.get("k") or ""]
json.dump(meta, open(os.path.join(BT, "meta.json"), "w"))
print(f"days {len(days)} ({days[0]} to {days[-1]}), missing {len(missing)} {missing[:10]}; keys {len(keys)}; products with type {len(meta)}; table {M.nbytes / 1e6:.0f} MB; prices {int((M > 0).sum())}")
