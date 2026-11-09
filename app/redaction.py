"""PII / sensitive-data redaction before sending text to an LLM.

Responsible AI: never send raw IPs, phone numbers, or emails to a model
when it can be avoided. Redact first; analyze second.
"""

from __future__ import annotations

import re

# IPv4 (simple, covers most ops logs)
_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}" r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)

# Common private-range aware? Not needed — redact all IPv4 for privacy.

# Emails
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Phone-like sequences (CN mobile + general international-ish)
_PHONE = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}\b")

# MAC addresses
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")

# JWT-ish / long opaque tokens (conservative)
_TOKEN = re.compile(r"\b(?:Bearer\s+)?[A-Za-z0-9_-]{32,}\b")


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Return redacted text and a count of replacements by category.

    Order matters: emails before phones (emails contain digits),
    IPs before phones, MACs before generic tokens.
    """
    counts: dict[str, int] = {
        "email": 0,
        "ipv4": 0,
        "mac": 0,
        "phone": 0,
        "token": 0,
    }

    def _sub(pattern: re.Pattern[str], replacement: str, key: str, s: str) -> str:
        def repl(m: re.Match[str]) -> str:
            counts[key] += 1
            return replacement

        return pattern.sub(repl, s)

    out = text
    out = _sub(_EMAIL, "[REDACTED_EMAIL]", "email", out)
    out = _sub(_IPV4, "[REDACTED_IP]", "ipv4", out)
    out = _sub(_MAC, "[REDACTED_MAC]", "mac", out)
    out = _sub(_PHONE, "[REDACTED_PHONE]", "phone", out)
    out = _sub(_TOKEN, "[REDACTED_TOKEN]", "token", out)
    return out, counts
