# Decision log (ADRs)

Status: Accepted unless noted. Newest decisions go at the bottom; supersede rather than edit.

| # | Decision | Why / trade-off |
|---|---|---|
| 1 | **Vite + React + TS as a PWA** (not Next.js) | App is offline-first and mostly behind login; SSR/SEO adds nothing. Cost: we host a separate API. |
| 2 | **FastAPI (Python)** backend | AI/vision stack is Python; one backend runtime instead of Node + Python. |
| 3 | **PostgreSQL 16** | Free hosting options (Neon/Supabase), JSONB for AI output, strong reporting SQL. |
| 4 | **SQLAlchemy 2.0 (async) + Alembic** (not Prisma, not raw SQL) | Prisma's Python client is community-maintained and needs Node; owner chose a full ORM + migrations. Cost: authorisation lives in API code (no RLS) — must be tested. |
| 5 | **AI Provider Abstraction Layer**, Gemini first | Provider/pricing may change; local model possible later. Interface `extract_pod()`, config-driven, fallback chain, cost/latency/accuracy logging. |
| 6 | Deterministic decision engine (AI extracts, rules decide) | Predictable routing: verified / needs review / retake; retake cap 2. |
| 7 | Hired drivers: signed SMS link, no login | Zero install; token scoped to one trip, expiring, revocable, rate-limited. |
| 8 | Compress on device to <300 KB | Dead zones + free-tier storage; DB constraint is the backstop. |
| 9 | Tally export as Tally Prime XML vouchers + CSV | Standard import path; no live Tally connection. |
| 10 | Voice: browser TTS now → recorded hi/mr audio before pilot | Recording needs a native speaker; TTS quality varies by phone. |
| 11 | Docker Compose for local dev | Reproducible Postgres; api/web containers added later. |
| 12 | Synthetic POD generator for dev/eval; fake test PII | No real PODs yet; collect 100–200 real ones in pilot week 1. Real data never in repo. |
| 13 | Git: protected `main`, short-lived branches, PRs, Conventional Commits, no AI co-author trailers | Owner's standard. |
| 14 | `md` (Managing Director) role: read-only executive dashboard | Deal signer; ROI proof from live data. |
| 15 | Mock AI provider reads ground-truth labels embedded in synthetic PNGs | Whole pipeline + decision rules testable offline, deterministic, free. Does NOT measure real accuracy. |
| 16 | Gemini model name is config (`GEMINI_MODEL`), key sent in header not URL | Model names change; keys must not leak into URLs/logs. |
| 17 | If all providers fail, caller queues POD for human review | Driver is never blocked by an AI outage. |
| 18 | `APP_ENV` guard: seed runs only in dev/test; non-dev startup rejects default/short `JWT_SECRET` | Demo credentials and the default signing key live in the repo; they must never work on a deployed server. |
| 19 | Server stores the uploaded bytes unmodified; validates by decoding (not by client MIME), 300 KB / 25 MP limits | Re-encoding on server would alter evidence; web client already compresses and strips EXIF. |
| 20 | Driver sees a trip as "not found" (404) if it is not theirs; POD upload idempotent on `client_upload_id` | No existence leak; offline retries are safe. |
| 21 | Native camera app via `<input capture>` instead of getUserMedia (for now) | Works on every cheap Android/WebView, handles focus/flash natively; in-app camera + framing guide is a later enhancement. |
| 22 | Offline queue id == server idempotency key; FIFO with strictly increasing stamps | Retries never double-submit or double-count a retake. |
| 23 | Tests run against a separate `<db>_test` database, created + migrated automatically | Test runs were leaving junk trips in the dev DB used for demos. |
| 24 | Reviewer corrections stored in `corrected_fields` beside untouched `ai_result`; approve requires LR to match the trip and a delivery date | Image/AI output stays auditable; a wrong-document POD cannot be approved by typo. |
| 25 | Gemini provider retries 429/5xx twice (0.7 s, 1.8 s) then fails over; errors carry the HTTP status only | Live testing hit transient 503/429s on the free tier; response bodies can echo document text (PII). |
| 26 | Tests force `AI_PROVIDER=mock` and an empty key regardless of `.env` | Real keys must never make tests slow, flaky, or send images to a third party. |
| 27 | Settings read repo-root `.env` and `api/.env` (latter wins) | Developers put the file in either place. |
| 28 | Creating an invoice makes a draft inside CargoOne only; exporting stamps `exported_at`; nothing is sent to clients | Brief: invoices are never sent automatically. |
| 29 | One invoice = one client, one voucher in Tally (party Dr / Freight Income Cr); numbers from a Postgres sequence `CO/<FY>/<n>` | Matches how transporters bill; sequence is race-free for concurrent billers. Gaps are possible and acceptable. |
| 30 | PDF uses "Rs." not the rupee sign | The built-in PDF font has no rupee glyph; embed a TTF font later for the symbol and Devanagari. |
| 31 | CSV export neutralises cells starting with = + - @ | Prevents spreadsheet formula injection. |
| 32 | KPI definitions: 24 h share = first POD upload <= 24 h after delivery (over trips delivered > 24 h ago); POD-to-invoice = verified -> invoiced; lost/disputed = rejected; working capital = the brief formula on annualised window freight | Makes every dashboard number reproducible and testable; `first_pod_at` is stored because retakes overwrite `pod_uploaded_at`. |
| 33 | Dashboard defaults to the last 30 days (90 selectable) | A 90-day window blends before/after eras and understates current performance. |
| 34 | Demo data generator is dev-only, deterministic, DEMO- coded, creates no verified-unbilled trips, and the dashboard shows a banner while any are in the window | Dashboards need history to demo, but fabricated numbers must never pass as real. |
| 35 | Charts: ordinal blue ramp for age buckets (not red/green), single-series lines with a dashed target, hover readout, table view under every chart, status shown with icon + label | Colour never carries meaning alone; follows the dataviz guidance. Dark mode not yet built. |
| 36 | E2E runs on its own stack (API :8001, web :5174, `cargoone_e2e` DB dropped/recreated each run, refuses non-`_e2e` names) with a scripted mock AI (`MOCK_SCENARIO`) | Browser re-encoding strips the label the mock reads, so the mock needs a scripted mode; isolation keeps dev data safe. |
| 37 | Screenshots are saved by E2E (git-ignored) and reviewed by eye after UI changes | Visual bugs (stale badge, ambiguous offline icon, misleading 0% KPI) passed every assertion and were only visible in pictures. |
| 38 | Upload links store only a SHA-256 of the token; 72 h TTL; one active link per trip | A DB leak must not leak working links; limits exposure of a forwarded SMS. |
| 39 | Guess-throttling applies only to UNKNOWN tokens (a blocked IP can still use a valid link) | Carrier NAT puts many real drivers behind one IP; found by a test - the first version would have locked them out. |
| 40 | Upload rules live in one service (`app/pod/ingest.py`) used by the logged-in and the link route; one shared `CaptureFlow` component on the web | Two entry points must never drift apart on retake cap, size limits, idempotency or AI routing. |
| 41 | Mock SMS only (in-memory outbox, masked phone in logs/audit) | Real provider needs DLT-registered templates; the interface is ready. |
