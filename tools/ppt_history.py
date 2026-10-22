"""Pokémon price history backfill from PokemonPriceTracker (paid plan: up to 6 months of daily prices).

    python tools/ppt_history.py probe                       # print the response shape for a few products
    python tools/ppt_history.py fetch SITE STORE            # fetch a batch into STORE/cache/*.json (resumable)
    python tools/ppt_history.py merge STORE SNAPDIR         # write past days into snapshot files (data/snapshots)

Needs PPT_API_KEY.
"""
import json
import os
import sys
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


if __name__ == "__main__":
    main(sys.argv[1:])
