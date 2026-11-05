"""Phone number hygiene shared by every screen that takes one. Indian mobile numbers are stored as the plain 10 digits
(the form people sign in with); +91 / 0 prefixes and spaces are accepted on the way in."""
import re

from fastapi import HTTPException, status

MOBILE = re.compile(r"[6-9]\d{9}")


def clean_phone(text: str) -> str:
    digits = re.sub(r"\D", "", text)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not MOBILE.fullmatch(digits):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a 10-digit Indian mobile number")
    return digits
