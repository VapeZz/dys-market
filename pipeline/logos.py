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


def norm_keep(name):
    return re.sub(r"^(ME|SV|SWSH|SM|XY|BW|M)\d*[a-z]?\s*[:\-–]\s*", "", name, flags=re.I)
