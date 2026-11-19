"""DYS research database — PUBLIC part (catalog + permitted tcgcsv price history only).

Holds nothing private: no research records, evidence, screening, recheck dates, pending identities, credentials or
restricted provider data (PkmnPrices, PokemonPriceTracker, eBay, PSA, TCGplayer website). Those live only in the
encrypted private file (vault.py). TEST BRANCH CODE — not used by production.

  build(db, days_dir, catalog, provenance, missing)   full build from Pokémon-only daily extracts
  add_day(db, extract_path, day, provenance)          one new day, in one transaction (refuses out-of-order days)
  backup(db, out_gz) / restore(in_gz, db)             verified snapshot + manifest
  logical_hash(db)                                     content hash independent of row ids and file layout
"""
import gzip, hashlib, json, os, shutil, sqlite3, time
from datetime import date, timedelta

SCHEMA_VERSION = 1
D0 = date(2024, 2, 8)
FIELDS = ('market', 'low', 'mid', 'high', 'dlow')
PUBLIC_TABLES = {'meta', 'sets', 'cards', 'price_change', 'presence', 'current_state', 'archive_days', 'missing_days', 'coverage',
                 'card_fts', 'card_fts_data', 'card_fts_idx', 'card_fts_content', 'card_fts_docsize', 'card_fts_config',
                 'sqlite_stat1', 'sqlite_stat4'}  # sqlite_stat*: query-planner statistics from ANALYZE

def dnum(s): return (date.fromisoformat(s) - D0).days
def dstr(n): return (D0 + timedelta(n)).isoformat()
def cents(x): return None if x in ('', None) else int(round(float(x) * 100))
def slug(p):
    import re
    return re.sub(r'[^a-z0-9]+', '-', (p or 'normal').lower()).strip('-') or 'normal'
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

DDL = """
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE sets(set_id INTEGER PRIMARY KEY, lang TEXT, name TEXT, pub_date TEXT);
CREATE TABLE cards(card_id INTEGER PRIMARY KEY, card_key TEXT NOT NULL UNIQUE, lang TEXT NOT NULL CHECK(lang IN ('en','ja')),
  cat INTEGER NOT NULL, pid INTEGER NOT NULL, printing TEXT, kind TEXT, set_id INTEGER, name TEXT, number TEXT, rarity TEXT,
  catalog_src TEXT NOT NULL, identity TEXT NOT NULL, UNIQUE(cat, pid, printing));
CREATE TABLE archive_days(d INTEGER PRIMARY KEY, day TEXT NOT NULL UNIQUE, source TEXT NOT NULL, asset TEXT NOT NULL, sha256 TEXT NOT NULL,
  rows_en INTEGER NOT NULL, rows_ja INTEGER NOT NULL, changes INTEGER NOT NULL);
CREATE TABLE missing_days(day TEXT PRIMARY KEY, reason TEXT NOT NULL);
CREATE TABLE price_change(card_id INTEGER NOT NULL, d INTEGER NOT NULL, market INTEGER, low INTEGER, mid INTEGER, high INTEGER, dlow INTEGER,
  PRIMARY KEY(card_id, d)) WITHOUT ROWID;
CREATE TABLE presence(card_id INTEGER NOT NULL, d_from INTEGER NOT NULL, d_to INTEGER NOT NULL, PRIMARY KEY(card_id, d_from)) WITHOUT ROWID;
CREATE TABLE current_state(card_id INTEGER PRIMARY KEY, last_d INTEGER NOT NULL, market INTEGER, low INTEGER, mid INTEGER, high INTEGER,
  dlow INTEGER, run_from INTEGER NOT NULL);
CREATE TABLE coverage(card_id INTEGER PRIMARY KEY, first_listed TEXT, last_listed TEXT, days_listed INTEGER NOT NULL, gap_runs INTEGER NOT NULL,
  max_gap_days INTEGER NOT NULL, price_changes INTEGER NOT NULL, last_market INTEGER, price_age_days INTEGER, fresh INTEGER NOT NULL);
CREATE VIRTUAL TABLE card_fts USING fts5(name, set_name, number, card_key UNINDEXED, tokenize='unicode61 remove_diacritics 2');
"""

