"""Sneaker "Cop or drop?" (release day) and "Did it flip?" (weekly recap) posts: retail vs eBay resale.

    python tools/kicks_social.py SPEC.json SITE_DIR OUT_ROOT [--offline]

SPEC: {"date": "2026-11-01", "mode": "drop" | "recap",
       "pairs": [{"c": style code, "n"?, "r"?, "d"?, "sold_n"?, "sold_med"?, "sold_days"?, "ask_n"?, "ask_low"?, "ask_p25"?}]}
Missing name / retail / date / photo come from SITE_DIR/sneakers.json and SITE_DIR/data/sneaker-images.json.
Recap mode also scores "our calls": what we said before the release (the release calendar's pick, else the call in
our Cop or drop post, read from OUT_ROOT/<date>/post.json) vs how it did. "Cop" means we expected a flip; "Cop to
wear", "Wait" and "Drop" mean we didn't. Adds a scorecard slide when 2+ pairs had a call.
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
SAID = {"cop": ("Cop", "#3ee08f"), "wear": ("Cop to wear", "#a78bfa"), "wait": ("Wait", "#ffd36e"), "drop": ("Drop", "#ff7a59")}
DID = {"cop": "flipped", "wear": "was a wash", "drop": "bricked"}


def past_calls(site, out_root):
    """Our call on each pair before it dropped, by style code: the release calendar's pick (cop / wear / wait),
    else the call in our Cop or drop post the night before (cop / wear / drop)."""
    calls = {}
    if out_root and os.path.isdir(out_root):
        for d in sorted(os.listdir(out_root)):
            try:
                post = json.load(open(os.path.join(out_root, d, "post.json")))
            except (OSError, ValueError):
                continue
            if post.get("mode") == "drop":
                for p in post.get("pairs", []):
                    if p.get("c") and p.get("call") in SAID:
                        calls[p["c"]] = (p["call"], "our Cop or drop post")
    try:
        picks = json.load(open(os.path.join(site, "sneakers.json"))).get("picks", [])
    except (OSError, ValueError):
        picks = []
    for p in picks:
        if p.get("c") and p.get("v") in SAID:
            calls[p["c"]] = (p["v"], "our release calendar")
    return calls


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


def load(spec, site, out_root=None):
    calls = past_calls(site, out_root) if spec.get("mode") == "recap" else {}
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
        if not q.get("im"):
            print(f"::warning title=Kicks: no photo::{q['c']} {q.get('n', '')} left out (every pair needs an official photo)")
            continue
        if not q.get("r"):
            continue                      # no retail price, no call
        v, src = resale(q)
        if v is None:
            continue
        q["v"], q["src"] = v, src
        q["call"], q["profit"] = verdict(q["r"], v)
        if q["c"] in calls:   # recap: did our call before the release hold up? "cop" = we expected a flip
            q["said"], q["said_src"] = calls[q["c"]]
            q["right"] = (q["said"] == "cop") == (q["call"] == "cop")
        out.append(q)
    return out


def score(pairs):
    called = [p for p in pairs if p.get("said")]
    return sum(p["right"] for p in called), len(called)


def scorecard(pairs):
    called = [p for p in pairs if p.get("said")]
    right, n = score(pairs)
    rows = "".join(f"""<div style="display:flex;align-items:center;gap:24px;padding:14px 0;border-top:2px solid rgba(242,240,235,.12)">
<div style="width:108px;height:108px;flex:none;background:#f2f2f2;border-radius:18px;overflow:hidden">{shoe(p)}</div>
<div style="flex:1;min-width:0"><div style="font-family:'Barlow Condensed';font-weight:800;font-size:40px;line-height:1.05;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(p['n'])}</div>
<div style="margin-top:8px;font-size:30px;color:#bdb9b2">We said <b style="color:{SAID[p['said']][1]}">{SAID[p['said']][0]}</b> · it <b style="color:{CALL['recap'][p['call']][1]}">{DID[p['call']]}</b></div></div>
<div style="width:84px;height:84px;flex:none;border-radius:50%;display:grid;place-content:center;font-family:'Barlow Condensed';font-weight:800;font-size:34px;letter-spacing:.04em;color:#050404;background:{'#3ee08f' if p['right'] else '#ff7a59'}">{'RIGHT' if p['right'] else 'MISS'}</div></div>"""
                   for p in called[:6])
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}" style="height:72px"><div class="tag">Scorecard</div></div>
<div style="margin-top:34px;display:flex;align-items:flex-end;justify-content:space-between">
 <div style="font-family:'Barlow Condensed';font-weight:800;font-size:120px;line-height:.9;text-transform:uppercase">Our<br><span class="holo">calls</span></div>
 <div style="text-align:right"><div style="font-family:'Barlow Condensed';font-weight:800;font-size:150px;line-height:.9">{right}<span style="color:#8f8a84">/{n}</span></div><div style="font-size:30px;color:#bdb9b2">right</div></div></div>
<div style="margin-top:30px">{rows}</div>
<div style="margin-top:auto;font-size:24px;color:#8f8a84">We said = our call before release (release calendar pick or Cop or drop post). "Cop" means we expected it to flip after fees.</div></div>"""


