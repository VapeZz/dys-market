"""Preview of the site with the rebuilt price history: a short report plus screenshots. Test branch only.

    python tools/history_preview.py site preview-out

Reads the freshly built site/data, writes preview-out/report.md, then serves the site folder locally
and photographs a few pages (1-year and all-time movers, 1-year charts). Publishes nothing.
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import config  # noqa: E402
import snapshots  # noqa: E402

PORT = 8765
# (name, page, clicks, phone or desk)
SHOTS = [
    ("1-cards-1year", "cards.html", ['#game button[data-v="pokemon"]', '#win button[data-v="365"]'], "phone"),
    ("2-cards-alltime", "cards.html", ['#game button[data-v="pokemon"]', '#win button[data-v="all"]'], "phone"),
    ("3-sealed-1year", "trends.html", ['[data-g] button[data-v="pokemon"]', '[data-w] button[data-v="365"]'], "phone"),
    ("4-chart-prismatic-etb", "product.html?id=593355&set=23821", [], "phone"),
    ("5-chart-charizard-151", "product.html?id=517045&set=23237", [], "phone"),
    ("6-cards-1year-desktop", "cards.html", ['#game button[data-v="pokemon"]', '#win button[data-v="365"]'], "desk"),
]


def money(c):
    return f"${c / 100:,.2f}"


def load(site, rel):
    with open(os.path.join(site, "data", rel), encoding="utf-8") as f:
        return json.load(f)


def report(site, out):
    meta = load(site, "meta.json")
    hist = snapshots.history_days()
    lines = ["# Price history preview", "",
             f"- Built from saved data dated **{meta['updated']}**. Nothing here is live.",
             f"- History days rebuilt from the stored tcgcsv archives: **{len(hist)}**" + (f" ({hist[0]} to {hist[-1]})" if hist else ""),
             f"- Days the site can now use: **{len(snapshots.site_days())}** (was {len(snapshots.available())}); first day **{meta['first']}**",
             "", "## Comparison days", "", "| Window | Compared with |", "|---|---|"]
    names = {"7": "7 days", "30": "30 days", "90": "90 days", "365": "1 year", "all": "All time"}
    for w, d in meta["anchors"].items():
        lines.append(f"| {names.get(w, w)} | {d or 'not available'} |")

    lines += ["", "## How many movers each list has (items worth $20 or more)", "",
              "| List | 7 days | 30 days | 90 days | 1 year | All time |", "|---|---|---|---|---|---|"]
    for name, label in (("cards-pokemon", "Pokémon cards"), ("sealed-pokemon", "Pokémon sealed"), ("cards-all", "All cards"), ("sealed-all", "All sealed")):
        mv = load(site, f"movers/{name}.json")
        cells = []
        for w in ("7", "30", "90", "365", "all"):
            x = mv["windows"].get(w, {}).get("20")
            cells.append(f"{len(x['up'])} up, {len(x['down'])} down" if x else "none")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    for name, thr, label in (("cards-pokemon", "100", "Pokémon cards worth $100 or more"), ("sealed-pokemon", "20", "Pokémon sealed worth $20 or more")):
        mv = load(site, f"movers/{name}.json")
        for w, wl in (("365", "1 year"), ("all", "all time")):
            x = mv["windows"].get(w, {}).get(thr)
            if not x:
                continue
            lines += ["", f"## {label}: biggest gains over {wl}", "", "| Item | Then | Now | Change |", "|---|---|---|---|"]
            for r in x["up"][:10]:
                lines.append(f"| {r[1].replace('|', '/')} | {money(r[4])} | {money(r[3])} | {r[5]:+.0f}% |")
            lines += ["", f"Biggest drops over {wl}: " + "; ".join(f"{r[1]} {r[5]:+.0f}%" for r in x["down"][:5]) + "."]

    sets = [f for f in os.listdir(os.path.join(site, "data", "set")) if f.endswith(".json")] if os.path.isdir(os.path.join(site, "data", "set")) else []
    one = load(site, "set/23821.json") if os.path.exists(os.path.join(site, "data", "set", "23821.json")) else None
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _d, fs in os.walk(os.path.join(site, "data")) for f in fs)
    lines += ["", "## Charts and size", ""]
    if one:
        d = one.get("dates") or []
        lines.append(f"- Chart points per item: **{len(d)}** ({d[0]} to {d[-1]}), daily for the last 30 days then weekly.")
    lines.append(f"- Site data folder: **{total / 1e6:.0f} MB** in {len(sets)} set files.")
    hsize = sum(os.path.getsize(os.path.join(snapshots.HIST_DIR, f)) for f in os.listdir(snapshots.HIST_DIR)) if os.path.isdir(snapshots.HIST_DIR) else 0
    lines.append(f"- History files that would be added to the saved data: **{hsize / 1e6:.0f} MB**.")
    checks = os.path.join(out, "checks.txt")
    if os.path.exists(checks):
        lines += ["", "## Other nightly steps run against this build", "", "```", open(checks, encoding="utf-8").read().strip(), "```"]
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:14]))


def shots(site, out):
    from playwright.sync_api import sync_playwright
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=site,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pages = {"phone": b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2),
                     "desk": b.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)}
            for name, path, clicks, kind in SHOTS:
                pg = pages[kind]
                try:
                    pg.goto(f"http://127.0.0.1:{PORT}/{path}", wait_until="networkidle", timeout=60000)
                    pg.wait_for_timeout(1500)
                    for sel in clicks:
                        pg.locator(sel).first.click(timeout=15000)
                        pg.wait_for_timeout(1200)
                    pg.wait_for_timeout(1500)
                    # the floating menu and buttons would be stamped into the middle of a full-page photo
                    pg.add_style_tag(content=".tabbar,.sell-fab,.ofr-nudge,.v2-pill,#toast{display:none!important}")
                    width = 1280 if kind == "desk" else 390
                    height = min(pg.evaluate("document.documentElement.scrollHeight"), 2400 if kind == "phone" else 1500)
                    pg.screenshot(path=os.path.join(out, f"{name}.jpg"), type="jpeg", quality=80, full_page=True,
                                  clip={"x": 0, "y": 0, "width": width, "height": height})
                    print(f"::notice title=Preview shot::{name} ok")
                except Exception as e:  # noqa: BLE001
                    print(f"::warning title=Preview shot::{name}: {str(e)[:300]}")
            b.close()
    finally:
        server.terminate()


def main(argv):
    site = os.path.abspath(argv[0] if argv else "site")
    out = os.path.abspath(argv[1] if len(argv) > 1 else "preview-out")
    os.makedirs(out, exist_ok=True)
    report(site, out)
    if "--no-shots" not in argv:
        shots(site, out)


if __name__ == "__main__":
    main(sys.argv[1:])
