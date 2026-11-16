"""Browser checks for the Ledger (M2) in the real Edge app, on a local site copy, with the real Sheet script
(tools/ledger/Code.gs) running on an emulated Sheet (mock_sheet.js) behind a stand-in web app address.
Nothing is published and no Google service is called.
    python3 tools/ledger/browser_check.py /tmp/m2site
(the site copy needs data/ for sets 23821 and 23237, and assets/ + edge/ from this branch)
"""
import functools
import hashlib
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

from playwright.sync_api import sync_playwright

DIR = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
PORT, SHEET_PORT = 8765, 8767
URL = "https://script.google.com/macros/s/TESTLEDGER/exec"
TOKEN = "5e" * 32
checks, fails = 0, []
UMB = {"k": "610516|Umbreon ex - 161/131 (Holofoil)", "id": 610516, "g": 23821, "n": "Umbreon ex - 161/131 (Holofoil)", "t": "c", "qty": 1, "cost": 80000, "cond": "NM", "at": "2026-10-01"}
ETB = {"k": "593324|Prismatic Evolutions Pokemon Center Elite Trainer Box (Exclusive)", "id": 593324, "g": 23821, "n": "Prismatic Evolutions Pokemon Center Elite Trainer Box (Exclusive)", "t": "s", "qty": 2, "cost": 30000, "cond": "NM", "at": "2026-11-01"}


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        fails.append(what)
        print("FAIL", what)


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=DIR))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def sheet(path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{SHEET_PORT}{path}", data=None if body is None else body.encode(), method="GET" if body is None else "POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


MODE = {"m": "ok"}


def ledger_route(route):
    if MODE["m"] == "offline":
        return route.abort()
    req = route.request
    data = req.post_data or ""
    r = urllib.request.Request(f"http://127.0.0.1:{SHEET_PORT}/exec", data=data.encode() if req.method == "POST" else None, method=req.method)
    try:
        with urllib.request.urlopen(r) as res:
            return route.fulfill(status=res.status, headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}, body=res.read())
    except urllib.error.HTTPError as e:
        return route.fulfill(status=e.code, headers={"Access-Control-Allow-Origin": "*"}, body=e.read())


def money(c):
    return f"{'−' if c < 0 else ''}${abs(c) / 100:,.2f}"


def whole(c):
    return f"{'−' if c < 0 else ''}${round(abs(c) / 100):,}"


def tab(dump, name):
    rows = dump["tabs"].get(name) or []
    if not rows:
        return []
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:]]


def no_junk(page, where):
    html = page.inner_html("#m-body")
    ok(not re.search(r"undefined|NaN|\bnull\b|Infinity|\[object", html), f"{where}: a missing value printed")
    over = page.evaluate("() => { const W = document.documentElement.clientWidth; return [...document.querySelectorAll('#m-body *')].filter((e) => { const r = e.getBoundingClientRect(); return r.width && r.right > W + 1 }).map((e) => e.className || e.tagName).slice(0, 3) }")
    ok(not over, f"{where}: wider than the screen {over}")


def tiles(page):
    return {t.query_selector(".lab").text_content().strip(): t.query_selector("b").text_content().strip() for t in page.query_selector_all(".lg-tiles .tile")}


def wait_synced(page, timeout=8000):
    page.wait_for_function("() => { try { const d = JSON.parse(localStorage.getItem('dys-edge-ledger')); return d && d.q.length === 0 && d.pulled > 0 } catch { return false } }", timeout=timeout)


def toast(page, want):
    try:
        page.wait_for_function("(w) => { const t = document.querySelector('#toast'); return t && !t.hidden && t.textContent.includes(w) }", arg=want, timeout=4000)
    except Exception:
        pass
    return page.text_content("#toast")


def compute_in_page(page, year="2026"):
    return page.evaluate("""(y) => { const d = JSON.parse(localStorage.getItem('dys-edge-ledger')); return EdgeLedger.compute(d.T, { year: y }) }""", year)


