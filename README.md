# CargoOne

Proof-of-delivery capture, AI verification and billing for full-truckload transporters.
Driver photographs the POD at the gate → AI checks it on the spot → billing exports to Tally.

## Run everything (Docker)
Requirements: Docker Desktop, and [Ollama](https://ollama.com) on this computer with `ollama pull qwen3-vl:4b` (it stays outside Docker so it can use the GPU).

```bash
docker compose up -d --build     # database, API and web app; open http://localhost:5173
```
The three containers restart by themselves and the database is migrated on every start. Nothing watches your files, so:
- **after changing code**, run the same command again (it rebuilds only what changed);
- **after changing `.env`**, run `docker compose up -d api`;
- see what the API says with `docker compose logs -f api`; stop everything with `docker compose down` (the data stays).

The web app is on 5173 and 4173 (a phone tunnel such as `cloudflared tunnel --url http://localhost:4173` points at 4173) and reaches the API through `/api`. The API is also on http://localhost:8000. The read-the-photo step runs on the CPU inside the container (no GPU), so it is slower than the old way below.

## Run for development (code reloads by itself, uses the GPU)
Needs Node 22+, pnpm, Python 3.12+, [uv](https://docs.astral.sh/uv/) and a one-time `uv sync` and `pnpm install`. Stop the Docker web app and API first (`docker compose stop api web`), then from `web/`:

```bash
pnpm dev:all          # or: node scripts/dev.mjs
pnpm dev:all:phone    # the same, plus a phone link (Cloudflare quick tunnel); the link is printed
```
It starts Postgres, runs migrations, starts Ollama, the API and the phone build, and keeps them current by itself: saving `.env` restarts the API, editing API code reloads it, editing web code rebuilds the phone app. Run it again at any time: it first clears stale processes. Ctrl+C stops everything it started.

## AI provider
Local reader (no cloud, free): see `docs/09-local-ai-setup.md`. Set `AI_PROVIDER=local` in `.env`.

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

Browser tests (Playwright, real Chromium incl. a phone-sized driver project): `cd web && pnpm exec playwright install chromium && pnpm e2e`.
They start their own API (:8001), web (:5174) and a throw-away `cargoone_e2e` database, so your dev data is never touched.

Tests need migrated Postgres: `cd api && uv run pytest`.

## Trip import
Office → **Import**: upload a CSV/Excel (download the template there). It is checked first and only written when you confirm; re-uploading is safe.

## Docs
- [Product brief](docs/01-product-brief.md) · [Roadmap / to-do](docs/02-roadmap.md) · [Decisions](docs/03-decisions.md)
- [Git workflow](docs/05-git-workflow.md) · [CLAUDE.md](CLAUDE.md) (working rules for AI-assisted development)

## Showing the app on a phone (tunnel)

`vite preview` serves the last build, so rebuild before showing changes: `cd web && pnpm demo` (build, then serve on port 4173), and point the tunnel at `http://localhost:4173`. Phones pick up a new build on the next open. For live editing use `pnpm dev` (port 5173) and tunnel that instead, but the offline behaviour only exists in the built app.
