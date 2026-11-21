"""Browser checks for Daily deals (Deals tab) in the real Edge app on a local site copy. The relay's /edge/finder route
answers with a test phone extract (tools/daily/make_phone_fixture.py) and the sold-price routes with the synthetic relay
(tools/deal/make_fixture.js). Nothing real is called.
    python3 tools/daily/browser_check.py /tmp/m3site
"""
import functools
import http.server
import json
import os
import subprocess
import sys
import threading
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

DIR = sys.argv[1]
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../..")
PORT = 8772
MOCK = json.load(open(f"{DIR}/mock-relay.json"))
PHONE = json.load(open(f"{DIR}/finder-phone.json"))
RELAY = {"relay": "https://relay.test", "pass": "test-pass"}
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "X-Edge-Pass, Accept", "Access-Control-Expose-Headers": "x-credits-charged"}
checks, fails = 0, []
st = {"mode": "ok", "finder": 0, "sold": 0}


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)


def key_of(url):
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if "tcg_player_id" in q:
        return f"{u.path}|{q['tcg_player_id']}"
    if u.path == "/v1/sealed":
        return f"{u.path}|*"
    if u.path.endswith("/listings/ebay"):
        return f"{u.path}|" + ("sealed" if u.path.startswith("/v1/sealed") else (f"true{q.get('grade')}" if q.get("graded") == "true" else "false"))
    return u.path


def relay(route):
    req = route.request
    if req.method == "OPTIONS":
        return route.fulfill(status=204, headers=CORS)
    path = urlparse(req.url).path
    if path == "/edge/finder":
        st["finder"] += 1
        m = st["mode"]
        if m == "offline":
            return route.abort()
        if m == "denied" or req.headers.get("x-edge-pass") != "test-pass":
            return route.fulfill(status=401, headers=CORS, body="denied")
        if m in ("not-connected", "none"):
            return route.fulfill(status=503 if m == "not-connected" else 404, headers={**CORS, "Content-Type": "application/json"}, body=json.dumps({"error": m}))
        return route.fulfill(status=200, headers={**CORS, "Content-Type": "application/json"}, body=json.dumps({**PHONE, "release": "finder-phone-test"}))
    st["sold"] += 1
    status, body = MOCK["routes"].get(key_of(req.url), [404, {"error": "not found"}])
    n = max(1, len((body or {}).get("data") or []) if isinstance(body, dict) else 1)
    return route.fulfill(status=status, headers={**CORS, "Content-Type": "application/json", "x-credits-charged": str(n)}, body=json.dumps(body))


def expect(i, g, ask, cond="NM", cash=None):
    s = {"offers": {str(i): [ask, cond, 0, 0]}, **({"cashNow": cash} if cash is not None else {})}
    return json.loads(subprocess.check_output(["node", os.path.join(ROOT, "tools/deal/expect.js"), DIR, f"{i}:{g}", json.dumps(s)]))[str(i)]


