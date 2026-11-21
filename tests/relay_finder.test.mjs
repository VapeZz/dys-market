// Checks for the relay's Daily deals route (tools/deal/relay-worker.js, GET /edge/finder) with a fake GitHub and file
// store. No network, no token. node tests/relay_finder.test.mjs
import assert from "assert";
import { createHash } from "crypto";
const W = (await import(new URL("../tools/deal/relay-worker.js", import.meta.url))).default;

const TOKEN = "github_pat_TESTONLY_" + "x".repeat(40), DEVICE = "d".repeat(64);
const HASH = createHash("sha256").update(DEVICE).digest("hex");
const ENV = { PKMNPRICES_KEY: "pk", EDGE_DEVICE_HASHES: HASH, FINDER_READ_TOKEN: TOKEN };
const ext = (o = {}) => ({ kind: "nm-finder-phone", format: 1, data_day: "2026-11-19", run: "r1", counts: { candidates: 1 }, cards: [{ tcgplayer_id: 1, label: "CANDIDATE" }], ...o });
const sha = (s) => createHash("sha256").update(s).digest("hex");

let seen = [];
function github(releases, files) {
  seen = [];
  globalThis.fetch = async (url, init = {}) => {
    const h = init.headers || {}; seen.push({ url, auth: h.Authorization || h.authorization || null });
    if (url.startsWith("https://api.github.com/repos/VapeZz/dys-research/releases?")) return new Response(JSON.stringify(releases), { status: 200 });
    if (url.startsWith("https://api.github.com/repos/VapeZz/dys-research/releases/assets/")) return new Response(null, { status: 302, headers: { Location: `https://objects.example/${url.split("/").pop()}?sig=1` } });
    if (url.startsWith("https://objects.example/")) { const id = url.split("/").pop().split("?")[0]; return files[id] != null ? new Response(files[id], { status: 200 }) : new Response("gone", { status: 404 }); }
    if (url.startsWith("https://api.pkmnprices.com/")) return new Response("{}", { status: 200, headers: { "x-credits-charged": "1" } });
    throw new Error("unexpected " + url);
  };
}
const rel = (id, name, body, o = {}) => ({ id, name, draft: false, published_at: "2026-11-20T03:20:00Z", assets: [{ name: "phone.json", url: `https://api.github.com/repos/VapeZz/dys-research/releases/assets/${id}`, digest: body == null ? null : "sha256:" + sha(body) }], ...o });
const call = (path = "/edge/finder", pass = DEVICE, env = ENV) => W.fetch(new Request("https://relay.example" + path, { headers: { "X-Edge-Pass": pass, Origin: "https://market.driveyourstyle.net" } }), env);

let n = 0; const test = async (name, fn) => { try { await fn(); n++; } catch (e) { console.error("FAIL " + name + "\n", e); process.exitCode = 1; } };

