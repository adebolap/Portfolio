"""OCR-based detection and visual redaction of text baked into image pixels.

A screenshot or scanned document can carry proprietary text (an email in a
chat screenshot, a server name in a terminal capture) that no metadata
strip or file-format parser will ever see, because it's pixels, not text.
This module uses Tesseract (via pytesseract) to find that text and its
on-image location, then paints over the matched regions.

This only supports permanent visual redaction, not scaffolding: there's no
meaningful way to give a frontier model a "placeholder" for pixels and
restore the original ones afterward, since the model only ever sees the
image, not a reversible text token.

Requires the Tesseract OCR engine to be installed separately (e.g. `apt
install tesseract-ocr` / `brew install tesseract`) - it is not a Python
dependency and cannot be installed via pip alone.
"""

from __future__ import annotations

from pathlib import Path

from . import proprietary


class TesseractNotAvailableError(RuntimeError):
    """Raised when the Tesseract OCR binary isn't installed on the system."""


def is_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _require_tesseract() -> None:
    if not is_available():
        raise TesseractNotAvailableError(
            "Tesseract OCR is not installed. Install the 'tesseract-ocr' system "
            "package (e.g. `apt install tesseract-ocr` or `brew install tesseract`) "
            "to scan text embedded in image pixels."
        )


def extract_text(image_path: Path) -> str:
    """OCR every line of text found in the image, newline-joined."""
    _require_tesseract()
    import pytesseract
    from PIL import Image

    with Image.open(image_path) as img:
        return pytesseract.image_to_string(img)


def redact_image_text(
    source: Path,
    destination: Path,
    categories: tuple[str, ...] | None = None,
    custom_terms: list[str] | None = None,
) -> int:
    """Black out any proprietary text detected in the image via OCR.

    Matches are found per text line (so a multi-word match like an email
    isn't missed by scanning word-by-word), then mapped back to the
    individual word bounding boxes that overlap the match before painting
    over them. Returns the number of word regions redacted.
    """
    _require_tesseract()
    import pytesseract
    from PIL import Image, ImageDraw

    with Image.open(source) as opened:
        img = opened.convert("RGB")

    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    n = len(data["text"])

    lines: dict[tuple[int, int, int], list[int]] = {}
    for i in range(n):
        if not data["text"][i].strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(i)

    draw = ImageDraw.Draw(img)
    redacted = 0
    for indices in lines.values():
        words = [data["text"][i] for i in indices]
        line_text = " ".join(words)
        matches = proprietary.detect(line_text, categories, custom_terms)
        if not matches:
            continue

        offsets = []
        pos = 0
        for word in words:
            offsets.append((pos, pos + len(word)))
            pos += len(word) + 1  # +1 for the joining space

        for match in matches:
            for idx, (start, end) in zip(indices, offsets):
                if start < match.end and end > match.start:  # spans overlap
                    x, y = data["left"][idx], data["top"][idx]
                    w, h = data["width"][idx], data["height"][idx]
                    draw.rectangle([x, y, x + w, y + h], fill="black")
                    redacted += 1

    img.save(destination)
    return redacted
