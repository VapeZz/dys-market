"""M3 Step 2 independent recheck. Does not import the app's scout code or scout_replay; reads the daily files directly.
usage: python3 -I tools/m3/step2_recheck.py <days dir> <meta.json> <cases.json.gz>"""
import gzip, json, re, sys
from datetime import date, timedelta
DAYS, META, CASES = sys.argv[1:4]
meta = json.load(open(META))["meta"]
cases = json.load(gzip.open(CASES, "rt"))
_cache = {}
def day(d):
    if d not in _cache:
        if len(_cache) > 40: _cache.clear()
        _cache[d] = json.load(gzip.open(f"{DAYS}/{d}.json.gz", "rt"))
    return _cache[d]
def plus(d, n): return (date.fromisoformat(d) + timedelta(days=n)).isoformat()
def ship_sell(price, t):
    if t == "s": return 1500 if price >= 10000 else 800
    return 500 if price >= 5000 else 100
def net(ex, m, t):
    if ex == "E1": return m * (1 - 0.1325) - 30 - ship_sell(m, t)
    if ex == "E3": return round(m * 0.9)
    if ex == "E4": return round(m * 0.8)
    pr = round(m * 0.89); b = round(pr * 1.075)
    return pr - round(40 + min(b, 750000) * 0.1325 + max(b - 750000, 0) * 0.0235) - ship_sell(pr, t) - 50
SHIP_IN = {"c": 150, "s": 600}

# 1) Under market list rebuilt from scratch on 6 days
SKIP = re.compile(r"prerelease|\[staff\]|code card|jumbo|oversize|\bdeck\b.*\bcard\b|world championships", re.I)
for d in ("2025-02-05", "2025-07-09", "2025-11-26", "2026-02-04", "2026-05-13", "2026-09-09"):
    rows = []
    for k, (m, lo, md) in day(d).items():
        mt = meta.get(k.split(":")[0])
        if not mt or not m or not lo or (mt[2] or "") > d or SKIP.search(mt[3]): continue
        if m < (2000 if mt[0] == "s" else 1000): continue
        if lo >= m * 0.8 or lo < m * 0.25: continue
        rows.append((-(m - lo), k))
    mine = [k for _, k in sorted(rows)[:80]]
    theirs = [c["key"] for c in cases if c["list"] == "under" and c["day"] == d]
    same_set = set(mine) == set(theirs)
    print(f"under list {d}: {len(mine)} vs {len(theirs)}, same items: {same_set}")
    assert same_set, (set(mine) ^ set(theirs))

# 2) every Flip pick passes the app's flip gates, recomputed here
bad = 0
for c in cases:
    if c["list"] != "flip": continue
    m, lo, md = day(c["day"])[c["key"]]
    t = c["t"]; off = (1 - lo / m) * 100; cost = lo + SHIP_IN[t]; pr = m * (1 - 0.1325) - 30 - ship_sell(m, t)
    profit = pr - cost
    ok = m == c["p"] and lo == c["lo"] and 12 <= off <= 55 and profit >= (300 if t == "c" else 800) and profit / cost * 100 >= 12
    bad += not ok
print("flip gate violations:", bad); assert bad == 0

# 3) every case's buy and exit prices, from the daily files
mism = 0
for c in cases:
    m, lo, md = day(c["day"])[c["key"]]
    buy = (lo if c["list"] in ("flip", "under") else m) + SHIP_IN[c["t"]]
    mism += buy != c["buy"] or m != c["p"]
    for h in (7, 14, 30):
        v = day(plus(c["day"], h)).get(c["key"], [0, 0, 0])[0]
        mism += v != c["exit"][str(h)]
print("buy / exit price mismatches:", mism); assert mism == 0

# 4) headline numbers, pure Python
def cell(lst, y, ex, h):
    per, profits, rois = {}, [], []
    for c in cases:
        if c["list"] != lst or c["y"] != y: continue
        m1 = c["exit"][str(h)]
        if m1 <= 0: continue
        p = net(ex, m1, c["t"]) - c["buy"]; r = p / c["buy"] * 100
        per.setdefault(c["key"], []).append(p >= 500 and r >= 20); profits.append(p); rois.append(r)
    profits.sort(); n = len(profits)
    hit = sum(sum(v) / len(v) for v in per.values()) / len(per) * 100
    med = (profits[n // 2] + profits[(n - 1) // 2]) / 2
    return f"{lst} {y} {ex} {h}d: items {len(per)} hit {hit:.1f} median ${med / 100:.2f} total ${sum(profits) / 100:,.0f}"
for args in (("flip", 2026, "E3", 30), ("under", 2026, "E3", 30), ("under", 2025, "E4", 7), ("ride", 2026, "E3", 30), ("flip", 2025, "E2", 30)):
    print(cell(*args))
