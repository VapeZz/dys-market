"""Browser checks for the Holdings Advisor and Today's action list (P3/P4) in the real Edge app, on a local site copy,
with a synthetic PkmnPrices relay (tools/deal/make_fixture.js) answered inside the browser and a synthetic ledger.
Nothing is published; no real API, relay or Sheet is called.
    node tools/deal/make_fixture.js /tmp/advsite 23821 23237 604 && python3 tools/advisor/browser_check.py /tmp/advsite /tmp/adv_holdings.json
"""
import functools
import http.server
import json
import os
import re
import subprocess
import sys
import threading
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

DIR, HOLD = sys.argv[1], json.load(open(sys.argv[2]))
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8779
MOCK = json.load(open(f"{DIR}/mock-relay.json"))
checks, fails = 0, []
calls = {"n": 0}


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)
        print("FAIL", what)


def key_of(url):  # same rule as tools/deal/mock_relay.js
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if "tcg_player_id" in q:
        return f"{u.path}|{q['tcg_player_id']}"
    if u.path == "/v1/sealed":
        return f"{u.path}|*"
    if u.path.endswith("/listings/ebay"):
        return f"{u.path}|" + ("sealed" if u.path.startswith("/v1/sealed") else (f"true{q.get('grade')}" if q.get("graded") == "true" else "false"))
    return u.path


CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "X-Edge-Pass, Accept", "Access-Control-Expose-Headers": "x-credits-charged"}


def relay(mode):
    def h(route):
        req = route.request
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        if mode["m"] == "offline":
            return route.abort()
        calls["n"] += 1
        if req.headers.get("x-edge-pass") != "test-pass":
            return route.fulfill(status=401, headers=CORS, body="denied")
        status, body = MOCK["routes"].get(key_of(req.url), [404, {"error": "not found"}])
        n = max(1, len((body or {}).get("data") or []) if isinstance(body, dict) else 1)
        return route.fulfill(status=status, headers={**CORS, "Content-Type": "application/json", "x-credits-charged": str(n)}, body=json.dumps(body))
    return h


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=DIR))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def money(c):
    return f"{'−' if c < 0 else ''}${abs(c) / 100:,.2f}"


def signed(c):
    return ("+" if c >= 0 else "") + money(c)


# the synthetic ledger: one item per holding (ids i1..), held, no sales
names = {}
for g in (23821, 23237, 604):
    for it in json.load(open(f"{DIR}/data/set/{g}.json"))["items"]:
        names[it["id"]] = it["n"]
items = []
for h in HOLD:
    iid = h["key"].split(":")[0]
    items.append({"id": iid, "buy": "", "day": "2026-11-01", "book": "Business", "kind": h["kind"], "tcg": h["id"], "g": h["g"], "n": names[h["id"]], "name": names[h["id"]], "set": "",
                  "cond": h.get("cond", "") if h["kind"] == "Raw" else "", "grader": h.get("grader", ""), "grade": h.get("grade", ""), "cert": "", "qty": h.get("qty", 1),
                  "price": h["cost"], "status": "", "note": "SYNTH"})
LEDGER = {"v": 1, "T": {"buys": [], "items": items, "sales": [], "costs": [], "cash": []}, "q": [], "pulled": 0, "err": "", "migrated": True, "sheet": ""}
# a watched card at its target (market under target) and one that isn't
umb = next(it for it in json.load(open(f"{DIR}/data/set/23821.json"))["items"] if it["id"] == 610516)
leaf = next(it for it in json.load(open(f"{DIR}/data/set/23821.json"))["items"] if it["id"] == 610499)
WATCH = [{"id": 610516, "g": 23821, "n": umb["n"], "target": umb["p"] + 100, "at": "2026-11-10"}, {"id": 610499, "g": 23821, "n": leaf["n"], "target": 100, "at": "2026-11-10"}]
SEED = {"inv": [], "watch": WATCH, "set": {"platform": "ebay"}}
hold_in = [{**h, "key": h["key"].split(":")[0]} for h in HOLD]
EXP = json.loads(subprocess.check_output(["node", os.path.join(HERE, "expect.js"), DIR, json.dumps(hold_in)]))
EXPK = {x["key"]: x for x in EXP["items"]}


def junk_free(page, sel, where):
    html = page.inner_html(sel)
    ok(not re.search(r"undefined|NaN|\bnull\b|Infinity|\[object", html), f"{where}: a missing value printed")
    w = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    ok(w[0] <= w[1], f"{where}: sideways scroll {w}")


