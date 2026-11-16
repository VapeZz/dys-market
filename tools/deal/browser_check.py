"""Browser checks for the Deal check (M1) in the real Edge app, on a local site copy, with a synthetic PkmnPrices
relay (tools/deal/make_fixture.js) answered inside the browser. Nothing is published and no real API is called.
    node tools/deal/make_fixture.js /tmp/m1site 23821 23237 604 && python3 tools/deal/browser_check.py /tmp/m1site
"""
import functools
import http.server
import json
import os
import re
import subprocess
import sys
import threading
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

DIR = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
MOCK = json.load(open(f"{DIR}/mock-relay.json"))
RELAY = {"relay": "https://relay.test", "pass": "test-pass"}
checks, fails, calls = 0, [], {"n": 0}


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


def key_of(url):  # same rule as tools/deal/mock_relay.js
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if "tcg_player_id" in q:
        return f"{u.path}|{q['tcg_player_id']}"
    if u.path == "/v1/sealed":
        return f"{u.path}|*"
    if u.path.endswith("/listings/ebay"):
        return f"{u.path}|" + ("sealed" if u.path.startswith("/v1/sealed") else (f"true{q.get('grade')}" if q.get("graded") == "true" else "false"))
    return u.path


CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "X-Edge-Pass, Accept", "Access-Control-Expose-Headers": "x-credits-charged"}


def relay_handler(mode="ok"):
    def h(route):
        req = route.request
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        if mode == "offline":
            return route.abort()
        calls["n"] += 1
        if req.headers.get("x-edge-pass") != "test-pass":
            return route.fulfill(status=401, headers=CORS, body="denied")
        status, body = MOCK["routes"].get(key_of(req.url), [404, {"error": "not found"}])
        n = max(1, len((body or {}).get("data") or []) if isinstance(body, dict) else 1)
        return route.fulfill(status=status, headers={**CORS, "Content-Type": "application/json", "x-credits-charged": str(n)}, body=json.dumps(body))
    return h


def pick_cards():
    picks = {}
    for g in (23821, 23237, 604):
        s = json.load(open(f"{DIR}/data/set/{g}.json"))
        for it in s["items"]:
            if not it.get("p") or str(it["id"]) not in MOCK["kinds"]:
                continue
            key = (g, MOCK["kinds"][str(it["id"])], it["t"], "hi" if it["p"] >= 2000 else "lo")
            if key not in picks or "Umbreon ex - 161/131" in it["n"]:
                picks[key] = (it["id"], g)
    return sorted(set(picks.values()))


def expect(cards, settings=None, owned=None):
    arg = ",".join(f"{i}:{g}" for i, g in cards)
    cmd = ["node", os.path.join(HERE, "expect.js"), DIR, arg, json.dumps(settings) if settings else "-"] + ([json.dumps(owned)] if owned else [])
    return json.loads(subprocess.check_output(cmd))


def money(c):
    return f"{'−' if c < 0 else ''}${abs(c) / 100:,.2f}"


def open_card(page, i, g):
    page.evaluate("""([i, g]) => { document.querySelector('#sheet-card').innerHTML = '';
      const b = document.createElement('button'); b.dataset.open = i; b.dataset.g = g; b.dataset.n = ''; document.body.append(b); b.click(); b.remove(); }""", [i, g])
    page.wait_for_function("() => { const c = document.querySelector('#sheet-card'); return c && !/Loading…/.test(c.textContent) && c.querySelector('.grab') }", timeout=15000)
    page.wait_for_timeout(120)


def load_sold(page):
    page.click("#c-deal .dl-load")
    page.wait_for_function("() => !document.querySelector('#c-deal .dl-beta').textContent.includes('Getting')", timeout=15000)


