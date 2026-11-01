"""PSA population (how many copies got each grade) for the owner's private DYS Edge app.

    python tools/psapop.py SITE STORE

PSA's Public API looks population up by PSA "spec ID" (one per card variant), and the only way to get a
card's spec ID is a cert lookup on any slab of that card. So, for each new card:
  1. eBay Browse API (official, public listing data): find a PSA slab listing of the card and read its
     "Certification Number" item specific (one search + a few item lookups; no page scraping)
  2. PSA cert lookup -> spec ID, checked against our card (number, name, year, language, reverse/1st ed.)
  3. PSA spec population -> PSA 1-10 counts
Spec IDs are kept for good; populations are refreshed every REFRESH_DAYS.

PSA's free API allows 100 calls a day: we stop at PSA_DAILY (counted across runs per UTC day).
Their terms allow the data for our own research and sales but not publishing or sharing it, so:
  - the stored cache (STORE/cache.enc) is sealed with the "ppt" key (pipeline/sealed.py)
  - the copy for DYS Edge, SITE/data/edge/psapop.enc, is sealed with the "edge" key (only the owner's phone opens it):
    gzip'd JSON {"u": date, "c": {"<tcgplayer id>": [date, total graded, psa10, psa9, psa8, spec id]}}
Candidates: Pokemon cards (EN + JP) from SITE/data/grading*.json with PokemonPriceTracker PSA 10 prices
(SITE/data/edge/graded.enc), best grading profit first.

Needs PSA_TOKEN, EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, PPT_API_KEY (or PPT_API_KEY_NEW).
"""
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import sealed  # noqa: E402
import ebay  # noqa: E402

PSA = "https://api.psacard.com/publicapi"
PSA_DAILY = int(os.environ.get("PSA_DAILY", "95"))          # their free limit is 100/day
REFRESH_DAYS = int(os.environ.get("PSA_REFRESH_DAYS", "30"))
REFRESH_SHARE = float(os.environ.get("PSA_REFRESH_SHARE", "0.2"))   # share of the day's calls for refreshes (once there are stale ones)
RETRY_DAYS = 21                                               # a card we couldn't match is tried again after this
MAX_CERTS = 2                                                 # PSA cert lookups per card per try
FEES = 2500                                                   # grading + shipping, cents, for ranking only
TODAY = datetime.now(timezone.utc).date().isoformat()


class Stop(Exception):
    pass


def psa_get(path, cache):
    used = cache["calls"].get(TODAY, 0)
    if used >= PSA_DAILY:
        raise Stop(f"daily PSA limit reached ({PSA_DAILY})")
    # pasted tokens sometimes carry the "bearer " prefix, quotes or line breaks
    tok = re.sub(r"^bearer", "", re.sub(r"[\s\"']+", "", os.environ.get("PSA_TOKEN") or ""), flags=re.I)
    req = urllib.request.Request(PSA + path, headers={"Authorization": "bearer " + tok, "Accept": "application/json",
                                                       "User-Agent": "DYS-Market/1.0 (+https://market.driveyourstyle.net)"})
    cache["calls"][TODAY] = used + 1
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 500):
            raw = e.read()[:400].decode("utf-8", "replace")
            hint = ("blocked by PSA's firewall (Cloudflare), not the token" if re.search(r"cloudflare|cf-ray|attention required|just a moment", raw + str(e.headers), re.I)
                    else "token expired or rejected? make a new one and update PSA_TOKEN")
            print(f"psa debug: HTTP {e.code} server={e.headers.get('server')} token_len={len(tok)} body={re.sub(r'\s+', ' ', raw)[:200]!r}")
            raise Stop(f"PSA said HTTP {e.code} ({hint})")
        if e.code == 429:
            raise Stop("PSA rate limit (HTTP 429)")
        return None
    time.sleep(0.6)
    return json.loads(body) if body else None


def ebay_get(url):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + ebay.token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def base_name(n):
    return re.sub(r"\s*\([^)]*\)", "", n).split(" - ")[0].strip()


def norm_no(no):
    s = (no or "").split("/")[0].upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s.lstrip("0") or s


