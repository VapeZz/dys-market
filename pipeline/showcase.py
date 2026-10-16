"""Collectors page data: public binders, likes and followers.

Every signed-in collector's binder is saved on their Shopify customer record
(metafield dys.binder, written by the site through the Customer Account API).
It holds: name, items, alias (public collector name), pub (show on the
Collectors page), likes [profile ids], follows [profile ids].

This job reads those metafields with the Admin API and publishes only what
collectors chose to make public:
    <site>/data/showcase.json            directory of public binders
    <site>/data/showcase/<pid>.json      one public binder (no prices paid, no email)
Like and follower counts are tallied from everyone's likes/follows lists, so
each account counts once. A profile id (pid) is a one-way hash of the customer
id, so Shopify ids are never published.

    python pipeline/showcase.py <site dir>
Needs SHOPIFY_SHOP + SHOPIFY_CLIENT_ID/SHOPIFY_CLIENT_SECRET (or SHOPIFY_ADMIN_TOKEN).
Hidden profiles: list pids in site/showcase-hidden.json.
"""
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shopify_api import Shopify  # noqa: E402

ALIAS = re.compile(r"^[A-Za-z0-9_.]{3,20}$")
BLOCK = re.compile(r"fuck|shit|bitch|cunt|nigg|fag|rape|nazi|hitler|porn|sex|dick|pussy|whore|slut|kkk|retard|admin|driveyourstyle|drive_your_style|official", re.I)
PRINT = {"Normal": "", "Holofoil": "H", "Reverse Holofoil": "RH"}


def pid_of(gid):
    return hashlib.sha256(("dys:" + gid).encode()).hexdigest()[:12]


def sub_of(name):
    m = re.search(r" \(([^)]+)\)$", name or "")
    return m.group(1) if m else "Normal"


def code_of(sub):
    return PRINT[sub] if sub in PRINT else re.sub(r"[^A-Za-z0-9]", "", sub).upper()[:12]


def fetch_binders(api):
    q = """query($after: String) { customers(first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { id createdAt metafield(namespace: "dys", key: "binder") { value } } } }"""
    out, after = [], None
    while True:
        d = api.gql(q, {"after": after})["customers"]
        for c in d["nodes"]:
            if c.get("metafield"):
                try:
                    out.append((c["id"], c["createdAt"], json.loads(c["metafield"]["value"])))
                except ValueError:
                    pass
        if not d["pageInfo"]["hasNextPage"]:
            return out
        after = d["pageInfo"]["endCursor"]


def main(argv):
    site = argv[0]
    data = os.path.join(site, "data")
    rows = json.load(open(os.path.join(data, "search.json")))
    price = {f"{r[0]}|{code_of(sub_of(r[1]))}": r[4] for r in rows}
    kind = {r[0]: r[3] for r in rows}
    try:
        hidden = set(json.load(open(os.path.join(site, "showcase-hidden.json"))))
    except (OSError, ValueError):
        hidden = set()

    shop = os.environ.get("SHOPIFY_SHOP")
    if not shop:
        print("::warning title=Collectors::SHOPIFY_SHOP not set; skipping")
        return
    try:
        binders = fetch_binders(Shopify(shop))
    except Exception as err:  # e.g. the app can't read customers yet
        # warn instead of failing so a missing permission doesn't send failure emails every 30 minutes
        print(f"::warning title=Collectors::{str(err)[:400]}")
        return
    sdir = os.path.join(data, "showcase")
    if os.path.isdir(sdir):                      # binders made private since last run disappear
        for f in os.listdir(sdir):
            os.remove(os.path.join(sdir, f))

    likes, followers = {}, {}
    for gid, _, b in binders:
        me = pid_of(gid)
        for p in set(b.get("likes") or []):
            if p != me:
                likes[p] = likes.get(p, 0) + 1
        for p in set(b.get("follows") or []):
            if p != me:
                followers[p] = followers.get(p, 0) + 1

    profiles, taken = [], set()
    for gid, created, b in sorted(binders, key=lambda x: x[1]):   # older accounts keep a name first
        pid = pid_of(gid)
        alias = (b.get("alias") or "").strip()
        if not b.get("pub") or pid in hidden or not ALIAS.match(alias) or BLOCK.search(alias):
            continue
        if alias.lower() in taken:
            alias = f"{alias}_{pid[:3]}"
        taken.add(alias.lower())
        items, value, cards = [], 0, 0
        for it in b.get("items") or []:
            try:
                iid, qty = int(it["id"]), max(1, int(it.get("qty") or 1))
            except (KeyError, TypeError, ValueError):
                continue
            gr = str(it["gr"])[:30] if it.get("gr") else None
            gv = it.get("gv") if gr and isinstance(it.get("gv"), (int, float)) else None
            mkt = price.get(f"{iid}|{code_of(sub_of(it.get('n') or ''))}")
            each = gv if gv is not None else mkt
            value += (each or 0) * qty
            if kind.get(iid) == "c":
                cards += qty
            row = {"id": iid, "g": it.get("g"), "n": (it.get("n") or "")[:120], "qty": qty}
            if gr:
                row["gr"], row["gv"] = gr, gv
            items.append((each or 0, row))
        if not items:
            continue
        items.sort(key=lambda x: -x[0] * x[1]["qty"])
        top = [[r["id"], r.get("gr")] for _, r in items[:4]]
        prof = {"p": pid, "a": alias, "bn": (b.get("name") or "")[:60], "v": round(value), "n": sum(r["qty"] for _, r in items),
                "c": cards, "top": top, "l": likes.get(pid, 0), "f": followers.get(pid, 0), "u": b.get("updated") or 0}
        profiles.append(prof)
        os.makedirs(os.path.join(data, "showcase"), exist_ok=True)
        with open(os.path.join(data, "showcase", f"{pid}.json"), "w", encoding="utf-8") as f:
            json.dump({**prof, "items": [r for _, r in items]}, f, separators=(",", ":"), ensure_ascii=False)

    with open(os.path.join(data, "showcase.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": int(time.time() * 1000), "profiles": profiles}, f, separators=(",", ":"), ensure_ascii=False)
    print(f"collectors: {len(profiles)} public binders out of {len(binders)} saved, {sum(likes.values())} likes, {sum(followers.values())} follows")


if __name__ == "__main__":
    main(sys.argv[1:])
