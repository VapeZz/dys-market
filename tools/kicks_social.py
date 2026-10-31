"""Sneaker "Cop or drop?" (release day) and "Did it flip?" (weekly recap) posts: retail vs eBay resale.

    python tools/kicks_social.py SPEC.json SITE_DIR OUT_ROOT [--offline]

SPEC: {"date": "2026-11-01", "mode": "drop" | "recap",
       "pairs": [{"c": style code, "n"?, "r"?, "d"?, "sold_n"?, "sold_med"?, "sold_days"?, "ask_n"?, "ask_low"?, "ask_p25"?}]}
Missing name / retail / date / photo come from SITE_DIR/sneakers.json and SITE_DIR/data/sneaker-images.json.
Resale used for the call: eBay SOLD median when there are 5+ sales, else the low end (25th percentile) of
new-with-box Buy It Now listings. Writes OUT_ROOT/<date>/: slide-N.jpg (1080x1350), tt-N.jpg (1080x1920),
short.mp4, index.html (the links page), post.json; OUT_ROOT/latest.json, OUT_ROOT/index.html (redirect to newest).
"""
import json
import os
import re
import sys
from datetime import date
from urllib.parse import quote_plus, urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from social import BASE, FONT_CSS, LOGO  # noqa: E402
from sneaker_social import day, esc, shoe  # noqa: E402

SITE = "https://market.driveyourstyle.net"
EPN = "5339229587"                 # eBay Partner Network campaign
TAX = 0.08                         # sales tax paid at retail (Las Vegas ~8.4%)
SHIP = 15.0                        # shipping a pair to the buyer / authenticator
HASHTAGS = "#sneakers #sneakerreleases #copordrop #resell #sneakerhead #jordan #nike #kicks #sneakernews #lasvegas #driveyourstyle"
# Retailer links. Swap in CJ deep links (prefix + encoded URL) once each program approves us.
RETAIL = {"Nike": "https://www.nike.com/w?q={q}", "Jordan": "https://www.nike.com/w?q={q}",
          "New Balance": "https://www.newbalance.com/search?q={q}", "adidas": "https://www.adidas.com/us/search?q={q}",
          "Vans": "https://www.vans.com/en-us/search?q={q}", "PUMA": "https://us.puma.com/us/en/search?q={q}"}
CALL = {"drop": {"cop": ("Cop", "#3ee08f"), "wear": ("Cop to wear", "#a78bfa"), "drop": ("Drop", "#ff7a59")},
        "recap": {"cop": ("Flipped", "#3ee08f"), "wear": ("Wash", "#ffd36e"), "drop": ("Bricked", "#ff7a59")}}


def fee(p):
    """eBay sneaker selling fee: 8% at $150+ (no per-order fee), else 12.9% + $0.40 per order."""
    return p * 0.08 if p >= 150 else p * 0.129 + 0.40


def resale(p):
    if (p.get("sold_n") or 0) >= 5 and p.get("sold_med"):
        return float(p["sold_med"]), "sold"
    if (p.get("ask_n") or 0) >= 3 and p.get("ask_p25"):
        return float(p["ask_p25"]), "ask"
    return None, None


def profit(r, v):
    return v - fee(v) - SHIP - r * (1 + TAX)


def verdict(r, v):
    pr = profit(r, v)
    if pr >= max(25, 0.15 * r):
        return "cop", pr
    if pr >= -25:
        return "wear", pr
    return "drop", pr


def usd(v, cents=False):
    return f"${v:,.2f}" if cents else f"${v:,.0f}"


def signed(v):
    return ("+" if v >= 0 else "−") + usd(abs(v))


def ebay(q, day_, sold=False):
    p = {"_nkw": q, "mkcid": "1", "mkrid": "711-53200-19255-0", "siteid": "0", "campid": EPN, "customid": f"kicks-{day_}",
         "toolid": "10001", "mkevt": "1", "LH_ItemCondition": "1000"}
    p.update({"LH_Sold": "1", "LH_Complete": "1", "_sop": "13"} if sold else {"LH_BIN": "1", "_sop": "15"})
    return "https://www.ebay.com/sch/i.html?" + urlencode(p)


