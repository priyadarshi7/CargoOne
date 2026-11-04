# Git workflow

- `main` is protected: no direct pushes. Enable on GitHub: *Settings → Branches → Add rule* → require PR, require status checks (`api`, `web`), no force-push.
- Branch names: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`, `docs/<topic>`.
- Commits: [Conventional Commits](https://www.conventionalcommits.org) — `feat(api): add trip import`. No AI co-author trailers.
- One PR = one purpose, small, with docs updated. Use the PR template. Squash-merge.
- Flow: `git switch -c feat/x` → commit → `git push -u origin feat/x` → open PR → CI green → review → squash-merge → delete branch.
