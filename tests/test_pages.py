"""Tests for the static price pages (tools/price_pages.py): which pages exist and what their addresses are.

    python -m unittest tests/test_pages.py

No network, and nothing outside a temp folder is written: every case passes its own site folder and registry file.
"""
import json, os, re, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import price_pages as pp

TODAY = "2026-11-12"


def item(pid, name, price, t="c", **kw):
    return {"id": pid, "n": name, "t": t, "p": price, "s": [price, price], **kw}


def a_set(gid, name, game, items, pub="2025-01-01"):
    return {"id": gid, "n": name, "k": game, "pub": pub, "dates": ["2026-11-11", TODAY], "items": items}


def world():
    return {
        1: a_set(1, "SV01: Base Test", "pokemon", [item(101, "Pikachu (Holofoil)", 5000, no="1/10"), item(102, "Eevee (Holofoil)", 400), item(103, "Bulk Rat", 20),
                                                  item(190, "Base Test Booster Box", 12000, t="s")]),
        2: a_set(2, "YGO: Duel Test", "yugioh", [item(201, "Dark Mage", 9000), item(202, "Blue Dragon", 800), item(203, "Kuri", 350)]),
    }


def slugs_of(picks):
    return {pp.key_of(i): s for i, _, s in picks}


class PlanTests(unittest.TestCase):
    def test_first_night_picks_candidates_and_registers_them(self):
        pages = {}
        picks, st = pp.plan(world(), pages, TODAY)
        got = slugs_of(picks)
        self.assertNotIn("103|Bulk Rat", got)                      # under the price floor: no page
        self.assertEqual(got["101|Pikachu (Holofoil)"], "pikachu-base-test")
        self.assertEqual(got["190|Base Test Booster Box"], "base-test-booster-box")
        self.assertEqual(set(got), set(pages))
        self.assertEqual(st, {"kept": 0, "added": 6, "resting": 0, "waiting": 0})

    def test_a_published_page_stays_when_its_price_or_rank_falls(self):
        pages = {}
        pp.plan(world(), pages, TODAY)
        w = world()
        w[1]["items"][1]["p"] = 5          # Eevee crashes under the floor
        w[2]["items"][0]["p"] = None       # Dark Mage has no market price today
        picks, st = pp.plan(w, pages, "2026-11-13")
        got = slugs_of(picks)
        self.assertIn("102|Eevee (Holofoil)", got)
        self.assertIn("201|Dark Mage", got)
        self.assertEqual(st["kept"], 6)
        self.assertEqual(st["added"], 0)

    def test_addresses_never_change(self):
        pages = {}
        first = slugs_of(pp.plan(world(), pages, TODAY)[0])
        w = world()
        for d in w.values():               # every price reshuffled
            for n, i in enumerate(d["items"]):
                i["p"] = 100000 - n * 7
        second = slugs_of(pp.plan(w, pages, "2026-11-13")[0])
        for k, s in first.items():
            self.assertEqual(second[k], s)

    def test_an_item_that_leaves_the_data_rests_and_returns_at_the_same_address(self):
        pages = {}
        first = slugs_of(pp.plan(world(), pages, TODAY)[0])
        gone = world()
        del gone[2]                        # the whole set is missing one night
        picks, st = pp.plan(gone, pages, "2026-11-13")
        self.assertNotIn("201|Dark Mage", slugs_of(picks))
        self.assertEqual(st["resting"], 3)
        self.assertIn("201|Dark Mage", pages)                     # still registered
        back = slugs_of(pp.plan(world(), pages, "2026-11-14")[0])
        self.assertEqual(back["201|Dark Mage"], first["201|Dark Mage"])

    def test_a_new_item_never_takes_an_address_that_was_ever_used(self):
        pages = {"999|Pikachu (Holofoil)": ["pikachu-base-test", "2026-10-12", "2026-10-20"]}   # an old page, resting
        got = slugs_of(pp.plan(world(), pages, TODAY)[0])
        self.assertEqual(got["101|Pikachu (Holofoil)"], "pikachu-base-test-101")
        self.assertEqual(pages["999|Pikachu (Holofoil)"][0], "pikachu-base-test")

    def test_pokemon_always_gets_a_page_and_other_games_stop_at_the_cap(self):
        pages = {}
        picks, _ = pp.plan(world(), pages, TODAY, cap=2)
        got = slugs_of(picks)
        self.assertEqual({k for k in got if k.split("|")[0].startswith("1")}, {"101|Pikachu (Holofoil)", "102|Eevee (Holofoil)", "190|Base Test Booster Box"})
        self.assertEqual([k for k in got if k.startswith("2")], [])   # 3 Pokémon pages already pass the cap of 2
        pages = {}
        got = slugs_of(pp.plan(world(), pages, TODAY, cap=4)[0])
        self.assertEqual([k for k in got if k.startswith("2")], ["201|Dark Mage"])   # one slot left: the most valuable

    def test_the_cap_never_removes_a_page_that_exists(self):
        pages = {}
        pp.plan(world(), pages, TODAY)
        picks, st = pp.plan(world(), pages, "2026-11-13", cap=1)
        self.assertEqual(st["kept"], 6)

    def test_past_the_page_limit_nothing_new_is_added_but_nothing_is_removed(self):
        pages = {}
        pp.plan(world(), pages, TODAY)                              # 6 pages exist
        w = world()
        w[1]["items"].append(item(104, "Mew ex (Holofoil)", 70000))
        picks, st = pp.plan(w, pages, "2026-11-13", max_pages=6)
        self.assertEqual((st["kept"], st["added"], st["waiting"]), (6, 0, 1))
        self.assertNotIn("104|Mew ex (Holofoil)", pages)
        picks, st = pp.plan(w, pages, "2026-11-14", max_pages=7)    # room again: it gets its page
        self.assertEqual((st["kept"], st["added"], st["waiting"]), (6, 1, 0))

    def test_unreleased_sets_get_no_new_pages(self):
        w = world()
        w[3] = a_set(3, "SV99: Future", "pokemon", [item(301, "Mew", 9999)], pub="2027-01-01")
        self.assertNotIn("301|Mew", slugs_of(pp.plan(w, {}, TODAY)[0]))

    def test_same_result_whatever_order_the_sets_are_read_in(self):
        a, b = {}, {}
        w = world()
        r1 = slugs_of(pp.plan(w, a, TODAY)[0])
        r2 = slugs_of(pp.plan(dict(reversed(list(world().items()))), b, TODAY)[0])
        self.assertEqual(r1, r2)

    def test_slug_edge_cases(self):
        d = a_set(9, "日本語", "pokemon-jp", [])
        self.assertEqual(pp.new_slug(item(1, "カード", 500), d, set(), {}), "item")
        self.assertEqual(pp.new_slug(item(1, "カード", 500), d, {"item"}, {}), "item-1")
        self.assertEqual(pp.new_slug(item(1, "カード", 500), d, {"item", "item-1"}, {}), "item-1-2")
        for s in ("item", "item-1", "item-1-2"):
            self.assertRegex(s, r"^[a-z0-9-]+$")


