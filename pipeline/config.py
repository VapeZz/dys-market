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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(ROOT, "data"))
SITE_DIR = os.environ.get("SITE_DIR", os.path.join(ROOT, "site"))
OUT_DIR = os.path.join(SITE_DIR, "data")
