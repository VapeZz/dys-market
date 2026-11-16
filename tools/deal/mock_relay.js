// The synthetic relay's answer to a URL (shared by expect.js; browser_check.py applies the same key rule).
const keyOf = (url) => {
  const u = new URL(url), q = u.searchParams;
  if (q.has("tcg_player_id")) return `${u.pathname}|${q.get("tcg_player_id")}`;
  if (u.pathname === "/v1/sealed") return `${u.pathname}|*`;
  if (/\/listings\/ebay$/.test(u.pathname)) return `${u.pathname}|${u.pathname.startsWith("/v1/sealed") ? "sealed" : q.get("graded") === "true" ? `true${q.get("grade")}` : "false"}`;
  return u.pathname;
};
function fetcher(routes) {
  return async (url, opts) => {
    const hit = (opts.headers["X-Edge-Pass"] === "test-pass") ? routes[keyOf(url)] || [404, { error: "not found" }] : [401, "denied"];
    const [status, body] = hit;
    return { status, json: async () => body, headers: { get: (h) => h === "x-credits-charged" ? String(Math.max(1, (body && body.data && body.data.length) || 0)) : null } };
  };
}
module.exports = { keyOf, fetcher };
