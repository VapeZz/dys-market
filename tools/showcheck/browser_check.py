"""Browser checks for Show check (Deals tab) and the watchlist → Deal check links, in the real Edge app on a local site
copy with the synthetic PkmnPrices relay (tools/deal/make_fixture.js) answered inside the browser. Nothing real is called.
    node tools/deal/make_fixture.js /tmp/m3site 23237 23821 604 && python3 tools/showcheck/browser_check.py /tmp/m3site
Expected verdicts come from tools/deal/expect.js (the same engine and settings, run in Node).
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
PORT = 8771
MOCK = json.load(open(f"{DIR}/mock-relay.json"))
RELAY = {"relay": "https://relay.test", "pass": "test-pass"}
checks, fails, calls = 0, [], {"n": 0}
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "X-Edge-Pass, Accept", "Access-Control-Expose-Headers": "x-credits-charged"}


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
    calls["n"] += 1
    status, body = MOCK["routes"].get(key_of(req.url), [404, {"error": "not found"}])
    n = max(1, len((body or {}).get("data") or []) if isinstance(body, dict) else 1)
    return route.fulfill(status=status, headers={**CORS, "Content-Type": "application/json", "x-credits-charged": str(n)}, body=json.dumps(body))


def items():
    out = {}
    for g in (23821, 23237, 604):
        for it in json.load(open(f"{DIR}/data/set/{g}.json"))["items"]:
            out[it["id"]] = (g, it)
    return out


IT = items()


def expect(cases, extra=None):
    """cases: [(id, ask cents, cond)] -> engine result per id (in person: no shipping, no tax)"""
    st = {"offers": {str(i): [a, c, 0, 0] for i, a, c in cases}, **(extra or {})}
    arg = ",".join(f"{i}:{IT[i][0]}" for i, _, _ in cases)
    return json.loads(subprocess.check_output(["node", os.path.join(ROOT, "tools/deal/expect.js"), DIR, arg, json.dumps(st)]))


def pick_by_kind(kind, lo, hi):
    for i, (g, it) in IT.items():
        if MOCK["kinds"].get(str(i)) == kind and it["t"] == "c" and it.get("p") and lo <= it["p"] <= hi:
            return i
    raise SystemExit(f"no {kind} card in {lo}-{hi}")


def money(c):
    return f"{'−' if c < 0 else ''}${abs(c) / 100:,.2f}"


def clean(n):
    for s in (" (Holofoil)", " (Normal)", " (Foil)"):
        n = n.replace(s, "")
    return n


def new_page(b, width, theme, paired=True, seed=None, errors=None):
    ctx = b.new_context(viewport={"width": width, "height": 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)) if errors is not None else None)
    page.route("https://relay.test/**", relay)
    page.route("https://script.google.com/**", lambda r: r.abort())
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
    page.evaluate("""([theme, relay, seed]) => { localStorage.setItem('dys-theme', theme);
      if (relay) localStorage.setItem('dys-edge-relay', JSON.stringify(relay)); else localStorage.removeItem('dys-edge-relay');
      const d = JSON.parse(localStorage.getItem('dys-edge-v1') || '{}'); Object.assign(d, seed || {}); localStorage.setItem('dys-edge-v1', JSON.stringify(d)); }""",
                  [theme, RELAY if paired else None, seed])
    page.goto(f"http://127.0.0.1:{PORT}/edge/#deals")
    page.reload()
    page.wait_for_selector("#sc-q", timeout=20000)
    return page


def verdict(page):
    return page.eval_on_selector("#sc-deal", "e => [e.dataset.verdict, e.dataset.reason]")


SEEN = set()


def check_one(page, i, ask, cond, tag, cash=None, extra=None):
    """pick card i in Show check, type the price and condition; compare with the engine"""
    g, it = IT[i]
    page.fill("#sc-q", "")
    page.type("#sc-q", clean(it["n"]).split(" - ")[0][:24], delay=5)
    page.wait_for_selector(f"#sc-res .sc-hit[data-sc='{i}']", timeout=8000)
    hits = page.query_selector_all("#sc-res .sc-hit")
    total = page.eval_on_selector("#sc-res .sr-count", "e => +e.dataset.n")           # Nov 21: every match, 20 at a time
    ok(0 < len(hits) == min(20, total), f"{tag}: search shows the first {min(20, total)} of {total} matches ({len(hits)})")
    n0 = calls["n"]
    page.click(f"#sc-res .sc-hit[data-sc='{i}']")
    page.wait_for_function("() => /Sold prices read today/.test(document.querySelector('#sc-deal .dl-beta')?.textContent || '')", timeout=20000)
    ok(calls["n"] > n0 if i not in SEEN else calls["n"] == n0, f"{tag}: picking reads sold prices once per card per visit ({calls['n'] - n0} calls)")
    SEEN.add(i)
    ok(page.evaluate("() => document.activeElement && document.activeElement.classList.contains('dl-ask')"), f"{tag}: price box is ready to type")
    ok(page.input_value("#sc-q") == clean(it["n"]), f"{tag}: search shows the picked card")
    page.fill("#sc-deal .dl-ask", f"{ask / 100:.2f}")
    page.dispatch_event("#sc-deal .dl-ask", "change")
    if it["t"] == "c":
        page.select_option("#sc-deal .dl-cond", cond)
    page.wait_for_timeout(150)
    e = expect([(i, ask, cond)], {**({"cashNow": cash} if cash is not None else {}), **(extra or {})})[str(i)]
    v, why = verdict(page)
    ok(v == e["verdict"] and (why or None) == e["reason"], f"{tag}: {clean(it['n'])} at {money(ask)} {cond}: page {v}/{why} vs engine {e['verdict']}/{e['reason']}")
    ok(page.inner_text("#sc-deal .dl-sum").strip() == e["summary"], f"{tag}: summary {page.inner_text('#sc-deal .dl-sum')[:90]!r} vs {e['summary'][:90]!r}")
    if e["verdict"] == "buy":
        ok("BUY candidate" in page.inner_text("#sc-deal .dl-call"), f"{tag}: BUY label")
    else:
        ok("PASS" in page.inner_text("#sc-deal .dl-call") and "BUY" not in page.inner_text("#sc-deal .dl-call"), f"{tag}: PASS label")
    if e["profit"] is not None:
        ok(money(e["profit"]).lstrip("−") in page.inner_text("#sc-deal .dl-tiles"), f"{tag}: net profit tile shows {money(e['profit'])}")
    if e["max"]:
        ok(money(e["max"]) in page.inner_text("#sc-deal .dl-tiles"), f"{tag}: max to pay {money(e['max'])}")
    log = page.inner_text("#sc-log") if page.query_selector("#sc-log .sc-hit") else ""
    ok(clean(it["n"]) in log and money(ask) in log, f"{tag}: the check is listed under Checked this visit")
    return e


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(type("Q", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}), directory=DIR))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    good = pick_by_kind("good", 4000, 7000)          # resells $40-70: buys at a low price
    big = pick_by_kind("good", 15000, 40000)         # resells $150+: over the $75 limit at a fair price
    thin = pick_by_kind("thin", 3000, 20000)
    stale = pick_by_kind("stale", 3000, 20000)
    gx = expect([(good, 1000, "NM"), (big, 1000, "NM")])
    gexit, bexit = gx[str(good)]["exit"], gx[str(big)]["exit"]
    ok(gexit and bexit, "fixture: both good cards have sold exits")
    cheap, fair = int(gexit * 0.5), int(gexit * 0.9)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for width, theme in ((390, "dark"), (360, "light")):
            tag = f"{width} {theme}"
            errors, calls["n"] = [], 0
            SEEN.clear()
            page = new_page(b, width, theme, errors=errors)
            ok("Show check" in page.inner_text("#d-seg") and page.is_hidden("#d-game") and page.is_hidden(".filters"), f"{tag}: Deals opens on Show check, list filters hidden")
            ok("$75.00 most per purchase" in page.inner_text("#d-list") and "$100.00 cash kept back" in page.inner_text("#d-list"), f"{tag}: rules shown")
            e = check_one(page, good, cheap, "NM", f"{tag} good cheap")
            ok(e["verdict"] == "pass" and e["reason"] == "cash", f"{tag}: without cash on hand a good price is not yet a BUY ({e['reason']})")
            ok("Enter your cash on hand to confirm you keep $100.00 back" in page.inner_text("#sc-deal .dl-sum") and "BUY" not in page.inner_text("#sc-deal .dl-call"), f"{tag}: asks for cash on hand")
            page.fill("#sc-deal .dl-cash", "300"); page.dispatch_event("#sc-deal .dl-cash", "change"); page.wait_for_timeout(150)
            e = expect([(good, cheap, "NM")], {"cashNow": 30000})[str(good)]
            ok(verdict(page)[0] == e["verdict"] == "buy" and "BUY candidate" in page.inner_text("#sc-deal .dl-call"), f"{tag}: with $300 cash it's a BUY candidate {verdict(page)}")
            ok(e["profit"] >= 500 and e["profit"] * 100 >= e["cost"] * 20 and e["cost"] <= 7500 and 30000 - e["cost"] >= 10000, f"{tag}: that BUY clears $5, 20%, $75 and the $100 reserve {e}")
            # Bought it opens the Ledger's buy form, filled in; nothing is recorded until Save buy
            led0 = page.evaluate("() => localStorage.getItem('dys-edge-ledger')")
            page.click("#sc-card .sc-buy"); page.wait_for_selector("#lf", timeout=10000)
            ok("Save buy" in page.inner_text("#lf") and clean(IT[good][1]["n"]) in page.inner_text("#lf"), f"{tag}: Bought it opens the buy form filled in")
            ok(abs(float(page.input_value("#lf input[data-k=price]") or 0) - cheap / 100) < 0.005, f"{tag}: buy form has the seller's price ({page.input_value('#lf input[data-k=price]')})")
            ok(page.evaluate("() => localStorage.getItem('dys-edge-ledger')") == led0, f"{tag}: nothing recorded until Save buy")
            page.goto(f"http://127.0.0.1:{PORT}/edge/#deals"); page.wait_for_selector("#sc-deal .dl-cash", timeout=10000)
            ok(page.input_value("#sc-deal .dl-cash") == "300", f"{tag}: cash on hand kept for this visit ({page.input_value('#sc-deal .dl-cash')!r})")
            e = check_one(page, good, fair, "NM", f"{tag} good fair", cash=30000)
            ok(e["verdict"] == "pass" and e["reason"] == "margin", f"{tag}: at 90% of sold value it doesn't clear the margin ({e['reason']})")
            e = check_one(page, good, cheap, "LP", f"{tag} good LP", cash=30000)
            e = check_one(page, big, int(bexit * 0.5), "NM", f"{tag} big over limit", cash=30000)
            ok(e["verdict"] == "pass" and e["reason"] == "limit", f"{tag}: over $75 all-in is research only ({e['reason']})")
            ok("research only" in page.inner_text("#sc-deal .dl-call").lower() and "limit" in page.inner_text("#sc-deal .dl-tiles"), f"{tag}: says research only; max to pay is held to the limit")
            e = check_one(page, thin, 500, "NM", f"{tag} thin", cash=30000)
            ok(e["verdict"] == "pass" and e["reason"] in ("evidence", "liquidity", "fresh"), f"{tag}: thin sales never BUY ({e['reason']})")
            ok("$" not in page.inner_text("#sc-deal .dl-tiles").split("Max to pay")[0].split("Net profit")[1] if e["profit"] is None else True, f"{tag}: no profit shown without sales")
            check_one(page, stale, 500, "NM", f"{tag} stale", cash=30000)
            # cash on hand: $120 leaves $90 after a $30 buy -> PASS (reserve); $250 -> fine
            check_one(page, good, 3000 if gexit * 0.5 >= 3000 else cheap, "NM", f"{tag} reserve pre", cash=30000)
            page.fill("#sc-deal .dl-cash", "120"); page.dispatch_event("#sc-deal .dl-cash", "change"); page.wait_for_timeout(150)
            e = expect([(good, 3000 if gexit * 0.5 >= 3000 else cheap, "NM")], {"cashNow": 12000})[str(good)]
            ok(verdict(page) == [e["verdict"], e["reason"]], f"{tag}: $120 cash: page {verdict(page)} vs engine {e['verdict']}/{e['reason']}")
            ok(e["verdict"] == "pass" and e["reason"] == "reserve", f"{tag}: a buy that leaves less than $100 cash is a PASS ({e['reason']})")
            page.fill("#sc-deal .dl-cash", "250"); page.dispatch_event("#sc-deal .dl-cash", "change"); page.wait_for_timeout(300)
            ok(verdict(page)[0] == "buy", f"{tag}: with $250 cash the same buy clears {verdict(page)}")
            ok("cash" not in page.evaluate("() => localStorage.getItem('dys-edge-v1')").lower().replace("cashreserve", ""), f"{tag}: cash on hand isn't saved anywhere")
            # re-checking from the visit list costs nothing (sold prices in memory)
            n0 = calls["n"]
            page.click(f"#sc-log .sc-past[data-sc='{thin}']"); page.wait_for_timeout(500)
            ok(calls["n"] == n0 and verdict(page)[0] == "pass", f"{tag}: re-check from the visit list uses memory ({calls['n'] - n0} calls)")
            cred = page.inner_text("#sc-log .sec-head")
            ok("credits" in cred, f"{tag}: credits used this visit shown {cred!r}")
            # watch at max to pay -> watchlist -> Deal check chip -> Show check with the card picked
            check_one(page, good, cheap, "NM", f"{tag} watch", cash=25000)
            ok(verdict(page)[0] == "buy", f"{tag}: watch case is a BUY with $250 cash")
            mx = expect([(good, cheap, "NM")], {"cashNow": 25000})[str(good)]["max"]
            page.click("#sc-card .sc-watch"); page.wait_for_timeout(200)
            w = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-v1')).watch")
            ok(any(x["id"] == good and x["target"] == mx and x.get("from") == "deal" for x in w), f"{tag}: watched at max to pay {money(mx)} {w}")
            page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
            page.click("#m-seg >> text=Watchlist")
            page.wait_for_selector(".w-dc", timeout=10000)
            ok("Target = max to pay on sold prices" in page.inner_text("#m-body"), f"{tag}: watchlist says where the target came from")
            n0 = calls["n"]
            page.click(f".w-dc[data-id='{good}']")
            page.wait_for_selector("#sc-deal .dl-call", timeout=15000)
            page.wait_for_function("() => /Sold prices read today/.test(document.querySelector('#sc-deal .dl-beta')?.textContent || '')", timeout=20000)
            lo = min(x for x in (IT[good][1].get("lo"), IT[good][1].get("p")) if x)
            ok(page.input_value("#sc-deal .dl-ask") == f"{lo / 100:.2f}" and clean(IT[good][1]["n"]) in page.inner_text("#sc-card .sc-head"), f"{tag}: Deal check chip opens Show check at today's lowest price")
            ok(calls["n"] == n0, f"{tag}: sold prices already in memory, nothing spent ({calls['n'] - n0})")
            # Today: a watched card at target carries the chip
            page.evaluate("(id) => { const d = JSON.parse(localStorage.getItem('dys-edge-v1')); d.watch.find((x) => x.id === id).target = 999999; localStorage.setItem('dys-edge-v1', JSON.stringify(d)); }", good)
            page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.reload(); SEEN.clear()     # a reload forgets sold prices (memory only)
            page.wait_for_selector("#t-buy .w-dc", timeout=15000)
            ok("Not checked against sold prices yet" in page.inner_text("#t-buy"), f"{tag}: Today hit labelled unchecked, with the chip")
            # settings: the limit is the owner's, and changing it changes the call
            page.goto(f"http://127.0.0.1:{PORT}/edge/#mine"); page.click("#m-seg >> text=Settings")
            page.wait_for_selector("#st-lim", timeout=10000)
            ok(float(page.input_value("#st-lim")) == 75 and float(page.input_value("#st-res")) == 100, f"{tag}: settings show $75 / $100 ({page.input_value('#st-lim')}, {page.input_value('#st-res')})")
            if width == 390:
                page.fill("#st-lim", "250"); page.click("#st-f button[type=submit]"); page.wait_for_timeout(200)
                page.goto(f"http://127.0.0.1:{PORT}/edge/#deals"); page.wait_for_selector("#sc-q")
                ok(page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-cash') || 'null')?.c") == 25000, f"{tag}: cash on hand kept on this phone across a reload (shared, 12 hours)")
                check_one(page, big, int(bexit * 0.5), "NM", f"{tag} limit 250 pre", cash=25000, extra={"buyLimit": 25000})   # the $250 typed earlier is still set
                page.fill("#sc-deal .dl-cash", "1000"); page.dispatch_event("#sc-deal .dl-cash", "change"); page.wait_for_timeout(200)
                e2 = expect([(big, int(bexit * 0.5), "NM")], {"buyLimit": 25000, "cashNow": 100000})[str(big)]
                ok(verdict(page)[0] == e2["verdict"] == "buy", f"{tag}: with a $250 limit the big card is a BUY candidate {verdict(page)} {e2['verdict']}")
                page.goto(f"http://127.0.0.1:{PORT}/edge/#mine"); page.click("#m-seg >> text=Settings"); page.wait_for_selector("#st-lim")
                page.fill("#st-lim", "75"); page.click("#st-f button[type=submit]")
            # card sheet Deal check uses the same rules
            page.goto(f"http://127.0.0.1:{PORT}/edge/#deals"); page.wait_for_selector("#sc-q")
            page.fill("#sc-q", clean(IT[big][1]["n"]).split(" - ")[0]); page.wait_for_selector(f".sc-hit[data-sc='{big}']"); page.click(f".sc-hit[data-sc='{big}']")
            page.wait_for_selector("#sc-card .sc-open"); page.click("#sc-card .sc-open")
            page.wait_for_selector("#c-deal .dl-call", timeout=15000)
            ok("per-purchase limit" in page.inner_text("#c-deal") or "within your" in page.inner_text("#c-deal"), f"{tag}: the card sheet's Deal check shows the limit check")
            page.keyboard.press("Escape")
            ok(page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"), f"{tag}: fits the phone width")
            if width == 390:
                page.goto(f"http://127.0.0.1:{PORT}/edge/#deals"); page.wait_for_selector("#sc-q")
                page.fill("#sc-q", clean(IT[good][1]["n"]).split(" - ")[0]); page.wait_for_selector(f".sc-hit[data-sc='{good}']"); page.click(f".sc-hit[data-sc='{good}']")
                page.wait_for_function("() => /Sold prices read today/.test(document.querySelector('#sc-deal .dl-beta')?.textContent || '')", timeout=20000)
                page.fill("#sc-deal .dl-ask", f"{cheap / 100:.2f}"); page.dispatch_event("#sc-deal .dl-ask", "change"); page.wait_for_timeout(200)
                page.fill("#sc-deal .dl-cash", "300"); page.dispatch_event("#sc-deal .dl-cash", "change"); page.wait_for_timeout(200)
                page.screenshot(path="/tmp/pv/sc-buy.png", full_page=False)
                page.fill("#sc-deal .dl-ask", f"{int(bexit * 0.5) / 100:.2f}")
                page.fill("#sc-q", clean(IT[big][1]["n"]).split(" - ")[0]); page.wait_for_selector(f".sc-hit[data-sc='{big}']"); page.click(f".sc-hit[data-sc='{big}']")
                page.wait_for_function("() => /Sold prices read today/.test(document.querySelector('#sc-deal .dl-beta')?.textContent || '')", timeout=20000)
                page.fill("#sc-deal .dl-ask", f"{int(bexit * 0.5) / 100:.2f}"); page.dispatch_event("#sc-deal .dl-ask", "change"); page.wait_for_timeout(200)
                page.screenshot(path="/tmp/pv/sc-limit.png")
            ok(not errors, f"{tag}: no script errors {errors[:2]}")
            page.context.close()
        # not paired: everything stays a PASS, nothing is called
        errors, calls["n"] = [], 0
        page = new_page(b, 390, "dark", paired=False, errors=errors)
        ok("aren't set up on this phone" in page.inner_text("#d-list"), "unpaired: says how to set up")
        page.fill("#sc-q", clean(IT[good][1]["n"]).split(" - ")[0]); page.wait_for_selector(f".sc-hit[data-sc='{good}']"); page.click(f".sc-hit[data-sc='{good}']")
        page.wait_for_selector("#sc-deal .dl-call")
        page.fill("#sc-deal .dl-ask", f"{cheap / 100:.2f}"); page.dispatch_event("#sc-deal .dl-ask", "change"); page.wait_for_timeout(150)
        ok(verdict(page)[0] == "pass" and calls["n"] == 0, f"unpaired: PASS with no sold prices, no calls {verdict(page)} {calls['n']}")
        page.click(".sc-pair"); page.wait_for_selector("#rl-pair", timeout=8000)
        ok(True, "unpaired: Go to Settings opens pairing")
        ok(not errors, f"unpaired: no script errors {errors[:2]}")
        b.close()
    srv.shutdown()
    for f in fails:
        print("FAIL", f)
    print(f"{checks - len(fails)} of {checks} Show check browser checks passed")
    sys.exit(1 if fails else 0)


main()
