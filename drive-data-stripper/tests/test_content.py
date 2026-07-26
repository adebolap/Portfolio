from pathlib import Path

from drive_stripper import content


def test_read_text_plain_file(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("hello world")
    assert content.read_text(path) == "hello world"


def test_read_text_returns_none_for_image(tmp_path: Path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"\xff\xd8\xff")  # not a valid jpeg, but suffix is enough for this check
    assert content.read_text(path) is None


def test_read_text_bim_file_treated_as_json_text(tmp_path: Path):
    path = tmp_path / "model.bim"
    path.write_text('{"name": "SalesModel", "owner": "jane@acme.com"}')
    assert content.read_text(path) == '{"name": "SalesModel", "owner": "jane@acme.com"}'
    assert content.is_text_extractable(path) is True


def test_write_docx_text_replaces_paragraph(tmp_path: Path):
    from docx import Document

    source = tmp_path / "doc.docx"
    dest = tmp_path / "doc.out.docx"
    doc = Document()
    doc.add_paragraph("contact jane@acme.com now")
    doc.save(source)

    content.write_docx_text(source, dest, lambda text: text.replace("jane@acme.com", "[REDACTED]"))

    result = Document(str(dest))
    assert result.paragraphs[0].text == "contact [REDACTED] now"


def test_write_xlsx_text_replaces_cell(tmp_path: Path):
    from openpyxl import Workbook, load_workbook

    source = tmp_path / "book.xlsx"
    dest = tmp_path / "book.out.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "jane@acme.com"
    wb.save(source)

    content.write_xlsx_text(source, dest, lambda text: text.replace("jane@acme.com", "[REDACTED]"))

    result = load_workbook(str(dest))
    assert result.active["A1"].value == "[REDACTED]"
