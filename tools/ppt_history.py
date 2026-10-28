"""Pokémon price history backfill from PokemonPriceTracker (paid plan: up to 6 months of daily prices).

    python tools/ppt_history.py probe                       # print the response shape for a few products
    python tools/ppt_history.py fetch SITE STORE            # fetch a batch into STORE/cache/*.json (resumable)
    python tools/ppt_history.py merge STORE SNAPDIR         # write past days into snapshot files (data/snapshots)

Needs PPT_API_KEY.
"""
import glob
import gzip
import json
import os
import sys
from datetime import date
import time
import urllib.error
import urllib.request

API = "https://www.pokemonpricetracker.com/api/v2"


def get(path, key):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + key, "User-Agent": "dys-market"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def shape(x, depth=0, maxd=4):
    if depth > maxd:
        return "…"
    if isinstance(x, dict):
        return {k: shape(v, depth + 1, maxd) for k, v in list(x.items())[:25]}
    if isinstance(x, list):
        return [f"list[{len(x)}]", shape(x[0], depth + 1, maxd)] if x else "list[0]"
    return type(x).__name__ + (f"={str(x)[:40]}" if isinstance(x, (str, int, float)) else "")


def main(argv):
    key = (os.environ.get("PPT_API_KEY") or "").strip()
    cmd = argv[0]
    if cmd == "probe":
        for label, path in [("card 610516", "/cards?tcgPlayerId=610516&includeHistory=true&days=180"),
                            ("multi-printing 610435", "/cards?tcgPlayerId=610435&includeHistory=true&days=180"),
                            ("sealed", "/sealed-products?tcgPlayerId=593324&includeHistory=true&days=180")]:
            try:
                d = get(path, key)
                data = d.get("data")
                first = data[0] if isinstance(data, list) and data else data
                ph = (first or {}).get("priceHistory") if isinstance(first, dict) else None
                print(f"::notice title=PPT {label}::top={list(d.keys())} credits={d.get('metadata', {}).get('creditsUsed') if isinstance(d.get('metadata'), dict) else d.get('metadata')} "
                      f"keys={list(first.keys())[:40] if isinstance(first, dict) else type(first).__name__}")
                print(f"::notice title=PPT {label} history::{json.dumps(shape(ph, maxd=3))[:900]}")
                prices = (first or {}).get("prices") if isinstance(first, dict) else None
                print(f"::notice title=PPT {label} prices::{json.dumps(shape(prices, maxd=2))[:600]}")
            except urllib.error.HTTPError as e:
                print(f"::warning title=PPT {label}::HTTP {e.code} {e.read()[:200]!r}")
            time.sleep(1.2)
    elif cmd == "fetch":
        fetch(argv[1], argv[2])


PER_RUN = int(os.environ.get("PPT_HIST_PER_RUN", "4500"))
MIN_CARD = 200          # cards worth $2+ (all sealed)


def num(p):
    for k in ("market", "price", "marketPrice", "value", "unopenedPrice", "avg"):
        v = p.get(k) if isinstance(p, dict) else None
        if isinstance(v, (int, float)) and v > 0:
            return v
    return None


def series(item, sealed):
    """[(YYYY-MM-DD, cents)] for the primary printing, Near Mint (cards) or unopened (sealed)."""
    ph = item.get("priceHistory")
    if sealed:
        pts = ph if isinstance(ph, list) else (ph or {}).get("history") or []
    else:
        conds = (ph or {}).get("conditions") or {}
        pts = (conds.get("Near Mint") or {}).get("history") or []
    out = []
    for pt in pts:
        d, v = (pt.get("date") or "")[:10], num(pt)
        if len(d) == 10 and v:
            out.append((d, round(v * 100)))
    return out


def snap_path(snapdir, day):
    return os.path.join(snapdir, f"{day}.json.gz")


