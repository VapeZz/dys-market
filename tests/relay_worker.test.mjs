// Checks for the PkmnPrices relay (tools/deal/relay-worker.js) with a mocked upstream. node tests/relay_worker.test.mjs
import assert from "assert";
import { createHash } from "crypto";
const W = (await import(new URL("../tools/deal/relay-worker.js", import.meta.url))).default;
let n = 0, seen = [];
globalThis.fetch = async (url, opts) => { seen.push({ url, opts }); return new Response(JSON.stringify({ data: [1, 2] }), { status: 200, headers: { "Content-Type": "application/json", "x-credits-charged": "2" } }); };
const T = (name, fn) => fn().then(() => n++, (e) => { console.error("FAIL", name, e); process.exitCode = 1; });
const ORIGIN = "https://market.driveyourstyle.net", token = "a".repeat(20) + "b".repeat(30);
const hash = createHash("sha256").update(token).digest("hex");
const env = { PKMNPRICES_KEY: "KEY-123", EDGE_PASS: "keo-phrase-xyz", EDGE_DEVICE_HASHES: `${"0".repeat(64)}, ${hash}` };
const req = (path, pass, o = {}) => new Request(`https://dys-edge-relay.example.workers.dev${path}`, { method: o.method || "GET", headers: { Origin: o.origin || ORIGIN, ...(pass != null ? { "X-Edge-Pass": pass } : {}) } });
await T("preflight answers with CORS for the site only", async () => {
  let r = await W.fetch(req("/v1/cards", null, { method: "OPTIONS" }), env);
  assert.strictEqual(r.status, 204); assert.strictEqual(r.headers.get("Access-Control-Allow-Origin"), ORIGIN);
  r = await W.fetch(req("/v1/cards", null, { method: "OPTIONS", origin: "https://evil.example" }), env);
  assert.strictEqual(r.headers.get("Access-Control-Allow-Origin"), "null");
});
await T("no pass, wrong pass, short token, a hash itself: denied, upstream never called", async () => {
  seen = [];
  for (const p of [null, "", "wrong", "keo-phrase-xy", hash, "short"]) assert.strictEqual((await W.fetch(req("/v1/cards?tcg_player_id=1", p), env)).status, 401, String(p));
  assert.strictEqual(seen.length, 0);
});
await T("the passphrase and a paired device token both work; the key goes upstream only", async () => {
  for (const p of [env.EDGE_PASS, token]) {
    seen = [];
    const r = await W.fetch(req("/v1/cards?tcg_player_id=610516&evil=1", p), env);
    assert.strictEqual(r.status, 200); assert.strictEqual(r.headers.get("x-credits-charged"), "2"); assert.strictEqual(r.headers.get("Cache-Control"), "no-store");
    assert.strictEqual(seen[0].url, "https://api.pkmnprices.com/v1/cards?tcg_player_id=610516");
    assert.strictEqual(seen[0].opts.headers["X-API-Key"], "KEY-123");
    const body = await r.text(); assert.ok(!body.includes("KEY-123") && ![...r.headers.values()].some((v) => v.includes("KEY-123")));
  }
});
await T("only the five read-only paths; POST refused; no key means 503", async () => {
  const ok = ["/v1/cards", "/v1/cards/abc-1/listings/ebay", "/v1/cards/abc/population", "/v1/sealed", "/v1/sealed/s-1/listings/ebay"];
  for (const p of ok) assert.strictEqual((await W.fetch(req(p, token), env)).status, 200, p);
  for (const p of ["/v1/account", "/v1/cards/1/prices/history", "/v1/cards/../keys", "/v2/cards"]) assert.strictEqual((await W.fetch(req(p, token), env)).status, 404, p);
  assert.strictEqual((await W.fetch(req("/v1/cards", token, { method: "POST" }), env)).status, 405);
  assert.strictEqual((await W.fetch(req("/v1/cards", token), { ...env, PKMNPRICES_KEY: "" })).status, 503);
  assert.strictEqual((await W.fetch(req("/v1/cards", token), { EDGE_DEVICE_HASHES: "", PKMNPRICES_KEY: "k" })).status, 401);
});
console.log(`${n} relay tests passed`);
