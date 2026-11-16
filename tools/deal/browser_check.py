"""Browser checks for the Deal check panel and the experimental trend reading, on a local site copy with
synthetic deal files (tools/deal/make_fixture.js). Nothing is published.
    python3 tools/deal/browser_check.py /tmp/m1site
"""
import functools
import http.server
import json
import os
import re
import subprocess
import sys
import threading

from playwright.sync_api import sync_playwright

DIR = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
checks, fails = 0, []


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=DIR))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def pick_cards():
    """A spread of items: each synthetic kind, cards and sealed, $20+ and under, modern and vintage."""
    picks = {}
    for g in (23821, 23237, 604):
        s = json.load(open(f"{DIR}/data/set/{g}.json"))
        deal = json.load(open(f"{DIR}/data/edge/deal/{g}.json"))["items"]
        for it in s["items"]:
            if not it.get("p") or str(it["id"]) not in deal:
                continue
            kind = deal[str(it["id"])]["kind"]
            band = "hi" if it["p"] >= 2000 else "lo"
            key = (g, kind, it["t"], band)
            if key not in picks or "Umbreon ex - 161/131" in it["n"]:
                picks[key] = (it["id"], g)
    return sorted(set(picks.values()))


def expect(cards, settings=None):
    arg = ",".join(f"{i}:{g}" for i, g in cards)
    cmd = ["node", os.path.join(HERE, "expect.js"), DIR, arg] + ([json.dumps(settings)] if settings else [])
    return json.loads(subprocess.check_output(cmd))


def money(c):
    return f"{'−' if c < 0 else ''}${abs(c) / 100:,.2f}"


def open_card(page, i, g):
    page.evaluate("""([i, g]) => { document.querySelector('#sheet-card').innerHTML = '';
      const b = document.createElement('button'); b.dataset.open = i; b.dataset.g = g; b.dataset.n = ''; b.id = 'tst'; document.body.append(b); b.click(); b.remove(); }""", [i, g])
    page.wait_for_function("() => { const c = document.querySelector('#sheet-card'); return c && !/Loading…/.test(c.textContent) && c.querySelector('.grab') }", timeout=15000)
    page.wait_for_timeout(150)


def check_card(page, i, g, exp, label):
    tag = f"{label} {i}:{g} {exp['name'][:40]}"
    panel = page.query_selector("#c-deal")
    in_scope_data = True
    ok(panel is not None, f"{tag}: deal panel shown")
    if not panel:
        return
    txt = panel.inner_text()
    strat = page.query_selector("#c-strat")
    setup, verdict = (strat.get_attribute("data-setup"), strat.get_attribute("data-verdict")) if strat else (None, None)
    want = exp["verdict"]
    if setup in ("knife", "breakdown") and verdict == "pass":
        want = "pass"
    shown = panel.get_attribute("data-verdict")
    ok(shown == want, f"{tag}: verdict {shown} != {want} ({exp['why']}, setup {setup}/{verdict})")
    head = panel.query_selector(".dl-call b").inner_text()
    ok(head == ("BUY candidate" if want == "buy" else "PASS"), f"{tag}: headline {head!r} for {want}")
    if exp["profit"] is not None:
        ok(money(exp["profit"]).lstrip("−") in txt, f"{tag}: net profit {money(exp['profit'])} shown")
    if exp["max"]:
        ok(f"Offer up to {money(exp['max'])}" in txt, f"{tag}: offer up to {money(exp['max'])}")
    ok(f"Evidence: {exp['confidence']}" in txt, f"{tag}: confidence {exp['confidence']}")
    ok(not re.search(r"undefined|NaN|\bnull\b|Infinity", txt), f"{tag}: a missing number printed")
    ok("SYNTHETIC TEST DATA" in txt, f"{tag}: source label")
    if strat:
        st = strat.inner_text()
        ok("trend reading" in st.lower() and "experimental" in st.lower() and "buy zone" not in st.lower() and "execution:" not in st.lower(), f"{tag}: trend reading labels")
        ok(not page.query_selector("#c-strat .sg-call.sg-buy"), f"{tag}: no buy call in the trend box")
    over = page.evaluate("() => { const W = document.documentElement.clientWidth; return [...document.querySelectorAll('#c-deal *')].filter((e) => e.getBoundingClientRect().right > W + 1).length }")
    ok(over == 0, f"{tag}: {over} elements wider than the screen")


