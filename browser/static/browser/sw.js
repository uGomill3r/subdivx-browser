// Service Worker mínimo — solo necesario para que Safari iOS reconozca la app como PWA
const CACHE_NAME = "subdivx-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(clients.claim());
});

// Sin interceptar fetch — la app funciona normalmente sin caché offline
