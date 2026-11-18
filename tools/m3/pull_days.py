"""M3 Step 1 (Quick Flip): one English Pokémon price snapshot per needed day, from the tcgcsv archives stored in this
repo's own releases (read-only; nothing written to the repo). Keeps TCGplayer market price per productId:printing, in
cents. Needed days: every 7th day from 2025-01-01 (decision days) plus the days 7, 14 and 30 later (exit days).
usage: python3 tools/m3/pull_days.py <out dir> <workers>"""
import gzip, json, os, shutil, sys, tempfile, time, urllib.request
from datetime import date, timedelta
from multiprocessing import Pool
import py7zr

OUT = sys.argv[1]
FIRST, LAST_DECISION = date(2025, 1, 1), date(2026, 9, 9)     # the archive ends 2026-10-11, so 30-day exits stay inside it
HOLDS = (7, 14, 30)

def needed():
    days, d = set(), FIRST
    while d <= LAST_DECISION:
        days.add(d)
        for h in HOLDS: days.add(d + timedelta(days=h))
        d += timedelta(days=7)
    return sorted(x.isoformat() for x in days)

def build(day):
    out = os.path.join(OUT, f"{day}.json.gz")
    if os.path.exists(out): return day, -1
    work = tempfile.mkdtemp(prefix="m3-")
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
                p = row.get("marketPrice")
                try: c = int(round(float(p) * 100))
                except (TypeError, ValueError): continue
                if c > 0: snap[f"{row['productId']}:{row.get('subTypeName') or 'Normal'}"] = c
        with gzip.open(out + ".tmp", "wt", encoding="utf-8") as f: json.dump(snap, f)
        os.replace(out + ".tmp", out)
        return day, len(snap)
    finally:
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    days = needed()
    print(f"{len(days)} days needed ({days[0]} to {days[-1]})", flush=True)
    with Pool(int(sys.argv[2])) as p:
        for i, (day, n) in enumerate(p.imap_unordered(build, days)):
            if n == 0 or i % 25 == 0: print(i, day, n, flush=True)
    have = sorted(f[:10] for f in os.listdir(OUT) if f.endswith(".json.gz"))
    print("have", len(have), "missing", sorted(set(days) - set(have)))
