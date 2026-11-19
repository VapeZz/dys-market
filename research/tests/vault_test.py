"""Private-part tests with DISPOSABLE keys (generated in memory, never saved) and SYNTHETIC records only.
Usage: vault_test.py <workdir> <results.json>"""
import hashlib, json, os, random, shutil, sqlite3, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import vault, leakscan
from private_schema import PRIVATE_DDL, PRIVATE_TABLES
from cryptography.hazmat.primitives import serialization

W, OUT = sys.argv[1], sys.argv[2]; os.makedirs(W, exist_ok=True); R = {}
def ok(name, cond, detail=''):
    R[name] = {'pass': bool(cond), 'detail': detail}; print(('PASS ' if cond else 'FAIL ') + name, detail, flush=True)
def fails(f):
    try: f(); return False
    except Exception: return True

# synthetic private database: 73 synthetic records on 50 synthetic card keys + one pending identity
random.seed(7); db = f'{W}/private-synthetic.db'
con = sqlite3.connect(db); con.executescript(PRIVATE_DDL)
con.execute("INSERT INTO meta VALUES('note','SYNTHETIC-PRIVATE test data, no real research')")
con.execute("INSERT INTO pending_cards VALUES('pkm|unk|pending:synthetic-card','SYNTHETIC-PRIVATE pending','synthetic')")
con.execute("INSERT INTO source_docs VALUES('synthetic.jsonl','0'||hex(randomblob(31)),73,1,'2026-11-19')")
keys = [f'pkm|en|tcgp:{900000+i}|normal' for i in range(50)]
for i in range(73):
    line = json.dumps({'synthetic': 'SYNTHETIC-PRIVATE', 'n': i})
    con.execute('INSERT INTO research_record VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (hashlib.sha256(f'syn{i}'.encode()).hexdigest(), keys[i % 50], random.choice(['REJECT', 'UNCERTAIN']), f'2026-11-18T0{i%10}:00',
                 '2026-11-17', 'SYNTHETIC', 'A', '2026-11-25', None, 1000 + i, 800 + i, None, 'synthetic.jsonl', i + 1, line,
                 hashlib.sha256(line.encode()).hexdigest(), line))
con.executemany("INSERT INTO evidence VALUES(?,?,?,?,?,?,NULL)", [(k, 'confirmed', '2026-11-18', 'none', None, None) for k in keys])
con.execute("INSERT INTO screen_run VALUES('syn-run','SYNTHETIC','2026-11-18','2026-11-19','synthetic')")
con.executemany("INSERT INTO screen_result VALUES('syn-run',?,'flagged','A')", [(k,) for k in keys])
con.executemany("INSERT INTO research_status VALUES(?,'E2','syn-run','flagged',NULL,'REJECT','2026-11-25','SYNTHETIC-PRIVATE')", [(k,) for k in keys])
con.commit(); counts = {t: con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in PRIVATE_TABLES}; con.close()
pt = open(db, 'rb').read(); pt_sha = hashlib.sha256(pt).hexdigest()

t = time.time(); A = vault.new_keypair(); B = vault.new_keypair(); keygen_s = time.time() - t
t = time.time(); blob = vault.encrypt(pt, A.public_key()); enc_ms = (time.time() - t) * 1000
enc = f'{W}/research-private-SYNTHETIC.enc'; open(enc, 'wb').write(blob)
ok('encrypt_roundtrip', vault.decrypt(blob, A) == pt, f'{len(pt)/1024:.0f} KB private file -> {len(blob)/1024:.0f} KB ciphertext in {enc_ms:.0f} ms')
ok('ciphertext_has_no_plaintext', leakscan.scan([enc]) == [] and b'SYNTHETIC-PRIVATE' not in blob and b'REJECT' not in blob,
   'leak scan of the encrypted file finds nothing; markers absent')
ok('wrong_key_refused', fails(lambda: vault.decrypt(blob, B)), 'a different private key cannot open it')
def flip(b, i): b = bytearray(b); b[i] ^= 1; return bytes(b)
hl = 4 + int.from_bytes(blob[:4], 'big')
ok('tampered_ciphertext_refused', fails(lambda: vault.decrypt(flip(blob, len(blob) - 100), A)), 'one flipped bit in the ciphertext -> refused')
hdr_json = blob[4:hl]; i = hdr_json.index(b'"plaintext_sha256": "') + 21
edited = hdr_json[:i] + (b'0' if hdr_json[i:i+1] != b'0' else b'1') + hdr_json[i+1:]
ok('tampered_header_refused', len(edited) == len(hdr_json) and fails(lambda: vault.decrypt(blob[:4] + edited + blob[hl:], A)),
   'one character changed inside the header (same length, still valid JSON) -> refused, because the header is authenticated')
ok('truncated_refused', fails(lambda: vault.decrypt(blob[:len(blob) // 2], A)), 'half a file -> refused')

# backup + recovery into a clean folder
bk = f'{W}/backup'; os.makedirs(bk, exist_ok=True); shutil.copy(enc, bk)
man = {'ciphertext_sha256': hashlib.sha256(blob).hexdigest(), 'plaintext_sha256': pt_sha, 'kid': vault.key_id(A.public_key()), 'counts': counts}
json.dump(man, open(f'{bk}/manifest.json', 'w'))
rec = f'{W}/recovered'; shutil.rmtree(rec, ignore_errors=True); os.makedirs(rec)
b2 = open(f'{bk}/{os.path.basename(enc)}', 'rb').read(); m2 = json.load(open(f'{bk}/manifest.json'))
assert hashlib.sha256(b2).hexdigest() == m2['ciphertext_sha256']
open(f'{rec}/private.db', 'wb').write(vault.decrypt(b2, A))
c2 = sqlite3.connect(f'{rec}/private.db')
rc = {t: c2.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in PRIVATE_TABLES}; ic = c2.execute('PRAGMA integrity_check').fetchone()[0]
ok('backup_recovery', rc == counts and ic == 'ok' and hashlib.sha256(open(f'{rec}/private.db', 'rb').read()).hexdigest() == pt_sha,
   f'recovered from backup in a clean folder: checksums, integrity_check, row counts ({counts["research_record"]} records) match')
# password-manager copy of the key: export with a passphrase, reload, decrypt
pem = A.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(b'disposable-test-passphrase'))
A2 = serialization.load_pem_private_key(pem, b'disposable-test-passphrase')
ok('key_from_passphrase_backup', vault.decrypt(blob, A2) == pt and fails(lambda: serialization.load_pem_private_key(pem, b'wrong')),
   'key restored from its passphrase-protected copy opens the file; a wrong passphrase does not')
# rotation
blob_b = vault.rewrap(blob, A, B.public_key())
ok('key_rotation', vault.decrypt(blob_b, B) == pt and fails(lambda: vault.decrypt(blob_b, A)) and vault.decrypt(blob, A) == pt,
   'rewrapped for a new key; new key opens it, old key does not open the new file, old file still opens with the old key')
ok('disposable_keys_not_saved', not any(f.endswith(('.pem', '.key')) for f in os.listdir(W)) and b'PRIVATE KEY' not in blob,
   f'keys generated in memory ({keygen_s:.1f} s for two 4096-bit keys) and never written')
json.dump(R, open(OUT, 'w'), indent=1)
print(f'{sum(v["pass"] for v in R.values())}/{len(R)} passed')
