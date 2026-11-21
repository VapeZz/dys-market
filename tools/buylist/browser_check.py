"""Browser checks for the card-show buy list (Deals → Buy list) in the real Edge app, on a local site copy with the
synthetic PkmnPrices relay (tools/deal/make_fixture.js) answered inside the browser. Nothing real is called.
    node tools/deal/make_fixture.js /tmp/m3site 23237 23821 604 && python3 tools/buylist/browser_check.py /tmp/m3site
Expected estimates come from tools/buylist/expect_est.js and expected live verdicts from tools/deal/expect.js (the same
engine and settings, run in Node).
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

DIR = sys.argv[1]
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../..")
PORT = 8773
MOCK = json.load(open(f"{DIR}/mock-relay.json"))
RELAY = {"relay": "https://relay.test", "pass": "test-pass"}
checks, fails, calls = 0, [], {"n": 0, "urls": []}
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "X-Edge-Pass, Accept", "Access-Control-Expose-Headers": "x-credits-charged"}
KEY = "dys-edge-buylist"
GOOD, BIG, THIN, STALE, MISSING = (610513, 23821), (42355, 604), (517020, 23237), (610653, 23821), (42433, 604)
SET_OF = {i: g for i, g in (GOOD, BIG, THIN, STALE, MISSING)}


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
    calls["urls"].append(req.url)
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
META = json.load(open(f"{DIR}/data/meta.json"))
EST = json.loads(subprocess.check_output(["node", os.path.join(ROOT, "tools/buylist/expect_est.js"), DIR, ",".join(f"{i}:{g}" for i, g in SET_OF.items())]))


def expect(cases, extra=None):
    st = {"offers": {str(i): [a, c, 0, 0] for i, a, c in cases}, **(extra or {})}
    arg = ",".join(f"{i}:{IT[i][0]}" for i, _, _ in cases)
    return json.loads(subprocess.check_output(["node", os.path.join(ROOT, "tools/deal/expect.js"), DIR, arg, json.dumps(st)]))


def money(c):
    return f"{'−' if c < 0 else ''}${abs(c) / 100:,.2f}"


def step(c):
    return 100 if c < 2000 else 250 if c < 5000 else 500


def opening(w):
    o = max(100, (w * 8 // 10) // 100 * 100)
    return o if o < w else (w - 100 or None)


def k_of(i):
    return f"{i}|{IT[i][1]['n']}"


SLOW = {"on": False}


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if SLOW["on"] and self.path.split("?")[0].endswith("/data/scout.json"):
            time.sleep(12)                          # a nightly list on a bad connection (the server is threaded)
        return super().do_GET()


def serve():
    h = functools.partial(Handler, directory=DIR)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def new_page(b, width, theme, paired=True, seed=None, errors=None, slow_lists=False):
    ctx = b.new_context(viewport={"width": width, "height": 860}, device_scale_factor=2, is_mobile=True, has_touch=True, service_workers="allow")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)) if errors is not None else None)
    page.route("https://relay.test/**", relay)
    page.route("https://script.google.com/**", lambda r: r.abort())
    SLOW["on"] = slow_lists
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
    page.evaluate("""([theme, relay, seed]) => { localStorage.setItem('dys-theme', theme); localStorage.removeItem('dys-edge-buylist');
      if (relay) localStorage.setItem('dys-edge-relay', JSON.stringify(relay)); else localStorage.removeItem('dys-edge-relay');
      const d = JSON.parse(localStorage.getItem('dys-edge-v1') || '{}'); Object.assign(d, seed || {}); localStorage.setItem('dys-edge-v1', JSON.stringify(d)); }""",
                  [theme, RELAY if paired else None, seed])
    return ctx, page


def open_list(page):
    page.goto(f"http://127.0.0.1:{PORT}/edge/#deals")
    page.reload()                                   # a hash-only change doesn't reload: reread this phone's saved state
    page.wait_for_selector("#d-seg")
    page.click("#d-seg >> text=Buy list")
    page.wait_for_selector(".bl-sum", timeout=15000)


def stored(page):
    return page.evaluate(f"() => JSON.parse(localStorage.getItem('{KEY}') || 'null')")


def row(page, i):
    return f".bl-row[data-k='{k_of(i)}']"


def main():
    srv = serve()
    errors = []
    seed = {"watch": [{"k": k_of(GOOD[0]), "id": GOOD[0], "g": GOOD[1], "n": IT[GOOD[0]][1]["n"], "t": "c", "target": 1500},
                      {"k": k_of(BIG[0]), "id": BIG[0], "g": BIG[1], "n": IT[BIG[0]][1]["n"], "t": "c", "target": 9000}]}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for width, theme in ((390, "dark"), (360, "light")):
            tag = f"{width} {theme}"
            ctx, page = new_page(b, width, theme, seed=seed, errors=errors)
            open_list(page)
            ok("Your buy list is empty" in page.inner_text("#d-list"), f"{tag}: empty state")
            ok(page.is_disabled(".bl-prep-open"), f"{tag}: nothing to check while empty")
            # add from the watchlist and from search
            page.click(".bl-add-open")
            page.wait_for_selector(".bl-w")
            ok(len(page.query_selector_all(".bl-w")) == 2, f"{tag}: the watchlist is offered")
            page.click(f".bl-w[data-id='{GOOD[0]}']"); page.wait_for_selector(row(page, GOOD[0]))
            page.click(f".bl-w[data-id='{BIG[0]}']"); page.wait_for_selector(row(page, BIG[0]))
            for i in (THIN[0], STALE[0], MISSING[0]):
                n = IT[i][1]["n"]
                page.fill("#bl-q", n.replace(" (Holofoil)", "") + " " + META["groups"][str(IT[i][0])][0])   # name and set, as he'd type it
                try:
                    page.wait_for_selector(f".bl-s[data-id='{i}']", timeout=8000)
                except Exception:
                    print("DBG", i, n, page.inner_text("#bl-add")[:600]); raise
                page.click(f".bl-s[data-id='{i}']")
                page.wait_for_selector(row(page, i))
            ok(page.is_disabled(f".bl-w[data-id='{GOOD[0]}']"), f"{tag}: a card already on the list can't be added twice")
            page.click(".bl-add-open")
            st = stored(page)
            ok(st and len(st["items"]) == 5 and all(x["cond"] == "NM" and "est" not in x for x in st["items"]), f"{tag}: five cards saved, NM, not checked")
            txt = page.inner_text(".bl-list")
            ok(txt.count("not checked") == 5, f"{tag}: every row says not checked")
            ok(page.inner_text(f"{row(page, GOOD[0])} .bl-pr") == "Holofoil", f"{tag}: printing shown")
            # check prices within a 250-credit budget: two cards (101 each at most), raw sales only
            page.click(".bl-prep-open"); page.wait_for_selector(".bl-budget")
            page.select_option(".bl-budget", "250"); page.wait_for_selector(".bl-plan")
            plan = page.eval_on_selector(".bl-plan", "e => [+e.dataset.need, +e.dataset.take]")
            ok(plan == [5, 2], f"{tag}: 250 credits cover 2 of 5 cards ({plan})")
            n0, u0 = calls["n"], len(calls["urls"])
            page.click(".bl-go")
            page.wait_for_function("() => /Done/.test(document.querySelector('.bl-run')?.textContent || '')", timeout=20000)
            run = page.eval_on_selector(".bl-run", "e => [+e.dataset.done, +e.dataset.credits]")
            new_urls = calls["urls"][u0:]
            ok(run[0] == 2 and 0 < run[1] <= 250, f"{tag}: first run checked 2 cards within 250 credits ({run})")
            ok(all("graded=true" not in u and "/population" not in u for u in new_urls), f"{tag}: raw sold prices only: no graded reads, no population")
            st = stored(page)
            ok(sum(1 for x in st["items"] if x.get("est")) == 2, f"{tag}: two estimates saved")
            # the rest with a bigger budget: nothing already checked today is read again
            page.select_option(".bl-budget", "1000"); page.wait_for_selector(".bl-plan")
            ok(page.eval_on_selector(".bl-plan", "e => +e.dataset.need") == 3, f"{tag}: only the 3 unchecked cards are planned")
            page.click(".bl-go")
            page.wait_for_function("() => /Done/.test(document.querySelector('.bl-run')?.textContent || '') && +document.querySelector('.bl-run').dataset.done === 3", timeout=20000)
            st = stored(page)
            by = {x["id"]: x for x in st["items"]}
            ok(all(by[i].get("est") for i in SET_OF), f"{tag}: every card has an estimate")
            # estimates match the engine (same adapter and engine in Node), rounded down to their step
            for i in SET_OF:
                e, got = EST[str(i)], by[i].get("est") or {}
                if not e["ok"]:
                    ok(got.get("issue") == "not-found" and got.get("walk") == {}, f"{tag}: {i} not found says so")
                    continue
                ok(got.get("walk") == e["est"]["walk"] and got.get("issue") == e["est"]["issue"] and got.get("grade") == e["est"]["grade"]
                   and got.get("resale") == e["est"]["resale"] and got.get("pace") == e["est"]["pace"], f"{tag}: {i} estimate {got} vs engine {e['est']}")
                for cond, w in (got.get("walk") or {}).items():
                    x = e["exactMax"][cond]
                    ok(w <= x and w > x - step(x) and w % step(w) == 0, f"{tag}: {i} {cond} walk {w} rounds the exact max {x} down")
            ok(by[BIG[0]]["est"]["walk"]["NM"] <= 7500, f"{tag}: the $75 limit caps the walk-away")
            # nothing restricted is stored
            raw = page.evaluate(f"() => localStorage.getItem('{KEY}')")
            ok(not re.search(r'"(comps|median|exit|price|sold|profit|max)"', raw), f"{tag}: no sold prices, medians, comps, exact max or profit stored")
            ok(all(set(x.keys()) <= {"k", "id", "g", "n", "setN", "t", "r", "cond", "added", "est"} and set(x["est"].keys()) <= {"at", "tcg", "grade", "pace", "resale", "walk", "issue"} for x in st["items"]), f"{tag}: only the allowed fields")
            # rows: walk-away and opening offer on a priced card; a reason on the others
            w = by[GOOD[0]]["est"]["walk"]["NM"]
            r_txt = page.inner_text(row(page, GOOD[0]))
            ok(money(w) in r_txt and "walk-away (est.)" in r_txt and f"open {money(opening(w))}" in r_txt, f"{tag}: walk-away and opening offer in the row")
            ok("Evidence " in r_txt and "sold in 30 days" in r_txt and "checked" in r_txt, f"{tag}: evidence grade, pace and age in the row")
            ok("no buy" in page.inner_text(row(page, THIN[0])) and "Not enough reliable recent sales" in page.inner_text(row(page, THIN[0])), f"{tag}: thin card: no buy, with the reason")
            ok("no buy" in page.inner_text(row(page, MISSING[0])), f"{tag}: card PkmnPrices doesn't have: no buy")
            ok(page.eval_on_selector(".bl-sum", "e => +e.dataset.ready") == 2, f"{tag}: summary counts 2 cards with a walk-away")
            # at the table
            page.click(f"{row(page, GOOD[0])} .bl-head"); page.wait_for_selector(".bl-ask")
            neg = page.inner_text(".bl-neg")
            ok("negotiation suggestions, not valuations" in neg.lower() and money(opening(w)) in neg and money(w) in neg, f"{tag}: negotiation box labelled, opening offer and walk-away")
            res = lambda: page.eval_on_selector(".bl-out", "e => e.dataset.result")
            page.fill(".bl-ask", f"{(w - 100) / 100:.2f}"); page.wait_for_timeout(100)
            ok(res() == "need-cash" and "Enter your cash on hand" in page.inner_text(".bl-out"), f"{tag}: within the walk-away, asks for cash")
            page.fill(".bl-cash", "300"); page.wait_for_timeout(100)
            out = page.inner_text(".bl-out")
            ok(res() == "fits" and "Fits your rules (estimate)" in out and "ESTIMATE" in out and "not a verified BUY" in out, f"{tag}: fits on the saved estimate, labelled an estimate")
            ok("Estimated net profit" in out and "All-in" in out and "Leaves $" in out, f"{tag}: profit range, limit and reserve lines")
            ok("BUY candidate" not in page.inner_text("#d-list"), f"{tag}: the buy list never says BUY candidate")
            if width == 390:
                page.screenshot(path="/tmp/pv/bl-table.png")
            page.fill(".bl-ask", f"{(w + 100) / 100:.2f}"); page.wait_for_timeout(100)
            ok(res() == "over" and "Over your walk-away" in page.inner_text(".bl-out"), f"{tag}: over the walk-away")
            page.fill(".bl-ask", f"{(w - 100) / 100:.2f}"); page.fill(".bl-cash", f"{(w - 100 + 9000) / 100:.2f}"); page.wait_for_timeout(100)
            ok(res() == "reserve", f"{tag}: a price that would break the $100 reserve")
            page.fill(".bl-cash", "300"); page.wait_for_timeout(100)
            page.select_option(".bl-cnd", "LP"); page.wait_for_selector(".bl-ask")
            wl = by[GOOD[0]]["est"]["walk"]["LP"]
            ok(money(wl) in page.inner_text(".bl-neg") and stored(page)["items"][0]["cond"] == "LP", f"{tag}: LP uses the LP walk-away and is saved")
            page.select_option(".bl-cnd", "NM"); page.wait_for_selector(".bl-ask")
            # verify now: Show check with the card, price and condition; the live engine decides
            ask = w - 100
            page.fill(".bl-ask", f"{ask / 100:.2f}"); page.wait_for_timeout(80)
            n0 = calls["n"]
            page.click(".bl-verify")
            page.wait_for_function("() => /Sold prices read today/.test(document.querySelector('#sc-deal .dl-beta')?.textContent || '')", timeout=20000)
            ok(calls["n"] > n0, f"{tag}: verify reads live sold prices")
            ok(abs(float(page.input_value("#sc-deal .dl-ask")) * 100 - ask) < 1 and page.input_value("#sc-deal .dl-cond") == "NM", f"{tag}: Show check opens with the price and condition")
            ex = expect([(GOOD[0], ask, "NM")], {"cashNow": 30000})[str(GOOD[0])]
            v = page.eval_on_selector("#sc-deal", "e => [e.dataset.verdict, e.dataset.reason]")
            ok(v == [ex["verdict"], ex["reason"] or ""], f"{tag}: live verdict {v} vs engine {ex['verdict']}/{ex['reason']} (cash carried over)")
            if ex["verdict"] == "buy":
                ok(ex["profit"] >= 500 and ex["profit"] * 100 >= ex["cost"] * 20 and ex["cost"] <= 7500 and 30000 - ex["cost"] >= 10000, f"{tag}: a verified BUY clears $5, 20%, $75 and $100")
            if width == 390:
                page.screenshot(path="/tmp/pv/bl-verified.png")
            at_before = by[GOOD[0]]["est"]["at"]
            page.wait_for_timeout(200)
            ok(stored(page)["items"][0]["est"]["at"] >= at_before, f"{tag}: the live read refreshes the saved estimate")
            ok("On your buy list" in page.inner_text(".sc-acts"), f"{tag}: Show check knows the card is on the list")
            # Show check's Add to buy list
            page.fill("#sc-q", ""); page.type("#sc-q", "Iron Valiant ex", delay=5)
            iv = next(i for i, (g, it) in IT.items() if it["n"].startswith("Iron Valiant ex") and g == 23821)
            page.wait_for_selector(f"#sc-res .sc-hit[data-sc='{iv}']"); page.click(f"#sc-res .sc-hit[data-sc='{iv}']")
            page.wait_for_selector(".sc-blist"); page.click(".sc-blist"); page.wait_for_timeout(100)
            ok(any(x["id"] == iv for x in stored(page)["items"]), f"{tag}: Show check adds a card to the buy list")
            # stale, too old, a week old
            page.evaluate(f"""() => {{ const j = JSON.parse(localStorage.getItem('{KEY}')); j.items.forEach((x) => {{ if (x.est) x.est.at = Date.now() - 30 * 36e5; }}); localStorage.setItem('{KEY}', JSON.stringify(j)); }}""")
            open_list(page)
            ok("older than a day" in page.inner_text(".bl-sum") and page.eval_on_selector(row(page, GOOD[0]), "e => e.dataset.state") == "stale", f"{tag}: stale warning")
            page.click(f"{row(page, GOOD[0])} .bl-head"); page.fill(".bl-ask", f"{(w - 100) / 100:.2f}"); page.fill(".bl-cash", "300"); page.wait_for_timeout(100)
            ok(res() == "fits" and "STALE" in page.inner_text(".bl-out") and "stale estimate" in page.inner_text(".bl-out"), f"{tag}: a stale estimate is labelled stale")
            page.evaluate(f"""() => {{ const j = JSON.parse(localStorage.getItem('{KEY}')); j.items.forEach((x) => {{ if (x.est) x.est.at = Date.now() - 80 * 36e5; }}); localStorage.setItem('{KEY}', JSON.stringify(j)); }}""")
            open_list(page)
            ok("older than 3 days" in page.inner_text(".bl-sum") and "too old: verify" in page.inner_text(row(page, GOOD[0])), f"{tag}: too-old warning")
            page.click(f"{row(page, GOOD[0])} .bl-head"); page.fill(".bl-ask", f"{(w - 100) / 100:.2f}"); page.wait_for_timeout(100)
            ok(res() == "expired" and "Fits" not in page.inner_text(".bl-out"), f"{tag}: a too-old estimate gives no rules result")
            page.evaluate(f"""() => {{ const j = JSON.parse(localStorage.getItem('{KEY}')); j.items.forEach((x) => {{ if (x.est) x.est.at = Date.now() - 8 * 864e5; }}); localStorage.setItem('{KEY}', JSON.stringify(j)); }}""")
            open_list(page)
            ok(all("est" not in x for x in stored(page)["items"]) and page.inner_text(".bl-list").count("not checked") == len(stored(page)["items"]), f"{tag}: week-old numbers are dropped, cards kept")
            ok(page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"), f"{tag}: fits the phone width")
            ctx.close()

        # offline: open once online (the app saves its files), then open with no network at all
        ctx, page = new_page(b, 390, "dark", seed=seed, errors=errors)
        page.evaluate(f"""() => localStorage.setItem('{KEY}', JSON.stringify({{ v: 1, items: [{{ k: '{k_of(GOOD[0])}', id: {GOOD[0]}, g: {GOOD[1]}, n: {json.dumps(IT[GOOD[0]][1]['n'])}, setN: 'SV: Prismatic Evolutions', t: 'c', r: '', cond: 'NM', added: Date.now(),
          est: {{ at: Date.now() - 2 * 36e5, tcg: 2714, grade: 'B', pace: '3–6', resale: [2000, 3000], walk: {{ NM: 1600, LP: 1300, MP: 900 }}, issue: null }} }}] }}))""")
        open_list(page)
        page.evaluate("() => navigator.serviceWorker.ready")
        page.reload(); page.wait_for_timeout(500)
        ok(page.evaluate("() => !!navigator.serviceWorker.controller"), "offline: the app's saver is running")
        page.click("#d-seg >> text=Show check"); page.wait_for_timeout(300); page.click("#d-seg >> text=Buy list"); page.wait_for_selector(".bl-sum")
        ctx.set_offline(True)
        page.goto(f"http://127.0.0.1:{PORT}/edge/#deals"); page.wait_for_selector("#d-seg", timeout=15000)
        page.click("#d-seg >> text=Buy list"); page.wait_for_selector(".bl-sum", timeout=10000)
        ok("$16.00" in page.inner_text(row(page, GOOD[0])), "offline: the list and walk-away show with no network")
        page.click(f"{row(page, GOOD[0])} .bl-head"); page.fill(".bl-ask", "15.00"); page.fill(".bl-cash", "300"); page.wait_for_timeout(100)
        ok(page.eval_on_selector(".bl-out", "e => e.dataset.result") == "fits" and "not a verified BUY" in page.inner_text(".bl-out"), "offline: the table check works, as an estimate")
        ok(page.is_disabled(".bl-verify") and "No connection" in page.inner_text(".bl-vnote"), "offline: verify waits for signal")
        page.screenshot(path="/tmp/pv/bl-offline.png")
        ctx.set_offline(False)
        ctx.close()

        # a slow nightly list never holds the buy list up
        ctx, page = new_page(b, 390, "dark", seed=seed, errors=errors, slow_lists=True)
        t0 = time.time()
        page.goto(f"http://127.0.0.1:{PORT}/edge/#deals"); page.wait_for_selector("#d-seg")
        page.click("#d-seg >> text=Buy list"); page.wait_for_selector(".bl-sum", timeout=8000)
        ok(time.time() - t0 < 6, f"slow lists: the buy list opened in {time.time() - t0:.1f} s")
        ctx.close()

        # unpaired: the list works, checking prices asks to pair
        ctx, page = new_page(b, 390, "dark", paired=False, seed=seed, errors=errors)
        page.evaluate(f"""() => localStorage.setItem('{KEY}', JSON.stringify({{ v: 1, items: [{{ k: '{k_of(GOOD[0])}', id: {GOOD[0]}, g: {GOOD[1]}, n: {json.dumps(IT[GOOD[0]][1]['n'])}, setN: '', t: 'c', r: '', cond: 'NM', added: Date.now() }}] }}))""")
        n0 = calls["n"]
        open_list(page); page.click(".bl-prep-open")
        ok("aren't set up on this phone" in page.inner_text("#bl-prep") and calls["n"] == n0, "unpaired: asks to pair, calls nothing")
        page.click(f"{row(page, GOOD[0])} .bl-head")
        ok(page.is_disabled(".bl-verify"), "unpaired: verify is off")
        ctx.close()
        b.close()
    srv.shutdown()
    ok(not errors, f"no script errors {errors[:3]}")
    for f in fails:
        print("FAIL", f)
    print(f"{checks - len(fails)} of {checks} buy list browser checks passed")
    sys.exit(1 if fails else 0)


main()
