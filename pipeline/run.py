"""Nightly job: sync catalog, save today's prices, rebuild site data.

    python pipeline/run.py            # normal nightly run
    python pipeline/run.py --rebuild  # just rebuild site data from saved snapshots
"""
import json
import os
import sys

import build
import logos
import config  # noqa: F401  (loads settings / env overrides)
import snapshots
import store
import tcgcsv


def main(argv):
    if "--rebuild" in argv:
        groups, products = tcgcsv.load_catalog()
    else:
        groups, products = tcgcsv.sync_catalog()
    if "--rebuild" not in argv:
        day = tcgcsv.source_date()
        if snapshots.exists(day):
            snap = snapshots.load(day)
            have = {products.get(k.split(":", 1)[0], {}).get("k") for k in snap}
            missing = {gid: g for gid, g in groups.items() if g.get("k") not in have}
            if missing:   # a game was just added: fetch its prices for today too
                extra = tcgcsv.fetch_prices(missing)
                snap.update({k: v for k, v in extra.items() if k not in snap})
                snapshots.save(day, snap)
                print(f"prices: added {len(extra)} prices for newly added games to {day}")
            else:
                print(f"prices: snapshot for {day} already saved; skipping download")
        else:
            snapshots.save(day, tcgcsv.fetch_prices(groups))
            lows = getattr(tcgcsv.fetch_prices, "lows", None)
            if lows:
                os.makedirs(os.path.join(config.DATA_DIR, "lows"), exist_ok=True)
                with open(os.path.join(config.DATA_DIR, "lows", "latest.json"), "w", encoding="utf-8") as f:
                    json.dump({"day": day, "lows": lows, "mids": getattr(tcgcsv.fetch_prices, "mids", None) or {}}, f, separators=(",", ":"))
        removed = snapshots.prune(day)
        if removed:
            print(f"snapshots: pruned {removed} old files")
    logos.attach(groups)
    store_rows = store.fetch_store_products()
    stock = store.match_in_stock(products, store_rows)
    build.build(groups, products, stock)
    build.write("sneakers-stock.json", store.sneaker_rows(store_rows))


if __name__ == "__main__":
    main(sys.argv[1:])
