# Drive Your Style — Market Insights

A market price tracker in the style of market.tcgguy.com, built to run at **market.driveyourstyle.net**.

- Records the TCGplayer market price of every **Pokémon, Pokémon Japan and One Piece** sealed product and card every night
- Overview with search, stats, biggest sealed and card movers (7D / 30D / 90D / 1Y / All), and recent and upcoming sets
- Sets list, set pages (sealed and card prices with 7/30/90-day change), product pages with a price-history chart
- Trends page ($5+ / $20+ / $100+ sealed movers) and a Card movers page (filter by game, set, last 12 months)
- "In stock at Drive Your Style" badges that link to your Shopify products, with your price next to the market price
- **Daily Scout** (owner only, `scout.html`): a ranked buy list every night. Flips (cheapest listing far enough under market to resell for profit after fees), momentum and dip picks, each with a score, max buy price, reasons and risk flags
- Dark and light themes, works on phones

It costs nothing to run. Prices come from the free daily TCGplayer data at [tcgcsv.com](https://tcgcsv.com). GitHub runs the nightly job and hosts the site.

---

## Setup (about 15 minutes, one time)

### 1. Put the code on GitHub
1. Sign in at github.com (or create a free account).
2. Click **+ → New repository**. Name it `dys-market`, choose **Public**, and click **Create repository**.
3. On the new repo page, click **uploading an existing file**. Drag in **everything inside** the unzipped `dys-market` folder, then click **Commit changes**.
   - On a Mac, the `.github` folder is hidden. In Finder, press **Cmd + Shift + .** to show it, and make sure it gets uploaded. Without it, nothing runs nightly.

### 2. Turn on Pages and the nightly job
1. After the first run, go to **Settings → Pages** and make sure the source is **Deploy from a branch → gh-pages / (root)**. GitHub usually sets this automatically.
2. Go to **Settings → Actions → General**. Under **Workflow permissions**, choose **Read and write permissions** and click **Save**.

### 3. First run, with price history
1. Open the **Actions** tab and click **Nightly market update** on the left.
2. Click **Run workflow**, check **Download past prices**, and click **Run workflow**.
3. Wait for the run to finish (about 20–40 minutes the first time). The site is now live at `https://<your-username>.github.io/dys-market/`.

After that it runs on its own every day at about 2:30pm Pacific, shortly after TCGplayer data updates. No need to check the box again.

### 4. Use your own domain: market.driveyourstyle.net
1. In GitHub, go to **Settings → Pages → Custom domain**, enter `market.driveyourstyle.net`, and click **Save**.
2. Add a DNS record where your domain is managed. If you bought it through Shopify, that's **Shopify admin → Settings → Domains → driveyourstyle.net → Domain settings → Edit DNS settings → Add custom record**:
   - Type: **CNAME**
   - Name: **market**
   - Points to: **`<your-username>.github.io`**
3. Back in **Settings → Pages**, tick **Enforce HTTPS** once it's available (DNS can take up to a few hours).

---

## Day to day

- **Nothing to do.** Prices update nightly. If a run fails, GitHub emails you, and the next night's run usually catches up.
- **GitHub pauses schedules on repos with no activity for 60 days.** The nightly job saves data every day, which should keep it active. If GitHub ever emails that the workflow was disabled, open **Actions → Nightly market update → Enable workflow**.
- **In-stock badges** appear when your Shopify store is open to the public; while it's password-protected, that section is hidden. Products synced by Synq are matched automatically. To force a match, edit `store-overrides.json` on GitHub: `{"your-shopify-handle": 123456}`, where the number is the TCGplayer product ID from its tcgplayer.com/product/… URL.
- **Grading and selling fees** (Grading Insights, the card-page calculator and the Intel grading picks) live in `site/assets/grade-fees.json`. When PSA, CGC, BGS, TAG, eBay, TCGplayer or Whatnot change prices, edit that file on GitHub and update its `checked` date. Prices are in cents.
- **PokemonPriceTracker data is switched off** until the account is on its Business plan, which its terms require for a site that promotes a store. While `PPT_BUSINESS_PLAN = False` in `pipeline/config.py`, the site shows no graded prices and leaves the price history PokemonPriceTracker filled in (before Oct 12, 2026) out of charts and movers. After upgrading, change it to `True` on GitHub; everything comes back on the next nightly run.
- **Third-party data is stored encrypted.** This repo is public, so data we may keep but not publish is encrypted on the data branch: PokemonPriceTracker graded prices and the price history it filled in before Oct 12, 2026 (key from the `PPT_API_KEY` secret), and cached eBay listings (key from `EBAY_CLIENT_SECRET`). The site still shows the data to visitors. **Before you change either secret**, add the old value as a new secret named `PPT_API_KEY_OLD` or `EBAY_CLIENT_SECRET_OLD`; the files are re-encrypted with the new key on the next nightly run. Deleting a secret without doing that makes the stored data unreadable.
- **Add more games** (Lorcana, Magic, etc.): add a line to `GAMES` in `pipeline/config.py` with the TCGplayer category ID from tcgcsv.com/tcgplayer/categories.

## How it works

```
GitHub Actions (nightly)
  pipeline/run.py
    ├─ tcgcsv.py     download sets, product lists and today's market prices
    ├─ snapshots.py  save today's prices (kept daily for 120 days, weekly for ~13 months)
    ├─ store.py      match your Shopify products to TCGplayer IDs
    └─ build.py      write the small JSON files in site/data/
  saved prices → "data" branch (overwritten each night, so the repo stays small)
  site/ → GitHub Pages
```

Run locally with Python 3.10+:
```
python pipeline/backfill.py       # optional: past prices, needs 7-Zip
python pipeline/run.py
cd site && python -m http.server  # open http://localhost:8000
```

Market data is for research only and isn't financial advice. This site isn't affiliated with The Pokémon Company, Bandai or TCGplayer.
