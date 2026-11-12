"""Preview only: render the new cover slides from the live feeds' data. Nothing is published or scheduled.

    python tools/cover_preview.py PAGES_DIR OUT_DIR
"""
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily_card  # noqa: E402
import deals_social  # noqa: E402
import sneaker_social  # noqa: E402
import social  # noqa: E402
import tiktok  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

pages, out = sys.argv[1], os.path.abspath(sys.argv[2])
os.makedirs(out, exist_ok=True)
jobs, notes = [], []
for feed in ("social-daily", "social-daily-other"):
    d = json.load(open(os.path.join(pages, feed, "latest.json")))
    label = daily_card.GAMES[d["game"]][0]
    jobs.append((feed, daily_card.slides(d["cards"], d["theme"], "this week", d["game"], {})[0], 1920))
    notes.append({"feed": feed, "first_line": daily_card.first_line(d["theme"], len(d["cards"]), label, "this week", d["cards"]),
                  "youtube": daily_card.yt_title(d["theme"], d["cards"], "this week", d["game"]), "tiktok_title": daily_card.tt_title(d["theme"], d["cards"], label)})
    if feed == "social-daily":   # layout checks for the other headlines (same cards, numbers are examples)
        for th in ("dip", "newset"):
            cards = [dict(c, pct=-abs(c["pct"]) / 3) if th == "dip" else dict(c) for c in d["cards"]]
            jobs.append((f"layout-{th}", daily_card.slides(cards, th, "this week", d["game"], {})[0], 1920))
d = json.load(open(os.path.join(pages, "social-deals", "latest.json")))
if d.get("items"):
    jobs.append(("social-deals", deals_social.cover([dict(i, off=1 - i["p"] / i["m"]) for i in d["items"]]), 1350))
d = json.load(open(os.path.join(pages, "social-sneakers", "latest.json")))
start = date.fromisoformat(d["date"]) + timedelta(days=1)
week, feat = sneaker_social.pick(pages, start, start + timedelta(days=6))
if feat:
    jobs.append(("social-sneakers", sneaker_social.cover(feat, d.get("span", "")), 1350))
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, body, h in jobs:
        pg = b.new_page(viewport={"width": 1080, "height": h})
        base = social.BASE if h == 1350 else social.BASE.replace("height:1350px", "height:1920px")
        tmp = os.path.join(out, "_s.html")
        open(tmp, "w", encoding="utf-8").write(base % (social.FONT_CSS, body))
        pg.goto("file://" + tmp, wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        path = os.path.join(out, name + ".jpg")
        pg.screenshot(path=path, type="jpeg", quality=88)
        if h == 1350:   # the 9:16 frame TikTok and Shorts get
            tiktok.full_screen(pg, [path], out)
            os.replace(os.path.join(out, "tt-1.jpg"), os.path.join(out, name + "-tt.jpg"))
        os.remove(tmp)
        pg.close()
    b.close()
json.dump(notes, open(os.path.join(out, "notes.json"), "w"), indent=1, ensure_ascii=False)
print("rendered", [j[0] for j in jobs])
