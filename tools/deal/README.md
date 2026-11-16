# Deal Check (M1) — development tools

The Deal check panel (`site/assets/edge-deal.js`) answers BUY candidate or PASS for one item at one asking price from sold comps. PASS is the default; every gate must clear for a BUY candidate. Gates and thresholds are in the file's header.

**Status:** in isolated development on synthetic data. No real sold data is read or stored until PkmnPrices confirms its terms (project doc 14). Nothing here runs in a workflow.

| File | What it does |
|---|---|
| `synth.js` | Synthetic comps: named scenarios (one per gate) and random cases. Nothing is real market data. |
| `dump.js` + `ref.py` | Independent cross-check: `ref.py` is a second implementation written from the rules, not the code. `node tools/deal/dump.js 20000 > /tmp/deal.json && python3 tools/deal/ref.py /tmp/deal.json` |
| `make_fixture.js` | Synthetic deal files on real item ids for a local site copy (source "SYNTHETIC TEST DATA"). Never published. |
| `expect.js` + `browser_check.py` | Browser checks of the panel in the real Edge app on a local site copy, at 360/390/430 px, dark and light. |

Unit tests: `node tests/edge_deal.test.js`.

## Data file the panel reads (for the M1b data job)
`data/edge/deal/index.json` = `{ "v": 1, "sets": [<set id>, ...] }` and `data/edge/deal/<set id>.json` =
`{ "v": 1, "asOf": <day>, "source": "<provider>", "items": { "<item id>": { "comps": [[day, cents, grade, exact]], "pop": { "total", "g10", "g9" } } } }`
(days since 1970-01-01 UTC; grade `raw`, `sealed`, `PSA 10`, `PSA 9`...; exact 1 when the sale belongs to this printing alone).
Before real data: encrypt these files like `graded.enc` (the site is public) and keep within the provider's terms.
