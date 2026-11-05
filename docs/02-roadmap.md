# CargoOne roadmap & to-do

Legend: [ ] todo · [~] in progress · [x] done. Each item = one branch/PR (`feat/…`, `fix/…`, `chore/…`, `docs/…`).
Priority: **P0** core slice (client's must-ship) · **P1** must-have depth · **P2** "wow" — the out-of-scope items, built later so the client is not disappointed.

## Phase 0 — Foundations (decide before coding)
- [x] P0 Finalise stack decisions (see `03-decisions.md`) — one at a time, with trade-offs
- [~] P0 Git workflow: branches, Conventional Commits, PR template, CI done; GitHub branch protection on `main` pending (owner setting)
- [x] P0 Monorepo layout (`web/`, `api/`), Ruff + oxlint, TypeScript strict
- [~] P0 Local dev: one-command start (Postgres in Docker done; api/web containers + `make dev` pending) (DB container, migrate, seed, web, api)
- [x] P0 CI (GitHub Actions): typecheck, lint, unit tests, build on every PR
- [x] P0 Env/config management, `.env.example`, secrets rules
- [~] P0 Docs: README (README, CLAUDE.md, ADRs done; architecture diagram + runbook pending), CLAUDE.md, ADRs, architecture diagram, runbook skeleton

## Phase 1 — Design system & app shell (P0)
- [x] Web login with role-based routing; live **Build progress** page (`/progress`) rendering this roadmap
- [x] `GET /trips` (office roles, no consignee PII) and `GET /trips/mine` (driver) endpoints
- [~] Design tokens: colour (neutral + one accent #1e40af, green/amber/red semantic) in `web/src/index.css` done; type scale, motion pending
- [~] Component kit: status badge + shells done; Button, Dialog, Toast, Empty state, Skeleton, Stepper pending
- [ ] Icon set + illustrations for driver flow (no text dependence)
- [x] i18n: English / हिन्दी / मराठी on every office screen (dashboard, trips, review, billing, import, drivers, account, link dialogs), dates and crore/lakh in the chosen language; unit test guards the dictionaries. **Wording is a first draft: needs native-speaker review.** Only the public build-progress page stays English
- [ ] Accessibility: contrast AA, 64px+ driver targets, focus states, reduced motion
- [~] Two shells: basic driver home (placeholder POD button + own trips) and office shell (header nav + trips table) done; sidebar, keyboard nav, real capture pending
- [x] Dark mode everywhere (office, driver, public pages): follows the device by default, toggle in the office header (device / light / dark), applied before first paint; own dark colour steps incl. chart ramp

## Phase 2 — Data, auth, roles (P0)
- [x] DB schema + migration 0001 + seed from client sample data (fake PII)
- [ ] Larger realistic demo dataset (≈200 trips across branches/clients/ages) for dashboard demos
- [~] Auth: office login + driver phone/PIN login with JWT done; OTP/PIN reset, token refresh, login rate-limit pending
- [~] Roles & permissions: role guard (`require_roles`) done + tested; per-branch scoping pending
- [x] Hired-driver tokenised link: trip-scoped, 72 h expiry, revocable, hashed at rest, rate-limited, audited; office creates it from the Trips table and (mock) SMS-es it in Hindi/Marathi/English. **Real SMS provider (DLT templates) pending**
- [ ] Audit log for every sensitive read/write
- [x] Trip import: CSV/XLSX upload with check-then-import (dry run report), row-numbered errors, idempotent re-import, trips with POD activity never altered, unknown vehicles/branches auto-created, unknown clients only on request; accepts the client's own sample sheet format (incl. "(hired)" vehicles). **Still manual upload: no scheduled/auto feed from Company A's system yet**
- [~] E-way bill field validation: 12 digits enforced on import; real e-way bill API lookup still pending

## Phase 3 — Driver capture (P0, the hard part)
- [x] Driver home: assigned trips, one giant "POD" button (opens the next open trip), big status icons, pending-upload counter
- [~] Camera capture via the phone's native camera (file input, `capture=environment`) done — most reliable on cheap Android; in-app camera with framing guide + torch pending
- [x] GPS + timestamp attached on capture; never blocks the driver if GPS is denied/slow (4 s)
- [x] On-device compression to <300 KB (WebP/JPEG quality ladder, then shrink, EXIF orientation applied, metadata stripped; refuses below 900 px) — unit-tested logic; **real-phone photo test pending**
- [x] Client-side quick checks on the phone before upload: blur, dark/covered lens, glare/washed-out page, blank frame -> instant spoken + icon "retake" (the driver may still "use this photo"; the server AI makes the real call). Not covered: document-edge detection, mild blur on high-resolution photos
- [~] Offline queue (IndexedDB): persisted, FIFO, idempotent, retries on reconnect + every 30 s, permanent errors isolated — done & tested; exponential backoff + Background Sync API pending
- [x] PWA: installable (manifest, icons incl. maskable, service worker caching only the app shell, auto-update, "Install" banner for drivers, iPhone hint), opens offline and keeps the driver signed in when the network is down
- [ ] PWA still to do: update prompt UI, storage-quota handling; installing needs HTTPS (a tunnel in dev, a real host in production)
- [x] Result screens usable by non-readers: green ✓ done · amber ↺ retake (with retakes left) · amber 👁 sent for checking · cloud-off saved offline
- [~] Voice prompts hi/mr/en via browser TTS + replay button done; **Hindi/Marathi wording needs native-speaker review**, recorded audio pending
- [x] Retake flow, capped at 2; then auto-routed to human review (server-enforced + DB constraint)
- [x] SMS-link capture page `/u/:token`: no login, same capture engine as the driver app (shared `CaptureFlow`), offline queue, voice, clear expired/invalid/already-done screens

## Phase 4 — AI POD verification (P0)
- [~] AI provider abstraction layer (Python): interface, registry, config-driven selection, fallback chain, latency logging done; per-provider cost + accuracy logging pending
- [~] Providers: mock + Gemini done and **verified live** (6/9 synthetic scenarios checked, 5 match expected routing, 1 differs: blurry photo -> review instead of retake; 3 hit transient 429/503 before retries were added). Claude, OpenAI, local pending
- [~] Synthetic POD generator: 9 scenarios (clean, no stamp/signature, blur, shortage, damage, wrong LR, low confidence, not-a-POD) done; hi/mr handwriting, skew/glare, bulk generation pending
- [ ] Collect 100–200 real PODs from client in pilot week 1 → real accuracy report for the MD
- [~] Extraction schema + prompt for LR no., stamp, quantity, shortage/damage remarks, date, signature, confidence done; tuning on real PODs pending
- [ ] Prompt + structured output schema + validation; Hindi/Marathi handwriting cases
- [x] Deterministic decision engine (verified / needs review / retake) — unit-tested rule table (`api/app/pod/decision.py`)
- [~] Upload endpoint `POST /trips/{id}/pod` runs AI + decision engine and returns the verdict; AI outage parks POD for review; idempotent; image access role-checked + audited. Latency target (<10 s) unmeasured until real Gemini key
- [~] Cost/latency controls: timeouts, retry on 429/5xx, provider fallback done (live latency 4-7 s per photo on free tier, 6.2 s end-to-end); image-hash caching pending
- [x] Evaluation harness (`uv run python -m app.devtools.evaluate`, see docs/06-ai-evaluation.md): synthetic labelled PODs degraded like phone photos, unsafe-error / friction / per-field accuracy / latency report, regression gate flags. Verified on the mock (100%) and by tests that a trusting reader is caught as unsafe. **Not yet run against the real model: Gemini answered HTTP 429 (quota) on 5 Nov 2026.** Still to do: run it once the quota is back, read real labelled PODs from a folder in the pilot
- [ ] Never auto-send invoices; image remains source of truth

## Phase 5 — Office workflows (P0)
- [x] Review queue: oldest-first list with reason chips; detail view with zoom/rotate image viewer, editable extracted fields (corrections stored beside AI output), approve / retake / reject (two-step), notes, keyboard shortcuts A/R/X, audit trail. Approve refused if LR ≠ trip LR or date missing; retake limited by the cap of 2
- [x] Billing queue: verified trips grouped by client and billing-cycle period (weekly Mon-Sun / fortnightly 1-15 & 16-end / monthly, in IST), oldest first, select trips, create draft invoice (one client per invoice, numbered `CO/26-27/00001` from a DB sequence, row-locked against double billing, audited)
- [x] Invoice PDF with each trip's POD photo attached as an appendix page (no consignee personal data printed). **Draft layout only: GST, company address/bank details and logo still to come**
- [~] Tally export: Sales-voucher XML + CSV done and unit-tested; **not yet imported into a real Tally** — needs Company A's ledger names / a sample voucher; GST lines, per-trip bill allocation pending
- [x] Missing-POD dashboard: trips without POD by age bucket and branch, oldest-first chase list, KPIs vs the brief's targets (24 h share, POD-to-invoice days, lost/disputed %), branch comparison, weekly trends, pipeline counts (`/office`, ops head + MD). Metrics are a pure, unit-tested module (`api/app/dashboard/metrics.py`)
- [x] Client POD view link (per trip): read-only, expiring (30 days), revocable, access log in the office dialog, no amounts/consignee data. Still pending: per-invoice link, watermark, client login portal
- [x] "Needs attention" panel (ops dashboard, billing screen; MD read-only): delivered trips with no POD, reviews waiting hours, verified-not-invoiced, expenses waiting, truck papers due; "Remind drivers" texts each driver once per trip per day through the SMS adapter (a mock today: the UI says so) and audits each send with a masked number
- [ ] Still to do: scheduled (automatic) reminders and a real SMS/WhatsApp/email provider; escalation rules

## Phase 5b — Role journeys, end to end (P0/P1)
| Role | Journey |
|---|---|
| Driver | Open app → trip → one button → photo → voice says OK/retake → done (works offline) |
| Hired driver | SMS link → photo → done (no install, no login) |
| Operations head | Missing-POD board by branch/age, chase drivers (mock SMS), reassign/escalate, import trips, resolve disputes |
| Billing executive | Review queue → fix fields → approve → billing queue by client/cycle → invoice + POD pack → Tally export |
| Managing Director | Read-only executive dashboard: working capital released (₹), POD-to-invoice days vs 18→4 target, % PODs within 24h vs 80%, lost/disputed rate vs 1.5→0.5%, ₹ at risk, branch league table, weekly digest email/PDF |
| Client (external) | Expiring link → view POD images for their trips (no login) |
- [x] `md` role with read-only executive dashboard; ROI panel uses the brief's own formula (reproduced exactly in a test: Rs 3.24 crore / Rs 38.9 lakh). MD digest PDF is downloadable from the dashboard (`/dashboard/digest.pdf`); scheduled email delivery still pending (needs an email provider)
- [ ] Ops head role distinct from billing: assignment, escalation, dispute workflow

## Phase 6 — Privacy, security, quality (P0/P1, continuous)
- [ ] DPDP Act 2023: data inventory, consent/notice text, purpose limitation, retention & auto-delete, access/erasure workflow
- [ ] Private image storage, signed short-lived URLs, no PII in logs, encryption at rest/in transit
- [ ] Input validation everywhere, rate limiting, upload type/size checks, CSRF/CORS, security headers
- [x] Unit tests (decision, compression, queue), API+DB integration tests (own `cargoone_test` DB) and **Playwright E2E (14 tests, desktop + Pixel 7 driver)**: login/roles, driver capture online + offline-then-sync, review → bill → PDF/Tally download, dashboards; runs in CI
- [~] Offline test matrix: offline capture → saved → auto-upload on reconnect covered in E2E; flaky-2G throttling and low-storage cases pending
- [ ] Performance budget for low-end Android (bundle size, LCP, memory)
- [ ] Error monitoring + structured logging (free-tier tooling)

## Fleet and driver onboarding (real-product gaps closed)
- [x] **Truck record**: registration, type, capacity, ownership (company-owned or hired from a vendor), registered owner, RC number / registration date / chassis / engine, insurance policy number, **insurance, fitness, permit and PUC validity**, and **availability** (available / in maintenance / broken down, with a note).
- [x] **Driver record**: name, phone, language, **driving licence number and expiry**, **employment type** (company / contract / hired through a vendor), **assigned truck**. Registering with an expired licence is refused.
- [x] **Papers on file**: photo or PDF of the RC, insurance, fitness, permit, PUC (truck) and licence front/back (driver), uploaded with the new record or later from **Details**; one current file per kind, replacing deletes the old file; private, role-checked.
- [x] Every field is shown on a **Details** view of the truck / driver, and in the tables (papers state, availability, licence state, assigned truck).
- [x] Planning refuses a truck that is not available or has an expired paper, and a driver whose licence has expired; the ops dashboard's needs-attention panel lists PUC and licences due within 30 days.
- [ ] Not done: reading the licence/RC photo automatically (AI), a fleet-availability calendar, and e-challan/Vahan lookups.

## Driver onboarding and notifications
- [x] **Registering a driver sends a WhatsApp message** with a one-time link: the driver opens it, chooses their own PIN, and lands signed in on the home screen with the install card. The office-read PIN stays as a backup. The link works once, expires in 72 h, is replaced when sent again, and dies the moment the driver sets a PIN.
- [x] **Assigning, re-planning or cancelling a trip** tells the driver: an in-app notification (inbox card on the driver home, refreshed every minute and when the app comes back to the front) and a WhatsApp message with trip code, LR number, route, truck, start time and a link that opens that trip. A driver who has not opened the app yet gets a fresh onboarding link in the same message.
- [x] The driver home shows the trip's details: LR number, route, truck, start, goods/weight, e-way bill, who to deliver to (with a Call button) and the LR copy as a PDF.
- [x] Real **WhatsApp Cloud API** sender (template messages in English, Hindi, Marathi) behind the same interface as a recording mock; **Setup > Messages** logs every attempt with the result (numbers masked, secrets cut out). Until the Meta credentials are added the app is honest that nothing was sent (see `docs/07-whatsapp-setup.md`).
- [x] A failing sender never blocks planning or registration; the failure is recorded and the in-app notification still arrives.
- [ ] Not done: delivery/read receipts from Meta (webhook), push notifications to a closed phone (needs Web Push keys), SMS as a second channel, per-driver opt-out.

## LR numbers and the LR document
- [x] **LR numbers are generated, never typed**: `LR/<branch code>/<financial year>/<serial>`, e.g. `LR/MH20/26-27/000123`. The serial counts per branch code and restarts each April; two people saving at the same moment cannot get the same number; a refused trip does not use one up. A typed number in the request is ignored.
- [x] **Branches** (Setup): name and LR code; changing a code never changes numbers already issued.
- [x] A trip records the goods (description, weight, packages) and the consignee; a load heavier than the truck's capacity is refused.
- [x] **LR document**: a one-page PDF generated from the trip (parties, route, vehicle, driver, goods, e-way bill, signature boxes), downloadable by ops/billing and by the trip's own driver; freight is deliberately not printed. After creating a trip the screen offers the PDF straight away.
- [x] **Signed LR scan** can be uploaded against the trip (photo or PDF) next to the generated one.
- [x] Trip import: a blank LR cell gets a generated number (new trips only); a dry run uses none.
- [ ] Not done: Devanagari text on the PDF (needs an embedded font), the client's own LR format if they insist on one, e-way bill generation through the GST portal.

## Setup area (people, trucks, clients, hired vendors)
- [x] **Setup** screen (ops head edits, billing reads): Drivers, Trucks, Clients, Hired vendors; Office staff tab for the admin only. Add / edit / deactivate; nothing is deleted, so old trips, invoices and the audit trail stay intact.
- [x] Register a driver by mobile number (10-digit, +91 / spaces accepted); a random one-time 6-digit PIN is shown once for the office to read out; the driver must choose their own at first sign-in. Duplicate numbers refused.
- [x] Deactivating a driver/truck is blocked while it is on a planned or running trip; a deactivated driver is signed out at once and is not offered in planning.
- [x] Hired trucks and drivers belong to a **vendor** (a transporter we hire from); vendor shows trucks/drivers counts; own truck vs hired is just the vendor link.
- [x] Truck details: type, capacity, insurance / fitness / permit expiry with a "valid / due in 30 days / expired" flag; registration numbers normalised (MH20AB1234 = MH-20 AB 1234).
- [x] Clients: billing cycle, Tally ledger name, contact; admin creates office staff with a temporary password that must be replaced at first sign-in.
- [ ] Still to do here: vendor rates and amounts payable to vendors, expiry reminders (digest/notification), branches screen, bulk import of drivers/trucks from a sheet, first-day setup wizard, role-specific home screens, delivering first PINs by SMS (SMS is still mocked).

## Phase 7 — "Out-of-scope" wow features (P2, after core is solid)
**Live GPS tracking**
- [x] Live tracking: driver agrees once (recorded, withdrawable); while a trip is on the road the phone sends GPS fixes (60 s / 100 m, batched, retried safely, screen kept awake); live map for ops and the MD with moving / stopped / no-signal states and stoppage + silent alerts; path per trip; client **tracking link** (position rounded to ~100 m, never the driver, stops once delivered); 30-day retention purge. English/Hindi/Marathi
- [ ] Still to do here: background tracking (a browser PWA only tracks while the app is open and the screen is on - a native wrapper is needed for true background), ETA and geofenced arrival (needs destination coordinates / geocoding), route-deviation alerts, scheduled purge job in deployment
**Trip planning**
- [x] Trip lifecycle (planned / on the road / delivered / cancelled; a POD photo marks delivered), trip creation by ops with generated trip codes, vehicle + driver assignment for a time window, **clash detection** (vehicle and driver double-booking, explicit "book anyway"), 15-day planning board per vehicle, driver "Start trip" button, cancel, audit trail, English/Hindi/Marathi
- [ ] Still to do here: orders before trips, load/vehicle matching, backhaul suggestions, drag-and-drop on the board, hired-vehicle vendor management
**Fuel & driver expenses**
- [x] Driver expenses: icon-first phone screen (diesel, toll, repair, loading, food, fine, other), amount + optional bill photo (compressed, <300 KB), diesel needs litres + odometer; saved once even if retried; office review queue with receipt viewer, approve / reject with a reason the driver sees
- [x] Fuel economy: km per litre between fills, per truck; flags for odometer going backwards, implausible mileage or litres, and mileage far below the truck's own usual (checked the moment a fill arrives and reported per truck)
- [x] Advances and settlement per driver (advances minus approved expenses), trip profit (freight minus approved costs, pending shown apart, warning when many trips have no costs yet), where-the-money-went by category. English/Hindi/Marathi
- [ ] Still to do here: reading the amount/litres from the bill photo with the AI layer (the driver types it today), offline expense queue (needs a connection today), payroll-style trip settlement/closing, per-client profitability
**Platform polish**
- [ ] Rule/automation builder, e-way bill API integration, GST e-invoice, direct Tally connector, multi-tenant for other transporters, analytics/BI export, mobile wrapper (Capacitor) if needed

## Phase 8 — Release (later, per your note)
- [ ] Deployment (free tiers), environments, backups, domain/SSL, UAT with client data, pilot rollout plan, training material (Hindi/Marathi), handover docs

## Suggested milestones (6-week core build)
| Week | Outcome |
|---|---|
| 1 | Phases 0–1 + schema/auth; clickable shell |
| 2 | Driver capture + offline queue + compression |
| 3 | AI check + decision engine + retake flow + voice |
| 4 | Review queue + billing queue + Tally export |
| 5 | Dashboard, client link, import, privacy/security hardening |
| 6 | Tests, polish, demo data, docs; then Phase 7 begins |