def cover(pairs, mode, when, sc=(0, 0)):
    spots = [(330, 0, 0, 5, 380), (60, 110, -9, 4, 340), (600, 110, 9, 4, 340)]
    fan = "".join(
        f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{w}px;transform:rotate({rot}deg);z-index:{z};'
        f'background:#f2f2f2;border-radius:28px;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.6)">{shoe(r)}</div>'
        for r, (x, y, rot, z, w) in zip([p for p in pairs if p.get("im")][:3],
                                        spots if sum(bool(p.get("im")) for p in pairs) > 1 else [(250, 0, 0, 5, 520)]))
    best = max(pairs, key=lambda p: p["profit"])
    title = 'Cop or<br><span class="holo">drop?</span>' if mode == "drop" else 'Did it<br><span class="holo">flip?</span>'
    sub = (f"Retail vs eBay resale · {esc(when)}" if mode == "drop" else f"Last week's drops, retail vs eBay sold · {esc(when)}")
    hook = (f"{esc(best['n'])}: {usd(best['r'])} retail → {usd(best['v'])} on eBay" if best["profit"] > 0
            else "Which ones are worth it? Swipe")
    if mode == "drop":   # countdown + reveal: don't give away any eBay price or call on the cover
        sub = f"{len(pairs)} pairs · {esc(when)}"
        hook = "Vote cop or drop on each pair, then swipe for our call" if len(pairs) > 1 else "Vote cop or drop, then swipe for our call"
    score_html = ""
    if mode == "recap" and sc[1] >= 2:
        score_html = ("<div style=\"margin-top:14px;font-family:'Barlow Condensed';font-weight:800;font-size:44px;letter-spacing:.04em;"
                      f"text-transform:uppercase\">Our calls: <span class=\"holo\">{sc[0]} of {sc[1]} right</span></div>")
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}"><div class="tag">{'Release day' if mode == 'drop' else 'Resale recap'}</div></div>
<div style="margin-top:48px;font-family:'Barlow Condensed';font-weight:800;font-size:150px;line-height:.9;text-transform:uppercase">{title}</div>
<div style="margin-top:20px;font-size:38px;color:#d8d5cf">{sub}</div>
<div style="margin-top:14px;font-size:36px;line-height:1.25;color:#f2f0eb;font-weight:700;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{hook}</div>
{score_html}
<div style="position:relative;height:{390 if score_html else 520}px;margin-top:{20 if score_html else 30}px{';transform:scale(.78);transform-origin:top center' if score_html else ''}">{fan}</div>
<div class="bar" style="margin-top:auto;margin-bottom:26px"></div>
<div class="foot"><span>{'Swipe to vote →' if mode == 'drop' else 'Swipe for the numbers →'}</span><span>market.driveyourstyle.net</span></div></div>"""


def vote_slide(p, k):
    """Cop or drop countdown: same layout as the reveal, with the eBay price and our call hidden."""
    name = p["n"]
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}" style="height:72px">
 <div style="text-align:right;font-family:'Barlow Condensed';font-weight:800;line-height:.95;text-transform:uppercase"><div style="font-size:40px;color:#bdb9b2">Drops {day(p['d'], '%a')} · #{k}</div><div class="holo" style="font-size:88px">{day(p['d'], '%b %d')}</div></div></div>
<div style="margin-top:26px;height:560px;background:#f2f2f2;border-radius:28px;overflow:hidden;position:relative">{shoe(p, True)}
 <div style="position:absolute;left:24px;top:24px;font-family:'Barlow Condensed';font-weight:800;font-size:46px;letter-spacing:.06em;text-transform:uppercase;color:#050404;background:#a78bfa;padding:10px 24px 6px;border-radius:999px">Cop or drop?</div></div>
<div style="margin-top:30px;font-family:'Barlow Condensed';font-weight:800;font-size:{60 if len(name) < 34 else 50}px;line-height:1.02;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{esc(name)}</div>
<div style="margin-top:auto;display:flex;align-items:flex-end;gap:40px">
 <div><div style="font-size:28px;color:#bdb9b2">Retail</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:104px;line-height:1">{usd(p['r'])}</div></div>
 <div style="font-family:'Barlow Condensed';font-weight:800;font-size:80px;color:#bdb9b2;padding-bottom:10px">→</div>
 <div><div style="font-size:28px;color:#bdb9b2">eBay resale</div><div class="holo" style="font-family:'Barlow Condensed';font-weight:800;font-size:104px;line-height:1">$???</div></div>
</div>
<div style="margin-top:18px;font-size:34px;font-weight:700">Cop or drop? <span style="color:#bdb9b2;font-weight:500">Vote in the comments, then swipe for our call →</span></div>
<div style="margin-top:10px;font-size:26px;color:#8f8a84">{esc(p['c'])}</div></div>"""


