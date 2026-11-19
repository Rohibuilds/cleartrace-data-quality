// ClearTrace PWA Service Worker v2.3.2
// Strict Security Architecture: Shell assets cached, zero customer data caching.

const CACHE_NAME = 'cleartrace-shell-v2.3.2';

const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/static/cleartrace.css',
  '/static/app.js',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon-maskable-192.png',
  '/static/icon-maskable-512.png',
  '/static/apple-touch-icon.png',
  '/static/favicon-32.png',
  '/static/offline.html'
];

// Install: Pre-cache static shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate: Prune stale cache versions
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// Fetch: Security Boundary & Network-Only for all API routes
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 1. Critical Security Boundary: NEVER cache dynamic API responses, customer datasets, or repair operations
  if (url.pathname.startsWith('/api/')) {
    // Network-only bypass: Let browser network stack handle directly so Cloudflare Access authentication,
    // redirects, cookies, and CORS are handled cleanly without SW synthetic 503 errors.
    return;
  }

  // 2. HTML Navigation requests: Network-first with cache fallback, then offline page
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => {
          return caches.match(event.request).then((cached) => {
            return cached || caches.match('/static/offline.html') || caches.match('/');
          });
        })
    );
    return;
  }

  // 3. Static Assets: Cache-first with network fallback
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(event.request).then((response) => {
        // Cache static JS, CSS, PNG, SVG assets on the fly
        if (
          response.status === 200 &&
          (url.pathname.startsWith('/static/') || url.pathname === '/manifest.json' || url.pathname === '/favicon.ico')
        ) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      }).catch(() => {
        if (event.request.destination === 'image') {
          return caches.match('/static/icon-192.png');
        }
        return new Response('Asset unavailable offline', { status: 503, statusText: 'Offline' });
      });
    })
  );
});
