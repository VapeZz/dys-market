// A synthetic PkmnPrices relay for local browser tests: real item ids and TCGplayer prices from a site copy,
// made-up sold listings and population in the API's own shape. Never published; nothing here is a real sale.
// Usage: node tools/deal/make_fixture.js <site dir> <set id>...   → <site dir>/mock-relay.json
// Route keys: path + "|" + the one parameter that picks the answer (keyOf in mock_relay.js; browser_check.py uses the same rule).
const fs = require("fs"), path = require("path");
const Y = require(path.join(__dirname, "synth.js"));
const [dir, ...sets] = process.argv.slice(2);
const DAYMS = 864e5, today = Math.floor(Date.now() / DAYMS);
const KINDS = ["good", "thin", "stale", "scattered", "falling", "fair", "good", "good", "none"];
const kindOf = (id) => KINDS[(id * 2654435761 >>> 0) % KINDS.length];
const iso = (d) => new Date(d * DAYMS).toISOString().slice(0, 10);
const rows = (list, variant) => list.map(([d, c, , exact]) => ({ sold_at: iso(d), price: c / 100, currency: "USD", attribution: exact ? "exact" : "shared", sale_type: "fixed_price", variant }));
const page = (list, variant = null) => [200, { data: rows(list, variant).reverse(), pagination: { has_more: false, next_cursor: null } }];
const out = {}, kinds = {};
for (const g of sets) {
  const s = JSON.parse(fs.readFileSync(path.join(dir, `data/set/${g}.json`), "utf8"));
  for (const it of s.items) {
    if (!it.p) continue;
    const r = Y.rng(it.id), k = kindOf(it.id), mid = it.p, grade = it.t === "s" ? "sealed" : "raw";
    kinds[it.id] = k;
    const S = (o) => Y.sales(r, { day: today, grade, mid, ...o });
    const main = k === "thin" ? S({ n: 3 }) : k === "stale" ? Y.sales(r, { day: today - 30, grade, mid, n: 12 })
      : k === "scattered" ? [...S({ n: 6, mid: mid * 0.55 }), ...S({ n: 6 }), ...S({ n: 6, mid: mid * 1.5 })]
      : k === "falling" ? S({ n: 20, mid: mid * 1.15, drift: -0.4, jitter: 0.04 }) : S({ n: 18, jitter: 0.06 });
    const id = `syn-${it.id}`;
    if (it.t === "s") {
      // sealed is found by name; the mock answers any name with every sealed item of these sets
      (out["/v1/sealed|*"] ||= [200, { data: [] }])[1].data.push({ id, tcg_player_id: it.id, name: it.n });
      out[`/v1/sealed/${id}/listings/ebay|sealed`] = page(k === "none" ? [] : main);
      continue;
    }
    if (k === "none") { out[`/v1/cards|${it.id}`] = [200, { data: [] }]; continue; }
    out[`/v1/cards|${it.id}`] = [200, { data: [{ id, name: it.n }] }];
    const v = (/\((1st Edition Holofoil|1st Edition Normal|1st Edition|Unlimited Holofoil|Unlimited|Reverse Holofoil|Holofoil)\)$/.exec(it.n) || [, "Normal"])[1];   // TCGplayer printing names, as PkmnPrices uses them
    out[`/v1/cards/${id}/listings/ebay|false`] = page(main, v);
    const big = it.p >= 2000;
    out[`/v1/cards/${id}/listings/ebay|true10`] = page(big ? S({ grade: "PSA 10", n: 10, mid: mid * 2.6, jitter: 0.06 }) : [], v);
    out[`/v1/cards/${id}/listings/ebay|true9`] = page(big ? S({ grade: "PSA 9", n: 9, mid: mid * 1.2, jitter: 0.06 }) : [], v);
    out[`/v1/cards/${id}/population`] = [200, { variants: [{ variant: v, updated_at: iso(today - 12), total_population: 2000, graders: { PSA: { total: 2000, grades: { 10: 700, 9: 900 } } } }] }];
  }
}
fs.writeFileSync(path.join(dir, "mock-relay.json"), JSON.stringify({ today, kinds, routes: out }));
console.log(`synthetic relay answers for ${sets.length} sets: ${Object.keys(out).length} routes`);