def run(page, width, theme, mode):
    tag = f"{width}px {theme}"
    page.set_viewport_size({"width": width, "height": 860})
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
    page.wait_for_selector("#t-adv .adv-go", timeout=15000)
    body0 = page.inner_text("#view")
    ok("Best flips right now" not in body0, f"{tag}: the disproven lowest-listing flips are gone from Today")
    ok(page.inner_text("#t-adv .adv-go").strip() == f"Review my {len(HOLD)} holdings", f"{tag}: review button {page.inner_text('#t-adv .adv-go')!r}")
    ok(not page.query_selector("#t-adv .adv-row"), f"{tag}: no actions shown before a review (nothing guessed)")
    order = page.evaluate("() => [...document.querySelectorAll('#view > section')].map(s => s.id || s.className).slice(0, 3)")
    ok(order[:2] == ["t-adv", "t-buy"], f"{tag}: action list and buying leads come first {order}")
    # what to consider buying: the watched card at its price, labelled as not checked against sold prices
    buy = page.inner_text("#t-buy")
    ok("What to consider buying" in buy and umb["n"].split(" - ")[0] in buy and "Not checked against sold prices yet" in buy, f"{tag}: buying lead labelled {buy[:200]!r}")
    ok("Leafeon" not in buy, f"{tag}: a watched card above its target isn't listed")
    ok("BUY candidate" in buy and "Deal check" in buy, f"{tag}: points at the Deal check for a BUY call")
    store0 = page.evaluate("() => JSON.stringify(Object.keys(localStorage).sort())")
    n0 = calls["n"]
    page.click("#t-adv .adv-go")
    page.wait_for_function("() => /Reviewed \\d+ of \\d+/.test(document.querySelector('#t-adv .adv-st')?.textContent || '')", timeout=30000)
    st = page.inner_text("#t-adv .adv-st")
    ok(f"Reviewed {len(HOLD)} of {len(HOLD)}" in st and re.search(r"[\d,]+ credits", st), f"{tag}: status {st!r}")
    if mode == "offline":
        acts = page.eval_on_selector_all("#t-adv .adv-row", "rs => rs.map(r => r.dataset.act)")
        ok(len(acts) == len(HOLD) and set(acts) == {"data"}, f"{tag} offline: every holding is NOT ENOUGH DATA {set(acts)}")
        ok("No connection to the sold-price relay" in page.inner_text("#t-adv"), f"{tag} offline: says why")
        return
    ok(calls["n"] > n0, f"{tag}: the review read sold prices through the relay")
    tiles = dict(page.eval_on_selector_all("#t-adv .adv-tile", "ts => ts.map(t => [t.dataset.jump, +t.querySelector('b').textContent])"))
    ok(tiles == EXP["counts"], f"{tag}: action counts {tiles} vs {EXP['counts']}")
    rows = page.eval_on_selector_all("#t-adv .adv-row", "rs => rs.map(r => ({ key: r.dataset.key, act: r.dataset.act, rt: r.querySelector('.adv-rt').innerText, txt: r.innerText, open: r.dataset.open }))")
    ok(len(rows) == len(HOLD) and len({r["key"] for r in rows}) == len(HOLD), f"{tag}: each holding listed once ({len(rows)})")
    for r in rows:
        e = EXPK.get(r["key"])
        if not e:
            ok(False, f"{tag}: unexpected row {r['key']}"); continue
        ok(r["act"] == e["action"], f"{tag}: {r['key']} action {r['act']} vs {e['action']}")
        if e["action"] == "data":
            ok("no value" in r["rt"] and "$" not in r["rt"] and "Best estimate" not in r["txt"] and "valued at" not in r["txt"], f"{tag}: {r['key']} NOT ENOUGH DATA shows no number {r['rt']!r}")
        elif e["action"] == "grade":
            ok(signed(e["gradeProfit"]) in r["rt"] and "if graded" in r["rt"] and "bets on the grade" in r["txt"], f"{tag}: {r['key']} grade row {r['rt']!r}")
        else:
            ok(signed(e["profitNow"]) in r["rt"] and "eBay, at sold prices" in r["rt"], f"{tag}: {r['key']} profit at sold prices {r['rt']!r} vs {signed(e['profitNow'])}")
            if e["best"]:
                ok(f"Best estimate: {e['best']['name']}" in r["txt"] and signed(e["best"]["profit"]) in r["txt"], f"{tag}: {r['key']} best option {e['best']}")
            ok(f"valued at {money(e['ref'])}" in r["txt"], f"{tag}: {r['key']} shows its sold reference")
        ok(r["open"] is not None, f"{tag}: {r['key']} opens its card")
    sumtxt = page.inner_text("#t-adv .adv-sum") if page.query_selector("#t-adv .adv-sum") else ""
    ok(signed(EXP["sellProfit"]) in sumtxt and "eBay at today's sold prices" in sumtxt, f"{tag}: sell total {sumtxt!r} vs {signed(EXP['sellProfit'])}")
    for sec, words in (("sell", "Worth selling"), ("grade", "May be worth grading"), ("monitor", "Monitor"), ("hold", "Hold"), ("data", "Not enough data")):
        if EXP["counts"][sec]:
            ok(page.query_selector(f"#adv-{sec}") and words in page.inner_text(f"#adv-{sec}"), f"{tag}: section {sec}")
    junk_free(page, "#t-adv", f"{tag} Today")
    if width == 390 and theme == "dark":
        page.screenshot(path="/tmp/adv_today.png", full_page=True)
    # tap a tile: scrolls to its section; tap a row: opens the card sheet
    page.click("#t-adv .adv-tile[data-jump=sell]")
    first = rows[0]
    page.click(f"#t-adv .adv-row[data-key='{first['key']}'] .adv-n")
    page.wait_for_selector(".sheet, #sheet, [role=dialog]", timeout=8000)
    ok(True, f"{tag}: a row opens its card")
    page.keyboard.press("Escape")
    # Inventory: the same review, compact (tiles + per-row chips), without a second review
    n1 = calls["n"]
    page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
    page.wait_for_selector("#inv-adv .adv-tiles", timeout=15000)
    t2 = dict(page.eval_on_selector_all("#inv-adv .adv-tile", "ts => ts.map(t => [t.dataset.jump, +t.querySelector('b').textContent])"))
    ok(t2 == EXP["counts"], f"{tag}: Inventory shows the same counts {t2}")
    ok(not page.query_selector("#inv-adv .adv-row"), f"{tag}: Inventory is compact (no duplicate list)")
    chips = page.eval_on_selector_all("#m-body .list .own-res .chip", "cs => cs.map(c => c.textContent)")
    ok(len(chips) == len(HOLD), f"{tag}: every Inventory row carries its call ({len(chips)})")
    ok(calls["n"] == n1, f"{tag}: switching tabs made no new relay calls")
    junk_free(page, "#m-body", f"{tag} Inventory")
    # nothing stored: no new keys, no sold-price data on the phone, ledger untouched
    store1 = page.evaluate("() => JSON.stringify(Object.keys(localStorage).sort())")
    ok(store0 == store1, f"{tag}: no new storage keys {store1}")
    blob = page.evaluate("() => Object.values(localStorage).join(' ')")
    ok("sold median" not in blob and "adv" not in json.dumps([k for k in json.loads(store1)]), f"{tag}: no advisor or sold-price data stored")
    led = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-ledger')).T.items")
    ok(len(led) == len(items) and all(a["price"] == b["price"] and a["qty"] == b["qty"] for a, b in zip(sorted(led, key=lambda x: x["id"]), sorted(items, key=lambda x: x["id"]))), f"{tag}: ledger items unchanged")
    # reload forgets the review (memory only); a hash change alone is the same page, so reload for real
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
    page.reload()
    page.wait_for_selector("#t-adv .adv-go", timeout=15000)
    ok(not page.query_selector("#t-adv .adv-row") and "Review my" in page.inner_text("#t-adv .adv-go"), f"{tag}: a reload forgets the review")