await test("not connected: no token -> 503 not-connected, nothing fetched", async () => {
  github([], {}); const r = await call("/edge/finder", DEVICE, { ...ENV, FINDER_READ_TOKEN: "" });
  assert.strictEqual(r.status, 503); assert.deepStrictEqual(await r.json(), { error: "not-connected" }); assert.strictEqual(seen.length, 0);
});
await test("a device that isn't paired is refused before anything is fetched", async () => {
  github([], {}); const r = await call("/edge/finder", "nope".repeat(20));
  assert.strictEqual(r.status, 401); assert.strictEqual(seen.length, 0);
});
await test("newest published finder-phone release wins; drafts, staging and other releases are ignored", async () => {
  const a = JSON.stringify(ext({ run: "old" })), b = JSON.stringify(ext({ run: "new" })), d = JSON.stringify(ext({ run: "draft" }));
  github([rel(5, "finder-phone-2026-11-18-r1", a), rel(9, "finder-phone-2026-11-19-r2", b), rel(12, "finder-phone-2026-11-20-r3", d, { draft: true }),
    rel(13, "finder-phone-2026-11-20-r4-staging", d), rel(14, "finder-2026-11-20-r4", d), rel(15, "private-ref-2026-11-19", d)], { 5: a, 9: b, 12: d, 13: d, 14: d, 15: d });
  const r = await call(); const j = await r.json();
  assert.strictEqual(r.status, 200); assert.strictEqual(j.run, "new"); assert.strictEqual(j.release, "finder-phone-2026-11-19-r2");
  assert.ok(/private/.test(r.headers.get("Cache-Control")));
  assert.strictEqual(r.headers.get("Access-Control-Allow-Origin"), "https://market.driveyourstyle.net");
});
await test("the token goes only to api.github.com, never to the file store, never back to the phone", async () => {
  const b = JSON.stringify(ext()); github([rel(9, "finder-phone-x", b)], { 9: b });
  const r = await call(); const txt = await r.text();
  assert.ok(seen.filter((s) => s.url.startsWith("https://api.github.com/")).every((s) => s.auth === `Bearer ${TOKEN}`));
  assert.ok(seen.filter((s) => !s.url.startsWith("https://api.github.com/")).every((s) => s.auth == null), JSON.stringify(seen));
  assert.ok(!txt.includes(TOKEN) && !txt.includes("github_pat"));
});
await test("a file that doesn't match GitHub's digest, or isn't a phone extract, is refused", async () => {
  const b = JSON.stringify(ext()); github([rel(9, "finder-phone-x", b)], { 9: b + " " });
  assert.deepStrictEqual(await (await call()).json(), { error: "digest" });
  const bad = JSON.stringify({ kind: "nm-finder-report", format: 1, cards: [] }); github([rel(9, "finder-phone-x", bad)], { 9: bad });
  const r = await call(); assert.strictEqual(r.status, 502); assert.deepStrictEqual(await r.json(), { error: "format" });
});
await test("no published extract -> 404 none; GitHub trouble -> 502", async () => {
  github([], {}); let r = await call(); assert.strictEqual(r.status, 404); assert.deepStrictEqual(await r.json(), { error: "none" });
  globalThis.fetch = async () => new Response("rate", { status: 403 }); r = await call(); assert.strictEqual(r.status, 502);
});
await test("the sold-price routes are unchanged; unknown paths still 404; only GET", async () => {
  github([], {});
  let r = await call("/v1/cards?tcg_player_id=1"); assert.strictEqual(r.status, 200); assert.strictEqual(r.headers.get("x-credits-charged"), "1");
  r = await call("/v1/anything"); assert.strictEqual(r.status, 404);
  r = await call("/edge/finder/../v1/x"); assert.notStrictEqual(r.status, 200);
  r = await W.fetch(new Request("https://relay.example/edge/finder", { method: "POST", headers: { "X-Edge-Pass": DEVICE } }), ENV); assert.strictEqual(r.status, 405);
});
await test("only the finder summary fields reach the phone, whatever the file holds", async () => {
  const card = { tcgplayer_id: 7, name: "X", label: "UNCERTAIN", reasons: ["r"], max_listing_price: 10, tcgplayer_url: "https://www.tcgplayer.com/product/7?Language=English&Condition=Near+Mint",
    evidence: { ebay_raw_sales_30d: "8–19", ebay_comps: [[1, 2, "raw", 1]], seller: "bob" }, listing_price: 9.5, seller_name: "bob", sold_prices: [1, 2, 3], market_tcgcsv: 20 };
  const evil = { tcgplayer_id: 8, label: "REJECT", tcgplayer_url: "javascript:alert(1)" };
  const odd = { tcgplayer_id: 9, label: "SOMETHING" };
  const b = JSON.stringify(ext({ cards: [card, evil, odd], comps: [[1, 2]], pkmnprices: { key: "x" }, counts: { candidates: 1, secret: 5 }, reasons_top: [["seller under 98%", 3], ["bad"], { x: 1 }] }));
  github([rel(9, "finder-phone-x", b)], { 9: b });
  const j = await (await call()).json(), txt = JSON.stringify(j);
  assert.deepStrictEqual(Object.keys(j).sort(), ["cards", "counts", "data_day", "finished", "format", "kind", "published", "reasons_top", "release", "rules_version", "run", "status"]);
  assert.strictEqual(j.cards.length, 2, "unknown labels dropped");
  assert.deepStrictEqual(j.cards[0].evidence, { ebay_raw_sales_30d: "8–19" });
  for (const bad of ['"listing_price"', '"seller"', "bob", "sold_prices", "market_tcgcsv", '"comps"', "pkmnprices", "secret", "ebay_comps"]) assert.ok(!txt.includes(bad), bad);
  assert.strictEqual(j.cards[1].tcgplayer_url, null, "only tcgplayer.com product links pass");
  assert.deepStrictEqual(j.reasons_top, [["seller under 98%", 3]]);
});
console.log(`${n} relay Daily deals tests passed`);