def fetch(site, store):
    snapdir = os.path.join(store, "snapshots")
    days = sorted(os.path.basename(f)[:10] for f in glob.glob(os.path.join(snapdir, "*.json.gz")))
    latest = json.load(gzip.open(snap_path(snapdir, days[-1]), "rt"))
    keys_of = {}
    for k in latest:
        keys_of.setdefault(k.split(":", 1)[0], []).append(k)
    donep = os.path.join(store, "ppt-history-done.json")
    try:
        done = set(json.load(open(donep)))
    except (OSError, ValueError):
        done = set()
    cands = []
    for f in glob.glob(os.path.join(site, "data", "set", "*.json")):
        d = json.load(open(f))
        if d.get("k") != "pokemon":
            continue
        for i in d["items"]:
            pid = str(i["id"])
            if not i.get("p") or pid in done or pid not in keys_of:
                continue
            if i["t"] == "s" or i["p"] >= MIN_CARD:
                cands.append((i["p"], pid, i["t"] == "s"))
    uniq = {}
    for p, pid, sealed in sorted(cands, reverse=True):
        uniq.setdefault(pid, (p, sealed))
    todo = list(uniq.items())[:PER_RUN]
    key = (os.environ.get("PPT_API_KEY") or "").strip()
    add = {}          # day -> {key: cents}
    got = skipped = 0
    sp = os.path.join(store, "ppt-history-start.txt")      # first day of our own nightly tracking
    try:
        first_day = open(sp).read().strip()
    except OSError:
        first_day = days[0]
        open(sp, "w").write(first_day)
    for pid, (p, sealed) in todo:
        d, stop = None, False
        for attempt in range(4):
            try:
                d = get(f"/{'sealed-products' if sealed else 'cards'}?tcgPlayerId={pid}&limit=1&includeHistory=true&days=180", key)
                break
            except urllib.error.HTTPError as e:
                body = e.read()[:200]
                if e.code == 429 and b"inute" in body and attempt < 3:      # per-minute limit: wait for the window
                    time.sleep(65)
                    continue
                if e.code in (401, 402, 403, 429):
                    print(f"::warning title=History::stopped: HTTP {e.code} {body!r}")
                    stop = True
                break
            except Exception as e:
                print(f"history: {pid} failed: {e}")
                time.sleep(2)
                break
        if stop:
            break
        if d is None:
            continue
        data = d.get("data")
        item = data[0] if isinstance(data, list) and data else data
        done.add(pid)
        if not isinstance(item, dict):
            skipped += 1
            continue
        ks = keys_of[pid]
        if sealed:
            k = ks[0] if len(ks) == 1 else next((x for x in ks if x.endswith(":Normal")), None)
        else:
            prim = (item.get("prices") or {}).get("primaryPrinting") or ""
            k = f"{pid}:{prim}" if f"{pid}:{prim}" in latest else (ks[0] if len(ks) == 1 else None)
        pts = series(item, sealed)
        if not k or not pts:
            skipped += 1
            continue
        # sanity: their latest price must match ours (same printing / product)
        now = latest.get(k)
        if now and not (0.65 <= pts[-1][1] / now <= 1.5):
            skipped += 1
            continue
        for day, cents in pts:
            if day < first_day:                      # only fill days before our own tracking started
                add.setdefault(day, {})[k] = cents
        got += 1
        time.sleep(2.1)
    # through the snapshot store, so days before our own tracking are written encrypted (their terms: store, don't publish)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
    import snapshots  # noqa: E402
    snapshots.SNAP_DIR = snapdir
    for day, vals in add.items():
        cur = snapshots.load(day)
        for k, v in vals.items():
            cur.setdefault(k, v)
        snapshots.save(day, cur)
    json.dump(sorted(done), open(donep, "w"))
    left = len(uniq) - len(todo)
    print(f"history: {got} products backfilled, {skipped} skipped, {len(add)} past days written, {left} products left")


if __name__ == "__main__":
    main(sys.argv[1:])
