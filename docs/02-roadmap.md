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

## Forms: phone numbers and exact places
- [x] **Mobile numbers are checked as you type** on every form that takes one (company request, planning consignee, drivers, clients, vendors, upload link): a fixed **+91** in front, digits only, "starts with 6, 7, 8 or 9" shown from the first wrong digit, "enter all 10 digits" once you leave the box, and the browser refuses to send the form while it is wrong. Pasting "+91 98765 43210" works. Stored exactly as before (the plain 10 digits), so logins, WhatsApp and old data are unchanged. India only for now (owner's choice).
- [x] **Place suggestions with exact map positions** for pickup and delivery on the company request form and for origin and destination when planning a trip: type 3 letters, pick from the list (keyboard works), and the latitude and longitude are saved with the trip and the request. "View on map" opens the spot. The driver's **Navigate** button goes to the exact saved drop point (falls back to the typed name). A request's picked places carry into the trip when ops plans it. If suggestions are unavailable the form says so and the person types the place; nothing blocks.
- [x] **Google Places API (New) and a Zomato-style map picker** (owner's choice). With a server key, suggestions come from Google (India only, biased to the depot; a search-then-pick is one billed session) and every place field gets a **Pick on map** button: a Google map with a fixed pin, search, "use my current location", the address of the spot under the pin updating as you move the map, and Confirm saving the pin's exact latitude and longitude. Google suggestions are credited ("Powered by Google") and never cached. Without keys the free OpenStreetMap search (Photon, cached a day) is used and there is no map button. Setup, key restrictions, costs and the terms question: `docs/10-google-maps-setup.md`.
- [ ] Not done: a real-key check of the Google calls and the real map (everything is tested with a stand-in for Google until the keys are added); showing saved positions on the live map or planning screen; distance and ETA from the two positions; other countries' phone numbers; a decision on storing coordinates under Google's terms (see the setup doc).

## Local AI reader and boxes on the photo
- [x] **Local reader (no cloud, no cost):** `AI_PROVIDER=local` reads the photo with PaddleOCR (text and where it is) and Qwen3-VL 4B through Ollama (is it a POD, stamp, signature, remarks), then checks every claim of the model against the OCR text. The LR number counts only when the text reader can see it on the paper. Gemini stays an optional fallback. Setup and limits: `docs/09-local-ai-setup.md`.
- [x] **Boxes with tags in Review:** each found field (LR number, date, quantity, remarks, stamp, signature) is drawn on the photo with a tag; a list says what was found and what was not; focusing a form field lights its box and the other way round; the reviewer can hide the boxes. Stored as fractions of the photo, so zoom and rotate keep them in place.
- [x] **Measured (18 synthetic photos, original and phone-degraded):** 0 unsafe errors, 18 of 18 decisions match a perfect reader, 0 good PODs sent back; median 36 s, slowest 96 s per photo on an RTX 4050 laptop.
- [x] **Every POD can be opened read-only** ("View" next to the status on the trips page and next to each trip in billing; the MD too): what the AI read, which reader read it, its notes, and the boxes on the photo, for PODs the AI verified by itself as well as ones waiting for review. No decision buttons unless the POD is actually waiting for review.
- [x] **Fast OCR:** PaddleOCR's models on ONNX Runtime and the GPU: OCR 20 s to 1 s; a real eLR photo is read in about 8-12 s (was 26-30 s). Accuracy test unchanged.
- [ ] Not done: measuring on real client photos (needed before trusting any number above); speed of photos whose signature needs the model's second, thinking look (30 s or more: options are a larger or faster model, or checking after the driver has left); Hindi/Marathi print (`OCR_LANGS=en,devanagari`, untested); boxes on the driver's own result screen; boxes from Gemini.

## Driver alerts (Web Push) and Messages
- [x] **Alerts reach a closed app.** Assigning, changing or cancelling a trip, and registering a driver, now buzz the driver's phone (Web Push, signed with VAPID keys) as well as the in-app message and WhatsApp. Tapping the alert opens that trip. Sending runs in the background and never blocks planning; a phone the push service says is gone is forgotten; one phone belongs to one person; 5 phones per person at most.
- [x] **Driver turns alerts on with one big button** (offered on the home screen once, and always in Help), can turn them off, and can **send themselves a test alert**. The screen says plainly when alerts are blocked, impossible on this phone, or not set up by the office.
- [x] **Messages tab** (fourth tab, with an unread badge): every message from the office, newest first, unread ones marked; tapping one opens its trip and marks it read; "mark all as read"; works offline from the phone's saved copy.
- [x] **Colour switch (auto, light, dark)** on the landing page, sign-in, request, request status, client delivery-proof and tracking pages and the office; big three-button choice in the driver's Help.
- Setup: `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` in `.env` (generated once; never commit or share the private key); optional `VAPID_SUBJECT` (a `mailto:` contact the push services can reach, default admin@cargoone.dev: set a real one before launch). Alerts need the built app over HTTPS (`pnpm demo` and the tunnel); they do not work in `pnpm dev`. Android Chrome works; iPhone needs the app added to the home screen (iOS 16.4 or later).
- [x] **More alerts.** The driver is also told (Messages tab and phone alert, no WhatsApp template needed) when a claim is approved or not accepted (with the office's reason) and when the office asks for the receipt photo again. Tapping opens Expenses or that trip.
- [ ] Not done: alerts for payments, quiet hours, a sound or vibration pattern per kind, an office view of who has alerts on and whether the last alert was accepted.

## Driver app: offline-first and simple
- [x] **Works with no network.** Trips, messages and expenses are saved on the phone after every successful read and shown (with a "no network, showing saved information" line) when the network drops; the app opens signed in with no network. Starting a trip and adding an expense are saved first and sent in order later (same id on every retry, so nothing is done twice); POD photos keep their own queue as before. The top bar always says whether the network is on and how many items are waiting; a send that can never succeed is shown with a Dismiss button.
- [x] **Redesigned for low-literacy drivers on cheap phones.** One trip, one huge button (Start trip, then POD photo); From and To in large type with a Listen button that reads the route aloud; Navigate (opens Maps) and Call; three bottom tabs (Trips, Expenses, Help); a language switch (EN, हि, म) on every screen; a Help screen with three pictured steps, "send saved items now", change PIN and sign out. No blur or shadows; office screens load on demand, so the driver's first download is smaller.
- [x] **Phone demo through the tunnel.** The tunnel was serving an old build (`vite preview` shows the last build, and the service worker keeps the old one). `pnpm demo` rebuilds and serves; new builds now take over at once (skip waiting and claim clients) and the manifest colour matches the new look.
- [ ] Not done: the driver's earnings or advances view, trip history beyond the list, an office phone number to call (not stored anywhere yet), offline start of a trip the phone has never seen, recorded Hindi/Marathi audio instead of the phone's own voice (many phones have no Marathi voice and read Hindi), the main script is about 170 KB compressed (further splitting would help the cheapest phones).

## Landing page and role home screens
- [x] **Public landing page** at `/` for signed-out visitors (English / Hindi / Marathi): what CargoOne does, how a company asks for a truck in three steps, what it gets (status link, delivery proof, its language), a **Request transport** button on every section, and "Staff and driver sign in". Signed-in people skip it and go to their own home. The sign-in page's logo links back to it. No statistics, logos or testimonials are shown, because none are verified.
- [x] **Role home screens.** Ops and admin: *Operations desk* (needs-attention list, companies waiting for a reply, trips waiting to start, on the road, delivered without receipt, receipts to check, trucks available, quick actions). Billing: *Billing desk* (receipts to check, loads ready to invoice with the freight total, receipts missing, driver claims to approve, quick actions). MD: the performance dashboard (read-only). The performance figures for ops moved under **Performance**. Counts come from `/home`; the MD never receives the freight total.
- [x] **Redesign, step 1.** Landing page rebuilt (hero on a pale sky with slow clouds, soft hills and a container truck driving along a road, plus a four-item strip: full-truckload cargo, signed proof of delivery, live tracking links, WhatsApp updates; request-page preview, three steps, four benefits, closing call to action); shared colour tokens switched app-wide to neutral graphite and white with black primary buttons; Geist font. The hero scene is pure SVG and CSS (no image files) and stays still when the device asks for reduced motion; dark mode shows a graphite night version. The full design canvas (foundations, request form, sign in, ops and billing desks, driver phone) is the reference for the remaining screens.
- [x] **Redesign, step 2.** Left sidebar for the office (drawer on phones), new sign-in page (show password, role panel), request form in sections with quick truck picks and a sticky "what happens next" panel, request status as a timeline, desks with a header action and two-column tiles on phones, driver home with brand header and a clearer photo button, one heading style on every office page, softer radii everywhere.
- [x] **Redesign, step 3.** Review detail (sticky decision panel, larger fields, key hints), review list and billing polished; planning form split into sections (client and route, truck and time, freight and goods, who receives it); client delivery-proof and tracking pages share a branded frame; driver onboarding page restyled; tabs and checkboxes are black, not blue.
- [ ] Not done: setup dialogs, the expenses detail tabs, import, requests list, MD dashboard and live map keep their layouts (new colours and radii only); the drivers' and hired drivers' home keep the current single design; the landing page has no phone number, address or company story until the owner supplies real details; no analytics on landing visits; role-specific navigation for billing still shows planning and requests (billing may read them).

## Email
- [x] **Email to requesting companies** (request received and every update) over plain SMTP (Gmail app password or the company's mail host), only when they gave an address, in their language, with their status link. Recorded in the same Setup > Messages log as WhatsApp, with a channel column and a **Send a test email** box to check the mailbox. Recording mode (stated on screen) until the SMTP settings are filled in. Setup guide: `docs/08-email-setup.md`.
- [ ] Not done: the MD's weekly digest by email, bounce handling, a sending service with domain authentication (better delivery than a personal mailbox), driver/staff emails.

## Client requests and onboarding
- [x] **Public request page** (`/request`, no login, English / Hindi / Marathi): company, contact, mobile, optional email and GSTIN, pickup and delivery city, material, weight, truck type, pickup date, notes, and an explicit agreement to be contacted. Linked from the sign-in page.
- [x] The requester gets a reference (REQ-1001) and a **private status link** (reference plus an HMAC signature, nothing stored) that shows received / accepted / booked as trip TRP-... / declined, with the office's reply and quote. They are also told on WhatsApp (recording mode until Meta is set up).
- [x] **Requests** screen for the office (ops decides, billing reads) and a "new transport requests" line on the dashboard's needs-attention panel.
- [x] **Accept** onboards the company as a client in the same step (name, contact, phone, GSTIN carried over; billing cycle chosen) or links the request to an existing client; a duplicate company name is refused with a pointer to the existing client. Optional quote and message to the requester.
- [x] **Decline** needs a reason that the requester reads. **Book a trip** opens the planning form already filled from the request; creating the trip closes the request as booked and tells the requester the trip code and start time. One request books one trip.
- [x] Clients now carry a **GSTIN** (validated format) in Setup.
- [x] Abuse guards on the public form: hidden bot field, 5 requests per hour per address and 3 per day per phone, strict sizes, nothing about other requests or clients ever returned.
- [ ] Not done: a CAPTCHA (add Cloudflare Turnstile before advertising the address), a retention rule that deletes old declined requests, the requester accepting a quote online, attachments (e.g. a packing list), and a branded/real company address on the page.

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

## Shipment workflow: order, dispatch, loading, transit, delivery, billing, close (owner's brief)

One shipment, one link, one timeline. Built in stages; each is on main when its box is ticked.

- [x] **Booking rules.** A trip needs a start time (it never showed on the calendar without one) and the e-way bill's validity, which must cover the trip; a start in the past, more than a year ahead, or a trip longer than 60 days is refused. One e-way bill covers one trip until that trip is cancelled (also checked in imports, with LR numbers). A driver can start a trip only within 3 hours of its planned time and never while the truck or driver is still on another trip (the office can start it for them). Cancelling and re-planning (truck, driver or time) need a reason, which the driver is told and the audit trail keeps.
- [ ] Dispatch: the driver's acknowledgement shows to the office.
- [ ] Loading: the driver confirms "loaded" with a photo of the loaded truck and LR before the trip starts.
- [ ] In transit: delay and breakdown posts, ETA from the live position, late alerts.
- [ ] Delivery: the receiver's 4-digit code, shortage or damage noted at the door.
- [ ] Shipment link: one page with the timeline, live map and ETA, for the client (with price, POD and invoice) and the receiver (with the code, no price); WhatsApp at each step.
- [ ] Billing: invoice marked sent by a person, payments recorded, invoiced and paid shown to the client.
- [ ] Close: a paid trip is closed and locked; reopening needs an admin and a reason.
- [ ] Order: the client accepts the quote online; clients get their own login with all their shipments.

