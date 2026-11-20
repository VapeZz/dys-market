"""Browser checks for the inventory value fix (unknown is not $0; session-only PSA sold values) in the real Edge app,
on a local site copy with a fake PkmnPrices relay and a fake Sheet. Synthetic data only. Nothing is published.
    python3 tools/inventory/browser_check.py /tmp/m2site
"""
import functools
import http.server
import json
import re
import sys
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

DIR = sys.argv[1]
PORT = 8773
TOKEN = "7c" * 32
checks, fails = 0, []
TODAY = datetime.now(timezone.utc).date()


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)
        print("FAIL", what)


def iso(age):
    return (TODAY - timedelta(days=age)).isoformat()


def sale(age, price, **o):
    return {"sold_at": iso(age), "price": price, "currency": "USD", "attribution": "exact", "variant": "Normal", "title": o.pop("title", "SYNTH PSA 10"), **o}


PIKA = [sale(6, 82), sale(7, 80), sale(8, 84), sale(9, 79), sale(12, 83), sale(20, 82), sale(25, 81)]
THIN9 = [sale(30, 1200, variant="Holofoil", title="Umbreon PSA 9"), sale(70, 1150, variant="Holofoil", title="Umbreon PSA 9")]
LOG, SHEET = [], []


def relay(route):
    u = urllib.parse.urlparse(route.request.url)
    q = dict(urllib.parse.parse_qsl(u.query))
    LOG.append((u.path, q))
    h = {"Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "x-credits-charged", "Content-Type": "application/json"}
    if u.path == "/v1/cards":
        return route.fulfill(status=200, headers={**h, "x-credits-charged": "1"}, body=json.dumps({"data": [{"id": f"pk-{q.get('tcg_player_id')}"}]}))
    if u.path.endswith("/listings/ebay"):
        tcg = u.path.split("/")[3][3:]
        rows = PIKA if tcg == "649586" and q.get("grade") == "10" else THIN9 if tcg == "610516" and q.get("grade") == "9" else []
        return route.fulfill(status=200, headers={**h, "x-credits-charged": str(len(rows) or 1)}, body=json.dumps({"data": rows, "pagination": {"has_more": False}}))
    return route.fulfill(status=404, headers=h, body="{}")


def sheet(route):
    """a fake Sheet web app: records what Edge sends and returns the same tables, so syncs succeed"""
    body = route.request.post_data or "{}"
    SHEET.append(body)
    st = json.loads(STATE_JSON)
    route.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
                  body=json.dumps({"ok": True, "applied": [], "tables": st["T"], "left": 0}))


def item(i, tcg, n, kind, price, grader="", grade="", cond="", book="Personal"):
    return {"id": i, "buy": "b-" + i, "day": "2026-11-16", "book": book, "kind": kind, "tcg": tcg, "g": 23821, "n": n, "name": n, "set": "", "cond": cond,
            "grader": grader, "grade": grade, "cert": "", "qty": 1, "price": price, "status": "", "note": "", "upd": 1}


ITEMS = [item("i-pika", 649586, "SYNTH Pikachu - 020/M-P", "Graded", 7000, "PSA", "10"),
         item("i-umb", 610516, "Umbreon ex - 161/131 (Holofoil)", "Raw", 90000, cond="NM", book="Business"),
         item("i-gone", 999999, "SYNTH Card not in Edge's data", "Raw", 500, cond="NM"),
         item("i-umb9", 610516, "Umbreon ex - 161/131 (Holofoil)", "Graded", 90000, "PSA", "9", book="Business")]
BUYS = [{"id": "b-" + x["id"], "day": "2026-11-16", "book": x["book"], "where": "Card show", "from": "", "pay": "Cash", "tax": 0, "ship": 0, "fees": 0, "note": "", "upd": 1} for x in ITEMS]
STATE = {"v": 1, "T": {"buys": BUYS, "items": ITEMS, "sales": [], "costs": [], "cash": []}, "q": [], "pulled": 0, "err": "", "migrated": True, "sheet": ""}
STATE_JSON = json.dumps(STATE)


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=DIR))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def no_junk(page, where):
    t = page.inner_text("body")
    ok(not any(j in t for j in ["undefined", "NaN", "[object", "Infinity"]), f"{where}: no junk text")
    w = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    ok(w[0] <= w[1], f"{where}: no sideways scroll {w}")


def tiles(page, sel="#m-body"):
    return page.eval_on_selector_all(f"{sel} .tiles .tile", "ts => ts.map(t => t.innerText.replace(/\\n/g, ' | '))")


def row(page, name):
    return page.eval_on_selector_all("#m-body .list .row", f"rs => (rs.find(r => r.innerText.includes({json.dumps(name)})) || {{innerText: ''}}).innerText")


