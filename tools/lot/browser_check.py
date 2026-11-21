"""Browser checks for binder / lot offers (Deals → Lot offer) in the real Edge app, on a local site copy with the
synthetic PkmnPrices relay (tools/deal/make_fixture.js) answered inside the browser. Nothing real is called.
    node tools/deal/make_fixture.js <site> 23237 23821 604 && python3 tools/lot/browser_check.py <site>
The site copy gets one extra search row (a made-up Reverse Holofoil printing of Wartortle 171/165) so the printing check
has a card with two printings. Expected results come from tools/lot/expect.js (same modules, run in Node).
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
PORT = 8783
MOCK = json.load(open(f"{DIR}/mock-relay.json"))
RELAY = {"relay": "https://relay.test", "pass": "test-pass"}
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "X-Edge-Pass, Accept", "Access-Control-Expose-Headers": "x-credits-charged"}
KEY, LKEY = "dys-edge-lots", "dys-edge-ledger"
checks, fails, calls = 0, [], {"n": 0, "urls": []}
# (id, set, search words): two printings, good, good, thin, no sales, under $20
WART, IVY, IRON, DRAG, MAG, DUG = (517038, 23237, "wartortle 171"), (516998, 23237, "ivysaur 167"), (610513, 23821, "iron crown ex"), \
    (517020, 23237, "dragonair 181"), (42433, 604, "magneton base set"), (42359, 604, "dugtrio base")
CARDS = [WART, IVY, IRON, DRAG, MAG, DUG]


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)


def prepare_site():
    rows = json.load(open(f"{DIR}/data/search.json"))
    if not any(r[0] == WART[0] and "Reverse Holofoil" in r[1] for r in rows):
        r = next(x for x in rows if x[0] == WART[0])
        alt = list(r); alt[1] = r[1].replace("(Holofoil)", "(Reverse Holofoil)"); alt[4] = round(r[4] * 0.4)
        rows.append(alt)
        json.dump(rows, open(f"{DIR}/data/search.json", "w"), separators=(",", ":"))


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
    calls["urls"].append(req.url)
    status, body = MOCK["routes"].get(key_of(req.url), [404, {"error": "not found"}])
    n = max(1, len((body or {}).get("data") or []) if isinstance(body, dict) else 1)
    return route.fulfill(status=status, headers={**CORS, "Content-Type": "application/json", "x-credits-charged": str(n)}, body=json.dumps(body))


def expect(spec):
    return json.loads(subprocess.check_output(["node", os.path.join(ROOT, "tools/lot/expect.js"), DIR, json.dumps(spec)]))


def spec_of(lines, **kw):
    return {"lines": [{"id": c[0], "g": c[1], **o} for c, o in lines], **kw}


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Handler, directory=DIR))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def new_page(b, width, theme, paired=True, errors=None, seed_bl=None):
    ctx = b.new_context(viewport={"width": width, "height": 860}, device_scale_factor=2, is_mobile=True, has_touch=True, service_workers="block")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)) if errors is not None else None)
    page.route("https://relay.test/**", relay)
    page.route("https://script.google.com/**", lambda r: r.abort())
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
    page.evaluate("""([theme, relay, bl]) => { localStorage.clear(); localStorage.setItem('dys-theme', theme);
      if (relay) localStorage.setItem('dys-edge-relay', JSON.stringify(relay));
      if (bl) localStorage.setItem('dys-edge-buylist', JSON.stringify(bl)); }""", [theme, RELAY if paired else None, seed_bl])
    return ctx, page


def open_lots(page):
    page.goto(f"http://127.0.0.1:{PORT}/edge/#deals")
    page.reload()
    page.wait_for_selector("#d-seg")
    page.click("#d-seg >> text=Lot offer")
    page.wait_for_selector(".lot-new, .lot-top", timeout=15000)


def line_sel(c):
    return f".lot-line[data-k^='{c[0]}|']"


def lines_state(page):
    return page.eval_on_selector_all(".lot-line", "es => es.map(e => [e.dataset.k, e.dataset.flags, +e.dataset.value])")


def out(page):
    return page.eval_on_selector("#lot-out", "e => ({ result: e.dataset.result, mode: e.dataset.mode, value: +e.dataset.value, max: +e.dataset.max, walk: e.dataset.walk ? +e.dataset.walk : null, open: e.dataset.open ? +e.dataset.open : null, text: e.innerText })")


def stored(page, key=KEY):
    return page.evaluate(f"() => JSON.parse(localStorage.getItem('{key}') || 'null')")


def type_in(page, sel, v):
    page.fill(sel, "")
    page.fill(sel, v)
    page.wait_for_timeout(60)


def same(o, e, what):
    ok(o["result"] == e["result"] and o["mode"] == e["mode"] and o["value"] == e["value"] and o["max"] == e["max"] and o["walk"] == e["walk"] and o["open"] == e["open"],
       f"{what}: page {[o[k] for k in ('result', 'mode', 'value', 'max', 'walk', 'open')]} vs expected {[e[k] for k in ('result', 'mode', 'value', 'max', 'walk', 'open')]}")
    ok(all(r[1] == ",".join(x["flags"]) and r[2] == x["value"] for r, x in zip(lines_state_cache["v"], e["rows"])) if lines_state_cache["v"] else True, f"{what}: per-card flags and values match")


lines_state_cache = {"v": None}


def main():
    prepare_site()
    srv = serve()
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for width, theme in ((390, "dark"), (360, "light")):
            tag = f"{width} {theme}"
            ctx, page = new_page(b, width, theme, errors=errors)
            open_lots(page)
            ok("No lots yet" in page.inner_text("#d-list"), f"{tag}: empty state")
            page.fill("#lot-name", "Blue binder")
            page.click("#lot-create")
            page.wait_for_selector("#lot-q")
            ok(page.input_value(".lot-title") == "Blue binder", f"{tag}: lot named")
            for c in CARDS:
                page.fill("#lot-q", c[2])
                page.wait_for_selector(f".lot-s[data-id='{c[0]}']", timeout=8000)
                page.click(f".lot-s[data-id='{c[0]}']")
                page.wait_for_selector(line_sel(c))
            page.click(".lot-add-open")
            ok(len(page.query_selector_all(".lot-line")) == 6, f"{tag}: six cards in the lot")
            ok(page.query_selector(f"{line_sel(WART)} .lot-pr-ok") is not None and page.query_selector(f"{line_sel(IVY)} .lot-pr-ok") is None,
               f"{tag}: printing confirmation only on the card with two printings")
            ok("Reverse Holofoil" in page.inner_text(line_sel(WART)), f"{tag}: names the other printing")
            # before any check: nothing counted, asks for prices
            ok(out(page)["result"] == "need-prices", f"{tag}: unchecked lot asks for prices first")
            ok(all(r[1] == "not-checked" or r[1] == "printing,not-checked" for r in lines_state(page)), f"{tag}: every card not checked")
            # prepare (estimates) within 250 credits: 2 cards
            page.click(".lot-prep-open"); page.wait_for_selector(".lot-budget")
            page.select_option(".lot-budget", "250"); page.wait_for_selector(".lot-plan")
            plan = page.eval_on_selector(".lot-plan", "e => [+e.dataset.need, +e.dataset.take]")
            ok(plan == [6, 2], f"{tag}: 250 credits cover 2 of 6 cards ({plan})")
            u0 = len(calls["urls"])
            page.click(".lot-prep-go")
            page.wait_for_function("() => /Done/.test(document.querySelector('.lot-run')?.textContent || '')", timeout=20000)
            run = page.eval_on_selector(".lot-run", "e => [+e.dataset.done, +e.dataset.credits]")
            ok(run[0] == 2 and 0 < run[1] <= 250, f"{tag}: prepared 2 cards within 250 credits ({run})")
            ok(all("graded=true" not in u and "/population" not in u for u in calls["urls"][u0:]), f"{tag}: raw sold prices only")
            ok(sum(1 for x in stored(page)["lots"][0]["lines"] if x.get("est")) == 2, f"{tag}: two estimates saved")
            page.select_option(".lot-budget", "1000"); page.wait_for_selector(".lot-plan")
            ok(page.eval_on_selector(".lot-plan", "e => +e.dataset.need") == 4, f"{tag}: only the 4 unchecked cards planned")
            page.click(".lot-prep-go")
            page.wait_for_function("() => /Done: 4 of 4/.test(document.querySelector('.lot-run')?.textContent || '')", timeout=20000)
            # every card has an estimate; seller's price and cash
            # all 6 were read this visit, so the lot is live; reload drops memory: estimates only
            ok(page.eval_on_selector("[data-live]", "e => [+e.dataset.live, +e.dataset.cards]") == [6, 6], f"{tag}: six cards read this visit")
            page.reload(); page.wait_for_selector("#d-seg"); page.click("#d-seg >> text=Lot offer")
            page.wait_for_selector(".lot-pick"); page.click(".lot-pick"); page.wait_for_selector(".lot-top")
            ok(page.eval_on_selector("[data-live]", "e => +e.dataset.live") == 0, f"{tag}: live sold prices aren't kept after a reload")
            page.fill(".lot-cash", "300"); page.wait_for_timeout(100)
            lines_state_cache["v"] = lines_state(page)
            walk = expect(spec_of([(c, {}) for c in CARDS], total=4000, cash=30000, live=False))["walk"]   # estimates value at the low end: their walk-away is lower
            type_in(page, ".lot-total", f"{walk / 100:.2f}"); type_in(page, ".lot-cash", "300")
            e_est = expect(spec_of([(c, {}) for c in CARDS], total=walk, cash=30000, live=False))
            o = out(page)
            same(o, e_est, f"{tag}: estimate")
            ok(o["result"] == "fits" and "not a verified BUY" in o["text"] and "BUY candidate" not in o["text"], f"{tag}: estimates say fits, never BUY ({o['result']})")
            # offline: still works from estimates; live check disabled
            ctx.set_offline(True)
            page.evaluate("() => window.dispatchEvent(new Event('offline'))")
            page.click(".lot-back"); page.click(".lot-pick"); page.wait_for_selector(".lot-top")
            ok(page.is_disabled(".lot-live-open") and "No connection" in page.inner_text(".lot-off"), f"{tag}: offline: live check off, says why")
            page.fill(".lot-cash", "300"); page.wait_for_timeout(100)
            ok(out(page)["result"] == "fits", f"{tag}: offline estimate still works")
            ctx.set_offline(False)
            page.evaluate("() => window.dispatchEvent(new Event('online'))")
            page.click(".lot-back"); page.click(".lot-pick"); page.wait_for_selector(".lot-top")
            # live check: confirm panel shows the credit cap; nothing read before Check now
            n0 = calls["n"]
            page.click(".lot-live-open"); page.wait_for_selector(".lot-confirm")
            ok("up to 606 credits" in page.inner_text(".lot-confirm"), f"{tag}: confirm shows the most it can cost")
            page.click(".lot-live-no")
            ok(calls["n"] == n0, f"{tag}: cancel reads nothing")
            page.click(".lot-live-open"); page.click(".lot-live-go")
            page.wait_for_function("() => /Done: 6 of 6/.test(document.querySelector('.lot-run')?.textContent || '')", timeout=20000)
            ok(calls["n"] > n0, f"{tag}: live check read sold prices")
            ok(page.inner_text(".lot-live-open").startswith("All checked live"), f"{tag}: all checked live")
            page.fill(".lot-cash", "300"); page.wait_for_timeout(100)
            lines_state_cache["v"] = lines_state(page)
            e = expect(spec_of([(c, {}) for c in CARDS], total=4000, cash=30000))
            same(out(page), e, f"{tag}: live $40, $300 cash")
            ok(out(page)["result"] == "buy" and "LIVE" in out(page)["text"], f"{tag}: live BUY candidate")
            fl = {r[0].split("|")[0]: r[1] for r in lines_state(page)}
            ok(fl[str(WART[0])] == "printing" and fl[str(DRAG[0])] == "evidence" and fl[str(MAG[0])] == "missing" and fl[str(DUG[0])] == "scope", f"{tag}: flags {fl}")
            txt = page.inner_text("#lot-out")
            ok("Counted at $0 (4)" in txt and "Where the value is" in txt, f"{tag}: value list and $0 list shown")
            # confirm the printing: it counts now
            page.check(f"{line_sel(WART)} .lot-pr-ok"); page.wait_for_timeout(150)
            page.fill(".lot-cash", "300"); page.wait_for_timeout(100)
            lines_state_cache["v"] = lines_state(page)
            e2 = expect(spec_of([(WART, {"prOk": True})] + [(c, {}) for c in CARDS[1:]], total=4000, cash=30000))
            same(out(page), e2, f"{tag}: printing confirmed")
            ok(e2["value"] > e["value"], f"{tag}: confirmed printing adds value")
            # the rules across prices and cash
            seen = set()
            for total, cash in (("40", "300"), ("40", ""), ("40", "120"), ("80", "300"), ("60", "300"), ("10", "300")):
                type_in(page, ".lot-total", total); type_in(page, ".lot-cash", cash)
                lines_state_cache["v"] = lines_state(page)
                ex = expect(spec_of([(WART, {"prOk": True})] + [(c, {}) for c in CARDS[1:]], total=int(float(total) * 100), cash=int(float(cash) * 100) if cash else None))
                o = out(page); same(o, ex, f"{tag}: ${total} cash {cash or 'none'}"); seen.add(o["result"])
                if o["result"] == "buy":
                    ok(ex["cost"] <= 7500 and ex["profit"] >= 500 and ex["profit"] * 100 >= ex["cost"] * 20, f"{tag}: BUY clears the rules")
            ok({"buy", "need-cash", "reserve"} <= seen and ({"limit", "over"} & seen), f"{tag}: rule outcomes seen {sorted(seen)}")
            # quantity: more copies than sell in a month count $0
            type_in(page, ".lot-total", "40"); type_in(page, ".lot-cash", "300")
            page.fill(f"{line_sel(IRON)} .lot-qty", "9"); page.dispatch_event(f"{line_sel(IRON)} .lot-qty", "change"); page.wait_for_timeout(150)
            page.click(f"{line_sel(IVY)} .lot-step[data-d='1']"); page.wait_for_timeout(150)
            page.select_option(f"{line_sel(IVY)} .lot-cond", "LP"); page.wait_for_timeout(150)
            page.fill(".lot-cash", "300"); page.wait_for_timeout(100)
            lines_state_cache["v"] = lines_state(page)
            spec_q = [(WART, {"prOk": True}), (IVY, {"qty": 2, "cond": "LP"}), (IRON, {"qty": 9})] + [(c, {}) for c in CARDS[3:]]
            e3 = expect(spec_of(spec_q, total=4000, cash=30000))
            same(out(page), e3, f"{tag}: quantities and condition")
            iron = next(r for r in e3["rows"] if r["k"].startswith(str(IRON[0])))
            ok(iron["counted"] < 9 and "counted $0" in page.inner_text(line_sel(IRON)), f"{tag}: extra copies counted $0 ({iron['counted']} of 9)")
            # price per card
            page.click("#lot-mode >> text=Price per card"); page.wait_for_selector(".lot-ask")
            asks = {WART: "6", IVY: "9", IRON: "2", DRAG: "3", MAG: "2", DUG: "1"}
            for c, a in asks.items():
                page.fill(f"{line_sel(c)} .lot-ask", a)
            page.fill(".lot-cash", "300"); page.wait_for_timeout(150)
            lines_state_cache["v"] = lines_state(page)
            spec_e = [(c, {**o, "ask": int(float(asks[c]) * 100)}) for c, o in spec_q]
            e4 = expect(spec_of(spec_e, askMode="each", cash=30000))
            same(out(page), e4, f"{tag}: per-card prices")
            ok(f"total ${e4['ask'] / 100:,.2f}" in page.inner_text(".lot-sum-each"), f"{tag}: per-card total shown ({e4['ask']})")
            # shipping and tax count in the all-in cost
            page.click(".lot-more summary"); page.fill(".lot-ship", "5"); page.fill(".lot-tax", "8.375"); page.fill(".lot-cash", "300"); page.wait_for_timeout(150)
            e5 = expect(spec_of(spec_e, askMode="each", cash=30000, shipIn=500, taxIn=8.375))
            same(out(page), e5, f"{tag}: shipping and tax"); ok(e5["cost"] == e4["cost"] + 500 + round(e4["ask"] * 8.375 / 100), f"{tag}: all-in includes shipping and tax")
            # storage: cards, typed prices, rounded estimates; no sold prices anywhere
            st = stored(page)
            raw = page.evaluate("() => Object.keys(localStorage).map(k => localStorage.getItem(k)).join('\\n')")
            ok(all(k in ("v", "lots") for k in st) and all(set(x) <= {"id", "name", "created", "askMode", "total", "shipIn", "taxIn", "lines"} for x in st["lots"]), f"{tag}: lot fields")
            ok(all(set(l) <= {"l", "k", "id", "g", "n", "setN", "t", "r", "cond", "qty", "ask", "alts", "prOk", "tcg", "tcgDay", "est"} and set(l.get("est", {})) <= {"at", "tcg", "grade", "pace", "resale", "walk", "issue"}
                   for l in st["lots"][0]["lines"]), f"{tag}: line fields")
            ok(not any(w in raw for w in ('"comps"', '"sold_at"', '"median"', '"m90"', '"proceeds"', '"exit"')), f"{tag}: no sold prices or exact results stored")
            for l in st["lots"][0]["lines"]:
                e_ = l.get("est") or {}
                for w in (e_.get("walk") or {}).values():
                    ok(w % (100 if w < 2000 else 250 if w < 5000 else 500) == 0, f"{tag}: walk-away rounded")
            # ledger: nothing saved until Save buy; prices add up
            led0 = (stored(page, LKEY) or {}).get("T", {}).get("items", [])
            page.click(".lot-ledger-open"); page.wait_for_selector(".lot-paid")
            ok(page.input_value(".lot-paid") == f"{e5['ask'] / 100:g}".rstrip("0").rstrip(".") or page.input_value(".lot-paid") != "", f"{tag}: paid prefilled")
            page.fill(".lot-paid", "23.50"); page.click(".lot-ledger-go")
            page.wait_for_selector("#lf", timeout=15000)
            n_lines = len(page.query_selector_all(".lg-line"))
            draft = expect(spec_of(spec_e, askMode="each", cash=30000, shipIn=500, taxIn=8.375, paid=2350))["draft"]
            ok(n_lines == len(draft["lines"]), f"{tag}: buy form has every card ({n_lines} vs {len(draft['lines'])})")
            ok(len((stored(page, LKEY) or {}).get("T", {}).get("items", [])) == len(led0), f"{tag}: nothing in the Ledger before Save buy")
            ok(sum(l["price"] * l["qty"] for l in draft["lines"]) == 2350 and sum(l["qty"] for l in draft["lines"]) == 1 + 2 + 9 + 1 + 1 + 1, f"{tag}: draft adds up")
            ok(page.input_value("#lf-ship") == "5", f"{tag}: shipping carried to the buy")
            page.click("#lf button[type=submit]")
            page.wait_for_function(f"() => (JSON.parse(localStorage.getItem('{LKEY}') || '{{}}').T?.items || []).length === {len(led0) + len(draft['lines'])}", timeout=8000)
            T = stored(page, LKEY)["T"]
            buy = T["buys"][-1]
            its = [x for x in T["items"] if x["buy"] == buy["id"]]
            ok(sum(x["price"] * x["qty"] for x in its) == 2350 and buy["ship"] == 500 and sum(x["qty"] for x in its) == 15, f"{tag}: saved buy adds up")
            ok(sorted((x["tcg"], x["cond"], x["qty"]) for x in its) == sorted((l["tcg"], l["cond"], l["qty"]) for l in draft["lines"]), f"{tag}: cards, conditions, quantities saved")
            # back to the lot: remove a card, delete the lot (two taps)
            open_lots(page)
            page.click(".lot-pick"); page.wait_for_selector(".lot-top")
            page.click(f"{line_sel(DUG)} .lot-rm"); page.wait_for_timeout(100)
            ok(len(page.query_selector_all(".lot-line")) == 5, f"{tag}: card removed")
            ok(page.evaluate("() => document.documentElement.scrollWidth") <= width, f"{tag}: no sideways scroll")
            page.screenshot(path=f"/tmp/lot-{width}.png", full_page=True)
            page.click(".lot-del")
            ok(stored(page)["lots"], f"{tag}: one tap doesn't delete")
            page.click(".lot-del"); page.wait_for_selector(".lot-new")
            ok(not stored(page)["lots"], f"{tag}: second tap deletes")
            ctx.close()
        # not paired: estimates only, live off, reuse a Buy-list estimate for the same card
        ivy_n = next(it["n"] for it in json.load(open(f"{DIR}/data/set/{IVY[1]}.json"))["items"] if it["id"] == IVY[0])
        e_iv = expect(spec_of([(IVY, {})], total=1500, cash=30000, live=False))
        import time
        bl = {"v": 1, "items": [{"k": f"{IVY[0]}|{ivy_n}", "id": IVY[0], "g": IVY[1], "n": ivy_n, "setN": "151", "t": "c", "r": "", "cond": "NM", "added": int(time.time() * 1000),
                                "est": None}]}
        est = json.loads(subprocess.check_output(["node", os.path.join(ROOT, "tools/buylist/expect_est.js"), DIR, f"{IVY[0]}:{IVY[1]}"]))[str(IVY[0])]["est"]
        bl["items"][0]["est"] = est
        ctx, page = new_page(b, 390, "dark", paired=False, errors=errors, seed_bl=bl)
        open_lots(page)
        page.click("#lot-create"); page.wait_for_selector(".lot-bl")
        page.click(".lot-bl"); page.wait_for_selector(line_sel(IVY))
        ok(page.is_disabled(".lot-live-open") and "pair it" in page.inner_text(".lot-off"), "unpaired: live off, says how to pair")
        ok(stored(page)["lots"][0]["lines"][0].get("est") == est, "the Buy list's estimate is reused")
        page.fill(".lot-total", "15"); page.fill(".lot-cash", "300"); page.wait_for_timeout(100)
        lines_state_cache["v"] = lines_state(page)
        same(out(page), e_iv, "unpaired estimate from the Buy list")
        ctx.close()
        b.close()
    srv.shutdown()
    ok(not errors, f"page errors: {errors[:3]}")
    print(f"lot browser checks: {checks - len(fails)} / {checks} passed")
    for f in fails:
        print("FAIL", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
