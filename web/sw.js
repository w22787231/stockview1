// StockView Service Worker — PWA 離線快取
// 策略:
//  - 導覽(HTML)：network-first → 失敗用快取(離線可開上次版本)
//  - 同源靜態(icon/manifest/json/css/js)：stale-while-revalidate(秒開、背景更新)
//  - echarts CDN：cache-first(離線圖表可用)
//  - /api/*：network-only(永遠抓即時報價,失敗才回快取)
const VERSION = "sv-v1";
const SHELL = "shell-" + VERSION;
const STATIC = "static-" + VERSION;
const SHELL_URLS = ["/", "/index.html", "/manifest.json",
  "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_URLS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !k.endsWith(VERSION)).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function networkFirst(req, cacheName) {
  return fetch(req).then((res) => {
    if (res && res.ok) { const cp = res.clone(); caches.open(cacheName).then((c) => c.put(req, cp)); }
    return res;
  }).catch(() => caches.match(req).then((r) => r || caches.match("/index.html")));
}

function staleWhileRevalidate(req, cacheName) {
  return caches.open(cacheName).then((c) =>
    c.match(req).then((cached) => {
      const net = fetch(req).then((res) => { if (res && res.ok) c.put(req, res.clone()); return res; }).catch(() => cached);
      return cached || net;
    })
  );
}

function cacheFirst(req, cacheName) {
  return caches.open(cacheName).then((c) =>
    c.match(req).then((cached) => cached || fetch(req).then((res) => { if (res && (res.ok || res.type === "opaque")) c.put(req, res.clone()); return res; }))
  );
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // 即時 API:永遠走網路,失敗才回快取(可能沒有)
  if (url.origin === location.origin && url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(req).catch(() => caches.match(req)));
    return;
  }
  // echarts 等跨域 CDN:cache-first
  if (url.origin !== location.origin) {
    e.respondWith(cacheFirst(req, STATIC));
    return;
  }
  // 導覽(開 App / 重整):network-first
  if (req.mode === "navigate") {
    e.respondWith(networkFirst(req, SHELL));
    return;
  }
  // 同源靜態與資料 JSON:stale-while-revalidate
  e.respondWith(staleWhileRevalidate(req, STATIC));
});

// ── Web Push:收盤後伺服器偵測到自訂股池金叉 → 推播通知(App 關著也會跳)──
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { body: e.data ? e.data.text() : "" }; }
  const title = d.title || "股觀觀股 · 金叉提醒";
  const opts = {
    body: d.body || "你的自訂股池出現黃金交叉",
    icon: "/icon-192.png", badge: "/icon-192.png",
    tag: d.tag || "golden-cross", renotify: true,
    data: { url: d.url || "/?src=push#cross" },
  };
  e.waitUntil(self.registration.showNotification(title, opts));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) => {
      for (const c of cs) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
      return self.clients.openWindow(url);
    })
  );
});
