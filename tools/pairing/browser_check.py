"""Browser checks for Mine → Settings → Sold prices pairing: a paired phone shows its code and keeps its key unless he
confirms "Pair again". python3 tools/pairing/browser_check.py /tmp/m3site"""
import functools, hashlib, http.server, json, sys, threading
from playwright.sync_api import sync_playwright
DIR, PORT = sys.argv[1], 8775
checks, fails = 0, []
def ok(c, w):
    global checks; checks += 1
    if not c: fails.append(w)
h = functools.partial(type("Q", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}), directory=DIR)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
TOKEN = "11" * 32; HASH = hashlib.sha256(TOKEN.encode()).hexdigest()
errors = []
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for width in (390, 360):
        ctx = b.new_context(viewport={"width": width, "height": 900}, is_mobile=True, has_touch=True)
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("https://dys-edge-relay.keo-llaneza.workers.dev/**", lambda r: r.fulfill(status=200, body="{}", headers={"Access-Control-Allow-Origin": "*"}))
        page.route("https://script.google.com/**", lambda r: r.abort())
        page.goto(f"http://127.0.0.1:{PORT}/edge/#mine")
        def setting(store):
            page.evaluate("(s) => { if (s) localStorage.setItem('dys-edge-relay', JSON.stringify(s)); else localStorage.removeItem('dys-edge-relay'); const d = JSON.parse(localStorage.getItem('dys-edge-v1') || '{}'); localStorage.setItem('dys-edge-v1', JSON.stringify(d)); }", store)
            page.goto(f"http://127.0.0.1:{PORT}/edge/#today"); page.goto(f"http://127.0.0.1:{PORT}/edge/#mine"); page.reload()
            page.wait_for_selector("#m-seg"); page.click("#m-seg >> text=Settings"); page.wait_for_selector("#rl-pair")
        tag = str(width)
        # not paired
        setting(None)
        ok(page.inner_text("#rl-pair") == "Pair this phone" and not page.query_selector("#rl-paired"), f"{tag}: unpaired says Pair this phone")
        # paired by this phone: shows the code; Pair again asks first; Cancel keeps the key
        stored = {"relay": "https://dys-edge-relay.keo-llaneza.workers.dev", "pass": TOKEN, "device": "phone", "paired": "2026-11-21T17:00:00Z", "hash": HASH}
        setting(stored)
        t = page.inner_text("#rl-paired")
        ok("Paired ✓" in t and HASH in t and TOKEN not in page.content(), f"{tag}: paired phone shows its code, never its key")
        ok(page.inner_text("#rl-pair") == "Pair again (new key)", f"{tag}: the button says it makes a new key ({page.inner_text('#rl-pair')})")
        page.once("dialog", lambda d: d.dismiss()); page.click("#rl-pair"); page.wait_for_timeout(300)
        after = json.loads(page.evaluate("() => localStorage.getItem('dys-edge-relay')"))
        ok(after["hash"] == HASH and after["pass"] == TOKEN, f"{tag}: Cancel keeps the key")
        msg = {}
        page.once("dialog", lambda d: (msg.setdefault("t", d.message), d.accept())); page.click("#rl-pair"); page.wait_for_selector("#rl-code b")
        after = json.loads(page.evaluate("() => localStorage.getItem('dys-edge-relay')"))
        ok(after["hash"] != HASH and after["hash"] == hashlib.sha256(after["pass"].encode()).hexdigest() and after["hash"] in page.inner_text("#rl-code"), f"{tag}: confirmed: a new key and its code")
        ok("Claude adds the new code to the relay and the Sheet" in msg.get("t", ""), f"{tag}: the warning names the relay and the Sheet")
        # a relay address + passphrase (no device pairing) still offers pairing
        setting({"relay": "https://x.workers.dev", "pass": "manual"})
        ok(page.inner_text("#rl-pair") == "Pair this phone" and not page.query_selector("#rl-paired"), f"{tag}: passphrase setup offers pairing")
        ok(page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"), f"{tag}: fits the phone width")
        ctx.close()
    b.close()
srv.shutdown()
ok(not errors, f"no script errors {errors[:3]}")
for f in fails: print("FAIL", f)
print(f"{checks - len(fails)} of {checks} pairing checks passed"); sys.exit(1 if fails else 0)
