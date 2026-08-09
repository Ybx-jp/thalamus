// Console service worker. Shell strategy is NETWORK-FIRST with cache
// fallback: the app is useless without its server, so when the server is
// reachable we always want the latest shell (no two-launch update dance after an
// upgrade), and when it isn't, the API is unreachable too — the cached shell is
// just a nicer error state than a browser error page. API calls are never
// intercepted (live tmux state must never be cached).
// All shell URLs are relative to the SW's own location, so the app works under
// whatever path a reverse proxy mounts it at without caring where it's rooted.
// Upgrades need no VERSION bump to become visible; bump only to purge renamed or
// removed files from the cache.
const VERSION = "plane-v1";
const SHELL = [
  "./", "index.html", "app.js", "style.css",
  "manifest.webmanifest", "icon-192.png", "icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;              // sends/keys: never intercept
  if (url.pathname.includes("/api/")) return;          // live state: always network
  // Frame art is multi-MB, desktop-only, and already carries max-age. Caching it
  // here would pin megabytes per frame in the phone's storage — the one device that
  // can never display them — and nothing but a VERSION bump would ever evict it.
  if (url.pathname.includes("/frame/")) return;
  e.respondWith(
    fetch(e.request).then((res) => {
      if (res.ok && url.origin === location.origin) {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(e.request, copy));
      }
      return res;
    }).catch(() =>
      caches.match(e.request).then((hit) => hit || caches.match("./"))
    )
  );
});
