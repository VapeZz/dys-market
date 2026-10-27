"""Grading cost model shared by the Python tools; mirrors the one in site/assets/app.js.

Fees live in site/assets/grade-fees.json (grader tiers with upcharges, marketplace selling fees).
All money is in cents.
"""
import json
import os

SHIP = 1500          # shipping + insurance per card, both ways
STALE_DAYS = 45      # a graded price whose last sale is older than this is stale


def load(site):
    with open(os.path.join(site, "assets", "grade-fees.json"), encoding="utf-8") as f:
        return json.load(f)


def tier_for(gr, value):
    """Index of the cheapest tier whose value limit covers value (the top tier if none does)."""
    for i, t in enumerate(gr["tiers"]):
        if t[2] is None or value <= t[2]:
            return i
    return len(gr["tiers"]) - 1


def fee_at(gr, ti, value):
    """Grading fee for one outcome worth value, submitted at tier ti (upcharged to the tier that covers it)."""
    base = gr["tiers"][ti][1]
    return max(base, gr["tiers"][tier_for(gr, value)][1]) if gr.get("upcharge") else base


def net_sale(pl, value):
    """What the seller keeps from a sale of value on a marketplace."""
    if not pl or not value:
        return value or 0
    fee = pl.get("flat", 0)
    for pct, lo, hi, cap in pl["parts"]:
        part = max(0, (value if hi is None else min(value, hi)) - lo) * pct / 100
        fee += min(part, cap) if cap is not None else part
    return max(0, value - fee)


def liquidity(g):
    """'daily', 'weekly' or 'slow' from a graded entry [price, sales 90d, sales/day 7d, trend, avg, 7d, last sale]."""
    if not g:
        return None
    rate = max(g[2] or 0, (g[1] or 0) / 90)
    return "daily" if rate >= 1 else "weekly" if rate >= 1 / 7 else "slow"


def expected(fees, raw_buy, raw, v10, v9, o10=0.30, o9=0.50, co="PSA", platform="ebay", ship=SHIP):
    """Expected profit of buying raw and grading, after grading fees (with upcharges) and selling fees."""
    gr, pl = fees["graders"][co], fees["sell"][platform]
    o8 = max(0.0, 1 - o10 - o9)
    low = raw * 0.7
    grading = o10 * fee_at(gr, 0, v10) + o9 * fee_at(gr, 0, v9) + o8 * fee_at(gr, 0, low)
    cost = raw_buy + grading + ship
    value = o10 * net_sale(pl, v10) + o9 * net_sale(pl, v9) + o8 * net_sale(pl, low)
    return value - cost, cost
