# Backtest of Edge's strategy rules

Scores every rule in `site/assets/edge-strat.js` on our own price history and writes
`site/assets/edge-backtest.json`, which the strategy box in DYS Edge reads. Nothing here runs in the nightly:
rerun it by hand when the rules change. Owner only; TCGplayer market prices from tcgcsv's archives (kept in this
repo's `tcgcsv-<year>` releases) and our nightly snapshots. Nothing from PokemonPriceTracker is read.

What it does, for every 7th day and every item priced $1 or more that day: rebuilds what Edge would have held on
that day (a price for each of the last 120 days and one a week before that, back a year), runs the app's own code
on it (`edge-ta.js` analyse, `edge-strat.js` facts, pick, ladder, risk) and records the price 7, 14, 30, 60 and
90 days later and whether the first sell level or the cut level came first.

A rule is scored on the 30-day move against the average of all items on the same days. The pass rule is written
at the top of `stats.py` and was fixed before any result was looked at.

## Run it (about 45 minutes on 2 cores; needs about 3 GB of disk in `bt-work/`, which is not in git)

    python3 pipeline/run.py --rebuild                              # site data, for each product's type and set (DATA_DIR = the data branch)
    python3 tools/backtest/pull.py 2024-02-08 2026-10-11 3         # one price file per day from the stored archives (pip install py7zr, or a 7za program)
    python3 tools/backtest/matrix.py 2024-02-08 <newest day>       # all days in one table
    node tools/backtest/run.js 0 2 & node tools/backtest/run.js 1 2; wait
    python3 tools/backtest/stats.py bt-work/sig site/assets/edge-backtest.json
    node tools/backtest/check_stats.js site/assets/edge-backtest.json   # the scoring again, separately written
    python3 tools/backtest/verify.py                               # recorded prices, forward moves and rebuilt days against the table

Folders: `BT_DIR` (default `bt-work/`), `DATA_DIR` (default `data/`, the data branch's folder).

## Limits to keep in mind

- Prices are TCGplayer market prices, which follow real sales with a lag, so part of any follow-through is the
  price catching up. The result says which way the market price tends to go next, not that a card could have
  been bought at that price.
- The verdict uses days with a full year of prices behind them (from 2025-02-07). Earlier days are reported
  beside it.
- Changing a rule after reading these results and scoring it on the same days proves nothing: test a changed
  rule on days it was not shaped on.