def connect(p):
    con = sqlite3.connect(p); con.execute('PRAGMA foreign_keys=ON'); return con

def load_catalog(con, catalog):
    sets = {}; rows = []
    for line in gzip.open(catalog, 'rt'):
        r = json.loads(line)
        if r['lang'] not in ('en', 'ja'): raise ValueError('catalog may only hold en/ja identities')
        if r['set_id'] is not None: sets[r['set_id']] = (r['lang'], r['set_name'], r['set_pub'])
        rows.append(r)
    con.executemany('INSERT INTO sets VALUES(?,?,?,?)', [(k, *v) for k, v in sorted(sets.items())])
    rows.sort(key=lambda r: r['card_key'])
    con.executemany('INSERT INTO cards(card_key,lang,cat,pid,printing,kind,set_id,name,number,rarity,catalog_src,identity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    [(r['card_key'], r['lang'], r['cat'], r['pid'], r['printing'], r['kind'], r['set_id'], r['name'], r['number'], r['rarity'],
                      r['catalog_src'], r['identity']) for r in rows])

def _cache(con):
    return {(c, p, s): i for i, c, p, s in con.execute('SELECT card_id,cat,pid,printing FROM cards')}

def _ensure(con, cache, cat, pid, sub, gid):
    cid = cache.get((cat, pid, sub))
    if cid is None:
        lg = 'en' if cat == 3 else 'ja'
        if not con.execute('SELECT 1 FROM sets WHERE set_id=?', (gid,)).fetchone():
            con.execute('INSERT INTO sets VALUES(?,?,?,?)', (gid, lg, None, None))
        cid = con.execute('INSERT INTO cards(card_key,lang,cat,pid,printing,kind,set_id,catalog_src,identity) VALUES(?,?,?,?,?,?,?,?,?)',
                          (f'pkm|{lg}|tcgp:{pid}|{slug(sub)}', lg, cat, pid, sub, 'unknown', gid, 'archive price file only', 'id-only')).lastrowid
        cache[(cat, pid, sub)] = cid
    return cid

def _read_extract(path):
    rows = []
    for line in gzip.open(path, 'rt'):
        c, pid, sub, gid, *v = line.rstrip('\n').split(',')
        if len(v) != 5: raise ValueError(f'{path}: bad row')
        rows.append((int(c), int(pid), sub, int(gid), [cents(x) for x in v]))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return rows

def _ingest(con, rows, d, cache, state, closed):
    changes = []; touched = []; n = {3: 0, 85: 0}
    for cat, pid, sub, gid, vals in rows:
        n[cat] += 1
        cid = _ensure(con, cache, cat, pid, sub, gid)
        s = state.get(cid)
        if s is None or s[0] != d - 1:
            if s is not None: closed.append((cid, s[6], s[0]))
            changes.append((cid, d, *vals)); run_from = d
        else:
            run_from = s[6]
            if s[1:6] != vals: changes.append((cid, d, *vals))
        state[cid] = [d, *vals, run_from]; touched.append(cid)
    con.executemany('INSERT INTO price_change VALUES(?,?,?,?,?,?,?)', changes)
    return n, len(changes), touched

