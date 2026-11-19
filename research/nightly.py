"""Nightly update of the PUBLIC research database, stored as release assets. TEST BRANCH CODE.

Safety rules built in:
- Writes only to a DRAFT release whose name starts with WRITE_PREFIX. Source releases (tcgcsv-*) are read-only here.
- Never deletes or overwrites anything: every snapshot and pointer gets a new unique name.
- A snapshot counts only once a pointer naming it is uploaded and verified; readers take the newest pointer whose snapshot
  verifies (sha256 of gz and db, quick_check, row counts, table allowlist) and fall back to older ones otherwise.
- Days are applied in order. A day not archived yet stops the catch-up (nothing later is applied or published).
- Logs print counts and states only; the token is never printed.
"""
import hashlib, json, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rdbpub
from extract_day import extract

REPO = os.environ.get('GITHUB_REPOSITORY', 'VapeZz/dys-market')
API = os.environ.get('GITHUB_API_URL', 'https://api.github.com')
UPLOADS = 'https://uploads.github.com'
WRITE_PREFIX = 'research-db-test'
SOURCE_TAGS = ('tcgcsv-2024', 'tcgcsv-2025', 'tcgcsv-2026')

def _tok(): return os.environ['GH_TOKEN']

def api(method, path, data=None, raw=False, accept='application/vnd.github+json'):
    url = path if path.startswith('http') else f'{API}{path}'
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={'Authorization': f'Bearer {_tok()}', 'Accept': accept,
                                                                         'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(req, timeout=300) as r:
        b = r.read()
        return b if raw else (json.loads(b) if b else None)

def list_assets(release_id):
    out = []; page = 1
    while True:
        a = api('GET', f'/repos/{REPO}/releases/{release_id}/assets?per_page=100&page={page}'); out += a; page += 1
        if len(a) < 100: return out

def source_days():
    days = {}
    for tag in SOURCE_TAGS:
        rel = api('GET', f'/repos/{REPO}/releases/tags/{tag}')
        for a in list_assets(rel['id']):
            if a['name'].startswith('prices-') and a['state'] == 'uploaded':
                days[a['name'][7:17]] = {'tag': tag, 'name': a['name'], 'digest': (a.get('digest') or '').split(':')[-1],
                                         'url': a['browser_download_url'], 'size': a['size']}
    return days

def _drafts_named(name):
    out = []; page = 1
    while True:
        rs = api('GET', f'/repos/{REPO}/releases?per_page=100&page={page}'); page += 1
        out += [r for r in rs if r['name'] == name]
        if len(rs) < 100: return sorted(out, key=lambda r: r['id'])

def release_by_id(release_id):
    """Preferred: address the storage release by its id (saved once), never by name."""
    r = api('GET', f'/repos/{REPO}/releases/{int(release_id)}')
    if not r['name'].startswith(WRITE_PREFIX) or not r['draft']: raise PermissionError(f'refused: release {release_id} is not a test draft')
    return r

def draft_release(name, create=False, wait_s=90):
    """Find the draft named `name`; if several exist (an earlier race), always use the lowest id and report the rest.
    Creates one only when create=True AND none exists, then waits until the release list shows it, so a later
    lookup in another process can't miss it and create a second one."""
    if not name.startswith(WRITE_PREFIX): raise PermissionError(f'refused: {name} is not a test release')
    found = _drafts_named(name)
    if any(not r['draft'] for r in found): raise PermissionError(f'refused: {name} exists and is not a draft')
    if found:
        if len(found) > 1: print(f'note: {len(found)} drafts named {name}; using the lowest id', flush=True)
        return found[0]
    if not create: raise LookupError(f'no draft named {name} (create=False)')
    r = api('POST', f'/repos/{REPO}/releases', {'tag_name': name, 'name': name, 'draft': True, 'prerelease': True,
                                                'body': 'Disposable test of the research database storage. Not production.'})
    t = time.time()
    while time.time() - t < wait_s:
        if any(x['id'] == r['id'] for x in _drafts_named(name)): return r
        time.sleep(3)
    raise TimeoutError(f'created draft {r["id"]} but it did not appear in the list within {wait_s}s')

def download_public(url, path, digest, fault=None):
    """Download a source archive by its public URL (no API quota) and verify GitHub's sha256 digest."""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=300) as r, open(path, 'wb') as f:
                while True:
                    b = r.read(1 << 20)
                    if not b: break
                    f.write(b)
            break
        except Exception:
            if attempt == 3: raise
            time.sleep(5 * (attempt + 1))
    if fault == 'corrupt_download':
        with open(path, 'r+b') as f: f.seek(1000); x = f.read(1); f.seek(1000); f.write(bytes([x[0] ^ 0xFF]))
    got = rdbpub.sha256_file(path)
    if not digest or got != digest: raise ValueError(f'{os.path.basename(path)}: sha256 does not match the release digest — refused')

