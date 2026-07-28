import json
import zipfile
from pathlib import Path

from drive_stripper import scaffold
from drive_stripper.pipeline import process_file


def _make_pbix(path: Path) -> bytes:
    binary_blob = bytes(range(256)) * 8
    layout = json.dumps({"visuals": [{"title": "Owned by jane@acme.com"}]})
    connections = json.dumps({"server": "sql-prod-01.acme.internal", "user": "jane@acme.com"})
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Report/Layout", layout)
        zf.writestr("Connections", connections)
        zf.writestr("DataModel", binary_blob)  # the opaque, untouched binary model
    return binary_blob


def _read_member(path: Path, name: str) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read(name).decode("utf-8")


def test_pbix_strip_mode_redacts_json_parts_leaves_data_model_untouched(tmp_path: Path):
    source = tmp_path / "report.pbix"
    dest = tmp_path / "report.sanitized.pbix"
    binary_blob = _make_pbix(source)

    result = process_file(source, dest, mode="strip", categories=("email",))

    assert result.matches_found == 2
    assert "jane@acme.com" not in _read_member(dest, "Report/Layout")
    assert "jane@acme.com" not in _read_member(dest, "Connections")
    with zipfile.ZipFile(dest) as zf:
        assert zf.read("DataModel") == binary_blob
    # still valid, openable JSON after redaction
    json.loads(_read_member(dest, "Report/Layout"))
    json.loads(_read_member(dest, "Connections"))


def test_pbix_scaffold_mode_is_reversible(tmp_path: Path):
    source = tmp_path / "report.pbix"
    dest = tmp_path / "report.sanitized.pbix"
    mapping_path = tmp_path / "report.map.json"
    _make_pbix(source)

    result = process_file(
        source, dest, mode="scaffold", categories=("email",), mapping_destination=mapping_path
    )

    assert result.mapping_path == mapping_path
    mapping = scaffold.load_mapping(mapping_path)

    restored_layout = scaffold.restore(_read_member(dest, "Report/Layout"), mapping)
    restored_connections = scaffold.restore(_read_member(dest, "Connections"), mapping)
    assert "jane@acme.com" in restored_layout
    assert "jane@acme.com" in restored_connections
