"""Test-branch scenarios for the public research database storage. Runs in GitHub Actions on the disposable branch only.
Writes only to the draft release named in RDB_TEST_RELEASE (must start with research-db-test). Reads tcgcsv-* releases.
Usage: scenarios.py <workdir> <results.json>"""
import concurrent.futures as cf, json, os, shutil, sys, time, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import nightly as N, rdbpub, leakscan
from extract_day import extract

W, OUT = sys.argv[1], sys.argv[2]; os.makedirs(W, exist_ok=True)
REL = os.environ['RDB_TEST_RELEASE']; CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'catalog', 'catalog-2026-11-18.jsonl.gz')
BASE_UNTIL, TARGET = '2026-11-15', '2026-11-18'
R = {'results': {}, 'timings_s': {}, 'sizes_mb': {}, 'hashes': {}}
def log(m): print(m, flush=True)
def ok(name, cond, detail=''):
    R['results'][name] = {'pass': bool(cond), 'detail': detail}; log(('PASS ' if cond else 'FAIL ') + f'{name}: {detail}')
def timed(name):
    class T:
        def __enter__(s): s.t = time.time()
        def __exit__(s, *a): R['timings_s'][name] = round(time.time() - s.t, 1)
    return T()
def fails(f):
    try: f(); return False
    except Exception as e: return f'{type(e).__name__}'
def save(): json.dump(R, open(OUT, 'w'), indent=1)

