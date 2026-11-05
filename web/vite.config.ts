import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { VitePWA } from 'vite-plugin-pwa'

// lets a phone reach the dev/preview server over an HTTPS tunnel (GPS and install need HTTPS); local use only
const TUNNELS = ['.trycloudflare.com', '.ngrok-free.app', '.ngrok-free.dev', '.ngrok.app']

// The dev server proxies /api to FastAPI, so the browser never deals with CORS locally.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Installable app. The service worker caches only the app shell (screens, scripts, icons) so it opens fast and offline;
    // the API is never cached, so data is always live. Disabled in `pnpm dev` so development never serves stale pages.
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'CargoOne',
        short_name: 'CargoOne',
        description: 'Proof of delivery, trips and expenses for drivers',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        theme_color: '#0e0e10',
        background_color: '#ffffff',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        cleanupOutdatedCaches: true,
        skipWaiting: true, // a new version takes over at once, so a phone never keeps showing an old build
        clientsClaim: true,
      },
    }),
  ],
  test: { environment: 'node', setupFiles: ['fake-indexeddb/auto'], include: ['src/**/*.test.ts'] },
  preview: { port: 4173, allowedHosts: TUNNELS, proxy: { '/api': { target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') } } },
  server: {
    port: 5173,
    allowedHosts: TUNNELS,
    // allow importing ../docs/*.md?raw (the Progress page renders the roadmap)
    fs: { allow: ['..'] },
    proxy: {
      '/api': { target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
