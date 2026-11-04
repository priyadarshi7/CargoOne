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
