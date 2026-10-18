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

# ---------------------------------------------------------------------------
# Slab watchlist — cards to pull eBay sold comps for every night.
# Requires EBAY_APP_ID secret in GitHub Actions.
#
# Fields:
#   name    Card name as you'd search it on eBay (be specific)
#   set     Set name to narrow results (e.g. "Base Set", "Obsidian Flames")
#   game    Matches a slug from GAMES above (for grouping on the site)
#   key     Optional short slug used as the dict key; auto-generated if omitted
#
# Examples (uncomment / add your own):
# ---------------------------------------------------------------------------
# Auto-mover slab pulls — eBay comps are also fetched for the top N cards
# by 1-day raw price gain each night. Tune these to control scope/API usage.
SLAB_AUTO_MOVERS_TOP_N = 30        # how many top movers to pull comps for
SLAB_AUTO_MOVERS_MIN_USD = 10      # ignore cards under this market price
SLAB_AUTO_MOVERS_MIN_PCT = 5.0     # ignore moves smaller than this % gain
SLAB_AUTO_MOVERS_CARDS_ONLY = True # True = skip sealed products (booster boxes etc.)

SLAB_WATCHLIST = [
    # Pokémon — high-value chase cards
    {"name": "Charizard", "set": "Base Set", "game": "pokemon"},
    {"name": "Charizard ex", "set": "Obsidian Flames", "game": "pokemon"},
    {"name": "Pikachu", "set": "Base Set", "game": "pokemon"},
    {"name": "Umbreon VMAX", "set": "Evolving Skies", "game": "pokemon"},
    {"name": "Lugia V", "set": "Silver Tempest", "game": "pokemon"},
    # One Piece
    {"name": "Nika Luffy", "set": "OP-01", "game": "one-piece"},
    # Add more cards here — one dict per card
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(ROOT, "data"))
SITE_DIR = os.environ.get("SITE_DIR", os.path.join(ROOT, "site"))
OUT_DIR = os.path.join(SITE_DIR, "data")
