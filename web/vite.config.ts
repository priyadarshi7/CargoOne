import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The dev server proxies /api to FastAPI, so the browser never deals with CORS locally.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: { environment: 'node', setupFiles: ['fake-indexeddb/auto'] },
  server: {
    port: 5173,
    // allow importing ../docs/*.md?raw (the Progress page renders the roadmap)
    fs: { allow: ['..'] },
    proxy: {
      '/api': { target: 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