def check_card(page, i, g, exp, label):
    tag = f"{label} {i}:{g} {exp['name'][:36]}"
    panel = page.query_selector("#c-deal")
    ok(panel is not None, f"{tag}: deal panel shown")
    if not panel:
        return
    ok(panel.get_attribute("data-reason") == "no-data" and "No sold prices yet" in panel.inner_text(), f"{tag}: starts with no sold data")
    load_sold(page)
    panel = page.query_selector("#c-deal")
    txt = panel.inner_text()
    strat = page.query_selector("#c-strat")
    setup, verdict = (strat.get_attribute("data-setup"), strat.get_attribute("data-verdict")) if strat else (None, None)
    flagged = setup in ("knife", "breakdown") and verdict == "pass"
    want = "pass" if flagged else exp["verdict"]
    ok(panel.get_attribute("data-verdict") == want, f"{tag}: verdict {panel.get_attribute('data-verdict')} != {want} ({exp['why']})")
    head = panel.query_selector(".dl-call b").inner_text()
    ok(head == ("BUY candidate" if want == "buy" else "PASS"), f"{tag}: headline {head!r}")
    if not flagged:
        ok(page.inner_text("#c-deal .dl-sum") == exp["summary"], f"{tag}: summary {page.inner_text('#c-deal .dl-sum')!r} != {exp['summary']!r}")
    if exp["found"]:
        ok("Read just now:" in txt and "Kept on this page only" in txt, f"{tag}: data status line")
    else:
        ok("doesn't have this exact item" in txt and panel.get_attribute("data-reason") == "no-data", f"{tag}: not found says so")
    if exp["profit"] is not None:
        ok(money(exp["profit"]).lstrip("−") in txt, f"{tag}: net profit {money(exp['profit'])}")
    if exp["max"]:
        ok(money(exp["max"]) in page.inner_text("#c-deal .dl-tiles"), f"{tag}: max to pay {money(exp['max'])}")
    if exp["reason"] != "no-data":
        ok(f"Evidence: {exp['confidence']}" in txt, f"{tag}: evidence {exp['confidence']}")
    ok(not re.search(r"undefined|NaN|\bnull\b|Infinity", panel.inner_html()), f"{tag}: a missing number printed")
    if strat:
        st = strat.inner_text().lower()
        ok("trend reading" in st and "experimental" in st and "buy zone" not in st, f"{tag}: trend reading labels")
    over = page.evaluate("() => { const W = document.documentElement.clientWidth; return [...document.querySelectorAll('#c-deal *')].filter((e) => e.getBoundingClientRect().right > W + 1).length }")
    ok(over == 0, f"{tag}: {over} elements wider than the screen")


def new_page(b, width, theme="dark", relay=RELAY, mode="ok", errors=None, inv=None):
    ctx = b.new_context(viewport={"width": width, "height": 800}, device_scale_factor=2, has_touch=True)
    page = ctx.new_page()
    if errors is not None:
        page.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
        page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and "fetching the script" not in m.text and errors.append(f"console {m.text}"))
    page.route("https://relay.test/**", relay_handler(mode))
    page.goto(f"http://127.0.0.1:{PORT}/edge/")
    page.evaluate("""([theme, relay, inv]) => { localStorage.setItem('dys-theme', theme); document.documentElement.dataset.theme = theme;
      if (relay) localStorage.setItem('dys-edge-relay', JSON.stringify(relay)); else localStorage.removeItem('dys-edge-relay');
      if (inv) { const d = JSON.parse(localStorage.getItem('dys-edge-v1') || '{}'); d.inv = inv; localStorage.setItem('dys-edge-v1', JSON.stringify(d)); } }""", [theme, relay, inv])
    page.reload()
    page.wait_for_timeout(400)
    return ctx, page


