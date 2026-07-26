from pathlib import Path

from drive_stripper import scaffold
from drive_stripper.pipeline import process_file


def test_strip_mode_on_text_file_redacts_and_reports_matches(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("email jane@acme.com about Project SkyNet")
    dest = tmp_path / "notes.sanitized.txt"

    result = process_file(source, dest, mode="strip", custom_terms=["Project SkyNet"])

    assert result.matches_found == 2
    text = dest.read_text()
    assert "jane@acme.com" not in text
    assert "Project SkyNet" not in text
    assert result.mapping_path is None


def test_scaffold_mode_on_text_file_is_reversible(tmp_path: Path):
    source = tmp_path / "notes.txt"
    original = "email jane@acme.com about the launch"
    source.write_text(original)
    dest = tmp_path / "notes.sanitized.txt"
    mapping_path = tmp_path / "notes.map.json"

    result = process_file(
        source, dest, mode="scaffold", mapping_destination=mapping_path
    )

    assert result.mapping_path == mapping_path
    scaffolded_text = dest.read_text()
    assert "jane@acme.com" not in scaffolded_text

    # simulate the round trip through a frontier model that echoes the text back unchanged
    model_response = scaffolded_text
    mapping = scaffold.load_mapping(mapping_path)
    restored = scaffold.restore(model_response, mapping)
    assert restored == original


def test_metadata_only_mode_leaves_content_untouched(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("email jane@acme.com")
    dest = tmp_path / "notes.out.txt"

    result = process_file(source, dest, mode="metadata-only")

    assert result.matches_found == 0
    assert dest.read_text() == "email jane@acme.com"


def test_scaffold_mode_across_docx_paragraphs_keeps_tokens_unique(tmp_path: Path):
    from docx import Document

    source = tmp_path / "doc.docx"
    dest = tmp_path / "doc.sanitized.docx"
    mapping_path = tmp_path / "doc.map.json"

    doc = Document()
    doc.add_paragraph("reach jane@acme.com")
    doc.add_paragraph("or john@acme.com")
    doc.save(source)

    result = process_file(source, dest, mode="scaffold", mapping_destination=mapping_path)

    assert result.matches_found == 2
    mapping = scaffold.load_mapping(mapping_path)
    assert len(mapping) == 2  # tokens for both paragraphs are distinct, no collision

    sanitized = Document(str(dest))
    restored_paragraphs = [scaffold.restore(p.text, mapping) for p in sanitized.paragraphs]
    assert restored_paragraphs == ["reach jane@acme.com", "or john@acme.com"]
