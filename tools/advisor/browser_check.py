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
import time
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

DIR, HOLD = sys.argv[1], json.load(open(sys.argv[2]))
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8779
MOCK = json.load(open(f"{DIR}/mock-relay.json"))
checks, fails = 0, []
calls = {"n": 0, "keys": {}}


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
        calls["keys"][key_of(req.url)] = calls["keys"].get(key_of(req.url), 0) + 1
        if mode["m"] == "denied" or req.headers.get("x-edge-pass") != "test-pass":
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
EST = sum(161 if h["kind"] == "Graded" else 90 if h["kind"] == "Sealed" else 210 for h in HOLD)


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
    ok(order[:3] == ["t-home", "t-adv", "t-buy"], f"{tag}: command center, then the action list and buying leads {order}")
    # what to consider buying: the watched card at its price, labelled as not checked against sold prices
    buy = page.inner_text("#t-buy")
    ok("What to consider buying" in buy and umb["n"].split(" - ")[0] in buy and "Not checked against sold prices yet" in buy, f"{tag}: buying lead labelled {buy[:200]!r}")
    ok("Leafeon" not in buy, f"{tag}: a watched card above its target isn't listed")
    ok("BUY candidate" in buy and "Deal check" in buy, f"{tag}: points at the Deal check for a BUY call")
    store0 = page.evaluate("() => JSON.stringify(Object.keys(localStorage).sort())")
    # the cost is shown before anything is spent, and a review needs a second, explicit tap
    est = page.inner_text("#t-adv .adv-est")
    ok(f"Up to about {EST:,} credits for {len(HOLD)} items" in est, f"{tag}: estimate before reviewing {est!r} vs {EST}")
    n0 = calls["n"]
    page.click("#t-adv .adv-go")
    ask = page.inner_text("#t-adv .adv-ask")
    ok(f"Review {len(HOLD)} holdings?" in ask and f"{EST:,} credits" in ask and page.query_selector("#t-adv .adv-yes"), f"{tag}: confirm shows the cost {ask!r}")
    page.click("#t-adv .adv-no")
    page.wait_for_timeout(300)
    ok(calls["n"] == n0 and not page.query_selector("#t-adv .adv-row") and page.is_hidden("#t-adv .adv-ask"), f"{tag}: Cancel spends nothing")
    page.click("#t-adv .adv-go")
    calls["keys"] = {}
    page.dblclick("#t-adv .adv-yes")      # a double tap starts one review, not two
    page.wait_for_function("() => /Reviewed \\d+ of \\d+/.test(document.querySelector('#t-adv .adv-st')?.textContent || '')", timeout=30000)
    if mode != "offline":
        multi = {str(h["id"]) for h in HOLD if sum(1 for y in HOLD if y["id"] == h["id"]) > 1}   # a card held raw and as a slab is read once for each
        dup = {k: v for k, v in calls["keys"].items() if v > (2 if any(f"|{i}" in k or f"syn-{i}/" in k for i in multi) else 1)}
        ok(not dup, f"{tag}: no provider call made twice in one review {list(dup.items())[:3]}")
        log = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-v1')).advLog")
        ok(isinstance(log, list) and len(log) == 1 and set(log[0]) == {"at", "day", "n", "cr", "full"} and log[0]["n"] == len(HOLD) and log[0]["full"], f"{tag}: review log keeps only time, count and credits {log}")
        # asking again right away warns that it was just done
        page.click("#t-adv .adv-go")
        ask = page.inner_text("#t-adv .adv-ask")
        ok("You already reviewed your holdings at" in ask and "Review again anyway" in ask, f"{tag}: a repeat warns {ask!r}")
        page.click("#t-adv .adv-no")
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
    ok(signed(EXP["sellProfit"]) in sumtxt and "eBay at the sold prices checked" in sumtxt, f"{tag}: sell total {sumtxt!r} vs {signed(EXP['sellProfit'])}")
    for sec, words in (("sell", "Worth selling"), ("grade", "May be worth grading"), ("monitor", "Monitor"), ("hold", "Hold"), ("data", "Not enough data")):
        if EXP["counts"][sec]:
            ok(page.query_selector(f"#adv-{sec}") and words in page.inner_text(f"#adv-{sec}"), f"{tag}: section {sec}")
    junk_free(page, "#t-adv", f"{tag} Today")
    if page.query_selector("#t-grade:not([hidden]) .list"):
        ok("$" not in page.inner_text("#t-grade .list"), f"{tag}: grading ideas on Today show no unchecked profit")
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
    # stored: only the saved calls (our own calls, ranges, counts) under one new key; no sold-price data; ledger untouched
    store1 = page.evaluate("() => JSON.stringify(Object.keys(localStorage).sort())")
    ok(sorted(set(json.loads(store1)) - set(json.loads(store0))) == ["dys-edge-advice"] and set(json.loads(store0)) <= set(json.loads(store1)), f"{tag}: one new storage key {store1}")
    saved = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-advice'))")
    allowed = {"key", "name", "kind", "qty", "cost", "cond", "grade", "book", "action", "why", "band", "ev", "bestName", "bestAssumed", "fp", "at"}
    ok(saved["v"] == 1 and len(saved["rows"]) == len(HOLD), f"{tag}: one saved call per holding ({len(saved['rows'])})")
    for r in saved["rows"]:
        e = EXPK.get(r["key"], {})
        ok(set(r) <= allowed and (r["ev"] is None or set(r["ev"]) <= {"n30", "n90", "capped", "age"}), f"{tag}: {r['key']} saved fields {sorted(set(r) - allowed)}")
        ok(r["action"] == e.get("action"), f"{tag}: {r['key']} saved call {r['action']} vs {e.get('action')}")
        ok("$" not in (r["why"] or ""), f"{tag}: {r['key']} saved reason has no amount {r['why']!r}")
        nums = {v for v in (e.get("ref"), e.get("profitNow"), e.get("gradeProfit"), (e.get("best") or {}).get("profit"), (e.get("best") or {}).get("price")) if v}
        found = set(re.findall(r"-?\d+", json.dumps({k: v for k, v in r.items() if k not in ("cost", "at", "fp", "key", "qty")})))
        ok(not ({str(n) for n in nums} & found), f"{tag}: {r['key']} saved row holds an exact sold amount {nums & {int(x) for x in found}}")
    blob = page.evaluate("() => Object.values(localStorage).join(' ')")
    ok("sold median" not in blob and "comps" not in blob and "valued at" not in blob, f"{tag}: no sold-price data stored")
    ok('"action"' not in page.evaluate("() => localStorage.getItem('dys-edge-v1')"), f"{tag}: saved calls aren't in the backup file's data")
    led = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-ledger')).T.items")
    ok(len(led) == len(items) and all(a["price"] == b["price"] and a["qty"] == b["qty"] for a, b in zip(sorted(led, key=lambda x: x["id"]), sorted(items, key=lambda x: x["id"]))), f"{tag}: ledger items unchanged")
    # a reload (a real one) shows the saved calls at no cost: same calls, ranges instead of amounts
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
    page.reload()
    page.wait_for_selector("#t-adv .adv-kept", timeout=15000)
    n2 = calls["n"]
    acts = dict(page.eval_on_selector_all("#t-adv .adv-row", "rs => rs.map(r => [r.dataset.key, r.dataset.act])"))
    ok(acts == {k: v["action"] for k, v in EXPK.items()}, f"{tag}: after a reload the saved calls show {acts}")
    kept = page.inner_text("#t-adv .adv-kept")
    ok("kept on this phone until" in kept and "exact sold prices aren't stored" in kept, f"{tag}: saved calls are labelled {kept!r}")
    ok(page.inner_text("#t-adv .adv-go").strip() == "Review all again", f"{tag}: nothing left to check after a reload")
    rows2 = page.eval_on_selector_all("#t-adv .adv-row", "rs => rs.map(r => ({ key: r.dataset.key, act: r.dataset.act, rt: r.querySelector('.adv-rt').innerText, txt: r.innerText }))")
    for r in rows2:
        e = EXPK[r["key"]]
        ok("valued at" not in r["txt"] and "Best estimate" not in r["txt"], f"{tag}: {r['key']} saved row shows no sold value")
        if e["action"] == "data":
            ok("no value" in r["rt"] and "$" not in r["rt"], f"{tag}: {r['key']} saved data row has no value")
        else:
            exact = signed(e["gradeProfit"] if e["action"] == "grade" else e["profitNow"])
            ok(exact not in r["rt"] and "range" in r["rt"] and (" to " in r["rt"] or "or more" in r["rt"] or "loss over" in r["rt"]), f"{tag}: {r['key']} saved row shows a range {r['rt']!r}")
            if e["best"]:
                ok(f"Best place to sell: {e['best']['name']}" in r["txt"], f"{tag}: {r['key']} saved best place")
    junk_free(page, "#t-adv", f"{tag} Today (saved)")
    if width == 390 and theme == "dark":
        page.screenshot(path="/tmp/pv/09-saved-calls.png")
    ok("Last full review today at" not in page.inner_text("#t-adv .adv-est"), f"{tag}: no duplicate last-review line with results showing")
    page.click("#t-adv .adv-go")
    ok("You already reviewed your holdings at" in page.inner_text("#t-adv .adv-ask"), f"{tag}: after a reload a repeat still warns")
    page.click("#t-adv .adv-no")
    page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
    page.wait_for_selector("#inv-adv .adv-tiles", timeout=15000)
    chips = page.eval_on_selector_all("#m-body .list .own-res .chip", "cs => cs.map(c => c.textContent)")
    ok(len(chips) == len(HOLD), f"{tag}: Inventory chips come back from saved calls ({len(chips)})")
    ok(calls["n"] == n2, f"{tag}: revisiting Today and Inventory spent nothing ({calls['n'] - n2} calls)")
    # a holding whose cost changed loses its saved call (only that one)
    first = items[0]["id"]
    page.evaluate("(id) => { const L = JSON.parse(localStorage.getItem('dys-edge-ledger')); L.T.items.find((x) => x.id === id).price += 100; localStorage.setItem('dys-edge-ledger', JSON.stringify(L)); }", first)
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.reload()
    page.wait_for_selector("#t-adv .adv-kept", timeout=15000)
    ok(page.inner_text("#t-adv .adv-go").strip() == "Check 1 unchecked holding", f"{tag}: an edited holding needs a new check {page.inner_text('#t-adv .adv-go')!r}")
    page.evaluate("(id) => { const L = JSON.parse(localStorage.getItem('dys-edge-ledger')); L.T.items.find((x) => x.id === id).price -= 100; localStorage.setItem('dys-edge-ledger', JSON.stringify(L)); }", first)
    # changing a selling setting (ROI target) clears them; so does the 12-hour limit; so does Clear
    page.evaluate("() => { const s = JSON.parse(localStorage.getItem('dys-edge-v1')); s.set.roi = 25; localStorage.setItem('dys-edge-v1', JSON.stringify(s)); }")
    page.reload(); page.wait_for_selector("#t-adv .adv-go", timeout=15000)
    ok(not page.query_selector("#t-adv .adv-kept") and "Review my" in page.inner_text("#t-adv .adv-go") and page.evaluate("() => localStorage.getItem('dys-edge-advice')") is None, f"{tag}: a new ROI target clears saved calls")
    page.evaluate("(sv) => { const s = JSON.parse(localStorage.getItem('dys-edge-v1')); s.set.roi = 20; localStorage.setItem('dys-edge-v1', JSON.stringify(s)); localStorage.setItem('dys-edge-advice', JSON.stringify(sv)); }", saved)
    page.reload(); page.wait_for_selector("#t-adv .adv-kept", timeout=15000)
    page.click("#t-adv .adv-forget"); page.wait_for_timeout(300)
    ok(not page.query_selector("#t-adv .adv-kept") and page.evaluate("() => localStorage.getItem('dys-edge-advice')") is None, f"{tag}: Clear saved calls removes them")
    old = dict(saved, rows=[dict(r, at=r["at"] - 12 * 3600 * 1000 - 60000) for r in saved["rows"]])
    page.evaluate("(sv) => localStorage.setItem('dys-edge-advice', JSON.stringify(sv))", old)
    page.reload(); page.wait_for_selector("#t-adv .adv-go", timeout=15000)
    ok(not page.query_selector("#t-adv .adv-row") and page.evaluate("() => localStorage.getItem('dys-edge-advice')") is None, f"{tag}: saved calls expire after 12 hours")
    ok(calls["n"] == n2, f"{tag}: none of this spent anything")


