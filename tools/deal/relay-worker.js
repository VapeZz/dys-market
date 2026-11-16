/* DYS Edge → PkmnPrices relay (Cloudflare Worker, free plan). Deployed Nov 16, 2026 as dys-edge-relay (Keo's go).

   Why: PkmnPrices' API sends no CORS header, so a phone page can't call it, and the API key must not sit in a
   public page. This worker holds the key and forwards only the read-only calls the Deal check uses.
   It stores nothing and logs nothing beyond Cloudflare's default request counts.

   Secrets (set in the Cloudflare dashboard, never in code):
     PKMNPRICES_KEY  the PkmnPrices Pro key (Keo types it himself)
     EDGE_PASS       optional: a passphrase Keo picks; Edge sends it as X-Edge-Pass (typed once in Mine → Settings)
   Plain variable:
     EDGE_DEVICE_HASHES  SHA-256 (hex) of each paired device's random token, comma-separated. A browser that holds
                         the token sends it as X-Edge-Pass; the relay compares its hash. Only hashes live here: a hash
                         can't be used to sign in, and removing one unpairs that device.
   Workers Logs are turned off for this worker, so requests and headers aren't kept by Cloudflare's log viewer.
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

async function sha256hex(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
async function allowed(pass, env) {
  if (!pass) return false;
  if (env.EDGE_PASS && same(pass, env.EDGE_PASS)) return true;
  const hashes = String(env.EDGE_DEVICE_HASHES || "").split(/[\s,]+/).filter((h) => /^[0-9a-f]{64}$/.test(h));
  if (!hashes.length || pass.length < 32) return false;
  const h = await sha256hex(pass);
  return hashes.some((x) => same(x, h));
}

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
    if (!(await allowed(req.headers.get("X-Edge-Pass") || "", env))) return new Response("denied", { status: 401, headers: head });
    if (!env.PKMNPRICES_KEY) return new Response("relay not set up: no PkmnPrices key", { status: 503, headers: head });
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