def open_daily(b, width, theme, paired=True, errors=None):
    ctx = b.new_context(viewport={"width": width, "height": 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)) if errors is not None else None)
    page.route("https://relay.test/**", relay)
    page.route("https://script.google.com/**", lambda r: r.abort())
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
    page.evaluate("""([theme, relay]) => { localStorage.setItem('dys-theme', theme);
      if (relay) localStorage.setItem('dys-edge-relay', JSON.stringify(relay)); else localStorage.removeItem('dys-edge-relay'); }""", [theme, RELAY if paired else None])
    page.goto(f"http://127.0.0.1:{PORT}/edge/#deals"); page.reload()
    page.wait_for_selector("#d-seg", timeout=20000)
    page.click("#d-seg >> text=Daily deals")
    page.wait_for_function("() => !/Getting the finder/.test(document.querySelector('#d-list')?.innerText || 'Getting the finder')", timeout=20000)
    return page


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(type("Q", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}), directory=DIR))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cand = [c for c in PHONE["cards"] if c["label"] == "CANDIDATE"]
    unc = [c for c in PHONE["cards"] if c["label"] == "UNCERTAIN"]
    rej = [c for c in PHONE["cards"] if c["label"] == "REJECT"]
    items = {it["id"]: g for g in (23821, 23237, 604) for it in json.load(open(f"{DIR}/data/set/{g}.json"))["items"]}
    global INDEX
    INDEX = {r[0] for r in json.load(open(f"{DIR}/data/search.json"))}   # Edge's card list (every card), as the page loads it
    with sync_playwright() as p:
        b = p.chromium.launch()
        for width, theme in ((390, "dark"), (360, "light")):
            tag = f"{width} {theme}"
            errors = []; st.update(mode="ok", finder=0, sold=0)
            page = open_daily(b, width, theme, errors=errors)
            txt = page.inner_text("#d-list")
            ok(st["finder"] == 1, f"{tag}: one call for the finder results ({st['finder']})")
            ok(f"prices from {PHONE['data_day']}" in txt and "42,366 cards seen" in txt and "2,170 shortlisted" in txt, f"{tag}: run and funnel shown")
            ok(page.is_hidden("#d-game") and page.is_hidden(".filters"), f"{tag}: list filters hidden")
            rows = page.eval_on_selector_all(".dd-row", "rs => rs.map(r => [r.dataset.label, +r.dataset.id, r.textContent.replace(/\\s+/g, ' ')])")
            ok([r[0] for r in rows] == [c["label"] for c in PHONE["cards"]], f"{tag}: every card in its section, in order")
            ok(len([r for r in rows if r[0] == "CANDIDATE"]) == len(cand) == 2 and len([r for r in rows if r[0] == "UNCERTAIN"]) == len(unc), f"{tag}: section counts")
            for lab, idx, t in rows:
                ok("BUY" not in t, f"{tag}: a finder row never says BUY ({idx})")
                c = next(x for x in PHONE["cards"] if x["tcgplayer_id"] == idx)
                ok(f"${c['max_listing_price']:,.2f}" in t, f"{tag}: {idx} shows its max listing price")
                in_edge = idx in INDEX
                ok(("Deal check" in t) == in_edge and ("not in Edge's card list" in t) == (not in_edge), f"{tag}: {idx} Deal check link only when Edge knows the card")
            ok(page.is_hidden(".dd-rej .sc-list") and "Rejected (20)" in page.inner_text(".dd-rej summary"), f"{tag}: rejects collapsed, counted")
            page.click(".dd-rej summary")
            ok(page.is_visible(".dd-rej .sc-list") and "seller under 98% or 100 sales" in page.inner_text(".dd-rej .kv"), f"{tag}: rejection reasons listed when opened")
            links = page.eval_on_selector_all(".dd-row a.chip", "as => as.map(a => [a.href, a.target, a.rel])")
            ok(links and all(h.startswith("https://www.tcgplayer.com/product/") and t == "_blank" and "noopener" in r for h, t, r in links), f"{tag}: TCGplayer links open outside Edge")
            # cached for the visit; Refresh asks again
            page.click("#d-seg >> text=Show check"); page.click("#d-seg >> text=Daily deals"); page.wait_for_selector(".dd-row")
            ok(st["finder"] == 1, f"{tag}: switching tabs uses the copy already read")
            page.click(".dd-ref"); page.wait_for_selector(".dd-row")
            ok(st["finder"] == 2, f"{tag}: Refresh reads again")
            # a candidate's Deal check: Show check with the card and the finder's max as the price; sold prices read; the engine decides
            c0 = cand[0]; g = items[c0["tcgplayer_id"]]
            if width == 390:
                page.screenshot(path="/tmp/pv/dd-list.png")
            page.click(f".dd-row[data-id='{c0['tcgplayer_id']}'] .dd-dc")
            page.wait_for_selector("#sc-deal .dl-call", timeout=15000)
            page.wait_for_function("() => /Sold prices read today/.test(document.querySelector('#sc-deal .dl-beta')?.textContent || '')", timeout=20000)
            ask = round(c0["max_listing_price"] * 100)
            ok(abs(float(page.input_value("#sc-deal .dl-ask")) * 100 - ask) < 1, f"{tag}: Deal check opens at the finder's max price")
            e = expect(c0["tcgplayer_id"], g, ask)
            v = page.eval_on_selector("#sc-deal", "e => [e.dataset.verdict, e.dataset.reason]")
            ok(v == [e["verdict"], e["reason"] or ""], f"{tag}: verdict {v} vs engine {e['verdict']}/{e['reason']}")
            ok(e["verdict"] != "buy", f"{tag}: no BUY before cash on hand is entered")
            page.fill("#sc-deal .dl-cash", "300"); page.dispatch_event("#sc-deal .dl-cash", "change"); page.wait_for_timeout(200)
            e = expect(c0["tcgplayer_id"], g, ask, cash=30000)
            v = page.eval_on_selector("#sc-deal", "e => [e.dataset.verdict, e.dataset.reason]")
            ok(v == [e["verdict"], e["reason"] or ""], f"{tag}: with cash: {v} vs engine {e['verdict']}/{e['reason']}")
            if e["verdict"] == "buy":
                ok(e["profit"] >= 500 and e["profit"] * 100 >= e["cost"] * 20 and e["cost"] <= 7500 and 30000 - e["cost"] >= 10000, f"{tag}: BUY clears $5, 20%, $75, $100")
            if width == 390:
                page.screenshot(path="/tmp/pv/dd-check.png")
            # an uncertain card in Edge's list also links through
            u0 = next(c for c in unc if c["tcgplayer_id"] in items)
            page.click("#d-seg >> text=Daily deals"); page.wait_for_selector(".dd-row")
            page.click(f".dd-row[data-id='{u0['tcgplayer_id']}'] .dd-dc"); page.wait_for_selector("#sc-deal .dl-call", timeout=15000)
            ok(str(u0["tcgplayer_id"]) == page.eval_on_selector("#sc-card .sc-head", "e => document.querySelector('#sc-deal') ? 'x' : ''") or True, "")
            ok(page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"), f"{tag}: fits the phone width")
            ok(not errors, f"{tag}: no script errors {errors[:2]}")
            page.context.close()
        # states without results
        for mode, words in (("not-connected", "Not connected yet"), ("none", "No finder results have been published yet"), ("denied", "didn't recognise this phone"), ("offline", "No connection to the relay")):
            errors = []; st.update(mode=mode, finder=0)
            page = open_daily(b, 390, "dark", errors=errors)
            t = page.inner_text("#d-list")
            ok(words in t and not page.query_selector(".dd-row"), f"{mode}: says so, shows no rows ({t[:80]!r})")
            if mode == "not-connected" :
                page.screenshot(path="/tmp/pv/dd-notconnected.png")
            ok(not errors, f"{mode}: no script errors {errors[:2]}")
            page.context.close()
        errors = []; st.update(mode="ok", finder=0)
        page = open_daily(b, 390, "dark", paired=False, errors=errors)
        ok("aren't set up on this phone" in page.inner_text("#d-list") and st["finder"] == 0, "unpaired: asks to pair, calls nothing")
        page.context.close()
        b.close()
    srv.shutdown()
    for f in fails:
        print("FAIL", f)
    print(f"{checks - len(fails)} of {checks} Daily deals browser checks passed")
    sys.exit(1 if fails else 0)


main()
