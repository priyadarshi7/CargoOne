# WhatsApp setup (Meta Cloud API)

CargoOne sends WhatsApp messages to drivers (the app link on registration, a new trip, a change to a trip) to companies that ask for transport (request received, request update), and to clients and receivers about a shipment on the road (shipment update). Until the credentials below are set, the app runs in **recording mode**: every message is built, shown in **Setup > Messages** and marked "Not sent (not connected)", and the Setup screen also shows the one-time link so the office can hand it over by their own WhatsApp (an "Open in WhatsApp" button prepares the message). Nothing leaves the machine in this mode.

## One-time setup (by the owner, about a day plus Meta's approval time)

1. Create a **Meta Business** account (business.facebook.com) and verify the business. Company A's legal name and a document are needed.
2. In **developers.facebook.com** create an app of type *Business*, add the **WhatsApp** product, and add a phone number for the business. This must be a number that is **not already used on a personal WhatsApp** (a new SIM or a landline works). Verify it by the code Meta sends.
3. In **WhatsApp Manager > Message templates** create the six templates below, in each of the three languages, category **Utility**. Copy the text exactly: the order and number of `{{n}}` variables must match what the app sends. Approval usually takes minutes to a day.
4. Create a **System User** with a permanent access token that has `whatsapp_business_messaging` permission, and note the **Phone number ID** (WhatsApp > API setup).
5. Put these in the settings file (`.env`, never in git) and restart the API:

```
WHATSAPP_PROVIDER=meta
WHATSAPP_TOKEN=<permanent access token>
WHATSAPP_PHONE_NUMBER_ID=<phone number id>
# optional: WHATSAPP_API_VERSION=v21.0   WHATSAPP_TEMPLATE_PREFIX=cargoone
# a template name can be changed without code (Meta will not let you reuse a deleted name for a while):
# WHATSAPP_TEMPLATE_WELCOME=cargoone_driver_account   (also _TRIP_ASSIGNED, _TRIP_UPDATE, _REQUEST_RECEIVED, _REQUEST_UPDATE, _SHIPMENT_UPDATE)
```

