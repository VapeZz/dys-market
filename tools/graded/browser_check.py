"""Browser checks for the graded sold-price check in the real Edge app, on a local site copy, with a fake PkmnPrices relay
(synthetic sales only). Nothing is published; no Google or PkmnPrices service is called.
    python3 tools/graded/browser_check.py /tmp/m2site
(the site copy needs data/ for sets 23821 and 23237, and assets/ + edge/ from this branch)
"""
import functools
import http.server
import json
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

DIR = sys.argv[1]
PORT = 8771
TOKEN = "7a" * 32
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
    return {"sold_at": iso(age), "price": price, "currency": "USD", "attribution": "exact", "variant": "Normal", "title": o.pop("title", "SYNTH card PSA 10"), **o}


# synthetic sold rows per (card, grader, grade): the Pikachu-shaped HOLD case, an Umbreon SELL case, a thin PSA 9
PIKA = [sale(6, 82), sale(7, 80), sale(8, 84), sale(9, 79), sale(12, 83), sale(20, 82), sale(25, 81), sale(9, 75, title="SYNTH PSA 9"), sale(10, 60, title="SYNTH PSA 10 lot of 3")]
UMB10 = [sale(a, p, variant="Holofoil") for a, p in [(6, 2600), (8, 2550), (10, 2650), (14, 2580), (18, 2620), (24, 2590), (40, 2500)]]
UMB9 = [sale(30, 1200, variant="Holofoil", title="Umbreon PSA 9"), sale(70, 1150, variant="Holofoil", title="Umbreon PSA 9")]
ROWS = {("649586", "PSA", "10"): PIKA, ("610516", "PSA", "10"): UMB10, ("610516", "PSA", "9"): UMB9}
LOG = []


