# Deal Check (M1) — development tools

The Deal check (`site/assets/edge-deal.js`) answers BUY candidate or PASS for one item at one price from real sold
prices, in plain words. PASS is the default; only a resale that clears every check is a BUY candidate (grading is
shown as information, never called). Gates and thresholds are in the file's header.

Sold prices come from PkmnPrices on demand (`site/assets/edge-pkmn.js`): one card at a time, when the owner taps
"Get sold prices", kept in the page's memory only. Nothing is stored, shared or published (Keo's decision, Nov 16:
use the Pro plan within its published terms; no licensing inquiry).

**Status:** isolated development. Not pushed, not deployed. Real data needs the relay below.

## The relay (deployed Nov 16, 2026)
`dys-edge-relay` on Keo's free Cloudflare account (signed up with Google, keo.llaneza@gmail.com):
https://dys-edge-relay.keo-llaneza.workers.dev. Code: `relay-worker.js` (tests: `node tests/relay_worker.test.mjs`).
PkmnPrices' API sends no CORS header (checked Nov 16), so a phone page can't call it, and the key can't sit in a
public page. The relay holds the key and forwards only the five read-only calls the Deal check uses, only for
`market.driveyourstyle.net`, and only for a paired device or the owner's passphrase. Workers Logs are off.
- `PKMNPRICES_KEY` (secret): Keo types it in the Cloudflare dashboard himself. Never in code, chat or GitHub.
- `EDGE_DEVICE_HASHES` (plain): SHA-256 of each paired device's random token. The token is made in that browser and
  stays in its storage (`dys-edge-relay`); only the hash goes to Cloudflare. Paired: skibidi's built-in browser.
- `EDGE_PASS` (optional secret): a passphrase Keo can set and type once in Edge on his phone.

## Files
| File | What it does |
|---|---|
| `synth.js` | Synthetic comps: named scenarios (one per gate) and random cases. Nothing is real market data. |
| `dump.js` + `ref.py` | Independent cross-check: `ref.py` is a second implementation written from the rules, not the code (verdict, resale value, profit, max price, every gate, grading, hold, collection label). `node tools/deal/dump.js 20000 > /tmp/deal.json && python3 tools/deal/ref.py /tmp/deal.json` |
| `make_fixture.js` + `mock_relay.js` | A synthetic relay in PkmnPrices' response shape, on real item ids, for local tests. Never published. |
| `expect.js` + `browser_check.py` | Browser checks in the real Edge app on a local site copy with the synthetic relay: 360/390/430 px, dark and light. |
| `relay-worker.js` | The relay above. |

Unit tests: `node tests/edge_deal.test.js`, `node tests/edge_pkmn.test.js`, `node tests/edge_strat.test.js`.
