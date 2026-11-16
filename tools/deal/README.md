# Deal Check (M1) — development tools

The Deal check (`site/assets/edge-deal.js`) answers BUY candidate or PASS for one item at one price from real sold
prices, in plain words. PASS is the default; only a resale that clears every check is a BUY candidate (grading is
shown as information, never called). Gates and thresholds are in the file's header.

Sold prices come from PkmnPrices on demand (`site/assets/edge-pkmn.js`): one card at a time, when the owner taps
"Get sold prices", kept in the page's memory only. Nothing is stored, shared or published (Keo's decision, Nov 16:
use the Pro plan within its published terms; no licensing inquiry).

**Status:** isolated development. Not pushed, not deployed. Real data needs the relay below.

## The relay (not deployed; needs Keo's go)
PkmnPrices' API sends no CORS header (checked Nov 16 from market.driveyourstyle.net: "No 'Access-Control-Allow-Origin'
header"), so a phone page can't call it, and the key can't sit in a public page. `relay-worker.js` is a Cloudflare
Worker (free plan) that holds the key and forwards only the five read-only calls the Deal check uses, only for
`market.driveyourstyle.net`, only with the owner's passphrase. Setup (Keo, about 10 minutes):
1. Free Cloudflare account → Workers → Create → paste `relay-worker.js` → Deploy.
2. Worker → Settings → Variables → add secrets `PKMNPRICES_KEY` (the Pro key) and `EDGE_PASS` (a long random phrase).
3. Edge → Mine → Settings → Sold prices: the worker's https address and the passphrase → Save → Test.

## Files
| File | What it does |
|---|---|
| `synth.js` | Synthetic comps: named scenarios (one per gate) and random cases. Nothing is real market data. |
| `dump.js` + `ref.py` | Independent cross-check: `ref.py` is a second implementation written from the rules, not the code (verdict, resale value, profit, max price, every gate, grading, hold, collection label). `node tools/deal/dump.js 20000 > /tmp/deal.json && python3 tools/deal/ref.py /tmp/deal.json` |
| `make_fixture.js` + `mock_relay.js` | A synthetic relay in PkmnPrices' response shape, on real item ids, for local tests. Never published. |
| `expect.js` + `browser_check.py` | Browser checks in the real Edge app on a local site copy with the synthetic relay: 360/390/430 px, dark and light. |
| `relay-worker.js` | The relay above. |

Unit tests: `node tests/edge_deal.test.js`, `node tests/edge_pkmn.test.js`, `node tests/edge_strat.test.js`.