def run(page, width, theme):
    tag = f"{width}px {theme}"
    page.set_viewport_size({"width": width, "height": 860})
    page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
    page.wait_for_selector("#m-seg button", timeout=15000)
    segs = [b.inner_text() for b in page.query_selector_all("#m-seg button")]
    ok(segs == ["Inventory", "Ledger", "Watchlist", "Settings"], f"{tag}: Mine tabs {segs}")
    # the old inventory is still shown, with the move note
    inv_txt = page.inner_text("#m-body")
    ok("Your ledger is ready" in inv_txt and "Umbreon ex" in inv_txt, f"{tag}: old inventory with the move note")
    value_before = page.inner_text(".tiles .tile b")
    page.click("#inv-move")
    page.wait_for_selector(".lg-move", timeout=5000)
    ok("2 inventory items" in page.inner_text(".lg-move"), f"{tag}: move offer counts 2 items")
    page.click(".lg-move [data-b=Business]")
    ok("2 items moved into Business" in toast(page, "moved"), f"{tag}: move toast")
    wait_synced(page)
    d = sheet("/dump")
    items = tab(d, "Items")
    ok(len(items) == 2 and all(i["Book"] == "Business" for i in items), f"{tag}: 2 items in the Sheet, Business")
    umb = next((i for i in items if i["Item"].startswith("Umbreon")), {})
    ok(umb.get("Price each") == 800 and umb.get("Acquired") == "2026-10-01" and umb.get("Cost each") == 800 and umb.get("Qty held") == 1, f"{tag}: Umbreon row {umb}")
    etb = next((i for i in items if "Elite Trainer" in i["Item"]), {})
    ok(etb.get("Qty") == 2 and etb.get("Type") == "Sealed" and etb.get("Price each") == 300, f"{tag}: ETB row")
    ok(page.evaluate("() => JSON.parse(localStorage.getItem('dys-edge-v1')).inv.length") == 0, f"{tag}: old list emptied")
    # Inventory now reads the ledger: same value as before
    page.click("#m-seg button:has-text('Inventory')")
    page.wait_for_selector(".tiles .tile b")
    ok(page.inner_text(".tiles .tile b") == value_before, f"{tag}: inventory value unchanged after the move ({value_before})")
    ok("Your ledger is ready" not in page.inner_text("#m-body"), f"{tag}: move note gone")
    no_junk(page, f"{tag} inventory")

    # Bought it from a card sheet: the buy form opens with the card at its lowest listing
    page.evaluate("""() => { const b = document.createElement('button'); b.dataset.open = 610516; b.dataset.g = 23821; b.dataset.n = 'Umbreon ex - 161/131 (Holofoil)'; document.body.append(b); b.click(); b.remove(); }""")
    page.wait_for_selector("#c-buy", timeout=15000)
    ok("you hold 1" in page.inner_text("#c-buy"), f"{tag}: card sheet shows 1 held")
    page.click("#c-buy")
    page.wait_for_selector("#lf .lg-line", timeout=8000)
    ok(page.input_value("[data-line='0'] [data-k=price]") == "949.47", f"{tag}: line price starts at the lowest listing")
    page.fill("[data-line='0'] [data-k=price]", "900")
    page.fill("#lf-tax", "75.38")
    page.select_option("#lf-where", "Card show")
    page.fill("#lf-from", "Table 12")
    ok("$975.38" in page.inner_text(".lg-total"), f"{tag}: buy total live")
    page.click("#lf button[type=submit]")
    tt = toast(page, "Saved: 1"); ok("Saved: 1 item, $975.38" in tt, f"{tag}: buy saved toast {tt!r}")

    # a buy built from search: one card from Edge plus one thing Edge doesn't track
    page.click("[data-a=buy]")
    page.wait_for_selector("#lf")
    page.click("[data-a=pick]")
    page.wait_for_selector(".pickbar", timeout=8000)
    ok("this buy" in page.inner_text(".pickbar"), f"{tag}: pick bar names the buy")
    page.fill("#q", "espeon ex")
    page.wait_for_function("() => { const r = document.querySelector('#s-res'); return r && !/Recently viewed/.test(r.textContent) && r.querySelector('.row') }", timeout=8000)
    page.click("#s-res .row >> nth=0")
    ok("Added to this buy (1)" in toast(page, "Added"), f"{tag}: picked a card")
    picked = page.evaluate("() => (JSON.parse(localStorage.getItem('dys-edge-v1')).recent || []).length") and None
    page.click("#pick-done")
    page.wait_for_selector("#lf .lg-line", timeout=8000)
    ok(len(page.query_selector_all("#lf .lg-line")) == 1, f"{tag}: back in the buy with 1 line")
    picked = page.text_content("#lf .lg-line .lg-lh b").strip()
    page.click("[data-a=addline]")
    page.fill("[data-line='0'] [data-k=price]", "45")
    page.fill("[data-line='1'] [data-k=name]", "Pop Mart Labubu, Big Into Energy")
    page.select_option("[data-line='1'] [data-k=kind]", "Other")
    page.fill("[data-line='1'] [data-k=price]", "30")
    page.fill("[data-line='1'] [data-k=qty]", "2")
    page.fill("#lf-ship", "7.50")
    ok("$112.50" in page.inner_text(".lg-total"), f"{tag}: two-line total")
    page.click("#lf button[type=submit]")
    tt = toast(page, "Saved: 2"); ok("Saved: 2 items, $112.50" in tt, f"{tag}: two-line buy saved {tt!r}")

    # a sale: fees start at Edge's estimate, the profit shows before saving
    page.click("[data-a=sell]")
    page.wait_for_selector("[data-item]")
    page.click("[data-item]:has-text('Umbreon ex - 161/131') >> nth=0")
    page.wait_for_selector("#lf-price")
    page.fill("#lf-price", "1200")
    page.wait_for_timeout(50)
    fee = page.input_value("#lf-fees")
    ok(fee == "171.33", f"{tag}: eBay fee estimate: 13.25% of $1,290 ($1,200 + 7.5% tax) + $0.40 ({fee})")
    page.fill("#lf-fees", "158.40")
    page.fill("#lf-shipout", "5.25")
    page.fill("#lf-sup", "1")
    out = page.inner_text("#lf-out")
    ok("$1,035.35" in out, f"{tag}: net shown ({out})")
    page.click("#lf button[type=submit]")
    t = toast(page, "Sale saved")
    ok("Sale saved" in t, f"{tag}: sale toast {t}")

    # expense, starting cash
    page.click("[data-a=cost]")
    page.select_option("#lf-kind", "Show table")
    page.fill("#lf-amt", "75")
    page.click("#lf button[type=submit]")
    ok("Expense saved" in toast(page, "Expense"), f"{tag}: expense")
    page.click("[data-a=cash]")
    page.fill("#lf-amt", "2000")
    page.click("#lf button[type=submit]")
    wait_synced(page)

    # what Edge shows agrees with the engine and with the Sheet
    R = compute_in_page(page)
    b = R["tot"]["Business"]
    tl = tiles(page)
    ok(tl.get("Cash") == whole(b["cash"]), f"{tag}: Cash tile {tl.get('Cash')} vs {whole(b['cash'])}")
    ok(tl.get("Holding") == whole(b["costHeld"]), f"{tag}: Holding tile")
    ok(tl.get("Profit 2026", "") == "+" + whole(b["realized"]), f"{tag}: Profit tile {tl.get('Profit 2026')} vs {whole(b['realized'])}")
    d = sheet("/dump")
    sales = tab(d, "Sales")
    ok(len(sales) == 1 and sales[0]["Net"] == 1035.35 and sales[0]["Sold on"] == "eBay", f"{tag}: sale in the Sheet {sales}")
    s0 = R["sales"][0]
    ok(abs(sales[0]["Profit"] * 100 - s0["profit"]) < 0.5 and abs(sales[0]["Cost"] * 100 - s0["cost"]) < 0.5, f"{tag}: Sheet profit and cost match Edge")
    buys = tab(d, "Buys")
    ok(sorted(round(x["Total"] * 100) for x in buys) == sorted([97538, 11250]), f"{tag}: buy totals in the Sheet {[x['Total'] for x in buys]}")
    lab = next((i for i in tab(d, "Items") if i["Item"].startswith("Pop Mart")), {})
    # $7.50 shipping split 45 : 60 by price → $4.29 on the two Labubu → $64.29 / 2 = $32.15 each (shown rounded)
    ok(lab.get("Type") == "Other" and lab.get("Qty") == 2 and lab.get("Cost each") == 32.15, f"{tag}: shipping split by price ({lab.get('Cost each')})")
    summ = d["tabs"]["Summary"]
    ok(summ[0][0] == "DYS Edge ledger" and abs(summ[1][1] * 100 - b["cash"]) < 0.5, f"{tag}: Summary tab cash")
    ok(not any(TOKEN in json.dumps(v) for v in d["tabs"].values()), f"{tag}: token not in the Sheet")

    # grading: send, then back as a PSA 10 (its cost includes the fee)
    page.click("[data-view=items]")
    page.click(f"[data-item]:has-text({json.dumps(picked)}) >> nth=0")
    page.wait_for_selector("[data-a=tograde]")
    page.click("[data-a=tograde]")
    page.fill("#lf-fee", "24.99")
    page.fill("#lf-ship", "6")
    page.click("#lf button[type=submit]")
    page.wait_for_selector("[data-a=back]")
    ok("At grading" in page.inner_text("#m-body"), f"{tag}: at grading")
    page.click("[data-a=back]")
    page.fill("#lf-grade", "10")
    page.fill("#lf-cert", "0012345678")
    page.click("#lf button[type=submit]")
    page.wait_for_selector("[data-a=move]")
    kv = page.inner_text(".lg-kv")
    # $45 + its $3.21 share of the $7.50 shipping (45 : 60) + $24.99 grading + $6 shipping to the grader = $79.20
    ok("PSA 10" in page.inner_text("#m-body") and "$79.20" in kv and "$3.21" in kv and "0012345678" in kv, f"{tag}: graded cost ({kv[:200]})")
    page.click("[data-a=move]")
    ok("Moved to Personal" in toast(page, "Moved"), f"{tag}: moved to Personal")
    page.click("[data-a=close]")

    # offline at a show: the change waits, then goes when back online
    MODE["m"] = "offline"
    page.click("[data-view=home]")
    page.click("[data-a=cost]")
    page.select_option("#lf-kind", "Supplies")
    page.fill("#lf-amt", "12.34")
    page.click("#lf button[type=submit]")
    page.wait_for_timeout(1800)
    page.click("[data-view=home]")
    ok("waiting to reach your Sheet" in page.inner_text(".lg-sync"), f"{tag}: offline change waits ({page.inner_text('.lg-sync')})")
    MODE["m"] = "ok"
    page.click(".lg-sync [data-a=sync]")
    wait_synced(page)
    page.click("[data-view=home]")
    ok("Synced with your Sheet" in page.inner_text(".lg-sync"), f"{tag}: synced after reconnecting")
    ok(any(x["Category"] == "Supplies" and x["Amount"] == 12.34 for x in tab(sheet("/dump"), "Expenses")), f"{tag}: offline expense reached the Sheet")

    # delete from Activity: confirm in the page, row kept in the Sheet as deleted
    page.click("[data-view=act]")
    page.click(".lg-ev:has-text('Supplies') [data-del]")
    page.click(".lg-confirm .btn.primary")
    wait_synced(page)
    ok(any(x["Category"] == "Supplies" and x["Deleted"] == 1 for x in tab(sheet("/dump"), "Expenses")), f"{tag}: deleted row kept as Deleted = 1")
    ok("Supplies" not in page.inner_text("#lg-body"), f"{tag}: deleted entry gone from Activity")
    no_junk(page, f"{tag} activity")

    # books
    page.click("[data-view=home]")
    page.click("[data-book=Personal]")
    tl = tiles(page)
    ok(tl.get("Holding") == "$79", f"{tag}: Personal holds the graded card at $79 ({tl.get('Holding')})")
    page.click("[data-book=All]")
    no_junk(page, f"{tag} overview")

    # tax export: the Sales CSV downloads and agrees
    page.click("[data-view=tax]")
    with page.expect_download() as dl:
        page.click("[data-csv=sales]")
    path = dl.value.path()
    text = open(path, encoding="utf-8", newline="").read()
    ok(dl.value.suggested_filename == "dys-ledger-2026-both-sales.csv" and "1035.35" in text and text.count("\r\n") == 2, f"{tag}: sales CSV {dl.value.suggested_filename} {text!r}")
    with page.expect_download() as dl2:
        page.click("[data-csv=summary]")
    summ_csv = open(dl2.value.path(), encoding="utf-8", newline="").read()
    ok("Not tax advice" in summ_csv and "Profit on sales" in summ_csv, f"{tag}: summary CSV")
    no_junk(page, f"{tag} export")

    # a phone the Sheet doesn't know is refused, and says so
    page.evaluate(f"() => {{ const r = JSON.parse(localStorage.getItem('dys-edge-relay')); r.pass = '{'0' * 64}'; localStorage.setItem('dys-edge-relay', JSON.stringify(r)); }}")
    page.click("#m-seg button:has-text('Settings')")
    page.wait_for_selector("#lg-now")
    page.click("#lg-now")
    page.wait_for_function("() => /doesn't know this phone|waiting|failed/.test(document.querySelector('#lg-st').textContent)", timeout=6000)
    ok("doesn't know this phone" in page.inner_text("#lg-st"), f"{tag}: refused phone ({page.inner_text('#lg-st')})")
    no_junk(page, f"{tag} settings")


