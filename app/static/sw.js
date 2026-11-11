// Service worker mínimo: hace la app instalable y muestra una página de aviso sin internet.
// Solo se guardan archivos estáticos; las páginas con datos de la familia nunca se guardan.
const CACHE = "miyjo-v1";
const OFFLINE = new Response(
  "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>" +
  "<body style='font-family:system-ui;padding:2rem;text-align:center'><h1>Sin conexión</h1>" +
  "<p>Revisa tu internet y vuelve a intentarlo.</p><button onclick='location.reload()' " +
  "style='font-size:1.1rem;padding:.8rem 1.4rem'>Reintentar</button>",
  { headers: { "Content-Type": "text/html; charset=utf-8" } });

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(["/static/css/app.css", "/static/js/app.js"])));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(fetch(req).then((r) => { caches.open(CACHE).then((c) => c.put(req, r.clone())); return r; })
      .catch(() => caches.match(req)));
  } else if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => OFFLINE.clone()));
  }
});
