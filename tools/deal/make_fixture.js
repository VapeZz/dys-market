// Synthetic deal files for local browser tests: real item ids and TCGplayer prices from a site copy, made-up sold comps.
// Usage: node tools/deal/make_fixture.js <site dir> <set id>...   (writes <site dir>/data/edge/deal/<set>.json and index.json)
// Never published: the source is "SYNTHETIC TEST DATA" and nothing here is a real sale.
const fs = require("fs"), path = require("path");
const Y = require(path.join(__dirname, "synth.js"));
const [dir, ...sets] = process.argv.slice(2);
const DAYMS = 864e5, KINDS = ["good", "thin", "stale", "scattered", "falling", "fair", "good", "good"];
const out = path.join(dir, "data/edge/deal"); fs.mkdirSync(out, { recursive: true });
const kindOf = (id) => KINDS[(id * 2654435761 >>> 0) % KINDS.length];
for (const g of sets) {
  const s = JSON.parse(fs.readFileSync(path.join(dir, `data/set/${g}.json`), "utf8"));
  const last = Math.floor(Date.parse(s.dates[s.dates.length - 1] + "T00:00:00Z") / DAYMS), today = Math.floor(Date.now() / DAYMS);
  const items = {};
  for (const it of s.items) {
    if (!it.p) continue;
    const r = Y.rng(it.id), k = kindOf(it.id), mid = it.p, grade = it.t === "s" ? "sealed" : "raw";
    const S = (o) => Y.sales(r, { day: today, grade, mid, ...o });
    let comps = k === "thin" ? S({ n: 3 }) : k === "stale" ? Y.sales(r, { day: today - 30, grade, mid, n: 12 })
      : k === "scattered" ? [...S({ n: 6, mid: mid * 0.55 }), ...S({ n: 6 }), ...S({ n: 6, mid: mid * 1.5 })]
      : k === "falling" ? S({ n: 20, mid: mid * 1.15, drift: -0.4, jitter: 0.04 }) : S({ n: 18, jitter: 0.06 });
    if (it.t === "c" && it.p >= 2000) comps = comps.concat(S({ grade: "PSA 10", n: 10, mid: mid * 2.6, jitter: 0.06 }), S({ grade: "PSA 9", n: 9, mid: mid * 1.2, jitter: 0.06 }));
    items[it.id] = { comps, pop: it.t === "c" ? { total: 2000, g10: 700, g9: 900 } : null, kind: k };
  }
  fs.writeFileSync(path.join(out, `${g}.json`), JSON.stringify({ v: 1, asOf: Math.min(today, last + 1), source: "SYNTHETIC TEST DATA", items }));
}
fs.writeFileSync(path.join(out, "index.json"), JSON.stringify({ v: 1, sets: sets.map(Number) }));
console.log(`synthetic deal files for ${sets.length} sets in ${out}`);