def main():
    srv = serve()
    mock = subprocess.Popen(["node", os.path.join(HERE, "mock_sheet.js"), str(SHEET_PORT), hashlib.sha256(TOKEN.encode()).hexdigest()], stdout=subprocess.PIPE)
    mock.stdout.readline()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for width, theme in [(390, "dark"), (360, "light"), (430, "dark")]:
                subprocess.run(["true"])
                # a fresh Sheet and a fresh phone for each pass
                mock.terminate(); mock.wait()
                mock = subprocess.Popen(["node", os.path.join(HERE, "mock_sheet.js"), str(SHEET_PORT), hashlib.sha256(TOKEN.encode()).hexdigest()], stdout=subprocess.PIPE)
                mock.stdout.readline()
                ctx = br.new_context(accept_downloads=True)
                ctx.add_init_script(f"""if (!sessionStorage.getItem('seeded')) {{ sessionStorage.setItem('seeded', '1');
                  localStorage.clear();
                  localStorage.setItem('dys-theme', '{theme}');
                  localStorage.setItem('dys-edge-v1', JSON.stringify({{ inv: {json.dumps([UMB, ETB])} }}));
                  localStorage.setItem('dys-edge-relay', JSON.stringify({{ relay: 'https://relay.test', pass: '{TOKEN}', device: 'phone' }}));
                  localStorage.setItem('dys-edge-ledger-url', '{URL}'); }}""")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(f"{e} {getattr(e, 'stack', '')[:400]}"))
                page.route("https://script.google.com/**", ledger_route)
                page.route("https://relay.test/**", lambda r: r.abort())
                run(page, width, theme)
                ok(not errors, f"{width}px: page errors {errors[:3]}")
                ctx.close()
            br.close()
    finally:
        mock.terminate()
        srv.shutdown()
    print(f"{checks - len(fails)} of {checks} ledger browser checks passed")
    sys.exit(1 if fails else 0)


main()
