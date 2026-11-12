"""Settings for the Drive Your Style market tracker pipeline."""
import os

# Free daily mirror of TCGplayer catalog + prices. https://tcgcsv.com
BASE_URL = os.environ.get("TCGCSV_BASE", "https://tcgcsv.com").rstrip("/")
USER_AGENT = "DriveYourStyleMarket/1.0 (+https://driveyourstyle.net)"
REQUEST_PAUSE_SECONDS = float(os.environ.get("TCGCSV_PAUSE", "0.25"))

# Games to track. Add more by appending TCGplayer category IDs
# (see https://tcgcsv.com/tcgplayer/categories).
GAMES = [
    {"slug": "pokemon", "label": "Pokémon", "category": 3},
    {"slug": "pokemon-jp", "label": "Pokémon Japan", "category": 85},
    {"slug": "one-piece", "label": "One Piece", "category": 68},
    {"slug": "lorcana", "label": "Lorcana", "category": 71},
    {"slug": "riftbound", "label": "Riftbound", "category": 89},
    {"slug": "palworld", "label": "Palworld", "category": 91},
    {"slug": "gundam", "label": "Gundam", "category": 86},
    {"slug": "union-arena", "label": "Union Arena", "category": 81},
    {"slug": "yugioh", "label": "Yu-Gi-Oh!", "category": 2},
    {"slug": "dragon-ball-fusion-world", "label": "Dragon Ball", "category": 80},
]

# Your Shopify store, used to mark "In stock at Drive Your Style".
STORE_URL = os.environ.get("STORE_URL", "https://driveyourstyle.net").rstrip("/")

# Mover thresholds (USD). Items under the smallest threshold are ignored.
MOVER_THRESHOLDS = [5, 20, 100]
MOVER_WINDOWS = [7, 30, 90, 365, "all"]
MOVERS_PER_LIST = 50
# A move bigger than this is almost always a one-off sale or a bad listing, not a real move.
MOVER_MAX_GAIN_DEFAULT = 300                     # percent, for the 7, 30 and 90-day lists (unchanged)
# Over a year or more, real moves get much bigger (in Nov 2026 the median 1-year gain of Pokémon cards worth
# $20+ was over 100%, and about 990 of them had more than quadrupled), so the long lists get more room and
# two extra checks instead: the item must have been worth MOVER_LONG_MIN_START back then (a card going from
# $1 to $20 is noise), and anything that jumped past the short-window limits in the last 7 or 30 days is
# left out as a suspect listing.
MOVER_MAX_GAIN = {"365": 2500, "all": 5000}      # percent, for the 1-year and all-time lists
MOVER_LONG_MIN_START = 500                       # cents

# Snapshot retention: keep every day for this many days, then one per week.
KEEP_DAILY_DAYS = 120
KEEP_WEEKLY_DAYS = 400

# Re-download a set's product list at least this often (days).
CATALOG_REFRESH_DAYS = 7

# Our own nightly tracking started on this day. Snapshots before it hold price history filled in from
# PokemonPriceTracker, whose terms let us store it but not publish it, so they're kept encrypted
# (see sealed.py and snapshots.py).
SEALED_BEFORE = "2026-10-12"

# PokemonPriceTracker's terms allow showing its data on a site like this one (it promotes the store,
# so it counts as commercial use) only on its Business or Enterprise plan. While this is False the
# site uses none of it: no graded prices, and the price history it filled in before SEALED_BEFORE is
# left out of charts and movers. The data stays stored (encrypted), so set this to True after
# upgrading and everything comes back on the next nightly run.
PPT_BUSINESS_PLAN = False

# Personal use, which PokemonPriceTracker's API plan allows ("personal and non-commercial purposes"):
# graded prices are fetched for the owner's private DYS Edge app only. They're published encrypted
# (data/edge/graded.enc, readable only with the PokemonPriceTracker API key, which only the owner has)
# and never shown on this site. Using them for the business's buying decisions needs the Business plan.
PPT_PERSONAL = True

# Release dates TCGplayer's feed leaves blank, from the official announcement (TCGplayer group id -> YYYY-MM-DD).
# Without a date a set sorts to the bottom of the Sets page under "Other" and is missing from the calendar.
PUB_FIX = {
    24831: "2026-11-06",   # Pokémon ME06: Delta Reign
}

# Officially announced sets that TCGplayer doesn't list yet. Shown as "Announced" on the Sets page and the release
# calendar; each one drops off by itself once TCGplayer adds a set whose name contains it, or 30 days after release.
# Only add sets with an official name AND date. k = game slug, a = set code if announced.
ANNOUNCED = [
    {"k": "pokemon", "n": "Flowing Fists", "a": "", "pub": "2027-02-05"},
    {"k": "pokemon-jp", "n": "Special Deck Set MEGA", "a": "", "pub": "2026-11-13"},
    {"k": "pokemon-jp", "n": "Aura Seeker", "a": "", "pub": "2026-11-27"},
    {"k": "gundam", "n": "Blazing Fist", "a": "GD07", "pub": "2027-01-29"},
    {"k": "gundam", "n": "Cosmic Crisis", "a": "EB02", "pub": "2027-02-26"},
    {"k": "gundam", "n": "Unicorn Awakening", "a": "ST15", "pub": "2027-04-16"},
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(ROOT, "data"))
SITE_DIR = os.environ.get("SITE_DIR", os.path.join(ROOT, "site"))
OUT_DIR = os.path.join(SITE_DIR, "data")
