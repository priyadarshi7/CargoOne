# Email setup (SMTP)

CargoOne emails the **companies that ask for transport** (request received, and every update: accepted, booked as a trip, declined), but only when they typed an email address on the request form. WhatsApp goes out too; email is the second channel. Drivers have no email, so they are not emailed.

Until the settings below are filled in, the app runs in **recording mode**: each email is built, shown in **Setup > Messages** as "Not sent (not connected)", and nothing leaves the machine.

## Option 1: Gmail (quickest for a pilot)

1. Use a Google account with **2-Step Verification** turned on (Google Account > Security).
2. Create an **app password**: Google Account > Security > 2-Step Verification > App passwords. Name it "CargoOne". Google shows 16 letters once. This is *not* your normal password.
3. Put these in `.env` (never in git), then restart the API:

```
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USER=youraddress@gmail.com
SMTP_PASSWORD=<the 16-letter app password, no spaces>
EMAIL_FROM=CargoOne <youraddress@gmail.com>
```

Gmail only sends as the signed-in mailbox, so `EMAIL_FROM` must use the same address as `SMTP_USER`. Gmail limits sending to about 500 messages a day, which is plenty for a pilot.

## Option 2: the company's own mail host

Ask whoever runs Company A's email for: the **SMTP host**, the **port** (587 with `starttls`, or 465 with `ssl`), a **user name** and **password** for a mailbox such as `desk@companya.example`. Use that address as `SMTP_USER` and in `EMAIL_FROM`. Set `SMTP_SECURITY=ssl` for port 465, `none` only on a trusted internal network.

## Check it works

Open **Setup > Messages**, type your own address in **Send a test email**, and press **Send test**. You should see "Sent. Check the inbox (and spam)". If it fails, the reason is shown, and the usual ones are:

| Message | What to fix |
|---|---|
| login refused (535) | wrong user name, or the normal password was used instead of an app password |
| sender address refused | `EMAIL_FROM` is not an address this mailbox may send as |
| could not connect | wrong host or port, or the security setting does not match the port (587 = `starttls`, 465 = `ssl`) |
| the address was refused | the recipient address does not exist |

If `EMAIL_PROVIDER=smtp` is set but the host or from address is missing, the app logs a warning and stays in recording mode: it never pretends to send.

## What to expect and what is not done

- **Spam folders.** Mail sent through a personal mailbox without SPF/DKIM for your own domain can land in spam. For better delivery later, move to a sending service on a domain you own (the sender sits behind one small interface, so that is a contained change).
- **The MD's weekly digest** is still a downloadable PDF, not an email.
- **No bounce handling.** A message the recipient's server rejects later is not reported back.
- **Privacy.** The log holds only a masked address (`a***@acme.example`) and the message text with the status link's secret part cut out. The password is only in `.env`.
