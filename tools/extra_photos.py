"""Extra card photos for cards with no photo anywhere on TCGplayer, only from sources whose written terms allow it.

Yu-Gi-Oh!: YGOPRODeck API (https://db.ygoprodeck.com/api-guide-v2/): free to use; pull each image once and store it
yourself; at most 20 requests a second (we stay around 4). Credited on legal.html.

Reads the weekly photo audit, skips cards that already show a stand-in from another printing, and writes
<out>/ygo/<productId>.jpg plus <out>/index.json {productId: "img/extra/ygo/<productId>.jpg"} (the site's last
photo fallback). Names YGOPRODeck doesn't have are remembered in <out>/misses.json and retried after 30 days.

usage: python tools/extra_photos.py audit=img-audit.json out=photos-dir
"""
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

SITE = "https://market.driveyourstyle.net/data/"
YGO_API = "https://db.ygoprodeck.com/api/v7/cardinfo.php?name="
UA = {"User-Agent": "DriveYourStyleMarket/1.0 (+https://driveyourstyle.net)"}


def fetch(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
        return r.read()


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def main():
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    audit, out = load(args["audit"], {}), args["out"]
    os.makedirs(os.path.join(out, "ygo"), exist_ok=True)
    idx_path, miss_path = os.path.join(out, "index.json"), os.path.join(out, "misses.json")
    idx, misses = load(idx_path, {}), load(miss_path, {})
    today = date.today()
    retry_before = (today - timedelta(days=30)).isoformat()
    alt = json.loads(fetch(SITE + "img-alt.json"))
    nophoto = {m["id"] for m in audit.get("nophoto", [])} | {m["id"] for m in audit.get("missing", [])}

    # Yu-Gi-Oh! cards with no photo of their own and no working stand-in, not fetched yet
    names = {}
    for m in audit.get("missing", []):
        if m["k"] != "yugioh" or m["t"] != "c" or str(m["id"]) in idx:
            continue
        if str(m["id"]) in alt and alt[str(m["id"])] not in nophoto:
            continue
        name = m["n"].split(" (")[0].strip()
        if name.startswith("Token:"):   # character tokens ("Token: Joey and ...") are product-only art, not in the database
            continue
        names.setdefault(name, []).append(m["id"])

    found = new = 0
    for name, pids in sorted(names.items()):
        if misses.get(name, "") > retry_before:
            continue
        try:
            data = json.loads(fetch(YGO_API + urllib.parse.quote(name)))
            url = data["data"][0]["card_images"][0]["image_url"]
        except (urllib.error.HTTPError, KeyError, IndexError, ValueError):
            misses[name] = today.isoformat()
            time.sleep(0.25)
            continue
        time.sleep(0.25)
        first = os.path.join(out, "ygo", f"{pids[0]}.jpg")
        try:
            body = fetch(url)   # each image is pulled once; later runs skip cards already in index.json
        except Exception:
            continue
        time.sleep(0.25)
        with open(first, "wb") as f:
            f.write(body)
        for pid in pids:
            if pid != pids[0]:
                shutil.copyfile(first, os.path.join(out, "ygo", f"{pid}.jpg"))
            idx[str(pid)] = f"img/extra/ygo/{pid}.jpg"
            new += 1
        found += 1
        misses.pop(name, None)

    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, separators=(",", ":"))
    with open(miss_path, "w", encoding="utf-8") as f:
        json.dump(misses, f, ensure_ascii=False, indent=0)
    print(f"Yu-Gi-Oh!: {len(names)} card names without a photo; {found} found on YGOPRODeck; {new} cards got a photo; "
          f"{len(idx)} extra photos in total; not in the database: {sorted(misses)[:15]}")


if __name__ == "__main__":
    main()
