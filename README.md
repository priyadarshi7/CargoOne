# CargoOne

Proof-of-delivery capture, AI verification and billing for full-truckload transporters.
Driver photographs the POD at the gate → AI checks it on the spot → billing exports to Tally.

## Quick start (local)
Requirements: Docker Desktop, Node 22+, pnpm, Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example api/.env
docker compose up -d db
cd api && uv sync && uv run alembic upgrade head && uv run python -m app.seed && uv run uvicorn app.main:app --reload   # http://localhost:8000/docs
cd web && pnpm install && pnpm dev                                                          # http://localhost:5173
```

## AI provider (Gemini)
Put these in `.env` in the repo root (or `api/.env`; never commit it):
```
AI_PROVIDER=gemini
GEMINI_API_KEY=<your key from Google AI Studio>
```
Default is `mock`, which only understands the synthetic test images. Automated tests always force the mock.

## What to open
- http://localhost:5173/progress — live build progress (no login), read from `docs/02-roadmap.md`
- http://localhost:5173 — sign in with a demo login below (office → trips table, driver → mobile home)
- http://localhost:8000/docs — API explorer

## Demo logins (LOCAL DEVELOPMENT ONLY — fake data; seed refuses to run unless APP_ENV is dev/test)
| Role | Login | Secret |
|---|---|---|
| Ops head / Billing / MD / Admin | `ops@` · `billing@` · `md@` · `admin@cargoone.dev` | `cargoone-dev` |
| Driver | phone `9000000001` | PIN `1234` |

Dashboards look empty without history. Add illustrative demo trips (clearly coded `DEMO-…`, banner shown on the dashboard):
`cd api && uv run python -m app.demo_data` (remove again with `--remove`). Dev/test only.

Tests need migrated Postgres: `cd api && uv run pytest`.

## Docs
- [Product brief](docs/01-product-brief.md) · [Roadmap / to-do](docs/02-roadmap.md) · [Decisions](docs/03-decisions.md)
- [Git workflow](docs/05-git-workflow.md) · [CLAUDE.md](CLAUDE.md) (working rules for AI-assisted development)
