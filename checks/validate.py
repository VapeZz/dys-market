"""Check every static price page of a test build, and that no live address was lost or changed.

    python3 checks/validate.py <built site dir> <published copy dir>      exit code 1 on any problem
"""
import collections, glob, html, json, os, re, sys
site, live = sys.argv[1], sys.argv[2]
def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()
items = {}
for p in glob.glob(os.path.join(site, "data", "set", "*.json")):
    d = json.loads(read(p))
    for i in d["items"]:
        items.setdefault((i["id"], d["id"]), []).append(i)
pages = json.loads(read(os.path.join(site, "data", "pages.json")))
old = json.loads(read(os.path.join(live, "data", "pages.json")))
bad, titles, n = collections.Counter(), collections.Counter(), 0
for f in os.listdir(os.path.join(site, "p")):
    n += 1
    h, slug = read(os.path.join(site, "p", f)), f[:-5]
    if re.findall(r'<link rel="canonical" href="([^"]+)">', h) != [f"https://market.driveyourstyle.net/p/{slug}.html"]:
        bad["address tag"] += 1
    m = re.search(r'<body data-page="price" data-id="(\d+)" data-set="(\d+)" data-var="([^"]*)">', h)
    if not m:
        bad["body tag"] += 1
        continue
    var = html.unescape(m.group(3))
    hit = [v for v in items.get((int(m.group(1)), int(m.group(2))), []) if v["n"] == var]
    if not hit:
        bad["item not in the data"] += 1
        continue
    if hit[0].get("pg") != slug:
        bad["item's page address differs"] += 1
    if pages.get(f"{m.group(1)}|{var}") != slug:
        bad["pages.json differs"] += 1
    if "@@" in h:
        bad["placeholder left"] += 1
    if 'id="prod"' not in h or 'id="crumbs"' not in h or h.count("<h1") != 1:
        bad["page frame"] += 1
    if not re.search(r'<script src="assets/app\.js\?v=\d+"></script>', h):
        bad["script tag"] += 1
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        bad["address characters"] += 1
    titles[re.search(r"<title>([^<]*)</title>", h).group(1)] += 1
if set(pages.values()) != {f[:-5] for f in os.listdir(os.path.join(site, "p"))}:
    bad["pages.json and files differ"] += 1
lost = [k for k in old if k not in pages]
moved = [k for k in old if k in pages and pages[k] != old[k]]
locs = re.findall(r"<loc>([^<]+)</loc>", read(os.path.join(site, "sitemap.xml")))
if sum("/p/" in l for l in locs) != n or len(locs) != len(set(locs)):
    bad["sitemap"] += 1
print(f"static pages: {n} | problems: {dict(bad) or 'none'} | pages sharing a title: {sum(c for c in titles.values() if c > 1)}")
print(f"live pages: {len(old)} | lost: {len(lost)} | address changed: {len(moved)} | new: {len(pages) - len(old) + len(lost)}")
print(f"sitemap: {len(locs)} entries, {sum('/p/' in l for l in locs)} price pages, {sum('set.html?id' in l for l in locs)} set pages, {sum('product.html' in l for l in locs)} card pages")
sys.exit(1 if bad or lost or moved else 0)
