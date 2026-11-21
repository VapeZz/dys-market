// The buy list's saved estimate for given cards: the same adapter (raw sales only), engine and derivation the page uses,
// run in Node on the synthetic relay (mock-relay.json) with Edge's default settings. Used by tools/buylist/browser_check.py.
// Usage: node expect_est.js <site dir> <id:set,...>   -> { id: { est, exactMax: {NM, LP, MP}, calls } }
const fs = require("fs"), path = require("path");
const D = require(path.join(__dirname, "../../site/assets/edge-deal.js"));
const P = require(path.join(__dirname, "../../site/assets/edge-pkmn.js"));
const B = require(path.join(__dirname, "../../site/assets/edge-buylist.js"));
const M = require(path.join(__dirname, "../deal/mock_relay.js"));
const [dir, list] = process.argv.slice(2);
const F = JSON.parse(fs.readFileSync(path.join(dir, "assets/grade-fees.json"), "utf8"));
const mock = JSON.parse(fs.readFileSync(path.join(dir, "mock-relay.json"), "utf8"));
const day = (d) => Math.floor(Date.parse(d + "T00:00:00Z") / 864e5);
(async () => {
  const out = {};
  for (const pair of list.split(",")) {
    const [id, g] = pair.split(":").map(Number);
    const set = JSON.parse(fs.readFileSync(path.join(dir, `data/set/${g}.json`), "utf8")), it = set.items.find((x) => x.id === id);
    const cfg = { today: Math.floor(Date.now() / 864e5), fees: F.sell.ebay, buyerTax: 7.5,
      shipOut: (x, tt) => tt === "s" ? (x >= 10000 ? 1500 : 800) : (x >= 5000 ? 500 : 100), supplies: (tt) => tt === "s" ? 150 : 50,
      roi: 20, minProfit: 500, holdRate: 1, budget: { limit: 7500, reserve: 10000, cash: null }, grade: { fee: 2500, ship: 1500, months: 3 } };
    const item = { id, n: it.n, name: it.n, t: it.t, r: it.r, setN: set.n, tcg: it.p, tcgDay: day(set.dates[set.dates.length - 1]) };
    let calls = [];
    const fetcher = M.fetcher(mock.routes), spy = (url, o) => { calls.push(url); return fetcher(url, o); };
    const res = await P.lookup(item, { relay: "https://relay.test", pass: "test-pass", fetch: spy, today: cfg.today, rawOnly: true });
    const est = res.ok ? B.derive(D, item, res.data, cfg) : null;
    const exactMax = {};
    if (res.ok) for (const cond of B.CONDS) exactMax[cond] = D.check(item, res.data, { ask: 100, cond, shipIn: 0, taxIn: 0 }, { ...cfg, budget: { limit: 7500 } }).routes.flip.max;
    out[id] = { est, exactMax, calls: calls.length, ok: res.ok, reason: res.reason || null, name: it.n, p: it.p, kind: mock.kinds[id], credits: res.meta ? res.meta.credits : 0 };
  }
  process.stdout.write(JSON.stringify(out));
})();