def compute_coverage(con):
    data_d = con.execute('SELECT MAX(d) FROM archive_days').fetchone()[0]
    runs = {}
    for cid, a, b in con.execute('SELECT card_id,d_from,d_to FROM presence ORDER BY card_id,d_from'): runs.setdefault(cid, []).append((a, b))
    nchg = dict(con.execute('SELECT card_id, COUNT(*) FROM price_change GROUP BY card_id'))
    cur = {r[0]: r[1:] for r in con.execute('SELECT card_id,last_d,market FROM current_state')}
    out = []
    for (cid,) in con.execute('SELECT card_id FROM cards').fetchall():
        rr = runs.get(cid, []); c = cur.get(cid)
        gz = [b[0] - a[1] - 1 for a, b in zip(rr, rr[1:])]
        age = None if not c else data_d - c[0]
        out.append((cid, dstr(rr[0][0]) if rr else None, dstr(rr[-1][1]) if rr else None, sum(b - a + 1 for a, b in rr), max(len(rr) - 1, 0),
                    max(gz) if gz else 0, nchg.get(cid, 0), c[1] if c else None, age, int(bool(c and age <= 2 and c[1] is not None))))
    con.execute('DELETE FROM coverage')
    con.executemany('INSERT INTO coverage VALUES(?,?,?,?,?,?,?,?,?,?)', out)

def build_fts(con):
    con.execute('DELETE FROM card_fts')
    con.execute("INSERT INTO card_fts(rowid,name,set_name,number,card_key) SELECT c.card_id, COALESCE(c.name,''), COALESCE(s.name,''), "
                "COALESCE(c.number,''), c.card_key FROM cards c LEFT JOIN sets s USING(set_id)")

def _meta(con, **kv):
    for k, v in kv.items(): con.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (k, str(v)))

def build(db, days_dir, catalog, provenance, missing=None, until=None):
    """provenance: {day: (source, asset, sha256)}; missing: {day: reason} for days with no permitted archive."""
    if os.path.exists(db): os.remove(db)
    con = connect(db); con.executescript(DDL)
    load_catalog(con, catalog)
    cache = _cache(con); state = {}; closed = []
    days = sorted(f[:10] for f in os.listdir(days_dir) if f.endswith('.csv.gz') and (until is None or f[:10] <= until))
    for day in days:
        n, ch, _ = _ingest(con, _read_extract(f'{days_dir}/{day}.csv.gz'), dnum(day), cache, state, closed)
        src, asset, sha = provenance[day]
        con.execute('INSERT INTO archive_days VALUES(?,?,?,?,?,?,?,?)', (dnum(day), day, src, asset, sha, n[3], n[85], ch))
    con.executemany('INSERT INTO presence VALUES(?,?,?)', closed + [(cid, s[6], s[0]) for cid, s in state.items()])
    con.executemany('INSERT INTO current_state VALUES(?,?,?,?,?,?,?,?)', [(cid, *s) for cid, s in state.items()])
    first = days[0]
    for day, why in sorted((missing or {}).items()):
        if first < day < days[-1]: con.execute('INSERT INTO missing_days VALUES(?,?)', (day, why))
    build_fts(con); compute_coverage(con)
    _meta(con, schema_version=SCHEMA_VERSION, part='public', data_day=days[-1], day0=D0.isoformat(),
          note='Public-safe part: catalog + tcgcsv-derived prices only. Not production.')
    con.commit(); con.execute('ANALYZE'); con.commit(); con.execute('VACUUM'); con.close()

def add_day(db, extract_path, day, provenance, allow_gap_reason=None):
    """Apply one day atomically. Returns change count, or None if the day is already in (rerun). Refuses out-of-order days and,
    unless allow_gap_reason is given, refuses to skip a day (a skipped day could never be inserted later)."""
    con = connect(db); d = dnum(day)
    try:
        if con.execute('SELECT 1 FROM archive_days WHERE d=?', (d,)).fetchone(): return None
        last = con.execute('SELECT MAX(d) FROM archive_days').fetchone()[0]
        if d < last: raise ValueError(f'{day}: older than the data day {dstr(last)} — out-of-order days are refused')
        if d > last + 1 and not allow_gap_reason: raise ValueError(f'{day}: {d-last-1} day(s) missing before it — refused')
        rows = _read_extract(extract_path)          # a damaged extract fails here, before anything is written
        with con:
            state = {r[0]: list(r[1:]) for r in con.execute('SELECT card_id,last_d,market,low,mid,high,dlow,run_from FROM current_state')}
            cache = _cache(con); closed = []
            n, ch, touched = _ingest(con, rows, d, cache, state, closed)
            con.executemany('INSERT OR REPLACE INTO presence VALUES(?,?,?)', [(cid, state[cid][6], d) for cid in touched])
            con.executemany('INSERT OR REPLACE INTO current_state VALUES(?,?,?,?,?,?,?,?)', [(cid, *state[cid]) for cid in touched])
            for k in range(last + 1, d): con.execute('INSERT INTO missing_days VALUES(?,?)', (dstr(k), allow_gap_reason))
            src, asset, sha = provenance
            con.execute('INSERT INTO archive_days VALUES(?,?,?,?,?,?,?,?)', (d, day, src, asset, sha, n[3], n[85], ch))
            build_fts(con); compute_coverage(con); _meta(con, data_day=day)
        return ch
    finally:
        con.close()

