"""Picks the pairs for the sneaker posts. Every pair needs an official photo; pairs without one are
postponed (they come back on a later run once the nightly photo lookup finds one).

    python tools/kicks_plan.py drop  PAGES_DIR --date 2026-11-12 --scout scout.json [--history history.json]
        -> prints the "Cop or drop?" spec for pairs releasing on --date (exit 3 = nothing to post)
    python tools/kicks_plan.py recap PAGES_DIR --date 2026-11-02 [--history history.json]
        -> prints the "Did it flip?" candidates: pairs released in the 14 days before --date that
           weren't in a recap yet, best first (the posting task checks their eBay sold prices)
    python tools/kicks_plan.py photos PAGES_DIR --from 2026-11-01 --to 2026-11-14
        -> prints which releases still have no photo (postponed)
PAGES_DIR = a checkout of the gh-pages branch (sneakers.json, data/sneaker-images.json).
"""
import json
import os
import sys
from datetime import date, timedelta


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def arg(argv, k, default=None):
    return argv[argv.index(k) + 1] if k in argv else default


def releases(pages):
    cal = load(os.path.join(pages, "sneakers.json"), {}).get("releases", [])
    imgs = load(os.path.join(pages, "data", "sneaker-images.json"), {})
    for r in cal:
        r["photo"] = bool(r.get("im") or (r.get("c") and imgs.get(r["c"])))
    return [r for r in cal if r.get("c") and r.get("r")]


def main(argv):
    mode, pages = argv[0], argv[1]
    hist = load(arg(argv, "--history"), {})
    if mode == "photos":
        a, b = arg(argv, "--from"), arg(argv, "--to")
        miss = [r for r in releases(pages) if a <= r["d"] <= b and not r["photo"]]
        print(json.dumps([{k: r.get(k) for k in ("d", "c", "b", "n")} for r in miss], ensure_ascii=False))
        return
    day = date.fromisoformat(arg(argv, "--date"))
    rel = releases(pages)
    if mode == "drop":
        scout = {p["c"]: p for p in load(arg(argv, "--scout"), {}).get("pairs", [])}
        done = hist.get("drop", {})
        pairs, later = [], []
        for r in rel:
            if r["d"] != day.isoformat() or r["c"] in done:
                continue
            s = scout.get(r["c"], {})
            if (s.get("n_ask") or 0) < 3:
                continue
            if not r["photo"]:
                later.append(r["c"])
                continue
            pairs.append({"c": r["c"], "ask_n": s["n_ask"], "ask_low": s["low"], "ask_p25": s["p25"], "h": r.get("h", 1)})
        pairs.sort(key=lambda p: (-p.pop("h"), -p["ask_n"]))
        if later:
            print(f"postponed (no photo yet): {' '.join(later)}", file=sys.stderr)
        if not pairs:
            sys.exit(3)
        print(json.dumps({"date": day.isoformat(), "mode": "drop", "pairs": pairs[:6]}))
        return
    if mode == "recap":
        done = hist.get("recap", {})
        lo, hi = (day - timedelta(days=14)).isoformat(), (day - timedelta(days=1)).isoformat()
        cand = [r for r in rel if lo <= r["d"] <= hi and r["c"] not in done]
        later = [r["c"] for r in cand if not r["photo"]]
        cand = [r for r in cand if r["photo"]]
        cand.sort(key=lambda r: (-r.get("h", 1), r["d"]), reverse=False)
        if later:
            print(f"postponed (no photo yet): {' '.join(later)}", file=sys.stderr)
        print(json.dumps([{k: r.get(k) for k in ("c", "n", "d", "r", "h")} for r in cand[:12]], ensure_ascii=False))
        return
    sys.exit(f"unknown mode {mode}")


if __name__ == "__main__":
    main(sys.argv[1:])
