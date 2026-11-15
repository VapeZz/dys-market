"""Logic tests for DYS Edge's daily price files (pipeline/edge_daily.py; no network, no data folder).

    python -m unittest tests/test_edge_daily.py
"""
import json, os, random, sys, tempfile, unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import edge_daily


def days_back(latest, n):
    t = date.fromisoformat(latest)
    return [(t - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


class PackTests(unittest.TestCase):
    def test_pack_reads_as_documented(self):
        self.assertEqual(edge_daily.pack([None, None, 500, 500, 500, 510, None, 505]), "2 500 z2 10 n -5")
        self.assertEqual(edge_daily.pack([100]), "0 100")
        self.assertEqual(edge_daily.pack([100, 100]), "0 100 z")
        self.assertEqual(edge_daily.pack([None, 100, None, None, None]), "1 100")      # days with no price at the end are left off
        self.assertEqual(edge_daily.pack([None, None]), "")

    def test_unpack_is_the_reverse(self):
        self.assertEqual(edge_daily.unpack("2 500 z2 10 n -5", 8), [None, None, 500, 500, 500, 510, None, 505])
        self.assertEqual(edge_daily.unpack("1 100", 5), [None, 100, None, None, None])
        self.assertEqual(edge_daily.unpack("", 3), [None, None, None])
        self.assertEqual(edge_daily.unpack("0 100 n2 z 25", 5), [100, None, None, 100, 125])   # a change after a gap counts from the last price

    def test_round_trip_on_random_rows(self):
        rnd = random.Random(7)
        for _ in range(3000):
            n = rnd.randint(1, 130)
            row, p = [], rnd.randint(1, 500000)
            for _ in range(n):
                r = rnd.random()
                if r < 0.12:
                    row.append(None)
                else:
                    if r > 0.7:
                        p = max(1, p + rnd.randint(-5000, 5000))
                    row.append(p)
            self.assertEqual(edge_daily.unpack(edge_daily.pack(row), n), row)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.latest_day = "2026-11-14"
        self.days = days_back(self.latest_day, 150)      # more on hand than the window uses
        self.snaps = {}
        for i, d in enumerate(self.days):
            self.snaps[d] = {"1:Holofoil": 1000 + i, "1:Normal": 200, "2:Normal": 5000, "9:Normal": 50}
        for d in self.days[-40:-36]:                     # a 4-day hole for one price
            del self.snaps[d]["2:Normal"]
        self.latest = self.snaps[self.latest_day]
        self.set_files = {
            "10": {"items": [{"id": 1, "n": "Pika (Holofoil)", "t": "c", "p": 1149, "s": [1149]},
                             {"id": 1, "n": "Pika", "t": "c", "p": 200, "s": [200]},
                             {"id": 9, "n": "Cheap", "t": "c", "p": 50},                 # under $1: no price history, no row
                             {"id": 3, "n": "Unpriced", "t": "c", "p": None}]},
            "20": {"items": [{"id": 2, "n": "Box", "t": "s", "p": 5000, "s": [5000]},
                             {"id": 1, "n": "Pika (Holofoil)", "t": "c", "p": 1149, "s": [1149]}]},   # a card a second set lists too
            "30": {"items": [{"id": 9, "n": "Cheap", "t": "c", "p": 50}]},                # nothing tracked: no file
        }
        self.keys = {("1", "Pika (Holofoil)"): ["1:Holofoil"], ("1", "Pika"): ["1:Normal"], ("2", "Box"): ["2:Normal"]}
        self.calls = []

    def view(self, d):
        self.calls.append(d)
        return self.snaps[d]

    def build(self, **kw):
        return edge_daily.build(self.set_files, self.keys, kw.get("days", self.days), self.latest_day, self.view, kw.get("latest", self.latest))

    def test_window_is_the_last_120_days(self):
        win = edge_daily.window(self.days, self.latest_day)
        self.assertEqual(len(win), 120)
        self.assertEqual((win[0], win[-1]), ("2026-07-18", "2026-11-14"))
        self.assertEqual(edge_daily.window(self.days[-10:], self.latest_day), self.days[-10:])

    def test_files_and_rows(self):
        out = self.build()
        self.assertEqual(sorted(out), ["10", "20"])
        f = out["10"]
        self.assertEqual({k: v for k, v in f.items() if k != "s"}, {"v": 1, "day": "2026-11-14", "from": "2026-07-18", "days": 120})
        self.assertEqual(sorted(f["s"]), ["1|Pika", "1|Pika (Holofoil)"])
        self.assertEqual(edge_daily.unpack(f["s"]["1|Pika (Holofoil)"], 120), [1030 + i for i in range(120)])
        self.assertEqual(f["s"]["1|Pika"], "0 200 z119")
        self.assertEqual(sorted(out["20"]["s"]), ["1|Pika (Holofoil)", "2|Box"])
        self.assertEqual(out["20"]["s"]["1|Pika (Holofoil)"], f["s"]["1|Pika (Holofoil)"])
        self.assertEqual(out["20"]["s"]["2|Box"], "0 5000 z79 n4 z36")
        self.assertNotIn(self.latest_day, self.calls)        # today's prices come from the build, not a second read
        self.assertEqual(len(self.calls), 119)

    def test_a_missing_day_lists_the_dates(self):
        days = [d for d in self.days if d != "2026-10-01"]
        f = self.build(days=days)["10"]
        self.assertNotIn("from", f)
        self.assertEqual(len(f["dates"]), 119)
        self.assertNotIn("2026-10-01", f["dates"])
        self.assertEqual(edge_daily.unpack(f["s"]["1|Pika"], 119), [200] * 119)

    def test_two_prices_under_one_name_take_the_one_shown(self):
        self.keys[("2", "Box")] = ["2:Foil", "2:Normal"]
        for d in self.days:
            self.snaps[d]["2:Foil"] = 7000
        self.assertEqual(edge_daily.unpack(self.build()["20"]["s"]["2|Box"], 120)[-1], 5000)

    def test_write(self):
        with tempfile.TemporaryDirectory(prefix="dys-test-edge-daily-") as tmp:
            n_files, n_rows, n_bytes = edge_daily.write(tmp, self.build())
            self.assertEqual((n_files, n_rows), (2, 4))
            names = sorted(os.listdir(os.path.join(tmp, "edge", "daily")))
            self.assertEqual(names, ["10.json", "20.json"])
            self.assertEqual(n_bytes, sum(os.path.getsize(os.path.join(tmp, "edge", "daily", n)) for n in names))
            with open(os.path.join(tmp, "edge", "daily", "20.json"), encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["s"]["2|Box"], "0 5000 z79 n4 z36")

    def test_no_days_no_files(self):
        self.assertEqual(edge_daily.build(self.set_files, self.keys, [], self.latest_day, self.view, self.latest), {})


if __name__ == "__main__":
    unittest.main()
