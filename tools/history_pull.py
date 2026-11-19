"""One-time pull of tcgcsv's daily price archives (available from 2024-02-08) into this repo's releases.

    python tools/history_pull.py

tcgcsv asks that an archive is downloaded once and never again. So every day is stored the moment it
arrives, exactly as downloaded (release "tcgcsv-<year>", file "prices-<day>.ppmd.7z"), and days that
are already stored are skipped. Safe to run again: it only fetches what is missing, newest day first.
It does not touch the data branch or the site.

Status: the first pull finished on Nov 11, 2026 (all 977 days, Feb 8, 2024 to Oct 11, 2026). The "Price archive"
workflow now runs it every night for the last 14 days (PULL_START/PULL_END), so each new day is stored once and a
missed night heals itself. Every download is checked before it is stored (7z header, full length, tcgcsv's ETag,
the archive's own checksums), and every stored file is checked against what was sent; a file already in the
release is never replaced. tools/history_build.py turns the stored archives into the site's history.

Settings (environment):
  PULL_START     first day wanted (default 2024-02-08, tcgcsv's first archive)
  PULL_END       last day wanted (default: the day before config.SEALED_BEFORE, where our own tracking starts)
  PULL_MAX       most days to download in this run (default: all that are missing)
  PULL_PAUSE     seconds to wait after each day (default 7: gentle on tcgcsv, and under GitHub's hourly limits)
  PULL_RETRY_WAIT seconds to wait after a refused or failed download (default 30)
  GITHUB_API_URL, GITHUB_UPLOADS_URL  GitHub's addresses (defaults: api.github.com, uploads.github.com)
  SEED_ARTIFACT  id of a workflow artifact that already holds one downloaded day (so it isn't fetched twice)
  SEED_DAY       the day that artifact holds (default 2025-11-11); skipped if the artifact can't be read
  SEED_RECENT    name of the artifact earlier runs keep unstored days in (the nightly uses "tcgcsv-unsaved"):
                 those days are stored from it first, so they aren't downloaded from tcgcsv twice
  GH_TOKEN, GITHUB_REPOSITORY  set by GitHub Actions
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import config  # noqa: E402

API = os.environ.get("GITHUB_API_URL") or "https://api.github.com"
UPLOADS = os.environ.get("GITHUB_UPLOADS_URL") or "https://uploads.github.com"
REPO = os.environ.get("GITHUB_REPOSITORY", "VapeZz/dys-market")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT = os.path.join(ROOT, "pull-out")          # a day that could not be stored waits here; the workflow keeps it as an artifact
MAGIC = b"7z\xbc\xaf\x27\x1c"                 # every 7z file starts with these bytes
STOP_AFTER = 3                                # consecutive refusals before we stop asking


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def http(method, url, headers=None, data=None, follow=True, timeout=300):
    """(status, headers, body). Never raises for an HTTP status; status 0 is a network error."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, {k.lower(): v for k, v in (err.headers or {}).items()}, err.read()
    except Exception as err:  # noqa: BLE001
        return 0, {}, f"{type(err).__name__}: {err}".encode()


def gh_headers(extra=None):
    h = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "dys-market-history-pull"}
    h.update(extra or {})
    return h


