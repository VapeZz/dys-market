"""Browser checks for Edge's card search (Search tab, Show check, Buy list) on a local site copy with the real card list
(data/search.json, 67,613 items). Expected matches are worked out here, separately, from the written rules:
every word starts a word of name + set; a card number matches with or without leading zeros or as its first part;
printing words filter the exact printing.
    python3 tools/search/browser_check.py /tmp/m3site
"""
import functools
import http.server
import json
import re
import sys
import threading
import unicodedata

from playwright.sync_api import sync_playwright

DIR = sys.argv[1]
PORT = 8774
S = json.load(open(f"{DIR}/data/search.json"))
G = json.load(open(f"{DIR}/data/meta.json"))["groups"]
PR = ["1st Edition Holofoil", "1st Edition Normal", "1st Edition", "Unlimited Holofoil", "Unlimited", "Reverse Holofoil", "Holofoil", "Normal"]
checks, fails = 0, []


def ok(c, what):
    global checks
    checks += 1
    if not c:
        fails.append(what)


fold = lambda x: unicodedata.normalize("NFD", x or "").encode("ascii", "ignore").decode().lower()
setn = lambda g: (G.get(str(g)) or [""])[0]
game = lambda g: (G.get(str(g)) or ["", ""])[1]


def printing(r):
    if r[3] == "s":
        return ""
    m = re.search(r"\(([^()]*)\)\s*$", r[1])
    return m.group(1) if m and m.group(1) in PR else "Normal"


def num_norm(x):
    return "/".join(re.sub(r"^([a-z]*)0+(?=\d)", r"\1", p) for p in x.split("/"))


def expected(q, games=("pokemon", "pokemon-jp"), kind="all"):      # Edge's default game setting: Pokémon EN + JP
    x = " " + fold(q).replace("#", " ") + " "
    want = set()
    for k, rx in (("rev", r"\b(reverse holofoil|reverse holo|reverse|rev holo|rh)\b"), ("1st", r"\b(1st edition|1st ed|1st|first edition|first ed)\b"),
                  ("unl", r"\b(unlimited|unl)\b"), ("normal", r"\b(non[\s-]?holo|normal)\b"), ("holo", r"\b(holofoil|holo)\b")):
        if re.search(rx, x):
            want.add(k)
            x = re.sub(rx, " ", x)
    toks = [t for t in re.sub(r"[^a-z0-9/]+", " ", x).split() if t]
    out = []
    for r in S:
        if game(r[2]) not in games or (kind != "all" and r[3] != kind):
            continue
        p = printing(r)
        if want and (not p or ("rev" in want and p != "Reverse Holofoil") or ("holo" in want and "rev" not in want and not (p.endswith("Holofoil") and p != "Reverse Holofoil"))
                     or ("1st" in want and not p.startswith("1st Edition")) or ("unl" in want and not p.startswith("Unlimited"))
                     or ("normal" in want and p not in ("Normal", "Unlimited", "1st Edition", "1st Edition Normal"))):
            continue
        text = " " + re.sub(r"[^a-z0-9/]+", " ", fold(r[1] + " " + setn(r[2]))) + " "
        m = re.search(r" - ([a-z]*\d+[a-z]*(?:/[a-z]*\d+[a-z]*)?)", r[1], re.I)
        no = num_norm(m.group(1).lower()) if m else ""
        good = True
        for t in toks:
            if re.search(r"\d", t) and no and (no == num_norm(t) or no.split("/")[0] == num_norm(t)):
                continue
            if " " + t in text:
                continue
            good = False
            break
        if good:
            out.append(r)
    return out


def serve():
    h = functools.partial(type("Q", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}), directory=DIR)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def names(page, sel):
    return page.eval_on_selector_all(sel, "els => els.map((e) => e.dataset.n || e.dataset.open && e.querySelector('.nm')?.textContent)")


def show_all(page, box, item_sel):
    while page.query_selector(f"{box} .sr-more"):
        page.click(f"{box} .sr-more")
    return page.eval_on_selector_all(f"{box} {item_sel}", "els => els.map((e) => [e.dataset.sc || e.dataset.id || e.dataset.open, e.dataset.n])")


