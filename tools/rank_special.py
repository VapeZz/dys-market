"""One-off special set ranking (test branch only): set_rank.py with landscape cards kept and PSA 10 prices.

A ranking can't skip a card, so BREAK and LEGEND cards stay in the list here (the shared card filter in
daily_card.py leaves them out because their photos are landscape). Their slide gets a landscape photo frame
so the photo fills it instead of sitting small between white bars.

Cards listed in tools/rank_special_graded.json also show what a PSA 10 sells for: the median eBay SOLD
price, checked by hand on eBay's sold listings (owner's rule: graded prices are real eBay sold prices only).
A card with too few clean PSA 10 sales is not in that file and shows no graded price.

    python tools/rank_special.py <site/data> <out> --set ID-or-name [--n 10] [--date YYYY-MM-DD]
"""
import json
import os
import re
import sys

import daily_card as dc
import set_rank as sr
from social import money

WIDE = re.compile(r"\bBREAK\b|\bLEGEND\b", re.I)          # TCGplayer serves these photos in landscape
dc.SIDEWAYS = re.compile(r"jumbo|oversize", re.I)         # still left out: not standard-size cards
G = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rank_special_graded.json")))
GRADED, DAYS = {str(k): v for k, v in G["cards"].items()}, G["days"]
GREEN = "#3ee08f"
_slides, _texts, _timing = sr.slides, sr.texts, sr.timing
_ranks = {}                                                # rank -> graded entry, set when the slides are made


def p10(c):
    return GRADED.get(str(c["id"]))


def slides(cards, setname, label, day):
    out = _slides(cards, setname, label, day)
    n = len(cards)
    _ranks.clear()
    for rank, c in enumerate(cards, 1):
        k = n - rank + 1                                    # slide 0 is the cover, then #n down to #1
        if WIDE.search(c["full"]):
            for tall in ("width:560px;height:782px", "width:520px;height:726px"):
                out[k] = out[k].replace(tall, "width:800px;height:573px")
        g = p10(c)
        if not g:
            continue
        _ranks[rank] = g
        s = out[k]
        # make room: a smaller photo and raw price, then the PSA 10 line under the raw price
        s = s.replace("width:520px;height:726px", "width:424px;height:592px").replace("width:560px;height:782px", "width:464px;height:648px")
        price = f'line-height:.92">{money(c["now"])}</div>'
        block = (f'<div style="margin-top:10px;display:flex;align-items:center;justify-content:center;gap:20px">'
                 f'<div style="font-family:\'Barlow Condensed\';font-weight:800;font-size:46px;letter-spacing:.04em;color:#050404;'
                 f'background:{GREEN};border-radius:999px;padding:4px 24px 0">PSA 10</div>'
                 f'<div style="font-family:\'Barlow Condensed\';font-weight:800;font-size:104px;line-height:.92;color:{GREEN}">${g["p10"]:,.0f}</div></div>'
                 f'<div style="margin-top:6px;font-size:27px;color:#bdb9b2">median of {g["sold"]} eBay sales, last {DAYS} days</div>')
        assert price in s, f"price line not found on slide {k}"
        s = s.replace(price, price + "\n" + block)
        s = s.replace("font-size:200px;line-height:.92", "font-size:168px;line-height:.92").replace("font-size:180px;line-height:.92", "font-size:156px;line-height:.92")
        s = s.replace("PRICE: TCGPLAYER MARKET", "RAW PRICE: TCGPLAYER MARKET")
        out[k] = s
    return out


def timing(n):
    per = _timing(n)                                        # cover, then #n down to #1, then the ending
    for rank in _ranks:
        per[n - rank + 1] += 0.8                            # two prices to read
    return per


def texts(cards, setname, label, tags, day):
    cap, yt, tt = _texts(cards, setname, label, tags, day)
    graded = [(k, c, p10(c)) for k, c in enumerate(cards, 1) if p10(c)]
    for k, c, g in graded:
        line = f"{k}. {c['name']}{' (' + c['rarity'] + ')' if c.get('rarity') else ''}: {money(c['now'])}"
        assert line in cap, f"caption line not found for #{k}"
        cap = cap.replace(line, f"{line} · PSA 10: ${g['p10']:,.0f} (eBay sold)")
    if graded:
        cap = cap.replace(f"Prices: TCGplayer market, {day}",
                          f"Prices: TCGplayer market, {day}. PSA 10 = median eBay sold price, last {DAYS} days.")
        k, c, g = max(graded, key=lambda x: x[2]["p10"])    # the hook: the biggest PSA 10 price on the list
        first = cap.splitlines()[0]
        hook = (f"This ${c['now'] / 100:,.0f} {label} card sells for ${g['p10']:,.0f} in a PSA 10 👀 "
                f"Top {len(cards)} {setname} cards ranked by price 💎")
        cap = cap.replace(first, hook, 1)
        yt = f"${c['now'] / 100:,.0f} raw, ${g['p10']:,.0f} in a PSA 10 👀 Top {len(cards)} {setname} cards {tags.split()[0]}"[:100]
    long_tag = "#" + re.sub(r"[^a-z0-9]", "", setname.lower())
    if len(long_tag) > 24:                                  # "#30thcelebrationclassiccollection": nobody searches that
        words = re.sub(r"[^a-z0-9 ]", "", setname.lower()).split()
        half = (len(words) + 1) // 2
        cap = cap.replace(long_tag, "#" + "".join(words[:half]) + " #" + "".join(words[half:]))
    return cap, yt, tt


sr.slides, sr.texts, sr.timing = slides, texts, timing

if __name__ == "__main__":
    sr.main(sys.argv[1:])
