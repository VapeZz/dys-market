"""Photo audit: which cards and sealed items on the live site end up showing "No image yet".

For every set released in the last N days (plus upcoming and undated new sets), checks the same chain the site uses:
TCGplayer's photo -> the item's backup photo ("im", pokemontcg.io) -> the same card's other printing (img-alt.json).
Prints a summary per game and writes img-audit.json: "nophoto" = cards with no photo of their own (the nightly build
keeps a stand-in photo for these), "missing" = items that still show no photo after every fallback.

usage: python tools/img_audit.py [days=540] [games=all] [out=img-audit.json] [prev=last img-audit.json]
The nightly build reads the result and shows the same card's photo from another printing (img-alt.json).
"""
import concurrent.futures as cf
import json
import sys
import urllib.request
from datetime import date, timedelta

SITE = "https://market.driveyourstyle.net/data/"
CDN = "https://tcgplayer-cdn.tcgplayer.com/product/{}_200w.jpg"
UA = {"User-Agent": "DriveYourStyleMarket/1.0 (+https://driveyourstyle.net)"}


def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
        return json.loads(r.read())


def ok(u):
    """True if the URL serves an image (TCGplayer answers 403/404 when there's no photo)."""
    for method in ("HEAD", "GET"):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, method=method, headers=UA), timeout=20) as r:
                return r.status == 200 and r.headers.get("Content-Type", "").startswith("image")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return False
        except Exception:
            pass
    return False


def main():
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    days, games, out = int(args.get("days", 540)), args.get("games", "all"), args.get("out", "img-audit.json")
    prev = {}
    if args.get("prev"):   # last audit: its results for sets not re-checked this run are kept
        try:
            prev = json.load(open(args["prev"], encoding="utf-8"))
        except Exception:
            prev = {}
    meta, sets, alt = get(SITE + "meta.json"), get(SITE + "sets.json"), get(SITE + "img-alt.json")
    today = date.fromisoformat(meta["updated"][:10])
    cut = (today - timedelta(days=days)).isoformat()
    newest = max(s["id"] for s in sets)
    pick = [s for s in sets if (games == "all" or s["k"] in games.split(","))
            and ((s["pub"] and s["pub"] >= cut) or (not s["pub"] and s["id"] >= newest - 1500))]
    print(f"{len(pick)} sets to check (released since {cut}, upcoming, or new and undated)")

    items = []
    with cf.ThreadPoolExecutor(16) as ex:
        for s, d in zip(pick, ex.map(lambda s: get(f"{SITE}set/{s['id']}.json"), pick)):
            items += [(s, i) for i in d["items"]]
    print(f"{len(items)} items")

    def check(si):
        s, i = si
        if ok(CDN.format(i["id"])):
            return "tcgplayer"
        if i.get("im") and ok(i["im"]):
            return "backup"
        sib = alt.get(str(i["id"]))
        if sib and ok(CDN.format(sib)):
            return "sibling"
        return "missing"

    with cf.ThreadPoolExecutor(32) as ex:
        res = list(ex.map(check, items))

    summary, missing, nophoto = {}, [], []
    for (s, i), r in zip(items, res):
        if r in ("sibling", "missing") and i["t"] == "c":
            nophoto.append({"gid": s["id"], "id": i["id"]})   # no photo of its own: the build keeps a stand-in for these
        g = summary.setdefault(s["k"], {"items": 0, "tcgplayer": 0, "backup": 0, "sibling": 0, "missing": 0, "sets_missing": {}})
        g["items"] += 1
        g[r] += 1
        if r == "missing":
            g["sets_missing"][s["n"]] = g["sets_missing"].get(s["n"], 0) + 1
            missing.append({"k": s["k"], "set": s["n"], "gid": s["id"], "pub": s["pub"], "id": i["id"], "n": i["n"],
                            "t": i["t"], "no": i.get("no", ""), "p": i.get("p")})
    checked = {s["id"] for s in pick}
    kept = [m for m in prev.get("missing", []) if m["gid"] not in checked]
    missing += kept
    nophoto += [m for m in prev.get("nophoto", []) if m["gid"] not in checked]
    if kept:
        print(f"kept {len(kept)} no-photo items from the last audit for sets not checked this time")
    print(f"{len(nophoto)} cards with no photo of their own; {len(missing)} items still show no photo")
    for k, g in sorted(summary.items()):
        top = sorted(g["sets_missing"].items(), key=lambda x: -x[1])[:6]
        print(f"{k}: {g['items']} items · {g['missing']} with no photo · fallbacks: backup {g['backup']}, sibling {g['sibling']} · worst sets {top}")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"date": meta["updated"], "days": days, "summary": summary, "missing": missing, "nophoto": nophoto}, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