def main():
    srv = serve()
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for width in (390, 360):
            tag = f"{width}"
            ctx = b.new_context(viewport={"width": width, "height": 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{PORT}/edge/#deals")
            page.evaluate("() => { localStorage.setItem('dys-theme', 'dark'); localStorage.removeItem('dys-edge-buylist'); }")
            page.reload(); page.wait_for_selector("#sc-q")

            def sc(q):
                page.fill("#sc-q", "")
                page.type("#sc-q", q, delay=2)
                page.wait_for_function(f"() => {{ const c = document.querySelector('#sc-res .sr-count'); const e = document.querySelector('#sc-res p.muted'); return (c && document.querySelector('#sc-q').value === {json.dumps(q)}) || (e && /Nothing found/.test(e.textContent)); }}", timeout=10000)
                page.wait_for_timeout(250)

            # "Mew": every match, not 12; exact name first; paging to the end
            exp = expected("Mew")
            sc("Mew")
            n = page.eval_on_selector("#sc-res .sr-count", "e => +e.dataset.n")
            ok(n == len(exp) and n > 200, f"{tag}: Show check finds all {len(exp)} Mew matches (got {n}; before: 12 shown of the first 200)")
            first = page.eval_on_selector_all("#sc-res .sc-hit", "els => els.map((e) => e.dataset.n)")
            ok(len(first) == 20, f"{tag}: 20 shown first ({len(first)})")
            base = lambda nm: re.sub(r"[^a-z0-9]+", " ", fold(re.sub(r"\s*\(.*$", "", nm.split(" - ")[0]))).strip()
            ok(all(base(x) == "mew" for x in first), f"{tag}: the first page is cards named exactly Mew ({first[:4]})")
            got = show_all(page, "#sc-res", ".sc-hit")
            ok(len(got) == len(exp) and len({(a, b) for a, b in got}) == len(got), f"{tag}: Show more reaches all {len(exp)} with no repeats ({len(got)})")
            ok({(str(r[0]), r[1]) for r in exp} == {(a, b) for a, b in got}, f"{tag}: exactly the expected matches")
            cheapest = min(exp, key=lambda r: r[4])
            ok((str(cheapest[0]), cheapest[1]) in {(a, b) for a, b in got}, f"{tag}: the cheapest Mew ({cheapest[1]}, ${cheapest[4] / 100:.2f}) is reachable")
            ranks = [0 if base(nm) == "mew" else 1 if base(nm).startswith("mew ") else 2 if (" " + base(nm) + " ").find(" mew ") >= 0 else 3 for _, nm in got]
            bad = [(got[i][1], ranks[i], got[i + 1][1], ranks[i + 1]) for i in range(len(ranks) - 1) if ranks[i] > ranks[i + 1]]
            ok(not bad, f"{tag}: exact name, then 'Mew …', then other names (Mewtwo) in order {bad[:3]}")
            ok(not any("artholomew" in nm for _, nm in got), f"{tag}: no mid-word matches (Bartholomew)")
            prs = page.eval_on_selector_all("#sc-res .sc-hit .sc-hn small", "els => els.slice(0, 5).map((e) => e.textContent)")
            ok(all(re.search(r"· (Holofoil|Normal|Reverse Holofoil|1st Edition|Unlimited|sealed)", x) for x in prs), f"{tag}: each result shows its printing ({prs[:2]})")
            if width == 390:
                page.screenshot(path="/tmp/pv/search-mew.png")
            # numbers, sets and printings
            for q, must, every in (
                ("charizard 6/165", "Charizard ex - 006/165 (Holofoil)", None),
                ("pikachu ex 179", "Pikachu ex - 179/131 (Holofoil)", None),
                ("charizard base set", "Charizard (Holofoil)", None),
                ("dark tyranitar reverse", "Dark Tyranitar - 019/109 (Reverse Holofoil)", lambda p: p == "Reverse Holofoil"),
                ("dark tyranitar normal", "Dark Tyranitar - 019/109", lambda p: p in ("Normal", "Unlimited", "1st Edition", "1st Edition Normal")),
                ("umbreon 1st", None, lambda p: p.startswith("1st Edition")),
                ("arcanine unlimited", None, lambda p: p.startswith("Unlimited")),
                ("charizard holo", None, lambda p: p.endswith("Holofoil") and p != "Reverse Holofoil"),
            ):
                exp = expected(q)
                sc(q)
                if not exp:
                    ok("Nothing found" in page.inner_text("#sc-res"), f"{tag}: '{q}' finds nothing, and says so")
                    continue
                n = page.eval_on_selector("#sc-res .sr-count", "e => +e.dataset.n")
                got = show_all(page, "#sc-res", ".sc-hit")
                ok(n == len(exp) and {(str(r[0]), r[1]) for r in exp} == {(a, b) for a, b in got}, f"{tag}: '{q}' finds the expected {len(exp)} ({n})")
                if must:
                    ok(must in [x for _, x in got[:3]], f"{tag}: '{q}' puts {must} in the top 3 ({[x for _, x in got[:3]]})")
                if every:
                    ok(all(every(printing([0, x, 0, "c"])) for _, x in got), f"{tag}: '{q}' only that printing")
            # speed over the whole list
            ms = page.evaluate("""async () => { const q = document.querySelector('#sc-q'); const t0 = performance.now();
              for (const w of ['mew', 'charizard', 'pikachu ex 179', 'umbreon 1st', 'base set']) { q.value = w; q.dispatchEvent(new Event('input')); await new Promise((r) => setTimeout(r, 200)); }
              return (performance.now() - t0 - 1000) / 5; }""")
            print(f"{tag}: search over the card list about {ms:.0f} ms per query"); ok(ms < 150, f"{tag}: a search over 67,613 items takes about {ms:.0f} ms here")
            # Buy list add
            page.click("#d-seg >> text=Buy list"); page.wait_for_selector(".bl-add-open"); page.click(".bl-add-open"); page.wait_for_selector("#bl-q")
            page.type("#bl-q", "Mew", delay=2); page.wait_for_selector("#bl-res .sr-count", timeout=8000); page.wait_for_timeout(200)
            exp = expected("Mew")
            ok(page.eval_on_selector("#bl-res .sr-count", "e => +e.dataset.n") == len(exp) and len(page.query_selector_all("#bl-res .bl-s")) == 10, f"{tag}: Buy list finds all {len(exp)}, shows 10")
            page.click("#bl-res .sr-more"); ok(len(page.query_selector_all("#bl-res .bl-s")) == 20, f"{tag}: Buy list Show more adds 10")
            page.click("#bl-res .bl-s >> nth=12"); page.wait_for_timeout(200)
            ok(len(json.loads(page.evaluate("() => localStorage.getItem('dys-edge-buylist')"))["items"]) == 1, f"{tag}: a card from the second page can be added")
            # Search tab (and the Ledger's add-a-card, which uses it)
            page.goto(f"http://127.0.0.1:{PORT}/edge/#search"); page.wait_for_selector("#q")
            page.type("#q", "Mew", delay=2); page.wait_for_selector("#s-res .sr-count", timeout=8000); page.wait_for_timeout(200)
            exp_all = expected("Mew", kind="all")
            ok(page.eval_on_selector("#s-res .sr-count", "e => +e.dataset.n") == len(exp_all) and len(page.query_selector_all("#s-res .row")) == 30, f"{tag}: Search finds all {len(exp_all)}, shows 30")
            page.click("#s-res .sr-more"); ok(len(page.query_selector_all("#s-res .row")) == 60, f"{tag}: Search Show more adds 30")
            st = page.eval_on_selector_all("#s-res .row .st", "els => els.slice(0, 3).map((e) => e.textContent)")
            ok(all("·" in x for x in st), f"{tag}: Search rows show the printing ({st})")
            have = {int(f[:-5]) for f in __import__("os").listdir(f"{DIR}/data/set")}
            idx = page.eval_on_selector_all("#s-res .row", "els => els.map((e) => +e.dataset.g)")
            pick = next(i for i, g in enumerate(idx) if i >= 30 and g in have)
            page.click(f"#s-res .row >> nth={pick}"); page.wait_for_timeout(600)
            ok("#search" not in page.url or page.query_selector(".sheet, .card-sheet, #sheet"), f"{tag}: a result on the second page opens")
            ok(page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"), f"{tag}: fits the phone width")
            ctx.close()
        b.close()
    srv.shutdown()
    ok(not errors, f"no script errors {errors[:3]}")
    for f in fails:
        print("FAIL", f)
    print(f"{checks - len(fails)} of {checks} search browser checks passed")
    sys.exit(1 if fails else 0)


main()