class BuildTests(unittest.TestCase):
    """The whole script on a small made-up site."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dys-test-pages-")
        self.site = os.path.join(self.tmp, "site")
        self.reg = os.path.join(self.tmp, "data", "pages", "registry.json")
        os.makedirs(os.path.join(self.site, "data", "set"))
        self.write(world())
        with open(os.path.join(self.site, "sitemap.xml"), "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    '<url><loc>https://market.driveyourstyle.net/</loc><lastmod>2026-11-12</lastmod></url>'
                    '<url><loc>https://market.driveyourstyle.net/product.html?id=190&amp;set=1</loc><lastmod>2026-11-12</lastmod></url>'
                    '<url><loc>https://market.driveyourstyle.net/product.html?id=777&amp;set=1</loc><lastmod>2026-11-12</lastmod></url></urlset>')
        self._live = pp.live_pages
        pp.live_pages = lambda: (None, "")       # never the network in tests

    def tearDown(self):
        pp.live_pages = self._live

    def write(self, w, day=TODAY):
        with open(os.path.join(self.site, "data", "meta.json"), "w") as f:
            json.dump({"updated": day}, f)
        for gid, d in w.items():
            with open(os.path.join(self.site, "data", "set", f"{gid}.json"), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, separators=(",", ":"))

    def read(self, *path):
        with open(os.path.join(self.site, *path), encoding="utf-8") as f:
            return f.read()

    def registry(self):
        with open(self.reg, encoding="utf-8") as f:
            return json.load(f)

    def run_pages(self):
        pp.main([self.site, self.reg])

    def test_first_run_seeds_from_the_live_list_and_keeps_every_live_address(self):
        pp.live_pages = lambda: ({"102|Eevee (Holofoil)": "old-eevee-address", "203|Kuri": "kuri-old", "555|Gone Card": "gone-card"}, "a test")
        self.run_pages()
        files = set(os.listdir(os.path.join(self.site, "p")))
        self.assertIn("old-eevee-address.html", files)             # live address kept, not re-made
        self.assertIn("kuri-old.html", files)
        self.assertNotIn("gone-card.html", files)                  # its item isn't in the data: no page, but...
        reg = self.registry()
        self.assertEqual(reg["v"], 1)
        self.assertEqual(reg["pages"]["555|Gone Card"][0], "gone-card")   # ...the address stays reserved
        self.assertIn("pikachu-base-test.html", files)             # and the new candidates were added

    def test_no_registry_and_no_live_list_builds_but_saves_nothing(self):
        self.run_pages()
        self.assertTrue(os.listdir(os.path.join(self.site, "p")))
        self.assertFalse(os.path.exists(self.reg))

    def test_pages_files_and_links_agree(self):
        pp.live_pages = lambda: ({"102|Eevee (Holofoil)": "eevee-base-test"}, "a test")
        self.run_pages()
        files = {f[:-5] for f in os.listdir(os.path.join(self.site, "p"))}
        listed = json.loads(self.read("data", "pages.json"))
        self.assertEqual(set(listed.values()), files)
        sm = self.read("sitemap.xml")
        self.assertEqual({m for m in re.findall(r"/p/([a-z0-9-]+)\.html</loc>", sm)}, files)
        self.assertNotIn("product.html?id=190&amp;", sm)           # replaced by its price page
        self.assertIn("product.html?id=777&amp;", sm)              # no price page: stays
        self.assertEqual(sm.count("<urlset"), 1)
        self.assertTrue(sm.endswith("</urlset>"))
        for gid in (1, 2):                                         # every item's "pg" names a page that exists
            d = json.loads(self.read("data", "set", f"{gid}.json"))
            for i in d["items"]:
                if "pg" in i:
                    self.assertIn(i["pg"], files)
                    self.assertEqual(listed[pp.key_of(i)], i["pg"])
            self.assertEqual({pp.key_of(i) for i in d["items"] if "pg" in i}, {k for k in listed if k.split("|")[0].startswith(str(gid))})

    def test_a_page_is_complete_html_for_search_engines_and_names_its_item(self):
        pp.live_pages = lambda: ({"102|Eevee (Holofoil)": "eevee-base-test"}, "a test")
        self.run_pages()
        h = self.read("p", "pikachu-base-test.html")
        self.assertNotIn("@@", h)
        self.assertEqual(h.count('rel="canonical"'), 1)
        self.assertIn('<link rel="canonical" href="https://market.driveyourstyle.net/p/pikachu-base-test.html">', h)
        self.assertIn('<body data-page="price" data-id="101" data-set="1" data-var="Pikachu (Holofoil)">', h)
        self.assertIn('<base href="/">', h)
        self.assertIn('id="crumbs"', h)
        self.assertIn('id="prod"', h)
        self.assertIn("$50.00", h)
        self.assertIn("<title>Pikachu Price – Base Test | Drive Your Style</title>", h)
        self.assertNotIn("Photo from another printing", h)
        self.assertRegex(h, r'assets/app\.js\?v=\d+"')
        self.assertRegex(h, r'assets/app\.css\?v=\d+"')
        self.assertIn('href="p/eevee-base-test.html"', h)          # "More from this set" links to the other price pages

    def test_second_night_keeps_addresses_and_a_page_with_no_price_still_renders(self):
        pp.live_pages = lambda: ({"102|Eevee (Holofoil)": "eevee-base-test"}, "a test")
        self.run_pages()
        before = set(os.listdir(os.path.join(self.site, "p")))
        w = world()
        w[1]["items"][0]["p"] = None       # Pikachu: no market price tonight
        w[1]["items"][1]["p"] = 3          # Eevee: under every floor
        w[1]["items"].append(item(104, "Mew ex (Holofoil)", 70000))
        self.write(w, "2026-11-13")
        self.run_pages()
        after = set(os.listdir(os.path.join(self.site, "p")))
        self.assertTrue(before <= after)
        self.assertEqual(after - before, {"mew-ex-base-test.html"})
        h = self.read("p", "pikachu-base-test.html")
        self.assertIn("No market price yet", h)
        self.assertIn("It has no TCGplayer market price as of November 13, 2026.", h)
        self.assertNotIn("market price today: —", h)
        reg = self.registry()["pages"]
        self.assertEqual(reg["101|Pikachu (Holofoil)"], ["pikachu-base-test", TODAY, "2026-11-13"])

    def test_the_big_price_matches_what_the_page_script_shows(self):
        self.assertEqual(pp.money_shown(49304), "$493.04")
        self.assertEqual(pp.money_shown(99999), "$999.99")
        self.assertEqual(pp.money_shown(100000), "$1,000")
        self.assertEqual(pp.money_shown(291185), "$2,912")
        self.assertEqual(pp.money_shown(155250), "$1,553")      # .50 rounds up, as Math.round does
        pp.live_pages = lambda: ({"102|Eevee (Holofoil)": "eevee-base-test"}, "a test")
        w = world()
        w[1]["items"][0]["p"] = 291185
        self.write(w)
        self.run_pages()
        h = self.read("p", "pikachu-base-test.html")
        self.assertIn('<div class="price-big">$2,912</div>', h)
        self.assertIn("<b>$2,911.85</b>", h)                    # the sentence and description keep the exact price
        self.assertIn("market price today: $2,911.85.", h)

    def test_a_registry_that_cannot_be_read_is_set_aside_and_restarted_from_the_live_list(self):
        os.makedirs(os.path.dirname(self.reg))
        for broken in ('{"v": 2, "something": "else"}', "{not json", '{"v":1,"pages":{"1|A":["same","",""],"2|B":["same","",""]}}'):
            with open(self.reg, "w") as f:
                f.write(broken)
            pp.live_pages = lambda: ({"102|Eevee (Holofoil)": "old-eevee-address"}, "a test")
            self.run_pages()
            aside = [f for f in os.listdir(os.path.dirname(self.reg)) if ".unreadable-" in f]
            self.assertEqual(len(aside), 1)
            with open(os.path.join(os.path.dirname(self.reg), aside[0])) as f:
                self.assertEqual(f.read(), broken)                 # kept exactly as it was
            self.assertEqual(self.registry()["pages"]["102|Eevee (Holofoil)"][0], "old-eevee-address")
            self.assertIn("old-eevee-address.html", os.listdir(os.path.join(self.site, "p")))
            os.remove(os.path.join(os.path.dirname(self.reg), aside[0]))
            self.write(world())                                    # fresh set files for the next round

    def test_a_live_list_with_one_address_on_two_items_keeps_the_first_only(self):
        pp.live_pages = lambda: ({"102|Eevee (Holofoil)": "shared", "201|Dark Mage": "shared"}, "a test")
        self.run_pages()
        reg = self.registry()["pages"]
        self.assertEqual(reg["102|Eevee (Holofoil)"][0], "shared")
        self.assertNotEqual(reg["201|Dark Mage"][0], "shared")
        self.assertEqual(len({r[0] for r in reg.values()}), len(reg))

if __name__ == "__main__":
    unittest.main()
