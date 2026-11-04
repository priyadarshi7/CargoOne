# CargoOne roadmap & to-do

Legend: [ ] todo · [~] in progress · [x] done. Each item = one branch/PR (`feat/…`, `fix/…`, `chore/…`, `docs/…`).
Priority: **P0** core slice (client's must-ship) · **P1** must-have depth · **P2** "wow" — the out-of-scope items, built later so the client is not disappointed.

## Phase 0 — Foundations (decide before coding)
- [ ] P0 Finalise stack decisions (see `03-decisions.md`) — one at a time, with trade-offs
- [ ] P0 Git workflow: protected `main`, branch naming, Conventional Commits, PR template, CI required
- [ ] P0 Monorepo layout, lint/format (ESLint + Prettier), TypeScript strict, path aliases
- [ ] P0 Local dev: one-command start (DB container, migrate, seed, web, api)
- [ ] P0 CI (GitHub Actions): typecheck, lint, unit tests, build on every PR
- [ ] P0 Env/config management, `.env.example`, secrets rules
- [ ] P0 Docs: README, CLAUDE.md, ADRs, architecture diagram, runbook skeleton

## Phase 1 — Design system & app shell (P0)
- [ ] Design tokens: colour (neutral + one accent, green/amber/red semantic), type scale, spacing, radius, motion
- [ ] Component kit: Button (driver XL variant), Card, Table, Badge, Dialog, Toast, Empty state, Skeleton, Stepper
- [ ] Icon set + illustrations for driver flow (no text dependence)
- [ ] i18n framework: English / हिंदी / मराठी, language switch, number/date/₹ formatting (Indian grouping)
- [ ] Accessibility: contrast AA, 64px+ driver targets, focus states, reduced motion
- [ ] Two shells: driver (mobile-first, 1 action/screen) and office (sidebar, tables, keyboard nav)
- [ ] Dark mode for office shell (optional)

## Phase 2 — Data, auth, roles (P0)
- [ ] DB schema + migrations + seed from client sample data (+ larger realistic demo data set)
- [ ] Auth: office login (email+password), driver login (phone + PIN/OTP, mocked SMS), session handling
- [ ] Roles & permissions: driver, billing, ops, admin; per-branch scoping
- [ ] Hired-driver tokenised SMS link (trip-scoped, expiring, revocable, rate-limited)
- [ ] Audit log for every sensitive read/write
- [ ] Trip import: CSV/XLSX daily upload with LR + e-way bill, validation, dedupe, error report
- [ ] E-way bill field validation (12 digits) + mock lookup adapter

## Phase 3 — Driver capture (P0, the hard part)
- [ ] Driver home: assigned trips, one giant "Photograph POD" button, big status icons
- [ ] Camera capture (getUserMedia + file-input fallback), framing guide overlay, flash/torch toggle
- [ ] GPS + timestamp stamped on capture (with permission handling and "no GPS" fallback)
- [ ] On-device compression to <300 KB (resize, quality ladder, EXIF strip/orient), perceptual quality check
- [ ] Client-side quick checks: blur, brightness, document edges → instant "retake" before upload
- [ ] Offline queue (IndexedDB): persist photo + metadata, background sync, retry with backoff, idempotent upload
- [ ] PWA: installable, service worker, offline shell, update prompt, storage-quota handling
- [ ] Upload status UI usable by non-readers: ⏳ saved · ☁️ uploading · ✅ done · 🔁 retake
- [ ] Voice prompts hi/mr/en (recorded audio, TTS fallback), replay button
- [ ] Retake flow, capped at 2; then auto-route to human review
- [ ] SMS-link capture page (no login, same capture engine, lighter shell)

## Phase 4 — AI POD verification (P0)
- [ ] AI provider abstraction layer (Python): `extract_pod()` interface, registry, config-driven selection, fallback chain, per-provider cost/latency/accuracy logging
- [ ] Providers: mock, Gemini (default), Claude, OpenAI, local (PaddleOCR + rules / local VLM)
- [ ] Synthetic POD generator (stamps, signatures, hi/mr handwriting, blur/skew/glare) for dev + regression
- [ ] Collect 100–200 real PODs from client in pilot week 1 → real accuracy report for the MD
- [ ] Extraction: LR no., consignee stamp, quantity, shortage/damage remarks, date, signature, confidence
- [ ] Prompt + structured output schema + validation; Hindi/Marathi handwriting cases
- [ ] Deterministic decision engine (verified / needs review / retake) — unit-tested rule table
- [ ] Real-time result to driver while at the gate (<10 s target), graceful degrade if AI is down (queue as "review")
- [ ] Cost/latency controls: timeouts, retries, caching by image hash, provider fallback
- [ ] Evaluation harness: labelled POD image set, accuracy/recall report, regression gate
- [ ] Never auto-send invoices; image remains source of truth

## Phase 5 — Office workflows (P0)
- [ ] Review queue: side-by-side image viewer (zoom/rotate) + extracted fields, edit & approve/reject, reason codes, keyboard shortcuts
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
- [ ] Unit tests (decision engine, compression, queue), integration tests (API + DB), E2E (Playwright: capture→review→bill)
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