def say(line):
    print(line, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n\n")


def tag_for(day):
    return f"tcgcsv-{day[:4]}"


def name_for(day):
    return f"prices-{day}.ppmd.7z"


def get_release(tag):
    """The release for one year, created the first time it is needed. Returns its id."""
    status, _, body = http("GET", f"{API}/repos/{REPO}/releases/tags/{tag}", gh_headers())
    if status == 200:
        return json.loads(body)["id"]
    if status != 404:
        raise RuntimeError(f"could not read release {tag}: HTTP {status} {body[:200]!r}")
    year = tag.rsplit("-", 1)[-1]
    payload = {"tag_name": tag, "name": f"tcgcsv daily price archives {year}", "make_latest": "false",
               "body": ("Daily TCGplayer price archives from tcgcsv.com for " + year + ", stored exactly as downloaded "
                        "(one file per day: prices-<date>.ppmd.7z, open with 7-Zip). Each day is downloaded once and kept "
                        "here so it never has to be fetched again. Used to rebuild the site's price history.")}
    status, _, body = http("POST", f"{API}/repos/{REPO}/releases", gh_headers({"Content-Type": "application/json"}),
                           json.dumps(payload).encode())
    if status != 201:
        raise RuntimeError(f"could not create release {tag}: HTTP {status} {body[:200]!r}")
    return json.loads(body)["id"]


def etag_matches(body, etag):
    """True/False when tcgcsv's ETag can be checked, None when it can't (no ETag, or a multi-part upload).
    tcgcsv is served from S3: a plain ETag is the file's MD5; "<md5>-1" is the MD5 of that MD5 (one-part upload)."""
    tag = (etag or "").strip().strip('"')
    if tag.startswith("W/"):
        tag = tag[2:].strip('"')
    m = re.fullmatch(r"([0-9a-f]{32})(?:-(\d+))?", tag)
    if not m:
        return None
    md5 = hashlib.md5(body)
    if m.group(2) is None:
        return md5.hexdigest() == m.group(1)
    if m.group(2) == "1":
        return hashlib.md5(md5.digest()).hexdigest() == m.group(1)
    return None


def archive_test(body):
    """True when 7-Zip (or py7zr) reads every file in the archive and its checksums match; None when no tester exists."""
    exe = shutil.which("7z") or shutil.which("7za")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "day.7z")
        with open(path, "wb") as f:
            f.write(body)
        if exe:
            return subprocess.run([exe, "t", "-y", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        try:
            import py7zr
        except ImportError:
            return None
        try:
            with py7zr.SevenZipFile(path) as z:
                return z.testzip() is None
        except Exception:  # noqa: BLE001
            return False


def check_download(body, headers):
    """None when the downloaded day is complete and intact, else what is wrong."""
    if not body.startswith(MAGIC):
        return "not a 7z archive"
    want = headers.get("content-length")
    if want and want.isdigit() and int(want) != len(body):
        return f"incomplete download ({len(body)} of {want} bytes)"
    if etag_matches(body, headers.get("etag")) is False:
        return "content doesn't match tcgcsv's ETag (corrupted)"
    if archive_test(body) is False:
        return "the archive fails its own integrity test"
    return None


def stored_asset(release_id, name):
    """The release file with this name (any state), or None."""
    page = 1
    while True:
        status, _, body = http("GET", f"{API}/repos/{REPO}/releases/{release_id}/assets?per_page=100&page={page}", gh_headers())
        if status != 200:
            return None
        rows = json.loads(body)
        for r in rows:
            if r.get("name") == name:
                return r
        if len(rows) < 100:
            return None
        page += 1


def same_file(asset, data):
    """True when a stored release file holds exactly these bytes (GitHub's sha256 digest, else the size), False when not."""
    if not asset or asset.get("state", "uploaded") != "uploaded":
        return False
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:"):
        return digest == "sha256:" + hashlib.sha256(data).hexdigest()
    return asset.get("size") == len(data)


def stored_names(release_id):
    names, page = set(), 1
    while True:
        status, _, body = http("GET", f"{API}/repos/{REPO}/releases/{release_id}/assets?per_page=100&page={page}", gh_headers())
        if status != 200:
            raise RuntimeError(f"could not list stored files: HTTP {status} {body[:200]!r}")
        rows = json.loads(body)
        names.update(r["name"] for r in rows if r.get("state", "uploaded") == "uploaded")
        if len(rows) < 100:
            return names
        page += 1


def store(release_id, name, data):
    """Save one file in a release. True when it is stored (or already was)."""
    waits = [w * float(os.environ.get("PULL_STORE_WAIT_SCALE") or 1) for w in (30, 60, 180, 600)]
    for attempt in range(len(waits) + 1):
        status, headers, body = http("POST", f"{UPLOADS}/repos/{REPO}/releases/{release_id}/assets?name={name}",
                                     gh_headers({"Content-Type": "application/octet-stream"}), data)
        if status == 201:
            try:
                asset = json.loads(body)
            except ValueError:
                asset = None
            if asset and not asset.get("digest"):
                asset = stored_asset(release_id, name) or asset
            if same_file(asset, data):
                return True
            say(f"store {name}: GitHub's copy doesn't match what was sent (left as is, not replaced)")
            return False
        if status == 422 and b"already_exists" in body:
            # a file with this name is already there: fine if it's the same file; never replaced if it isn't
            if same_file(stored_asset(release_id, name), data):
                return True
            say(f"store {name}: a different or unfinished file with this name is already stored; left as is, not replaced")
            return False
        if attempt == len(waits):
            break
        try:
            wait = int(headers.get("retry-after") or 0)
        except ValueError:
            wait = 0
        wait = max(wait, waits[attempt])
        say(f"store {name}: HTTP {status} {body[:160]!r}; trying again in {wait}s")
        time.sleep(wait)
    return False


def seed_from_artifact(artifact_id, releases, have):
    """A day downloaded by an earlier test run is kept as a workflow artifact: store it instead of fetching it again."""
    status, headers, body = http("GET", f"{API}/repos/{REPO}/actions/artifacts/{artifact_id}/zip", gh_headers(), follow=False)
    if status in (301, 302, 303, 307) and headers.get("location"):
        status, headers, body = http("GET", headers["location"])      # the download link carries its own signature
    if status != 200:
        say(f"seed: artifact {artifact_id} not readable (HTTP {status}); its day will be left out of this run")
        return set()
    done = set()
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        for info in z.infolist():
            base = os.path.basename(info.filename)
            if not (base.startswith("prices-") and base.endswith(".ppmd.7z")):
                continue
            day = base[len("prices-"):-len(".ppmd.7z")]
            data = z.read(info)
            if not data.startswith(MAGIC):
                continue
            tag = tag_for(day)
            if tag not in releases:                         # a day outside this run's window
                releases[tag] = get_release(tag)
                have[tag] = stored_names(releases[tag])
            if base in have.get(tag, set()):
                done.add(day)
                continue
            if archive_test(data) is False:
                say(f"seed: {base} in artifact {artifact_id} fails its integrity test; not used")
                continue
            if store(releases[tag], base, data):
                have.setdefault(tag_for(day), set()).add(base)
                done.add(day)
                say(f"seed: stored {base} from an earlier run ({len(data) / 1e6:.2f} MB), no new download")
    return done


def seed_from_recent(name, releases, have):
    """Files kept by earlier runs (artifacts called `name`, newest first, not expired): store them instead of
    downloading the same days from tcgcsv again. Needs the workflow's `actions: read` permission."""
    status, _, body = http("GET", f"{API}/repos/{REPO}/actions/artifacts?name={name}&per_page=100", gh_headers())
    if status != 200:
        say(f"seed: couldn't list earlier runs' files (HTTP {status}); days will be downloaded instead")
        return set()
    rows = [a for a in json.loads(body).get("artifacts", []) if not a.get("expired")]
    rows.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    done = set()
    for a in rows:
        done |= seed_from_artifact(a["id"], releases, have)
    if rows:
        say(f"seed: {len(rows)} kept file set(s) from earlier runs checked, {len(done)} day(s) stored or already there")
    return done


def main():
    start = date.fromisoformat(os.environ.get("PULL_START") or "2024-02-08")
    default_end = date.fromisoformat(config.SEALED_BEFORE) - timedelta(days=1)
    end = date.fromisoformat(os.environ.get("PULL_END") or default_end.isoformat())
    limit = int(os.environ.get("PULL_MAX") or 0)
    pause = float(os.environ.get("PULL_PAUSE") or 7)
    seed = (os.environ.get("SEED_ARTIFACT") or "").strip()
    if not TOKEN:
        raise SystemExit("GH_TOKEN is not set")

    days = []
    d = end
    while d >= start:                          # newest first: the recent days matter most to the site
        days.append(d.isoformat())
        d -= timedelta(days=1)
    tags = sorted({tag_for(x) for x in days})
    releases = {t: get_release(t) for t in tags}
    have = {t: stored_names(releases[t]) for t in tags}
    seeded_only = set()
    recent = (os.environ.get("SEED_RECENT") or "").strip()
    if recent:
        seed_from_recent(recent, releases, have)
    if seed:
        got = seed_from_artifact(seed, releases, have)
        if not got:
            seeded_only = {os.environ.get("SEED_DAY") or "2025-11-11"}   # the day that artifact holds: never fetch it twice
    missing = [x for x in days if name_for(x) not in have[tag_for(x)] and x not in seeded_only]
    say(f"History pull {start} to {end}: {len(days)} days wanted, {len(days) - len(missing)} already stored, {len(missing)} to fetch"
        + (f" (this run: at most {limit})" if limit else ""))

    os.makedirs(OUT, exist_ok=True)
    fetched, absent, refusals, mb, stopped = 0, [], 0, 0.0, ""
    for day in missing:
        if limit and fetched >= limit:
            break
        url = f"{config.BASE_URL}/archive/tcgplayer/{name_for(day)}"
        status, headers, body = http("GET", url, {"User-Agent": config.USER_AGENT})
        if status == 404:
            absent.append(day)                 # tcgcsv has no file for this day
            if len(absent) >= 5 and fetched == 0:
                stopped = "the first 5 days were all missing at tcgcsv, so the address may have changed"
                break
            time.sleep(1)
            continue
        problem = f"HTTP {status}" if status != 200 else check_download(body, headers)
        if problem:
            refusals += 1
            say(f"{day}: {problem}, {len(body)} bytes; not stored ({body[:80]!r})")
            if refusals >= STOP_AFTER:
                stopped = f"tcgcsv refused {STOP_AFTER} requests in a row (last: HTTP {status})"
                break
            time.sleep(float(os.environ.get("PULL_RETRY_WAIT") or 30))
            continue
        refusals = 0
        if not store(releases[tag_for(day)], name_for(day), body):
            with open(os.path.join(OUT, name_for(day)), "wb") as f:   # keep it: the workflow saves this folder as an artifact
                f.write(body)
            stopped = f"GitHub would not store {name_for(day)}; the file is kept with this run"
            break
        fetched += 1
        mb += len(body) / 1e6
        if fetched % 25 == 0 or fetched <= 3:
            print(f"{fetched} stored, latest {day} ({len(body) / 1e6:.2f} MB)", flush=True)
        time.sleep(pause)

    left = len(missing) - fetched - len(absent)
    say(f"stored {fetched} new days ({mb:.0f} MB); not at tcgcsv: {len(absent)} {absent[:10]}; still to fetch: {max(left, 0)}")
    if stopped:
        say(f"RESULT: STOPPED, {stopped}")
        print(f"::warning title=History pull::stopped: {stopped}")
    elif left > 0:
        say(f"RESULT: PARTIAL, {left} days left for the next run")
        print(f"::notice title=History pull::{fetched} stored, {left} left")
    else:
        say("RESULT: COMPLETE, every available day in the range is stored")
        print(f"::notice title=History pull::complete, {fetched} stored this run")


if __name__ == "__main__":
    main()
