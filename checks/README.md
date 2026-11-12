# Pre-go-live checks for the market site

Not part of the site and not merged to `main`. These rebuild a change against a copy of the **published** site and
test it in a real browser, so a change is proven on real data before it goes live.

```
# 1. the published site (what is live now) and a working copy of it without the old price pages and post files
git clone --depth 1 --branch gh-pages https://github.com/VapeZz/dys-market live
mkdir site && (cd live && tar cf - --exclude='./social*' --exclude='./intel-daily' --exclude='./p' --exclude='./.git' .) | tar xf - -C site

# 2. overlay the branch under test (run from that branch's checkout, here ../dys-market)
cp ../dys-market/site/*.html site/ && cp ../dys-market/site/assets/app.js ../dys-market/site/assets/app.css site/assets/

# 3. build the price pages with that branch's code; the live page list is read from the published copy
python3 ../dys-market/checks/run_pages.py site reg/registry.json live/data/pages.json

# 4. serve both the way GitHub Pages does (404.html for missing pages), then check
python3 ../dys-market/checks/serve.py site 8765 &        # the test build
python3 ../dys-market/checks/serve.py live 8766 &        # the published copy, for the before/after control
python3 ../dys-market/checks/validate.py site live       # every static page, the sitemap, no live address lost or changed
node ../dys-market/checks/check.js                       # set, card, price, not-found, home + 24 other pages, phone and desktop
node ../dys-market/checks/sample.js site                 # random price pages from every game
python3 -m unittest discover -s ../dys-market/tests -p 'test_*.py'
```

`run_pages.py` takes its code from the checkout this folder sits in (`../tools`), so copy `checks/` next to the branch
under test or check that branch out here. Card photos don't load in a sandbox that blocks TCGplayer's image host; the
checks block every outside request on purpose.
