"""Browser checks for the real-profit scorecard (Mine → Scorecard) and the estimate line a buy carries, in the real Edge
app on a local site copy with the synthetic PkmnPrices relay. Synthetic ledger and sales only; nothing real is called.
    python3 tools/score/browser_check.py <site copy made by tools/deal/make_fixture.js, with tools/lot's extra row>
Expected numbers come from tools/score/expect.js (the same Ledger math and scorecard in Node).
"""
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../lot"))
import browser_check as LB   # the lot checks' server, relay and helpers
from playwright.sync_api import sync_playwright

DIR = LB.DIR
ROOT = LB.ROOT
LKEY = "dys-edge-ledger"
checks, fails = 0, []
TODAY = datetime.date.today().isoformat()


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)


def money(c):
    return f"{'−' if c < 0 else ''}${abs(c) / 100:,.2f}" if abs(c) < 100000 else f"{'−' if c < 0 else ''}${round(abs(c) / 100):,}"


def signed(c):
    return ("+" if c >= 0 else "") + money(c)


def d(days):
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def sample():
    t = {"buys": [], "items": [], "sales": [], "costs": [], "cash": []}
    t["buys"] += [{"id": "b1", "day": d(60), "book": "Business", "where": "Card show", "pay": "Cash", "tax": 838, "ship": 0, "fees": 0, "upd": 1},
                  {"id": "b2", "day": d(50), "book": "Personal", "where": "Online", "pay": "Card", "tax": 0, "ship": 500, "fees": 0, "upd": 1}]
    t["items"] += [{"id": "i1", "buy": "b1", "day": d(60), "book": "Business", "kind": "Raw", "name": "Pikachu (SAMPLE)", "cond": "NM", "qty": 2, "price": 2000, "upd": 1,
                    "note": f"Edge est: net $35.00–$40.00/copy (Show check · NM · B · {d(60)})"},
                   {"id": "i2", "buy": "b1", "day": d(60), "book": "Business", "kind": "Raw", "name": "Charmander (SAMPLE)", "cond": "LP", "qty": 1, "price": 1000, "upd": 1},
                   {"id": "i3", "buy": "b2", "day": d(50), "book": "Personal", "kind": "Graded", "grader": "PSA", "grade": "10", "name": "Umbreon (SAMPLE)", "qty": 1, "price": 30000, "upd": 1,
                    "note": f"Edge est: net $300.00–$325.00/copy (Deal check · B · {d(50)})"},
                   {"id": "i4", "buy": "", "day": d(400), "book": "Business", "kind": "Sealed", "name": "ETB (SAMPLE)", "qty": 1, "price": 4500, "upd": 1}]
    t["costs"] += [{"id": "c1", "day": d(40), "book": "Personal", "item": "i3", "kind": "Grading", "amount": 2500, "upd": 1},
                   {"id": "c2", "day": d(20), "book": "Business", "item": "", "kind": "Show table", "amount": 4000, "upd": 1}]
    t["sales"] += [{"id": "s1", "day": d(19), "item": "i1", "book": "Business", "qty": 1, "plat": "eBay", "price": 4500, "shipIn": 0, "fees": 650, "shipOut": 100, "supplies": 50, "other": 0, "upd": 1},
                   {"id": "s2", "day": d(10), "item": "i2", "book": "Business", "qty": 1, "plat": "Card show", "price": 1200, "shipIn": 0, "fees": 0, "shipOut": 0, "supplies": 0, "other": 0, "upd": 1},
                   {"id": "s3", "day": d(8), "item": "i3", "book": "Personal", "qty": 1, "plat": "eBay", "price": 30000, "shipIn": 500, "fees": 4100, "shipOut": 500, "supplies": 100, "other": 0, "upd": 1},
                   {"id": "s4", "day": d(200), "item": "i4", "book": "Business", "qty": 1, "plat": "Whatnot", "price": 6000, "shipIn": 0, "fees": 600, "shipOut": 0, "supplies": 0, "other": 0, "upd": 1}]
    return t


def expect(t, **o):
    return json.loads(subprocess.check_output(["node", os.path.join(ROOT, "tools/score/expect.js"), json.dumps(t), json.dumps({"today": TODAY, **o})]))


def seed_ledger(page, t):
    page.evaluate(f"(T) => localStorage.setItem('{LKEY}', JSON.stringify({{ v: 1, T, q: [], pulled: 0, err: '', migrated: true, sheet: '' }}))", t)


def open_score(page):
    page.goto(f"http://127.0.0.1:{LB.PORT}/edge/#mine"); page.reload()
    page.wait_for_selector("#m-seg")
    page.click("#m-seg >> text=Scorecard")
    page.wait_for_selector("#sc-book", timeout=15000)