def download_asset(asset, path):
    data = api('GET', asset['url'], raw=True, accept='application/octet-stream')
    open(path, 'wb').write(data)

class _Body:
    def __init__(self, path, fail_after=None):
        self.f = open(path, 'rb'); self.sent = 0; self.fail_after = fail_after
    def read(self, n=-1):
        b = self.f.read(1 << 20 if n is None or n < 0 else n)
        self.sent += len(b)
        if self.fail_after is not None and self.sent > self.fail_after:
            raise ConnectionAbortedError('simulated interrupted upload')
        return b

def upload(release, path, name, fail_after=None):
    """Upload under a NEW name and verify GitHub's digest. Never replaces an existing asset."""
    if not release['name'].startswith(WRITE_PREFIX) or not release['draft']: raise PermissionError('refused: not a test draft release')
    if any(a['name'] == name for a in list_assets(release['id'])): raise ValueError(f'{name} already exists — names are never reused')
    size = os.path.getsize(path)
    req = urllib.request.Request(f'{UPLOADS}/repos/{REPO}/releases/{release["id"]}/assets?name={name}', data=_Body(path, fail_after),
                                 method='POST', headers={'Authorization': f'Bearer {_tok()}', 'Content-Type': 'application/octet-stream',
                                                         'Content-Length': str(size), 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=1800) as r: a = json.loads(r.read())
    want = rdbpub.sha256_file(path)
    for _ in range(10):
        got = next((x for x in list_assets(release['id']) if x['name'] == name), None)
        if got and got['state'] == 'uploaded' and (got.get('digest') or '').split(':')[-1] == want: return got
        time.sleep(3)
    raise ValueError(f'{name}: uploaded asset does not verify')

def pointers(release):
    assets = list_assets(release['id'])
    return sorted([a for a in assets if a['name'].startswith('pointer-') and a['state'] == 'uploaded'], key=lambda a: a['name'], reverse=True), assets

def restore_latest(release, db, work, log):
    ptrs, assets = pointers(release); by_name = {a['name']: a for a in assets}
    for p in ptrs:
        try:
            download_asset(p, f'{work}/ptr.json'); ptr = json.load(open(f'{work}/ptr.json'))
            snap = by_name.get(ptr['snapshot'])
            if not snap or snap['state'] != 'uploaded': raise ValueError('snapshot asset missing or incomplete')
            download_asset(snap, f'{work}/snap.db.gz')
            rdbpub.restore(f'{work}/snap.db.gz', ptr['manifest'], db)
            log(f'restored {ptr["data_day"]} from {p["name"]}')
            return ptr
        except Exception as e:
            log(f'skipped pointer {p["name"]}: {type(e).__name__}: {e}')
    return None

def publish(release, db, work, attempt, log, fail_after=None):
    day = rdbpub.connect(db).execute("SELECT v FROM meta WHERE k='data_day'").fetchone()[0]
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    gz = f'{work}/research-public-{day}-{stamp}-a{attempt}.db.gz'
    man = rdbpub.backup(db, gz)
    snap = upload(release, gz, os.path.basename(gz), fail_after)
    ptr = {'data_day': day, 'snapshot': snap['name'], 'manifest': man, 'published_at': stamp}
    pp = f'{work}/pointer-{stamp}-{day}.json'; json.dump(ptr, open(pp, 'w'), indent=1, sort_keys=True)
    upload(release, pp, os.path.basename(pp))
    log(f'published {day}: {man["gz_bytes"]/1e6:.0f} MB gz')
    return ptr

def nightly(release, db, work, target, src, log, attempt=1, fault=None, fail_after=None):
    """Restore the newest verified snapshot, catch up to target in order, publish once. Returns a status dict."""
    ptr = restore_latest(release, db, work, log)
    if ptr is None: return {'status': 'no snapshot to restore'}
    day = ptr['data_day']; applied = []
    if day >= target: log(f'already at {day}: nothing to do'); return {'status': 'no-op', 'data_day': day}
    d = rdbpub.dnum(day) + 1
    while d <= rdbpub.dnum(target):
        ds = rdbpub.dstr(d); s = src.get(ds)
        if s is None: log(f'{ds} not archived yet: stop'); break
        arc = f'{work}/{s["name"]}'; ext = f'{work}/{ds}.csv.gz'
        download_public(s['url'], arc, s['digest'], fault)
        extract(arc, ext); os.remove(arc)
        if fault == 'truncate_extract':
            b = open(ext, 'rb').read(); open(ext, 'wb').write(b[:len(b) // 2])
        n = rdbpub.add_day(db, ext, ds, (f'github-release:{s["tag"]}', s['name'], s['digest']))
        applied.append(ds); log(f'{ds}: {n} changes'); d += 1
    if not applied: return {'status': 'nothing applied', 'data_day': day}
    newptr = publish(release, db, work, attempt, log, fail_after)
    return {'status': 'published', 'applied': applied, 'data_day': newptr['data_day']}