def certs_for(row, setname):
    """Cert numbers from PSA slab listings of this card on eBay (official Browse API)."""
    pid, sid, n, p, lo, rar, no, game, era = row
    q = f"{base_name(n)} {(no or '').split('/')[0]} PSA" + (" Japanese" if game == "pokemon-jp" else "")
    try:
        d = ebay.search(q, filters="buyingOptions:{FIXED_PRICE|AUCTION}", limit=40)
    except urllib.error.HTTPError:
        return []
    except RuntimeError as e:          # no eBay keys
        raise Stop(str(e))
    out, num, looked = [], norm_no(no), 0
    for it in d.get("itemSummaries") or []:
        if looked >= 6:
            break
        t = (it.get("title") or "").upper()
        if "PSA" not in t or (num and not re.search(rf"(?<![A-Z0-9])0*{re.escape(num)}(?![0-9])", re.sub(r"[#/]", " ", t))):
            continue
        looked += 1
        try:
            full = ebay_get(f"{ebay.API}/buy/browse/v1/item/{urllib.parse.quote(it['itemId'])}?fieldgroups=PRODUCT")
        except Exception:
            continue
        for a in full.get("localizedAspects") or []:
            if re.search(r"cert", a.get("name") or "", re.I):
                c = re.sub(r"\D", "", a.get("value") or "")
                if 7 <= len(c) <= 10 and c not in out:
                    out.append(c)
        if len(out) >= MAX_CERTS:
            break
    return out


def matches(cert, row, year):
    """Is this PSA cert the same card (variant) as our row?"""
    pid, sid, n, p, lo, rar, no, game, era = row
    c = cert or {}
    if norm_no(c.get("CardNumber")) != norm_no(no):
        return False, "number"
    subj = re.sub(r"[^A-Z0-9 ]", "", (c.get("Subject") or "").upper().replace("É", "E"))
    first = re.sub(r"[^A-Z0-9]", "", base_name(n).upper().replace("É", "E").split(" ")[0])
    if first and first not in subj.replace(" ", ""):
        return False, "name"
    brand, var = (c.get("Brand") or "").upper(), (c.get("Variety") or "").upper()
    if (game == "pokemon-jp") != ("JAPANESE" in brand):
        return False, "language"
    if ("reverse" in n.lower()) != ("REVERSE" in var):
        return False, "reverse holo"
    if ("1st edition" in n.lower()) != ("1ST EDITION" in var or "1ST EDITION" in brand):
        return False, "1st edition"
    y = re.match(r"\d{4}", c.get("Year") or "")
    if year and y and abs(int(y.group(0)) - int(year)) > 1:
        return False, "year"
    return True, ""


def pop_of(spec, cache):
    d = psa_get(f"/pop/GetPSASpecPopulation/{spec}", cache) or {}
    pp = d.get("PSAPop") or (d.get("PSASpecPopulationModel") or {}).get("PSAPop") or {}
    if not pp.get("Total"):
        return None
    return [TODAY, int(pp["Total"]), int(pp.get("Grade10") or 0), int(pp.get("Grade9") or 0), int(pp.get("Grade8") or 0)]


def candidates(site):
    sd = os.path.join(site, "data")
    graded = {}
    gp = os.path.join(sd, "edge", "graded.enc")
    if os.path.exists(gp):
        graded = json.loads(gzip.decompress(sealed.read("edge", gp)))["c"]
    rows = []
    for f in ("grading.json", "grading-cheap.json"):
        p = os.path.join(sd, f)
        if os.path.exists(p):
            rows += [r for r in json.load(open(p))["rows"] if r[7] in ("pokemon", "pokemon-jp")]
    sets, out = {}, []
    for r in rows:
        g = (graded.get(str(r[0])) or [None, {}])[1].get("psa10")
        if not g or g[1] < 3:                      # need a real PSA 10 market to be worth knowing
            continue
        profit = g[0] * 0.87 - r[3] - FEES
        if profit <= 0:
            continue
        if r[1] not in sets:
            try:
                d = json.load(open(os.path.join(sd, "set", f"{r[1]}.json")))
                sets[r[1]] = (d.get("n") or "", (d.get("pub") or "")[:4])
            except Exception:
                sets[r[1]] = ("", "")
        out.append((profit, r, sets[r[1]]))
    out.sort(key=lambda x: -x[0])
    return out


