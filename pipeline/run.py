"""Nightly job: sync catalog, save today's prices, rebuild site data.

    python pipeline/run.py            # normal nightly run
    python pipeline/run.py --rebuild  # just rebuild site data from saved snapshots
"""
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
            print(f"prices: snapshot for {day} already saved; skipping download")
        else:
            snapshots.save(day, tcgcsv.fetch_prices(groups))
        removed = snapshots.prune(day)
        if removed:
            print(f"snapshots: pruned {removed} old files")
    logos.attach(groups)
    stock = store.match_in_stock(products, store.fetch_store_products())
    build.build(groups, products, stock)


if __name__ == "__main__":
    main(sys.argv[1:])
