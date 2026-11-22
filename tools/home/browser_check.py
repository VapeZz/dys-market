"""Browser checks for the command center (top of Today) and Show check → lot, in the real Edge app on a local site copy
with the synthetic relay (sold prices and the finder route). Synthetic data only; nothing real is called.
    python3 tools/home/browser_check.py <site copy made by tools/deal/make_fixture.js, with tools/lot's extra row>
"""
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../lot"))
import browser_check as LB
from playwright.sync_api import sync_playwright

DIR, PORT = LB.DIR, LB.PORT
PHONE = json.load(open(f"{DIR}/finder-phone.json"))
checks, fails = 0, []


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)


def relay(route):
    if route.request.url.rstrip("/").endswith("/edge/finder"):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=LB.CORS)
        LB.calls["finder"] = LB.calls.get("finder", 0) + 1
        return route.fulfill(status=200, headers={**LB.CORS, "Content-Type": "application/json"}, body=json.dumps({**PHONE, "release": "finder-phone-test"}))
    return LB.relay(route)


def load_score_sample():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sc_bc", os.path.join(os.path.dirname(os.path.abspath(__file__)), "../score/browser_check.py"))
    m = importlib.util.module_from_spec(spec); sys_argv = sys.argv; spec.loader.exec_module(m); sys.argv = sys_argv
    return m


