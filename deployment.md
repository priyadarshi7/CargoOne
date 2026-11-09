# CargoOne: deployment.md

- **GitHub:** https://github.com/priyadarshi7/CargoOne
- **Live app:** none. CargoOne is **not deployed to a public host**. It runs locally in a few minutes (section 1) and is tested in CI on every push. Section 6 describes the deployment shape I would use and what is and is not proven about it.
- **Design document:** `CargoOne-TDD.pdf` / `CargoOne-TDD.docx` (in the same ZIP; also in `docs/`).

---

## 1. Run it locally

### What you need
| Tool | Version | Why |
|---|---|---|
| Docker Desktop | any recent | runs PostgreSQL 16 |
| Python | 3.12 or newer | the API |
| [uv](https://docs.astral.sh/uv/) | any recent | installs the API's packages |
| Node.js | 22 or newer | the web app |
| pnpm | any recent | the web app's packages |
| Ollama (optional) | any recent | the local AI reader; the app works without it |

### Step by step
```bash
git clone https://github.com/priyadarshi7/CargoOne.git
cd CargoOne

# 1. settings: the defaults are enough to run (mock AI, simulated SMS / WhatsApp / email)
cp .env.example .env

# 2. database
docker compose up -d db

# 3. API: packages, tables, sample data, server        -> http://localhost:8000/docs
cd api
uv sync
uv run alembic upgrade head
uv run python -m app.seed              # branches, the brief's 3 sample trips, demo logins
uv run python -m app.seed_fleet        # 8 own + 8 hired trucks, 6 vendors, 12 drivers, 5 clients, staff
uv run python -m app.demo_data         # about 140 trips over 75 days with photos, invoices and payments
uv run python -m app.devtools.demo_video   # 3 trips ready for trying the driver flow (add --reset to use them again)
uv run uvicorn app.main:app --reload

# 4. web app, in a second terminal                      -> http://localhost:5173
cd web
pnpm install
pnpm dev
```
The seed scripts refuse to run unless `APP_ENV` is `dev` or `test` (the default is `dev`). They are safe to run again. `uv run python -m app.demo_data --remove` removes the demo trips; `uv run python -m app.seed_fleet --wipe` clears the fleet.

### One command instead of steps 2 to 4 (recommended on Windows)
```bash
cd web
pnpm dev:all          # same as: node ../scripts/dev.mjs
```
It starts Docker and Postgres, runs the migrations, starts Ollama if installed, the API (restarts when `.env` changes) and the web app, and clears stale processes first. Ctrl+C stops everything it started. `pnpm dev:all:phone` also prints a phone link through a Cloudflare quick tunnel, which is how to try the driver app on a real phone (camera, GPS and install need HTTPS).

### Check it works
- http://localhost:8000/health returns `{"status":"ok"}`.
- http://localhost:5173 shows the landing page; sign in with a login below.
- http://localhost:5173/progress shows build progress with no login.

---

## 2. Demo logins (development only: fake data)

| Role | Sign in with | Secret | Where it lands |
|---|---|---|---|
| Operations head | `ops@cargoone.dev` | `cargoone-dev` | Today, Trips, Planning, Requests, Setup, Live map |
| Billing executive | `billing@cargoone.dev` | `cargoone-dev` | Review queue, Billing, Invoices |
| Managing Director | `md@cargoone.dev` | `cargoone-dev` | Performance dashboard, AI benchmark, Privacy requests |
| Admin | `admin@cargoone.dev` | `cargoone-dev` | Everything, including staff accounts |
| Driver (company) | phone `9000000001` | PIN `1234` | The driver app (use a phone-sized window) |
| Client | created by you: **Setup, Clients, Logins** (shows a one-time link) | you choose | `/portal`, the client's own shipments |
| Hired driver | **Trips, Send link** shows a one-trip link (SMS is simulated, so the link is on screen) | none | the capture page |
| Receiver | the `/s/...` link on a trip | none | shipment page with the delivery code |

These passwords exist only because the seed script creates them in a development database. Nothing in the repository holds a real credential.

---

## 3. A ten-minute tour for the reviewer

1. **Driver:** open a phone-sized window, sign in as `9000000001` / `1234`. One big button. Switch the language (EN, हि, म) on the result screen.
2. **Capture:** `python -m app.devtools.demo_video` created three trips for this driver. Their LR numbers match printed sheets in `docs/benchmark/photos`:
   - `S01_flat.jpeg` for trip TRP-70991 gives **verified**.
   - `S02.jpeg` for TRP-70992 (no stamp) gives a **retake** with a spoken prompt.
   - `S06.jpeg` for TRP-70993 (44 bags, remark "Short 6 bags") goes to the **review queue**.
   With `AI_PROVIDER=mock` the answers are scripted; with `groq` or `local` (section 4) a real model reads the photo.
3. **Offline:** in the browser's developer tools set Network to Offline, take a photo, go back online. It sends by itself, once.
4. **Review:** sign in as billing, open **Review**. The photo is on the left with what the AI found drawn on it; the fields on the right can be corrected. Approve, retake or reject (keys A, R, X).
5. **Billing:** **Billing**, pick verified trips, create an invoice, download the PDF (the POD photo of every trip is attached) or the Tally XML.
6. **Dashboard:** sign in as MD, **Performance**: 24-hour rate, POD-to-invoice days, lost rate, by branch, against the brief's targets.
7. **Client request:** open `/request` signed out, send a request. Sign in as ops, **Requests**: accept with a quote; the requester accepts on their status link; **Book a trip**.
8. **AI benchmark:** **AI benchmark** shows every model run on the 28 photos, expected against actual.

The numbers on every screen are calculated from simulated trips. They demonstrate the screens; they are not a result (see the design document, sections 9 and 16).

---

## 4. The AI reader

The AI only reads the photo; fixed rules in `api/app/pod/decision.py` decide.

| `AI_PROVIDER` | Reader | Needs |
|---|---|---|
| `mock` (default) | scripted answers | nothing |
| `groq` | Qwen3.8 27B on Groq (the main reader) | `GROQ_API_KEY`, and `CLOUD_AI_CONFIRMED=true` outside development |
| `local` | Qwen3-VL 4B + glm-ocr through Ollama, no cloud | Ollama running; see `docs/09-local-ai-setup.md` |
| `gemini` | Gemini 2.5 Flash | `GEMINI_API_KEY` |

Recommended: `AI_PROVIDER=groq` with `AI_FALLBACKS=local`. Tests always force the mock. For the local reader: `ollama pull qwen3-vl:4b` and `ollama pull glm-ocr`.

---

## 5. Outside systems (all optional)

Every one has a **simulated mode** that is the default: nothing leaves the machine, the screen says so, and the app never pretends to send. Setup guides:

| System | Guide | Without it |
|---|---|---|
| Twilio SMS | `docs/14-sms-setup.md` | the private link is shown on screen to copy |
| WhatsApp (Meta Cloud API) | `docs/07-whatsapp-setup.md` | messages are logged as "Not sent" in **Setup, Messages** |
| Email (SMTP) | `docs/08-email-setup.md` | the one-time link is shown on screen |
| Tally Prime | `docs/13-tally-setup.md` | download the XML instead |
| Razorpay | `docs/12-razorpay-setup.md` | the Pay online button is hidden; billing records payments by hand |
| Google Maps | `docs/10-google-maps-setup.md` | free OpenStreetMap search is used |
| Web Push | set `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | no phone alerts; the in-app badge still works |

For a Tally demo: Tally Prime open with a company loaded, **F1 Help, Settings, Connectivity** on port 9000. Tally's Educational mode accepts only the 1st, 2nd and last day of a month as a voucher date.

---

## 6. How it would be deployed

**Honest status:** I have not deployed CargoOne to a public host. CI builds it and runs the tests against a real Postgres on every push, but no hosted environment exists, so the steps below are the intended shape, not something I have run in production.

```
Browser / phone
    | HTTPS
Reverse proxy (nginx or Caddy)
    |-- /      -> static files from web/dist        (the built web app)
    |-- /api/  -> http://127.0.0.1:8000/            (strip the /api prefix; allow WebSocket upgrade)
                      FastAPI, ONE worker
                      |-- PostgreSQL 16 (managed or a container, with backups)
                      |-- STORAGE_DIR on a persistent volume (POD photos, papers)
```

1. **Build the web app:** `cd web && pnpm install && pnpm build`. Serve `web/dist` as static files. The app calls the API at `/api` by default (override with `VITE_API_URL`).
2. **Run the API:** `cd api && uv sync --frozen && uv run alembic upgrade head && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`.
3. **One worker only.** Live updates and the rate limiter are held in the API's memory. More than one worker or instance needs Redis (or Postgres LISTEN / NOTIFY) first; this is a known limit.
4. **HTTPS is required.** The phone app's install, camera and GPS only work over HTTPS.
5. **Settings for a non-development environment:** `APP_ENV=production`, a unique `JWT_SECRET` of at least 32 characters (the API refuses to start otherwise), `WEB_ORIGIN` set to the public address, `APP_BASE_URL` set to the same, `STORAGE_DIR` on persistent storage. The seed scripts refuse to run outside `dev` and `test`, so a production database starts empty and the owner creates the first admin deliberately.
6. **Privacy settings:** set `GRIEVANCE_OFFICER` and `GRIEVANCE_EMAIL` before real data. The daily retention job runs inside the API (`RETENTION_JOB`). Cloud AI stays off until `CLOUD_AI_CONFIRMED=true`.
7. **Tally is the exception.** A hosted API cannot reach a Tally Prime on someone's desk. Use the XML download, or a small connector next to Tally (not built).
8. **Backups:** back up the database and `STORAGE_DIR` together; photos and rows must match.

---

## 7. Environment variables (names only)

Copy `.env.example` to `.env` at the repository root (a second `api/.env`, if present, overrides it). `.env` is git-ignored. Never put values in a chat, a commit or an issue.

**Core**
`DATABASE_URL` · `APP_ENV` · `JWT_SECRET` · `WEB_ORIGIN` · `APP_BASE_URL` · `STORAGE_DIR` · `COMPANY_NAME` · `OFFICE_PHONE` · `INVOICE_PREFIX` · `DEFAULT_BRANCH_CODE` · `DEFAULT_ORIGIN`

**AI reader**
`AI_PROVIDER` · `AI_FALLBACKS` · `AI_TIMEOUT_S` · `AI_CONFIDENCE_THRESHOLD` · `GROQ_API_KEY` · `GROQ_MODEL` · `GROQ_URL` · `GEMINI_API_KEY` · `GEMINI_MODEL` · `OLLAMA_URL` · `OLLAMA_MODEL` · `OLLAMA_OCR_MODEL` · `LOCAL_AI_TIMEOUT_S` · `OCR_ENGINE` · `OCR_MODELS` · `OCR_LANGS` · `CLOUD_AI_CONFIRMED` · `MOCK_SCENARIO` · `BENCHMARK_DIR`

**POD rules and targets**
`MAX_IMAGE_BYTES` · `MAX_RETAKES` · `POD_REQUIRE_QUANTITY` · `POD_MAX_DISTANCE_KM` · `BASELINE_POD_TO_INVOICE_DAYS` · `TARGET_POD_TO_INVOICE_DAYS` · `TARGET_POD_WITHIN_24H_PCT` · `BASELINE_LOST_PCT` · `TARGET_LOST_PCT` · `INTEREST_RATE`

**Trips, tracking and links**
`UPLOAD_LINK_TTL_HOURS` · `CLIENT_LINK_TTL_DAYS` · `ONBOARDING_LINK_TTL_HOURS` · `TRACK_STALE_MIN` · `TRACK_STOPPED_MIN` · `TRACK_LINK_TTL_HOURS` · `ETA_SPEED_KMH` · `ETA_ROAD_FACTOR` · `LATE_GRACE_MIN` · `START_EARLY_HOURS` · `LOGIN_MAX_FAILURES` · `LOGIN_LOCK_MINUTES`

**Privacy (DPDP)**
`GRIEVANCE_OFFICER` · `GRIEVANCE_EMAIL` · `RETENTION_YEARS` · `REQUEST_RETENTION_DAYS` · `TRACKING_RETENTION_DAYS` · `PRIVACY_REPLY_DAYS` · `RETENTION_JOB`

**Places and maps**
`PLACES_PROVIDER` · `GOOGLE_MAPS_SERVER_KEY` · `GOOGLE_MAPS_BROWSER_KEY`

**SMS (Twilio)**
`SMS_PROVIDER` · `TWILIO_ACCOUNT_SID` · `TWILIO_AUTH_TOKEN` · `TWILIO_FROM` · `TWILIO_MESSAGING_SERVICE_SID` · `SMS_MAX_TOTAL`

**WhatsApp (Meta Cloud API)**
`WHATSAPP_PROVIDER` · `WHATSAPP_TOKEN` · `WHATSAPP_PHONE_NUMBER_ID` · `WHATSAPP_API_VERSION` · `WHATSAPP_TEMPLATE_PREFIX` · `WHATSAPP_TEMPLATE_WELCOME` · `WHATSAPP_TEMPLATE_TRIP_ASSIGNED` · `WHATSAPP_TEMPLATE_TRIP_UPDATE` · `WHATSAPP_TEMPLATE_REQUEST_RECEIVED` · `WHATSAPP_TEMPLATE_REQUEST_UPDATE` · `WHATSAPP_TEMPLATE_SHIPMENT_UPDATE` (each also with a `_HI` and `_MR` form)

**Email**
`EMAIL_PROVIDER` · `SMTP_HOST` · `SMTP_PORT` · `SMTP_SECURITY` · `SMTP_USER` · `SMTP_PASSWORD` · `EMAIL_FROM`

**Web Push**
`VAPID_PUBLIC_KEY` · `VAPID_PRIVATE_KEY` · `VAPID_SUBJECT`

**Tally Prime**
`TALLY_URL` · `TALLY_COMPANY` · `TALLY_SALES_LEDGER`

**Razorpay**
`RAZORPAY_KEY_ID` · `RAZORPAY_KEY_SECRET` · `RAZORPAY_WEBHOOK_SECRET`

**Web app (build time only)**
`VITE_API_URL` · `VITE_PROXY_TARGET`

---

## 8. Tests

```bash
cd api && uv run ruff check . && uv run pytest -q          # 478 tests; needs the migrated Postgres from step 2
cd web && pnpm exec tsc -b && pnpm test                    # type check and 49 unit tests
cd web && pnpm exec playwright install chromium && pnpm e2e   # browser tests, including a phone-sized driver project
```
The browser tests start their own API (port 8001), web app (port 5174) and a throw-away `cargoone_e2e` database, so your development data is never touched. GitHub Actions runs the same three jobs on every push.

---

## 9. If something does not work

| You see | Likely cause |
|---|---|
| The web app loads but every call fails | The API is not running or not migrated (`uv run alembic upgrade head`); check http://localhost:8000/health |
| "I changed the code and nothing changed" | An old API process is still running; `pnpm dev:all` clears stale ones first |
| Seed says "development only" | `APP_ENV` is not `dev` or `test` |
| The review screen shows no labels on the photo | First open of a POD places them and takes a few seconds; the local text reader needs `uv sync` to have run |
| Push to Tally fails | Tally is not open, Connectivity is off, the port is not 9000, or the voucher date is outside the company's financial period |
| Camera, GPS or install does not work on a phone | Needs HTTPS; use `pnpm dev:all:phone` |
| "Not sent" in Messages | The provider is in simulated mode (section 5) |
