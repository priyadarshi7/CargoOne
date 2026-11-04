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
- [ ] Client-side quick checks: blur, brightness, document edges → instant "retake" before upload
- [~] Offline queue (IndexedDB): persisted, FIFO, idempotent, retries on reconnect + every 30 s, permanent errors isolated — done & tested; exponential backoff + Background Sync API pending
- [ ] PWA: installable, service worker, offline shell, update prompt, storage-quota handling
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
- [ ] Evaluation harness: labelled POD image set, accuracy/recall report, regression gate
- [ ] Never auto-send invoices; image remains source of truth

## Phase 5 — Office workflows (P0)
- [x] Review queue: oldest-first list with reason chips; detail view with zoom/rotate image viewer, editable extracted fields (corrections stored beside AI output), approve / retake / reject (two-step), notes, keyboard shortcuts A/R/X, audit trail. Approve refused if LR ≠ trip LR or date missing; retake limited by the cap of 2
- [x] Billing queue: verified trips grouped by client and billing-cycle period (weekly Mon-Sun / fortnightly 1-15 & 16-end / monthly, in IST), oldest first, select trips, create draft invoice (one client per invoice, numbered `CO/26-27/00001` from a DB sequence, row-locked against double billing, audited)
- [x] Invoice PDF with each trip's POD photo attached as an appendix page (no consignee personal data printed). **Draft layout only: GST, company address/bank details and logo still to come**
- [~] Tally export: Sales-voucher XML + CSV done and unit-tested; **not yet imported into a real Tally** — needs Company A's ledger names / a sample voucher; GST lines, per-trip bill allocation pending
- [x] Missing-POD dashboard: trips without POD by age bucket and branch, oldest-first chase list, KPIs vs the brief's targets (24 h share, POD-to-invoice days, lost/disputed %), branch comparison, weekly trends, pipeline counts (`/office`, ops head + MD). Metrics are a pure, unit-tested module (`api/app/dashboard/metrics.py`)
- [x] Client POD view link (per trip): read-only, expiring (30 days), revocable, access log in the office dialog, no amounts/consignee data. Still pending: per-invoice link, watermark, client login portal
- [ ] Notifications (mock SMS/WhatsApp/email adapters): reminders to drivers, alerts to ops on aged missing PODs

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

## Phase 7 — "Out-of-scope" wow features (P2, after core is solid)
**Live GPS tracking**
- [ ] Trip tracking via driver PWA location pings (battery-aware), live map for ops, geofenced delivery arrival (auto-prompt POD at consignee gate), ETA, route deviation & stoppage alerts, share-tracking link for clients
**Trip planning**
- [ ] Order → trip creation, own vs hired vehicle allocation, driver assignment, load/vehicle matching, backhaul suggestions, planning board (drag-drop), hired-vehicle vendor management
**Fuel & driver expenses**
- [ ] Driver expense capture by photo (fuel, toll, repairs) with the same AI extraction, advances & settlement, trip P&L, fuel mileage anomaly flags, per-trip profitability dashboard
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