def counts(con):
    return {t: con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in
            ('cards', 'sets', 'price_change', 'presence', 'current_state', 'archive_days', 'missing_days', 'coverage')}

def logical_hash(db, through=None):
    """Hash of the content keyed by card_key/day (independent of card_id numbering and file layout)."""
    con = connect(db); h = hashlib.sha256(); lim = dnum(through) if through else 10 ** 9
    for q in ("SELECT c.card_key, p.d, p.market, p.low, p.mid, p.high, p.dlow FROM price_change p JOIN cards c USING(card_id) WHERE p.d<=? ORDER BY c.card_key, p.d",
              "SELECT c.card_key, p.d_from, MIN(p.d_to, ?) FROM presence p JOIN cards c USING(card_id) WHERE p.d_from<=? ORDER BY c.card_key, p.d_from",
              "SELECT day, rows_en, rows_ja, changes FROM archive_days WHERE d<=? ORDER BY d"):
        args = (lim,) if q.count('?') == 1 else (lim, lim)
        for row in con.execute(q, args): h.update(repr(row).encode())
    con.close(); return h.hexdigest()

def backup(db, out_gz):
    src = connect(db); tmp = out_gz + '.tmpdb'
    if os.path.exists(tmp): os.remove(tmp)
    dst = sqlite3.connect(tmp); src.backup(dst); dst.close()
    c = counts(src); day = src.execute("SELECT v FROM meta WHERE k='data_day'").fetchone()[0]; src.close()
    db_sha = sha256_file(tmp)
    with open(tmp, 'rb') as f, gzip.GzipFile(out_gz, 'wb', compresslevel=6, mtime=0) as g: shutil.copyfileobj(f, g, 1 << 20)
    os.remove(tmp)
    man = {'part': 'public', 'data_day': day, 'db_sha256': db_sha, 'gz_sha256': sha256_file(out_gz), 'gz_bytes': os.path.getsize(out_gz),
           'counts': c, 'schema_version': SCHEMA_VERSION}
    json.dump(man, open(out_gz + '.manifest.json', 'w'), indent=1, sort_keys=True)
    return man

def restore(in_gz, man, db):
    """Restore a snapshot; every check must pass or nothing is written at db."""
    if sha256_file(in_gz) != man['gz_sha256']: raise ValueError('snapshot gz checksum mismatch')
    tmp = db + '.restoring'
    with gzip.open(in_gz, 'rb') as g, open(tmp, 'wb') as f: shutil.copyfileobj(g, f, 1 << 20)
    try:
        if sha256_file(tmp) != man['db_sha256']: raise ValueError('restored database checksum mismatch')
        con = sqlite3.connect(tmp)
        ok = con.execute('PRAGMA quick_check').fetchone()[0]; c = counts(con)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}; con.close()
        if ok != 'ok' or c != man['counts']: raise ValueError(f'restore check failed: {ok}')
        if not tables <= PUBLIC_TABLES: raise ValueError(f'unexpected tables in public snapshot: {sorted(tables - PUBLIC_TABLES)}')
        os.replace(tmp, db)
        return c
    finally:
        if os.path.exists(tmp): os.remove(tmp)
