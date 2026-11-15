"""DYS Edge: a price for every day of the last DAYS days, one small file per set.

The set files (site/data/set/<id>.json) hold daily prices for 30 days and about weekly before that.
That is too thin for the daily indicators on Edge's card chart (RSI, MACD, Bollinger bands), so this
writes the same TCGplayer market prices, from the same snapshots the site build reads, for every day
of the last DAYS days: site/data/edge/daily/<set id>.json. Only DYS Edge reads these files; the
market site's pages don't.

One file:
    {"v": 1, "day": "2026-11-14", "from": "2026-07-18", "days": 120,
     "s": {"<product id>|<item name as in the set file>": "<packed prices>", ...}}
("dates": [...] replaces "from" and "days" when a day is missing from the window.)

Packed prices (pack / unpack below; assets/edge-ta.js reads the same format): tokens split by
spaces. The first is the position of the first day that has a price. After it, one token per step
forward in time:
    123     the first price in cents; later, a change in cents from the last price (never 0)
    z, z5   the price is unchanged for one day, for 5 days
    n, n5   no price that day, for 5 days (the next change still counts from the last price)
Days with no price at the end are left off. About three day-to-day steps in four are unchanged, so
this is a quarter of the size of plain lists.
"""
import json
import os
from datetime import date, timedelta

VERSION = 1
DAYS = 120       # config.KEEP_DAILY_DAYS: every day is on hand for this long


def pack(values):
    """A list of prices in cents (None = no price that day) as one short string; "" when it has no price."""
    start = next((i for i, v in enumerate(values) if v is not None), None)
    if start is None:
        return ""
    end = max(i for i, v in enumerate(values) if v is not None)
    out, prev, run, kind = [str(start), str(int(values[start]))], int(values[start]), 0, ""

    def flush():
        if run:
            out.append(kind if run == 1 else f"{kind}{run}")

    for v in values[start + 1:end + 1]:
        step = "n" if v is None else "z" if int(v) == prev else ""
        if step != kind:
            flush()
            run, kind = 0, step
        if step:
            run += 1
        else:
            out.append(str(int(v) - prev))
            prev = int(v)
    flush()
    return " ".join(out)


def unpack(text, n):
    """The reverse of pack: a list of n prices."""
    out = [None] * n
    tok = text.split()
    if len(tok) < 2:
        return out
    i, prev = int(tok[0]), int(tok[1])
    out[i] = prev
    i += 1
    for t in tok[2:]:
        if t[0] in "zn":
            k = int(t[1:] or 1)
            if t[0] == "z":
                out[i:i + k] = [prev] * k
            i += k
        else:
            prev += int(t)
            out[i] = prev
            i += 1
    return out[:n]


def window(days, latest_day, n=DAYS):
    """The saved days from the last n calendar days, oldest first."""
    t = date.fromisoformat(latest_day)
    return sorted(d for d in days if 0 <= (t - date.fromisoformat(d)).days < n)


def build(set_files, keys, days, latest_day, view, latest=None):
    """{set id: file} for every set that has a tracked item.

    set_files  the set files the site build just made ({set id: {"items": [...]}})
    keys       {(product id as text, item name): [snapshot key, ...]} for the tracked prices
    view       day -> {snapshot key: cents} (snapshots.view); `latest` is that for latest_day, if on hand
    Only items the set file gives a price history ("s") get a row, under the same id and name, so a
    card that a second set file lists too (build.LINKED_CARDS) is in both sets' files.
    """
    win = window(days, latest_day)
    if not win:
        return {}
    want = {}                                   # snapshot key -> its row of prices
    plan = {}                                   # set id -> [(row name, snapshot key)]
    for gid, sf in set_files.items():
        for it in sf.get("items", ()):
            if "s" not in it:
                continue
            cands = keys.get((str(it["id"]), it["n"])) or ()
            # two prices under one name (rare): the one the set file shows
            k = next((c for c in cands if latest is not None and latest.get(c) == it.get("p")), cands[0] if cands else None)
            if k is None:
                continue
            want.setdefault(k, [None] * len(win))
            plan.setdefault(gid, []).append((f"{it['id']}|{it['n']}", k))
    for j, d in enumerate(win):
        snap = latest if latest is not None and d == latest_day else view(d)
        for k, row in want.items():
            v = snap.get(k)
            if v is not None:
                row[j] = v
        del snap
    first = date.fromisoformat(win[0])
    whole = all(date.fromisoformat(d) == first + timedelta(days=i) for i, d in enumerate(win))
    head = {"v": VERSION, "day": latest_day, **({"from": win[0], "days": len(win)} if whole else {"dates": win})}
    packed = {k: pack(row) for k, row in want.items()}
    out = {}
    for gid, rows in plan.items():
        s = {name: packed[k] for name, k in rows if packed[k]}
        if s:
            out[gid] = {**head, "s": s}
    return out


def write(out_dir, files):
    """Write the files under out_dir/edge/daily/; returns (files, price rows, bytes)."""
    folder = os.path.join(out_dir, "edge", "daily")
    os.makedirs(folder, exist_ok=True)
    rows = size = 0
    for gid, data in files.items():
        path = os.path.join(folder, f"{gid}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        rows += len(data["s"])
        size += os.path.getsize(path)
    return len(files), rows, size
