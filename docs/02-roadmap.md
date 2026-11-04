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
- [ ] i18n framework: English / हिंदी / मराठी, language switch, number/date/₹ formatting (Indian grouping)
- [ ] Accessibility: contrast AA, 64px+ driver targets, focus states, reduced motion
- [~] Two shells: basic driver home (placeholder POD button + own trips) and office shell (header nav + trips table) done; sidebar, keyboard nav, real capture pending
- [ ] Dark mode for office shell (optional)

## Phase 2 — Data, auth, roles (P0)
- [x] DB schema + migration 0001 + seed from client sample data (fake PII)
- [ ] Larger realistic demo dataset (≈200 trips across branches/clients/ages) for dashboard demos
- [~] Auth: office login + driver phone/PIN login with JWT done; OTP/PIN reset, token refresh, login rate-limit pending
- [~] Roles & permissions: role guard (`require_roles`) done + tested; per-branch scoping pending
- [ ] Hired-driver tokenised SMS link (trip-scoped, expiring, revocable, rate-limited)
- [ ] Audit log for every sensitive read/write
- [ ] Trip import: CSV/XLSX daily upload with LR + e-way bill, validation, dedupe, error report
- [ ] E-way bill field validation (12 digits) + mock lookup adapter

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
- [ ] SMS-link capture page (no login, same capture engine, lighter shell)

## Phase 4 — AI POD verification (P0)
- [~] AI provider abstraction layer (Python): interface, registry, config-driven selection, fallback chain, latency logging done; per-provider cost + accuracy logging pending
- [~] Providers: mock + Gemini done (Gemini tested against a fake HTTP transport only — **needs a real key + real/synthetic image run**); Claude, OpenAI, local pending
- [~] Synthetic POD generator: 9 scenarios (clean, no stamp/signature, blur, shortage, damage, wrong LR, low confidence, not-a-POD) done; hi/mr handwriting, skew/glare, bulk generation pending
- [ ] Collect 100–200 real PODs from client in pilot week 1 → real accuracy report for the MD
- [~] Extraction schema + prompt for LR no., stamp, quantity, shortage/damage remarks, date, signature, confidence done; tuning on real PODs pending
- [ ] Prompt + structured output schema + validation; Hindi/Marathi handwriting cases
- [x] Deterministic decision engine (verified / needs review / retake) — unit-tested rule table (`api/app/pod/decision.py`)
- [~] Upload endpoint `POST /trips/{id}/pod` runs AI + decision engine and returns the verdict; AI outage parks POD for review; idempotent; image access role-checked + audited. Latency target (<10 s) unmeasured until real Gemini key
- [ ] Cost/latency controls: timeouts, retries, caching by image hash, provider fallback
- [ ] Evaluation harness: labelled POD image set, accuracy/recall report, regression gate
- [ ] Never auto-send invoices; image remains source of truth

## Phase 5 — Office workflows (P0)
- [x] Review queue: oldest-first list with reason chips; detail view with zoom/rotate image viewer, editable extracted fields (corrections stored beside AI output), approve / retake / reject (two-step), notes, keyboard shortcuts A/R/X, audit trail. Approve refused if LR ≠ trip LR or date missing; retake limited by the cap of 2
- [ ] Billing queue: verified trips grouped by client & billing cycle, select → create invoice batch
- [ ] Invoice generation (PDF) with POD images attached (as appendix, merged PDF)
- [ ] Tally export: Tally Prime XML vouchers + CSV, ledger mapping, re-export safe
- [ ] Missing-POD dashboard: trips without POD by age bucket/branch/client, POD-to-invoice days, KPIs vs targets (24h, 18→4 days, 1.5→0.5%)
- [ ] Client portal link: read-only POD view per trip/invoice, expiring, watermark, access log
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
- [ ] Add `md` (executive, read-only) role; ROI panel computes savings from live data using the brief's formula
- [ ] Ops head role distinct from billing: assignment, escalation, dispute workflow

## Phase 6 — Privacy, security, quality (P0/P1, continuous)
- [ ] DPDP Act 2023: data inventory, consent/notice text, purpose limitation, retention & auto-delete, access/erasure workflow
- [ ] Private image storage, signed short-lived URLs, no PII in logs, encryption at rest/in transit
- [ ] Input validation everywhere, rate limiting, upload type/size checks, CSRF/CORS, security headers
- [~] Unit tests (decision, compression, queue) and API+DB integration tests done — tests use their own `cargoone_test` database; Playwright E2E pending
- [ ] Offline test matrix (airplane mode, flaky 2G throttling, low-storage)
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
