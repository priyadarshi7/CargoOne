import { defineConfig, devices } from '@playwright/test'

/** E2E runs against its OWN stack: API on :8001 with a throw-away `cargoone_e2e` database (recreated each run)
 *  and the scripted mock AI, plus a Vite dev server on :5174. Your dev servers and data are never touched. */
process.env.TZ = 'Asia/Kolkata' // the business runs on IST: the tests' clock, the browser's and the server's agree wherever this runs (a UTC runner did not)
const API_PORT = 8001
const WEB_PORT = 5174

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // tests share one database and walk the real workflow in order
  workers: 1,
  timeout: process.env.CI ? 90_000 : 30_000, // a shared CI runner is several times slower than a laptop
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: { baseURL: `http://localhost:${WEB_PORT}`, timezoneId: 'Asia/Kolkata', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'mobile-driver', testMatch: /(driver|offline)\.spec\.ts/, use: { ...devices['Pixel 7'], permissions: ['geolocation'], geolocation: { latitude: 19.8762, longitude: 75.3433 } } },
    { name: 'desktop-office', testMatch: /(auth|office|dashboard|sms|import|client|security|pin|theme|planning|tracking|expenses|setup|notifications|requests|landing|desks|review-boxes|forms|map-picker|journey|portal|invoice-client|filters|hired-link|benchmark)\.spec\.ts/, use: { ...devices['Desktop Chrome'], viewport: { width: 1360, height: 900 } } },
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
        GROQ_API_KEY: '',
        GEMINI_API_KEY: '', // never reach a real AI from tests, whatever .env says
        WHATSAPP_PROVIDER: 'mock', // never message a real phone from tests, whatever .env says
        TALLY_URL: 'http://127.0.0.1:9', // never push into a real Tally from tests (one may be open on this machine)
        WHATSAPP_TOKEN: '',
        EMAIL_PROVIDER: 'mock', // nor email a real address
        VAPID_PUBLIC_KEY: '', // nor push-alert a real phone
        VAPID_PRIVATE_KEY: '',
        SMTP_HOST: '',
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
