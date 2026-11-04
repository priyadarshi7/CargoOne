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
| 19 | Server stores the uploaded bytes unmodified; validates by decoding (not by client MIME), 300 KB / 25 MP limits | Re-encoding on server would alter evidence; web client already compresses and strips EXIF. |
| 20 | Driver sees a trip as "not found" (404) if it is not theirs; POD upload idempotent on `client_upload_id` | No existence leak; offline retries are safe. |
| 21 | Native camera app via `<input capture>` instead of getUserMedia (for now) | Works on every cheap Android/WebView, handles focus/flash natively; in-app camera + framing guide is a later enhancement. |
| 22 | Offline queue id == server idempotency key; FIFO with strictly increasing stamps | Retries never double-submit or double-count a retake. |
| 23 | Tests run against a separate `<db>_test` database, created + migrated automatically | Test runs were leaving junk trips in the dev DB used for demos. |
| 24 | Reviewer corrections stored in `corrected_fields` beside untouched `ai_result`; approve requires LR to match the trip and a delivery date | Image/AI output stays auditable; a wrong-document POD cannot be approved by typo. |
