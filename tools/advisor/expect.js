// What the Holdings Advisor should show for a set of holdings: the same adapter, engines and advisor the page uses, run in
// Node on the synthetic relay (tools/deal/make_fixture.js) with Edge's default settings. Used by tools/advisor/browser_check.py.
// Usage: node expect.js <site dir> <holdings json [{key, id, g, kind: Raw|Sealed|Graded, cost, cond, grader, grade, qty}]>
const fs = require("fs"), path = require("path");
const A = require(path.join(__dirname, "../../site/assets/edge-advisor.js"));
const D = require(path.join(__dirname, "../../site/assets/edge-deal.js"));
const G = require(path.join(__dirname, "../../site/assets/edge-graded.js"));
const C = require(path.join(__dirname, "../../site/assets/edge-channels.js"));
const P = require(path.join(__dirname, "../../site/assets/edge-pkmn.js"));
const M = require(path.join(__dirname, "../deal/mock_relay.js"));
const [dir, holdingsArg] = process.argv.slice(2);
const S = { roi: 20, shipCard: 100, shipCard50: 500, shipSealed: 800, shipSealed100: 1500, gradeShip: 1500, buyerTax: 7.5, supCard: 50, supSealed: 150, minProfit: 500, holdRate: 1 };
const F = JSON.parse(fs.readFileSync(path.join(dir, "assets/grade-fees.json"), "utf8"));
const mock = JSON.parse(fs.readFileSync(path.join(dir, "mock-relay.json"), "utf8"));
const gr = F.graders.PSA, tier = gr.tiers[0];
const tierFor = (v) => { for (let i = 0; i < gr.tiers.length; i++) if (gr.tiers[i][2] == null || v <= gr.tiers[i][2]) return i; return gr.tiers.length - 1; };
const feeAt = (v) => gr.upcharge ? Math.max(tier[1], gr.tiers[tierFor(v)][1]) : tier[1];
const day = (d) => Math.floor(Date.parse(d + "T00:00:00Z") / 864e5);
const today = Math.floor(Date.now() / 864e5);
const shipOut = (x, t) => t === "s" ? (x >= 10000 ? S.shipSealed100 : S.shipSealed) : (x >= 5000 ? S.shipCard50 : S.shipCard);
const pl = F.sell.ebay, p0 = pl.parts[0] || [13.25, 0, null], p1 = pl.parts[1] || [0];
const chan = (kind, name, t) => ({ item: { kind, name }, saved: {}, roi: S.roi, minProfit: S.minProfit, breaks: t === "s" ? [10000] : [5000], shipAuto: (x) => shipOut(x, t),
  ebay: { feePct: p0[0], topFrom: p0[2] ?? 750000, topPct: p1[0] || 0, feeFlat: pl.flat || 0, buyerTax: S.buyerTax, ship: null, sup: t === "s" ? S.supSealed : S.supCard } });
(async () => {
  const conn = { relay: "https://relay.test", pass: "test-pass", fetch: M.fetcher(mock.routes), today };
  const list = [];
  for (const h of JSON.parse(holdingsArg)) {
    const set = JSON.parse(fs.readFileSync(path.join(dir, `data/set/${h.g}.json`), "utf8")), it = set.items.find((x) => x.id === h.id);
    const base = { key: h.key, name: it.n, qty: h.qty || 1, cost: h.cost, cond: h.cond || "NM", grade: h.kind === "Graded" ? `${h.grader} ${h.grade}` : "" };
    if (h.kind === "Graded") {
      const res = await P.lookupGrade({ id: h.id, n: it.n }, { grader: h.grader, grade: h.grade }, conn);
      if (!res.ok) { list.push({ ...base, kind: "graded", graded: null, note: res.reason }); continue; }
      const sell = { feePct: p0[0], topFrom: p0[2] ?? null, topPct: p1[0] || 0, perOrder: pl.flat || 0, buyerTax: S.buyerTax, ship: null, supplies: S.supCard, shipAuto: (x) => shipOut(x, "c"), breaks: [5000] };
      const r = G.evaluate(res.data, { cost: h.cost, label: base.grade }, sell, { today, roi: S.roi, minProfit: S.minProfit });
      const ch = r.typical != null ? C.compare({ ...chan("graded", it.n, "c"), cost: h.cost, ref: r.typical,
        ebay: { feePct: sell.feePct, topFrom: sell.topFrom ?? 750000, topPct: sell.topPct || 0, feeFlat: sell.perOrder || 0, buyerTax: sell.buyerTax, ship: sell.ship, sup: sell.supplies || 0 } }) : null;
      list.push({ ...base, kind: "graded", graded: r, ch }); continue;
    }
    const t = it.t, p = it.p;
    const cfg = { today, fees: F.sell.ebay, buyerTax: S.buyerTax, shipOut, supplies: (tt) => tt === "s" ? S.supSealed : S.supCard, roi: S.roi, minProfit: S.minProfit, holdRate: S.holdRate,
      grade: { fee: feeAt(p || 0), ship: S.gradeShip, months: Math.max(1, Math.round((parseInt(tier[3], 10) || 60) / 30)) + 1 } };
    const item = { id: h.id, n: it.n, name: it.n, t, tcg: p, tcgDay: day(set.dates[set.dates.length - 1]) };
    const res = await P.lookup(item, conn);
    if (!res.ok) { list.push({ ...base, kind: t === "s" ? "sealed" : "raw", own: null, note: res.reason }); continue; }
    const o = D.own(item, res.data, { cost: h.cost, cond: h.cond || "NM" }, cfg);
    const ref = o.r.routes.flip.exit;
    const ch = ref && ["sell", "hold", "grade"].includes(o.label) ? C.compare({ ...chan(t === "s" ? "sealed" : "card", it.n, t), cost: h.cost, ref }) : null;
    list.push({ ...base, kind: t === "s" ? "sealed" : "raw", own: o, ch });
  }
  const B = A.board(list);
  process.stdout.write(JSON.stringify({ counts: B.counts, sellProfit: B.sellProfit, items: B.items.map((x) => ({ key: x.key, action: x.action, ref: x.ref, best: x.best ? { name: x.best.name, profit: x.best.profit, keep: x.best.keep } : null,
    profitNow: x.profitNow, gradeProfit: x.gradeProfit, kind: mock.kinds[String(x.key).split(":")[1]] })) }));
})();
