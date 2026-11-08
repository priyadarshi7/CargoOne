# DPDP Act 2023: what CargoOne does, and what the owner does

An engineering record, not legal advice. Company A is the **Data Fiduciary**: it decides why and how the personal data below is used. CargoOne
(the software) and the services it calls are **Data Processors**. Have counsel confirm the wording of the notice and the retention periods.

## What is built

| DPDP duty | How it is met | Where |
|---|---|---|
| Notice (s.5) | Public page `/privacy` in English, Hindi, Marathi: what is kept, why, who sees it, how long, the person's rights, how to ask. Linked from the landing page, sign-in, the request form (next to its consent line) and the driver Help screen. The trip form tells staff what the receiver's details are for. | `web/src/pages/Privacy.tsx` |
| Consent (s.6) | Transport request form: explicit tick, stored with a time. Driver location: asked once, stored with a time, withdrawable at once. The receiver's details are not collected by consent but for a legitimate use (delivering the load) and are limited to that. | `requests.py`, `tracking.py` |
| Purpose limitation, data minimisation (s.4, 6) | Receiver name, phone and email are never returned by any office list; only the trip's own driver sees them. Client links show no receiver data. Place search sends no names. | tests in `test_trips.py`, `test_client_view.py` |
| Retention and erasure (s.8(7)) | Daily job removes the receiver's name, phone, email, the POD and loading photos, and what the AI read, `RETENTION_YEARS` (8) after a trip closes; declined requests after 180 days; GPS after 30 days. The trip, LR, invoice and payment records stay (tax). Runs inside the API once a day, one process at a time (database lock); also `python -m app.privacy`. | `api/app/privacy.py` |
| Rights of a person (s.11-14): access, correction, erasure, withdraw consent, grievance | Anyone files a request on `/privacy` with their mobile number (rate-limited, bot field). The privacy officer (admin or MD) sees it in **Privacy requests**, calls the number back to confirm who is asking, looks up what is held, erases it, and closes the request with what was done. A request taken by phone or in person is logged there too. A closed request keeps its number only as the last four digits. Target reply: 30 days (`PRIVACY_REPLY_DAYS`, the Act sets no number); overdue ones are marked. | `routers/privacy.py`, `OfficePrivacy.tsx` |
| Erasing a driver | Closes the account, removes name, phone, email, licence, location consent and all position history; trips they drove stay. | `privacy.erase_about` |
| Security safeguards (s.8(5)) | See `04-security-privacy.md`: role checks on every endpoint, private image storage, hashed secrets, audit log, lock-out, rate limits, encrypted email. | |
| Third parties / cross-border | Photos go to an outside AI service (Groq, Gemini) **only** when `CLOUD_AI_CONFIRMED=true` outside dev and test; otherwise the local model reads them. | `ai/registry.py` |
| Grievance officer | `GRIEVANCE_OFFICER` and `GRIEVANCE_EMAIL` in `.env` show on the notice. | `config.py` |
| Audit | Every request, lookup, erase, close and daily run is in the audit log, with phone numbers masked. | `audit_log` |

## What the owner must do before real data

1. **Set the grievance contact** in `.env`: `GRIEVANCE_OFFICER`, `GRIEVANCE_EMAIL`. The notice shows it. Name one real person who reads that mailbox.
2. **Confirm the periods with the client and counsel**: 8 years for receiver details and photos (a common tax record horizon), 30 days for GPS, 180 days for declined requests. Change with `RETENTION_YEARS`, `TRACKING_RETENTION_DAYS`, `REQUEST_RETENTION_DAYS`.
3. **Decide the AI route.** Either keep the local model (no photo leaves the building) or pay for a provider tier whose terms say your inputs are not used for training, then set `CLOUD_AI_CONFIRMED=true`. A free tier usually allows training on inputs: do not use it for real PODs.
4. **Have counsel read the notice** (`web/src/lib/i18n/en.ts`, keys `priv.*`; Hindi and Marathi next to it) and the consent line on the request form.
5. **Sign data processing terms** with the services that touch personal data: WhatsApp (Meta), Twilio, the email host, Google (Maps), the AI provider, the hosting provider and the backup provider.
6. **Keep the register**: the **Privacy requests** screen is the record that requests were answered. Reply within the target; if you cannot answer a person, tell them they may complain to the Data Protection Board of India.

## Breach response (runbook)

A personal data breach is any loss, leak or unauthorised access to personal data (a stolen laptop, a leaked key, a database export sent to the wrong person, a hacked account).

1. **Contain (first hour).** Revoke the leaked key or password (change `JWT_SECRET` to end every session; rotate the provider keys in `.env`); deactivate the account involved (Setup); stop the service if data is still flowing out.
2. **Record.** Write down what, when, how it was found, which people and which kinds of data (receiver details, photos, driver licences, locations). The audit log (`audit_log`, image-view and login records) shows who opened what.
3. **Tell (within 72 hours of knowing, as the rules ask; confirm with counsel).** The **Data Protection Board of India**, and **each affected person** in plain language: what happened, what data, what you did, what they can do, who to call.
4. **Fix and learn.** Close the hole, add a test, note it in the audit log, and review the safeguards in `04-security-privacy.md`.

## What is deliberately not done

- No automatic erase on request: the officer checks who is asking and decides, because erasing is permanent and a stranger could ask to wipe someone else's data. The erase button does the whole job in one click once confirmed.
- Photos are not removed on a person's erase request: they are the proof for invoices that tax law makes the company keep. They go at the retention date.
- No children's data is collected. If that ever changes, the Act needs a parent's consent.
- Backups are not purged on erase; they expire with the backup rotation. Say so in the answer to the person.
