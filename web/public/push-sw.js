/* Web Push handlers, loaded into the app's service worker (see vite.config.ts: workbox.importScripts).
   A push is a tiny JSON message { title, body, url }. We always show it (a browser requires that), and tapping it opens the app at `url`. */
self.addEventListener('push', (event) => {
  let data = {}
  try { data = event.data ? event.data.json() : {} } catch (e) { data = { title: 'CargoOne', body: event.data ? event.data.text() : '' } }
  const title = data.title || 'CargoOne'
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || '',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: data.url || 'cargoone', // a newer alert for the same place replaces the older one instead of stacking
    renotify: true,
    vibrate: [200, 100, 200],
    data: { url: data.url || '/driver' },
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || '/driver'
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const c of all) {
      if ('focus' in c) { await c.focus(); if ('navigate' in c) { try { await c.navigate(url) } catch (e) { /* cross-origin or closed */ } } return }
    }
    if (self.clients.openWindow) await self.clients.openWindow(url)
  })())
})
