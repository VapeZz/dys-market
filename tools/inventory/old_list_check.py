"""Regression checks for the inventory value fix on the older pre-Ledger inventory list (items kept on the phone before
the move to the Ledger), on a local site copy. Synthetic data only; no relay or Sheet is reachable (requests are logged).
    python3 tools/inventory/old_list_check.py /tmp/m2site
"""
import functools
import http.server
import json
import sys
import threading

from playwright.sync_api import sync_playwright

DIR = sys.argv[1]
PORT = 8774
checks, fails = 0, []
SHEETS = []   # the ledger's usual sync-on-open calls per run (compared with the live version)


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)
        print("FAIL", what)


INV = [{"k": "610516|Umbreon ex - 161/131 (Holofoil)", "id": 610516, "g": 23821, "n": "Umbreon ex - 161/131 (Holofoil)", "t": "c", "qty": 1, "cost": 90000, "cond": "NM", "at": "2026-11-01"},
       {"k": "999999|SYNTH card with no price", "id": 999999, "g": 23821, "n": "SYNTH card with no price", "t": "c", "qty": 2, "cost": 500, "cond": "LP", "at": "2026-11-02"},
       {"k": "999998|SYNTH sealed with no price", "id": 999998, "g": 23821, "n": "SYNTH sealed with no price", "t": "s", "qty": 1, "cost": 4500, "cond": "NM", "at": "2026-11-03"}]
