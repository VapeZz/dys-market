"""M3 Step 2: one English Pokémon snapshot per day (every day) from the tcgcsv archives in this repo's own releases
(read-only; nothing written to the repo). Keeps, per productId:printing, in cents: TCGplayer market price, lowest
listing (lowPrice, any condition) and median listing (midPrice). 0 = not given that day.
usage: python3 tools/m3/pull_full.py <out dir> <workers> [first] [last]"""
import gzip, json, os, shutil, sys, tempfile, time, urllib.request
from datetime import date, timedelta
from multiprocessing import Pool
import py7zr

OUT = sys.argv[1]
FIRST = date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else date(2024, 12, 1)
LAST = date.fromisoformat(sys.argv[4]) if len(sys.argv) > 4 else date(2026, 10, 11)

def cents(v):
    try: c = int(round(float(v) * 100))
    except (TypeError, ValueError): return 0
    return c if c > 0 else 0

def build(day):
    out = os.path.join(OUT, f"{day}.json.gz")
    if os.path.exists(out): return day, -1
    work = tempfile.mkdtemp(prefix="m3s-")
    try:
        arch = os.path.join(work, "p.7z")
        url = f"https://github.com/VapeZz/dys-market/releases/download/tcgcsv-{day[:4]}/prices-{day}.ppmd.7z"
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "dys-edge-m3"}), timeout=300) as r, open(arch, "wb") as f:
                    shutil.copyfileobj(r, f)
                break
            except Exception as e:
                if getattr(e, "code", None) == 404: return day, 0
                time.sleep(4 * (attempt + 1))
        else:
            return day, 0
        with py7zr.SevenZipFile(arch) as z:
            names = [n for n in z.getnames() if n.endswith("/prices") and n.split("/")[1] == "3"]
        with py7zr.SevenZipFile(arch) as z:
            z.extract(path=os.path.join(work, "x"), targets=names)
        snap = {}
        for dp, _d, files in os.walk(os.path.join(work, "x")):
            if "prices" not in files: continue
            try: rows = json.load(open(os.path.join(dp, "prices"), encoding="utf-8")).get("results", [])
            except (OSError, ValueError): continue
            for row in rows:
                v = [cents(row.get("marketPrice")), cents(row.get("lowPrice")), cents(row.get("midPrice"))]
                if any(v): snap[f"{row['productId']}:{row.get('subTypeName') or 'Normal'}"] = v
        with gzip.open(out + ".tmp", "wt", encoding="utf-8") as f: json.dump(snap, f)
        os.replace(out + ".tmp", out)
        return day, len(snap)
    finally:
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    days, d = [], FIRST
    while d <= LAST: days.append(d.isoformat()); d += timedelta(days=1)
    print(f"{len(days)} days ({days[0]} to {days[-1]})", flush=True)
    t0 = time.time()
    with Pool(int(sys.argv[2])) as p:
        for i, (day, n) in enumerate(p.imap_unordered(build, days)):
            if n == 0 or i % 25 == 0: print(i, day, n, f"{time.time()-t0:.0f}s", flush=True)
    have = sorted(f[:10] for f in os.listdir(OUT) if f.endswith(".json.gz"))
    print("have", len(have), "missing", sorted(set(days) - set(have)), flush=True)
