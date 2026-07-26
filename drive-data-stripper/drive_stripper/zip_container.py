"""Text-safe rewriting of ZIP-based container formats.

Formats like Power BI's .pbix/.pbit bundle many parts into one ZIP archive,
most of which are compressed binary data this tool has no way to safely
parse or rewrite (Power BI's Vertipaq/xVelocity data model in particular).
Rather than guess at what's text and what's binary, callers pass an explicit
allow-list of part names known to be plain JSON; every other part - the
imported data model included - is copied through byte-for-byte unchanged.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


def _decode(raw: bytes) -> str | None:
    for encoding in ("utf-8-sig", "utf-16-le"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def process_json_parts(
    source: Path, destination: Path, part_names: set[str], transform
) -> int:
    """Rewrite the members of a ZIP archive named in ``part_names`` via ``transform(str) -> str``.

    A part is only rewritten if it (a) is in ``part_names``, (b) decodes
    cleanly as text, and (c) still parses as valid JSON after the transform
    runs. If any of that fails, the part is left byte-for-byte unchanged
    rather than risking a corrupted package. Returns the number of parts
    actually changed.
    """
    changed = 0
    with zipfile.ZipFile(source, "r") as zin:
        infos = zin.infolist()
        contents = {info.filename: zin.read(info.filename) for info in infos}

    for name in part_names & contents.keys():
        raw = contents[name]
        text = _decode(raw)
        if text is None:
            continue
        try:
            json.loads(text)
        except ValueError:
            continue
        new_text = transform(text)
        if new_text == text:
            continue
        try:
            json.loads(new_text)
        except ValueError:
            continue  # transform broke the JSON structure - refuse to write it back
        contents[name] = new_text.encode("utf-8")
        changed += 1

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in infos:
            zout.writestr(info, contents[info.filename])

    return changed
