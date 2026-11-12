"""Read-only check: which of the saved keys still open the locked files on the data branch?

    python tools/key_check.py /path/to/data

Tries every key slot the jobs know (pipeline/sealed.py) on every *.enc file and prints counts only:
how many files each slot opens and how many nothing opens. It never prints a key, anything derived
from a key, or any of the data, and it writes nothing.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import sealed  # noqa: E402


def opener(blob):
    """(purpose, secret name) of the first slot that opens this file, or None."""
    AESGCM = sealed._aes()
    nonce, ct = blob[len(sealed.MAGIC):len(sealed.MAGIC) + 12], blob[len(sealed.MAGIC) + 12:]
    for purpose, names in sealed.SECRETS.items():
        for name in names:
            key = sealed._key(purpose, name)
            if key is None:
                continue
            try:
                AESGCM(key).decrypt(nonce, ct, sealed.MAGIC)
                return purpose, name
            except Exception:  # noqa: BLE001  (wrong key)
                continue
    return None


def main(argv):
    data = os.path.abspath(argv[0] if argv else "data")
    slots = sorted({n for names in sealed.SECRETS.values() for n in names})
    print("Key slots: " + ", ".join(f"{n} {'is set' if (os.environ.get(n) or '').strip() else 'is NOT set'}" for n in slots))
    by_folder = {}
    for dirpath, _dirs, files in os.walk(data):
        for f in sorted(files):
            if not f.endswith(".enc"):
                continue
            path = os.path.join(dirpath, f)
            with open(path, "rb") as fh:
                blob = fh.read()
            folder = os.path.relpath(dirpath, data)
            row = by_folder.setdefault(folder, {"files": 0, "opened": {}, "locked": [], "not sealed": 0})
            row["files"] += 1
            if not blob.startswith(sealed.MAGIC):
                row["not sealed"] += 1
                continue
            hit = opener(blob)
            if hit:
                row["opened"][hit[1]] = row["opened"].get(hit[1], 0) + 1
            else:
                row["locked"].append(f)
    total = locked = 0
    lines = ["| Folder | Locked files | Opens with | Nothing opens |", "|---|---|---|---|"]
    for folder in sorted(by_folder):
        row = by_folder[folder]
        total += row["files"]
        locked += len(row["locked"])
        opened = ", ".join(f"{n}: {c}" for n, c in sorted(row["opened"].items())) or "none"
        span = ""
        if row["locked"]:
            names = sorted(row["locked"])
            span = f" ({names[0][:10]} to {names[-1][:10]})" if names[0][:4].isdigit() else f" ({', '.join(names[:3])})"
        lines.append(f"| {folder} | {row['files']} | {opened} | {len(row['locked'])}{span} |")
    out = "\n".join(lines)
    print(out)
    result = f"RESULT: {total} locked files checked; {total - locked} open with a saved key; {locked} open with none"
    print(result)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(out + "\n\n" + result + "\n")
    print(f"::notice title=Key check::{result}")


if __name__ == "__main__":
    main(sys.argv[1:])
