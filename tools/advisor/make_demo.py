"""Build a tap-through demo of the real Edge app (Today + Holdings Advisor) for Keo's review: the site's own Edge files, a
local site copy's data, a synthetic ledger and watchlist, and the synthetic PkmnPrices relay (tools/deal/make_fixture.js)
answered inside the page. Nothing real is called: no relay, no PkmnPrices, no Google Sheet.
    node tools/deal/make_fixture.js <site copy> 23821 23237 604
    python3 tools/advisor/make_demo.py <site copy> <holdings.json> <out dir>
"""
import json
import re
import os
import shutil
import sys

SITE, HOLD, OUT = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3]
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../..")

if os.path.exists(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)
for d in ("data", "assets"):
    shutil.copytree(os.path.join(SITE, d), os.path.join(OUT, d))
for f in os.listdir(os.path.join(ROOT, "site/assets")):   # the current Edge code, not the site copy's
    if f.startswith("edge") and f.endswith((".js", ".css", ".json")):
        shutil.copy(os.path.join(ROOT, "site/assets", f), os.path.join(OUT, "assets", f))
shutil.copy(os.path.join(SITE, "mock-relay.json"), os.path.join(OUT, "mock-relay.json"))
if os.path.exists(os.path.join(SITE, "finder-phone.json")):
    shutil.copy(os.path.join(SITE, "finder-phone.json"), os.path.join(OUT, "finder-phone.json"))

names = {}
for g in (23821, 23237, 604):
    for it in json.load(open(f"{SITE}/data/set/{g}.json"))["items"]:
        names[it["id"]] = it
items = []
for h in HOLD:
    iid = h["key"].split(":")[0]
    n = names[h["id"]]["n"]
    items.append({"id": iid, "buy": "", "day": "2026-11-01", "book": "Business", "kind": h["kind"], "tcg": h["id"], "g": h["g"], "n": n, "name": n, "set": "",
                  "cond": h.get("cond", "") if h["kind"] == "Raw" else "", "grader": h.get("grader", ""), "grade": h.get("grade", ""), "cert": "", "qty": h.get("qty", 1),
                  "price": h["cost"], "status": "", "note": "SAMPLE"})
