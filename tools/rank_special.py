"""One-off special set ranking (test branch only): set_rank.py with landscape cards kept.

A ranking can't skip a card, so BREAK and LEGEND cards stay in the list here (the shared card filter in
daily_card.py leaves them out because their photos are landscape). Their slide gets a landscape photo frame
so the photo fills it instead of sitting small between white bars.

    python tools/rank_special.py <site/data> <out> --set ID-or-name [--n 10] [--date YYYY-MM-DD]
"""
import re
import sys

import daily_card as dc
import set_rank as sr

WIDE = re.compile(r"\bBREAK\b|\bLEGEND\b", re.I)          # TCGplayer serves these photos in landscape
dc.SIDEWAYS = re.compile(r"jumbo|oversize", re.I)         # still left out: not standard-size cards
_slides = sr.slides


def slides(cards, setname, label, day):
    out = _slides(cards, setname, label, day)
    n = len(cards)
    for rank, c in enumerate(cards, 1):
        if WIDE.search(c["full"]):
            k = n - rank + 1                                # slide 0 is the cover, then #n down to #1
            for tall in ("width:560px;height:782px", "width:520px;height:726px"):
                out[k] = out[k].replace(tall, "width:800px;height:573px")
    return out


sr.slides = slides

if __name__ == "__main__":
    sr.main(sys.argv[1:])
