"""Official set logos for English Pokémon sets, from the free Pokémon TCG API
(pokemontcg.io). Matched to TCGplayer sets by name, then by release date.

The API list is cached in data/catalog/ptcg-sets.json and refreshed weekly.
"""
import json
import os
import re
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

import config

API = "https://api.pokemontcg.io/v2/sets?pageSize=250&page={page}&select=id,name,series,releaseDate,images"
CACHE = os.path.join(config.DATA_DIR, "catalog", "ptcg-sets.json")

# TCGplayer name -> Pokémon TCG API name, where the two differ
ALIASES = {
    "SV: Scarlet & Violet 151": "151",
    "SM Base Set": "Sun & Moon",
    "SV: Scarlet & Violet Promo Cards": "Scarlet & Violet Black Star Promos",
    "SWSH: Sword & Shield Promo Cards": "SWSH Black Star Promos",
    "SM Promos": "SM Black Star Promos",
    "XY Promos": "XY Black Star Promos",
    "Black and White Promos": "BW Black Star Promos",
    "ME: Mega Evolution Promo": "Mega Evolution Black Star Promos",
    "Generations: Radiant Collection": "Generations",
    "Trading Card Game Classic": "Pokémon TCG Classic",
}


def norm(name):
    n = name.lower().replace("pokémon", "pokemon").replace("&", "and")
    n = re.sub(r"^(me|sv|swsh|sm|xy|bw|m)\d*[a-z]?\s*[:\-–]\s*", "", n)   # "ME05: ", "SM - "
    n = re.sub(r"^(scarlet and violet|sword and shield|sun and moon)\s*[:\-–]\s*", "", n)
    n = re.sub(r"\b(base set|pokemon tcg|tcg)\b", " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def tokens(name):
    return set(re.findall(r"[a-z0-9]+", name.lower().replace("pokémon", "pokemon").replace("&", "and"))) - {"the", "and", "of", "pokemon", "tcg", "set"}


def fetch(log=print):
    fresh = None
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            fresh = json.load(f)
        age = datetime.now(timezone.utc) - datetime.fromisoformat(fresh.get("fetched", "2000-01-01T00:00:00+00:00"))
        if age < timedelta(days=2):
            return fresh["sets"]
    rows, page = [], 1
    try:
        while page < 10:
            req = urllib.request.Request(API.format(page=page), headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            rows += data.get("data", [])
            if len(rows) >= data.get("totalCount", 0) or not data.get("data"):
                break
            page += 1
            time.sleep(0.5)
    except Exception as err:  # logos are a nice-to-have; never break the build
        log(f"logos: could not refresh ({err}); using cache" if fresh else f"logos: unavailable ({err})")
        return fresh["sets"] if fresh else []
    sets = [{"n": r["name"], "d": (r.get("releaseDate") or "").replace("/", "-"), "lg": (r.get("images") or {}).get("logo")} for r in rows]
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"fetched": datetime.now(timezone.utc).isoformat(), "sets": sets}, f)
    log(f"logos: {len(sets)} set logos")
    return sets


def attach(groups, log=print):
    """Add "lg" (logo URL) to English Pokémon groups that match a known set."""
    sets = [s for s in fetch(log) if s.get("lg")]
    by_name = {}
    for s in sets:
        by_name.setdefault(norm(s["n"]), []).append(s)
    matched = 0
    for g in groups.values():
        g.pop("lg", None)
        if g.get("k") != "pokemon":
            continue
        name = ALIASES.get(g["name"], g["name"])
        m = re.match(r"McDonald's (?:Promos|Collection) (\d{4})", name)
        if m:
            name = f"McDonald's Collection {m.group(1)}"
        cands = by_name.get(norm(name), [])
        if len(cands) > 1 and g.get("pub"):
            cands = sorted(cands, key=lambda s: abs((date.fromisoformat(s["d"]) - date.fromisoformat(g["pub"])).days) if s["d"] else 9999)
        pick = cands[0] if cands else None
        if pick is None and g.get("pub"):  # same release week and similar name
            gt, gd = tokens(norm_keep(g["name"])), date.fromisoformat(g["pub"])
            best = None
            for s in sets:
                if not s["d"] or abs((date.fromisoformat(s["d"]) - gd).days) > 3:
                    continue
                st = tokens(s["n"])
                if (gt - st) & {"promo", "promos", "kit", "trainer", "collection", "deck", "decks", "box"}:
                    continue  # don't give a promo/product group the main set's logo
                score = len(gt & st) / max(1, len(gt | st))
                if score >= 0.5 and (best is None or score > best[0]):
                    best = (score, s)
            pick = best[1] if best else None
        if pick:
            g["lg"] = pick["lg"]
            matched += 1
    log(f"logos: matched {matched} Pokémon sets")
    attach_scrydex(groups, log)


