"""Discord feeds: watches our own store and our release feed and posts changes to Discord webhooks.

What it posts (names, dates, our own prices only; no TCGplayer prices):
  store     -> #new-arrivals: new products, back in stock, price drops of 10% or more
  releases  -> #upcoming-releases: newly added releases and moved dates
  digest    -> #upcoming-releases: the next 14 days of releases (weekly)

Safe by default:
  * no webhook URL in the environment  -> dry run (prints what it would post, changes nothing)
  * first real run                     -> saves a baseline and posts nothing
  * more than MAX_POSTS events at once -> posts a short summary instead of a flood
Webhook URLs are secrets: DISCORD_WEBHOOK_NEW_ARRIVALS and DISCORD_WEBHOOK_RELEASES.
"""
import argparse, json, os, sys, time, urllib.error, urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
import config  # noqa: E402

STORE = os.environ.get("FEEDS_STORE_URL", "https://driveyourstyle.net")
MARKET = os.environ.get("FEEDS_MARKET_URL", "https://market.driveyourstyle.net")
MAX_POSTS = 8            # per feed per run
DROP_PCT = 0.10          # price drop worth posting
CYAN, PURPLE, GOLD = 0x5EE7FF, 0xA78BFA, 0xF5B301
UA = "DriveYourStyleFeeds/1.0 (+https://driveyourstyle.net)"


# ---------- tiny HTTP helpers ----------
def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def post_webhook(url, payload):
    body = json.dumps(payload).encode()
    for attempt in range(4):
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            urllib.request.urlopen(req, timeout=30).read()
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    wait = float(json.load(e).get("retry_after", 2))
                except Exception:
                    wait = 2.0
                time.sleep(min(wait, 10) + 0.5)
                continue
            print(f"  webhook error {e.code}", file=sys.stderr)
            return False
        except Exception as e:  # network hiccup
            print(f"  webhook error {e}", file=sys.stderr)
            time.sleep(2)
    return False


# ---------- store monitor ----------
def fetch_products():
    out, page = [], 1
    while True:
        data = get_json(f"{STORE}/products.json?limit=250&page={page}")
        items = data.get("products", [])
        if not items:
            return out
        out.extend(items)
        if len(items) < 250:
            return out
        page += 1


def summarize(p):
    variants = p.get("variants") or []
    live = [v for v in variants if v.get("available")]
    prices = []
    for v in (live or variants):
        try:
            prices.append(float(v.get("price")))
        except (TypeError, ValueError):
            pass
    imgs = p.get("images") or []
    return {
        "title": p.get("title", ""),
        "handle": p.get("handle", ""),
        "type": p.get("product_type", ""),
        "available": bool(live),
        "price": min(prices) if prices else None,
        "image": imgs[0].get("src") if imgs else None,
    }


def money(x):
    return "n/a" if x is None else f"${x:,.2f}"


def store_embed(kind, s):
    labels = {"new": ("🆕 New arrival", CYAN), "back": ("🔁 Back in stock", PURPLE), "drop": ("💸 Price drop", GOLD)}
    head, color = labels[kind]
    emb = {
        "title": f"{head}: {s['title']}",
        "url": f"{STORE}/products/{s['handle']}",
        "color": color,
        "fields": [{"name": "Price", "value": money(s["price"]), "inline": True}],
        "footer": {"text": "Drive Your Style · driveyourstyle.net · Free Las Vegas pickup by arrangement"},
    }
    if s.get("type"):
        emb["fields"].append({"name": "Type", "value": s["type"], "inline": True})
    if kind == "drop" and s.get("was"):
        emb["fields"].append({"name": "Was", "value": money(s["was"]), "inline": True})
    if s.get("image"):
        emb["thumbnail"] = {"url": s["image"]}
    return emb


def diff_store(old, new):
    """old is None on the first run (baseline, no events)."""
    if old is None:
        return []
    events = []
    for pid, s in new.items():
        prev = old.get(pid)
        if prev is None:
            if s["available"]:
                events.append(("new", s))
        elif s["available"] and not prev.get("available"):
            events.append(("back", s))
        elif (s["available"] and prev.get("available") and s["price"] is not None
              and prev.get("price") and s["price"] <= prev["price"] * (1 - DROP_PCT)):
            events.append(("drop", dict(s, was=prev["price"])))
    return events


# ---------- release monitor ----------
def row_key(r):
    return f"{r.get('k')}|{r.get('n')}"


