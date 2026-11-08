"""Extra card photos for cards with no photo anywhere on TCGplayer, only from sources whose written terms allow it.

Yu-Gi-Oh!: YGOPRODeck API (https://db.ygoprodeck.com/api-guide-v2/): free to use; pull each image once and store it
yourself; at most 20 requests a second (we stay around 4). Credited on legal.html.

Reads the weekly photo audit, skips cards that already show a stand-in from another printing, and writes
<out>/ygo/<productId>.jpg plus <out>/index.json {productId: "img/extra/ygo/<productId>.jpg"} (the site's last
photo fallback). Names YGOPRODeck doesn't have are remembered in <out>/misses.json and retried after 30 days.

Pokémon Japan (games=pokemon-jp): TCGdex API (free, no key; we pull each image once). TCGplayer's Japanese sets are
paired with TCGdex's by set code AND matching card total, then cards by number. dry=1 only matches and writes
<out>/report.json plus a few sample images, for checking before anything goes on the site.

usage: python tools/extra_photos.py audit=img-audit.json out=photos-dir [games=yugioh|pokemon-jp] [dry=1]
"""
import re
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

SITE = "https://market.driveyourstyle.net/data/"
YGO_API = "https://db.ygoprodeck.com/api/v7/cardinfo.php?name="
UA = {"User-Agent": "DriveYourStyleMarket/1.0 (+https://driveyourstyle.net)"}


def fetch(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
        return r.read()


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def main():
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    audit, out = load(args["audit"], {}), args["out"]
    os.makedirs(os.path.join(out, "ygo"), exist_ok=True)
    idx_path, miss_path = os.path.join(out, "index.json"), os.path.join(out, "misses.json")
    idx, misses = load(idx_path, {}), load(miss_path, {})
    today = date.today()
    retry_before = (today - timedelta(days=30)).isoformat()
    alt = json.loads(fetch(SITE + "img-alt.json"))
    nophoto = {m["id"] for m in audit.get("nophoto", [])} | {m["id"] for m in audit.get("missing", [])}

    # Yu-Gi-Oh! cards with no photo of their own and no working stand-in, not fetched yet
    names = {}
    for m in audit.get("missing", []):
        if m["k"] != "yugioh" or m["t"] != "c" or str(m["id"]) in idx:
            continue
        if str(m["id"]) in alt and alt[str(m["id"])] not in nophoto:
            continue
        name = m["n"].split(" (")[0].strip()
        if name.startswith("Token:"):   # character tokens ("Token: Joey and ...") are product-only art, not in the database
            continue
        names.setdefault(name, []).append(m["id"])

    found = new = 0
    for name, pids in sorted(names.items()):
        if misses.get(name, "") > retry_before:
            continue
        try:
            data = json.loads(fetch(YGO_API + urllib.parse.quote(name)))
            url = data["data"][0]["card_images"][0]["image_url"]
        except (urllib.error.HTTPError, KeyError, IndexError, ValueError):
            misses[name] = today.isoformat()
            time.sleep(0.25)
            continue
        time.sleep(0.25)
        first = os.path.join(out, "ygo", f"{pids[0]}.jpg")
        try:
            body = fetch(url)   # each image is pulled once; later runs skip cards already in index.json
        except Exception:
            continue
        time.sleep(0.25)
        with open(first, "wb") as f:
            f.write(body)
        for pid in pids:
            if pid != pids[0]:
                shutil.copyfile(first, os.path.join(out, "ygo", f"{pid}.jpg"))
            idx[str(pid)] = f"img/extra/ygo/{pid}.jpg"
            new += 1
        found += 1
        misses.pop(name, None)

    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, separators=(",", ":"))
    with open(miss_path, "w", encoding="utf-8") as f:
        json.dump(misses, f, ensure_ascii=False, indent=0)
    print(f"Yu-Gi-Oh!: {len(names)} card names without a photo; {found} found on YGOPRODeck; {new} cards got a photo; "
          f"{len(idx)} extra photos in total; not in the database: {sorted(misses)[:15]}")


TCGDEX = "https://api.tcgdex.net/v2/ja/"
# Hand-checked pairs where TCGplayer's set code / card total don't line up with TCGdex's on their own.
# Cards still have to match by number, and a numbered total (e.g. 016/070) must equal the TCGdex set's official count.
JP_MAP = {
    "L1: HeartGold Collection": "L1a",
    "L1: SoulSilver Collection": "L1b",
    "Pokemon VS": "VS1",
    "M-P Promotional Cards": "M-P",
    "SV-P Promotional Cards": "SV-P",
    "Start Deck 100 Battle Collection": "MC",
}
NO_RE = re.compile(r"^(\d+)/([A-Za-z0-9-]+)$")


def code_of(s):
    """Set code: TCGplayer's abbreviation or the part before ":" in the name, lowercased (SV2a, s12a, M1L...)."""
    c = (s.get("a") or s["n"].split(":")[0] if ":" in s["n"] else s.get("a") or "").strip()
    return re.sub(r"[^a-z0-9]", "", c.lower())


