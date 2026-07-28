"""Detection of proprietary / sensitive content inside a file's text.

Covers generic PII-ish patterns (emails, phone numbers, IP addresses) plus
common secret formats (cloud access keys, private key blocks, bearer
tokens), and lets callers layer on an organization's own vocabulary
(codenames, client names, internal hostnames) as literal terms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (label, compiled pattern) - order matters: more specific patterns first so
# a token like an AWS key isn't also reported as a generic id.
_BUILTIN_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "aws_access_key": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "generic_api_key": re.compile(
        r"\b(sk|pk|rk|api|key)[-_][A-Za-z0-9]{16,}\b", re.IGNORECASE
    ),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b"),
    "private_key_block": re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "phone": re.compile(r"\b\+?\d[\d\s().-]{7,}\d\b"),
    "credit_card": re.compile(r"\b\d(?:[ -]?\d){12,15}\b"),
}

DEFAULT_CATEGORIES = tuple(_BUILTIN_PATTERNS)


@dataclass(frozen=True)
class Match:
    label: str
    start: int
    end: int
    value: str
    confidence: str = "high"


def luhn_valid(digits: str) -> bool:
    """Checksum used by real card numbers - filters out arbitrary 13-16 digit runs."""
    if not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _custom_term_patterns(terms: list[str]) -> dict[str, re.Pattern]:
    patterns = {}
    for term in terms:
        term = term.strip()
        if not term:
            continue
        key = f"custom_term:{term}"
        patterns[key] = re.compile(re.escape(term), re.IGNORECASE)
    return patterns


def detect(
    text: str,
    categories: tuple[str, ...] | None = None,
    custom_terms: list[str] | None = None,
) -> list[Match]:
    """Find every proprietary/sensitive span in ``text``.

    ``categories`` restricts which built-in pattern types are scanned for
    (default: all of them). ``custom_terms`` are literal, case-insensitive
    strings supplied by the caller (company name, project codename, client
    names, ...).
    """
    active = {
        label: pattern
        for label, pattern in _BUILTIN_PATTERNS.items()
        if categories is None or label in categories
    }
    active.update(_custom_term_patterns(custom_terms or []))

    matches: list[Match] = []
    for label, pattern in active.items():
        for m in pattern.finditer(text):
            value = m.group()
            if label == "credit_card":
                digits = re.sub(r"[ -]", "", value)
                if len(digits) < 13 or not luhn_valid(digits):
                    continue  # fails the card checksum - almost certainly not a real card
            confidence = "medium" if label == "phone" else "high"
            matches.append(
                Match(label=label, start=m.start(), end=m.end(), value=value, confidence=confidence)
            )

    matches.sort(key=lambda m: m.start)
    return _drop_overlaps(matches)


def _drop_overlaps(matches: list[Match]) -> list[Match]:
    """Keep the first (leftmost, then longest) match when spans overlap."""
    kept: list[Match] = []
    last_end = -1
    for match in sorted(matches, key=lambda m: (m.start, -(m.end - m.start))):
        if match.start >= last_end:
            kept.append(match)
            last_end = match.end
    return kept


def redact(text: str, matches: list[Match]) -> str:
    """Permanently remove matched spans, replacing each with ``[REDACTED]``."""
    return replace_spans(text, matches, lambda match, index: "[REDACTED]")


def replace_spans(text: str, matches: list[Match], make_replacement) -> str:
    out = []
    cursor = 0
    for i, match in enumerate(sorted(matches, key=lambda m: m.start)):
        out.append(text[cursor:match.start])
        out.append(make_replacement(match, i))
        cursor = match.end
    out.append(text[cursor:])
    return "".join(out)