def main():
    srv = serve()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for width, theme, mode in [(390, "dark", "ok"), (360, "light", "ok"), (430, "dark", "ok"), (390, "light", "offline"), (390, "dark", "unpaired"),
                                      (390, "dark", "cap"), (390, "dark", "denied"), (390, "dark", "stop")]:
                ctx = br.new_context()
                calls["n"] = 0
                seed = dict(SEED, advLog=[{"at": int(time.time() * 1000) - 3600e3, "day": time.strftime("%Y-%m-%d"), "n": 14, "cr": 9000, "full": False}]) if mode == "cap" else SEED
                relay_cfg = "" if mode == "unpaired" else "localStorage.setItem('dys-edge-relay', JSON.stringify({ relay: 'https://relay.test', pass: 'test-pass' }));"
                ctx.add_init_script(f"""if (!sessionStorage.getItem('seeded')) {{ sessionStorage.setItem('seeded', '1');
                  localStorage.clear(); localStorage.setItem('dys-theme', '{theme}');
                  localStorage.setItem('dys-edge-v1', {json.dumps(json.dumps(seed))});
                  localStorage.setItem('dys-edge-ledger', {json.dumps(json.dumps(LEDGER))}); {relay_cfg} }}""")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                m = {"m": mode if mode in ("offline", "denied") else "ok"}
                page.route("https://relay.test/**", relay(m))
                page.route("https://script.google.com/**", lambda r: r.abort())
                if mode == "unpaired":
                    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
                    page.wait_for_selector("#t-adv .adv-go", timeout=15000)
                    txt = page.inner_text("#t-adv")
                    ok(page.is_disabled("#t-adv .adv-go") and "aren't set up on this phone" in txt and "no credits are used" in txt, "unpaired: review is off and says how to set it up")
                    ok(not page.query_selector("#t-adv .adv-row") and not page.query_selector("#t-adv .adv-yes"), "unpaired: no actions, nothing to confirm")
                    ok("What to consider buying" in page.inner_text("#view") and page.query_selector("#t-port .tiles"), "unpaired: the rest of Today still works")
                    page.screenshot(path="/tmp/pv/08-unpaired.png", full_page=False)
                    page.click("#t-adv .adv-pair")
                    page.wait_for_selector("#rl-pair", timeout=8000)
                    ok("Pair this phone" in page.inner_text("#rl-pair"), "unpaired: Go to Settings opens pairing")
                    page.click("#m-seg >> text=Inventory")
                    page.wait_for_selector("#inv-adv .adv-go", timeout=15000)
                    ok(page.is_disabled("#inv-adv .adv-go") and len(page.query_selector_all("#m-body .list .row")) == len(HOLD), "unpaired: Inventory still lists every holding, review off")
                    ok(calls["n"] == 0, "unpaired: no relay calls")
                elif mode == "cap":
                    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
                    page.wait_for_selector("#t-adv .adv-go", timeout=15000)
                    page.click("#t-adv .adv-go")
                    ask = page.inner_text("#t-adv .adv-ask")
                    ok("Today's review limit is reached" in ask and not page.query_selector("#t-adv .adv-yes"), f"cap: blocked {ask[:120]!r}")
                    page.screenshot(path="/tmp/pv/07-cap.png", full_page=False)
                    ok(calls["n"] == 0, "cap: no relay calls")
                elif mode == "denied":
                    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
                    page.wait_for_selector("#t-adv .adv-go", timeout=15000)
                    n0 = calls["n"]; page.click("#t-adv .adv-go"); page.click("#t-adv .adv-yes")
                    page.wait_for_function("() => /Reviewed \\d+ of \\d+/.test(document.querySelector('#t-adv .adv-st')?.textContent || '')", timeout=30000)
                    acts = page.eval_on_selector_all("#t-adv .adv-row", "rs => rs.map(r => r.dataset.act)")
                    ok(set(acts) == {"data"} and len(acts) == len(HOLD) and "refused" in page.inner_text("#t-adv"), f"denied: every holding NOT ENOUGH DATA, says why {set(acts)}")
                    ok(calls["n"] - n0 == 1, f"denied: stops after the first refusal ({calls['n'] - n0} calls)")
                    ok("$" not in "".join(page.eval_on_selector_all("#t-adv .adv-rt", "rs => rs.map(r => r.innerText)")), "denied: no money shown")
                    ok(page.evaluate("() => (JSON.parse(localStorage.getItem('dys-edge-v1')).advLog || []).length") == 0, "denied: nothing spent, nothing logged")
                elif mode == "stop":
                    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
                    page.wait_for_selector("#t-adv .adv-go", timeout=15000)
                    page.click("#t-adv .adv-go"); page.click("#t-adv .adv-yes")
                    page.click("#t-adv .adv-stop")
                    page.wait_for_function("() => /Stopped: \\d+ items? not checked/.test(document.querySelector('#t-adv .adv-st')?.textContent || '')", timeout=30000)
                    st = page.inner_text("#t-adv .adv-st")
                    m2 = re.search(r"Reviewed (\d+) of (\d+)", st)
                    left = len(HOLD) - int(m2.group(1))
                    ok(0 < int(m2.group(1)) < len(HOLD), f"stop: stopped part way {st!r}")
                    ok(page.inner_text("#t-adv .adv-go").strip() == f"Check {left} unchecked holding{'s' if left != 1 else ''}", f"stop: the button offers only the rest {page.inner_text('#t-adv .adv-go')!r}")
                    est2 = page.inner_text("#t-adv .adv-est")
                    ok(f"for {left} item" in est2, f"stop: estimate covers only the rest {est2!r}")
                    page.screenshot(path="/tmp/pv/06-stopped.png", full_page=False)
                    log = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-v1')).advLog")
                    ok(len(log) == 1 and not log[0]["full"], f"stop: a stopped review isn't counted as a full one {log}")
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
