"""tcgcsv daily archive (prices-<day>.ppmd.7z) -> Pokémon-only extract (categories 3 English, 85 Japanese), sorted.
Row: cat,pid,subTypeName,groupId,market,low,mid,high,directLow. Usage: extract_day.py <archive> <out.csv.gz>"""
import glob, gzip, json, os, shutil, subprocess, sys, tempfile

def extract(archive, out):
    tmp = tempfile.mkdtemp(prefix='x7z')
    try:
        r = subprocess.run(['7z', 'x', '-y', '-bso0', '-bsp0', f'-o{tmp}', archive, '*/3/*', '*/85/*', '-r'], capture_output=True)
        if r.returncode != 0: raise ValueError(f'{os.path.basename(archive)}: 7z failed ({r.returncode})')
        rows = set()
        for fp in glob.glob(f'{tmp}/*/*/*/prices'):
            cat, gid = fp.split('/')[-3], fp.split('/')[-2]
            if cat not in ('3', '85'): continue
            for p in json.load(open(fp)).get('results', []):
                v = [p.get(f) for f in ('marketPrice', 'lowPrice', 'midPrice', 'highPrice', 'directLowPrice')]
                rows.add((int(cat), p['productId'], p.get('subTypeName') or '', int(gid), tuple('' if x is None else str(x) for x in v)))
        seen = set(); lines = []
        for c, pid, sub, gid, v in sorted(rows):
            if (c, pid, sub) in seen: continue      # tcgcsv lists a few products under two groups: keep the first
            seen.add((c, pid, sub)); lines.append(f'{c},{pid},{sub},{gid},' + ','.join(v))
        if not lines: raise ValueError(f'{os.path.basename(archive)}: no Pokémon rows')
        with gzip.GzipFile(out + '.tmp', 'wb', mtime=0) as g: g.write('\n'.join(lines).encode())
        os.replace(out + '.tmp', out)
        return len(lines)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == '__main__':
    print(extract(sys.argv[1], sys.argv[2]))
