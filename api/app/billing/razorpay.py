"""Razorpay, the little we use: create an order for an invoice, check the payment that comes back, and read a payment from Razorpay itself.

The browser is never trusted about money. A payment counts only after (1) its signature checks out with our key secret and (2) Razorpay's own API says
that payment belongs to our order, is captured and is for the order's amount."""
import hashlib
import hmac
from decimal import Decimal

import httpx

from app.config import get_settings

API = "https://api.razorpay.com/v1"
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests put a fake Razorpay here


class RazorpayError(Exception):
    pass


def configured() -> bool:
    s = get_settings()
    return bool(s.razorpay_key_id and s.razorpay_key_secret)


def paise(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


async def _call(method: str, path: str, json: dict | None = None) -> dict:
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=20, transport=TRANSPORT, auth=(s.razorpay_key_id, s.razorpay_key_secret)) as http:
            r = await http.request(method, f"{API}{path}", json=json)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:  # the status only: the body can carry card details
        raise RazorpayError(f"Razorpay answered {e.response.status_code}") from None
    except httpx.HTTPError:
        raise RazorpayError("Razorpay could not be reached") from None


async def create_order(amount: Decimal, receipt: str, notes: dict[str, str]) -> dict:
    return await _call("POST", "/orders", {"amount": paise(amount), "currency": "INR", "receipt": receipt[:40], "notes": notes})


async def fetch_payment(payment_id: str) -> dict:
    return await _call("GET", f"/payments/{payment_id}")


async def capture(payment_id: str, amount: Decimal) -> dict:
    return await _call("POST", f"/payments/{payment_id}/capture", {"amount": paise(amount), "currency": "INR"})


def _same(expected: str, given: str) -> bool:
    return hmac.compare_digest(expected, given or "")


def checkout_signature_ok(order_id: str, payment_id: str, signature: str) -> bool:
    key = get_settings().razorpay_key_secret.encode()
    return _same(hmac.new(key, f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest(), signature)


def webhook_signature_ok(body: bytes, signature: str) -> bool:
    secret = get_settings().razorpay_webhook_secret
    return bool(secret) and _same(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), signature)
