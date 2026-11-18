"""M3 Step 2 look-ahead test: scramble every snapshot after day d and confirm the lists for day d don't change.
usage: python3 tools/m3/lookahead_test.py <days dir> <meta.json> <cache.npz>"""
import sys
from datetime import date
import numpy as np
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2], "/dev/null", "2025", "--cache", sys.argv[3]]
import scout_replay as R  # noqa: E402  (loads the matrices; its run block doesn't execute on import)

rng = np.random.default_rng(5)
for d0 in (date(2025, 3, 5), date(2025, 8, 13), date(2025, 12, 31)):
    di = R.DIX[d0]
    a = R.lists_on(di)
    M2, L2, D2 = R.M.copy(), R.L.copy(), R.D.copy()
    for X in (M2, L2, D2):
        X[di + 1:] = rng.integers(0, 10**6, X[di + 1:].shape, dtype=np.int32)
    b = R.lists_on(di, M2, L2, D2)
    same = all([r["j"] for r in a[k]] == [r["j"] for r in b[k]] and [r.get("score") for r in a[k]] == [r.get("score") for r in b[k]] for k in a)
    print(d0, {k: len(v) for k, v in a.items()}, "identical after scrambling the future:", same)
    assert same
print("look-ahead test passed")
