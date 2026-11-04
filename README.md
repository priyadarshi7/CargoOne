# CargoOne

Proof-of-delivery capture, AI verification and billing for full-truckload transporters.
Driver photographs the POD at the gate → AI checks it on the spot → billing exports to Tally.

## Quick start (local)
Requirements: Docker Desktop, Node 22+, pnpm, Python 3.12+, [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example api/.env
docker compose up -d db
cd api && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload   # http://localhost:8000/docs
cd web && pnpm install && pnpm dev                                                          # http://localhost:5173
```

## Docs
- [Product brief](docs/01-product-brief.md) · [Roadmap / to-do](docs/02-roadmap.md) · [Decisions](docs/03-decisions.md)
- [Git workflow](docs/05-git-workflow.md) · [CLAUDE.md](CLAUDE.md) (working rules for AI-assisted development)
