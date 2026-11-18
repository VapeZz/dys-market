"""Browser checks for "Where to sell?" in the real Edge app, on a local site copy, with a fake PkmnPrices relay
(synthetic sales only). Nothing is published; no Google or PkmnPrices service is called.
    python3 tools/channels/browser_check.py /tmp/m2site
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
PORT = 8772
TOKEN = "7b" * 32
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


PIKA = [sale(6, 82), sale(7, 80), sale(8, 84), sale(9, 79), sale(12, 83), sale(20, 82), sale(25, 81)]
UMB_RAW = [sale(a, p, variant="Holofoil", title="SYNTH Umbreon ex 161/131") for a, p in [(6, 950), (8, 940), (10, 960), (12, 955), (15, 945), (20, 950), (26, 948), (40, 930), (60, 920)]]
LOG = []


def relay(route):
    u = urllib.parse.urlparse(route.request.url)
    q = dict(urllib.parse.parse_qsl(u.query))
    LOG.append((u.path, q))
    h = {"Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "x-credits-charged", "Content-Type": "application/json"}
    if route.request.headers.get("x-edge-pass") != TOKEN:
        return route.fulfill(status=401, headers=h, body="{}")
    if u.path == "/v1/cards":
        return route.fulfill(status=200, headers={**h, "x-credits-charged": "1"}, body=json.dumps({"data": [{"id": f"pk-{q.get('tcg_player_id')}"}]}))
    if u.path.endswith("/population"):
        return route.fulfill(status=200, headers=h, body=json.dumps({"data": []}))
    if u.path.endswith("/listings/ebay"):
        tcg = u.path.split("/")[3][3:]
        if tcg == "649586" and q.get("grade") == "10":
            rows = PIKA
        elif tcg == "610516" and q.get("graded") == "false":
            rows = UMB_RAW
        else:
            rows = []
        return route.fulfill(status=200, headers={**h, "x-credits-charged": str(len(rows) or 1)}, body=json.dumps({"data": rows, "pagination": {"has_more": False}}))
    return route.fulfill(status=404, headers=h, body="{}")


ITEM = {"id": "i-pika", "buy": "b-i-pika", "day": "2026-11-16", "book": "Personal", "kind": "Graded", "tcg": 649586, "g": 23821, "n": "SYNTH Pikachu - 020/M-P",
        "name": "SYNTH Pikachu 020/M-P", "set": "", "cond": "", "grader": "PSA", "grade": "10", "cert": "", "qty": 1, "price": 7000, "status": "", "note": "", "upd": 1}
BUY = {"id": "b-i-pika", "day": "2026-11-16", "book": "Personal", "where": "Card show", "from": "", "pay": "Cash", "tax": 0, "ship": 0, "fees": 0, "note": "", "upd": 1}
STATE = {"v": 1, "T": {"buys": [BUY], "items": [ITEM], "sales": [], "costs": [], "cash": []}, "q": [], "pulled": 0, "err": "", "migrated": True, "sheet": ""}


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


def nums(page, sel, k):
    """[price, keep, profit] text for one option row"""
    return page.eval_on_selector(f"{sel} .ch-row[data-k={k}] .ch-nums", "el => [...el.querySelectorAll('b')].map(b => b.textContent)")


def edit(page, sel, k, field, value):
    row = f"{sel} .ch-row[data-k={k}]"
    if not page.eval_on_selector(f"{row} .ch-edit", "d => d.open"):
        page.click(f"{row} .ch-edit summary")
    page.fill(f"{row} .ch-in[data-f={field}]", value)
    page.dispatch_event(f"{row} .ch-in[data-f={field}]", "change")


def states(page, sel):
    return page.eval_on_selector_all(f"{sel} .ch-row", "rows => rows.map(r => [r.dataset.k, (r.querySelector('.ch-state') || {}).textContent || null, (r.querySelector('.ch-state') || {dataset: {}}).dataset.state || null])")


def best_is_max(page, sel, tag):
    """the row marked Best estimate has the highest estimated profit among rows without a rules warning"""
    rows = page.eval_on_selector_all(f"{sel} .ch-row", """rows => rows.map(r => ({ k: r.dataset.k, best: /Best estimate/.test(r.querySelector('.ch-top').textContent),
        rules: /Check rules/.test(r.querySelector('.ch-top').textContent), p: r.querySelectorAll('.ch-nums b')[2].textContent }))""")
    val = lambda t: None if t in ("—", "") else float(t.replace("−", "-").replace("+", "").replace("$", "").replace(",", ""))
    ok_rows = [r for r in rows if not r["rules"] and val(r["p"]) is not None]
    top = max(val(r["p"]) for r in ok_rows)
    marked = [r for r in rows if r["best"]]
    ok(len(marked) == 1 and val(marked[0]["p"]) == top and not marked[0]["rules"], f"{tag}: Best estimate = highest estimated profit {rows}")


def three_states(page, sel, cost_c, tag):
    """LOSS, PROFITABLE BELOW TARGET and MEETS TARGET on the three local options, from typed prices around the cost"""
    edit(page, sel, "fb", "price", f"{(cost_c - 100) / 100:.2f}")
    edit(page, sel, "offerup", "price", f"{(cost_c * 1.10) / 100:.2f}")
    edit(page, sel, "show", "price", f"{(cost_c * 1.25 + 100) / 100:.2f}")
    st = {k: (label, key) for k, label, key in states(page, sel)}
    ok(st["fb"] == ("LOSS", "loss"), f"{tag}: LOSS {st['fb']}")
    ok(st["offerup"] == ("PROFITABLE, BELOW TARGET", "below"), f"{tag}: PROFITABLE, BELOW TARGET {st['offerup']}")
    ok(st["show"] == ("MEETS TARGET", "meets"), f"{tag}: MEETS TARGET {st['show']}")
    ok("target 20%" in page.inner_text(f"{sel} .ch-row[data-k=offerup] .ch-sub"), f"{tag}: below-target row says the target")
    ok("−" in page.inner_text(f"{sel} .ch-row[data-k=fb] .ch-nums b.down"), f"{tag}: loss shown in red as negative")
    foot = page.inner_text(f"{sel} .dl-foot")
    ok("highest estimated profit" in foot and "doesn't mean the fastest or most likely sale" in foot, f"{tag}: Best estimate explained")
    best_is_max(page, sel, tag)


def run(page, width, theme):
    tag = f"{width}px {theme}"
    page.set_viewport_size({"width": width, "height": 860})
    page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
    page.wait_for_selector("#m-seg button", timeout=15000)
    before = page.evaluate("() => localStorage.getItem('dys-edge-ledger')")

    # 1. the PSA check on a graded item gets the comparison, with the PSA 10 typical price and what was paid
    page.click("#m-seg button:has-text('Ledger')")
    page.click("[data-view=items]")
    page.click("[data-item='i-pika']")
    page.click("[data-a=sold]")
    page.wait_for_selector(".lg-ch .ch-row[data-k=vinted]", timeout=10000)
    S = ".lg-ch"
    t = page.inner_text(S)
    ok("WHERE TO SELL?" in t.upper() and "$82.00 (PSA 10 typical sold price" in t and "Your cost: $70.00" in t, f"{tag}: comparison header ({t[:200]!r})")
    ok(nums(page, S, "ebay") == ["$82.00", "$64.42", "−$5.58"], f"{tag}: eBay row matches the PSA panel {nums(page, S, 'ebay')}")
    for k in ["fb", "offerup", "show"]:
        ok(nums(page, S, k) == ["$73.80", "$73.80", "+$3.80"], f"{tag}: {k} at 90% of $82, no platform fee {nums(page, S, k)}")
    ok(nums(page, S, "vinted") == ["$69.70", "$69.20", "−$0.80"], f"{tag}: Vinted at 85%, $0.50 supplies {nums(page, S, 'vinted')}")
    ok("Best estimate" in page.inner_text(f"{S} .ch-row[data-k=fb]"), f"{tag}: best estimate is Facebook (first of the tie)")
    vt = page.inner_text(f"{S} .ch-row[data-k=vinted]")
    ok("Check rules" in vt and "authenticity certificates" in vt and "Best estimate" not in vt, f"{tag}: Vinted flagged for a graded card")
    ok("Break-even $70.00" in page.inner_text(f"{S} .ch-row[data-k=fb]") and "20% profit at $84.00" in page.inner_text(f"{S} .ch-row[data-k=fb]"), f"{tag}: fb break-even and target")
    ok("Matches eBay at $64.42" in page.inner_text(f"{S} .ch-row[data-k=fb]"), f"{tag}: fb matches eBay price")
    ok("Break-even $88.51" in page.inner_text(f"{S} .ch-row[data-k=ebay]"), f"{tag}: eBay break-even")
    for s in ["Estimated profit", "Break-even", "Realized profit", "Ledger → Sell", "Price (est.)"]:
        ok(s in t, f"{tag}: wording {s!r}")
    no_junk(page, f"{tag} PSA comparison")
    st = {k: lab for k, lab, _ in states(page, S)}
    ok(st["ebay"] == "LOSS" and st["fb"] == "PROFITABLE, BELOW TARGET" and st["vinted"] == "LOSS", f"{tag}: PSA default states {st}")
    best_is_max(page, S, f"{tag} PSA default")
    three_states(page, S, 7000, f"{tag} PSA check")
    page.click(f"{S} .ch-reset")

    # 2. the PSA panel's own selling costs feed the eBay row
    page.click("#lg-sold-box .gs-costs summary")
    page.fill("#lg-sold-box .gs-ship", "4.00")
    page.dispatch_event("#lg-sold-box .gs-ship", "change")
    ok(nums(page, S, "ebay")[1] == "$65.42" and "Matches eBay at $65.42" in page.inner_text(f"{S} .ch-row[data-k=fb]"), f"{tag}: eBay row follows the PSA panel's shipping")
    page.click("#lg-sold-box .gs-reset")

    # 3. payment fee and sales tax on a local sale
    edit(page, S, "fb", "taxPct", "8.375")
    r = page.inner_text(f"{S} .ch-row[data-k=fb]")
    ok(nums(page, S, "fb") == ["$73.80", "$73.80", "+$3.80"] and "$6.18" in r and "passed on, not profit" in r, f"{tag}: tax shown apart, not in profit")
    page.select_option(f"{S} .ch-row[data-k=fb] .ch-pay", "venmo")
    ok(nums(page, S, "fb") == ["$73.80", "$71.41", "+$1.41"], f"{tag}: Venmo 2.99% on price + tax {nums(page, S, 'fb')}")
    ok(page.input_value(f"{S} .ch-row[data-k=fb] .ch-in[data-f=payPct]") == "2.99", f"{tag}: payment % filled from the method")
    page.select_option(f"{S} .ch-row[data-k=fb] .ch-pay", "card")
    ok(nums(page, S, "fb")[1] == "$71.57", f"{tag}: Square 2.6% + 15¢ {nums(page, S, 'fb')}")

    # 4. card show booth split, editable count; travel
    edit(page, S, "show", "booth", "50")
    ok(nums(page, S, "show")[1] == "$68.80" and "Booth share ($50.00 ÷ 10 sales)" in page.inner_text(f"{S} .ch-row[data-k=show]"), f"{tag}: booth $50 over 10 sales")
    edit(page, S, "show", "boothSales", "5")
    ok(nums(page, S, "show")[1] == "$63.80", f"{tag}: booth over 5 sales {nums(page, S, 'show')}")
    edit(page, S, "show", "travel", "6")
    ok(nums(page, S, "show")[1] == "$57.80", f"{tag}: travel $6 {nums(page, S, 'show')}")

    # 5. a typed price is for this card; save and reset defaults
    edit(page, S, "offerup", "price", "95")
    ok(nums(page, S, "offerup") == ["$95.00", "$95.00", "+$25.00"] and "Price (est.)" not in page.inner_text(f"{S} .ch-row[data-k=offerup]"), f"{tag}: typed price")
    ok("MEETS TARGET" in page.inner_text(f"{S} .ch-row[data-k=offerup]") and "Best estimate" in page.inner_text(f"{S} .ch-row[data-k=offerup]"), f"{tag}: typed price meets target and is best")
    page.click(f"{S} .ch-save")
    saved = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-v1')).set.channels")
    ok(saved and saved["show"]["booth"] == 5000 and saved["show"]["boothSales"] == 5 and saved["fb"]["pay"] == "card" and "price" not in json.dumps(saved), f"{tag}: costs saved, prices not {saved}")
    page.click(f"{S} .ch-reset")
    ok(page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-v1')).set.channels") is None and nums(page, S, "fb")[1] == "$73.80", f"{tag}: reset")

    # 6. the ledger is untouched
    a = json.loads(page.evaluate("() => localStorage.getItem('dys-edge-ledger')"))
    ok(json.loads(before)["T"] == a["T"] and a["q"] == [], f"{tag}: ledger unchanged, nothing queued")

    # 7. Sold on: three new places, old ones kept; local ones start with no shipping or supplies; nothing saved
    page.click("[data-a=close]")
    page.click("[data-item='i-pika']")
    page.click("[data-a=sell1]")
    page.wait_for_selector("#lf-plat", timeout=5000)
    opts = page.eval_on_selector("#lf-plat", "s => [...s.options].map(o => o.value)")
    ok(opts == ["eBay", "TCGplayer", "Whatnot", "Shopify", "Card show", "Local", "Facebook Marketplace", "OfferUp", "Vinted", "Trade", "Other"], f"{tag}: Sold on list {opts}")
    page.select_option("#lf-plat", "OfferUp")
    ok([page.input_value(s) for s in ["#lf-fees", "#lf-shipout", "#lf-sup"]] == ["", "", ""], f"{tag}: OfferUp starts at no fees, shipping or supplies")
    page.select_option("#lf-plat", "Vinted")
    ok([page.input_value(s) for s in ["#lf-fees", "#lf-shipout"]] == ["", ""] and page.input_value("#lf-sup") == "0.50", f"{tag}: Vinted: no fee, buyer pays the label, supplies kept")
    page.click("#lf [data-a=close]")
    a = json.loads(page.evaluate("() => localStorage.getItem('dys-edge-ledger')"))
    ok(a["T"]["sales"] == [] and a["q"] == [], f"{tag}: cancel saved nothing")

    # 8. the Deal check on a card sheet gets the comparison; it follows the price typed
    page.evaluate("""() => { const b = document.createElement('button'); b.dataset.open = 610516; b.dataset.g = 23821; b.dataset.n = 'Umbreon ex - 161/131 (Holofoil)'; document.body.append(b); b.click(); b.remove(); }""")
    page.wait_for_selector("#c-ch .ch-row[data-k=fb]", timeout=15000)
    ok("No sold price is loaded" in page.inner_text("#c-ch"), f"{tag}: before sold prices, no starting price")
    page.click("#c-deal .dl-load")
    page.wait_for_function("() => /Starting point/.test((document.querySelector('#c-ch') || {}).textContent || '')", timeout=15000)
    exit_ = page.eval_on_selector("#c-deal .dl-tiles .tile b", "b => b.textContent")
    cost = re.search(r"Your cost \(price[^\n]*\n−(\$[\d,.]+)", page.inner_text("#c-deal .dl-more") if page.eval_on_selector("#c-deal .dl-more", "d => (d.open = true, true)") else "")
    ct = page.inner_text("#c-ch")
    ok(f"Starting point: the eBay sold price {exit_}" in ct, f"{tag}: Deal check starting price {exit_}")
    ok(cost and f"Your cost: {cost.group(1)}" in ct, f"{tag}: Deal check cost {cost and cost.group(1)}")
    ok("Allowed: Vinted lists single trading cards" in ct, f"{tag}: Vinted allowed for a raw single")
    page.fill("#c-deal .dl-ask", "500")
    page.dispatch_event("#c-deal .dl-ask", "change")
    ok("Your cost: $50" in page.inner_text("#c-ch"), f"{tag}: comparison follows the Deal check price ({page.inner_text('#c-ch')[:260]!r})")
    ok(page.inner_text("#c-deal .dl-call") != "", f"{tag}: Deal check still shows its call")
    page.eval_on_selector("#c-deal .dl-more", "d => d.open = true")
    dc = re.search(r"Your cost \(price[^\n]*\n−\$([\d,.]+)", page.inner_text("#c-deal .dl-more"))
    cost_c = round(float(dc.group(1).replace(",", "")) * 100)
    three_states(page, "#c-ch", cost_c, f"{tag} Deal check")
    page.click("#c-ch .ch-reset")
    no_junk(page, f"{tag} Deal comparison")
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
                if width == 390:
                    page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
                    page.wait_for_selector("#m-seg button")
                    page.click("#m-seg button:has-text('Ledger')"); page.click("[data-view=items]"); page.click("[data-item='i-pika']"); page.click("[data-a=sold]")
                    page.wait_for_selector(".lg-ch .ch-row[data-k=vinted]")
                    page.click(".lg-ch .ch-row[data-k=fb] .ch-edit summary")
                    page.eval_on_selector(".lg-ch", "e => e.scrollIntoView()")
                    page.screenshot(path="/tmp/ch_psa.png", full_page=False)
                ok(not errors, f"{width}px: page errors {errors[:3]}")
                ctx.close()
            br.close()
    finally:
        srv.shutdown()
    print(f"{checks - len(fails)} of {checks} channel browser checks passed")
    sys.exit(1 if fails else 0)


main()
