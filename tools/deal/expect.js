// What the Deal check panel should show for given cards, worked out in Node from the same files the page reads
// and Edge's default settings. Used by tools/deal/browser_check.py. Usage: node expect.js <site dir> <id:set,...> [settings json]
const fs = require("fs"), path = require("path");
const D = require(path.join(__dirname, "../../site/assets/edge-deal.js"));
const [dir, list, over] = process.argv.slice(2);
const S = { platform: "ebay", roi: 20, shipCard: 100, shipCard50: 500, shipSealed: 800, shipSealed100: 1500, buyCard: 150, buySealed: 600, gradeShip: 1500,
  buyerTax: 7.5, supCard: 50, supSealed: 150, taxIn: 0, minProfit: 500, holdRate: 1, ...(over ? JSON.parse(over) : {}) };
const F = JSON.parse(fs.readFileSync(path.join(dir, "assets/grade-fees.json"), "utf8"));
const gr = F.graders.PSA, tier = gr.tiers[0];
const tierFor = (v) => { for (let i = 0; i < gr.tiers.length; i++) if (gr.tiers[i][2] == null || v <= gr.tiers[i][2]) return i; return gr.tiers.length - 1; };
const feeAt = (v) => gr.upcharge ? Math.max(tier[1], gr.tiers[tierFor(v)][1]) : tier[1];
const day = (d) => Math.floor(Date.parse(d + "T00:00:00Z") / 864e5);
const out = {};
for (const pair of list.split(",")) {
  const [id, g] = pair.split(":").map(Number);
  const set = JSON.parse(fs.readFileSync(path.join(dir, `data/set/${g}.json`), "utf8")), it = set.items.find((x) => x.id === id);
  const dealF = JSON.parse(fs.readFileSync(path.join(dir, `data/edge/deal/${g}.json`), "utf8")), dd = dealF.items[id];
  const t = it.t, p = it.p;
  const cfg = { today: Math.floor(Date.now() / 864e5), fees: F.sell[S.platform], buyerTax: S.platform === "none" ? 0 : S.buyerTax,
    shipOut: (x, tt) => S.platform === "none" ? 0 : tt === "s" ? (x >= 10000 ? S.shipSealed100 : S.shipSealed) : (x >= 5000 ? S.shipCard50 : S.shipCard),
    supplies: (tt) => tt === "s" ? S.supSealed : S.supCard, roi: S.roi, minProfit: S.minProfit, holdRate: S.holdRate,
    grade: { fee: feeAt(p || 0), ship: S.gradeShip, months: Math.max(1, Math.round((parseInt(tier[3], 10) || 60) / 30)) + 1 } };
  const offer = { ask: it.lo || p || 0, cond: "NM", shipIn: t === "s" ? S.buySealed : S.buyCard, taxIn: S.taxIn };
  const r = D.check({ name: it.n, t, tcg: p, tcgDay: day(set.dates[set.dates.length - 1]) }, { ...dd, asOf: dd.asOf ?? dealF.asOf, source: dealF.source }, offer, cfg, {});
  out[id] = { verdict: r.verdict, route: r.route, why: r.why, profit: r.routes.flip.profit, max: r.routes.flip.max, confidence: r.confidence, kind: dd.kind, ask: offer.ask, t, p, name: it.n };
}
process.stdout.write(JSON.stringify(out));
