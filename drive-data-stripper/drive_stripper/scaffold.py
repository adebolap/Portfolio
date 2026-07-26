"""Reversible scaffolding: swap sensitive spans for placeholder tokens.

Rather than deleting proprietary content outright, "scaffolding" replaces it
with a structurally meaningful placeholder (e.g. ``[[SCAFFOLD:email:0]]``) so
a frontier model can still reason about shape and relationships in the
document. The mapping back to the original values is written to a side file
that must stay local and never be sent to the model - it's only used
afterward, to restore the model's response.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .proprietary import Match, replace_spans

TOKEN_TEMPLATE = "[[SCAFFOLD:{label}:{index}]]"
_TOKEN_PATTERN = re.compile(r"\[\[SCAFFOLD:[^:\]]+:\d+\]\]")

_KDF_ITERATIONS = 390_000
_SALT_SIZE = 16


def apply_scaffold(
    text: str, matches: list[Match], index_offset: int = 0
) -> tuple[str, dict[str, str], int]:
    """Replace each match in ``text`` with a placeholder token.

    ``index_offset`` lets callers keep token indices globally unique when
    scaffolding several chunks of the same file (e.g. one call per
    paragraph or spreadsheet cell) so tokens never collide across chunks.

    Returns the scaffolded text, a ``{token: original_value}`` mapping to
    keep for :func:`restore`, and the next unused index.
    """
    mapping: dict[str, str] = {}

    def make_replacement(match: Match, index: int) -> str:
        token = TOKEN_TEMPLATE.format(label=match.label, index=index_offset + index)
        mapping[token] = match.value
        return token

    scaffolded = replace_spans(text, matches, make_replacement)
    return scaffolded, mapping, index_offset + len(matches)


def restore(text: str, mapping: dict[str, str]) -> str:
    """Swap scaffold tokens in ``text`` back to their original values."""
    restored = text
    for token, original in mapping.items():
        restored = restored.replace(token, original)
    return restored


def find_remaining_tokens(text: str) -> list[str]:
    """Tokens still present after a restore - signals a stale/mismatched mapping."""
    return _TOKEN_PATTERN.findall(text)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_KDF_ITERATIONS
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def save_mapping(mapping: dict[str, str], destination: Path, passphrase: str | None = None) -> None:
    """Persist a scaffold mapping to disk, encrypting it if a passphrase is given."""
    payload = json.dumps(mapping).encode("utf-8")
    if passphrase:
        salt = os.urandom(_SALT_SIZE)
        key = _derive_key(passphrase, salt)
        token = Fernet(key).encrypt(payload)
        destination.write_bytes(salt + token)
    else:
        destination.write_bytes(payload)


def load_mapping(source: Path, passphrase: str | None = None) -> dict[str, str]:
    """Load a scaffold mapping previously written by :func:`save_mapping`."""
    raw = source.read_bytes()
    if passphrase:
        salt, token = raw[:_SALT_SIZE], raw[_SALT_SIZE:]
        key = _derive_key(passphrase, salt)
        try:
            payload = Fernet(key).decrypt(token)
        except InvalidToken as exc:
            raise ValueError("Incorrect passphrase or corrupted mapping file.") from exc
    else:
        payload = raw
    return json.loads(payload.decode("utf-8"))