def pretty_date(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return d.strftime("%a %b ") + str(d.day)


def release_embed(kind, r, was=None):
    url = f"{MARKET}/set.html?id={r['id']}" if r.get("id") else f"{MARKET}/calendar.html"
    if kind == "new":
        title, color = f"📅 New release added: {r['n']}", CYAN
        desc = f"{r.get('g', '')} · {pretty_date(r['pub'])}"
    else:
        title, color = f"📅 Date moved: {r['n']}", GOLD
        desc = f"{r.get('g', '')} · now {pretty_date(r['pub'])} (was {pretty_date(was)})"
    return {"title": title, "url": url, "description": desc, "color": color,
            "footer": {"text": "DYS release calendar · market.driveyourstyle.net/calendar.html"}}


def diff_releases(old, rows, today):
    if old is None:
        return []
    events = []
    for r in rows:
        if not r.get("pub") or r["pub"] <= today:
            continue
        k = row_key(r)
        if k not in old:
            events.append(("new", r, None))
        elif old[k] != r["pub"]:
            events.append(("moved", r, old[k]))
    return events


def digest_embed(rows, today, days=14):
    end = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    soon = sorted([r for r in rows if r.get("pub") and today <= r["pub"] <= end], key=lambda r: (r["pub"], r["n"]))
    if not soon:
        return None
    lines, last = [], None
    for r in soon:
        if r["pub"] != last:
            lines.append(f"\n**{pretty_date(r['pub'])}**")
            last = r["pub"]
        lines.append(f"• {r['n']} ({r.get('g', '')})")
    return {"title": f"📅 Releases in the next {days} days", "description": "\n".join(lines).strip(),
            "url": f"{MARKET}/calendar.html", "color": CYAN,
            "footer": {"text": "Full calendar: market.driveyourstyle.net/calendar.html"}}


# ---------- runner ----------
def load_state(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return {}


def send(webhook, embeds, live, label):
    """Send one message per embed (capped). Returns number sent."""
    sent = 0
    over = max(0, len(embeds) - MAX_POSTS)
    for emb in embeds[:MAX_POSTS]:
        payload = {"embeds": [emb], "allowed_mentions": {"parse": []}}
        if live:
            if post_webhook(webhook, payload):
                sent += 1
            time.sleep(1.2)
        else:
            print(f"[dry-run:{label}] " + json.dumps(emb, ensure_ascii=False))
            sent += 1
    if over:
        msg = {"content": f"…and {over} more. See everything at {STORE}", "allowed_mentions": {"parse": []}}
        if live:
            post_webhook(webhook, msg)
        else:
            print(f"[dry-run:{label}] {msg['content']}")
    return sent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["store", "releases", "digest", "all"])
    ap.add_argument("--state", default="feeds-state/state.json")
    ap.add_argument("--dry-run", action="store_true", help="never post or save, even if webhook URLs are set")
    ap.add_argument("--sample", type=int, default=0, help="dry run only: show N existing products/releases as if new")
    ap.add_argument("--today", default=None, help="override today's date (YYYY-MM-DD), for tests")
    a = ap.parse_args()

    hook_store = os.environ.get("DISCORD_WEBHOOK_NEW_ARRIVALS", "").strip()
    hook_rel = os.environ.get("DISCORD_WEBHOOK_RELEASES", "").strip()
    today = a.today or date.today().isoformat()
    state = load_state(a.state)
    changed = False

    if a.mode in ("store", "all"):
        live = bool(hook_store) and not a.dry_run
        new = {str(p["id"]): summarize(p) for p in fetch_products()}
        if a.sample:
            for s in list(new.values())[:a.sample]:
                print("[sample:store] " + json.dumps(store_embed("new", s), ensure_ascii=False))
        old = state.get("store")
        events = diff_store(old, new)
        print(f"store: {len(new)} products, {len(events)} events" + ("" if old is not None else " (baseline run, nothing posted)"))
        send(hook_store, [store_embed(k, s) for k, s in events], live, "store")
        if live and new:
            state["store"] = new
            changed = True

    if a.mode in ("releases", "all"):
        live = bool(hook_rel) and not a.dry_run
        rows = get_json(f"{MARKET}/data/upcoming.json")
        if a.sample:
            for r in rows[:a.sample]:
                print("[sample:release] " + json.dumps(release_embed("new", r), ensure_ascii=False))
        old = state.get("releases")
        events = diff_releases(old, rows, today)
        print(f"releases: {len(rows)} rows, {len(events)} events" + ("" if old is not None else " (baseline run, nothing posted)"))
        send(hook_rel, [release_embed(k, r, w) for k, r, w in events], live, "releases")
        if live and rows:
            state["releases"] = {row_key(r): r.get("pub") for r in rows}
            changed = True

    if a.mode == "digest":
        live = bool(hook_rel) and not a.dry_run
        rows = get_json(f"{MARKET}/data/upcoming.json")
        emb = digest_embed(rows, today)
        print("digest: " + ("nothing in the next 14 days" if not emb else "ready"))
        if emb:
            send(hook_rel, [emb], live, "digest")

    if changed:
        os.makedirs(os.path.dirname(a.state) or ".", exist_ok=True)
        state["updated"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        json.dump(state, open(a.state, "w"), indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
