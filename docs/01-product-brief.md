# Product brief (from client)

**Client:** Company A, Chhatrapati Sambhajinagar, MH. FTL transporter (cement, steel, packaged goods). 140 own + ~200 hired trucks, 210 staff, ₹75–90 Cr revenue.

**Problem:** Signed LR/POD returns 10–20 days after delivery; WhatsApp photos get lost; Tally billing waits on POD.
Cost ≈ ₹1.02 Cr/yr: ₹38.9L working-capital interest (₹84.48 Cr × 14/365 = ₹3.24 Cr at 12%) + ₹63.36L lost/disputed POD freight (396 × ₹16,000).

**Users:** Drivers (basic phones, low literacy), billing executives, operations head; MD signs the deal.

## Must have
1. Driver app: one big button, photo POD, GPS + time stamp
2. SMS upload link for hired drivers (no install)
3. AI POD check: LR no., consignee stamp, quantity, shortage/damage remarks, date, signature; retake prompt
4. Billing queue of verified trips by client & cycle; Tally export; POD images attached to invoices
5. Dashboard: trips without POD, POD-to-invoice days by branch; client link to view PODs
6. Daily trip import with LR + e-way bill numbers

## Core slice (6–8 screens)
Driver capture → AI check/retake → review queue → billing queue + export → missing-POD dashboard.
Hard part: offline capture + compressed upload. Mock external systems; seed from sample data.

## Out of scope
Live GPS tracking, trip planning, fuel/driver expenses.

## AI rules
Image = source of truth · shortage/damage/low confidence → exec review (fields editable) · no auto-sent invoices · retakes ≤ 2.

## Constraints
Trip↔e-way bill link · icons + Hindi/Marathi voice, no typing · offline + <300 KB images · DPDP Act 2023 for consignee PII.

## Sample data
| Trip | Client | Vehicle | To | Freight ₹ | POD status | Remarks |
|---|---|---|---|---|---|---|
| TRP-66120 | Company B (cement) | MH20 EL 4521 | Nagpur | 38500 | Verified | – |
| TRP-66134 | Company C (steel) | MH20 GT 7718 | Pune | 26000 | Retake requested | Stamp not visible |
| TRP-66141 | Company D (packaged foods) | MH17 BY 3092 (hired) | Indore | 41200 | Needs review | Short by 6 cartons |

## Status (2026-11-09)
All must-haves and the core slice are built and tested; the out-of-scope items (live GPS, trip planning, fuel and expenses) are built too. What remains is proof on real PODs, owner steps for DPDP and go-live work. See `02-roadmap.md` (also shown live at `/progress`).