def source_line(p, mode):
    bits = []
    if p.get("sold_n"):
        bits.append(f"{p['sold_n']} sold on eBay" + (f", median {usd(p['sold_med'])}" if p.get("sold_med") else "") +
                    (f" (last {p.get('sold_days', 30)} days)" if mode == "recap" else ""))
    if p.get("ask_n") and (mode == "drop" or not p.get("sold_n")):
        bits.append(f"{p['ask_n']} new pairs listed from {usd(p['ask_low'])}")
    return " · ".join(bits)


def load(spec, site):
    cal = json.load(open(os.path.join(site, "sneakers.json")))
    by = {r.get("c"): r for r in cal["releases"] if r.get("c")}
    try:
        imgs = json.load(open(os.path.join(site, "data", "sneaker-images.json")))
    except (OSError, ValueError):
        imgs = {}
    big = lambda u: u and u.replace(",w_500/", ",w_1200/")
    out = []
    for p in spec["pairs"]:
        base = by.get(p["c"], {})
        q = dict(base, **{k: v for k, v in p.items() if v is not None})
        q["im"] = big(q.get("im") or imgs.get(q["c"]))
        if not q.get("r"):
            continue                      # no retail price, no call
        v, src = resale(q)
        if v is None:
            continue
        q["v"], q["src"] = v, src
        q["call"], q["profit"] = verdict(q["r"], v)
        out.append(q)
    return out


def cover(pairs, mode, when):
    spots = [(330, 0, 0, 5, 380), (60, 110, -9, 4, 340), (600, 110, 9, 4, 340)]
    fan = "".join(
        f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{w}px;transform:rotate({rot}deg);z-index:{z};'
        f'background:#f2f2f2;border-radius:28px;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.6)">{shoe(r)}</div>'
        for r, (x, y, rot, z, w) in zip([p for p in pairs if p.get("im")][:3], spots))
    best = max(pairs, key=lambda p: p["profit"])
    title = 'Cop or<br><span class="holo">drop?</span>' if mode == "drop" else 'Did it<br><span class="holo">flip?</span>'
    sub = (f"Retail vs eBay resale · {esc(when)}" if mode == "drop" else f"Last week's drops, retail vs eBay sold · {esc(when)}")
    hook = (f"{esc(best['n'])}: {usd(best['r'])} retail → {usd(best['v'])} on eBay" if best["profit"] > 0
            else "Which ones are worth it? Swipe")
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}"><div class="tag">{'Release day' if mode == 'drop' else 'Resale recap'}</div></div>
<div style="margin-top:48px;font-family:'Barlow Condensed';font-weight:800;font-size:150px;line-height:.9;text-transform:uppercase">{title}</div>
<div style="margin-top:20px;font-size:38px;color:#d8d5cf">{sub}</div>
<div style="margin-top:14px;font-size:36px;line-height:1.25;color:#f2f0eb;font-weight:700;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{hook}</div>
<div style="position:relative;height:520px;margin-top:30px">{fan}</div>
<div class="bar" style="margin-top:auto;margin-bottom:26px"></div>
<div class="foot"><span>Swipe for the numbers →</span><span>market.driveyourstyle.net</span></div></div>"""


def pair_slide(p, mode, i, n):
    label, color = CALL[mode][p["call"]]
    name = p["n"]
    what = "eBay sold" if p["src"] == "sold" else "eBay resale"
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}" style="height:72px">
 <div style="text-align:right;font-family:'Barlow Condensed';font-weight:800;line-height:.95;text-transform:uppercase"><div style="font-size:40px;color:#bdb9b2">{'Drops ' if mode == 'drop' else 'Dropped '}{day(p['d'], '%a')} · {i} / {n}</div><div class="holo" style="font-size:88px">{day(p['d'], '%b %d')}</div></div></div>
<div style="margin-top:26px;height:560px;background:#f2f2f2;border-radius:28px;overflow:hidden;position:relative">{shoe(p, True)}
 <div style="position:absolute;left:24px;top:24px;font-family:'Barlow Condensed';font-weight:800;font-size:46px;letter-spacing:.06em;text-transform:uppercase;color:#050404;background:{color};padding:10px 24px 6px;border-radius:999px">{label}</div></div>
<div style="margin-top:30px;font-family:'Barlow Condensed';font-weight:800;font-size:{60 if len(name) < 34 else 50}px;line-height:1.02;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{esc(name)}</div>
<div style="margin-top:auto;display:flex;align-items:flex-end;gap:40px">
 <div><div style="font-size:28px;color:#bdb9b2">Retail</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:104px;line-height:1">{usd(p['r'])}</div></div>
 <div style="font-family:'Barlow Condensed';font-weight:800;font-size:80px;color:#bdb9b2;padding-bottom:10px">→</div>
 <div><div style="font-size:28px;color:#bdb9b2">{what}</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:104px;line-height:1;color:{color}">{usd(p['v'])}</div></div>
</div>
<div style="margin-top:18px;font-size:34px"><b style="color:{'#3ee08f' if p['profit'] >= 0 else '#ff7a59'}">{signed(p['profit'])}</b> <span style="color:#bdb9b2">a pair after eBay fees, shipping &amp; tax</span></div>
<div style="margin-top:10px;font-size:26px;color:#8f8a84;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(source_line(p, mode))} · {esc(p['c'])}</div></div>"""