def main():
    srv = serve()
    cards = pick_cards()
    exp = expect(cards)
    kinds = {}
    for e in exp.values():
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"{len(cards)} items {kinds}; buy {sum(e['verdict'] == 'buy' for e in exp.values())}")
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for width in (360, 390, 430):
            for theme in ("dark", "light"):
                ctx, page = new_page(b, width, theme, errors=errors)
                for i, g in cards:
                    open_card(page, i, g)
                    check_card(page, i, g, exp[str(i)], f"{width}px {theme}")
                if width == 390 and theme == "dark":
                    # the three situations: card show price, online deal with shipping, condition
                    i, g = next(c for c in cards if exp[str(c[0])]["verdict"] == "buy" and exp[str(c[0])]["t"] == "c")
                    e = exp[str(i)]
                    open_card(page, i, g)
                    before = calls["n"]
                    ok(page.get_attribute("#c-deal", "data-verdict") == "buy", "a second open in the same page shows the sold prices already read")
                    ok(calls["n"] == before, "and makes no new calls")
                    page.fill("#c-deal .dl-ask", f"{e['max'] / 100:.2f}"); page.dispatch_event("#c-deal .dl-ask", "change")
                    ok(page.get_attribute("#c-deal", "data-verdict") == "buy", "paying exactly the max is still a BUY candidate")
                    page.fill("#c-deal .dl-ship", "5"); page.dispatch_event("#c-deal .dl-ship", "change")
                    ok(page.get_attribute("#c-deal", "data-verdict") == "pass" and "Doesn't clear your margin" in page.inner_text("#c-deal"), "adding $5 shipping to the max tips it to PASS")
                    page.fill("#c-deal .dl-ship", "0"); page.dispatch_event("#c-deal .dl-ship", "change")
                    page.select_option("#c-deal .dl-cond", "HP")
                    ok(page.get_attribute("#c-deal", "data-verdict") == "pass", "a heavily played copy at the NM max is a PASS")
                    page.click("#c-deal .dl-more > summary")
                    ok("sold comps" in page.inner_text("#c-deal").lower() and "marketplace fee" in page.inner_text("#c-deal").lower(), "details open")
                ctx.close()
        # not set up, wrong passphrase, offline
        for case, relay, mode, words in (("not set up", None, "ok", "aren't set up yet"), ("wrong passphrase", {"relay": "https://relay.test", "pass": "nope"}, "ok", "refused the passphrase"),
                                         ("offline", RELAY, "offline", "No connection")):
            errs = []
            ctx, page = new_page(b, 390, relay=relay, mode=mode, errors=errs)
            i, g = cards[0]
            open_card(page, i, g)
            if relay:
                load_sold(page)
            t = page.inner_text("#c-deal")
            ok(words in t and page.get_attribute("#c-deal", "data-verdict") == "pass" and page.get_attribute("#c-deal", "data-reason") == "no-data", f"{case}: says so and stays PASS ({t[:200]!r})")
            ok(page.query_selector("#c-ta") is not None, f"{case}: rest of the sheet works")
            ok(not [e for e in errs if "pageerror" in e], f"{case}: page errors {errs}")
            ctx.close()
        # my collection: sell, grade or keep
        owned_cards = [c for c in cards if exp[str(c[0])]["t"] == "c"][:10]
        owned = {str(i): [int(exp[str(i)]["p"] * (0.3 if n % 2 else 0.9)), "NM"] for n, (i, g) in enumerate(owned_cards)}
        exp_own = expect(owned_cards, None, owned)
        inv = []
        for i, g in owned_cards:
            s = json.load(open(f"{DIR}/data/set/{g}.json"))
            it = next(x for x in s["items"] if x["id"] == i)
            inv.append({"k": f"{i}|{it['n']}", "id": i, "g": g, "n": it["n"], "t": it["t"], "qty": 1, "cost": owned[str(i)][0], "cond": "NM", "at": "2026-11-16"})
        errs = []
        ctx, page = new_page(b, 390, inv=inv, errors=errs)
        page.evaluate("() => { location.hash = '#mine'; }")
        page.wait_for_timeout(600)
        page.click("#own-go")
        page.wait_for_function("() => /Checked \\d+ item/.test((document.querySelector('#own-st') || {}).textContent || '')", timeout=30000)
        labels = {"sell": "Sell clears your target", "grade": "Grading looks better", "hold": "Keep for now", "unclear": "Not enough sales", "unknown": "No sold data"}
        seen = {}
        for i, g in owned_cards:
            row = page.query_selector(f".row[data-open='{i}'] .own-res")
            e, found = exp_own[str(i)]["own"], exp_own[str(i)]["found"]
            t = row.inner_text() if row else ""
            want = labels[e["label"]] if found else labels["unknown"]
            seen[e["label"] if found else "unknown"] = 1
            ok(row is not None and t.startswith(want) and (not found or e["text"] in t), f"collection {i}: {t!r} vs {want} {e['text']!r}")
        ok(len(seen) >= 3, f"collection covers several outcomes: {sorted(seen)}")
        page.screenshot(path="/tmp/m1-shot-own.png", full_page=True)
        ok(not [e for e in errs if "pageerror" in e], f"collection: page errors {errs}")
        # settings: the relay form saves, tests and refuses a bad address
        page.evaluate("() => { const b = [...document.querySelectorAll('#m-seg button, #m-seg a')].find((x) => /Settings/.test(x.textContent)); if (b) b.click(); }")
        page.wait_for_timeout(400)
        ok(page.query_selector("#rl-u") is not None and page.input_value("#rl-u") == "https://relay.test", "settings show the saved relay")
        page.click("#rl-t")
        page.wait_for_function("() => !/Testing/.test(document.querySelector('#rl-st').textContent)", timeout=10000)
        ok("Connected" in page.inner_text("#rl-st"), f"relay test: {page.inner_text('#rl-st')!r}")
        page.fill("#rl-u", "http://insecure.example")
        page.evaluate("() => document.querySelector('#rl-f').requestSubmit()")
        ok("Needs an https address" in page.inner_text("#rl-st"), "an http address is refused")
        backup = page.evaluate("() => JSON.stringify(JSON.parse(localStorage.getItem('dys-edge-v1')))")
        ok("test-pass" not in backup and "relay.test" not in backup, "the relay is not in Edge's backup data")
        ctx.close()
        # screenshots for the report
        ctx, page = new_page(b, 390)
        shots = [next((c for c in cards if exp[str(c[0])][k] == v), None) for k, v in (("verdict", "buy"), ("kind", "thin"), ("kind", "none"))]
        for n, c in enumerate([c for c in shots if c]):
            open_card(page, *c)
            load_sold(page)
            page.query_selector("#c-deal").screenshot(path=f"/tmp/m1-shot-{n}.png")
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
