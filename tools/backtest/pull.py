"""Build one price snapshot per day from the tcgcsv archives stored in the repo's own releases (read-only; nothing is
written to the repo). The same steps as tools/history_build.py, kept for every day instead of the thinned set.
usage: python3 tools/backtest/pull.py <first day> <last day> <workers>"""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
BT = _os.environ.get("BT_DIR") or _os.path.join(ROOT, "bt-work")            # working folder (not in git): days/, prices.i32, sig/
DATA = _os.environ.get("DATA_DIR") or _os.path.join(ROOT, "data")           # the data branch's data/ folder
import gzip, json, os, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error
from datetime import date, timedelta
from multiprocessing import Pool
sys.path.insert(0, _os.path.join(ROOT, "pipeline"))
import config, tcgcsv  # noqa: E402
import py7zr  # noqa: E402

OUT = os.environ.get("BT_OUT") or os.path.join(BT, "days")
Z7 = os.environ.get("SEVENZIP") or shutil.which("7za") or shutil.which("7z") or ""     # a 7-Zip program unpacks about twice as fast as py7zr
HIST = os.path.join(DATA, "history")
CATS = {str(g["category"]) for g in config.GAMES}

def build(day):
    out = os.path.join(OUT, f"{day}.json.gz")
    if os.path.exists(out):
        return day, -1, "have"
    have = os.path.join(HIST, f"{day}.json.gz")
    if os.path.exists(have):                       # already built by the site's own history job from the same archive
        shutil.copyfile(have, out + ".tmp"); os.replace(out + ".tmp", out)
        return day, -2, "copied from data/history"
    work = tempfile.mkdtemp(prefix="bt-")
    try:
        arch = os.path.join(work, "p.7z")
        url = f"https://github.com/VapeZz/dys-market/releases/download/tcgcsv-{day[:4]}/prices-{day}.ppmd.7z"
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "dys-edge-backtest"}), timeout=300) as r, open(arch, "wb") as f:
                    shutil.copyfileobj(r, f)
                break
            except urllib.error.HTTPError as e:
                if e.code == 404: return day, 0, "no archive"
                time.sleep(4 * (attempt + 1))
            except Exception:
                time.sleep(4 * (attempt + 1))
        else:
            return day, 0, "download failed"
        if Z7:
            subprocess.run([Z7, "x", "-y", f"-o{os.path.join(work, 'x')}", arch] + [f"-i!{day}/{c}/*/prices" for c in sorted(CATS)], check=True, stdout=subprocess.DEVNULL)
        else:
            with py7zr.SevenZipFile(arch) as z:
                names = [n for n in z.getnames() if n.endswith("/prices") and len(n.split("/")) >= 3 and n.split("/")[-3] in CATS]
            with py7zr.SevenZipFile(arch) as z:
                z.extract(path=os.path.join(work, "x"), targets=names)
        snap = {}
        for dp, _d, files in os.walk(os.path.join(work, "x")):
            if "prices" in files:
                try:
                    rows = json.load(open(os.path.join(dp, "prices"), encoding="utf-8")).get("results", [])
                except (OSError, ValueError):
                    continue
                for row in rows:
                    tcgcsv.add_price(snap, row)
        if len(snap) < 1000:
            return day, 0, f"only {len(snap)} prices"
        with open(out + ".tmp", "wb") as f:
            f.write(gzip.compress(json.dumps(snap, separators=(",", ":")).encode("utf-8"), 6))
        os.replace(out + ".tmp", out)
        return day, len(snap), "built"
    except Exception as e:  # noqa: BLE001
        return day, 0, f"{type(e).__name__}: {e}"
    finally:
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    a, b, workers = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]), int(sys.argv[3])
    days = [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)][::-1]     # newest first
    t0, done, bad = time.time(), 0, []
    with Pool(workers) as pool:
        for day, n, note in pool.imap_unordered(build, days):
            done += 1
            if n == 0: bad.append((day, note))
            if done % 25 == 0 or n == 0:
                print(f"{done}/{len(days)} {day} {n} {note} {time.time() - t0:.0f}s", flush=True)
    print(f"DONE {done} days in {time.time() - t0:.0f}s; failed {len(bad)}: {bad[:20]}", flush=True)
