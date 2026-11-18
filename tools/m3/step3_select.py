"""M3 Step 3: reproducible sample of 30 live picks for real-listing verification.
Pool: Edge's live lists of Nov 17, 2026 (data/scout.json Flips, data/buyer.json Under market), English Pokémon only;
an item on both lists counts once, as a Flip. Strata: A = every Flip whose lowest listing is $75 or less (Keo's buy limit);
B = 9 of the other Flips; C = 10 of the Under market items not already in A/B's pool. Seeded random draw, items sorted by id first.
usage: python3 tools/m3/step3_select.py scout.json buyer.json out.json"""
import json, random, sys
s, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
fl = sorted([p for p in s["picks"] if p["plan"] == "flip" and p["k"] == "pokemon"], key=lambda p: p["id"])
fids = {p["id"] for p in fl}
un = sorted([p for p in b["under"] if p["k"] == "pokemon" and p["id"] not in fids], key=lambda p: p["id"])
A = [p for p in fl if p["lo"] <= 7500]
rest = [p for p in fl if p["lo"] > 7500]
rnd = random.Random(20261118)
B = sorted(rnd.sample(rest, 9), key=lambda p: p["id"])
C = sorted(rnd.sample(un, 10), key=lambda p: p["id"])
out = [dict(p, list="Flips", stratum="A <= $75") for p in A] + [dict(p, list="Flips", stratum="B > $75") for p in B] + [dict(p, list="Under market", stratum="C") for p in C]
json.dump(out, open(sys.argv[3], "w"), indent=1)
print(f"pool: {len(fl)} Flips, {len(un)} Under market (after overlap); picked A {len(A)}, B {len(B)}, C {len(C)}")
for i, p in enumerate(out, 1): print(i, p["stratum"], p["id"], p["n"], "|", p["sn"], "| market", p["p"] / 100, "lowest", p["lo"] / 100, "mid", (p.get("mid") or 0) / 100)
