# Tally Prime connection

Billing can push an invoice into Tally as a **Sales voucher** with one click (**Push to Tally** on the Invoices tab). The older **XML** download is still there for a Tally on another machine.

## Set up

1. In Tally Prime open the company, then **F1 Help > Settings > Connectivity** and make sure Tally acts as a server on port **9000** (the API explorer page at tallysolutions.com/tallyprime-api-explorer walks through it).
2. In `.env` (all optional, shown with their defaults):
   ```
   TALLY_URL=http://localhost:9000
   TALLY_COMPANY=            # leave empty when only one company is open
   TALLY_SALES_LEDGER=Freight Income
   ```
3. Restart the API. Billing > Invoices shows **Tally is connected: <company>**, or why it is not.

The API server must be able to reach Tally's address. On one development machine that is `localhost`. A hosted server cannot see a Tally on someone's desk: that needs Tally on a reachable machine (or a small connector running next to Tally), which is not built yet.

## What a push does

- Finds the company (the only open one, or `TALLY_COMPANY`).
- **Looks for a voucher with the same Reference (our invoice number) first.** Tally does not refuse duplicates (the same voucher sent twice is created twice), so a second click finds the first and adds nothing.
- If the party ledger (the client's Tally ledger name, else the client name) or the sales ledger is missing, it asks first, then creates the party under *Sundry Debtors* and the sales ledger under *Sales Accounts*. Nothing is created in Tally without that yes.
- Sends one Sales voucher: party Dr, sales ledger Cr, for the invoice total, narration listing the LRs. No GST lines yet.
- Records the push on the invoice (button turns to **In Tally - <voucher no>**) and in the audit log.

## Things Tally does that matter

- **Voucher number:** a Sales voucher type on auto-numbering ignores the number we send and uses its own (e.g. 41). Our invoice number is saved in the voucher's **Reference** field, and that is what the duplicate check uses. To make the numbers match, set the Sales voucher type to manual numbering in Tally.
- **Dates:** a voucher must fall inside the company's financial period. If the invoice date does not, the screen asks for another date (the voucher is then booked on that date; the Reference still carries the invoice number).
- **Educational mode** only accepts the **1st, 2nd and last day of a month**. For a demo, pick one of those and make sure the company's period includes it. A company created for 2026-27 (1 Apr 2026 to 31 Mar 2027) with a voucher date of 30 Nov 2026 works.
- Tally answers HTTP 200 even when it refuses; the reason comes back in its answer and is shown on the screen.
- A ledger that has had a voucher cannot be deleted from Tally through this connection.

## Demonstrating it

1. Tally open with the demo company (period covering the demo date).
2. CargoOne: capture and verify a POD, **Billing > Create invoice**.
3. **Push to Tally** (pick the voucher date if asked; say yes to creating the client's ledger).
4. In Tally: Display More Reports > Day Book (or Gateway > Display > Account Books > Sales Register) on that date shows the voucher, party and amount.
5. Click **Push to Tally** again: it says it is already in Tally and nothing is added.
