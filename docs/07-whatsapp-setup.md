# WhatsApp setup (Meta Cloud API)

CargoOne sends WhatsApp messages to drivers (the app link on registration, a new trip, a change to a trip) and to companies that ask for transport (request received, request update). Until the credentials below are set, the app runs in **recording mode**: every message is built, shown in **Setup > Messages** and marked "Not sent (not connected)", and the Setup screen also shows the one-time link so the office can hand it over by their own WhatsApp (an "Open in WhatsApp" button prepares the message). Nothing leaves the machine in this mode.

## One-time setup (by the owner, about a day plus Meta's approval time)

1. Create a **Meta Business** account (business.facebook.com) and verify the business. Company A's legal name and a document are needed.
2. In **developers.facebook.com** create an app of type *Business*, add the **WhatsApp** product, and add a phone number for the business. This must be a number that is **not already used on a personal WhatsApp** (a new SIM or a landline works). Verify it by the code Meta sends.
3. In **WhatsApp Manager > Message templates** create the five templates below, in each of the three languages, category **Utility**. Copy the text exactly: the order and number of `{{n}}` variables must match what the app sends. Approval usually takes minutes to a day.
4. Create a **System User** with a permanent access token that has `whatsapp_business_messaging` permission, and note the **Phone number ID** (WhatsApp > API setup).
5. Put these in the settings file (`.env`, never in git) and restart the API:

```
WHATSAPP_PROVIDER=meta
WHATSAPP_TOKEN=<permanent access token>
WHATSAPP_PHONE_NUMBER_ID=<phone number id>
# optional: WHATSAPP_API_VERSION=v21.0   WHATSAPP_TEMPLATE_PREFIX=cargoone
```

6. Register a driver with your own phone number (and submit a test transport request) and check **Setup > Messages**: the status should say **Sent**. If it says **Failed**, the reason (Meta's error code) is shown next to it; the usual causes are a template that is not approved yet in that language, a wrong phone number ID, or an expired token.

If `WHATSAPP_PROVIDER=meta` is set but a credential is missing, the app logs a warning and stays in recording mode: it never pretends to send.

## The templates

### `cargoone_welcome`

Sent when a driver is registered (and when the office sends the link again). Category: **Utility**. Variables in order: {{1}} = name, {{2}} = link.

**English (`en`)**

```
Hello {{1}}, welcome to CargoOne. Set your PIN and install the driver app here: {{2}}
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, CargoOne में आपका स्वागत है। अपना PIN बनाने और ड्राइवर ऐप इंस्टॉल करने के लिए यहाँ खोलें: {{2}}
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, CargoOne मध्ये तुमचे स्वागत आहे. तुमचा PIN तयार करण्यासाठी आणि ड्रायव्हर अ‍ॅप इन्स्टॉल करण्यासाठी येथे उघडा: {{2}}
```

Sample values for Meta's review: `Ramesh Patil` | `https://app.example.com/onboard/abc123`

### `cargoone_trip_assigned`

Sent when a trip is given to a driver. Category: **Utility**. Variables in order: {{1}} = name, {{2}} = trip_code, {{3}} = lr, {{4}} = route, {{5}} = vehicle, {{6}} = start, {{7}} = link.

**English (`en`)**

```
Hello {{1}}, a new trip is assigned to you. Trip {{2}}, LR {{3}}. Route: {{4}}. Truck: {{5}}. Start: {{6}}. Open the app to see the details and start the trip: {{7}}
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, आपको नई ट्रिप दी गई है। ट्रिप {{2}}, LR {{3}}। रूट: {{4}}। ट्रक: {{5}}। शुरू: {{6}}। विवरण देखने और ट्रिप शुरू करने के लिए ऐप खोलें: {{7}}
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, तुम्हाला नवीन ट्रिप दिली आहे. ट्रिप {{2}}, LR {{3}}. मार्ग: {{4}}. ट्रक: {{5}}. सुरू: {{6}}. तपशील पाहण्यासाठी आणि ट्रिप सुरू करण्यासाठी अ‍ॅप उघडा: {{7}}
```

Sample values for Meta's review: `Ramesh Patil` | `TRP-70012` | `LR/MH20/26-27/000123` | `Chhatrapati Sambhajinagar - Nagpur` | `MH20 EL 4521` | `12 Nov, 08:00` | `https://app.example.com/driver?trip=abc123`

### `cargoone_trip_update`

Sent when the driver's trip is cancelled, moved to another driver, or its truck/time changes. Category: **Utility**. Variables in order: {{1}} = name, {{2}} = trip_code, {{3}} = change, {{4}} = link.

**English (`en`)**

```
Hello {{1}}, trip {{2}} {{3}}. Details: {{4}}
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, ट्रिप {{2}} {{3}}। विवरण: {{4}}
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, ट्रिप {{2}} {{3}}. तपशील: {{4}}
```

Sample values for Meta's review: `Ramesh Patil` | `TRP-70012` | `has changed: truck is now MH20 GT 7718` | `https://app.example.com/driver?trip=abc123`

### `cargoone_request_received`

Sent to a company right after it submits the public transport request form. Category: **Utility**. Variables in order: {{1}} = name, {{2}} = reference, {{3}} = link.

**English (`en`)**

```
Hello {{1}}, we have received your transport request {{2}}. You can follow it here: {{3}}
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, आपका ट्रांसपोर्ट अनुरोध {{2}} हमें मिल गया है। यहाँ देख सकते हैं: {{3}}
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, तुमची वाहतूक विनंती {{2}} आम्हाला मिळाली आहे. येथे पाहू शकता: {{3}}
```

Sample values for Meta's review: `Anil Mehta` | `REQ-1001` | `https://app.example.com/request/REQ-1001.abc123`

### `cargoone_request_update`

Sent to a company when its request is accepted, booked as a trip, or declined. Category: **Utility**. Variables in order: {{1}} = name, {{2}} = reference, {{3}} = update, {{4}} = link.

**English (`en`)**

```
Hello {{1}}, update on your transport request {{2}}: {{3}}. Details: {{4}}
```

**Hindi (`hi`)**

```
नमस्ते {{1}}, आपके ट्रांसपोर्ट अनुरोध {{2}} की जानकारी: {{3}}। विवरण: {{4}}
```

**Marathi (`mr`)**

```
नमस्कार {{1}}, तुमच्या वाहतूक विनंती {{2}} बद्दल माहिती: {{3}}. तपशील: {{4}}
```

Sample values for Meta's review: `Anil Mehta` | `REQ-1001` | `booked as trip TRP-70012, pickup 12 Nov, 08:00` | `https://app.example.com/request/REQ-1001.abc123`

## What this does not do (yet)

- **Delivery and read receipts.** "Sent" means Meta accepted the message. Whether the driver's phone received or opened it needs a webhook that Meta calls back; that is a later addition.
- **Replies.** A driver answering the message is not read by the app. Drivers act inside the app, not by chatting.
- **Opt-out.** Messages are operational (their own trips and app access), sent to the number the office registered for them. If you later add anything promotional, add an opt-in and an opt-out first (DPDP).
- **Cost.** Meta charges per conversation/template message after a free monthly allowance; check the current price list for India before going live.
- **A fallback channel.** If WhatsApp is down or the driver has no WhatsApp, the in-app notification, the on-screen link, and the office-read PIN are the fallbacks. SMS is still the recording-only mock.
