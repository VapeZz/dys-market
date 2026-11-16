"use strict";
/* Synthetic sold-comps data for the Deal Check (M1) while the PkmnPrices licence is unconfirmed.
   Nothing here is real market data: names say "(synthetic)", prices and sales are generated from a seed.
   Same shape the nightly file will have: comps [[day, cents, grade, exact]], pop { total, g10, g9 }, asOf. */
const DAY0 = 20773;   // 2026-11-16 (days since 1970-01-01 UTC)

function rng(seed) {   // mulberry32
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
// n sales of one grade over `span` days around `mid` cents, scattered by `jitter` (share), drifting by `drift` (share over the span)
function sales(r, { grade, n, mid, jitter = 0.08, drift = 0, span = 90, exact = 1, lag = 8, day = DAY0 }) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const age = lag + Math.floor(r() * (span - lag));
    const trend = 1 + drift * (1 - age / span) - drift / 2;
    const px = Math.max(100, Math.round(mid * trend * (1 + (r() * 2 - 1) * jitter)));
    out.push([day - age, px, grade, exact]);
  }
  return out.sort((a, b) => a[0] - b[0]);
}

/* named scenarios for tests and the preview: each one aims at one gate */
function scenarios(day = DAY0) {
  const r = rng(20261116);
  const S = (o) => sales(r, { day, ...o });
  return [
    { key: "good-flip", item: { name: "Liquid modern chase card (synthetic)", t: "c", year: 2023, tcg: 12000, tcgDay: day },
      data: { asOf: day, source: "synthetic", comps: [...S({ grade: "raw", n: 24, mid: 12000 }), ...S({ grade: "PSA 10", n: 12, mid: 30000 }), ...S({ grade: "PSA 9", n: 10, mid: 15000 })], pop: { total: 4000, g10: 1200, g9: 1800 } },
      offer: { ask: 7500, cond: "NM" } },
    { key: "fair-price", item: { name: "Same card at market price (synthetic)", t: "c", year: 2023, tcg: 12000, tcgDay: day },
      data: null, offer: { ask: 11500, cond: "NM" }, same: "good-flip" },
    { key: "thin", item: { name: "Thin vintage holo (synthetic)", t: "c", year: 2000, tcg: 9000, tcgDay: day },
      data: { asOf: day, source: "synthetic", comps: [...S({ grade: "raw", n: 3, mid: 9000, span: 90 }), ...S({ grade: "raw", n: 9, mid: 5000, exact: 0, jitter: 0.4 })] },
      offer: { ask: 4000, cond: "NM" } },
    { key: "stale", item: { name: "Card with stale data (synthetic)", t: "c", year: 2022, tcg: 6000, tcgDay: day - 6 },
      data: { asOf: day - 6, source: "synthetic", comps: S({ grade: "raw", n: 15, mid: 6000, day: day - 6 }) },
      offer: { ask: 3000, cond: "NM" } },
    { key: "scattered", item: { name: "Mixed-condition card (synthetic)", t: "c", year: 2016, tcg: 5000, tcgDay: day },
      data: { asOf: day, source: "synthetic", comps: [...S({ grade: "raw", n: 7, mid: 5000, jitter: 0.05 }), ...S({ grade: "raw", n: 7, mid: 2800, jitter: 0.05 }), ...S({ grade: "raw", n: 6, mid: 7500, jitter: 0.05 })].sort((a, b) => a[0] - b[0]) },
      offer: { ask: 2500, cond: "NM" } },
    { key: "disagree", item: { name: "Sources disagree (synthetic)", t: "c", year: 2024, tcg: 9000, tcgDay: day },
      data: { asOf: day, source: "synthetic", comps: S({ grade: "raw", n: 20, mid: 5500 }) },
      offer: { ask: 3000, cond: "NM" } },
    { key: "falling", item: { name: "Falling card (synthetic)", t: "c", year: 2025, tcg: 7000, tcgDay: day },
      data: { asOf: day, source: "synthetic", comps: S({ grade: "raw", n: 30, mid: 8000, drift: -0.4, jitter: 0.04 }) },
      offer: { ask: 3500, cond: "NM" } },
    { key: "no-second", item: { name: "No second source (synthetic)", t: "c", year: 2024, tcg: null },
      data: { asOf: day, source: "synthetic", comps: S({ grade: "raw", n: 20, mid: 6000 }) },
      offer: { ask: 3000, cond: "NM" } },
    { key: "played", item: { name: "Lightly played copy (synthetic)", t: "c", year: 2023, tcg: 12000, tcgDay: day },
      data: null, offer: { ask: 7500, cond: "LP" }, same: "good-flip" },
    { key: "grade", item: { name: "Grading candidate (synthetic)", t: "c", year: 2024, tcg: 4000, tcgDay: day },
      data: { asOf: day, source: "synthetic", comps: [...S({ grade: "raw", n: 25, mid: 4000, jitter: 0.05 }), ...S({ grade: "PSA 10", n: 15, mid: 22000, jitter: 0.06 }), ...S({ grade: "PSA 9", n: 12, mid: 7000, jitter: 0.06 })], pop: { total: 3000, g10: 1500, g9: 1050 } },
      offer: { ask: 3800, cond: "NM" } },
    { key: "sealed", item: { name: "Booster box (synthetic)", t: "s", year: 2024, tcg: 16000, tcgDay: day },
      data: { asOf: day, source: "synthetic", comps: S({ grade: "sealed", n: 18, mid: 16000, jitter: 0.04 }) },
      offer: { ask: 11000 } },
    { key: "cheap", item: { name: "Under-$20 card (synthetic)", t: "c", year: 2025, tcg: 800, tcgDay: day },
      data: { asOf: day, source: "synthetic", comps: S({ grade: "raw", n: 30, mid: 800 }) },
      offer: { ask: 200, cond: "NM" } },
  ].map((s, i, all) => ({ ...s, offer: { shipIn: s.item.t === "s" ? 600 : 150, taxIn: 0, ...s.offer }, data: s.same ? all.find((x) => x.key === s.same).data : s.data }));
}

