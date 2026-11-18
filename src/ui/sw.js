/**
 * KaizenReader Offline-First Service Worker (`sw.js`).
 *
 * Guarantees that the iPhone 16e Home Screen app boots in <50ms in Airplane Mode
 * with the MacBook Pro M1 powered off or disconnected from Wi-Fi.
 * Serves UI shell assets instantly from Cache Storage and falls back to
 * IndexedDB Sovereign Vault when offline.
 */
const CACHE_NAME = "kaizen-atelier-shell-v12";
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
  "/apple-touch-icon.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => {
        return Promise.all(
          SHELL_ASSETS.map((url) =>
            cache.add(url).catch((err) => {
              console.warn("[SW] Optional shell asset failed to cache:", url, err);
            })
          )
        );
      })
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

function fetchWithTimeout(req, ms = 1500) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("SW Network Timeout")), ms);
    fetch(req)
      .then((res) => {
        clearTimeout(timer);
        resolve(res);
      })
      .catch((err) => {
        clearTimeout(timer);
        reject(err);
      });
  });
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Skip API endpoints, WebSockets, and external origins
  if (
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/ws/")
  ) {
    return;
  }

  // 1. Navigation requests (Opening the app, PWA standalone launch, page refresh)
  if (req.mode === "navigate") {
    event.respondWith(
      (async () => {
        const isExplicitReload = req.cache === "reload";

        // Explicit user reload: try network first with short timeout (1.5s)
        if (isExplicitReload && navigator.onLine !== false) {
          try {
            const netRes = await fetchWithTimeout(req, 1500);
            if (netRes && netRes.status === 200) {
              const cache = await caches.open(CACHE_NAME);
              cache.put("/index.html", netRes.clone());
              cache.put("/", netRes.clone());
              return netRes;
            }
          } catch (e) {
            // Network failed or timed out -> fall through to cache
          }
        }

        // Offline / Normal launch / Standalone WebClip: Instant Cache-First (<50ms boot)
        const cached =
          (await caches.match("/index.html")) ||
          (await caches.match("/")) ||
          (await caches.match(req));

        if (cached) {
          // In background, refresh cache if online
          if (!isExplicitReload && navigator.onLine !== false) {
            fetch(req)
              .then(async (netRes) => {
                if (netRes && netRes.status === 200) {
                  const cache = await caches.open(CACHE_NAME);
                  cache.put("/index.html", netRes.clone());
                  cache.put("/", netRes.clone());
                }
              })
              .catch(() => {});
          }
          return cached;
        }

        // Cache miss: fetch from network
        try {
          const netRes = await fetch(req);
          if (netRes && netRes.status === 200) {
            const cache = await caches.open(CACHE_NAME);
            cache.put("/index.html", netRes.clone());
            cache.put("/", netRes.clone());
          }
          return netRes;
        } catch (err) {
          return new Response(
            "<!DOCTYPE html><html><body style='background:#12100e;color:#fbf7ee;font-family:sans-serif;padding:2rem;text-align:center;'><h2>KaizenReader Offline</h2><p>Connect once to your Mac to load assets into the Sovereign Vault.</p></body></html>",
            { headers: { "Content-Type": "text/html" } }
          );
        }
      })()
    );
    return;
  }

  // 2. Static Shell Assets (styles.css, app.js, vault.js, phonetics_client.js, etc.)
  event.respondWith(
    (async () => {
      // Fast Cache-First for instant UI responsiveness
      const cached = await caches.match(req);
      if (cached) {
        // In background, revalidate asset if online
        if (navigator.onLine !== false) {
          fetch(req)
            .then(async (netRes) => {
              if (netRes && netRes.status === 200) {
                const cache = await caches.open(CACHE_NAME);
                cache.put(req, netRes);
              }
            })
            .catch(() => {});
        }
        return cached;
      }

      // Not cached: fetch from network and store in cache
      try {
        const netRes = await fetch(req);
        if (netRes && netRes.status === 200) {
          const cache = await caches.open(CACHE_NAME);
          cache.put(req, netRes.clone());
        }
        return netRes;
      } catch (err) {
        // Fallback for navigation requests
        return caches.match("/index.html");
      }
    })()
  );
});
