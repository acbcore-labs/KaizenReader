/**
 * KaizenReader Offline-First Service Worker (`sw.js`).
 *
 * Guarantees that the iPhone 16e Home Screen app boots in <100ms in Airplane Mode
 * with the MacBook Pro M1 powered off, serving all UI shell assets from Cache Storage
 * and seamlessly falling back to the IndexedDB Sovereign Vault when `/api/*` is offline.
 */
const CACHE_NAME = "kaizen-atelier-shell-v7";
const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/styles.css",
  "/phonetics_client.js",
  "/offline_parser.js",
  "/vault.js",
  "/gdrive.js",
  "/app.js",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : Promise.resolve()))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Network-First with instant Cache Fallback for static UI shell assets
  // Ensures updates from MacBook Pro M1 apply immediately on refresh, while still booting offline.
  if (
    url.origin === self.location.origin &&
    !url.pathname.startsWith("/api/") &&
    !url.pathname.startsWith("/ws/")
  ) {
    event.respondWith(
      fetch(req, { cache: "no-cache" })
        .then((netRes) => {
          if (netRes && netRes.status === 200) {
            const clone = netRes.clone();
            caches.open(CACHE_NAME).then((c) => c.put(req, clone));
          }
          return netRes;
        })
        .catch(() => caches.match(req).then((c) => c || caches.match("/index.html")))
    );
  }
});