def main():
    srv = serve()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for width, theme, mode in [(390, "dark", "ok"), (360, "light", "ok"), (430, "dark", "ok"), (390, "light", "offline"), (390, "dark", "unpaired")]:
                ctx = br.new_context()
                relay_cfg = "" if mode == "unpaired" else "localStorage.setItem('dys-edge-relay', JSON.stringify({ relay: 'https://relay.test', pass: 'test-pass' }));"
                ctx.add_init_script(f"""if (!sessionStorage.getItem('seeded')) {{ sessionStorage.setItem('seeded', '1');
                  localStorage.clear(); localStorage.setItem('dys-theme', '{theme}');
                  localStorage.setItem('dys-edge-v1', {json.dumps(json.dumps(SEED))});
                  localStorage.setItem('dys-edge-ledger', {json.dumps(json.dumps(LEDGER))}); {relay_cfg} }}""")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                m = {"m": "offline" if mode == "offline" else "ok"}
                page.route("https://relay.test/**", relay(m))
                page.route("https://script.google.com/**", lambda r: r.abort())
                if mode == "unpaired":
                    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
                    page.wait_for_selector("#t-adv .adv-go", timeout=15000)
                    ok(page.is_disabled("#t-adv .adv-go") and "Set up sold prices" in page.inner_text("#t-adv"), "unpaired: review is off and says how to set it up")
                else:
                    run(page, width, theme, mode)
                ok(not errors, f"{width}px {mode}: page errors {errors[:3]}")
                ctx.close()
            br.close()
    finally:
        srv.shutdown()
    print(f"{checks - len(fails)} of {checks} advisor browser checks passed")
    sys.exit(1 if fails else 0)


main()