def main():
    LB.prepare_site()
    srv = LB.serve()
    errors = []
    S = load_score_sample()
    T = S.sample()
    e30 = S.expect(T, period="d30")
    est = json.loads(__import__("subprocess").check_output(["node", os.path.join(LB.ROOT, "tools/buylist/expect_est.js"), DIR, f"{LB.IVY[0]}:{LB.IVY[1]}"]))[str(LB.IVY[0])]["est"]
    sets = {g: json.load(open(f"{DIR}/data/set/{g}.json")) for g in (LB.IVY[1], LB.IRON[1])}
    item = lambda c: next(it for it in sets[c[1]]["items"] if it["id"] == c[0])
    ivy, iron = item(LB.IVY), item(LB.IRON)
    now = int(time.time() * 1000)
    bl = {"v": 1, "items": [{"k": f"{ivy['id']}|{ivy['n']}", "id": ivy["id"], "g": LB.IVY[1], "n": ivy["n"], "setN": "151", "t": "c", "r": "", "cond": "NM", "added": now, "est": est},
                            {"k": f"{iron['id']}|{iron['n']}", "id": iron["id"], "g": LB.IRON[1], "n": iron["n"], "setN": "x", "t": "c", "r": "", "cond": "NM", "added": now}]}
    lots = {"v": 1, "lots": [{"id": "lot1", "name": "Blue binder", "created": now, "askMode": "total", "lines": []}, {"id": "lot2", "name": "Box", "created": now - 1000, "askMode": "total", "lines": []}]}
    watch = [{"k": f"{ivy['id']}|{ivy['n']}", "id": ivy["id"], "g": LB.IVY[1], "n": ivy["n"], "t": "c", "target": 999999},
             {"k": f"{iron['id']}|{iron['n']}", "id": iron["id"], "g": LB.IRON[1], "n": iron["n"], "t": "c", "target": 1}]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for width, theme in ((390, "dark"), (360, "light")):
            tag = f"{width} {theme}"
            ctx, page = LB.new_page(b, width, theme, errors=errors)
            page.unroute("https://relay.test/**"); page.route("https://relay.test/**", relay)
            n_open = LB.calls["n"]
            # an empty phone first
            S.seed_ledger(page, {"buys": [], "items": [], "sales": [], "costs": [], "cash": []})
            page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.reload(); page.wait_for_selector(".hm-tile")
            t0 = {e.get_attribute("data-k"): e.inner_text().replace("\n", " | ") for e in page.query_selector_all(".hm-tile")}
            ok("Plan a show" in t0["buylist"] and "Binder or stack" in t0["lots"] and "No cards" in t0["watch"] and "No sales yet" in t0["profit"], f"{tag}: empty tiles {t0}")
            ok("Latest run" in t0["daily"] and LB.calls.get("finder", 0) == 0 and LB.calls["n"] == n_open, f"{tag}: opening Today calls nothing ({t0['daily']})")
            ok("Nothing held" in t0["sell"] or "Review holdings" in t0["sell"], f"{tag}: Sell tile with nothing reviewed ({t0['sell']})")
            ok(page.evaluate("() => localStorage.getItem('dys-edge-lots')") is None, f"{tag}: looking at Today writes no lot record (the Buy list's own start-up write is older)")
            ok("$75.00 most per buy" in page.inner_text(".hm-rules") and "keep $100.00" in page.inner_text(".hm-rules"), f"{tag}: rules shown")
            # a filled phone
            page.evaluate("([bl, lots, watch]) => { localStorage.setItem('dys-edge-buylist', JSON.stringify(bl)); localStorage.setItem('dys-edge-lots', JSON.stringify(lots)); const s = JSON.parse(localStorage.getItem('dys-edge-v1') || '{}'); s.watch = watch; localStorage.setItem('dys-edge-v1', JSON.stringify(s)); }", [bl, lots, watch])
            S.seed_ledger(page, T)
            page.reload(); page.wait_for_selector(".hm-tile")
            tl = {e.get_attribute("data-k"): e.inner_text().replace("\n", " | ") for e in page.query_selector_all(".hm-tile")}
            ok("2 cards" in tl["buylist"] and "1 with fresh prices" in tl["buylist"], f"{tag}: buy list tile {tl['buylist']}")
            ok("2 lots" in tl["lots"], f"{tag}: lots tile {tl['lots']}")
            ok("1 at target" in tl["watch"] and "of 2 watched" in tl["watch"] and "not sold-checked" in tl["watch"], f"{tag}: watchlist tile {tl['watch']}")
            ok("1 item" in tl["held"] and "$23.35 cost" in tl["held"], f"{tag}: inventory tile {tl['held']}")
            ok(S.signed(e30["total"]["profit"]) in tl["profit"] and f"{e30['total']['sales']} sales · realized" in tl["profit"], f"{tag}: profit tile {tl['profit']} vs {S.signed(e30['total']['profit'])}")
            # tiles open the right screens
            for k, sel in (("buylist", ".bl-addp, .bl-list, #bl-prep, .bl-row"), ("lots", ".lot-new, .lot-pick"), ("daily", ".dd-sec, .dd-row, .dd-head, #dd")):
                page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.wait_for_selector(".hm-tile"); page.click(f".hm-tile[data-k={k}]")
                page.wait_for_selector("#d-seg", timeout=10000); page.wait_for_timeout(800)
                active = page.eval_on_selector("#d-seg", "e => (e.querySelector('[aria-pressed=true], .on, .active')||{}).textContent || ''")
                ok(active == {"buylist": "Buy list", "lots": "Lot offer", "daily": "Daily deals"}[k], f"{tag}: {k} tile opens {active}")
            for k, want in (("watch", "Watchlist"), ("held", "Ledger"), ("profit", "Scorecard")):
                page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.wait_for_selector(".hm-tile"); page.click(f".hm-tile[data-k={k}]")
                page.wait_for_selector("#m-seg", timeout=10000); page.wait_for_timeout(600)
                active = page.eval_on_selector("#m-seg", "e => (e.querySelector('[aria-pressed=true], .on, .active')||{}).textContent || ''")
                ok(active == want, f"{tag}: {k} tile opens {active}")
            # after Daily deals was opened this visit, the tile shows its counts (no new call), never a BUY
            page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.wait_for_selector(".hm-tile")
            dt = page.inner_text(".hm-tile[data-k=daily]").replace("\n", " | ")
            ok("2 leads" in dt and "7 worth a look" in dt and "not verified" in dt and "BUY" not in dt, f"{tag}: Daily deals tile after a visit ({dt})")
            # check a buy: search → Show check with the card picked
            page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.wait_for_selector("#hm-q")
            page.fill("#hm-q", LB.IRON[2]); page.wait_for_selector(f".hm-hit[data-id='{LB.IRON[0]}']", timeout=8000)
            n_before = LB.calls["n"]
            page.click(f".hm-hit[data-id='{LB.IRON[0]}']")
            page.wait_for_function("() => /Sold prices read today/.test(document.querySelector('#sc-deal .dl-beta')?.textContent || '')", timeout=20000)
            ok(page.input_value("#sc-q").lower().startswith("iron crown ex"), f"{tag}: Show check opened with the card")
            # Show check → lot: same sold prices reused, no new reads
            page.select_option("#sc-deal .dl-cond", "LP"); page.wait_for_timeout(200)
            n_mid = LB.calls["n"]
            page.click("#sc-card .sc-lot"); page.wait_for_selector(".lot-top", timeout=10000)
            ok(page.input_value(".lot-title") == "Blue binder", f"{tag}: added to the newest lot")
            row = LB.line_sel(LB.IRON)
            ok(page.query_selector(row) is not None and page.eval_on_selector(f"{row} .lot-cond", "e => e.value") == "LP", f"{tag}: card added in LP")
            ok(LB.calls["n"] == n_mid, f"{tag}: no new sold-price reads for the lot ({LB.calls['n'] - n_mid})")
            ok(page.eval_on_selector("[data-live]", "e => +e.dataset.live") == 1, f"{tag}: the card counts as checked live")
            ok(int(page.get_attribute(row, "data-value")) > 0 or page.get_attribute(row, "data-flags") != "", f"{tag}: card valued from Show check's prices")
            raw = page.evaluate("() => Object.keys(localStorage).map(k => localStorage.getItem(k)).join('\\n')")
            ok(not any(w in raw for w in ('"comps"', '"sold_at"', '"median"', '"m90"')), f"{tag}: no sold prices stored")
            led = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-ledger')).T")
            ok(len(led["buys"]) == len(T["buys"]) and len(led["sales"]) == len(T["sales"]), f"{tag}: Ledger unchanged")
            page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.wait_for_selector(".hm-tile")
            ok(page.evaluate("() => document.documentElement.scrollWidth") <= width, f"{tag}: no sideways scroll")
            page.screenshot(path=f"/tmp/home-{width}.png")
            # Deals: the four buying tools first; the older lists under More lists, still working
            page.goto(f"http://127.0.0.1:{PORT}/edge/#deals"); page.wait_for_selector("#d-seg")
            labels = page.eval_on_selector_all("#d-seg button", "bs => bs.map(b => b.textContent)")
            ok(labels == ["Show check", "Buy list", "Lot offer", "Daily deals", "More lists"], f"{tag}: Deals tabs {labels}")
            ok(page.is_hidden("#d-seg2"), f"{tag}: older lists hidden until asked")
            page.click("#d-seg >> text=More lists"); page.wait_for_selector("#d-seg2s button")
            old_tabs = page.eval_on_selector_all("#d-seg2s button", "bs => bs.map(b => b.textContent)")
            ok(old_tabs == ["Flips", "Momentum", "Dips", "Under market", "Movers", "Falling", "My store"], f"{tag}: older lists {old_tabs}")
            ok("Not checked against sold prices" in page.inner_text("#d-seg2"), f"{tag}: older lists labelled")
            for t in ("Flips", "Under market", "Movers", "Falling"):
                page.click(f"#d-seg2s >> text={t}"); page.wait_for_function("() => !/Loading/.test(document.querySelector('#d-list').innerText)", timeout=10000)
                ok(len(page.inner_text("#d-list").strip()) > 10 and not page.is_hidden("#d-game"), f"{tag}: {t} still works")
            page.click("#d-seg >> text=Show check"); page.wait_for_selector("#sc-q")
            ok(page.is_hidden("#d-seg2"), f"{tag}: back to a buying tool hides the older lists")
            page.click("#d-seg >> text=More lists"); page.wait_for_selector("#d-seg2s button")
            ok(page.eval_on_selector("#d-seg2s", "e => (e.querySelector('[aria-pressed=true], .on, .active')||{}).textContent || ''") == "Falling", f"{tag}: More lists reopens the last list")
            # one shared cash on hand: set on the command center, seen and edited in Show check, Lot offer and the Buy list
            led0 = page.evaluate("() => localStorage.getItem('dys-edge-ledger')")
            page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.wait_for_selector(".hm-cash-in")
            ok(page.input_value(".hm-cash-in") == "" and page.evaluate("() => localStorage.getItem('dys-edge-cash')") is None, f"{tag}: cash not set, nothing saved")
            ok("not your bank or Ledger cash" in page.inner_text(".hm-cash"), f"{tag}: cash labelled")
            page.fill(".hm-cash-in", "300"); page.dispatch_event(".hm-cash-in", "change"); page.wait_for_timeout(150)
            cj = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-cash'))")
            ok(cj["c"] == 30000 and abs(cj["at"] - time.time() * 1000) < 60000 and set(cj) == {"v", "c", "at"}, f"{tag}: cash saved on the phone {cj}")
            ok("Set " in page.inner_text(".hm-cash-note"), f"{tag}: shows when it was set")
            # Show check
            page.fill("#hm-q", LB.IVY[2]); page.wait_for_selector(f".hm-hit[data-id='{LB.IVY[0]}']", timeout=8000); page.click(f".hm-hit[data-id='{LB.IVY[0]}']")
            page.wait_for_function("() => /Sold prices read today/.test(document.querySelector('#sc-deal .dl-beta')?.textContent || '')", timeout=20000)
            ok(page.input_value("#sc-deal .dl-cash") == "300" and "not your bank or Ledger cash" in page.inner_text("#sc-deal"), f"{tag}: Show check uses the shared cash")
            # typing on while the check redraws keeps the digits in order (cursor stays at the end)
            page.fill("#sc-deal .dl-ask", ""); page.click("#sc-deal .dl-ask"); page.keyboard.type("1"); page.dispatch_event("#sc-deal .dl-ask", "change"); page.wait_for_timeout(150)
            page.keyboard.type("5"); page.wait_for_timeout(100)
            ok(page.input_value("#sc-deal .dl-ask") in ("15", "15.00"), f"{tag}: typing across a redraw keeps order ({page.input_value('#sc-deal .dl-ask')})")
            page.click("#sc-deal .dl-cash"); page.wait_for_timeout(150)   # tap the box first (leaving the price box redraws the check)
            page.fill("#sc-deal .dl-cash", "250"); page.dispatch_event("#sc-deal .dl-cash", "change"); page.wait_for_timeout(200)
            # Lot offer sees the edit
            LB.open_lots(page); page.click(".lot-pick"); page.wait_for_selector(".lot-top")
            ok(page.input_value(".lot-cash") == "250", f"{tag}: Lot offer sees the Show check edit ({page.input_value('.lot-cash')})")
            page.fill(".lot-cash", "220"); page.wait_for_timeout(150)
            # Buy list's at-the-table panel sees it
            page.click("#d-seg >> text=Buy list"); page.wait_for_selector(".bl-row")
            page.click(".bl-row .bl-head"); page.wait_for_selector(".bl-cash")
            ok(page.input_value(".bl-cash") == "220", f"{tag}: Buy list sees the lot edit ({page.input_value('.bl-cash')})")
            page.fill(".bl-cash", ""); page.wait_for_timeout(150)
            ok(page.evaluate("() => localStorage.getItem('dys-edge-cash')") is None, f"{tag}: clearing it clears it everywhere")
            page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.wait_for_selector(".hm-cash-in")
            ok(page.input_value(".hm-cash-in") == "", f"{tag}: command center shows it cleared")
            # an old number (over 12 hours) never confirms the reserve
            page.evaluate("() => localStorage.setItem('dys-edge-cash', JSON.stringify({ v: 1, c: 50000, at: Date.now() - 13 * 36e5 }))")
            page.reload(); page.wait_for_selector(".hm-cash-in")
            ok(page.input_value(".hm-cash-in") == "", f"{tag}: cash older than 12 hours isn't used")
            LB.open_lots(page); page.click(".lot-pick"); page.wait_for_selector(".lot-top")
            page.fill(".lot-total", "5"); page.wait_for_timeout(150)
            res = page.eval_on_selector("#lot-out", "e => e.dataset.result")
            ok(res in ("need-cash", "need-prices", "no-value", "over"), f"{tag}: lot with expired cash isn't a BUY ({res})")
            ok(page.evaluate("() => localStorage.getItem('dys-edge-ledger')") == led0, f"{tag}: Ledger unchanged by the cash entry")
            # unpaired: the Daily deals tile says so and reads nothing
            page.evaluate("() => localStorage.removeItem('dys-edge-relay')"); f0 = LB.calls.get("finder", 0)
            page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.reload(); page.wait_for_selector(".hm-tile")
            ok("Not set up" in page.inner_text(".hm-tile[data-k=daily]") and LB.calls.get("finder", 0) == f0, f"{tag}: unpaired Daily deals tile")
            LB.calls["finder"] = 0
            ctx.close()
        b.close()
    srv.shutdown()
    ok(not errors, f"page errors: {errors[:3]}")
    print(f"command center browser checks: {checks - len(fails)} / {checks} passed")
    for f in fails:
        print("FAIL", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