def open_inventory(page):
    page.click("#m-seg button:has-text('Inventory')")
    page.wait_for_selector("#m-body .tiles", timeout=10000)


def run(page, width, theme):
    tag = f"{width}px {theme}"
    page.set_viewport_size({"width": width, "height": 860})
    page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
    page.wait_for_selector("#m-seg button", timeout=15000)
    umb = page.evaluate("""async () => { const d = await (await fetch('/data/set/23821.json')).json(); const r = d.items.find(i => i.id === 610516); return r ? r.p : null; }""")
    ok(umb, f"{tag}: Umbreon has a market price in the test data ({umb})")
    open_inventory(page)
    before = page.evaluate("() => localStorage.getItem('dys-edge-ledger')")

    # 1. unknown is not $0: 1 of 4 priced; total cost apart from priced cost; no loss for unpriced items
    t = tiles(page)
    ok(t[0].startswith("MARKET VALUE") or "Market value" in t[0], f"{tag}: value tile {t}")
    money = lambda c: "$" + f"{round(c / 100):,}"
    ok(f"{money(umb)}" in t[0] and "1 of 4 items priced" in t[0], f"{tag}: value counts priced items only {t[0]}")
    ok("$1,875" in t[1] and "all 4 items" in t[1], f"{tag}: total cost of everything {t[1]}")
    pl = umb - 90000
    ok(("+" if pl >= 0 else "−") + money(abs(pl)) in t[2] and "on $900 priced" in t[2], f"{tag}: unrealized on priced items only {t[2]}")
    note = page.inner_text("#m-body .inv-unpriced")
    ok("3 items ($975 cost) have no price yet" in note and "unknown, not a loss" in note, f"{tag}: unpriced note {note!r}")
    rp = row(page, "SYNTH Pikachu")
    ok("No price yet" in rp and "cost $70.00" in rp and "−$70" not in rp and "$0.00" not in rp, f"{tag}: Pikachu row {rp!r}")
    ok("Check sold prices to value it for this visit" in rp, f"{tag}: how to value it")
    ru = row(page, "Umbreon ex - 161/131 (Holofoil)\n")
    ok("Value: TCGplayer market" in page.inner_text("#m-body .list"), f"{tag}: market source shown")
    rg = row(page, "SYNTH Card not in")
    ok("No price yet" in rg and "$0.00" not in rg, f"{tag}: raw item with no market price {rg!r}")
    ok("Realized profit is only from recorded sales" in page.inner_text("#m-body") and "estimates" in page.inner_text("#m-body"), f"{tag}: realized vs unrealized wording")
    no_junk(page, f"{tag} inventory before")

    # 2. Today's tile says the same
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
    page.wait_for_selector(".tiles", timeout=15000)
    tt = page.eval_on_selector_all(".tile", "ts => ts.map(t => t.innerText.replace(/\\n/g, ' | '))")
    ok(any("1 of 4 items priced" in x for x in tt) and any("Unrealized" in x.title() or "UNREALIZED" in x for x in tt), f"{tag}: Today tiles {tt[:3]}")
    ok("unknown, not a loss" in page.inner_text("body"), f"{tag}: Today unpriced note")

    # 3. a PSA check that already ran values the card for this visit; no calls from Inventory itself
    page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
    page.wait_for_selector("#m-seg button")
    page.click("#m-seg button:has-text('Ledger')"); page.click("[data-view=items]"); page.click("[data-item='i-pika']"); page.click("[data-a=sold]")
    page.wait_for_selector("#lg-sold-box .dl-call", timeout=10000)
    ok(page.query_selector(".lg-ch .ch-row[data-k=fb]") is not None, f"{tag}: Where to sell? still under the PSA check")
    page.click("[data-a=close]")
    page.click("[data-item='i-umb9']"); page.click("[data-a=sold]")
    page.wait_for_selector("#lg-sold-box .dl-call", timeout=10000)
    ok("INSUFFICIENT DATA" in page.inner_text("#lg-sold-box"), f"{tag}: thin PSA 9 is insufficient")
    LOG.clear()
    open_inventory(page)
    ok(LOG == [], f"{tag}: opening Inventory made no sold-price calls {LOG}")
    rp = row(page, "SYNTH Pikachu")
    ok("$82.00" in rp and "+$12.00 est." in rp, f"{tag}: Pikachu valued at the PSA 10 sold median {rp!r}")
    ok(re.search(r"Value: PSA 10 eBay sold median, 7 sales in 30 days \(newest \w+ \d+\) · checked \d+:\d\d [AP]M, this visit only", rp), f"{tag}: sold source, dates {rp!r}")
    r9 = row(page, "PSA 9")
    ok("No price yet" in r9, f"{tag}: insufficient PSA check doesn't value a card {r9!r}")
    t = tiles(page)
    ok("2 of 4 items priced" in t[1 - 1] and money(umb + 8200) in t[0], f"{tag}: value now counts the Pikachu {t[0]}")
    pl2 = umb + 8200 - 97000
    ok(("+" if pl2 >= 0 else "−") + money(abs(pl2)) in t[2] and "on $970 priced" in t[2], f"{tag}: unrealized on $970 priced {t[2]}")
    ok("this visit only and aren't saved" in page.inner_text("#m-body"), f"{tag}: session-only note")
    no_junk(page, f"{tag} inventory after PSA check")

    # 4. nothing from PkmnPrices is stored or sent to the Sheet
    SHEET.clear()
    page.click("#m-seg button:has-text('Settings')")
    page.click("#lg-now")
    page.wait_for_timeout(2500)
    sent = "\n".join(SHEET)
    ok(SHEET and "eBay sold median" not in sent, f"{tag}: Sheet sync sent {len(SHEET)} request(s), no sold-price source")
    bodies = [json.loads(b) for b in SHEET if b.strip().startswith("{")]
    summ = [r for b in bodies for r in (b.get("summary") or []) if r and r[0] == "Market value of what has a price"]
    ok(summ and all(r[2] == 0 for r in summ) and all(abs(r[1] - umb / 100) < 0.01 for r in summ), f"{tag}: Sheet summary values only Edge's stored prices (Personal 0, not the $82 sold median) {summ[:1]}")
    items_sent = [r for b in bodies for r in ((b.get("shown") or {}).get("items") or []) if r[0] == "i-pika"]
    ok(items_sent and all(len(r) == 3 for r in items_sent), f"{tag}: Sheet item rows carry no value {items_sent[:1]}")
    store = page.evaluate("() => Object.keys(localStorage).map(k => k + '=' + localStorage.getItem(k)).join('\\n') + sessionStorage.length")
    ok("eBay sold median" not in store and "SOLDV" not in store, f"{tag}: nothing saved on the phone")
    a = json.loads(page.evaluate("() => localStorage.getItem('dys-edge-ledger')"))
    ok(json.loads(before)["T"] == a["T"], f"{tag}: ledger records unchanged")

    # 5. a reload forgets the session value: back to No price yet; Sell, grade or keep? fills it again (user-tapped calls)
    page.reload(); page.wait_for_selector("#m-seg button")
    open_inventory(page)
    ok("No price yet" in row(page, "SYNTH Pikachu"), f"{tag}: after reload, no sold value")
    page.click("#inv-adv .adv-go")
    page.click("#inv-adv .adv-yes")   # the review asks first (cost shown)
    page.wait_for_function("() => /Reviewed 4 of 4/.test((document.querySelector('#inv-adv .adv-st') || {}).textContent || '')", timeout=15000)
    ok("$82.00" in row(page, "SYNTH Pikachu"), f"{tag}: Sell, grade or keep? values it for this visit")
    no_junk(page, f"{tag} inventory after Sell, grade or keep?")