# ---- Lorcana / Riftbound set logos (images.scrydex.com) -----------------------------
# The CDN answers every path, returning the game's own logo when it has no set logo, so each
# guess is checked against that placeholder. Results are cached; misses are retried weekly.
SCRYDEX = "https://images.scrydex.com/{game}/{code}-logo/logo"
SCRYDEX_CACHE = os.path.join(config.DATA_DIR, "catalog", "scrydex-logos.json")
KNOWN = {"The First Chapter": "TFC", "Rise of the Floodborn": "ROF", "Into the Inklands": "ITI", "Ursula's Return": "URR",
         "Shimmering Skies": "SSK", "Azurite Sea": "AZS", "Archazia's Island": "ARI", "Reign of Jafar": "ROJ", "Fabled": "FAB"}
SMALL = {"of", "the", "in", "a", "an", "and", "to", "on"}
SKIP_LOGO = re.compile(r"promo|judge|prototype|bundle|sleeve|champion|worlds|organized|quest|deck|gift", re.I)


def _get(url):
    import hashlib
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return hashlib.md5(resp.read()).hexdigest() if resp.headers.get("content-type", "").startswith("image/") else None


def guesses(name, abbr):
    words = re.findall(r"[A-Za-z]+", name.replace("'s", ""))
    big = [w for w in words if w.lower() not in SMALL]
    c = [abbr or "", KNOWN.get(name, "")]
    c += ["".join(w[0] for w in words), "".join(w[0] for w in big),
          "".join(w[0] for w in words if w.lower() not in ("the", "a", "an")), (big[0][0] + big[-1][:2]) if len(big) >= 2 else ""]
    if len(big) == 1:
        w = big[0].upper()
        c += [w[:3], w[0] + "".join(ch for ch in w[1:] if ch not in "AEIOU")[:2], w[:2] + w[-1]]
    if len(big) >= 2:
        a, b = big[0].upper(), big[1].upper()
        c += [a[:2] + b[0], a[0] + b[:2], a[0] + b[0] + b[-1], a[0] + a[-1] + b[0]]
    out = []
    for x in c:
        x = x.upper()
        if 2 <= len(x) <= 5 and x not in out:
            out.append(x)
    return out


def attach_scrydex(groups, log=print):
    try:
        with open(SCRYDEX_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    now, placeholder, found = time.time(), {}, 0
    used = {(k.split("|")[0], v["code"]): k for k, v in cache.items() if v.get("code")}   # a code belongs to one set
    for g in groups.values():
        game = g.get("k")
        if game not in ("lorcana", "riftbound") or SKIP_LOGO.search(g["name"]):
            continue
        key = f"{game}|{g['name']}"
        hit = cache.get(key)
        if hit and hit.get("code"):
            g["lg"] = SCRYDEX.format(game=game, code=hit["code"]); found += 1
            continue
        if hit and now - hit.get("t", 0) < 7 * 86400:
            continue
        try:
            if game not in placeholder:
                placeholder[game] = _get(SCRYDEX.format(game=game, code="ZZZQ"))
            code = None
            for cand in guesses(g["name"], g.get("abbr")):
                if used.get((game, cand), key) != key or (cand in KNOWN.values() and KNOWN.get(g["name"]) != cand):
                    continue
                h = _get(SCRYDEX.format(game=game, code=cand))
                if h and h != placeholder[game]:
                    code = cand
                    break
        except Exception as err:  # never break the build over logos
            log(f"logos: scrydex check failed ({err})")
            break
        cache[key] = {"code": code, "t": now}
        if code:
            used[(game, code)] = key
        if code:
            g["lg"] = SCRYDEX.format(game=game, code=code); found += 1
    os.makedirs(os.path.dirname(SCRYDEX_CACHE), exist_ok=True)
    with open(SCRYDEX_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    log(f"logos: {found} Lorcana/Riftbound set logos")


def norm_keep(name):
    return re.sub(r"^(ME|SV|SWSH|SM|XY|BW|M)\d*[a-z]?\s*[:\-–]\s*", "", name, flags=re.I)