def main():
    srv = serve()
    cards = pick_cards()
    exp = expect(cards)
    print(f"{len(cards)} items:", {k: sum(1 for e in exp.values() if e['kind'] == k) for k in sorted({e['kind'] for e in exp.values()})},
          "buy:", sum(1 for e in exp.values() if e["verdict"] == "buy"))
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for width in (360, 390, 430):
            for theme in ("dark", "light"):
                ctx = b.new_context(viewport={"width": width, "height": 800}, device_scale_factor=2)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
                page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and "fetching the script" not in m.text and errors.append(f"console {m.text}"))
                page.goto(f"http://127.0.0.1:{PORT}/edge/")
                page.evaluate(f"() => {{ localStorage.setItem('dys-theme', '{theme}'); document.documentElement.dataset.theme = '{theme}'; }}")
                page.wait_for_timeout(500)
                for i, g in cards:
                    open_card(page, i, g)
                    check_card(page, i, g, exp[str(i)], f"{width}px {theme}")
                if width == 390 and theme == "dark":
                    # typing a new asking price recomputes
                    i, g = next((c for c in cards if exp[str(c[0])]["kind"] == "good" and exp[str(c[0])]["t"] == "c" and exp[str(c[0])]["p"] >= 2000), cards[0])
                    open_card(page, i, g)
                    page.fill("#c-deal .dl-ask", "1")
                    page.dispatch_event("#c-deal .dl-ask", "change")
                    low = page.get_attribute("#c-deal", "data-verdict")
                    page.fill("#c-deal .dl-ask", str(exp[str(i)]["p"] * 2 / 100))
                    page.dispatch_event("#c-deal .dl-ask", "change")
                    ok(page.get_attribute("#c-deal", "data-verdict") == "pass", "twice the market price is a PASS")
                    ok("Doesn't clear your margin" in page.inner_text("#c-deal") or low == "pass", "margin reason after a higher ask")
                    page.select_option("#c-deal .dl-cond", "DMG")
                    ok("DMG: exit taken at 40%" in page.inner_text("#c-deal"), "condition changes the exit")
                    page.screenshot(path="/tmp/m1-shot-ask.png", full_page=False)
                ctx.close()
        # settings flow into the panel: buyer tax 0, supplies 0, ROI 10
        ctx = b.new_context(viewport={"width": 390, "height": 800})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
        page.goto(f"http://127.0.0.1:{PORT}/edge/")
        page.evaluate("""() => { const k = 'dys-edge-v1', d = JSON.parse(localStorage.getItem(k) || '{}'); d.set = { ...(d.set || {}), buyerTax: 0, supCard: 0, supSealed: 0, roi: 10 }; localStorage.setItem(k, JSON.stringify(d)); }""")
        page.reload()
        page.wait_for_timeout(400)
        exp2 = expect(cards, {"buyerTax": 0, "supCard": 0, "supSealed": 0, "roi": 10})
        for i, g in cards:
            open_card(page, i, g)
            check_card(page, i, g, exp2[str(i)], "settings")
        changed = sum(1 for k in exp if exp[k]["profit"] != exp2[k]["profit"])
        ok(changed > 0, "settings change the numbers")
        # the settings form has the new fields and saves them
        page.evaluate("() => { const c = document.querySelector('#sheet-card .close'); if (c) c.click(); location.hash = '#mine'; }")
        page.wait_for_timeout(600)
        page.evaluate("() => { const b = [...document.querySelectorAll('#m-seg button, #m-seg a')].find((x) => /Settings/.test(x.textContent)); if (b) b.click(); }")
        page.wait_for_timeout(400)
        ok(page.query_selector("#st-btax") is not None and page.query_selector("#st-hold") is not None, "settings show the deal check costs")
        if page.query_selector("#st-btax"):
            page.fill("#st-btax", "9")
            page.evaluate("() => document.querySelector('#st-f').requestSubmit()")
            saved = page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-v1')).set.buyerTax")
            ok(saved == 9, f"buyer tax saved ({saved})")
        ctx.close()
        # fallbacks: no index, then the module missing: no panel, the rest of the sheet works
        for case, route in (("no deal index", "**/data/edge/deal/index.json"), ("deal module missing", "**/assets/edge-deal.js*")):
            ctx = b.new_context(viewport={"width": 390, "height": 800})
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.route(route, lambda r: r.fulfill(status=404, body="no"))
            page.goto(f"http://127.0.0.1:{PORT}/edge/")
            page.wait_for_timeout(400)
            i, g = cards[0]
            open_card(page, i, g)
            ok(page.query_selector("#c-deal") is None, f"{case}: no panel")
            ok(page.query_selector("#c-ta") is not None and "Market" in page.inner_text("#sheet-card"), f"{case}: rest of the sheet")
            ok(not errs, f"{case}: page errors {errs}")
            ctx.close()
        # screenshots for the report
        ctx = b.new_context(viewport={"width": 390, "height": 1600}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(f"http://127.0.0.1:{PORT}/edge/")
        page.wait_for_timeout(400)
        shots = [next((c for c in cards if exp[str(c[0])][k] == v), None) for k, v in (("verdict", "buy"), ("kind", "thin"), ("kind", "falling"))]
        for n, (i, g) in enumerate([c for c in shots if c]):
            open_card(page, i, g)
            el = page.query_selector("#c-deal")
            if el:
                el.screenshot(path=f"/tmp/m1-shot-{n}.png")
        ctx.close()
        b.close()
    srv.shutdown()
    ok(not errors, f"console or page errors: {errors[:5]}")
    print(f"{checks - len(fails)} of {checks} browser checks passed")
    for f in fails[:30]:
        print("  FAIL", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