6. Register a driver with your own phone number (and submit a test transport request) and check **Setup > Messages**: the status should say **Sent**. If it says **Failed**, the reason (Meta's error code) is shown next to it; the usual causes are a template that is not approved yet in that language, a wrong phone number ID, or an expired token.

If `WHATSAPP_PROVIDER=meta` is set but a credential is missing, the app logs a warning and stays in recording mode: it never pretends to send.

## If Meta rejects a template or files it as Marketing

Meta approves **Utility** only for plain notices about something that already happened to the person. The texts below are written for that: no "welcome" or selling words, and a sentence after every link because a variable may not be the very first or last thing in the body. If one is still rejected or reclassified, do not argue the category: keep it as submitted and change the words (shorter, more factual), then change the same words in `TEXT` in `api/app/notify/whatsapp.py` so the app sends exactly what Meta approved. Give Meta a realistic **sample value** for every variable when you create the template. Hindi and Marathi are submitted as separate translations of the same template name.

## The templates

### `cargoone_driver_account`

Sent when a driver is registered (and when the office sends the link again). Category: **Utility**. Variables in order: {{1}} = name, {{2}} = link.

**English (`en`)**

```
Hello {{1}}, your driver account on CargoOne has been created by your company. Please open this link to finish your registration: {{2}} The link can be used once and expires in 72 hours.
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, आपकी कंपनी ने CargoOne पर आपका ड्राइवर खाता बना दिया है। अपना रजिस्ट्रेशन पूरा करने के लिए कृपया यह लिंक खोलें: {{2}} यह लिंक एक ही बार चलेगा और 72 घंटे में ख़त्म हो जाएगा।
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, तुमच्या कंपनीने CargoOne वर तुमचे ड्रायव्हर खाते तयार केले आहे. तुमची नोंदणी पूर्ण करण्यासाठी कृपया ही लिंक उघडा: {{2}} ही लिंक एकदाच वापरता येईल आणि 72 तासांत संपेल.
```

Sample values for Meta's review: `Ramesh Patil` | `https://app.example.com/onboard/abc123`

### `cargoone_trip_assigned`

Sent when a trip is given to a driver. Category: **Utility**. Variables in order: {{1}} = name, {{2}} = trip_code, {{3}} = lr, {{4}} = route, {{5}} = vehicle, {{6}} = start, {{7}} = link.

**English (`en`)**

```
Hello {{1}}, a trip has been assigned to you. Trip {{2}}, LR number {{3}}. Route: {{4}}. Truck: {{5}}. Start: {{6}}. Open the trip here: {{7}} Please check the details before you leave.
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, आपको एक ट्रिप दी गई है। ट्रिप {{2}}, LR नंबर {{3}}। रूट: {{4}}। ट्रक: {{5}}। शुरू: {{6}}। ट्रिप यहाँ खोलें: {{7}} निकलने से पहले विवरण जाँच लें।
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, तुम्हाला एक ट्रिप दिली आहे. ट्रिप {{2}}, LR क्रमांक {{3}}. मार्ग: {{4}}. ट्रक: {{5}}. सुरू: {{6}}. ट्रिप येथे उघडा: {{7}} निघण्यापूर्वी तपशील तपासा.
```

Sample values for Meta's review: `Ramesh Patil` | `TRP-70012` | `LR/MH20/26-27/000123` | `Chhatrapati Sambhajinagar - Nagpur` | `MH20 EL 4521` | `12 Nov, 08:00` | `https://app.example.com/driver?trip=abc123`

### `cargoone_trip_update`

Sent when the driver's trip is cancelled, moved to another driver, or its truck/time changes. Category: **Utility**. Variables in order: {{1}} = name, {{2}} = trip_code, {{3}} = change, {{4}} = link.

**English (`en`)**

```
Hello {{1}}, there is an update for your trip {{2}}: {{3}}. See the details here: {{4}} Please check them before you leave.
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, आपकी ट्रिप {{2}} में बदलाव हुआ है: {{3}}। विवरण यहाँ देखें: {{4}} निकलने से पहले जाँच लें।
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, तुमच्या ट्रिप {{2}} मध्ये बदल झाला आहे: {{3}}. तपशील येथे पहा: {{4}} निघण्यापूर्वी तपासा.
```

Sample values for Meta's review: `Ramesh Patil` | `TRP-70012` | `has changed: truck is now MH20 GT 7718` | `https://app.example.com/driver?trip=abc123`

### `cargoone_request_received`

Sent to a company right after it submits the public transport request form. Category: **Utility**. Variables in order: {{1}} = name, {{2}} = reference, {{3}} = link.

**English (`en`)**

```
Hello {{1}}, we have received your transport request {{2}}. You can follow its status here: {{3}} We will reply shortly.
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, आपका ट्रांसपोर्ट अनुरोध {{2}} हमें मिल गया है। इसकी स्थिति यहाँ देखें: {{3}} हम जल्द जवाब देंगे।
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, तुमची वाहतूक विनंती {{2}} आम्हाला मिळाली आहे. तिची स्थिती येथे पहा: {{3}} आम्ही लवकरच उत्तर देऊ.
```

Sample values for Meta's review: `Anil Mehta` | `REQ-1001` | `https://app.example.com/request/REQ-1001.abc123`

### `cargoone_request_update`

Sent to a company when its request is accepted, booked as a trip, or declined. Category: **Utility**. Variables in order: {{1}} = name, {{2}} = reference, {{3}} = update, {{4}} = link.

**English (`en`)**

```
Hello {{1}}, there is an update on your transport request {{2}}: {{3}}. See the details here: {{4}} Thank you for your patience.
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, आपके ट्रांसपोर्ट अनुरोध {{2}} की जानकारी: {{3}}। विवरण यहाँ देखें: {{4}} आपके धैर्य के लिए धन्यवाद।
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, तुमच्या वाहतूक विनंती {{2}} बद्दल माहिती: {{3}}. तपशील येथे पहा: {{4}} तुमच्या संयमाबद्दल धन्यवाद.
```

Sample values for Meta's review: `Anil Mehta` | `REQ-1001` | `booked as trip TRP-70012, pickup 12 Nov, 08:00` | `https://app.example.com/request/REQ-1001.abc123`

### `cargoone_shipment_update`

Sent to the client, and to the receiver (the consignee), at each step of a shipment: truck assigned, plan changed, started, running late, breakdown, moving again, delivered, proof checked, invoice issued, payment received, cancelled, and when the office sends the tracking link again. The receiver never gets the money steps. Category: **Utility**. Variables in order: {{1}} = name, {{2}} = trip_code, {{3}} = update, {{4}} = link. The `{{3}}` text is written by the app in the same language as the template (the client's language), so submit all three languages under this one name.

**English (`en`)**

```
Hello {{1}}, there is an update on your shipment {{2}}: {{3}}. Follow it here: {{4}} Thank you for your patience.
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, आपकी खेप {{2}} की जानकारी: {{3}}। यहाँ देखते रहें: {{4}} आपके धैर्य के लिए धन्यवाद।
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, तुमच्या मालाची खेप {{2}} बद्दल माहिती: {{3}}. येथे पाहत रहा: {{4}} तुमच्या संयमाबद्दल धन्यवाद.
```

Sample values for Meta's review: `Anil Mehta` | `TRP-70012` | `the truck has left and your goods are on the way` | `https://app.example.com/s/TRP-70012.c0.abc123`

Without this template every shipment message fails with Meta error `#132001` ("Template name does not exist in the translation"), and the client and receiver get nothing on WhatsApp (the receiver's email still goes). The Hindi and Marathi translations must be approved too, or clients set to those languages fail the same way.

## What this does not do (yet)

- **Delivery and read receipts.** "Sent" means Meta accepted the message. Whether the driver's phone received or opened it needs a webhook that Meta calls back; that is a later addition.
- **Replies.** A driver answering the message is not read by the app. Drivers act inside the app, not by chatting.
- **Opt-out.** Messages are operational (their own trips and app access), sent to the number the office registered for them. If you later add anything promotional, add an opt-in and an opt-out first (DPDP).
- **Cost.** Meta charges per conversation/template message after a free monthly allowance; check the current price list for India before going live.
- **A fallback channel.** If WhatsApp is down or the driver has no WhatsApp, the in-app notification, the on-screen link, and the office-read PIN are the fallbacks. SMS is still the recording-only mock.
