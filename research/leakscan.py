"""Leak scanner for anything that would be public: release files, logs, artifacts. TEST BRANCH CODE.
Usage: leakscan.py <file>... [--extra-patterns <file>]   (extra patterns: one regex per line, kept OUT of the repository)
Exit 1 if anything is found. Prints only the pattern NAME and file, never the matched text."""
import gzip, json, os, re, sqlite3, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rdbpub import PUBLIC_TABLES

PATTERNS = {
    'private key block': r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
    'GitHub token': r'\b(ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}',
    'bearer header': r'Authorization: *Bearer +[A-Za-z0-9_.-]{12,}',
    'pending identity': r'pkm\|unk\|',
    'synthetic private marker': r'SYNTHETIC-PRIVATE',
    'research decision field': r'"decision" *: *"(REJECT|UNCERTAIN|CANDIDATE|HOLD)"',
    'research record field': r'"(record_id|evidence_checks|recheck|our_numbers|rule_version)" *:',
    'restricted provider field': r'"(ebay_[a-z_]*|sold_price|psa_[a-z_]+|population|pkmnprices_[a-z_]+|ppt_[a-z_]+)" *:',
    'research table': r'CREATE TABLE (research_record|evidence|screen_run|screen_result|card_status|source_docs)\b',
}

def texts(path):
    """Yield text chunks from a file: SQLite (schema + every text value), gz, or plain."""
    raw = open(path, 'rb').read(16)
    tmp = None
    try:
        if raw[:2] == b'\x1f\x8b':
            tmp = tempfile.mkdtemp(); p2 = f'{tmp}/x'
            with gzip.open(path, 'rb') as g, open(p2, 'wb') as f: shutil.copyfileobj(g, f)
            path = p2; raw = open(path, 'rb').read(16)
        if raw.startswith(b'SQLite format 3'):
            con = sqlite3.connect(path)
            tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            extra = set(tables) - PUBLIC_TABLES
            if extra: yield f'CREATE TABLE {sorted(extra)[0]} (unexpected table)'
            for (sql,) in con.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"): yield sql
            for t in tables:
                if t.startswith('card_fts_'): continue
                cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")') if r[2] in ('TEXT', '')]
                for c in cols:
                    for (v,) in con.execute(f'SELECT DISTINCT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL'):
                        yield str(v)
            con.close()
        else:
            with open(path, 'rb') as f:
                while True:
                    b = f.read(1 << 22)
                    if not b: break
                    yield b.decode('utf-8', 'replace')
    finally:
        if tmp: shutil.rmtree(tmp, ignore_errors=True)

def scan(paths, extra=None):
    pats = {k: re.compile(v) for k, v in PATTERNS.items()}
    for i, line in enumerate(extra or []): pats[f'private pattern #{i+1}'] = re.compile(line)
    found = []
    for p in paths:
        for t in texts(p):
            if t.startswith('CREATE TABLE') and 'unexpected table' in t: found.append((p, 'unexpected table'))
            for name, rx in pats.items():
                if rx.search(t): found.append((p, name))
    return sorted(set(found))

if __name__ == '__main__':
    args = sys.argv[1:]; extra = None
    if '--extra-patterns' in args:
        i = args.index('--extra-patterns'); extra = [l.strip() for l in open(args[i + 1]) if l.strip()]; args = args[:i] + args[i + 2:]
    f = scan(args, extra)
    for p, name in f: print(f'LEAK {name}: {os.path.basename(p)}')
    print(json.dumps({'files': len(args), 'findings': len(f)}))
    sys.exit(1 if f else 0)
