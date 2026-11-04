"""What counts as an acceptable password (office) or PIN (drivers). Pure functions, easy to test.

Drivers type a PIN on a phone, so it is short (4-8 digits) but must not be guessable at a glance. Office users get a
real password: 10+ characters, not purely digits, not their own email name, not an obvious word."""
import re

COMMON = {"password", "password1", "cargoone", "cargoone-dev", "1234567890", "qwertyuiop", "transport1", "welcome123"}


def check_secret(new: str, *, is_pin: bool, email: str | None = None) -> str | None:
    """Returns a plain-language problem, or None if acceptable."""
    if is_pin:
        if not re.fullmatch(r"\d{4,8}", new):
            return "A PIN is 4 to 8 digits."
        if len(set(new)) == 1 or new in "01234567890" or new in "98765432109":
            return "That PIN is too easy to guess (like 1111 or 1234). Pick another."
        return None
    if len(new) < 10:
        return "Use at least 10 characters."
    if len(new) > 128:
        return "That is too long (128 characters at most)."
    if new.isdigit():
        return "Add letters as well as digits."
    if new.lower() in COMMON or (email and new.lower().startswith(email.split("@")[0].lower()) and len(email.split("@")[0]) >= 4):
        return "That is too easy to guess. Avoid common words and your own name or email."
    return None
