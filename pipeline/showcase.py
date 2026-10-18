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
import base64
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shopify_api import Shopify  # noqa: E402

ALIAS = re.compile(r"^[A-Za-z0-9_. \-]{3,20}$")
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


# Offers: the shop (these profile ids) can make offers on cards in public binders.
OWNERS = set(filter(None, os.environ.get("OFFER_OWNERS", "2008058b30b5").split(",")))
ACTS = {"offer", "counter", "accept", "decline", "withdraw"}
BOXKEY = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
OID = re.compile(r"^[A-Za-z0-9_-]{6,40}$")


def _ev(e, by):
    """One sanitized step of an offer thread, or None."""
    if not isinstance(e, dict) or e.get("act") not in ACTS:
        return None
    try:
        t = int(e.get("t") or 0)
        a = int(e["a"]) if e.get("a") is not None else None
    except (TypeError, ValueError):
        return None
    if e["act"] in ("offer", "counter") and not (a and 0 < a <= 10_000_000):
        return None
    return {"by": by, "act": e["act"], "a": a, "kind": "credit" if e.get("kind") == "credit" else "cash",
            "m": re.sub(r"\s+", " ", str(e.get("m") or ""))[:200], "t": t}


def thread(shop_steps, collector_steps):
    """Merge both sides' steps by time and keep only moves that are legal at that point."""
    evs = [x for x in (_ev(e, "s") for e in shop_steps or []) if x] + [x for x in (_ev(e, "c") for e in collector_steps or []) if x]
    evs.sort(key=lambda e: (e["t"], e["by"] == "c"))
    out = []
    for e in evs:
        if not out:
            if e["by"] == "s" and e["act"] == "offer":
                out.append(e)
            continue
        last = out[-1]
        if last["act"] in ("accept", "decline", "withdraw"):
            break
        waiting = "c" if last["by"] == "s" else "s"      # whose turn it is
        if e["by"] == waiting and e["act"] in ("accept", "decline", "counter"):
            if e["act"] == "accept":
                e = {**e, "a": last["a"], "kind": last["kind"]}
            out.append(e)
        elif e["by"] == last["by"] and e["act"] == "withdraw":
            out.append(e)
    return out


def _seal(key, obj):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()
    iv = hashlib.sha256(key.encode() + b"|" + raw).digest()[:12]   # same content -> same file, so quiet runs don't commit
    ct = AESGCM(hashlib.sha256(key.encode()).digest()).encrypt(iv, raw, None)
    b = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")
    return {"v": 1, "iv": b(iv), "ct": b(ct)}


