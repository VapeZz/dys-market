"""Independent pure-Python recheck of two headline cells of quickflip.py (no numpy, own arithmetic)."""
import gzip, json, sys
from datetime import date, timedelta
from collections import defaultdict
DAYS, META = sys.argv[1:3]
meta = json.load(open(META))["meta"]
load = lambda d: json.load(gzip.open(f"{DAYS}/{d.isoformat()}.json.gz", "rt"))
def r(x): return int(x + 0.5) if x >= 0 else -int(-x + 0.5)
def ebay(p):
    b = round(p * 1.075); fee = round(40 + min(b, 750000) * 0.1325 + max(b - 750000, 0) * 0.0235)
    return p - fee - (500 if p >= 5000 else 100) - 50
CELLS = [("local90 $50-100 30d 70%", 5000, 10000, 70, lambda m: round(m * 0.90)),
         ("ebay $100+ 30d 60%", 10000, 10**12, 60, lambda m: ebay(round(m * 0.89)))]
for name, lo, hi, pct, net in CELLS:
    per = defaultdict(list); profits = []; rois = []
    d = date(2025, 1, 1)
    while d.year == 2025:
        s0, s1 = load(d), load(d + timedelta(days=30))
        for k, m0 in s0.items():
            if not (lo <= m0 < hi): continue
            mt = meta.get(k.split(":")[0])
            if not mt or mt[0] != "c": continue
            m1 = s1.get(k, 0)
            if m1 <= 0: continue
            cost = round(m0 * pct / 100); pr = net(m1) - cost; roi = pr / cost * 100
            per[k].append(pr >= 500 and roi >= 20); profits.append(pr); rois.append(roi)
        d += timedelta(days=7)
    hit = sum(sum(v) / len(v) for v in per.values()) / len(per) * 100
    profits.sort(); rois.sort(); n = len(profits)
    med = (profits[n // 2] + profits[(n - 1) // 2]) / 2
    print(f"{name} 2025: cases {n} cards {len(per)} hit {hit:.1f} median ${med/100:.2f} p10~{rois[int(0.1*(n-1))]:.1f}")
