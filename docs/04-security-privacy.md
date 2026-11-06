# Security & privacy

Status of what is **built**, what is **open**, and what needs **legal/owner input**. Update with every relevant change.
This is an engineering record, not legal advice - the DPDP Act 2023 obligations must be confirmed with counsel.

## Personal data inventory
| Data | Where | Who can see it |
|---|---|---|
| Consignee name + phone | `trips.consignee_name/phone` | Nobody in the UI today (never returned by any API; tests assert this) |
| POD photos (may show names, signatures, phones, stamps) | private storage, `pod_submissions.storage_key` | billing, ops, admin, md (read), the trip's own driver; every view is audit-logged |
| Driver GPS at capture time | `pod_submissions.lat/lng` | billing/ops in the review screen |
| Requester name, phone, email (public form) | `transport_requests` | ops, billing (API only); the requester sees their own request by link |
| Driving licence number, expiry and photo | `users.licence_*`, `documents` | ops/admin (photo); ops/billing (number, expiry) |
| Driver / staff name, phone, email | `users` | the user; office roles (API) |
| Hired driver's mobile (typed when sending a link) | **not stored**; masked (`******3210`) in audit log | - |
| Audit trail | `audit_log` | ops/admin (API only) |

## Built
- **AuthN/Z in the API** (no DB row-level security): every endpoint declares `require_roles(...)`; 401/403/404 behaviour is tested. Drivers get 404 (not 403) for trips that are not theirs.
- **Passwords/PINs**: Argon2 hashes. Login errors do not reveal whether an account exists.
- **Images**: private storage only, served through role-checked endpoints with `Cache-Control: private, no-store`; stored bytes are never modified; validated by decoding, 300 KB / 25 MP limits; path-traversal guard.
- **No PII in lists, dashboards, logs, error messages or AI-provider errors** (status codes only).
- **Client view links** (`/v/<token>`): same token model, read-only, verified PODs only, shows LR/vehicle/route/date + the signed receipt photo (no freight, no consignee name/phone), 30-day expiry, opens are audit-logged (no IP stored).
- **Driver location (GPS)**: collected only after the driver agrees (timestamped, withdrawable in effect immediately), only while a trip is on the road, readable by ops and the MD (not billing), every view of a path audited, fixes deleted after 30 days (`purge_old_pings`, to be scheduled in deployment). Client tracking links show a ~100 m rounded position, never the driver, and stop showing once the load is delivered.
- **Accounts lifecycle**: drivers are registered by phone with a random one-time PIN (shown once, never stored in clear or audited) that must be replaced at first sign-in; office staff accounts are created by the admin only, with a temporary password treated the same way; a client's people get an emailed one-time link (hash stored, 72 h) to choose their own password, so no password for them is ever shown or sent. Deactivated users cannot sign in and their live sessions end (token version bump). Every create/update is audited with the fields changed, not the values.
- **Tokenised SMS upload links**: 256-bit random, only the SHA-256 is stored, scoped to one trip + one purpose, expire (72 h), revoked when a new link is issued or by the office, rate-limited (guessing throttle on unknown tokens only, per-link photo cap), public page shows destination + vehicle only.
- **Driver and truck papers**: licence and RC/insurance/fitness/permit/PUC photos or PDFs live in private storage behind role checks (truck papers: ops + billing; licences: ops/admin only), type taken from the file bytes not the name, 3 MB cap, replaced files are deleted, no public URL. Licence number and expiry are stored on the driver (personal data, office roles only).
- **Driver onboarding links and WhatsApp**: one-time, hashed, 72 h, replaced on resend, dead once used; the public pages reveal only the driver's name and language; the message log keeps masked numbers and never the link secret; the WhatsApp token lives only in `.env`. A driver's own trip list includes the consignee name and phone (they must call them); the office lists still never do.
- **Public transport request form**: the only place the internet writes to the database. Hidden bot field, rate limits (per address and per phone), strict field sizes and formats, explicit consent to be contacted (stored with a timestamp), status links are HMAC-signed and reveal no contact details or other requests, and the office sees contact details only through role-checked endpoints (ops, billing). Still to add before wide use: CAPTCHA, a retention period for declined requests (suggest 180 days), and a privacy notice on the page naming Company A and the purpose.
- **Email**: the SMTP password lives only in `.env`; the connection is encrypted (STARTTLS or SSL) before login; the log keeps masked addresses and never the status link's secret part; error messages shown to staff never echo the password or the recipient.
- **Audit log** for uploads, image views, review decisions, invoices/exports, link creation/revocation.
- **Safety rails**: demo seed and demo data refuse to run outside dev/test; non-dev refuses to start with the default/short JWT secret; tests use their own database and never call a real AI.
- **Secrets**: `.env` git-ignored. (A key was once printed into a development session transcript - rotated by owner; avoid `cat`/`sed` on `.env`.)

- **Place search sends the typed place text (or a pin's position) to the provider:** Google (Places, Geocoding) when keys are set, otherwise Photon (komoot, OpenStreetMap data), always from our server with no names, phone numbers or account details. The map loads Google's script in the browser, with a site-restricted browser key; the server key is never sent to a browser. People are asked only for a place, not a home address. The public endpoints under `/places` are rate-limited per address.

## Open before any real data / production
1. **Retention + auto-delete** of POD images and personal fields (period to be agreed with the client; DPDP purpose limitation).
2. **Notice / consent text** shown to drivers (and where consignee data is collected), plus a **data-principal request workflow** (access, correction, erasure).
3. **Login hardening** - DONE: 5 failures lock a real account for 15 min (database, survives restarts); failed attempts are also throttled per typed identifier and per address, identically for unknown accounts (no account enumeration); constant-time check for unknown users; every sign-in and failure is audited with masked identifiers; password/PIN policy and change flow; changing it signs out all other sessions (token version). Driver PIN reset DONE: ops/billing issue a one-time temporary PIN (never stored in clear, never audited), old sessions die, the lock clears, and the driver can do nothing but choose their own PIN until they do (enforced in the API, not just the screen); drivers can also change their PIN from their home screen. STILL OPEN: SMS delivery of the temporary PIN (needs the SMS provider), a refresh-token scheme (tokens last 12 h), and the lock being per source address behind a proxy (see item 6).
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
