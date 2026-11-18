# M3 Step 2: do the Daily Scout and Deals lists find real opportunities? (frozen plan)

Written and committed before any result was computed (Nov 17, 2026). Approved by Keo Nov 17, 9:12 PM.
Hypothetical research on archived TCGplayer prices only. No live app, data, credits or paid services involved.

## What is tested (unchanged app rules)
Every 7th day from 2025-01-01, English Pokémon only, the lists Edge's Deals tab would have shown that day:
- **Scout Flips, Momentum, Dips**: `pipeline/scout.py` `analyse()` + `score_item()` imported and run as they are,
  verdict buy or watch, top 60 per plan by the app's own ranking. "Buy" verdicts are also reported alone.
  Collector want lists (demand) have no history, so they count as none.
- **Under market**: `pipeline/buyer.py` rule: lowest listing at least 20% and at most 75% under market, cards $10+,
  sealed $20+, top 80 by dollars saved.
- Inputs on day d use only snapshots dated d or earlier: market price series (last 31 days), lowest and median listing.

**Development year:** decision days in 2025. **Holdout:** decision days 2026-01-07 to 2026-09-09, computed only
after this plan and the 2025 run are committed.

## Money
- **Buy:** Flips and Under market at the lowest listing (an advertised price, not a sale) + shipping to you
  ($1.50 card, $6 sealed, the app's defaults). Momentum and Dips at the market price + the same shipping.
- **Sell** after 7, 14 or 30 days, at that day's TCGplayer market price (an estimate, not a sale):
  - E1 TCGplayer at market: the app's own resale math (13.25% + $0.30, shipping $1 / $5 card $50+, $8 / $15 sealed $100+).
    This is what the app assumes; it is reported but does not count toward the verdict.
  - E2 eBay at 89% of market: 13.25% of price incl. 7.5% buyer tax (2.35% above $7,500) + $0.40, the app's shipping above, $0.50 supplies.
  - E3 Local cash at 90% of market, no fees.
  - E4 Local cash at 80% of market (realistic-conservative check).
- **Meets target:** profit at least $5 and ROI at least 20%.

## Pass rule (fixed now)
For a list, exit and hold, in a year: each item counts once (the average of its own cases), and
- at least 70% of items meet the target,
- median profit at least $5,
- the worst 10% of cases lose no more than 10% (10th-percentile ROI at least -10%),
- at least 100 distinct items over at least 6 months,
- and the same holds when a missing exit price is counted as a total loss.

**A list PASSES** only if, for at least one realistic exit (E2, E3 or E4) and one hold, it meets the rule in 2025
AND in the 2026 holdout. Otherwise it FAILS.

## Bias checks (reported, not used to tune anything)
- Look-ahead: a test changes every snapshot after day d and confirms the day-d lists don't change.
- Stale prices: days since the market price last changed; share of exits at an unchanged price; results without
  items whose market didn't move in the 14 days before.
- Unavailable listings: whether the lowest listing was still there the next day (next day's lowest at or under it).
- Condition: lowest listing covers any condition; results by discount depth; how often the market fell to within
  10% of the cheap listing within 30 days (sign the cheap price was the real price).
- Missing exit prices: left out in the base run (counted), total loss in the conservative run.

## Verification
- An independent pure-Python version (not importing the app) of the Flips and Under market selection and of the
  profit math, compared case by case on sample days and on headline numbers.
- 20+ random opportunities audited by hand from the raw archive files (downloaded again, read directly).

## After the holdout
No rule, threshold, exit or list is changed after looking at 2026. Any idea that comes from the results is a
proposal for Keo, tested later on new data.

## Amendment before the holdout (Nov 17, after the 2025 run; diagnostics only)
The 2025 run showed most Under market items had a market price that hadn't moved in 14 days, and most Flips were
35-55% under market (the app's own "check condition" zone). Added diagnostics only: results for items whose market
was unchanged for 14 days, and a condition check (lowest listing at least 70% of the median listing, or not).
No list, rule, exit, cost, target or pass criterion changed. 2025 results are in step2_dev2025.txt.
