# Text messages (Twilio)

CargoOne texts a hired driver their private link when the office creates it (Trips, **Send link**, with the driver's mobile filled in) and, with the **Remind drivers** button, texts a driver who still owes a proof of delivery. Until Twilio is set up the app uses a **simulated sender**: nothing leaves the machine, and the link dialog says "simulated". The link is always shown on screen, so the office can also paste it into WhatsApp.

## What to know first
- **The free trial balance is small.** CargoOne counts every real text in its audit log and stops at `SMS_MAX_TOTAL` (default 60), so the balance cannot be used up by accident. Tests never send (they force the simulated sender).
- **Trial accounts only text verified numbers.** In the Twilio console, add the phones you want to test with under *Verified Caller IDs*.
- **India needs a registered sender and template (DLT).** Until that is done, Twilio may refuse or filter texts to Indian numbers even from a paid account. When Twilio refuses, the dialog shows its reason and the link is still good: share it yourself. The wording in `api/app/notify/sms.py` (`TEMPLATES`) is what must be registered.

## Setup
1. Create a Twilio account and note the **Account SID** and **Auth Token** (Console home).
2. Get a Twilio number (or create a Messaging Service) that can send to India.
3. Put these in `.env` (never in git) and restart the API:

```
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=<account sid>
TWILIO_AUTH_TOKEN=<auth token>
TWILIO_FROM=+1XXXXXXXXXX              # or TWILIO_MESSAGING_SERVICE_SID=MG...
SMS_MAX_TOTAL=60
```

4. In Trips, press **Send link** on a trip, fill in **your own verified mobile**, and press **Create link and send SMS**. The dialog should say "SMS sent to the driver."

If `SMS_PROVIDER=twilio` is set but a key is missing, the app stays on the simulated sender; it never pretends to send.
