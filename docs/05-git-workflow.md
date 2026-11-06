# Git workflow

- Work goes **directly to `main`** (owner's decision, replacing the earlier PR-only flow): commit on `main`, run the tests, `git push origin main`. Never force-push. Branches and PRs only when the owner asks for one (names then: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`, `docs/<topic>`).
- Commits: [Conventional Commits](https://www.conventionalcommits.org) — `feat(api): add trip import`. No AI co-author trailers.
- One commit = one purpose, small, with docs updated in the same commit. CI (`api`, `web`) must stay green on `main`.
- Flow: `git switch main` → `git pull --ff-only` → change → run tests → commit → `git push origin main`.
