# CargoOne — POD capture & billing for full-truckload transporters

Client: Company A (Chhatrapati Sambhajinagar). Driver photographs the signed LR/POD at the consignee gate,
AI verifies it on the spot, billing invoices in days instead of weeks.
Targets: 80% PODs in-system within 24h · POD→invoice 18→4 days · lost/disputed PODs 1.5%→0.5%.
Budget ₹7.5L / 6 weeks. Brief: `docs/01-product-brief.md` · To-do: `docs/02-roadmap.md` · Decisions: `docs/03-decisions.md`.

## Stack
- `web/` — Vite + React + TypeScript + Tailwind v4, **PWA** (vite-plugin-pwa), offline queue in IndexedDB (`idb`). pnpm.
- `api/` — **FastAPI** (Python 3.12+), **SQLAlchemy 2.0 async** + **Alembic**, **PostgreSQL 16**, Pydantic v2. uv, Ruff, pytest.
- AI: provider-abstraction layer in `api/app/ai/` (Gemini default; Claude/OpenAI/local pluggable; mock for tests; fallback chain).
- Local dev: Docker Compose (Postgres now; api + web containers later). Deployment is a later phase (free tiers).
- i18n en/hi/mr. Voice prompts: browser TTS now, recorded native audio before pilot.

## Commands
- DB: `docker compose up -d db` (needs Docker Desktop running)
- API (in `api/`): `uv run alembic upgrade head` · `uv run uvicorn app.main:app --reload` · `uv run pytest` · `uv run ruff check .`
- Web (in `web/`): `pnpm dev` · `pnpm build` · `pnpm lint` · `pnpm test`
- New migration: `uv run alembic revision --autogenerate -m "msg"` — always review the generated file.

## Git workflow (strict)
- **Never push to `main`.** Branch `feat/…`, `fix/…`, `chore/…`, `docs/…` → push → PR → squash-merge by the owner.
- Conventional Commits (`feat(api): …`). **No Claude/AI co-author trailers** on commits or PRs (owner's rule).
- Keep PRs small and single-purpose. CI (typecheck, lint, tests, build) must pass.
- Update docs in the same PR as the behaviour change.

## Non-negotiable product rules
1. **Image is the source of truth.** AI extracts; humans correct. Invoices are never sent automatically.
2. Shortage/damage remark OR low confidence → review queue (billing exec).
3. Retakes capped at **2** (also enforced by DB check constraint).
4. Images compressed **<300 KB** on device; capture works **offline**, syncs later, idempotent via `client_upload_id`.
5. Driver UX: one big button, icons, voice prompts, **no forms/typing**. Success = green, retake = amber.
6. Consignee name/phone = personal data (DPDP Act 2023): private storage, signed URLs, role checks in API, audit log, no PII in logs, retention policy. Test data must be fake.
7. Every trip links to an e-way bill number.
8. Roles: `driver`, `billing`, `ops`, `md` (read-only executive), `admin`; external client = expiring token link. Mock payments/SMS/Tally.
9. Authorisation is enforced in the API (no DB row-level security) — every endpoint needs a role dependency and a test.

## Design principles
Minimal, white space, restrained palette (one accent + semantic green/amber/red), clear type, nothing without purpose.
Driver surfaces: ≥64px targets, one action per screen. Office surfaces: calm dense tables, keyboard friendly.

## Layout
`web/src` (driver, office, public token pages) · `api/app` (routers, services, ai, models) · `api/migrations` · `docs/` · `.github/`