def main():
    srv = serve()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for width, theme in [(390, "dark"), (360, "light"), (430, "dark")]:
                ctx = br.new_context()
                ctx.add_init_script(f"""if (!sessionStorage.getItem('seeded')) {{ sessionStorage.setItem('seeded', '1');
                  localStorage.clear();
                  localStorage.setItem('dys-theme', '{theme}');
                  localStorage.setItem('dys-edge-v1', JSON.stringify({{ inv: [] }}));
                  localStorage.setItem('dys-edge-ledger', {json.dumps(STATE_JSON)});
                  localStorage.setItem('dys-edge-relay', JSON.stringify({{ relay: 'https://relay.test', pass: '{TOKEN}', device: 'phone' }}));
                  localStorage.setItem('dys-edge-ledger-url', 'https://script.google.com/macros/s/TESTLEDGER/exec'); }}""")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("https://script.google.com/**", sheet)
                page.route("https://relay.test/**", relay)
                run(page, width, theme)
                if width == 390:
                    page.eval_on_selector("#m-body", "e => e.scrollIntoView()")
                    page.screenshot(path="/tmp/inv_fix.png", full_page=False)
                ok(not errors, f"{width}px: page errors {errors[:3]}")
                ctx.close()
            br.close()
    finally:
        srv.shutdown()
    print(f"{checks - len(fails)} of {checks} inventory value browser checks passed")
    sys.exit(1 if fails else 0)


main()
