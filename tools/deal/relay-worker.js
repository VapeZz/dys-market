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
   Optional, for Daily deals (not set until Keo approves it):
     FINDER_READ_TOKEN  a fine-grained GitHub token for VapeZz/dys-research only, Contents: read-only. It lists the
                        repo's published finder phone extracts ('finder-phone-*' prereleases: our own derived results,
                        no PkmnPrices data) and hands the newest to paired devices at GET /edge/finder. Without it the
                        route answers 503 "not-connected" and nothing else changes. Read-only: it can't see drafts or write.
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

/* ---------- Daily deals: the newest finder phone extract from the private research repo ---------- */
const FINDER_REPO = "VapeZz/dys-research", FINDER_PREFIX = "finder-phone-";
const json = (o, status, head, cache = "no-store") => { const h = new Headers(head); h.set("Content-Type", "application/json"); h.set("Cache-Control", cache); return new Response(JSON.stringify(o), { status, headers: h }); };
async function finder(env, head) {
  if (!env.FINDER_READ_TOKEN) return json({ error: "not-connected" }, 503, head);
  const gh = (url, accept) => fetch(url, { redirect: "manual", headers: { Authorization: `Bearer ${env.FINDER_READ_TOKEN}`, Accept: accept,
    "User-Agent": "dys-edge-relay", "X-GitHub-Api-Version": "2022-11-28" } });
  const r = await gh(`https://api.github.com/repos/${FINDER_REPO}/releases?per_page=30`, "application/vnd.github+json");
  if (!r.ok) return json({ error: "github", status: r.status }, 502, head);
  const rels = (await r.json()).filter((x) => x && !x.draft && typeof x.name === "string" && x.name.startsWith(FINDER_PREFIX) && !x.name.endsWith("-staging")).sort((a, b) => b.id - a.id);
  for (const rel of rels) {
    const a = (rel.assets || []).find((x) => x.name === "phone.json");
    if (!a) continue;
    let d = await gh(a.url, "application/octet-stream");
    // GitHub answers with a short-lived signed link to its file store; that request carries no token
    if (d.status >= 300 && d.status < 400 && d.headers.get("Location")) d = await fetch(d.headers.get("Location"), { headers: { "User-Agent": "dys-edge-relay" } });
    if (!d.ok) return json({ error: "download", status: d.status }, 502, head);
    const body = await d.text();
    const want = String(a.digest || "").replace(/^sha256:/, "");
    if (want && want !== await sha256hex(body)) return json({ error: "digest" }, 502, head);
    let j; try { j = JSON.parse(body); } catch { return json({ error: "format" }, 502, head); }
    if (!j || j.kind !== "nm-finder-phone" || j.format !== 1 || !Array.isArray(j.cards)) return json({ error: "format" }, 502, head);
    return json({ ...j, release: rel.name, published: rel.published_at || null }, 200, head, "private, max-age=300");
  }
  return json({ error: "none" }, 404, head);
}

export default {
  async fetch(req, env) {
    const origin = req.headers.get("Origin") || "", head = cors(origin);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: head });
    if (req.method !== "GET") return new Response("method", { status: 405, headers: head });
    if (!(await allowed(req.headers.get("X-Edge-Pass") || "", env))) return new Response("denied", { status: 401, headers: head });
    const u = new URL(req.url);
    if (u.pathname === "/edge/finder") return finder(env, head);
    if (!env.PKMNPRICES_KEY) return new Response("relay not set up: no PkmnPrices key", { status: 503, headers: head });
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