def cta(mode):
    head = "Copping one?" if mode == "drop" else "Missed one?"
    return f"""<div class="slide" style="justify-content:center;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:200px">
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:800;font-size:110px;line-height:.95;text-transform:uppercase">{head}<br><span class="holo">Links in bio</span></div>
<div style="margin-top:34px;font-size:40px;color:#d8d5cf;max-width:880px">Retail, eBay, StockX and GOAT links for every pair, plus the full release calendar.</div>
<div style="margin-top:56px;font-family:'Barlow Condensed';font-weight:700;font-size:52px;letter-spacing:.04em;border:4px solid #f2f0eb;padding:16px 36px 12px">market.driveyourstyle.net/social-kicks</div>
<div class="bar" style="width:100%;margin-top:80px"></div>
<div class="foot" style="width:100%;margin-top:26px"><span>Prices change fast. Not financial advice.</span><span>@drive.yourstyle</span></div></div>"""


def page(post, pairs, mode, day_):
    rows = []
    for i, p in enumerate(pairs, 1):
        label, color = CALL[mode][p["call"]]
        retail = RETAIL.get(p.get("b"), "https://www.google.com/search?q={q}").format(q=quote_plus(p["c"]))
        img = f'<img src="{esc(p["im"])}" alt="{esc(p["n"])}" loading="lazy">' if p.get("im") else ""
        rows.append(f"""<article class="c">{img}<div><h2>{i}. {esc(p['n'])} <small>{esc(p['c'])} · {'drops' if mode == 'drop' else 'dropped'} {day(p['d'], '%a %b %d')}</small></h2>
<p class="p"><span>Retail <b>{usd(p['r'])}</b></span><span>{'eBay sold' if p['src'] == 'sold' else 'eBay resale'} <b class="{'g' if p['v'] >= p['r'] else 'r'}">{usd(p['v'])}</b></span><span class="v" style="background:{color}">{label}</span></p>
<p class="m">{signed(p['profit'])} a pair after eBay fees, shipping and tax. {esc(source_line(p, mode))}.</p>
<p class="b"><a class="btn" href="{esc(ebay(p['c'], day_))}" target="_blank" rel="sponsored noopener">Buy on eBay</a><a class="btn o" href="{esc(retail)}" target="_blank" rel="noopener">Retail ({esc(p.get('b') or 'store')})</a><a class="btn o" href="https://stockx.com/search?s={quote_plus(p['c'])}" target="_blank" rel="noopener">StockX</a><a class="btn o" href="https://www.goat.com/search?query={quote_plus(p['c'])}" target="_blank" rel="noopener">GOAT</a><a class="btn o" href="{esc(ebay(p['c'], day_, True))}" target="_blank" rel="sponsored noopener">eBay sold prices</a></p></div></article>""")
    d = date.fromisoformat(day_)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(post['title'])} · Drive Your Style</title><meta name="description" content="Retail vs eBay resale for {len(pairs)} sneaker releases, with buy links.">
