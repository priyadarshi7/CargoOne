import { defineConfig, devices } from '@playwright/test'

/** E2E runs against its OWN stack: API on :8001 with a throw-away `cargoone_e2e` database (recreated each run)
 *  and the scripted mock AI, plus a Vite dev server on :5174. Your dev servers and data are never touched. */
const API_PORT = 8001
const WEB_PORT = 5174

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // tests share one database and walk the real workflow in order
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: { baseURL: `http://localhost:${WEB_PORT}`, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'mobile-driver', testMatch: /driver\.spec\.ts/, use: { ...devices['Pixel 7'], permissions: ['geolocation'], geolocation: { latitude: 19.8762, longitude: 75.3433 } } },
    { name: 'desktop-office', testMatch: /(auth|office|dashboard|sms|import|client|security|pin|theme|planning|tracking|expenses|setup|notifications|requests)\.spec\.ts/, use: { ...devices['Desktop Chrome'], viewport: { width: 1360, height: 900 } } },
  ],
  webServer: [
    {
      command: `uv run python -m app.devtools.e2e_prepare && uv run uvicorn app.main:app --port ${API_PORT}`,
      cwd: '../api',
      url: `http://localhost:${API_PORT}/health`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: {
        DATABASE_URL: process.env.E2E_DATABASE_URL ?? 'postgresql+asyncpg://cargoone:cargoone@localhost:5432/cargoone_e2e',
        APP_ENV: 'dev',
        AI_PROVIDER: 'mock',
        MOCK_SCENARIO: 'clean',
        AI_FALLBACKS: '',
        GEMINI_API_KEY: '', // never reach a real AI from tests, whatever .env says
        WHATSAPP_PROVIDER: 'mock', // never message a real phone from tests, whatever .env says
        WHATSAPP_TOKEN: '',
        STORAGE_DIR: './storage_e2e',
        WEB_ORIGIN: `http://localhost:${WEB_PORT}`,
      },
    },
    {
      command: `pnpm exec vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      env: { VITE_PROXY_TARGET: `http://localhost:${API_PORT}` },
    },
  ],
})
