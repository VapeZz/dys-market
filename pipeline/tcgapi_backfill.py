"""Backfill price history from TCG API (tcgapi.dev) into data/snapshots.

    python pipeline/tcgapi_backfill.py test   # free plan: check ID matching + recent history
    python pipeline/tcgapi_backfill.py full   # Pro plan: full history for sealed + cards >= MIN_CENTS

Needs env TCGAPI_KEY. Our own nightly snapshots always win over backfilled values
for the same day; backfill only fills days we don't have.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

import config
import snapshots
import tcgcsv

BASE = "https://api.tcgapi.dev/v1"
MIN_CENTS = int(os.environ.get("BACKFILL_MIN_CENTS", "200"))   # cards under $2 skipped
MAP_PATH = os.path.join(config.DATA_DIR, "catalog", "tcgapi-map.json")
DONE_PATH = os.path.join(config.DATA_DIR, "catalog", "tcgapi-done.json")


def note(level, title, msg):
    """Print and surface as a GitHub annotation (readable from the API)."""
    print(f"::{level} title={title}::{msg[:900]}")


class Api:
    def __init__(self, key):
        self.key, self.calls, self.left = key, 0, None

    def get(self, path, params=None):
        q = {k: v for k, v in (params or {}).items() if v is not None}
        url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
        for attempt in range(5):
            req = urllib.request.Request(url, headers={"X-API-Key": self.key, "Accept": "application/json", "User-Agent": config.USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = json.loads(r.read().decode("utf-8"))
                self.calls += 1
                rl = body.get("rate_limit") or {}
                self.left = rl.get("remaining", self.left)
                time.sleep(0.15)
                return body
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")[:300]
                if e.code == 429:
                    if attempt < 4 and "daily" not in text.lower():
                        time.sleep(10 * (attempt + 1))
                        continue
                    raise QuotaHit(text)
                if e.code in (500, 502, 503, 504) and attempt < 4:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise RuntimeError(f"HTTP {e.code} {path}: {text}")
        raise RuntimeError(f"gave up on {path}")


class QuotaHit(Exception):
    pass


def data(body):
    return body.get("data", body)


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def test(api):
    games = data(api.get("/games"))
    names = [f"{g.get('slug') or g.get('name')} (tcgplayer {g.get('tcgplayer_id')})" for g in games] if isinstance(games, list) else games
    note("notice", "Games", ", ".join(map(str, names))[:900])
    groups, products = tcgcsv.load_catalog()
    latest = snapshots.load(snapshots.available()[-1])
    samples = [("692947", "Pitch Black ETB"), ("717607", "Mew R/RGB"), ("704873", "Mega Darkrai ex 116")]
    for k in ("one-piece", "pokemon-jp"):
        best = max((key for key in latest if products.get(key.split(":")[0], {}).get("k") == k), key=lambda key: latest[key], default=None)
        if best:
            samples.append((best.split(":")[0], f"top {k}"))
    for pid, label in samples:
        try:
            card = data(api.get(f"/cards/tcgplayer/{pid}"))
        except Exception as e:
            note("warning", f"No match {label}", str(e))
            continue
        cid = card.get("id")
        ours = {k.split(":", 1)[1]: v / 100 for k, v in latest.items() if k.startswith(pid + ":")}
        try:
            hist = data(api.get(f"/cards/{cid}/history", {"range": "month"}))
        except Exception as e:
            hist = []
            note("warning", f"History {label}", str(e))
        pts = hist if isinstance(hist, list) else []
        dates = sorted({p.get("date") for p in pts if p.get("date")})
        printings = sorted({p.get("printing") or "" for p in pts})
        note("notice", f"Match {label}", f"tcgplayer {pid} -> card {cid} '{card.get('name')}'. Ours: {ours}. "
             f"History: {len(pts)} points, {dates[0] if dates else '-'} to {dates[-1] if dates else '-'}, printings {printings}. "
             f"Sample: {pts[-3:] if pts else []}")
    note("notice", "Quota", f"{api.calls} calls used, remaining today: {api.left}")


def build_map(api, groups, log):
    """tcgplayer product id -> tcgapi card id, via each set's card list."""
    mp = load(MAP_PATH, {"sets": {}, "cards": {}})
    if not mp["sets"]:
        for g in data(api.get("/games")):
            gid = g.get("slug") or g.get("id")
            if gid not in ("pokemon", "pokemon-japan", "one-piece-card-game"):
                continue
            page = 1
            while True:
                body = api.get("/sets", {"game": gid, "page": page, "per_page": 200})
                rows = data(body) or []
                for s in rows:
                    if s.get("tcgplayer_id"):
                        mp["sets"][str(s["tcgplayer_id"])] = s["id"]
                if len(rows) < 200:
                    break
                page += 1
        save(MAP_PATH, mp)
        log(f"tcgapi: {len(mp['sets'])} sets known")
    done_sets = set(mp.get("mapped_sets", []))
    for gid in groups:
        sid = mp["sets"].get(str(gid))
        if not sid or str(gid) in done_sets:
            continue
        page = 1
        while True:
            rows = data(api.get(f"/sets/{sid}/cards", {"page": page, "per_page": 200})) or []
            for c in rows:
                if c.get("tcgplayer_id"):
                    mp["cards"][str(c["tcgplayer_id"])] = c["id"]
            if len(rows) < 200:
                break
            page += 1
        done_sets.add(str(gid))
        mp["mapped_sets"] = sorted(done_sets)
        if len(done_sets) % 25 == 0:
            save(MAP_PATH, mp)
    save(MAP_PATH, mp)
    log(f"tcgapi: {len(mp['cards'])} products mapped")
    return mp["cards"]


