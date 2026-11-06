"""Shipment links: one private address per trip and audience.

`client` is the company that booked the trip (sees the price, the proof of delivery and the invoice); `receiver` is whoever takes the
goods (sees the delivery code, never a price). The address carries a signature only this server can make, so nothing is stored per link
and every message about the trip can carry the same working address. Raising the trip's `link_epoch` retires every link of that trip."""
import base64
import hashlib
import hmac

from app.config import get_settings
from app.models import Trip

AUDIENCES = {"c": "client", "r": "receiver"}


def _sig(trip_code: str, aud: str, epoch: int) -> str:
    key = hashlib.sha256(f"shipment:{get_settings().jwt_secret}".encode()).digest()
    raw = hmac.new(key, f"{trip_code}.{aud}{epoch}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")[:32]


def shipment_token(trip: Trip, audience: str) -> str:
    aud = "c" if audience == "client" else "r"
    return f"{trip.trip_code}.{aud}{trip.link_epoch}.{_sig(trip.trip_code, aud, trip.link_epoch)}"


def shipment_url(trip: Trip, audience: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/s/{shipment_token(trip, audience)}"


def parse(token: str) -> tuple[str, str, int, str] | None:
    """(trip_code, audience, epoch, signature) when the token is well formed (not yet proven genuine)."""
    parts = token.split(".")
    if len(parts) != 3 or not (4 <= len(parts[0]) <= 24) or len(parts[2]) < 20 or len(parts[1]) < 2 or parts[1][0] not in AUDIENCES or not parts[1][1:].isdigit():
        return None
    return parts[0], parts[1][0], int(parts[1][1:]), parts[2]


def genuine(trip: Trip, aud: str, epoch: int, sig: str) -> bool:
    return epoch == trip.link_epoch and hmac.compare_digest(_sig(trip.trip_code, aud, epoch), sig)