def write_offers(binders, data):
    """Each signed-in collector keeps a private inbox key ("box") in their binder. The shop's offers and the
    collector's replies are merged here and published encrypted with that key at data/box/<hash of key>.json,
    so only the two people involved can read them (the repo and the site are public)."""
    bdir = os.path.join(data, "box")
    if os.path.isdir(bdir):
        for f in os.listdir(bdir):
            os.remove(os.path.join(bdir, f))
    try:
        import cryptography  # noqa: F401
    except ImportError:
        print("::warning title=Offers::cryptography not installed; offers not published")
        return
    by_pid = {pid_of(gid): (gid, b) for gid, _, b in binders}
    shop_box, shop_wins, inbox, n = {}, {}, {}, 0
    for opid in OWNERS:
        if opid not in by_pid:
            continue
        ogid, ob = by_pid[opid]
        rows = []
        for o in (ob.get("offers") or [])[-300:]:
            if not isinstance(o, dict) or not OID.match(str(o.get("id") or "")) or o.get("to") not in by_pid or o["to"] in OWNERS:
                continue
            cgid, cb = by_pid[o["to"]]
            resp = (cb.get("oresp") or {}).get(o["id"]) if isinstance(cb.get("oresp"), dict) else None
            h = thread(o.get("h"), resp if isinstance(resp, list) else [])
            if not h:
                continue
            card = {"id": o.get("cid"), "g": o.get("g"), "n": str(o.get("n") or "")[:120], "gr": str(o.get("gr") or "")[:30] or None}
            inbox.setdefault(o["to"], []).append({"id": o["id"], "card": card, "h": h})
            rows.append({"id": o["id"], "to": o["to"], "alias": (cb.get("alias") or "")[:20], "cust": cgid.rsplit("/", 1)[-1], "card": card, "h": h})
            n += 1
        if BOXKEY.match(str(ob.get("box") or "")):
            shop_box[ob["box"]] = rows
            try:
                import giveaway
                wins = [{"month": w["month"], "alias": w["alias"], "cust": by_pid[w["pid"]][0].rsplit("/", 1)[-1] if w["pid"] in by_pid else ""}
                        for w in giveaway.winners()[-3:]]
            except Exception:
                wins = []
            shop_wins[ob["box"]] = wins
    os.makedirs(bdir, exist_ok=True)
    boxes = dict(shop_box)
    for pid, offers in inbox.items():
        key = by_pid[pid][1].get("box")
        if BOXKEY.match(str(key or "")) and key not in boxes:
            boxes[key] = offers
    for key, offers in boxes.items():
        name = hashlib.sha256(("dysbox:" + key).encode()).hexdigest()[:24]
        last = max((e["t"] for o in offers for e in o["h"]), default=0)
        with open(os.path.join(bdir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(_seal(key, {"updated": last, "offers": offers, **({"winners": shop_wins[key]} if key in shop_wins else {})}), f, separators=(",", ":"))
    print(f"offers: {n} threads, {len(boxes)} inboxes")


def write_demand(binders, data, rows):
    """Want lists -> data/wanted.json (public Most wanted) and data/demand.json (owner's report). Counts only, no names."""
    price = {f"{r[0]}|{code_of(sub_of(r[1]))}": (r[4], r[1], r[2]) for r in rows}
    try:
        stock = {s["id"]: s for s in json.load(open(os.path.join(data, "stock.json"))) if s.get("a")}
    except (OSError, ValueError):
        stock = {}
    agg, wanters = {}, 0
    for _, _, b in binders:
        seen = set()
        for w in b.get("want") or []:
            try:
                iid = int(w["id"])
            except (KeyError, TypeError, ValueError):
                continue
            k = w.get("k") if isinstance(w.get("k"), str) and w["k"].startswith(f"{iid}|") else f"{iid}|"
            if k in seen:
                continue
            seen.add(k)
            a = agg.setdefault(k, {"id": iid, "g": w.get("g"), "n": (w.get("n") or "")[:120], "c": 0, "maxes": []})
            a["c"] += 1
            if isinstance(w.get("max"), (int, float)) and w["max"] > 0:
                a["maxes"].append(int(w["max"]))
        wanters += 1 if seen else 0
    items = []
    for k, a in agg.items():
        m, name, g = price.get(k) or next((v for kk, v in price.items() if kk.startswith(f"{a['id']}|")), (None, a["n"], a["g"]))
        mx = sorted(a["maxes"])
        st = stock.get(a["id"])
        items.append({"id": a["id"], "g": g or a["g"], "n": name or a["n"], "c": a["c"], "m": m,
                      "mx": mx[len(mx) // 2] if mx else None, "nm": len(mx),
                      "st": {"p": st.get("p"), "u": st.get("u")} if st else None})
    items.sort(key=lambda i: (-i["c"], -(i["m"] or 0)))
    by_id = {}
    for i in items:
        by_id[str(i["id"])] = by_id.get(str(i["id"]), 0) + i["c"]
    top = [{"id": i["id"], "g": i["g"], "n": i["n"], "c": i["c"], "m": i["m"], "st": bool(i["st"])} for i in items[:30]]
    now = int(time.time() * 1000)
    with open(os.path.join(data, "wanted.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": now, "top": top, "all": by_id}, f, separators=(",", ":"), ensure_ascii=False)
    with open(os.path.join(data, "demand.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": now, "wanters": wanters, "items": items}, f, separators=(",", ":"), ensure_ascii=False)
    print(f"want lists: {wanters} collectors, {len(items)} items wanted")


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
        alias = re.sub(r"\s+", " ", (b.get("alias") or "").strip())
        if not b.get("pub") or pid in hidden or not ALIAS.match(alias) or BLOCK.search(alias):
            continue
        if alias.lower() in taken:
            alias = f"{alias} {pid[:3]}"
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

    write_demand(binders, data, rows)
    write_offers(binders, data)
    try:
        import giveaway
        giveaway.write_public(binders, data, pid_of)
    except Exception as err:
        print(f"::warning title=Giveaway::{str(err)[:300]}")
    with open(os.path.join(data, "showcase.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": int(time.time() * 1000), "profiles": profiles}, f, separators=(",", ":"), ensure_ascii=False)
    print(f"collectors: {len(profiles)} public binders out of {len(binders)} saved, {sum(likes.values())} likes, {sum(followers.values())} follows")


if __name__ == "__main__":
    main(sys.argv[1:])
