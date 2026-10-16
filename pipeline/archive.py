"""Daily price archive for other TCGs (Magic, Lorcana, Yu-Gi-Oh!, ...), so their
history is already building up if we add them to the site later.

Nothing here touches the live site. Each game's day is written to
archive-out/<game>/<date>.json.gz and the "Price archive" workflow uploads it
to a GitHub Release (one release per month), which keeps the repo small.

Daily file:   {"date", "category", "name", "groups": {gid: [name, published]},
               "prices": {"productId:subType": [market, low] (cents)}}
Monthly file: catalog-<date>.json.gz with {productId: [name, gid, number, rarity]}

    python pipeline/archive.py              # prices for every archived game
    python pipeline/archive.py --catalog    # also save each game's card list
"""
import gzip
import json
import os
import re
import sys
import time

import config
import tcgcsv

OUT = os.path.join(config.ROOT, "archive-out")

# Matched against TCGplayer category names (case-insensitive). Pokémon, Pokémon
# Japan and One Piece are skipped here: the main nightly job already saves them.
WANTED = [
    ("magic", r"^magic"),
    ("yugioh", r"yugioh|yu-gi-oh"),
    ("lorcana", r"lorcana"),
    ("flesh-and-blood", r"flesh (and|&) blood"),
    ("digimon", r"digimon"),
    ("star-wars-unlimited", r"star wars.*unlimited"),
    ("dragon-ball-fusion-world", r"dragon ball super.*fusion"),
    ("gundam", r"gundam"),
    ("riftbound", r"riftbound"),
    ("union-arena", r"union arena"),
    ("sorcery", r"sorcery"),
    ("weiss-schwarz", r"weiss"),
    ("palworld", r"palworld"),
]
SKIP_CATEGORIES = {g["category"] for g in config.GAMES}


def cents(v):
    try:
        c = int(round(float(v) * 100))
    except (TypeError, ValueError):
        return None
    return c if c > 0 else None


def pick_categories(log=print):
    cats = tcgcsv._results(tcgcsv.get_json("tcgplayer/categories"))
    out = []
    for slug, pattern in WANTED:
        hit = next((c for c in cats if c["categoryId"] not in SKIP_CATEGORIES
                    and re.search(pattern, (c.get("displayName") or c.get("name") or ""), re.I)), None)
        if hit:
            out.append((slug, hit["categoryId"], hit.get("displayName") or hit.get("name")))
        else:
            log(f"archive: no TCGplayer category matched {slug}")
    return out


def write_gz(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)


def archive_game(slug, cat, name, day, with_catalog, log=print):
    groups = tcgcsv._results(tcgcsv.get_json(f"tcgplayer/{cat}/groups"))
    gmap, prices, catalog = {}, {}, {}
    for g in groups:
        gid = g["groupId"]
        gmap[gid] = [g.get("name"), (g.get("publishedOn") or "")[:10]]
        try:
            for row in tcgcsv._results(tcgcsv.get_json(f"tcgplayer/{cat}/{gid}/prices")):
                m, lo = cents(row.get("marketPrice")), cents(row.get("lowPrice"))
                if m or lo:
                    prices[f"{row['productId']}:{row.get('subTypeName') or 'Normal'}"] = [m, lo]
            if with_catalog:
                for p in tcgcsv._results(tcgcsv.get_json(f"tcgplayer/{cat}/{gid}/products")):
                    ext = {e.get("name"): e.get("value") for e in p.get("extendedData") or []}
                    catalog[p["productId"]] = [p.get("name"), gid, ext.get("Number"), ext.get("Rarity")]
        except RuntimeError as err:  # one bad set shouldn't lose the whole game
            log(f"archive: {slug} set {gid} skipped ({err})")
    write_gz(os.path.join(OUT, slug, f"{day}.json.gz"),
             {"date": day, "category": cat, "name": name, "groups": gmap, "prices": prices})
    if with_catalog:
        write_gz(os.path.join(OUT, slug, f"catalog-{day}.json.gz"), catalog)
    log(f"archive: {name}: {len(groups)} sets, {len(prices)} prices" + (f", {len(catalog)} products" if with_catalog else ""))


def main(argv):
    day = tcgcsv.source_date()
    with_catalog = "--catalog" in argv
    start = time.time()
    for slug, cat, name in pick_categories():
        archive_game(slug, cat, name, day, with_catalog)
    with open(os.path.join(OUT, "day.txt"), "w") as f:
        f.write(day)
    print(f"archive: done in {int(time.time() - start)}s")


if __name__ == "__main__":
    main(sys.argv[1:])