/* random cases for the independent recompute */
function randomCases(n, seed = 7) {
  const r = rng(seed), out = [], grades = ["raw", "PSA 10", "PSA 9"];
  for (let i = 0; i < n; i++) {
    const t = r() < 0.2 ? "s" : "c", mid = Math.round(500 + r() * r() * 60000);
    const comps = [];
    if (t === "s") comps.push(...sales(r, { grade: "sealed", n: Math.floor(r() * 25), mid, jitter: r() * 0.6, drift: (r() - 0.6) * 0.6, exact: r() < 0.9 ? 1 : 0, lag: Math.floor(r() * 30) }));
    else for (const g of grades) comps.push(...sales(r, { grade: g, n: Math.floor(r() * (g === "raw" ? 30 : 14)), mid: g === "PSA 10" ? mid * (1.5 + r() * 4) : g === "PSA 9" ? mid * (0.9 + r()) : mid, jitter: r() * 0.6, drift: (r() - 0.6) * 0.6, exact: r() < 0.85 ? 1 : 0, lag: Math.floor(r() * 30) }));
    // a few comps outside the 90-day window or in the future must be ignored
    if (r() < 0.2) comps.push([DAY0 - 120, mid, t === "s" ? "sealed" : "raw", 1], [DAY0 + 2, mid * 3, t === "s" ? "sealed" : "raw", 1]);
    const total = Math.floor(r() * 5000);
    const g10 = Math.floor(total * r() * 0.7), g9 = Math.floor((total - g10) * r());
    out.push({
      item: { t, tcg: r() < 0.15 ? null : Math.round(mid * (0.6 + r() * 0.8)), tcgDay: DAY0 - Math.floor(r() * 6) },
      data: { asOf: DAY0 - Math.floor(r() * 6), comps, pop: r() < 0.3 ? null : { total, g10, g9 } },
      offer: { ask: Math.round(mid * (0.2 + r() * 1.2)), cond: t === "s" ? undefined : ["NM", "NM", "NM", "LP", "MP", "HP", "DMG"][Math.floor(r() * 7)], shipIn: [0, 150, 600][Math.floor(r() * 3)], taxIn: [0, 0, 8.375][Math.floor(r() * 3)] },
      ctx: r() < 0.15 ? { warning: { id: ["knife", "breakdown", "dip"][Math.floor(r() * 3)], verdict: ["pass", "unproven"][Math.floor(r() * 2)], name: "rule" } } : {},
    });
  }
  return out;
}

/* Edge's settings as the check sees them (Edge's defaults; eBay 13.25% + $0.40) */
const cfg = (o = {}) => ({
  today: DAY0, fees: { flat: 40, parts: [[13.25, 0, null, null]] }, buyerTax: 7.5,
  shipOut: (p, t) => t === "s" ? (p >= 10000 ? 1500 : 800) : (p >= 5000 ? 500 : 100),
  supplies: (t) => t === "s" ? 150 : 50, roi: 20, minProfit: 500, holdRate: 1,
  grade: { fee: 2500, ship: 1500, months: 3 }, ...o });

module.exports = { DAY0, rng, sales, scenarios, randomCases, cfg };
