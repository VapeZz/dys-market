"""Daily Market Brief as an Instagram/Facebook Story (1080x1920), only on days worth posting.

    python tools/intel_story.py site data/intel-daily [--force]

Reads site/data/intel.json (tools/intel.py). Posts only when the market actually moved:
  an index moved 1%+ in a day, or a $20+ card moved 10%+ in a day,
and the story isn't a repeat: the same headline + lead card as any of the last 3 posted days is skipped.
Writes <out>/<date>/story.jpg + post.json and <out>/latest.json ({"post": false, "reason": ...} on quiet days).
<out>/history.json remembers what was posted (the nightly job keeps data/ between runs).
"""
import json
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SITE = "https://market.driveyourstyle.net"
IDX_MIN, CARD_MIN_PCT, CARD_MIN_P = 1.0, 10.0, 2000


def clean(n):
    return re.sub(r" \((Holofoil|Normal|Foil)\)$", "", n).replace(" (Foil)", "")


def decide(d, history):
    big_idx = [i for i in d["indices"] if i.get("d1") is not None and abs(i["d1"]) >= IDX_MIN]
    movers = [m for m in d["movers"]["up"] + d["movers"]["down"] if m["p"] >= CARD_MIN_P and abs(m["d1"]) >= CARD_MIN_PCT]
    lead = max(movers, key=lambda m: abs(m["d1"]), default=None)
    if not big_idx and not lead:
        return None, "quiet day: no index moved 1%+ and no $20+ card moved 10%+"
    sig = f"{d['brief']['head']}|{lead['id'] if lead else ''}"
    cutoff = (date.fromisoformat(d["date"]) - timedelta(days=3)).isoformat()
    if any(h.get("sig") == sig and h["date"] >= cutoff for h in history):
        return None, "same story as a recent post"
    return {"sig": sig, "lead": lead, "idx": big_idx}, ""


def body(d, lead):
    from social import LOGO, esc, img
    money = lambda c: f"${c / 100:,.0f}" if c >= 10000 else f"${c / 100:,.2f}"
    day = date.fromisoformat(d["date"]).strftime("%b %-d").upper()
    tiles = "".join(
        f'''<div style="flex:1;border:3px solid rgba(242,240,235,.18);border-radius:22px;padding:22px 18px;text-align:left">
<div style="font-family:ui-monospace,Menlo,monospace;font-size:22px;letter-spacing:.1em;color:#9a968f">{esc(i["name"].upper())}</div>
<div style="font-family:'Barlow Condensed';font-weight:800;font-size:58px;line-height:1.05;margin-top:6px">{money(i["v"])}</div>
<div style="font-family:ui-monospace,Menlo,monospace;font-size:28px;font-weight:700;margin-top:6px;color:{"#3ee08f" if (i.get("d1") or 0) >= 0 else "#ff6b81"}">1D {"+" if (i.get("d1") or 0) >= 0 else ""}{(i.get("d1") or 0):.1f}%</div></div>'''
        for i in d["indices"][:3])
    lead_html = ""
    if lead:
        up = lead["d1"] >= 0
        lead_html = f'''<div style="margin-top:44px;width:920px;display:flex;gap:30px;align-items:center;border:3px solid rgba(242,240,235,.18);border-radius:26px;padding:26px;text-align:left">
{"" if lead["k"] == "one-piece" else f'<div class="card" style="flex:0 0 230px;height:322px"><img src="{img(lead["id"])}"></div>'}
<div><div style="font-family:ui-monospace,Menlo,monospace;font-size:24px;letter-spacing:.12em;color:#e7b84a">TOP MOVER · 24H</div>
<div style="font-family:'Barlow Condensed';font-weight:800;font-size:{56 if len(clean(lead["n"])) < 24 else 44}px;line-height:1;margin-top:10px;text-transform:uppercase">{esc(clean(lead["n"]))}</div>
<div style="font-size:28px;color:#bdb9b2;margin-top:8px">{esc(lead["sn"])}</div>
<div style="font-family:'Barlow Condensed';font-weight:800;font-size:96px;line-height:1;margin-top:14px;color:{"#3ee08f" if up else "#ff6b81"}">{"↑" if up else "↓"} {abs(lead["d1"]):.0f}%</div>
<div style="font-size:30px;color:#d8d5cf">{money(lead["was"])} → {money(lead["p"])}</div></div></div>'''
    return f'''<div class="slide" style="height:1920px;padding:150px 80px 360px;align-items:center;text-align:center">
<img src="file://{LOGO}" style="height:96px">
<div class="tag" style="margin-top:40px">Daily market brief · {day}</div>
<div style="margin-top:40px;font-family:'Barlow Condensed';font-weight:800;font-size:{88 if len(d["brief"]["head"]) < 50 else 74}px;line-height:.98;text-transform:uppercase;max-width:940px">{esc(d["brief"]["head"])}</div>
<div style="margin-top:44px;width:920px;display:flex;gap:16px">{tiles}</div>
{lead_html}
<div style="margin-top:auto;font-family:'Barlow Condensed';font-weight:700;font-size:50px;border:4px solid #f2f0eb;padding:14px 34px 10px">Full brief · link in bio</div></div>'''


def main(argv):
    site, out = argv[0], argv[1]
    force = "--force" in argv
    d = json.load(open(os.path.join(site, "data", "intel.json")))
    os.makedirs(out, exist_ok=True)
    hpath = os.path.join(out, "history.json")
    try:
        history = json.load(open(hpath))
    except (OSError, ValueError):
        history = []
    day_dir = os.path.join(out, d["date"])
    if os.path.exists(os.path.join(day_dir, "post.json")) and not force:     # already decided today
        post = json.load(open(os.path.join(day_dir, "post.json")))
        json.dump(post, open(os.path.join(out, "latest.json"), "w"), ensure_ascii=False)
        print(f"intel story: already made for {d['date']} (post={post.get('post')})")
        return
    pick, reason = decide(d, [h for h in history if h["date"] != d["date"]])
    os.makedirs(day_dir, exist_ok=True)
    if not pick:
        post = {"date": d["date"], "post": False, "reason": reason}
    else:
        from playwright.sync_api import sync_playwright
        from social import BASE, FONT_CSS
        html = BASE.replace("height:1350px", "height:1920px") % (FONT_CSS, body(d, pick["lead"]))
        tmp = os.path.abspath(os.path.join(day_dir, "_s.html"))
        open(tmp, "w", encoding="utf-8").write(html)
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1080, "height": 1920})
            pg.goto("file://" + tmp, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=os.path.join(day_dir, "story.jpg"), type="jpeg", quality=90)
            b.close()
        os.remove(tmp)
        post = {"date": d["date"], "post": True, "head": d["brief"]["head"], "story": f"{SITE}/{os.path.basename(out.rstrip('/'))}/{d['date']}/story.jpg",
                "link": f"{SITE}/intel.html?ref=story"}
        history = [h for h in history if h["date"] != d["date"]] + [{"date": d["date"], "sig": pick["sig"]}]
        json.dump(history[-30:], open(hpath, "w"), ensure_ascii=False)
    json.dump(post, open(os.path.join(day_dir, "post.json"), "w"), ensure_ascii=False)
    json.dump(post, open(os.path.join(out, "latest.json"), "w"), ensure_ascii=False)
    print(f"intel story: {'made' if post['post'] else 'skipped'} for {d['date']}" + (f" ({post.get('reason')})" if not post["post"] else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
