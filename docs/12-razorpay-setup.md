# Razorpay setup (online invoice payment)

A client can pay an invoice from their login or private link with UPI, card or netbanking. Optional: without keys the button is hidden and billing records payments by hand as before.

## 1. Keys (enough to start)

1. Razorpay Dashboard, **Test mode**, Account & Settings, API keys, Generate. You get a **Key Id** (`rzp_test_...`) and a **Key Secret**.
2. Put them in `.env` (never in git, never in chat):
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
   RAZORPAY_KEY_SECRET=xxxxxxxx
   ```
3. Restart the API. A sent, unpaid invoice now shows **Pay ₹X online**.

The Key Id is sent to the browser (it is public by design). The secret stays on the server and signs/verifies every payment.

## 2. Try it

Use Razorpay's test UPI id `success@razorpay` or the test cards from their docs. The payment lands on the invoice as a payment with the Razorpay payment id (`pay_...`) as its reference, and the invoice becomes paid if it covers the total. Failed test payments (`failure@razorpay`) change nothing.

## 3. Webhook (optional backup, needs a public address)

If a client pays and closes the tab before the page hears back, the webhook still records it. It cannot reach `localhost`, so set it up when deployed (or with a tunnel while testing):

1. Dashboard, Settings, Webhooks, Add: URL `https://<your host>/api/webhooks/razorpay` (the path your proxy gives the API), events **payment.captured** and **order.paid**.
2. Razorpay asks you to type a **secret**. Make one up (long, random) and put the same value in `.env` as `RAZORPAY_WEBHOOK_SECRET`. It is not issued by Razorpay and is not your key secret.

Until that is set, the webhook endpoint refuses everything.

## 4. Go live

Complete Razorpay KYC, generate **Live** keys (`rzp_live_...`), replace the two values, restart. Check that payment capture is automatic (Settings, Payment capture); if not, the server captures an authorized payment itself.

## What is guaranteed

- The amount is set by the server from the invoice balance, never by the browser.
- A payment counts only after the signature verifies and Razorpay's API confirms it is captured, for this order and amount.
- It is applied once, however often it is reported. Money that arrives after the invoice was already settled is not added: it shows in Needs attention (online payment to refund or fix) for a person to refund in Razorpay.
- Refunds are done in the Razorpay dashboard; they are not reflected in CargoOne automatically yet.
