/* Drive Your Style Market — app service worker.
   Network first for everything, so prices and pages are always fresh.
   The last copy of each page and data file is kept so the app still opens offline. */
const CACHE = "dys-app-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// DYS Edge on a weak signal (Nov 20, 2026, the card-show buy list): for Edge's own pages and the files it loads, wait for
// the network at most EDGE_WAIT ms when a saved copy exists, then answer from the saved copy; the network answer still
// refreshes the saved copy when it arrives. Every other page of the site keeps the plain network-first rule below.
const EDGE_WAIT = 3500;
const isEdge = (req, url) => url.pathname.includes("/edge/") || (req.referrer || "").includes("/edge/");

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (isEdge(req, url)) {
    const keep = (res) => { if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); } return res; };
    const net = fetch(req).then(keep);
    const saved = caches.match(req, { ignoreSearch: url.pathname.endsWith(".html") || url.pathname.endsWith("/") });
    e.respondWith(saved.then((hit) => {
      if (!hit) return net.catch(() => Response.error());
      return Promise.race([net.catch(() => hit), new Promise((r) => setTimeout(() => r(hit), EDGE_WAIT))]);
    }));
    return;
  }
  e.respondWith(fetch(req).then((res) => {
    if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
    return res;
  }).catch(() => caches.match(req, { ignoreSearch: url.pathname.endsWith(".html") || url.pathname.endsWith("/") })
    .then((hit) => hit || (req.mode === "navigate" ? caches.match("collection.html", { ignoreSearch: true }) : Response.error()))));
});