def full(api, log=print):
    groups, products = tcgcsv.load_catalog()
    days = snapshots.available()
    latest = snapshots.load(days[-1])
    want = {}
    for key, cents in latest.items():
        pid = key.split(":")[0]
        p = products.get(pid)
        if p and (p["t"] == "s" or cents >= MIN_CENTS):
            want[pid] = max(want.get(pid, 0), cents)
    cards = build_map(api, groups, log)
    # anything the set lists didn't cover: resolve one by one (biggest first)
    missing = sorted((p for p in want if p not in cards), key=lambda p: -want[p])
    tried = set(load(MAP_PATH, {}).get("unresolved", []))
    try:
        for n, pid in enumerate(m for m in missing if m not in tried):
            try:
                cards[pid] = data(api.get(f"/cards/tcgplayer/{pid}"))["id"]
            except RuntimeError:
                tried.add(pid)
            if n % 200 == 0:
                mp = load(MAP_PATH, {"sets": {}, "cards": {}}); mp["cards"].update(cards); mp["unresolved"] = sorted(tried); save(MAP_PATH, mp)
    except QuotaHit as e:
        note("warning", "Daily limit reached", f"Stopped while matching products ({e}). Run again tomorrow.")
    mp = load(MAP_PATH, {"sets": {}, "cards": {}}); mp["cards"].update(cards); mp["unresolved"] = sorted(tried); save(MAP_PATH, mp)
    done = set(load(DONE_PATH, []))
    todo = sorted((pid for pid in want if pid in cards and pid not in done), key=lambda p: -want[p])
    log(f"tcgapi: {len(want)} wanted, {len(todo)} still to fetch, {len(want) - sum(1 for p in want if p in cards)} not in TCG API")
    by_day = {}
    have_days = set(days)
    rev = {}
    for pid in todo:
        rev[str(cards[pid])] = pid
    try:
        for i in range(0, len(todo), 50):
            chunk = todo[i:i + 50]
            body = api.get("/bulk/history", {"ids": ",".join(str(cards[p]) for p in chunk), "range": "all"})
            for cid, pts in (data(body) or {}).items():
                pid = rev.get(str(cid))
                if not pid:
                    continue
                for pt in pts or []:
                    d, mp = pt.get("date", "")[:10], pt.get("market_price")
                    if not d or mp in (None, 0) or d in have_days:
                        continue
                    sub = pt.get("printing") or "Normal"
                    by_day.setdefault(d, {})[f"{pid}:{sub}"] = int(round(float(mp) * 100))
            done.update(chunk)
            if (i // 50) % 20 == 0:
                log(f"tcgapi: {len(done)} done, {api.calls} calls, remaining {api.left}")
    except QuotaHit as e:
        note("warning", "Daily limit reached", f"Stopped for today ({e}). Run again tomorrow to continue.")
    finally:
        save(DONE_PATH, sorted(done))
        written = 0
        for d, snap in by_day.items():
            prev = snapshots.load(d) if snapshots.exists(d) else {}
            for k, v in snap.items():
                prev.setdefault(k, v)
            snapshots.save(d, prev)
            written += 1
        note("notice", "Backfill", f"{len(done)}/{len(want)} products done; wrote {written} days of history "
             f"({min(by_day) if by_day else '-'} to {max(by_day) if by_day else '-'}). {api.calls} calls used, remaining {api.left}.")


if __name__ == "__main__":
    key = os.environ.get("TCGAPI_KEY")
    if not key:
        note("error", "Missing secret", "TCGAPI_KEY is not set")
        sys.exit(1)
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    api = Api(key)
    try:
        test(api) if mode == "test" else full(api)
    except Exception as err:
        note("error", "Backfill failed", f"{type(err).__name__}: {err}")
        raise
