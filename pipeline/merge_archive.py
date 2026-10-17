"""Fill in past prices for a newly added game from our own Price archive releases.

    python pipeline/merge_archive.py gundam,union-arena

The "Price archive" workflow saves other TCGs' daily prices as release assets
(<slug>-<date>.json.gz). For every day we already have a snapshot for, this adds that
game's market prices into it, so a game added to the site keeps the history we archived.
"""
import gzip
import json
import sys
import urllib.request

import snapshots

REPO = "VapeZz/dys-market"


def assets():
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases?per_page=20",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "dys-market"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rels = json.load(r)
    return {a["name"]: a["browser_download_url"] for rel in rels for a in rel.get("assets", [])}


def main(argv):
    slugs = [s.strip() for s in argv[0].split(",") if s.strip()]
    have = set(snapshots.available())
    found = assets()
    for slug in slugs:
        merged = 0
        for name, url in sorted(found.items()):
            if not name.startswith(slug + "-") or "catalog" in name:
                continue
            day = name[len(slug) + 1:].replace(".json.gz", "")
            if day not in have:
                continue
            with urllib.request.urlopen(url, timeout=120) as r:
                doc = json.loads(gzip.decompress(r.read()))
            prices = {k: v[0] for k, v in doc.get("prices", {}).items() if v and v[0]}
            base = snapshots.load(day)
            add = {k: v for k, v in prices.items() if k not in base}
            if add:
                base.update(add)
                snapshots.save(day, base)
                merged += 1
            print(f"{slug} {day}: +{len(add)} prices")
        print(f"{slug}: merged into {merged} day(s)")


if __name__ == "__main__":
    main(sys.argv[1:])
