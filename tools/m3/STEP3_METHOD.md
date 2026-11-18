# M3 Step 3: real listing check (method, fixed before collecting)

Approved by Keo Nov 17, 2026, 11:28 PM. Read-only: TCGplayer product pages opened in the built-in browser on skibidi,
reading the same data the page itself loads (listings, product details, price history, latest sales). No cart, no
account, no purchase, offer or message. ~5 page-data requests per card, spaced out.

## Sample (tools/m3/step3_select.py, reproducible)
Edge's live lists of Nov 17 (`data/scout.json` Flips, `data/buyer.json` Under market), English Pokémon only.
A = every Flip with a lowest listing of $75 or less (11). B = 9 of the other 17 Flips. C = 10 of the 33 Under market
items. Seeded draw (20261118) over items sorted by id. No item was chosen by hand.

## What is recorded per card
Name, set, number, rarity, language (English), printing; Edge's market and lowest listing (Nov 17); now: the cheapest
listings in any condition (condition, price, shipping, seller sales count), the cheapest Near Mint listings, the number of
NM listings; TCGplayer completed sales by condition from its price history (last 90 and 30 days: units sold, lowest and
highest sale, TCGplayer's NM market price); the 5 most recent sales shown to visitors (condition, price, shipping, date).

## Facts vs assumptions
- Facts: listings now (advertised prices) and completed sales as TCGplayer reports them.
- Assumptions (labelled): 8.375% Las Vegas sales tax on the purchase; resale on TCGplayer at the recent NM market
  (derived from completed sales) after the app's fees (13.25% + $0.30, shipping $1 under $50 / $5 at $50+); local cash at
  90% of that (Keo's default, demand unproven). Raw condition from a listing is the seller's claim.

## Verdict per card (fixed now)
- **VERIFIED**: an NM English listing of the exact printing is live, at least 3 NM sales in 90 days, and buying that
  listing (price + shipping + tax) then selling on TCGplayer at the NM market after fees leaves at least $5 and 20%.
- **FAIL**: at least 3 NM sales in 90 days, but no NM listing clears that bar (or none is listed).
- **UNCERTAIN**: fewer than 3 NM sales in 90 days (no reliable NM comparable), or the data couldn't be read.

## Flags
- Condition mismatch: Edge's lowest-listing price matches a non-NM copy (cheapest listings or recent sales at that price).
- Stale market: Edge's market more than 15% above TCGplayer's current NM market, or no NM sale in 30 days.
- Unavailable: nothing is listed at or under Edge's lowest-listing price now.
- Suspicious discount: Edge's discount over 35% (the app's own condition-check zone).
