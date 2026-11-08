"""Logic tests for pipeline/feeds.py (no network)."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import feeds


def prod(pid, title, price, available=True, handle=None, img=True):
    return {"id": pid, "title": title, "handle": handle or title.lower().replace(" ", "-"), "product_type": "Pokémon Sealed",
            "variants": [{"price": str(price), "available": available}],
            "images": [{"src": "https://cdn.example/x.jpg"}] if img else []}


class StoreTests(unittest.TestCase):
    def snap(self, *ps):
        return {str(p["id"]): feeds.summarize(p) for p in ps}

    def test_baseline_posts_nothing(self):
        self.assertEqual(feeds.diff_store(None, self.snap(prod(1, "A", 10))), [])

    def test_new_in_stock_only(self):
        old = self.snap(prod(1, "A", 10))
        new = self.snap(prod(1, "A", 10), prod(2, "B", 20), prod(3, "C", 5, available=False))
        ev = feeds.diff_store(old, new)
        self.assertEqual([(k, s["title"]) for k, s in ev], [("new", "B")])

    def test_back_in_stock(self):
        old = self.snap(prod(1, "A", 10, available=False))
        new = self.snap(prod(1, "A", 10))
        self.assertEqual([k for k, _ in feeds.diff_store(old, new)], ["back"])

    def test_price_drop_needs_10_percent(self):
        old = self.snap(prod(1, "A", 100), prod(2, "B", 100))
        new = self.snap(prod(1, "A", 95), prod(2, "B", 85))
        ev = feeds.diff_store(old, new)
        self.assertEqual([(k, s["title"], s["was"]) for k, s in ev], [("drop", "B", 100.0)])

    def test_sold_out_not_posted(self):
        old = self.snap(prod(1, "A", 10))
        new = self.snap(prod(1, "A", 10, available=False))
        self.assertEqual(feeds.diff_store(old, new), [])

    def test_embed_shape(self):
        s = feeds.summarize(prod(1, "30th Celebration ETB", 108.99, handle="eth"))
        e = feeds.store_embed("new", s)
        self.assertEqual(e["url"], "https://driveyourstyle.net/products/eth")
        self.assertIn("$108.99", e["fields"][0]["value"])
        self.assertTrue(e["title"].startswith("🆕"))
        self.assertLess(len(e["title"]), 256)


class ReleaseTests(unittest.TestCase):
    rows = [
        {"k": "yugioh", "g": "Yu-Gi-Oh!", "n": "Magnificent Maestros", "pub": "2026-11-13", "id": 24808},
        {"k": "pokemon-jp", "g": "Pokémon Japan", "n": "Aura Seeker", "pub": "2026-11-27"},
        {"k": "pokemon", "g": "Pokémon", "n": "Flowing Fists", "pub": "2027-02-05"},
    ]

    def old(self):
        return {feeds.row_key(r): r["pub"] for r in self.rows}

    def test_baseline_posts_nothing(self):
        self.assertEqual(feeds.diff_releases(None, self.rows, "2026-11-08"), [])

    def test_new_and_moved(self):
        old = self.old()
        rows = [dict(r) for r in self.rows]
        rows[1]["pub"] = "2026-12-04"                       # moved
        rows.append({"k": "lorcana", "g": "Lorcana", "n": "Into the Inkdark", "pub": "2027-02-05", "id": 1})
        ev = feeds.diff_releases(old, rows, "2026-11-08")
        self.assertEqual([(k, r["n"]) for k, r, _ in ev], [("moved", "Aura Seeker"), ("new", "Into the Inkdark")])
        self.assertEqual(ev[0][2], "2026-11-27")

    def test_past_rows_ignored(self):
        old = {}
        ev = feeds.diff_releases(old, self.rows, "2026-12-01")
        self.assertEqual([r["n"] for _, r, _ in ev], ["Flowing Fists"])

    def test_digest_window(self):
        e = feeds.digest_embed(self.rows, "2026-11-08")
        self.assertIn("Magnificent Maestros", e["description"])
        self.assertNotIn("Flowing Fists", e["description"])      # outside 14 days
        self.assertIn("Fri Nov 13", e["description"])
        self.assertIsNone(feeds.digest_embed(self.rows, "2027-03-01"))

    def test_release_embed_links(self):
        self.assertTrue(feeds.release_embed("new", self.rows[0])["url"].endswith("set.html?id=24808"))
        self.assertTrue(feeds.release_embed("new", self.rows[1])["url"].endswith("calendar.html"))


if __name__ == "__main__":
    unittest.main()