def pokemon_jp(audit, out, dry):
    """Japanese Pokémon cards with no photo anywhere on TCGplayer -> TCGdex's Japanese card image, matched by set and number."""
    sets = json.loads(fetch(SITE + "sets.json"))
    alt = json.loads(fetch(SITE + "img-alt.json"))
    nophoto = {m["id"] for m in audit.get("nophoto", [])} | {m["id"] for m in audit.get("missing", [])}
    idx = load(os.path.join(out, "index.json"), {})
    by_gid = {s["id"]: s for s in sets}
    want = {}
    for m in audit.get("missing", []):
        if m["k"] != "pokemon-jp" or m["t"] != "c" or str(m["id"]) in idx:
            continue
        if str(m["id"]) in alt and alt[str(m["id"])] not in nophoto:
            continue
        want.setdefault(m["gid"], []).append(m)
    dex = json.loads(fetch(TCGDEX + "sets"))
    time.sleep(0.3)
    print(f"Pokémon Japan: {sum(len(v) for v in want.values())} cards in {len(want)} sets; TCGdex lists {len(dex)} Japanese sets")
    print("TCGdex sample:", json.dumps(dex[:2], ensure_ascii=False)[:400])
    dex_by_id = {d["id"]: d for d in dex}
    dex_by_code = {}
    for d in dex:
        dex_by_code.setdefault(re.sub(r"[^a-z0-9]", "", d["id"].lower()), []).append(d)
    report, samples, total = [], [], 0
    for gid, cards in sorted(want.items(), key=lambda x: -len(x[1])):
        s = by_gid.get(gid)
        if not s:
            continue
        code = code_of(s)
        nums = [c["no"] for c in cards if re.match(r"^\d+/\d+$", c.get("no") or "")]
        tot = {int(n.split("/")[1]) for n in nums}
        if s["n"] in JP_MAP:
            ok = [dex_by_id[JP_MAP[s["n"]]]] if JP_MAP[s["n"]] in dex_by_id else []
        else:
            cands = dex_by_code.get(code, []) + [d for k, v in dex_by_code.items() if code and k != code and re.fullmatch(code + "[ab]", k) for d in v]
            ok = [d for d in cands if (d.get("cardCount") or {}).get("official") in tot] if tot else []
        if len(ok) != 1:
            report.append({"set": s["n"], "code": code, "cards": len(cards), "paired": None,
                           "why": "no TCGdex set with this code and card total" if not ok else f"{len(ok)} TCGdex sets fit"})
            continue
        d = ok[0]
        detail = json.loads(fetch(TCGDEX + "sets/" + urllib.parse.quote(d["id"])))
        time.sleep(0.3)
        by_no = {}
        for c in detail.get("cards", []):
            try:
                by_no[int(re.sub(r"\D", "", c["localId"]))] = c
            except ValueError:
                pass
        hits, noimg, skipped = [], 0, 0
        official = (d.get("cardCount") or {}).get("official")
        for c in cards:
            m = NO_RE.match(c.get("no") or "")
            if not m:
                skipped += 1
                continue
            den = m.group(2)
            if den.isdigit() and int(den) != official:   # e.g. a 015/023 deck card listed under a 742-card set
                skipped += 1
                continue
            named = re.search(r" - (\d+)/", c["n"])
            if named and int(named.group(1)) != int(m.group(1)):   # name and number disagree on TCGplayer: skip
                skipped += 1
                continue
            x = by_no.get(int(m.group(1)))
            if not x:
                skipped += 1
            elif not x.get("image"):
                noimg += 1
            else:
                hits.append((c, x))
        total += len(hits)
        report.append({"set": s["n"], "code": code, "cards": len(cards), "paired": d["id"], "matched": len(hits),
                       "tcgdex_no_image": noimg, "skipped": skipped,
                       "examples": [[c["n"], c["no"], x["localId"], x.get("name"), x["image"]] for c, x in hits[:3]]})
        for c, x in hits:
            if dry:
                if len(samples) < 16 and sum(1 for q in samples if q[0] == s["n"]) < 2:
                    samples.append((s["n"], c, x))
                continue
            path = os.path.join(out, "pokemon-jp", f"{c['id']}.webp")
            try:
                body = fetch(x["image"] + "/high.webp")   # pulled once; later runs skip cards already in index.json
            except Exception:
                continue
            time.sleep(0.3)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(body)
            idx[str(c["id"])] = f"img/extra/pokemon-jp/{c['id']}.webp"
    if dry:
        os.makedirs(os.path.join(out, "samples"), exist_ok=True)
        for i, (sn, c, x) in enumerate(samples):
            for tries in range(3):
                try:
                    body = fetch(x["image"] + "/low.webp")
                    with open(os.path.join(out, "samples", f"{i:02d}-{c['id']}.webp"), "wb") as f:
                        f.write(body)
                    break
                except Exception as e:
                    print("sample failed", x["image"], e)
                    time.sleep(3)
            time.sleep(0.5)
        with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
            json.dump({"matched": total, "dex_sets": dex, "sets": report, "samples": [[sn, c["n"], c["no"], x["localId"], x.get("name")] for sn, c, x in samples]},
                      f, ensure_ascii=False, indent=1)
    else:
        with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as f:
            json.dump(idx, f, separators=(",", ":"))
    paired = [r for r in report if r["paired"]]
    print(f"Pokémon Japan: {len(paired)} of {len(report)} sets paired with TCGdex; {total} cards matched"
          + (" (trial, nothing downloaded for the site)" if dry else ""))
    for r in report[:25]:
        print(" ", r["set"], "|", r["code"], "|", r["cards"], "cards |", r.get("paired") or r.get("why"), "|", r.get("matched", ""),
              "| no TCGdex image:", r.get("tcgdex_no_image", ""), "| skipped:", r.get("skipped", ""))


if __name__ == "__main__":
    a = dict(x.split("=", 1) for x in sys.argv[1:])
    if a.get("games", "yugioh") == "pokemon-jp":
        os.makedirs(a["out"], exist_ok=True)
        pokemon_jp(load(a["audit"], {}), a["out"], a.get("dry") == "1")
    else:
        main()