def said_line(p):
    if not p.get("said"):
        return ""
    label, color = SAID[p["said"]]
    mark = ('<b style="color:#3ee08f">our call was right</b>' if p["right"] else '<b style="color:#ff7a59">we missed this one</b>')
    return f'<div style="margin-top:12px;font-size:32px;color:#bdb9b2">We said <b style="color:{color}">{label}</b> before it dropped · {mark}</div>'


def pair_slide(p, mode, i, n, count=None):
    label, color = CALL[mode][p["call"]]
    name = p["n"]
    what = "eBay sold" if p["src"] == "sold" else "eBay resale"
    count = count or f"{i} / {n}"
    return f"""<div class="slide">
<div class="top"><img class="logo" src="file://{LOGO}" style="height:72px">
 <div style="text-align:right;font-family:'Barlow Condensed';font-weight:800;line-height:.95;text-transform:uppercase"><div style="font-size:40px;color:#bdb9b2">{'Drops ' if mode == 'drop' else 'Dropped '}{day(p['d'], '%a')} · {count}</div><div class="holo" style="font-size:88px">{day(p['d'], '%b %d')}</div></div></div>
<div style="margin-top:26px;height:560px;background:#f2f2f2;border-radius:28px;overflow:hidden;position:relative">{shoe(p, True)}
 <div style="position:absolute;left:24px;top:24px;font-family:'Barlow Condensed';font-weight:800;font-size:46px;letter-spacing:.06em;text-transform:uppercase;color:#050404;background:{color};padding:10px 24px 6px;border-radius:999px">{'Our call: ' if mode == 'drop' else ''}{label}</div></div>
<div style="margin-top:30px;font-family:'Barlow Condensed';font-weight:800;font-size:{60 if len(name) < 34 else 50}px;line-height:1.02;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{esc(name)}</div>
{said_line(p) if mode == 'recap' else ''}
<div style="margin-top:auto;display:flex;align-items:flex-end;gap:40px">
 <div><div style="font-size:28px;color:#bdb9b2">Retail</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:104px;line-height:1">{usd(p['r'])}</div></div>
 <div style="font-family:'Barlow Condensed';font-weight:800;font-size:80px;color:#bdb9b2;padding-bottom:10px">→</div>
 <div><div style="font-size:28px;color:#bdb9b2">{what}</div><div style="font-family:'Barlow Condensed';font-weight:800;font-size:104px;line-height:1;color:{color}">{usd(p['v'])}</div></div>
</div>
<div style="margin-top:18px;font-size:34px"><b style="color:{'#3ee08f' if p['profit'] >= 0 else '#ff7a59'}">{signed(p['profit'])}</b> <span style="color:#bdb9b2">a pair after eBay fees, shipping &amp; tax</span></div>
<div style="margin-top:10px;font-size:26px;color:#8f8a84;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(source_line(p, mode))} · {esc(p['c'])}</div></div>"""