def relay(route):
    u = urllib.parse.urlparse(route.request.url)
    q = dict(urllib.parse.parse_qsl(u.query))
    LOG.append((u.path, q, route.request.headers.get("x-edge-pass")))
    h = {"Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "x-credits-charged", "Content-Type": "application/json"}
    if route.request.headers.get("x-edge-pass") != TOKEN:
        return route.fulfill(status=401, headers=h, body="{}")
    if u.path == "/v1/cards":
        return route.fulfill(status=200, headers={**h, "x-credits-charged": "1"}, body=json.dumps({"data": [{"id": f"pk-{q.get('tcg_player_id')}"}]}))
    if u.path.endswith("/listings/ebay"):
        tcg = u.path.split("/")[3][3:]
        rows = ROWS.get((tcg, q.get("grader"), q.get("grade")), []) if q.get("graded") == "true" else []
        return route.fulfill(status=200, headers={**h, "x-credits-charged": str(len(rows) or 1)}, body=json.dumps({"data": rows, "pagination": {"has_more": False}}))
    return route.fulfill(status=404, headers=h, body="{}")


def item(i, tcg, n, name, grader, grade, price, book="Personal", kind="Graded", g=23821):
    return {"id": i, "buy": "b-" + i, "day": "2026-11-16", "book": book, "kind": kind, "tcg": tcg, "g": g, "n": n, "name": name, "set": "", "cond": "" if kind == "Graded" else "NM",
            "grader": grader if kind == "Graded" else "", "grade": grade if kind == "Graded" else "", "cert": "", "qty": 1, "price": price, "status": "", "note": "", "upd": 1}


ITEMS = [item("i-pika", 649586, "SYNTH Pikachu - 020/M-P", "SYNTH Pikachu 020/M-P", "PSA", "10", 7000),
         item("i-umb10", 610516, "Umbreon ex - 161/131 (Holofoil)", "Umbreon ex - 161/131 (Holofoil)", "PSA", "10", 150000, book="Business"),
         item("i-umb9", 610516, "Umbreon ex - 161/131 (Holofoil)", "Umbreon ex - 161/131 (Holofoil)", "PSA", "9", 90000, book="Business"),
         item("i-cgc", 610516, "Umbreon ex - 161/131 (Holofoil)", "Umbreon ex - 161/131 (Holofoil)", "CGC", "9.5", 90000, book="Business")]
BUYS = [{"id": "b-" + x["id"], "day": "2026-11-16", "book": x["book"], "where": "Card show", "from": "", "pay": "Cash", "tax": 0, "ship": 0, "fees": 0, "note": "", "upd": 1} for x in ITEMS]
STATE = {"v": 1, "T": {"buys": BUYS, "items": ITEMS, "sales": [], "costs": [], "cash": []}, "q": [], "pulled": 0, "err": "", "migrated": True, "sheet": ""}


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


def open_item(page, name):
    page.click("#m-seg button:has-text('Ledger')")
    page.wait_for_selector("[data-view=items]", timeout=8000)
    page.click("[data-view=items]")
    page.wait_for_selector(f"[data-item='{name}']", timeout=8000)
    page.click(f"[data-item='{name}']")
    page.wait_for_selector(".lg-kv", timeout=5000)


def sold(page):
    page.click("[data-a=sold]")
    page.wait_for_selector("#lg-sold-box .dl-call", timeout=8000)
    return page.inner_text("#lg-sold-box")


def run(page, width, theme):
    tag = f"{width}px {theme}"
    page.set_viewport_size({"width": width, "height": 860})
    page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
    page.wait_for_selector("#m-seg button", timeout=15000)
    before = page.evaluate("() => localStorage.getItem('dys-edge-ledger')")

    # 1. the Pikachu-shaped PSA 10: HOLD with the hand-checked numbers
    open_item(page, "i-pika")
    ok(page.query_selector("[data-a=sold]") is not None, f"{tag}: graded item has Check sold prices")
    LOG.clear()
    t = sold(page)
    for s in ["HOLD", "Selling now misses your target", "$82.00", "$64.42", "−$5.58", "$88.51", "$104.83", "not a prediction", "Only PSA 10 sales", "5 / 7 / 7", "2 calls, 10 credits"]:
        ok(s in t, f"{tag}: Pikachu panel shows {s!r}")
    ok("BUY" not in t and "PASS" not in t and "$26.67" not in t, f"{tag}: no raw Deal check wording or raw value")
    ok("2 left out (1 titled as another grade, 1 lots)" in t and "Kept on this page only" in t, f"{tag}: note on what was left out ({t[-300:]!r})")
    lst = [q for p, q, _ in LOG if p.endswith("/listings/ebay")]
    ok(lst and all(q.get("graded") == "true" and q.get("grader") == "PSA" and q.get("grade") == "10" for q in lst), f"{tag}: only PSA 10 asked {lst}")
    ok(all(pw == TOKEN for _, _, pw in LOG), f"{tag}: device token sent")
    no_junk(page, f"{tag} Pikachu panel")

    # 2. selling costs are editable: $4.00 shipping → keep $65.42; saved as defaults, then reset
    page.click("#lg-sold-box .gs-costs summary")
    page.fill("#lg-sold-box .gs-ship", "4.00")
    page.dispatch_event("#lg-sold-box .gs-ship", "change")
    t2 = page.inner_text("#lg-sold-box")
    ok("$65.42" in t2 and "−$4.58" in t2, f"{tag}: shipping change recalculates")
    page.click("#lg-sold-box .gs-save")
    ok(page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-v1')).set.gradedSell.ship") == 400, f"{tag}: saved as defaults")
    page.click("#lg-sold-box .gs-reset")
    ok(page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-v1')).set.gradedSell") is None, f"{tag}: reset to Edge defaults")
    ok("$64.42" in page.inner_text("#lg-sold-box"), f"{tag}: back to $64.42")

    # 3. the purchase is untouched: same rows, nothing queued for the Sheet
    after = page.evaluate("() => localStorage.getItem('dys-edge-ledger')")
    a = json.loads(after)
    pk = next(x for x in a["T"]["items"] if x["id"] == "i-pika")
    ok(a["q"] == [] and len(a["T"]["items"]) == 4 and len(a["T"]["buys"]) == 4 and a["T"]["costs"] == [], f"{tag}: no new rows or queued changes")
    ok(pk["price"] == 7000 and pk["book"] == "Personal" and pk["qty"] == 1 and pk["grade"] == "10" and pk["grader"] == "PSA", f"{tag}: Pikachu row unchanged {pk}")
    ok(json.loads(before)["T"] == a["T"], f"{tag}: ledger tables identical before and after")

    # 4. a PSA 10 that clears the target: SELL candidate
    page.click("[data-a=close]")
    open_item(page, "i-umb10")
    t = sold(page)
    ok("SELL candidate" in t and "clears your 20% target" in t, f"{tag}: Umbreon PSA 10 SELL candidate")
    # 5. thin PSA 9: INSUFFICIENT DATA, explained
    page.click("[data-a=close]")
    open_item(page, "i-umb9")
    t = sold(page)
    ok("INSUFFICIENT DATA" in t and "Only 2 PSA 9 sales" in t and "won't guess" in t, f"{tag}: PSA 9 insufficient")
    # 6. CGC: not asked, answered as insufficient
    page.click("[data-a=close]")
    open_item(page, "i-cgc")
    LOG.clear()
    t = sold(page)
    ok("INSUFFICIENT DATA" in t and "PSA grades only" in t and not LOG, f"{tag}: CGC 9.5 unsupported, no call")
    no_junk(page, f"{tag} CGC panel")

    # 7. "Sell, grade or keep?" now checks graded items too
    page.click("#m-seg button:has-text('Inventory')")
    page.wait_for_selector("#inv-adv .adv-go", timeout=8000)
    ok("Review my 4 holdings" in page.inner_text("#inv-adv .adv-go"), f"{tag}: inventory check counts graded items ({page.inner_text('#inv-adv .adv-go')})")
    page.click("#inv-adv .adv-go")
    page.click("#inv-adv .adv-yes")   # the review asks first (cost shown)
    page.wait_for_function("() => /Reviewed 4 of 4/.test((document.querySelector('#inv-adv .adv-st') || {}).textContent || '')", timeout=15000)
    rows = page.inner_text("#m-body .list")
    ok("Keep for now" in rows and "PSA 10 typical $82.00" in rows, f"{tag}: Pikachu row says keep")
    ok("Sell clears your target" in rows, f"{tag}: Umbreon PSA 10 row says sell")
    ok(rows.count("Not enough sales") == 2, f"{tag}: PSA 9 and CGC rows say not enough sales")
    no_junk(page, f"{tag} inventory")

    # 8. the card sheet says the owner holds it graded, and points to the Ledger check
    page.evaluate("""() => { const b = document.createElement('button'); b.dataset.open = 610516; b.dataset.g = 23821; b.dataset.n = 'Umbreon ex - 161/131 (Holofoil)'; document.body.append(b); b.click(); b.remove(); }""")
    page.wait_for_selector("#c-buy", timeout=15000)
    st = page.inner_text("#sheet-card")
    ok("You hold this card as PSA 10, PSA 9, CGC 9.5" in st and "Check sold prices" in st, f"{tag}: card sheet note")
    page.click("#sheet-card .close")


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
                  localStorage.setItem('dys-edge-ledger', {json.dumps(json.dumps(STATE))});
                  localStorage.setItem('dys-edge-relay', JSON.stringify({{ relay: 'https://relay.test', pass: '{TOKEN}', device: 'phone' }}));
                  localStorage.setItem('dys-edge-ledger-url', 'https://script.google.com/macros/s/TESTLEDGER/exec'); }}""")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("https://script.google.com/**", lambda r: r.abort())
                page.route("https://relay.test/**", relay)
                run(page, width, theme)
                ok(not errors, f"{width}px: page errors {errors[:3]}")
                ctx.close()
            br.close()
    finally:
        srv.shutdown()
    print(f"{checks - len(fails)} of {checks} graded browser checks passed")
    sys.exit(1 if fails else 0)


main()
