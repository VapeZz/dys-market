/* DYS Edge → PkmnPrices relay (Cloudflare Worker, free plan). NOT DEPLOYED. Needs Keo's go.

   Why: PkmnPrices' API sends no CORS header, so a phone page can't call it, and the API key must not sit in a
   public page. This worker holds the key and forwards only the read-only calls the Deal check uses.
   It stores nothing and logs nothing beyond Cloudflare's default request counts.

   Secrets (set in the Cloudflare dashboard, never in code):
     PKMNPRICES_KEY  the PkmnPrices Pro key
     EDGE_PASS       a long random passphrase; Edge sends it as X-Edge-Pass (typed once in Mine → Settings)
   Only market.driveyourstyle.net may call it from a browser (ALLOW_ORIGIN). */
const API = "https://api.pkmnprices.com";
const ALLOW_ORIGIN = "https://market.driveyourstyle.net";
// the only calls forwarded: card lookup by TCGplayer id, a card's eBay sold listings and population, sealed search and sold listings
const PATHS = [/^\/v1\/cards$/, /^\/v1\/cards\/[\w-]+\/listings\/ebay$/, /^\/v1\/cards\/[\w-]+\/population$/, /^\/v1\/sealed$/, /^\/v1\/sealed\/[\w-]+\/listings\/ebay$/];
const PARAMS = new Set(["tcg_player_id", "name", "per_page", "limit", "sort", "cursor", "graded", "grader", "grade"]);

const cors = (origin) => ({
  "Access-Control-Allow-Origin": origin === ALLOW_ORIGIN ? ALLOW_ORIGIN : "null",
  "Access-Control-Allow-Headers": "X-Edge-Pass, Accept",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Expose-Headers": "x-credits-charged",
  "Access-Control-Max-Age": "86400",
  Vary: "Origin",
});

function same(a, b) {   // constant-time compare
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

export default {
  async fetch(req, env) {
    const origin = req.headers.get("Origin") || "", head = cors(origin);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: head });
    if (req.method !== "GET") return new Response("method", { status: 405, headers: head });
    if (!env.EDGE_PASS || !same(req.headers.get("X-Edge-Pass") || "", env.EDGE_PASS)) return new Response("denied", { status: 401, headers: head });
    const u = new URL(req.url);
    if (!PATHS.some((p) => p.test(u.pathname))) return new Response("not allowed", { status: 404, headers: head });
    const q = new URLSearchParams();
    for (const [k, v] of u.searchParams) if (PARAMS.has(k)) q.set(k, v);
    const r = await fetch(`${API}${u.pathname}${[...q].length ? `?${q}` : ""}`, { headers: { "X-API-Key": env.PKMNPRICES_KEY, Accept: "application/json", "User-Agent": "dys-edge-relay" } });
    const out = new Headers(head);
    out.set("Content-Type", r.headers.get("Content-Type") || "application/json");
    out.set("Cache-Control", "no-store");
    const c = r.headers.get("x-credits-charged"); if (c) out.set("x-credits-charged", c);
    return new Response(r.body, { status: r.status, headers: out });
  },
};