def cta(mode):
    head = "Agree with<br>our calls?" if mode == "drop" else "Missed one?"
    return f"""<div class="slide" style="justify-content:center;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:200px">
<div style="margin-top:70px;font-family:'Barlow Condensed';font-weight:800;font-size:110px;line-height:.95;text-transform:uppercase">{head}<br><span class="holo">{'Tell us below' if mode == 'drop' else 'Links in bio'}</span></div>
<div style="margin-top:34px;font-size:40px;color:#d8d5cf;max-width:880px">{'Links in bio: ' if mode == 'drop' else ''}Retail, eBay, StockX and GOAT links for every pair, plus the full release calendar.</div>
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
<p class="p"><span>Retail <b>{usd(p['r'])}</b></span><span>{'eBay sold' if p['src'] == 'sold' else 'eBay resale'} <b class="{'g' if p['v'] >= p['r'] else 'r'}">{usd(p['v'])}</b></span><span class="v" style="background:{color}">{label}</span>{f'<span>We said <b>{SAID[p["said"]][0]}</b> · <b class="{"g" if p["right"] else "r"}">{"right" if p["right"] else "missed"}</b></span>' if mode == 'recap' and p.get('said') else ''}</p>
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
        said = f" (we said {SAID[p['said']][0]})" if mode == "recap" and p.get("said") else ""
        lines.append(f"{i}. {p['n']}: {usd(p['r'])} retail → {usd(p['v'])} eBay ({signed(p['profit'])}) · {label}{said}")
    best = max(pairs, key=lambda p: p["profit"])
    right, called = score(pairs)
    scored = mode == "recap" and called >= 2
    if mode == "drop":   # countdown + reveal: the first line asks for votes; our calls sit lower in the caption
        lo, hi = min(p["r"] for p in pairs), max(p["r"] for p in pairs)
        rng = usd(lo) if lo == hi else f"{usd(lo)}–{usd(hi)}"
        first = (f"Cop or drop? 👟 {len(pairs)} pair{'s' if len(pairs) > 1 else ''} drop {when}, {rng} retail. "
                 + ("Vote on each before you swipe 👀" if len(pairs) > 1 else "Vote before you swipe 👀"))
        ask = "Agree with our calls? 👇"
    else:
        flips = sum(p["call"] == "cop" for p in pairs)
        first = f"Did it flip? 📈 {flips} of last week's {len(pairs)} drops made money on eBay after fees"
        ask = "Did you cop any of these? 👇" + (" Think we got one wrong? Tell us." if scored else "")
    note = ("eBay = median sold price (5+ sales) or the low end of new pairs listed. Profit after ~8% tax, eBay fees and shipping. "
            "Prices vary by size and change fast.")
    scoreline = (f"Our calls before release: {right} of {called} right {'✅' if right * 2 >= called else '😬'}\n\n" if scored else "")
    cap = (f"{first}\n\n{scoreline}" + ("Our calls (no peeking 🙈):\n" if mode == "drop" else "") + "\n".join(lines) + f"\n\n{note}\n\n{ask}\n\n"
           f"🛒 Links for every pair (eBay links are affiliate links): market.driveyourstyle.net/social-kicks (link in bio)\n\n{HASHTAGS}")
    cap_tt = f"{first}{f'. Our calls went {right} for {called}' if scored else ''} {ask} Links in bio #sneakers #copordrop #resell #jordan #nike"
    short = (f"Cop or drop? Vote before the reveal 👟 Sneakers dropping {when}" if mode == "drop" else
             f"Did these sneakers flip? Our calls went {right} for {called} 👟" if scored else "Did these sneakers flip? Retail vs resale 👟")[:100]
    return first, cap, cap_tt, short


def main(argv):
    spec, site, out_root = json.load(open(argv[0])), argv[1], argv[2]
    day_, mode = spec["date"], spec.get("mode", "drop")
    pairs = load(spec, site, out_root)
    pairs.sort(key=lambda p: -p["profit"])
    sc = score(pairs)
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
    if mode == "drop":   # countdown: vote slide then reveal for each pair, the best flip (#1) last
        n = len(pairs)
        body = []
        for idx, p in enumerate(pairs[::-1]):
            body += [vote_slide(p, n - idx), pair_slide(p, mode, 0, n, count=f"#{n - idx}")]
        slides = [cover(pairs, mode, when, sc)] + body + [cta(mode)]
        per = [3.2] + [2.6, 3.4] * n + [3.2]
    else:
        slides = ([cover(pairs, mode, when, sc)] + [pair_slide(p, mode, i, len(pairs)) for i, p in enumerate(pairs, 1)] +
                  ([scorecard(pairs)] if mode == "recap" and sc[1] >= 2 else []) + [cta(mode)])
        per = 3.6
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
        video = make_short(tt, os.path.join(out, "short.mp4"), per=per)
    base = f"{SITE}/social-kicks/{day_}"
    post = {"date": day_, "mode": mode, "title": title, "first": first, "caption": cap, "caption_tiktok": cap_tt, "short_title": short,
            "slides": [f"{base}/slide-{i}.jpg" for i in range(1, len(slides) + 1)],
            "slides_tiktok": [f"{base}/tt-{i}.jpg" for i in range(1, len(tt) + 1)],
            "short": f"{base}/short.mp4" if video else None, "page": f"{base}/",
            "pairs": [{k: p.get(k) for k in ("c", "n", "d", "r", "v", "src", "call", "profit", "said", "right")} for p in pairs]}
    if mode == "recap":
        post["score"] = {"right": sc[0], "of": sc[1]}
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(page(post, pairs, mode, day_))
    json.dump(post, open(os.path.join(out, "post.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(post, open(os.path.join(out_root, "latest.json"), "w"), indent=1, ensure_ascii=False)
    hpath = os.path.join(out_root, "history.json")   # which pairs were in which kind of post (no repeats)
    try:
        hist = json.load(open(hpath))
    except (OSError, ValueError):
        hist = {}
    hist.setdefault(mode, {}).update({p["c"]: day_ for p in pairs})
    json.dump(hist, open(hpath, "w"), indent=0)
    open(os.path.join(out_root, "index.html"), "w").write(
        f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={day_}/"><link rel="canonical" href="{day_}/"><a href="{day_}/">{esc(title)}</a>')
    print(f"kicks social: {mode} {len(pairs)} pairs, {len(slides)} slides -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
