"""Turn the catalog + snapshots into the small JSON files the website reads."""
import json
import os
import re
import shutil
from datetime import date, timedelta

import config
import snapshots

BOOSTER_BOX = re.compile(r"\bbooster box\b", re.I)
NOT_BOX = re.compile(r"\b(case|bundle|half|sleeved|display case|lot)\b", re.I)


def pct(new, old):
    return round((new - old) / old * 100, 1)


def write(rel, data):
    path = os.path.join(config.OUT_DIR, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


# collection set id -> (set id where TCGplayer lists its cards, first card number, last card number)
LINKED_CARDS = {
    "24584": ("24451", 37, 63),  # First Partner Collection 2026 -> ME promos 037-063 (the 27 starters)
}


def is_code_card(p):
    """Online code cards (TCG Live codes) clutter set lists and movers; leave them out of the site."""
    return p.get("r") == "Code Card" or p.get("n", "").lower().startswith("code card")


def ptcg_img(set_id, number):
    """Fallback card image from pokemontcg.io, used when TCGplayer has no picture."""
    if not number:
        return None
    n = number.split("/")[0].strip()
    if n.isdigit():
        n = str(int(n))
    return f"https://images.pokemontcg.io/{set_id}/{n}.png"


def label(products, key):
    pid, sub = key.split(":", 1)
    p = products[pid]
    name = p["n"]
    if p["t"] == "c" and sub not in ("Normal",):
        name = f"{name} ({sub})"
    return pid, name


def build(groups, products, stock, log=print):
    products = {k: v for k, v in products.items() if not is_code_card(v)}
    matched = stock
    stock = {k: {"u": v["u"], "p": v["p"]} for k, v in matched.items() if v.get("a", True)}
    days = snapshots.available()
    if not days:
        raise RuntimeError("No price snapshots yet. Run the nightly job first.")
    latest_day = days[-1]
    latest = snapshots.load(latest_day)
    # keep only keys we know about
    latest = {k: v for k, v in latest.items() if k.split(":", 1)[0] in products}
    log(f"build: latest snapshot {latest_day}, {len(latest)} prices, {len(days)} snapshots on hand")

    if os.path.isdir(config.OUT_DIR):
        shutil.rmtree(config.OUT_DIR)
    os.makedirs(config.OUT_DIR)

    game_of = {gid: g["k"] for gid, g in groups.items()}
    # TCGplayer sometimes stamps many old sets with the same "published" date when it
    # re-imports them. Treat a date shared by 15+ sets as unknown.
    from collections import Counter
    # Counted per game, so a real release that happens to share that date in another game keeps it.
    bulk = {kd for kd, n in Counter((g["k"], g["pub"]) for g in groups.values()).items() if kd[1] and n >= 15}
    for g in groups.values():
        if (g["k"], g["pub"]) in bulk:
            g["pub"] = ""

    # ---- window anchors -------------------------------------------------
    anchors = {}
    for w in config.MOVER_WINDOWS:
        if w == "all":
            d = days[0] if days[0] != latest_day else None
        else:
            d = snapshots.closest_on_or_before(days, snapshots.minus_days(latest_day, w))
        anchors[str(w)] = d

    # ---- per-item changes for 7/30/90 (used on set pages) --------------
    changes = {}  # key -> {"7": pct, ...}
    for w in ("7", "30", "90", "all"):
        d = anchors.get(w)
        if not d:
            continue
        old = snapshots.load(d)
        for k, v in latest.items():
            o = old.get(k)
            if o and o >= 50:
                changes.setdefault(k, {})["a" if w == "all" else w] = pct(v, o)
        del old

    # ---- movers ---------------------------------------------------------
    kinds = {"s": "sealed", "c": "cards"}
    game_slugs = ["all"] + [g["slug"] for g in config.GAMES]
    movers = {f"{kind}-{gs}": {"anchors": anchors, "windows": {}} for kind in kinds.values() for gs in game_slugs}
    for w, d in anchors.items():
        if not d:
            continue
        old = snapshots.load(d)
        buckets = {}
        for k, v in latest.items():
            o = old.get(k)
            if not o or o < 100:  # ignore items that were under $1
                continue
            pid = k.split(":", 1)[0]
            p = products[pid]
            if v < config.MOVER_THRESHOLDS[0] * 100:
                continue
            row = [int(pid), label(products, k)[1], p["g"], v, o, pct(v, o)]
            if row[5] > 300 or row[5] < -75:  # almost always a one-off sale or bad listing, not a real move
                continue
            for gs in ("all", p["k"]):
                buckets.setdefault(f"{kinds[p['t']]}-{gs}", []).append(row)
        del old
        for name, rows in buckets.items():
            per_thr = {}
            for thr in config.MOVER_THRESHOLDS:
                eligible = [r for r in rows if r[3] >= thr * 100]
                up = sorted((r for r in eligible if r[5] > 0), key=lambda r: -r[5])[: config.MOVERS_PER_LIST]
                down = sorted((r for r in eligible if r[5] < 0), key=lambda r: r[5])[: config.MOVERS_PER_LIST]
                per_thr[str(thr)] = {"up": up, "down": down}
            movers[name]["windows"][w] = per_thr
    for name, data in movers.items():
        write(f"movers/{name}.json", data)

    # ---- sets -----------------------------------------------------------
    by_set = {}
    for k, v in latest.items():
        pid = k.split(":", 1)[0]
        by_set.setdefault(str(products[pid]["g"]), []).append(k)
    products_per_set = {}
    for pid, p in products.items():
        products_per_set[str(p["g"])] = products_per_set.get(str(p["g"]), 0) + 1

    sealed_change = {}
    d7 = anchors.get("7")
    if d7:
        old = snapshots.load(d7)
        for gid, keys in by_set.items():
            now_sum = old_sum = 0
            for k in keys:
                if products[k.split(":", 1)[0]]["t"] != "s":
                    continue
                o = old.get(k)
                if o:
                    now_sum += latest[k]
                    old_sum += o
            if old_sum >= 500:
                sealed_change[gid] = pct(now_sum, old_sum)
        del old

    ptcg = {}
    for gid, g in groups.items():
        m = re.match(r"https://images\.pokemontcg\.io/([^/]+)/logo\.png", g.get("lg") or "")
        if m and g.get("k") == "pokemon":
            ptcg[gid] = m.group(1)
    cards_in = {}
    for pid, p in products.items():
        if p["t"] == "c":
            cards_in.setdefault(str(p["g"]), []).append(pid)

    def top_cards(gid, keys):
        """Up to 3 of the set's most valuable cards, for a picture when the set has no logo or box."""
        best = {}
        for k in keys:
            pid = k.split(":", 1)[0]
            if products[pid]["t"] == "c":
                best[pid] = max(best.get(pid, 0), latest[k])
        ids = sorted(best, key=lambda x: -best[x])[:3]
        ids += [x for x in cards_in.get(gid, []) if x not in ids][: 3 - len(ids)]
        return [[int(x), ptcg_img(ptcg[gid], products[x].get("no")) if gid in ptcg else None] for x in ids]

    sets_out = []
    has_products = {str(p["g"]) for p in products.values()}
    for gid, g in groups.items():
        if gid not in has_products:  # TCGplayer lists the set but has no products in it yet
            continue
        keys = by_set.get(gid, [])
        bb_key = None
        for k in keys:
            pid = k.split(":", 1)[0]
            nm = products[pid]["n"]
            if products[pid]["t"] == "s" and BOOSTER_BOX.search(nm) and not NOT_BOX.search(nm):
                if bb_key is None or latest[k] > latest[bb_key]:
                    bb_key = k
        if bb_key is None:  # no booster box: show the set's main sealed product instead
            for k in keys:
                pid = k.split(":", 1)[0]
                nm = products[pid]["n"]
                if products[pid]["t"] == "s" and not re.search(r"\bcase\b", nm, re.I):
                    if bb_key is None or latest[k] > latest[bb_key]:
                        bb_key = k
        sets_out.append({
            "id": int(gid), "n": g["name"], "a": g["abbr"], "k": g["k"], "pub": g["pub"],
            "np": products_per_set.get(gid, 0),
            "bb": latest[bb_key] if bb_key else None,
            "bbId": int(bb_key.split(":")[0]) if bb_key else None,
            "bbN": products[bb_key.split(":")[0]]["n"] if bb_key else None,
            "c7": sealed_change.get(gid),
            **({"lg": g["lg"]} if g.get("lg") else {}),
            # newer games: show the set's top cards rather than a booster box when there's no logo
            **({"tc": top_cards(gid, keys)} if not g.get("lg") and (not bb_key or g["k"] in ("lorcana", "riftbound", "palworld", "gundam", "union-arena")) else {}),
        })
    sets_out.sort(key=lambda s: s["pub"] or "", reverse=True)
    write("sets.json", sets_out)

    # ---- per-set detail with price history ------------------------------
    series_days = pick_series_days(days, latest_day)
    tracked = [k for k, v in latest.items() if v >= 100]
    idx = {k: i for i, k in enumerate(tracked)}
    series = [[None] * len(series_days) for _ in tracked]
    for j, d in enumerate(series_days):
        snap = latest if d == latest_day else snapshots.load(d)
        for k, i in idx.items():
            v = snap.get(k)
            if v is not None:
                series[i][j] = v
        del snap

    by_group = {}
    for pid, p in products.items():
        by_group.setdefault(str(p["g"]), []).append((pid, p))
    for gid in by_group:
        by_set.setdefault(gid, [])
    set_files = {}
    for gid, keys in by_set.items():
        g = groups.get(gid)
        if not g:
            continue
        items = []
        for k in sorted(keys, key=lambda k: -latest[k]):
            pid, name = label(products, k)
            p = products[pid]
            item = {"id": int(pid), "n": name, "t": p["t"], "p": latest[k]}
            if p.get("no"):
                item["no"] = p["no"]
            if p.get("r"):
                item["r"] = p["r"]
            if k in changes:
                item["ch"] = changes[k]
            if k in idx:
                item["s"] = series[idx[k]]
            if pid in stock:
                item["dys"] = stock[pid]
            if p["t"] == "c" and gid in ptcg:
                item["im"] = ptcg_img(ptcg[gid], p.get("no"))
            items.append(item)
        # cards and sealed with no market price yet still belong in the set list
        priced_ids = {k.split(":", 1)[0] for k in keys}
        for pid, p in sorted(by_group.get(gid, []), key=lambda x: x[1]["n"]):
            if pid in priced_ids:
                continue
            item = {"id": int(pid), "n": p["n"], "t": p["t"], "p": None}
            if p.get("no"):
                item["no"] = p["no"]
            if p.get("r"):
                item["r"] = p["r"]
            if p["t"] == "c" and gid in ptcg:
                item["im"] = ptcg_img(ptcg[gid], p.get("no"))
            items.append(item)
        set_files[gid] = {
            "id": int(gid), "n": g["name"], "a": g["abbr"], "k": g["k"], "pub": g["pub"],
            "dates": series_days, "items": items,
        }
    # Some collections' cards are catalogued by TCGplayer under a promo set; show them in both places.
    for gid, (src, lo, hi) in LINKED_CARDS.items():
        if gid in set_files and src in set_files:
            have = {i["id"] for i in set_files[gid]["items"]}
            for i in set_files[src]["items"]:
                m = re.match(r"\d+", i.get("no") or "")
                if i["t"] == "c" and m and lo <= int(m.group()) <= hi and i["id"] not in have:
                    set_files[gid]["items"].append(dict(i))
            set_files[gid]["items"].sort(key=lambda i: (i["t"] != "s", -(i["p"] or -1)))
    for gid, data in set_files.items():
        write(f"set/{gid}.json", data)

    # ---- search index ---------------------------------------------------
    search = []
    for k, v in latest.items():
        pid, name = label(products, k)
        p = products[pid]
        if p["t"] == "c" and v < 100:
            continue
        search.append([int(pid), name, p["g"], p["t"], v])
    search.sort(key=lambda r: -r[4])
    write("search.json", search)

    # full index for the Search page: every card and sealed product, priced or not
    rar_ix, rows_all, seen_pid = {}, [], set()
    for k, v in latest.items():
        pid, name = label(products, k)
        p = products[pid]
        seen_pid.add(pid)
        r = p.get("r")
        rows_all.append([int(pid), name, p["g"], p["t"], v, p.get("no", ""), rar_ix.setdefault(r, len(rar_ix)) if r else -1])
    for pid, p in products.items():
        if pid in seen_pid or str(p["g"]) not in groups:
            continue
        r = p.get("r")
        rows_all.append([int(pid), p["n"], p["g"], p["t"], None, p.get("no", ""), rar_ix.setdefault(r, len(rar_ix)) if r else -1])
    rows_all.sort(key=lambda r: -(r[4] or 0))
    write("search-all.json", {"r": list(rar_ix), "rows": rows_all})

    # ---- in-stock list + meta --------------------------------------------
    stock_rows = []
    for pid, s in stock.items():
        p = products.get(pid)
        if not p:
            continue
        mk = max((v for k, v in latest.items() if k.startswith(pid + ":")), default=None)
        stock_rows.append({"id": int(pid), "n": p["n"], "g": p["g"], "k": p["k"], "t": p["t"],
                           "m": mk, **s})
    stock_rows.sort(key=lambda r: -(r["m"] or 0))
    write("stock.json", stock_rows)

    # ---- market price by store handle (for the Shopify product-page widget)
    by_handle = {}
    for pid, s in matched.items():
        p = products.get(pid)
        keys = [k for k in latest if k.startswith(pid + ":")]
        if not p or not keys:
            continue
        k = max(keys, key=lambda k: latest[k])
        handle = s["u"].rsplit("/products/", 1)[-1]
        by_handle[handle] = {"id": int(pid), "g": p["g"], "t": p["t"], "m": latest[k], "c7": (changes.get(k) or {}).get("7")}
    write("store-prices.json", by_handle)

    sealed_priced = {k.split(":")[0] for k in latest if products[k.split(":")[0]]["t"] == "s"}
    cards_priced = {k.split(":")[0] for k in latest if products[k.split(":")[0]]["t"] == "c"}
    today = date.fromisoformat(latest_day)
    recent = [s for s in sets_out if s["pub"] and s["pub"] <= (today + timedelta(days=120)).isoformat()][:12]
    meta = {
        "updated": latest_day,
        "first": days[0],
        "sealed": len(sealed_priced),
        "cards": len(cards_priced),
        "sets": len(groups),
        "games": [
            {"slug": g["slug"], "label": g["label"],
             "sets": sum(1 for x in groups.values() if x["k"] == g["slug"])}
            for g in config.GAMES
        ],
        "groups": {gid: [g["name"], g["k"]] for gid, g in groups.items()},
        "recent": [s["id"] for s in recent],
        "anchors": anchors,
        "store": config.STORE_URL,
    }
    write("meta.json", meta)
    write_sitemap(groups, products, latest, latest_day)
    log(f"build: wrote {len(by_set)} set files, {len(search)} search rows, {len(stock_rows)} in-stock")


def pick_series_days(days, latest_day):
    """Daily for the last 30 days, then about weekly back one year."""
    t = date.fromisoformat(latest_day)
    picked, last_weekly = [], None
    for d in reversed(days):
        age = (t - date.fromisoformat(d)).days
        if age > 366:
            break
        if age <= 30:
            picked.append(d)
            last_weekly = d
        elif last_weekly is None or (date.fromisoformat(last_weekly) - date.fromisoformat(d)).days >= 7:
            picked.append(d)
            last_weekly = d
    return sorted(picked)


def write_sitemap(groups, products, latest, day, base="https://market.driveyourstyle.net/"):
    """Static pages, every set page and every priced sealed product page."""
    from xml.sax.saxutils import escape
    urls = [base] + [base + p for p in ("intel.html", "sets.html", "trends.html", "cards.html", "search.html", "compare.html", "calendar.html", "sneakers.html", "collectors.html", "sell.html", "links.html", "watchlist.html", "about.html", "centering.html")]
    urls += [f"{base}set.html?id={gid}" for gid in groups]
    seen = set()
    for k in latest:
        pid = k.split(":", 1)[0]
        p = products[pid]
        if p["t"] == "s" and pid not in seen:
            seen.add(pid)
            urls.append(f"{base}product.html?id={pid}&set={p['g']}")
    body = "".join(f"<url><loc>{escape(u)}</loc><lastmod>{day}</lastmod></url>" for u in urls[:50000])
    with open(os.path.join(config.SITE_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + body + "</urlset>")