SEED = {"inv": INV, "set": {"platform": "ebay"}}
LEDGER = {"v": 1, "T": {"buys": [], "items": [], "sales": [], "costs": [], "cash": []}, "q": [], "pulled": 0, "err": "", "migrated": False, "sheet": ""}


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=DIR))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def run(page, width, theme, net):
    tag = f"{width}px {theme}"
    page.set_viewport_size({"width": width, "height": 860})
    page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
    page.wait_for_selector("#m-seg button", timeout=15000)
    page.click("#m-seg button:has-text('Inventory')")
    page.wait_for_selector("#m-body .tiles", timeout=10000)
    umb = page.evaluate("""async () => { const d = await (await fetch('/data/set/23821.json')).json(); return d.items.find(i => i.id === 610516).p; }""")
    store0 = page.evaluate("() => JSON.stringify(Object.keys(localStorage).sort().map(k => [k, localStorage.getItem(k)]))")
    ok(page.query_selector("#inv-move") is not None, f"{tag}: this is the pre-Ledger list (move offer shown)")
    tiles = page.eval_on_selector_all("#m-body .tiles .tile", "ts => ts.map(t => t.innerText.replace(/\\n/g, ' | '))")
    m = lambda c: "$" + f"{round(c / 100):,}"
    ok(m(umb) in tiles[0] and "1 of 3 items priced" in tiles[0], f"{tag}: value counts the priced item only {tiles[0]}")
    ok("$955" in tiles[1] and "all 3 items" in tiles[1], f"{tag}: total cost of everything, costs kept ($900 + 2×$5 + $45) {tiles[1]}")
    pl = umb - 90000
    ok(("+" if pl >= 0 else "−") + m(abs(pl)) in tiles[2] and "on $900 priced" in tiles[2], f"{tag}: unrealized only on the priced item {tiles[2]}")
    note = page.inner_text("#m-body .inv-unpriced")
    ok("2 items ($55 cost) have no price yet" in note and "unknown, not a loss" in note, f"{tag}: unpriced note {note!r}")
    rows = page.eval_on_selector_all("#m-body .list .row", "rs => rs.map(r => r.innerText)")
    card = next((r for r in rows if "SYNTH card with no price" in r), "")
    sealed = next((r for r in rows if "SYNTH sealed" in r), "")
    for name, r, cost in [("card", card, "$10.00"), ("sealed", sealed, "$45.00")]:
        ok("No price yet" in r and f"cost {cost}" in r, f"{tag}: {name} shows No price yet and its cost {r!r}")
        ok("$0.00" not in r and "−$" not in r, f"{tag}: {name} has no $0 value and no loss {r!r}")
    ok("2× · LP · paid $5.00 each" in card, f"{tag}: quantity, condition and cost kept {card!r}")
    umbr = next((r for r in rows if "Umbreon" in r), "")
    ok(m(umb).replace("$", "") in umbr.replace(",", "") or "Value: TCGplayer market" in umbr, f"{tag}: priced row shows its value and source {umbr!r}")
    ok("Value: TCGplayer market" in umbr, f"{tag}: source on the priced row")
    w = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    ok(w[0] <= w[1], f"{tag}: no sideways scroll {w}")
    body = page.inner_text("body")
    ok(not any(j in body for j in ["undefined", "NaN", "[object", "Infinity"]), f"{tag}: no junk text")
    if width == 390:
        page.add_style_tag(content=".row img,.row .thumb{display:none}")
        page.screenshot(path="/tmp/inv_oldlist.png")
    # Today shows the same totals
    page.goto(f"http://127.0.0.1:{PORT}/edge/#today")
    page.wait_for_selector(".tiles", timeout=15000)
    tt = page.eval_on_selector_all(".tile", "ts => ts.map(t => t.innerText.replace(/\\n/g, ' | '))")
    ok(any("1 of 3 items priced" in x for x in tt) and "unknown, not a loss" in page.inner_text("body"), f"{tag}: Today tiles and note {tt[:3]}")
    # nothing changed or added on the phone, and nothing went out to the relay or a Sheet
    store1 = page.evaluate("() => JSON.stringify(Object.keys(localStorage).sort().map(k => [k, localStorage.getItem(k)]))")
    s0, s1 = dict(json.loads(store0)), dict(json.loads(store1))
    ok(sorted(s0) == sorted(s1), f"{tag}: no new storage keys {sorted(set(s1) - set(s0))}")
    ok(json.loads(s1["dys-edge-v1"])["inv"] == INV, f"{tag}: inventory unchanged")
    ok(json.loads(s1["dys-edge-ledger"])["T"] == LEDGER["T"], f"{tag}: ledger untouched")
    ok(not any("eBay sold median" in v for v in s1.values()), f"{tag}: no sold-price data stored")
    relay = [u for u in net if "relay.test" in u]
    ok(relay == [], f"{tag}: no PkmnPrices relay calls {relay[:3]}")
    SHEETS.append(len([u for u in net if "script.google" in u]))


def main():
    srv = serve()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for width, theme in [(390, "dark"), (360, "light"), (430, "dark")]:
                ctx = br.new_context()
                ctx.add_init_script(f"""if (!sessionStorage.getItem('seeded')) {{ sessionStorage.setItem('seeded', '1');
                  localStorage.clear(); localStorage.setItem('dys-theme', '{theme}');
                  localStorage.setItem('dys-edge-v1', {json.dumps(json.dumps(SEED))});
                  localStorage.setItem('dys-edge-ledger', {json.dumps(json.dumps(LEDGER))});
                  localStorage.setItem('dys-edge-relay', JSON.stringify({{ relay: 'https://relay.test', pass: '{"7d" * 32}', device: 'phone' }})); }}""")
                page = ctx.new_page()
                errors, net = [], []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("https://relay.test/**", lambda r: (net.append(r.request.url), r.abort()))
                page.route("https://script.google.com/**", lambda r: (net.append(r.request.url), r.abort()))
                run(page, width, theme, net)
                ok(not errors, f"{width}px: page errors {errors[:3]}")
                ctx.close()
            br.close()
    finally:
        srv.shutdown()
    print("Sheet sync calls per run:", SHEETS)
    print(f"{checks - len(fails)} of {checks} pre-Ledger inventory checks passed")
    sys.exit(1 if fails else 0)


main()
