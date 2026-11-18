"""M3 Step 2 audit: 20+ random cases checked against the raw tcgcsv archives (downloaded again, raw JSON read directly).
usage: python3 -I tools/m3/step2_audit.py <meta.json> <cases.json.gz> <work dir>"""
import gzip, json, os, random, sys, urllib.request
from datetime import date, timedelta
import py7zr
META, CASES, WORK = sys.argv[1:4]
meta = json.load(open(META))["meta"]
cases = json.load(gzip.open(CASES, "rt"))
rnd = random.Random(20)
pick = []
for lst, n in (("flip", 7), ("under", 7), ("ride", 4), ("dip", 4)):
    pool = [c for c in cases if c["list"] == lst]
    pick += rnd.sample(pool, n)

def raw(day, gid, pid, sub):
    arch = os.path.join(WORK, f"{day}.7z")
    if not os.path.exists(arch):
        url = f"https://github.com/VapeZz/dys-market/releases/download/tcgcsv-{day[:4]}/prices-{day}.ppmd.7z"
        urllib.request.urlretrieve(url, arch)
    name = f"{day}/3/{gid}/prices"
    out = os.path.join(WORK, "x")
    with py7zr.SevenZipFile(arch) as z:
        if name not in z.getnames(): return None
    with py7zr.SevenZipFile(arch) as z:
        z.extract(path=out, targets=[name])
    rows = json.load(open(os.path.join(out, name)))["results"]
    for r in rows:
        if str(r["productId"]) == pid and (r.get("subTypeName") or "Normal") == sub: return r
    return None

os.makedirs(WORK, exist_ok=True)
c2 = lambda v: round(v * 100) if v else 0
print("list | day | card (set) | raw market / low / mid on the day | low next day | market +30d | buy | local 90% profit +30d | matches replay")
ok_all = True
for c in pick:
    pid, sub = c["key"].split(":", 1)
    gid = meta[pid][1]
    a = raw(c["day"], gid, pid, sub)
    nx = raw((date.fromisoformat(c["day"]) + timedelta(days=1)).isoformat(), gid, pid, sub)
    e = raw((date.fromisoformat(c["day"]) + timedelta(days=30)).isoformat(), gid, pid, sub)
    m, lo, md = c2(a["marketPrice"]), c2(a["lowPrice"]), c2(a["midPrice"])
    m30 = c2(e["marketPrice"]) if e else 0
    buy = (lo if c["list"] in ("flip", "under") else m) + (600 if c["t"] == "s" else 150)
    prof = round(m30 * 0.9) - buy if m30 else None
    match = m == c["p"] and buy == c["buy"] and m30 == c["exit"]["30"] and (c["lo"] in (None, lo))
    ok_all &= match
    print(f'{c["list"]} | {c["day"]} | {meta[pid][3]} [{sub}] ({meta[pid][4]}, {meta[pid][2][:4]}) | ${m/100:.2f} / ${lo/100:.2f} / ${md/100:.2f} | '
          f'${c2(nx["lowPrice"]) / 100 if nx else 0:.2f} | ${m30/100:.2f} | ${buy/100:.2f} | {"$%.2f" % (prof / 100) if prof is not None else "missing"} | {match}')
print("all match:", ok_all)