def write_edge(site, cache):
    edge = {pid: [cache["pop"][str(s)][0], *cache["pop"][str(s)][1:5], s]
            for pid, s in cache.get("spec", {}).items() if isinstance(s, int) and str(s) in cache.get("pop", {})}
    out = os.path.join(site, "data", "edge")
    os.makedirs(out, exist_ok=True)
    sealed.write("edge", os.path.join(out, "psapop.enc"),
                 gzip.compress(json.dumps({"u": cache.get("last_run") or TODAY, "c": edge}, separators=(",", ":")).encode("utf-8"), mtime=0))
    return edge


def main(argv):
    publish_only = "--publish-only" in argv            # nightly rebuild: re-publish the Edge copy from the cache, no API calls
    site, store = [a for a in argv if not a.startswith("--")][:2]
    cpath = os.path.join(store, "cache.enc")
    if publish_only:
        if os.path.exists(cpath):
            print(f"psapop: {len(write_edge(site, json.loads(sealed.read('ppt', cpath))))} cards with PSA population (cache only)")
        else:
            print("psapop: no cache yet")
        return
    if not os.environ.get("PSA_TOKEN", "").strip():
        print("::warning title=PSA pop::PSA_TOKEN isn't set: nothing to do")
        return
    os.makedirs(store, exist_ok=True)
    cache = json.loads(sealed.read("ppt", cpath)) if os.path.exists(cpath) else {}
    cache.setdefault("spec", {})     # tcgplayer id -> spec id, or ["miss", date, reason]
    cache.setdefault("pop", {})      # spec id -> [date, total, 10, 9, 8]
    cache["calls"] = {k: v for k, v in cache.get("calls", {}).items() if k >= TODAY[:8] + "01" or k == TODAY}
    new = refreshed = misses = 0
    why = ""
    try:
        # 1) refresh the oldest populations (a share of today's calls)
        stale = sorted((v[0], s) for s, v in cache["pop"].items() if (date.fromisoformat(TODAY) - date.fromisoformat(v[0])).days >= REFRESH_DAYS)
        for _, s in stale[: int(PSA_DAILY * REFRESH_SHARE)]:
            p = pop_of(s, cache)
            if p:
                cache["pop"][s] = p
                refreshed += 1
        # 2) new cards, best grading profit first
        for profit, row, (setname, year) in candidates(site):
            if cache["calls"].get(TODAY, 0) >= PSA_DAILY - 1:
                break
            pid = str(row[0])
            s = cache["spec"].get(pid)
            if isinstance(s, int):
                if str(s) not in cache["pop"]:
                    p = pop_of(s, cache)
                    if p:
                        cache["pop"][str(s)] = p
                continue
            if isinstance(s, list) and (date.fromisoformat(TODAY) - date.fromisoformat(s[1])).days < RETRY_DAYS:
                continue
            reason = "no PSA slab listed on eBay"
            for cert in certs_for(row, setname):
                d = psa_get(f"/cert/GetByCertNumber/{cert}", cache) or {}
                c = d.get("PSACert") or {}
                ok, reason = matches(c, row, year)
                if ok and c.get("SpecID"):
                    spec = int(c["SpecID"])
                    cache["spec"][pid] = spec
                    if str(spec) not in cache["pop"]:
                        p = pop_of(spec, cache)
                        if p:
                            cache["pop"][str(spec)] = p
                    new += 1
                    break
                reason = f"cert {cert} didn't match ({reason})"
            else:
                cache["spec"][pid] = ["miss", TODAY, reason]
                misses += 1
    except Stop as e:
        why = str(e)
    cache["last_run"] = TODAY
    sealed.write("ppt", cpath, json.dumps(cache, separators=(",", ":")).encode("utf-8"))
    edge = write_edge(site, cache)
    msg = (f"psapop: {new} new cards matched, {misses} not matched, {refreshed} refreshed, "
           f"{cache['calls'].get(TODAY, 0)} PSA calls today; {len(edge)} cards with PSA population")
    print(msg + (f" (stopped: {why})" if why else ""))
    if why.startswith("PSA said"):
        print(f"::error title=PSA pop::{why}")


if __name__ == "__main__":
    main(sys.argv[1:])