def tiles(page):
    return {e.query_selector("span").inner_text(): e.query_selector("b").inner_text() for e in page.query_selector_all(".sc-tiles .sc-tile")}


def table(page, g):
    return [[r.get_attribute("data-k"), r.query_selector_all("span")[1].inner_text(), r.query_selector("b").inner_text()] for r in page.query_selector_all(f".sc-tbl[data-g='{g}'] .sc-tr[data-k]")]


def main():
    LB.prepare_site()
    srv = LB.serve()
    errors = []
    t = sample()
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for width, theme in ((390, "dark"), (360, "light")):
            tag = f"{width} {theme}"
            ctx, page = LB.new_page(b, width, theme, errors=errors)
            # empty ledger
            seed_ledger(page, {"buys": [], "items": [], "sales": [], "costs": [], "cash": []})
            open_score(page)
            ok("No sales recorded yet" in page.inner_text("#m-body"), f"{tag}: empty state")
            # the sample ledger
            seed_ledger(page, t)
            open_score(page)
            e = expect(t)
            tl = tiles(page)
            ok(tl.get("Realized profit") == signed(e["total"]["profit"]), f"{tag}: realized profit {tl.get('Realized profit')} vs {signed(e['total']['profit'])}")
            ok(tl.get("ROI") == f"{'+' if e['total']['roi'] > 0 else ''}{e['total']['roi']:.0f}%", f"{tag}: ROI {tl.get('ROI')}")
            ok(tl.get("Money in") == money(e["total"]["proceeds"]) and tl.get("Selling fees") == money(e["total"]["fees"]) and tl.get("Shipping paid") == money(e["total"]["shipOut"]), f"{tag}: money in, fees, shipping {tl}")
            ok(tl.get("Won / lost") == f"{e['total']['wins']} / {e['total']['sales'] - e['total']['wins']}", f"{tag}: won / lost")
            ok(money(e["expenses"]) in page.inner_text(".sc-exp") and signed(e["afterExpenses"]) in page.inner_text(".sc-exp"), f"{tag}: other expenses and profit after them")
            for g, key in (("source", "bySource"), ("type", "byType"), ("plat", "byPlat"), ("cost", "byCost")):
                got = [[k, int(re.match(r"\d+", s).group(0)), p] for k, s, p in table(page, g)]
                want = [[k, n, signed(p)] for k, n, p in e[key]]
                ok(got == want, f"{tag}: {g} table {got} vs {want}")
            txt = page.inner_text("#m-body")
            ok("1 of 4 sales had an Edge estimate" in txt or f"{e['est']['recorded']} of 4 sales had an Edge estimate" in txt, f"{tag}: estimate count shown")
            ok(e["est"]["recorded"] == 2 and page.eval_on_selector_all(".sc-est", "es => es.map(e => e.dataset.where).sort().join(',')") == "below,in", f"{tag}: estimates in range / below")
            ok("Best sales" in txt and "Losses" in txt and "Still held: 1 item" in txt, f"{tag}: best, losses, still held")
            # filters
            page.click("#sc-per >> text=30 days"); page.wait_for_timeout(200)
            e30 = expect(t, period="d30")
            ok(tiles(page).get("Realized profit") == signed(e30["total"]["profit"]) and e30["total"]["sales"] == 3, f"{tag}: 30 days")
            page.click("#sc-book >> text=Personal"); page.wait_for_timeout(200)
            ep = expect(t, period="d30", book="Personal")
            ok(tiles(page).get("Realized profit") == signed(ep["total"]["profit"]) and ep["total"]["sales"] == 1, f"{tag}: Personal, 30 days")
            page.click("#sc-book >> text=Both books"); page.click("#sc-per >> text=All time"); page.wait_for_timeout(200)
            ok(page.evaluate("() => document.documentElement.scrollWidth") <= width, f"{tag}: no sideways scroll")
            page.screenshot(path=f"/tmp/score-{width}.png", full_page=True)
            # an estimate line from Show check's Bought it (live sold prices through the synthetic relay)
            card = LB.IVY
            page.goto(f"http://127.0.0.1:{LB.PORT}/edge/#deals"); page.reload(); page.wait_for_selector("#sc-q", timeout=20000)
            page.fill("#sc-q", card[2]); page.wait_for_selector(f"#sc-res .sc-hit[data-sc='{card[0]}']", timeout=8000); page.click(f"#sc-res .sc-hit[data-sc='{card[0]}']")
            page.wait_for_function("() => /Sold prices read today/.test(document.querySelector('#sc-deal .dl-beta')?.textContent || '')", timeout=20000)
            page.fill("#sc-deal .dl-ask", "20"); page.dispatch_event("#sc-deal .dl-ask", "change")
            page.select_option("#sc-deal .dl-cond", "LP"); page.wait_for_timeout(200)
            page.click("#sc-card .sc-buy"); page.wait_for_selector("#lf", timeout=10000)
            ok(page.input_value(".lg-line [data-k=cond]") == "LP", f"{tag}: Show check's condition carried into the buy")
            ok(page.input_value(".lg-line [data-k=price]") == "20", f"{tag}: Show check's price carried into the buy")
            n0 = len(page.evaluate(f"() => JSON.parse(localStorage.getItem('{LKEY}')).T.items"))
            page.click("#lf button[type=submit]")
            page.wait_for_function(f"() => JSON.parse(localStorage.getItem('{LKEY}')).T.items.length === {n0 + 1}", timeout=8000)
            item = page.evaluate(f"() => JSON.parse(localStorage.getItem('{LKEY}')).T.items.slice(-1)[0]")
            m = re.search(r"Edge est: net \$([\d,.]+)–\$([\d,.]+)/copy \(Show check · LP · ([A-D]) · (\d{4}-\d{2}-\d{2})\)", item.get("note", ""))
            ok(m is not None, f"{tag}: the buy carries Edge's estimate as a band ({item.get('note')})")
            if m:
                lo, hi = round(float(m.group(1).replace(",", "")) * 100), round(float(m.group(2).replace(",", "")) * 100)
                w = 200 if lo < 2000 else 500 if lo < 5000 else 1000 if lo < 10000 else 2500
                ok(lo % w == 0 and hi - lo == w and m.group(4) == TODAY, f"{tag}: band on its step, dated today")
            # a sale of it shows up in the comparison
            raw = page.evaluate(f"() => JSON.parse(localStorage.getItem('{LKEY}'))")
            T2 = raw["T"]; T2["sales"].append({"id": "s9", "day": TODAY, "item": item["id"], "book": item["book"], "qty": 1, "plat": "eBay", "price": 4000, "shipIn": 0, "fees": 580, "shipOut": 100, "supplies": 50, "other": 0, "upd": 1})
            seed_ledger(page, T2)
            open_score(page)
            e2 = expect(T2)
            ok(e2["est"]["recorded"] == 3 and len(page.query_selector_all(".sc-est")) == 3, f"{tag}: the new sale is compared with its estimate")
            # a lot's buy carries an estimate per counted card, and per-card prices set the cost split
            LB.open_lots(page)
            page.click("#lot-create"); page.wait_for_selector("#lot-q")
            for c in (LB.IVY, LB.IRON, LB.DUG):
                page.fill("#lot-q", c[2]); page.wait_for_selector(f".lot-s[data-id='{c[0]}']", timeout=8000); page.click(f".lot-s[data-id='{c[0]}']"); page.wait_for_selector(LB.line_sel(c))
            page.click(".lot-add-open"); page.click(".lot-live-open"); page.click(".lot-live-go")
            page.wait_for_function("() => /Done/.test(document.querySelector('.lot-run')?.textContent || '')", timeout=20000)
            page.click("#lot-mode >> text=Price per card"); page.wait_for_selector(".lot-ask")
            for c, a in ((LB.IVY, "12"), (LB.IRON, "8"), (LB.DUG, "2")):
                page.fill(f"{LB.line_sel(c)} .lot-ask", a)
            page.click(".lot-ledger-open"); page.fill(".lot-paid", "22"); page.click(".lot-ledger-go"); page.wait_for_selector("#lf", timeout=10000)
            prices = page.eval_on_selector_all(".lg-line [data-k=price]", "es => es.map(e => e.value)")
            ok(prices == ["12", "8", "2"], f"{tag}: lot cost split by the per-card prices ({prices})")
            n1 = len(page.evaluate(f"() => JSON.parse(localStorage.getItem('{LKEY}')).T.items"))
            page.click("#lf button[type=submit]")
            page.wait_for_function(f"() => JSON.parse(localStorage.getItem('{LKEY}')).T.items.length === {n1 + 3}", timeout=8000)
            notes = page.evaluate(f"() => JSON.parse(localStorage.getItem('{LKEY}')).T.items.slice(-3).map(x => x.note || '')")
            ok(bool(re.search(r"Edge est: net .*\(Lot offer · NM", notes[0])) and bool(re.search(r"\(Lot offer · NM", notes[1])) and notes[2] == "", f"{tag}: estimate on counted cards, none on the $0 card ({notes})")
            raw = page.evaluate("() => Object.keys(localStorage).map(k => localStorage.getItem(k)).join('\\n')")
            ok(not any(w in raw for w in ('"comps"', '"sold_at"', '"median"', '"m90"')), f"{tag}: no sold prices stored")
            ctx.close()
        b.close()
    srv.shutdown()
    ok(not errors, f"page errors: {errors[:3]}")
    print(f"scorecard browser checks: {checks - len(fails)} / {checks} passed")
    for f in fails:
        print("FAIL", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
