# Security & privacy

Status of what is **built**, what is **open**, and what needs **legal/owner input**. Update with every relevant change.
This is an engineering record, not legal advice - the DPDP Act 2023 obligations must be confirmed with counsel.

## Personal data inventory
| Data | Where | Who can see it |
|---|---|---|
| Consignee name + phone | `trips.consignee_name/phone` | Nobody in the UI today (never returned by any API; tests assert this) |
| POD photos (may show names, signatures, phones, stamps) | private storage, `pod_submissions.storage_key` | billing, ops, admin, md (read), the trip's own driver; every view is audit-logged |
| Driver GPS at capture time | `pod_submissions.lat/lng` | billing/ops in the review screen |
| Driver / staff name, phone, email | `users` | the user; office roles (API) |
| Hired driver's mobile (typed when sending a link) | **not stored**; masked (`******3210`) in audit log | - |
| Audit trail | `audit_log` | ops/admin (API only) |

## Built
- **AuthN/Z in the API** (no DB row-level security): every endpoint declares `require_roles(...)`; 401/403/404 behaviour is tested. Drivers get 404 (not 403) for trips that are not theirs.
- **Passwords/PINs**: Argon2 hashes. Login errors do not reveal whether an account exists.
- **Images**: private storage only, served through role-checked endpoints with `Cache-Control: private, no-store`; stored bytes are never modified; validated by decoding, 300 KB / 25 MP limits; path-traversal guard.
- **No PII in lists, dashboards, logs, error messages or AI-provider errors** (status codes only).
- **Tokenised SMS upload links**: 256-bit random, only the SHA-256 is stored, scoped to one trip + one purpose, expire (72 h), revoked when a new link is issued or by the office, rate-limited (guessing throttle on unknown tokens only, per-link photo cap), public page shows destination + vehicle only.
- **Audit log** for uploads, image views, review decisions, invoices/exports, link creation/revocation.
- **Safety rails**: demo seed and demo data refuse to run outside dev/test; non-dev refuses to start with the default/short JWT secret; tests use their own database and never call a real AI.
- **Secrets**: `.env` git-ignored. (A key was once printed into a development session transcript - rotated by owner; avoid `cat`/`sed` on `.env`.)

## Open before any real data / production
1. **Retention + auto-delete** of POD images and personal fields (period to be agreed with the client; DPDP purpose limitation).
2. **Notice / consent text** shown to drivers (and where consignee data is collected), plus a **data-principal request workflow** (access, correction, erasure).
3. **Login hardening**: rate limit + lockout, token refresh/revocation, logout-everywhere, driver PIN reset flow.
4. **Per-branch scoping** of office users; admin role audit.
5. **Transport/headers**: HTTPS/HSTS, CSP and other security headers, strict CORS per environment.
6. **Rate limiter is per process** (in-memory): move to Redis/edge before running more than one API instance. Behind a proxy, read the client IP from a trusted `X-Forwarded-For` only.
7. **Sending POD photos to an AI provider** (Gemini free tier) is a cross-border/third-party disclosure; free-tier terms may allow training on inputs. Needs a decision: paid tier with no-training terms, or a local model, before real PODs are processed.
8. **Backups, encryption at rest** (managed by the DB/storage host - verify), breach-response runbook, penetration test.
9. **Real SMS provider** needs DLT-registered templates in India; links in SMS are bearer secrets - keep TTL short.

## Threat notes: SMS links
| Threat | Mitigation |
|---|---|
| Guessing a token | 256-bit random; unknown tokens throttled |
| Link forwarded to someone else | Scope is one trip, upload-only; shows no commercial/personal data; can be revoked |
| DB leak exposes working links | Only hashes stored |
| Flooding a trip with photos | Per-link cap, retake cap (2), size cap (300 KB), POD closed once verified |
| Stale link reused | 72 h expiry; 410 after revoke/expiry; new link revokes old |
