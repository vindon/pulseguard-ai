import hashlib
import re

# Compiled once at import time for performance
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(?<!\d)" r"(\+?1[\s\-.]?)?" r"(\(?\d{3}\)?[\s\-.]?)" r"\d{3}[\s\-.]?\d{4}" r"(?!\d)"
)
_CC_RE = re.compile(
    r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|"
    r"3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|"
    r"(?:2131|1800|35\d{3})\d{11})\b"
)
_SSN_RE = re.compile(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b")


def sanitise_pii(text: str) -> str:
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _CC_RE.sub("[CARD]", text)
    text = _SSN_RE.sub("[SSN]", text)
    return text


def hash_handle(handle: str) -> str:
    return hashlib.sha256(handle.lower().strip().encode()).hexdigest()
