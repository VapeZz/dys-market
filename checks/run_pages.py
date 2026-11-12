"""Run tools/price_pages.py on a copy of the published site, with the live page list read from that copy
instead of the network (the nightly job reads it from the live site).

    python3 checks/run_pages.py <site dir> <registry.json> <live pages.json>
"""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import price_pages as pp
site, reg, live = sys.argv[1], sys.argv[2], sys.argv[3]
with open(live, encoding="utf-8") as f:
    LIVE = json.load(f)
pp.live_pages = lambda: (LIVE, "the published copy")
t = time.time()
pp.main([site, reg])
print(f"took {time.time() - t:.1f}s")
