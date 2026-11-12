"""Logic tests for the price-history layer in pipeline/snapshots.py (no network).

    python -m unittest tests/test_history.py
"""
import gzip, json, os, sys, tempfile, unittest

_TMP = tempfile.mkdtemp(prefix="dys-test-history-")
os.environ["DATA_DIR"] = _TMP
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import config, snapshots


def write_plain(day, snap):
    os.makedirs(snapshots.SNAP_DIR, exist_ok=True)
    with gzip.open(os.path.join(snapshots.SNAP_DIR, f"{day}.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(snap, f)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        # These tests empty their folders before each case, so they must only ever see their own temp
        # folder. Another test file may have imported config first (then DATA_DIR above came too late and
        # snapshots would point at the real data/ folder), so the folders are pinned here, every time.
        self._dirs = (snapshots.SNAP_DIR, snapshots.HIST_DIR)
        snapshots.SNAP_DIR = os.path.join(_TMP, "snapshots")
        snapshots.HIST_DIR = os.path.join(_TMP, "history")
        for d in (snapshots.SNAP_DIR, snapshots.HIST_DIR):
            assert os.path.realpath(d).startswith(os.path.realpath(_TMP) + os.sep), d
            if os.path.isdir(d):
                for f in os.listdir(d):
                    os.remove(os.path.join(d, f))
        self.ppt = config.PPT_BUSINESS_PLAN

    def tearDown(self):
        snapshots.SNAP_DIR, snapshots.HIST_DIR = self._dirs
        config.PPT_BUSINESS_PLAN = self.ppt

    def test_history_days_join_the_site_days(self):
        write_plain("2026-10-12", {"1:Normal": 100})
        snapshots.save_history("2026-10-11", {"1:Normal": 90})
        snapshots.save_history("2025-11-09", {"1:Normal": 50})
        self.assertEqual(snapshots.available(), ["2026-10-12"])                       # the snapshot files themselves are unchanged
        self.assertEqual(snapshots.site_days(), ["2025-11-09", "2026-10-11", "2026-10-12"])
        self.assertEqual(snapshots.view("2026-10-11"), {"1:Normal": 90})
        self.assertEqual(snapshots.view("2026-10-12"), {"1:Normal": 100})

    def test_locked_snapshot_is_never_shown_while_the_plan_is_off(self):
        # A day before SEALED_BEFORE whose snapshot file exists (stands in for the PokemonPriceTracker fill).
        write_plain("2026-10-01", {"1:Normal": 777, "2:Normal": 888})
        snapshots.save_history("2026-10-01", {"1:Normal": 90})
        config.PPT_BUSINESS_PLAN = False
        self.assertEqual(snapshots.view("2026-10-01"), {"1:Normal": 90})              # only the tcgcsv rebuild
        self.assertNotIn("2026-10-01", snapshots.available())
        self.assertIn("2026-10-01", snapshots.site_days())
        config.PPT_BUSINESS_PLAN = True
        self.assertEqual(snapshots.view("2026-10-01"), {"1:Normal": 90, "2:Normal": 888})   # rebuild first, the fill only where it has nothing

    def test_a_locked_day_without_a_rebuild_stays_hidden(self):
        write_plain("2026-09-01", {"1:Normal": 777})
        config.PPT_BUSINESS_PLAN = False
        self.assertEqual(snapshots.site_days(), [])
        self.assertEqual(snapshots.view("2026-09-01"), {})

    def test_history_is_only_for_days_before_our_own_tracking(self):
        with self.assertRaises(ValueError):
            snapshots.save_history(config.SEALED_BEFORE, {"1:Normal": 1})

    def test_keep_rule_daily_weekly_monthly(self):
        from datetime import date, timedelta
        today = date(2026, 11, 12)
        days = [(today - timedelta(days=n)).isoformat() for n in range(1, 700)]
        keep = snapshots.keep_days(days, today.isoformat(), monthly=True)
        ages = sorted((today - date.fromisoformat(d)).days for d in keep)
        self.assertEqual([a for a in ages if a <= config.KEEP_DAILY_DAYS], list(range(1, config.KEEP_DAILY_DAYS + 1)))
        weekly = [a for a in ages if config.KEEP_DAILY_DAYS < a <= config.KEEP_WEEKLY_DAYS]
        self.assertTrue(all(b - a == 7 for a, b in zip(weekly[1:], weekly[2:])), weekly[:6])    # one a week
        monthly = [d for d in keep if (today - date.fromisoformat(d)).days > config.KEEP_WEEKLY_DAYS]
        self.assertEqual(len({d[:7] for d in monthly}), len(monthly))                            # one a month
        self.assertFalse(snapshots.keep_days(days, today.isoformat()) & set(monthly))            # snapshots keep no monthly tier

    def test_prune_history_leaves_snapshots_alone(self):
        write_plain("2026-10-12", {"1:Normal": 100})
        for d in ("2024-03-05", "2024-03-20", "2024-03-31", "2026-10-11"):
            snapshots.save_history(d, {"1:Normal": 1})
        removed = snapshots.prune_history("2026-11-12")
        self.assertEqual(removed, 2)
        self.assertEqual(snapshots.history_days(), ["2024-03-31", "2026-10-11"])
        self.assertEqual(snapshots.available(), ["2026-10-12"])


if __name__ == "__main__":
    unittest.main()
