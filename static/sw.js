const CACHE_NAME = 'mealie-importer-v1';
const ASSETS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Solo cachear peticiones GET a recursos estáticos
  if (event.request.method === 'GET' && event.request.url.includes('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
  }
});