try:
    release = N.draft_release(REL)
    ok('writes_only_to_test_draft', release['draft'] and release['name'] == REL, f'draft release {REL}')
    ok('refuses_other_release', fails(lambda: N.draft_release('tcgcsv-2026')), 'writing to tcgcsv-2026 is refused by the code')
    src = N.source_days()
    days = sorted(d for d in src if d <= BASE_UNTIL)
    R['source_days'] = len(src)

    # ---- S0 base build from the permitted source archives
    os.makedirs(f'{W}/days', exist_ok=True); os.makedirs(f'{W}/arc', exist_ok=True)
    def one(day):
        s = src[day]; arc = f'{W}/arc/{s["name"]}'
        N.download_public(s['url'], arc, s['digest']); extract(arc, f'{W}/days/{day}.csv.gz'); os.remove(arc)
        return s['size']
    with timed('download_and_extract_base'):
        with cf.ThreadPoolExecutor(6) as ex: total = sum(ex.map(one, days))
    R['sizes_mb']['source_archives_read'] = round(total / 1e6)
    prov = {d: (f'github-release:{src[d]["tag"]}', src[d]['name'], src[d]['digest']) for d in days}
    allday = [rdbpub.dstr(i) for i in range(rdbpub.dnum(days[0]), rdbpub.dnum(BASE_UNTIL) + 1)]
    missing = {d: 'not in GitHub releases (Drive-only copy; backfill pending)' for d in allday if d not in src}
    with timed('build_base'):
        rdbpub.build(f'{W}/base.db', f'{W}/days', CATALOG, prov, missing)
    R['sizes_mb']['public_db'] = round(os.path.getsize(f'{W}/base.db') / 1e6)
    R['hashes']['base_through_2026-11-15'] = rdbpub.logical_hash(f'{W}/base.db')
    c = rdbpub.connect(f'{W}/base.db')
    R['base'] = {'days': c.execute('SELECT COUNT(*) FROM archive_days').fetchone()[0], 'missing_days': c.execute('SELECT COUNT(*) FROM missing_days').fetchone()[0],
                 'cards': c.execute('SELECT COUNT(*) FROM cards').fetchone()[0]}
    c.close()
    ok('base_built_from_sources', R['base']['days'] == len(days) and R['base']['missing_days'] == len(missing),
       f'{len(days)} archived days ingested, {len(missing)} days recorded as missing (not in GitHub), {R["base"]["cards"]} identities')
    with timed('publish_base'):
        p0 = N.publish(release, f'{W}/base.db', W, 1, log)
    R['sizes_mb']['public_snapshot_gz'] = round(p0['manifest']['gz_bytes'] / 1e6)
    save()

    # ---- S1 interrupted upload: nothing becomes current
    n_ptr = len(N.pointers(release)[0])
    db = f'{W}/live.db'
    with timed('nightly_interrupted'):
        e = fails(lambda: N.nightly(release, db, W, TARGET, src, log, attempt=1, fail_after=40_000_000))
    ptrs, assets = N.pointers(release)
    partial = [a['state'] for a in assets if a['name'].startswith(f'research-public-{TARGET}')]
    ok('interrupted_upload_not_current', e and len(ptrs) == n_ptr, f'upload cut at 40 MB ({e}); no new pointer; partial asset states: {partial or "none left"}')

    # ---- S2 rerun after the interruption: restores the base snapshot, catches up the 3 missed days, publishes
    with timed('nightly_catch_up_3_days'):
        st = N.nightly(release, db, W, TARGET, src, log, attempt=2)
    ok('missed_days_caught_up', st.get('status') == 'published' and st.get('applied') == ['2026-11-16', '2026-11-17', '2026-11-18'], json.dumps(st))
    R['hashes']['nightly_through_2026-11-18'] = rdbpub.logical_hash(db)

    # ---- S3 rerun: no-op
    n_assets = len(N.list_assets(release['id']))
    with timed('nightly_rerun_noop'):
        st = N.nightly(release, f'{W}/rerun.db', W, TARGET, src, log, attempt=3)
    ok('rerun_is_noop', st.get('status') == 'no-op' and len(N.list_assets(release['id'])) == n_assets, json.dumps(st))
    os.remove(f'{W}/rerun.db')

    # ---- S4/S5 corrupted inputs leave the database unchanged
    shutil.copy(f'{W}/base.db', f'{W}/c.db'); before = rdbpub.sha256_file(f'{W}/c.db')
    s16 = src['2026-11-16']
    e1 = fails(lambda: N.download_public(s16['url'], f'{W}/bad.7z', s16['digest'], fault='corrupt_download'))
    ok('corrupt_archive_refused', e1 and rdbpub.sha256_file(f'{W}/c.db') == before, f'one flipped byte in the downloaded archive -> {e1}; database unchanged')
    N.download_public(s16['url'], f'{W}/good.7z', s16['digest']); extract(f'{W}/good.7z', f'{W}/16.csv.gz')
    b = open(f'{W}/16.csv.gz', 'rb').read(); open(f'{W}/16bad.csv.gz', 'wb').write(b[:len(b) // 2])
    e2 = fails(lambda: rdbpub.add_day(f'{W}/c.db', f'{W}/16bad.csv.gz', '2026-11-16', ('t', 't', 't')))
    ok('corrupt_extract_rolled_back', e2 and rdbpub.sha256_file(f'{W}/c.db') == before, f'half an extract -> {e2}; database byte-identical')
    e3 = fails(lambda: rdbpub.add_day(f'{W}/c.db', f'{W}/16.csv.gz', '2026-11-10', ('t', 't', 't')))
    e4 = fails(lambda: rdbpub.add_day(f'{W}/c.db', f'{W}/16.csv.gz', '2026-11-18', ('t', 't', 't')))
    ok('out_of_order_and_skips_refused', e3 and e4 and rdbpub.sha256_file(f'{W}/c.db') == before, f'older day -> {e3}; skipping 2 days -> {e4}')

    # ---- S6 corrupted snapshot in storage: readers fall back to the last good one
    bad = f'{W}/research-public-{TARGET}-corrupt-test.db.gz'
    good = sorted(f for f in os.listdir(W) if f.startswith(f'research-public-{TARGET}') and f.endswith('.db.gz'))[-1]
    data = bytearray(open(f'{W}/{good}', 'rb').read()); data[5_000_000] ^= 0xFF; open(bad, 'wb').write(data)
    snap = N.upload(release, bad, os.path.basename(bad))
    man = json.load(open(f'{W}/{good}.manifest.json'))
    ptr = {'data_day': TARGET, 'snapshot': snap['name'], 'manifest': man, 'published_at': 'corrupt-test'}
    pp = f'{W}/pointer-{time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())}-zz-corrupt-test.json'; json.dump(ptr, open(pp, 'w'))
    N.upload(release, pp, os.path.basename(pp))
    msgs = []
    got = N.restore_latest(release, f'{W}/fallback.db', W, msgs.append)
    ok('corrupt_snapshot_falls_back', got and got['data_day'] == TARGET and any('corrupt-test' in m and 'skipped' in m for m in msgs),
       '; '.join(msgs))
    os.remove(f'{W}/fallback.db'); os.remove(f'{W}/c.db')

    # ---- S7 a day not archived yet stops the catch-up and publishes nothing
    n_ptr = len(N.pointers(release)[0])
    st = N.nightly(release, f'{W}/future.db', W, '2026-11-25', {k: v for k, v in src.items() if k <= TARGET}, log, attempt=4)
    if os.path.exists(f'{W}/future.db'): os.remove(f'{W}/future.db')
    ok('unarchived_day_stops', st.get('status') == 'nothing applied' and len(N.pointers(release)[0]) == n_ptr, json.dumps(st))

    # ---- S8 independent restore + equivalence with a from-scratch rebuild
    shutil.rmtree(f'{W}/clean', ignore_errors=True); os.makedirs(f'{W}/clean')
    with timed('independent_restore'):
        got = N.restore_latest(release, f'{W}/clean/restored.db', f'{W}/clean', log)
    h_rest = rdbpub.logical_hash(f'{W}/clean/restored.db')
    ok('independent_restore', h_rest == R['hashes']['nightly_through_2026-11-18'], f'restored {got["data_day"]} in a clean folder; content hash matches')
    for d in ('2026-11-16', '2026-11-17', '2026-11-18'):
        s = src[d]; arc = f'{W}/arc/{s["name"]}'; N.download_public(s['url'], arc, s['digest']); extract(arc, f'{W}/days/{d}.csv.gz'); os.remove(arc)
        prov[d] = (f'github-release:{s["tag"]}', s['name'], s['digest'])
    allday = [rdbpub.dstr(i) for i in range(rdbpub.dnum(days[0]), rdbpub.dnum(TARGET) + 1)]
    with timed('full_rebuild_through_target'):
        rdbpub.build(f'{W}/rebuild.db', f'{W}/days', CATALOG, prov, {d: 'x' for d in allday if d not in src})
    R['hashes']['rebuild_through_2026-11-18'] = rdbpub.logical_hash(f'{W}/rebuild.db')
    ok('nightly_equals_full_rebuild', R['hashes']['rebuild_through_2026-11-18'] == R['hashes']['nightly_through_2026-11-18'],
       'base + 3 nightly updates gives the same content as a from-scratch rebuild')

    # ---- S9 leak scan of every file this run uploaded (downloaded back from the release)
    scan_dir = f'{W}/scan'; os.makedirs(scan_dir, exist_ok=True); files = []
    for a in N.list_assets(release['id']):
        if a['state'] != 'uploaded' or 'corrupt-test' in a['name']: continue
        p = f'{scan_dir}/{a["name"]}'; N.download_asset(a, p); files.append(p)
    found = leakscan.scan(files)
    ok('no_leaks_in_release_files', not found, f'{len(files)} uploaded files scanned (snapshots, pointers): {len(found)} findings')
except Exception:
    R['error'] = traceback.format_exc().splitlines()[-1]; log('ERROR ' + R['error'])
finally:
    R['passed'] = sum(v['pass'] for v in R['results'].values()); R['total'] = len(R['results']); save()
    log(f'{R["passed"]}/{R["total"]} passed')
