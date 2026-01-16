const CACHE = 'wrf-v1';
const ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/favicon.ico',
  // añade aquí tus HTML de mapas si quieres
  '/precipitacion.html',
  '/precipitacionacumulada.html',
  '/precipitacionacumulada24h.html',
  '/temperatura.html',
  '/viento.html',
  '/humedadrelativa.html',
  '/saffirsimpson.html'
];

self.addEventListener('install', event =>
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(ASSETS))
  )
);

self.addEventListener('fetch', event =>
  event.respondWith(
    caches.match(event.request).then(resp => resp || fetch(event.request))
  )
);

