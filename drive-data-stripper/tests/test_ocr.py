from pathlib import Path

import pytest

from drive_stripper import ocr

pytestmark = pytest.mark.skipif(not ocr.is_available(), reason="tesseract OCR binary not installed")


def _find_ttf() -> str | None:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def _render_text_image(path: Path, text: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    font_path = _find_ttf()
    font = ImageFont.truetype(font_path, 28) if font_path else ImageFont.load_default()
    img = Image.new("RGB", (700, 90), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), text, fill="black", font=font)
    img.save(path)


def test_extract_text_reads_rendered_text(tmp_path: Path):
    path = tmp_path / "shot.png"
    _render_text_image(path, "Contact jane.doe@acme.com now")
    assert "jane.doe@acme.com" in ocr.extract_text(path)


def test_redact_image_text_blacks_out_matched_region(tmp_path: Path):
    from PIL import Image

    source = tmp_path / "shot.png"
    dest = tmp_path / "shot.redacted.png"
    _render_text_image(source, "Contact jane.doe@acme.com now")

    redacted = ocr.redact_image_text(source, dest, categories=("email",))
    assert redacted >= 1

    # the email should no longer be recoverable via OCR from the redacted image
    assert "jane.doe@acme.com" not in ocr.extract_text(dest)
    # "Contact" and "now" were not matches, so pixels there should be unchanged
    with Image.open(source) as src_img, Image.open(dest) as dest_img:
        assert src_img.getpixel((15, 30)) == dest_img.getpixel((15, 30))
