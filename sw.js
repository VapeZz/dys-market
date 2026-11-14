/* Drive Your Style Market — app service worker.
   Network first for everything, so prices and pages are always fresh.
   The last copy of each page and data file is kept so the app still opens offline. */
const CACHE = "dys-app-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  e.respondWith(fetch(req).then((res) => {
    if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
    return res;
  }).catch(() => caches.match(req, { ignoreSearch: url.pathname.endsWith(".html") || url.pathname.endsWith("/") })
    .then((hit) => hit || (req.mode === "navigate" ? caches.match("collection.html", { ignoreSearch: true }) : Response.error()))));
});