LEDGER = {"v": 1, "T": {"buys": [], "items": items, "sales": [], "costs": [], "cash": []}, "q": [], "pulled": 0, "err": "", "migrated": True, "sheet": ""}
umb, leaf = names[610516], names[610499]
# card-show buy list (Nov 20): four sample cards on the watchlist and on the buy list, not checked yet, so "Check prices"
# can be tried (the synthetic relay answers; nothing is spent)
BL_CARDS = [(610513, 23821), (42355, 604), (517020, 23237), (610653, 23821)]
SETN = {23821: "SV: Prismatic Evolutions", 23237: "SV: Scarlet & Violet 151", 604: "Base Set"}
SEED = {"inv": [], "watch": [{"id": 610516, "g": 23821, "n": umb["n"], "target": umb["p"] + 100, "at": "2026-11-10"},
                             {"id": 610499, "g": 23821, "n": leaf["n"], "target": 100, "at": "2026-11-10"}]
        + [{"k": f"{i}|{names[i]['n']}", "id": i, "g": g, "n": names[i]["n"], "t": "c", "target": names[i]["p"] // 2, "at": "2026-11-20"} for i, g in BL_CARDS],
        "set": {"platform": "ebay"}}
BUYLIST = {"v": 1, "items": [{"k": f"{i}|{names[i]['n']}", "id": i, "g": g, "n": names[i]["n"], "setN": SETN[g], "t": "c", "r": names[i].get("r", ""), "cond": "NM", "added": 1795200000000}
                             for i, g in BL_CARDS[:3]]}

# binder / lot offer (Nov 21): a sample binder page of six cards, not checked yet, so "Check prices" and "Check live" can be
# tried. Wartortle shows the printing check only when the site copy carries a second printing of it (tools/lot's test copy).
srows = json.load(open(os.path.join(SITE, "data/search.json")))
LOT_CARDS = [(517038, 23237, 1), (516998, 23237, 2), (610513, 23821, 1), (517020, 23237, 1), (42433, 604, 1), (42359, 604, 1)]
def alts(i, n):
    m = re.compile(r"\(([^()]*)\)\s*$")
    out = []
    for r in srows:
        if r[0] == i and r[1] != n and r[3] != "s":
            g = m.search(r[1]); pr = g.group(1) if g and g.group(1) in ("1st Edition Holofoil", "1st Edition Normal", "1st Edition", "Unlimited Holofoil", "Unlimited", "Reverse Holofoil", "Holofoil", "Normal") else "Normal"
            if pr not in out: out.append(pr)
    return out
LOTS = {"v": 1, "lots": [{"id": "lotdemo", "name": "Sample binder page", "created": 1795300000000, "askMode": "total", "lines": [
    {"l": f"ld{j}", "k": f"{i}|{names[i]['n']}", "id": i, "g": g, "n": names[i]["n"], "setN": SETN[g], "t": "c", "r": names[i].get("r", ""), "cond": "NM", "qty": q,
     "alts": alts(i, names[i]["n"]), "prOk": not alts(i, names[i]["n"]), "tcg": names[i]["p"]} for j, (i, g, q) in enumerate(LOT_CARDS)]}]}

DEMO = """/* Edge demo shim: sample ledger + synthetic sold-price relay answered in the page. Nothing real is called. */
(() => {
  const V = "lot-demo-1", SEED = %s, LEDGER = %s, BUYLIST = %s, LOTS = %s;
  const seed = (paired) => { try { localStorage.clear(); localStorage.setItem("dys-theme", "dark"); localStorage.setItem("dys-edge-v1", JSON.stringify(SEED)); localStorage.setItem("dys-edge-buylist", JSON.stringify(BUYLIST)); localStorage.setItem("dys-edge-lots", JSON.stringify(LOTS));
    localStorage.setItem("dys-edge-ledger", JSON.stringify(LEDGER)); if (paired) localStorage.setItem("dys-edge-relay", JSON.stringify({ relay: "https://relay.test", pass: "sample" }));
    localStorage.setItem("dys-demo", V); } catch (e) {} };
  try { if (localStorage.getItem("dys-demo") !== V) seed(true); } catch (e) {}
  let MOCK = null; const mock = () => MOCK ||= fetch("mock-relay.json").then((r) => r.json());
  const keyOf = (url) => { const u = new URL(url), q = Object.fromEntries(u.searchParams), p = u.pathname;
    if (q.tcg_player_id) return p + "|" + q.tcg_player_id; if (p === "/v1/sealed") return p + "|*";
    if (p.endsWith("/listings/ebay")) return p + "|" + (p.startsWith("/v1/sealed") ? "sealed" : q.graded === "true" ? "true" + q.grade : "false"); return p; };
  const real = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.startsWith("https://relay.test/edge/finder")) {   // Daily deals: a test phone extract, if the site copy has one
      const f = await real("finder-phone.json"); await new Promise((r) => setTimeout(r, 150));
      return f.ok ? new Response(await f.text(), { status: 200, headers: { "Content-Type": "application/json" } }) : new Response(JSON.stringify({ error: "not-connected" }), { status: 503 });
    }
    if (url.startsWith("https://relay.test")) {
      const m = await mock(); await new Promise((r) => setTimeout(r, 120));
      const [status, body] = m.routes[keyOf(url)] || [404, { error: "not found" }];
      const n = Math.max(1, (body && Array.isArray(body.data)) ? body.data.length : 1);
      return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "x-credits-charged": String(n) } });
    }
    if (url.startsWith("https://script.google.com")) throw new TypeError("demo: no Sheet");
    return real(input, init);
  };
  addEventListener("DOMContentLoaded", () => {
    const paired = (() => { try { return !!localStorage.getItem("dys-edge-relay"); } catch (e) { return true; } })();
    const b = document.createElement("div"); b.className = "demo-bar";
    b.innerHTML = `<b>Preview · sample cards, made-up sales.</b> Try Deals → Lot offer. Daily deals shows the real Nov 19 finder run. Nothing real is called and no credits are spent.
      <span><button type="button" data-d="pair">${paired ? "Unpair this phone" : "Pair again"}</button><button type="button" data-d="reset">Reset preview</button></span>`;
    b.onclick = (e) => { const d = e.target.dataset.d; if (!d) return; seed(d === "reset" ? true : !paired); location.hash = "#deals"; location.reload(); };
    document.body.prepend(b);
  });
})();
""" % (json.dumps(SEED), json.dumps(LEDGER), json.dumps(BUYLIST), json.dumps(LOTS))
open(os.path.join(OUT, "assets/demo.js"), "w").write(DEMO)

html = open(os.path.join(SITE, "edge/index.html")).read()
html = html.replace("../assets/", "assets/").replace('href="manifest.webmanifest"', 'href="data:,"')
html = html.replace("<title>DYS Edge</title>", "<title>DYS Edge preview: Lot offers (sample data)</title>")
html = html.replace("</head>", """<style>.demo-bar{padding:8px 12px;font:13px/1.4 Inter,system-ui,sans-serif;background:#3b2a05;color:#ffd77a;display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center}
.demo-bar span{display:flex;gap:6px}.demo-bar button{font:inherit;font-size:12px;padding:4px 10px;border-radius:999px;border:1px solid #ffd77a66;background:transparent;color:#ffd77a}</style>
<script src="assets/demo.js"></script>
</head>""")
open(os.path.join(OUT, "index.html"), "w").write(html)
n = sum(len(fs) for _, _, fs in os.walk(OUT))
print(f"demo in {OUT}: {n} files")