<meta property="og:image" content="{SITE}/social-kicks/{day_}/slide-1.jpg"><link rel="icon" type="image/png" href="../../assets/favicon.png">
<style>body{{margin:0;background:#050404;color:#f2f0eb;font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}main{{max-width:760px;margin:0 auto;padding:22px 16px 40px}}
a{{color:#5ee7ff}}h1{{font-size:28px;line-height:1.15;margin:14px 0 6px}}.sub{{color:#bdb9b2;margin:0 0 18px}}.c{{display:grid;grid-template-columns:130px 1fr;gap:16px;padding:16px 0;border-top:1px solid #222}}
.c img{{width:130px;aspect-ratio:1;object-fit:cover;border-radius:10px;background:#f2f2f2}}h2{{font-size:19px;margin:0 0 6px}}h2 small{{display:block;font-size:13px;color:#bdb9b2;font-weight:400}}
.p{{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;margin:0 0 6px}}.g{{color:#3ee08f}}.r{{color:#ff7a59}}.v{{color:#050404;font-weight:800;font-size:13px;text-transform:uppercase;letter-spacing:.05em;padding:3px 10px;border-radius:999px}}
.m{{color:#bdb9b2;font-size:14px;margin:0 0 10px}}.b{{display:flex;flex-wrap:wrap;gap:8px;margin:0}}.btn{{display:inline-block;padding:9px 14px;border-radius:10px;background:#3ee08f;color:#050404;font-weight:700;text-decoration:none;font-size:14px}}
.btn.o{{background:none;color:#f2f0eb;border:1px solid #444}}.f{{color:#8f8a84;font-size:13px;margin-top:24px}}.top{{display:flex;justify-content:space-between;align-items:center;font-weight:700}}
@media(max-width:420px){{.c{{grid-template-columns:90px 1fr;gap:12px}}.c img{{width:90px}}}}</style></head>
<body><main><div class="top"><a href="../../sneakers.html?ref=kicks" style="color:#f2f0eb;text-decoration:none">DRIVE YOUR STYLE · Kicks</a><a href="../../links.html">More links</a></div>
<h1>{esc(post['title'])}</h1><p class="sub">{len(pairs)} pairs · {d.strftime('%B %-d, %Y')} · <a href="../../sneakers.html?ref=kicks">full release calendar</a></p>{''.join(rows)}
<p class="f">eBay resale = median of new-with-box pairs sold on eBay when there are 5+ sales, otherwise the low end of new pairs listed for sale on eBay (Buy It Now, shipping included), checked {d.strftime('%b %-d')}. Profit assumes about 8% sales tax at retail, eBay's sneaker selling fee and ${SHIP:.0f} shipping. Prices change fast and differ by size; release dates can change. Not financial advice.<br><br>
Affiliate disclosure: eBay links on this page are affiliate links (eBay Partner Network). If you buy through them we may earn a small commission at no extra cost to you.</p></main></body></html>"""


def captions(pairs, mode, when):
    lines = []
    for i, p in enumerate(pairs, 1):
        label = CALL[mode][p["call"]][0]
        lines.append(f"{i}. {p['n']}: {usd(p['r'])} retail → {usd(p['v'])} eBay ({signed(p['profit'])}) · {label}")
    best = max(pairs, key=lambda p: p["profit"])
    if mode == "drop":
        first = f"Cop or drop? 👟 {best['n']} retails for {usd(best['r'])} and eBay pairs are going for {usd(best['v'])}"
        ask = "Which one are you copping? 👇"
    else:
        flips = sum(p["call"] == "cop" for p in pairs)
        first = f"Did it flip? 📈 {flips} of last week's {len(pairs)} drops made money on eBay after fees"
        ask = "Did you cop any of these? 👇"
    note = ("eBay = median sold price (5+ sales) or the low end of new pairs listed. Profit after ~8% tax, eBay fees and shipping. "
            "Prices vary by size and change fast.")
    cap = (f"{first}\n\n" + "\n".join(lines) + f"\n\n{note}\n\n{ask}\n\n"
           f"🛒 Links for every pair (eBay links are affiliate links): market.driveyourstyle.net/social-kicks (link in bio)\n\n{HASHTAGS}")
    cap_tt = f"{first} {ask} Links in bio #sneakers #copordrop #resell #jordan #nike"
    short = (f"Cop or drop? Retail vs resale for {when} 👟" if mode == "drop" else f"Did these sneakers flip? Retail vs resale 👟")[:100]
    return first, cap, cap_tt, short


def main(argv):
    spec, site, out_root = json.load(open(argv[0])), argv[1], argv[2]
    day_, mode = spec["date"], spec.get("mode", "drop")
    pairs = load(spec, site)
    pairs.sort(key=lambda p: -p["profit"])
    if len(pairs) < (1 if mode == "drop" else 2):
        print(f"::warning title=Kicks social::only {len(pairs)} pairs with retail and resale data; nothing built")
        return
    ds = sorted({p["d"] for p in pairs})
    a, b = date.fromisoformat(ds[0]), date.fromisoformat(ds[-1])
    when = day(ds[0], "%a %b %d") if a == b else (f"{a:%b} {a.day}–{b.day}" if a.month == b.month else f"{a:%b} {a.day}–{b:%b} {b.day}")
    first, cap, cap_tt, short = captions(pairs, mode, when)
    title = ("Cop or drop? " if mode == "drop" else "Did it flip? ") + when
    out = os.path.join(out_root, day_)
    os.makedirs(out, exist_ok=True)
    slides = [cover(pairs, mode, when)] + [pair_slide(p, mode, i, len(pairs)) for i, p in enumerate(pairs, 1)] + [cta(mode)]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        if "--offline" in argv:
            pg.route(re.compile(r"static\.nike\.com|images\.|cdn"), lambda r: r.fulfill(path=os.environ["FAKE_SHOE"], content_type="image/jpeg"))
        tmp = os.path.abspath(os.path.join(out, "_slide.html"))
        paths = []
        for i, body in enumerate(slides, 1):
            open(tmp, "w", encoding="utf-8").write(BASE % (FONT_CSS, body))
            pg.goto("file://" + tmp, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            paths.append(os.path.join(out, f"slide-{i}.jpg"))
            pg.screenshot(path=paths[-1], type="jpeg", quality=92)
        os.remove(tmp)
        from tiktok import full_screen
        tt = full_screen(pg, paths, out, foot="Retail vs resale · market.driveyourstyle.net")
        b.close()
    video = None
    if "--no-video" not in argv:
        from tiktok import make_short
        video = make_short(tt, os.path.join(out, "short.mp4"), per=3.6)
    base = f"{SITE}/social-kicks/{day_}"
    post = {"date": day_, "mode": mode, "title": title, "first": first, "caption": cap, "caption_tiktok": cap_tt, "short_title": short,
            "slides": [f"{base}/slide-{i}.jpg" for i in range(1, len(slides) + 1)],
            "slides_tiktok": [f"{base}/tt-{i}.jpg" for i in range(1, len(tt) + 1)],
            "short": f"{base}/short.mp4" if video else None, "page": f"{base}/",
            "pairs": [{k: p.get(k) for k in ("c", "n", "d", "r", "v", "src", "call", "profit")} for p in pairs]}
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(page(post, pairs, mode, day_))
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(out_root, "index.html"), "w").write(
        f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={day_}/"><link rel="canonical" href="{day_}/"><a href="{day_}/">{esc(title)}</a>')
    print(f"kicks social: {mode} {len(pairs)} pairs, {len(slides)} slides -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
