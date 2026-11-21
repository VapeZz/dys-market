// Expected lot results for tools/lot/browser_check.py: the same sold-price adapter (raw sales only), Deal check, Buy list
// and lot modules the page uses, run in Node on the synthetic relay (mock-relay.json) with Edge's default settings.
// Usage: node expect.js <site dir> '<spec json>'
//   spec { lines: [{ id, g, cond, qty, prOk, ask }], askMode, total, shipIn, taxIn, cash, live: true | false }
//   live false: values from each card's saved estimate (derived as the page does) instead of live data.
const fs = require("fs"), path = require("path");
const A = (f) => require(path.join(__dirname, "../../site/assets", f));
const D = A("edge-deal.js"), P = A("edge-pkmn.js"), B = A("edge-buylist.js"), L = A("edge-lot.js");
const M = require(path.join(__dirname, "../deal/mock_relay.js"));
const [dir, specS] = process.argv.slice(2), spec = JSON.parse(specS);
const F = JSON.parse(fs.readFileSync(path.join(dir, "assets/grade-fees.json"), "utf8"));
const mock = JSON.parse(fs.readFileSync(path.join(dir, "mock-relay.json"), "utf8"));
const rows = JSON.parse(fs.readFileSync(path.join(dir, "data/search.json"), "utf8"));
const day = (d) => Math.floor(Date.parse(d + "T00:00:00Z") / 864e5);
const SPR = ["1st Edition Holofoil", "1st Edition Normal", "1st Edition", "Unlimited Holofoil", "Unlimited", "Reverse Holofoil", "Holofoil", "Normal"];
const printing = (n) => { const m = /\(([^()]*)\)\s*$/.exec(n || ""); return m && SPR.includes(m[1]) ? m[1] : "Normal"; };
(async () => {
  const today = Math.floor(Date.now() / 864e5);
  const cfg = { today, fees: F.sell.ebay, buyerTax: 7.5, shipOut: (x, tt) => tt === "s" ? (x >= 10000 ? 1500 : 800) : (x >= 5000 ? 500 : 100), supplies: (tt) => tt === "s" ? 150 : 50,
    roi: 20, minProfit: 500, holdRate: 1, budget: { limit: 7500, reserve: 10000, cash: spec.cash ?? null } };
  const live = new Map(), lines = [];
  let credits = 0;
  for (const [i, s] of spec.lines.entries()) {
    const set = JSON.parse(fs.readFileSync(path.join(dir, `data/set/${s.g}.json`), "utf8")), it = set.items.find((x) => x.id === s.id);
    const k = `${it.id}|${it.n}`, tcgDay = day(set.dates[set.dates.length - 1]);
    const alts = rows.filter((r) => r[0] === it.id && r[1] !== it.n && r[3] !== "s").map((r) => printing(r[1])).filter((p, j, a) => a.indexOf(p) === j);
    const item = { id: it.id, n: it.n, name: it.n, t: it.t, r: it.r, setN: set.n, tcg: it.p, tcgDay };
    let est;
    if (!live.has(k)) {
      const res = await P.lookup(item, { relay: "https://relay.test", pass: "test-pass", fetch: M.fetcher(mock.routes), today, rawOnly: true });
      credits += res.meta ? res.meta.credits || 0 : 0;
      const data = res.ok ? res.data : { asOf: today, source: "none", comps: [] };
      live.set(k, { data, tcg: it.p, tcgDay, est: res.ok ? B.derive(D, item, res.data, { ...cfg, budget: { limit: 7500, reserve: 10000, cash: null } }) : { at: Date.now(), tcg: it.p || null, grade: null, pace: null, resale: null, walk: {}, issue: "not-found" } });
    }
    est = live.get(k).est;
    lines.push({ l: `l${i}`, k, id: it.id, g: s.g, n: it.n, setN: set.n, t: it.t, cond: s.cond || "NM", qty: s.qty || 1, ask: s.ask, alts, prOk: alts.length ? !!s.prOk : true, tcg: it.p, est });
  }
  const lot = { askMode: spec.askMode || "total", total: spec.total, shipIn: spec.shipIn, taxIn: spec.taxIn, lines };
  const R = L.evaluate(D, B, lot, spec.live === false ? () => null : (k) => live.get(k), cfg, Date.now());
  const draft = spec.paid ? L.ledgerDraft(D, lot, spec.paid) : null;
  process.stdout.write(JSON.stringify({ result: R.result, mode: R.mode, value: R.value, max: R.max, walk: R.walk, open: R.open, ask: R.ask, cost: R.cost, profit: R.profit,
    rows: R.rows.map((r) => ({ k: r.k, flags: r.flags, value: r.value, counted: r.counted, qty: r.qty })), credits, draft, alts: lines.map((x) => x.alts) }));
})();
