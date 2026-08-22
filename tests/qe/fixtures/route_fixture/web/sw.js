// A declared client that calls no route. It is not literal-free: it names the api
// namespace in order to exclude it from its cache, exactly as the real service worker
// does, so the bare namespace prefix is found and then discarded rather than absent.
//
// It is an element of the measured system regardless. Membership follows the
// declaration, not the finding: a predicate of "the matcher found literals" cannot
// distinguish a file that issues no requests from one whose requests the matcher could
// not see, and those two have opposite meanings under a metric whose denominator is the
// element count.

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.includes("/api/")) return;
  e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request)));
});
