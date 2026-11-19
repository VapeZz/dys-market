"""Focused re-test (Nov 19): duplicate-draft fix and the corrected out-of-order check, in GitHub Actions.
Reads the existing test drafts; creates at most ONE new empty draft (the lookup check); uploads nothing else.
Usage: focused.py <phase> <workdir> <results.json>   phase = lookup-create | lookup-verify | ordering"""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import nightly as N, rdbpub
from extract_day import extract

PHASE, W, OUT = sys.argv[1:4]; os.makedirs(W, exist_ok=True)
R = json.load(open(OUT)) if os.path.exists(OUT) else {}
def ok(name, cond, detail=''):
    R[name] = {'pass': bool(cond), 'detail': detail}; print(('PASS ' if cond else 'FAIL ') + f'{name}: {detail}', flush=True)
def fails(f):
    try: f(); return False
    except Exception as e: return type(e).__name__
OLD = 'research-db-test-1119'; NEW = 'research-db-test-1119-lookupcheck'
lookup = lambda name: subprocess.run([sys.executable, '-c', f'import sys; sys.path.insert(0, "research"); import nightly as N; print(N.draft_release("{name}")["id"])'],
                                     capture_output=True, text=True).stdout.strip().splitlines()[-1]

if PHASE == 'lookup-create':
    ids = [lookup(OLD) for _ in range(5)]
    ok('duplicate_pair_resolves_to_one', len(set(ids)) == 1 and ids[0] == str(min(r['id'] for r in N._drafts_named(OLD))),
       f'5 separate processes all chose the lowest id {ids[0]} of the 2 existing drafts; nothing created')
    ok('no_create_by_default', fails(lambda: N.draft_release(NEW + '-never')) == 'LookupError', 'a missing draft is not created unless asked')
    ok('non_test_name_refused', fails(lambda: N.draft_release('tcgcsv-2026', create=True)) == 'PermissionError', 'tcgcsv-2026 refused')
    before = N._drafts_named(NEW)
    r = N.draft_release(NEW, create=True)          # creates once and waits until listed
    again = [lookup(NEW) for _ in range(5)]          # immediately, from 5 separate processes
    r2 = N.draft_release(NEW, create=True)          # a second "create" call must find it, not make another
    how = f'created draft {r["id"]}' if not before else f'draft {r["id"]} already existed (made by the previous run), so nothing was created'
    ok('create_once_then_found', (not before or before[0]['id'] == r['id']) and set(again) == {str(r['id'])} and r2['id'] == r['id']
       and len(N._drafts_named(NEW)) == 1, f'{how}; 5 immediate lookups in other processes + a second create call all returned it; drafts with that name: 1')
    with open(os.environ['GITHUB_ENV'], 'a') as f: f.write(f'RDB_LOOKUP_ID={r["id"]}\nRDB_STORE_ID={N.draft_release(OLD)["id"]}\n')
elif PHASE == 'lookup-verify':
    r = N.release_by_id(os.environ['RDB_LOOKUP_ID'])
    ok('id_passed_between_steps', r['name'] == NEW and len(N._drafts_named(NEW)) == 1, f'next step addressed draft {r["id"]} by id; still exactly 1')
    ok('by_id_refuses_production', fails(lambda: N.release_by_id(N.api('GET', f'/repos/{N.REPO}/releases/tags/tcgcsv-2026')['id'])) == 'PermissionError',
       'release_by_id refuses a published production release')
elif PHASE == 'ordering':
    rel = N.release_by_id(os.environ['RDB_STORE_ID'])
    assets = {a['name']: a for a in N.list_assets(rel['id'])}
    ptr_a = assets['pointer-20261119T074119Z-2026-11-15.json']; N.download_asset(ptr_a, f'{W}/p.json'); ptr = json.load(open(f'{W}/p.json'))
    N.download_asset(assets[ptr['snapshot']], f'{W}/s.db.gz'); db = f'{W}/ord.db'
    rdbpub.restore(f'{W}/s.db.gz', ptr['manifest'], db)
    src = N.source_days(); s16 = src['2026-11-16']
    N.download_public(s16['url'], f'{W}/16.7z', s16['digest']); extract(f'{W}/16.7z', f'{W}/16.csv.gz')
    before = rdbpub.sha256_file(db); P = ('t', 't', 't')
    e_old = fails(lambda: rdbpub.add_day(db, f'{W}/16.csv.gz', '2026-11-01', P))
    present = rdbpub.add_day(db, f'{W}/16.csv.gz', '2026-11-10', P)
    e_skip = fails(lambda: rdbpub.add_day(db, f'{W}/16.csv.gz', '2026-11-17', P))
    unchanged = rdbpub.sha256_file(db) == before
    ok('older_missing_day_refused', e_old == 'ValueError' and unchanged, f'2026-11-01 (older than data day, not in the database) -> {e_old}')
    ok('present_day_is_rerun_noop', present is None and unchanged, '2026-11-10 (already in) -> no-op')
    ok('skipped_day_refused', e_skip == 'ValueError' and unchanged, f'2026-11-17 with 11-16 missing -> {e_skip}; database byte-identical after all three')
    n = rdbpub.add_day(db, f'{W}/16.csv.gz', '2026-11-16', (f'github-release:{s16["tag"]}', s16['name'], s16['digest']))
    ok('next_day_still_applies', n and n > 0, f'2026-11-16 then applies normally ({n} changes)')
json.dump(R, open(OUT, 'w'), indent=1)
