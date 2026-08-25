import hashlib
import re

# Compiled once at import time for performance
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(?<!\d)" r"(\+?1[\s\-.]?)?" r"(\(?\d{3}\)?[\s\-.]?)" r"\d{3}[\s\-.]?\d{4}" r"(?!\d)"
)
# Card numbers are commonly typed with spaces or dashes between groups
# ("4111 1111 1111 1111") — a plain digit-run pattern misses those and lets
# a full PAN through into storage and LLM prompts, violating the
# PII-sanitised-before-storage rule. `[- ]?` between each group covers the
# common groupings without over-matching unrelated long digit runs.
_CC_RE = re.compile(
    r"\b(?:4[0-9]{3}(?:[- ]?[0-9]{4}){2}[- ]?[0-9]{1,4}|"  # Visa (13/16/19)
    r"5[1-5][0-9]{2}(?:[- ]?[0-9]{4}){3}|"  # Mastercard
    r"3[47][0-9]{2}[- ]?[0-9]{6}[- ]?[0-9]{5}|"  # Amex
    r"3(?:0[0-5]|[68][0-9])[0-9](?:[- ]?[0-9]{4}){2}[- ]?[0-9]|"  # Diners
    r"6(?:011|5[0-9]{2})(?:[- ]?[0-9]{4}){3}|"  # Discover
    r"(?:2131|1800|35[0-9]{2})(?:[- ]?[0-9]{4}){2}[- ]?[0-9]{3})\b"  # JCB
)
# Bare 9-digit SSNs (no separators) are ambiguous with other numbers in free
# text, so this stays anchored to the standard dash/space-grouped format.
_SSN_RE = re.compile(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b")


def sanitise_pii(text: str) -> str:
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _CC_RE.sub("[CARD]", text)
    text = _SSN_RE.sub("[SSN]", text)
    return text


def hash_handle(handle: str) -> str:
    return hashlib.sha256(handle.lower().strip().encode()).hexdigest()
