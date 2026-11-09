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

## One command for everything (recommended)
After the one-time setup below (`uv sync`, `pnpm install`, `ollama pull qwen3-vl:4b`), from `web/`:

```bash
pnpm dev:all          # or: node scripts/dev.mjs
pnpm dev:all:phone    # the same, plus a phone link (Cloudflare quick tunnel); the link is printed
```
It starts Docker (and Postgres), runs migrations, starts Ollama, the API and the phone build, and **keeps them current by itself**: saving `.env` restarts the API, editing API code reloads it, editing web code rebuilds the phone app (refresh the phone after a few seconds). Run it again at any time: it first clears stale processes (old API workers left behind are what made "I changed it and nothing changed"). Ctrl+C stops everything it started. A quick tunnel gets a new address each time it starts, so leave the tunnel running; restarting only the app does not change the link.

## AI provider
The AI only reads the photo; fixed rules in `api/app/pod/decision.py` decide. Pick the reader in `.env`:

| Setting | Reader | Use |
|---|---|---|
| `AI_PROVIDER=groq` + `GROQ_API_KEY` | Qwen3.8 27B on Groq (cloud) | **Main reader** (best on the benchmark: 27 of 28 sheets, 0 unsafe, about 16 s a photo) |
| `AI_PROVIDER=local` | Qwen3-VL 4B + glm-ocr through Ollama, no cloud | Free fallback that works with no network (`docs/09-local-ai-setup.md`) |
| `AI_PROVIDER=gemini` + `GEMINI_API_KEY` | Gemini 2.5 Flash | Works; the free quota is too small to run on |
| `AI_PROVIDER=mock` | Scripted answers | Default, tests, demos |

Recommended: `AI_PROVIDER=groq` with `AI_FALLBACKS=local`. Outside dev and test a cloud reader is used only when `CLOUD_AI_CONFIRMED=true` (a photo leaving for a third party is a DPDP disclosure; see `docs/16-dpdp.md`). Automated tests always force the mock.
How the models were compared, and how to add one: `docs/15-benchmark-forms.md` and the **AI benchmark** tab in the office app.

## What to open
- http://localhost:5173/progress — live build progress (no login), read from `docs/02-roadmap.md`
- http://localhost:5173 — sign in with a demo login below (office → trips table, driver → mobile home)
- http://localhost:8000/docs — API explorer

## Demo logins (LOCAL DEVELOPMENT ONLY — fake data; seed refuses to run unless APP_ENV is dev/test)
| Role | Login | Secret |
|---|---|---|
| Ops head / Billing / MD / Admin | `ops@` · `billing@` · `md@` · `admin@cargoone.dev` | `cargoone-dev` |
| Driver | phone `9000000001` | PIN `1234` |

A small, believable demo company, in this order (all fabricated, dev/test only, safe to run again):
```bash
cd api
uv run python -m app.seed          # branches, the brief's sample trips, the demo logins
uv run python -m app.seed_fleet    # 8 own + 8 hired trucks, 6 transporters (vendors), 12 drivers with licences, 5 clients, 9 office staff
uv run python -m app.demo_data     # 140 illustrative trips over 75 days (coded DEMO-..., a banner says so); --remove deletes them
uv run python -m app.devtools.demo_video   # three trips ready for a screen recording of the driver flow (--reset to record again)
```
`uv run python -m app.seed_fleet --wipe` clears the fleet again (remove the demo trips first). The numbers are not typed into any screen: the dashboard is worked out from these trips, so it moves as you add drivers, take photos and make invoices. It shows the targets met overall (80% of PODs in within a day, 4 days POD to invoice, 0.5% lost), with the Nagpur branch below target on purpose so a red flag is visible. Drivers sign in with their phone and PIN `1234` (the first is `9000000001`); hired drivers use their private link.

Browser tests (Playwright, real Chromium incl. a phone-sized driver project): `cd web && pnpm exec playwright install chromium && pnpm e2e`.
They start their own API (:8001), web (:5174) and a throw-away `cargoone_e2e` database, so your dev data is never touched.

Tests need migrated Postgres: `cd api && uv run pytest`.

## Privacy (DPDP Act 2023)
Public notice at `/privacy` (English, Hindi, Marathi) with a form for a person's request. The admin and the MD answer them under **Privacy requests**. A daily job inside the API erases receiver details and POD photos 8 years after a trip closes (`RETENTION_YEARS`). Set `GRIEVANCE_OFFICER` and `GRIEVANCE_EMAIL` in `.env` before real data.

## Trip import
Office → **Import**: upload a CSV/Excel (download the template there). It is checked first and only written when you confirm; re-uploading is safe.

## Docs
- [Product brief](docs/01-product-brief.md) · [Roadmap / to-do](docs/02-roadmap.md) · [Decisions](docs/03-decisions.md)
- [Security and privacy](docs/04-security-privacy.md) · [DPDP: what is built, owner checklist, breach runbook](docs/16-dpdp.md)
- [AI evaluation](docs/06-ai-evaluation.md) · [Benchmark sheets, results and the model decision](docs/15-benchmark-forms.md) · [Local AI setup](docs/09-local-ai-setup.md)
- Setup guides: [WhatsApp](docs/07-whatsapp-setup.md) · [Email](docs/08-email-setup.md) · [Google Maps](docs/10-google-maps-setup.md) · [Razorpay](docs/12-razorpay-setup.md) · [Tally](docs/13-tally-setup.md) · [SMS](docs/14-sms-setup.md) · [Shipment workflow](docs/11-shipment-workflow.md)
- [Git workflow](docs/05-git-workflow.md) · [CLAUDE.md](CLAUDE.md) (working rules for AI-assisted development)

## Showing the app on a phone (tunnel)

`vite preview` serves the last build, so rebuild before showing changes: `cd web && pnpm demo` (build, then serve on port 4173), and point the tunnel at `http://localhost:4173`. Phones pick up a new build on the next open. For live editing use `pnpm dev` (port 5173) and tunnel that instead, but the offline behaviour only exists in the built app.
