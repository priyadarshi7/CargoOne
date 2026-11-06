# The shipment workflow, from order to closing

One shipment has one timeline. Everyone sees the part that is theirs. This is what the software does at each step and who does it.

## 1. Order

- A new company asks on the public form (`/request`). A client that already exists signs in at `/login` with the email the ops head made for them (Setup, Clients, **Logins**). The person is emailed a one-time link (72 hours) to choose their own password, so no password is ever shown or sent; if the email cannot be sent, the dialog shows the link to pass on another way. Reset password works the same way and ends their open sessions and asks for a truck from `/portal/new`: the route and the goods only, because the company is already known. A phone number is asked for only if none is saved.
- Ops accepts the request, with a quote if they want one. The requester sees the quote on their request page and says **yes or no** there. A yes lets the office book the trip; a no closes the request. If they say yes on the phone, ops records that ("Client said yes by phone"). A trip cannot be booked from a quoted request before a yes.
- Booking creates the trip with its LR number, the quote as the freight, and the e-way bill with its validity. A trip needs a start time; a start in the past, more than a year ahead, or a trip longer than 60 days is refused; the e-way bill must cover the trip and can be on only one live trip.

## 2. Dispatch

- Ops assigns a truck and driver (papers, capacity and clashes are checked). The driver is told in the app and by WhatsApp. The client is told a truck is assigned.
- When the driver opens the job, the office sees "Driver has seen the job" (Trips, click the trip code).
- Changing the truck, driver or time, or cancelling, needs a reason. The driver and the client are told.

## 3. Loading

- The driver taps **Truck is loaded** and takes a photo of the loaded truck and the LR. It is saved on the phone first and sent when there is network. Only then does **Start trip** work, and only from 3 hours before the planned start, and never while the truck or driver is still on another trip. The office can start a trip for a driver, and can confirm loading without a photo if it says why.

## 4. In transit

- The shipment page (`/s/...`) shows progress, the timeline, the live position (rounded to about 100 m) and an arrival estimate.
- The driver reports a delay or a truck problem in a few taps (reasons, no typing). The client and receiver are told. If the estimate passes the planned end, or the e-way bill's validity, the timeline says so, once every 3 hours.

## 5. Delivery

- Planning requires the consignee's name, phone and email (the link and the delivery code have nowhere to go without them; imports and old trips may lack them). The receiver's link goes by WhatsApp to their phone and by email too (same link, same messages; the private part is masked in the log). Email needs the SMTP settings in `.env`.
- The delivery photo carries its proof with it: the app adds a dark strip below the picture (never over the paper) with "CargoOne", the date and time in Indian time and the GPS position. The time is the server's clock, not the phone's (the app learns the difference when it can reach the server; offline it uses the phone clock and prints "(phone clock)"). The AI is told to ignore the strip. Loading photos and expense photos are not stamped yet.
- The receiver opens their shipment page and reads out the 4-digit **delivery code**. The driver enters it, and notes anything short or damaged. Five wrong tries lock it for 15 minutes. Only then can the proof-of-delivery photo be sent. A hired driver does the same from the upload link.
- Only the office can deliver without the code, and must say why.
- The AI checks the photo as before: verified straight away, or sent to a person.

## 6. Billing

- A verified proof lands in the billing queue. A person makes the invoice (a draft), sends it to the client themselves, and marks it **sent**. The system never sends an invoice.
- The client's shipment page then shows the invoice; each step also sends a WhatsApp note.
- Payments are recorded against the invoice (amount, date, UTR or cheque number). Part payments are allowed; more than the balance, or a future date, is refused.

## 7. Close

- When the payments cover the total, the invoice is paid and its trips are **closed**: they cannot be cancelled or re-planned. Only an admin can undo a payment, with a reason, which reopens the trips. Every step is on the trip's timeline and in the audit log.

## Nothing falls between two people

Every step where one person acts and another must react shows up for the office, without anyone having to look for it. The ops dashboard's **Needs attention** list (and the numbers on the **Requests** sidebar item and in the browser tab) count:

| Where | What is waiting |
|---|---|
| Request | a new request; a client's **no** to the quote (with the reason, until someone reads it); a **yes** nobody has booked; a quote unanswered for 2 days |
| Trip, before it leaves | leaving within 2 days with no driver; a driver who has not opened a job starting within 12 hours; a trip an hour past its start that has not started |
| Trip, on the road | a breakdown not yet marked as moving again; a trip running late |
| Delivery | shortage or damage noted at the door and not yet invoiced; a POD missing or waiting for a person (as before) |
| Money | an invoice made but not marked sent (1 day); an invoice sent over 30 days ago and unpaid |
| Messages | a note to a client or driver that failed to send (last 3 days) |

When a client says **no** to a quote, the request shows who said no, when and why (also in its History). The office can **send a new quote**, which asks the client again, or **close** it. A request's own history is on its Details. A decline by the office is a different thing and is not re-opened that way. If a trip made from a request is **cancelled**, the request goes back to accepted (the agreed quote stands) and appears again as something to book.

## The pages and who sees what

| Page | Who | Sees |
|---|---|---|
| `/s/...` (client address) | the client | progress, timeline, map, price, proof photo, invoice and payment status |
| `/s/...` (receiver address) | the receiver | progress, timeline, map, the delivery code until it is entered; never a price or an invoice |
| `/portal` | a client login | all that client's shipments (each opens its shipment page) and requests; ask for a truck |
| `/request/...` | the requester | where the request stands; the quote and the yes or no |
| Trips, then the trip code | office | the whole timeline, loading photo, both addresses to copy or send |

Neither shipment address shows who is driving, other trips, or any phone number. The office can stop every address of a trip at once. WhatsApp notes are recorded in the message log; until WhatsApp is connected they are recorded as "not sent", and the office can use **Open WhatsApp** to send from their own phone.

## Settings

`ETA_SPEED_KMH` (40), `ETA_ROAD_FACTOR` (1.3), `LATE_GRACE_MIN` (30) and `START_EARLY_HOURS` (3) are in `api/app/config.py` and can be set in `.env`. The driver app shows the 3-hour start limit as a fixed value, so change both together.
