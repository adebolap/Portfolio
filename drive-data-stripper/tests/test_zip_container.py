import zipfile
from pathlib import Path

from drive_stripper import zip_container


def _make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _read_member(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as zf:
        return zf.read(name)


def test_rewrites_only_allow_listed_json_parts(tmp_path: Path):
    source = tmp_path / "pkg.zip"
    binary_blob = bytes(range(256)) * 4  # deliberately not valid text
    _make_zip(
        source,
        {
            "Connections": b'{"server": "jane@acme.com"}',
            "DataModel": binary_blob,
            "Other/Ignored.json": b'{"server": "jane@acme.com"}',
        },
    )
    dest = tmp_path / "pkg.out.zip"

    changed = zip_container.process_json_parts(
        source, dest, {"Connections"}, lambda text: text.replace("jane@acme.com", "[REDACTED]")
    )

    assert changed == 1
    assert b"[REDACTED]" in _read_member(dest, "Connections")
    assert b"jane@acme.com" not in _read_member(dest, "Connections")
    # not in the allow-list - copied through untouched even though it's valid JSON
    assert _read_member(dest, "Other/Ignored.json") == b'{"server": "jane@acme.com"}'
    # binary member is always byte-for-byte unchanged
    assert _read_member(dest, "DataModel") == binary_blob


def test_refuses_to_write_back_if_transform_breaks_json(tmp_path: Path):
    source = tmp_path / "pkg.zip"
    _make_zip(source, {"Connections": b'{"server": "jane@acme.com"}'})
    dest = tmp_path / "pkg.out.zip"

    # a transform that corrupts JSON structure (e.g. leaves a dangling quote)
    changed = zip_container.process_json_parts(
        source, dest, {"Connections"}, lambda text: text.replace('"jane@acme.com"', "jane")
    )

    assert changed == 0
    assert _read_member(dest, "Connections") == b'{"server": "jane@acme.com"}'


def test_non_json_text_member_is_left_untouched(tmp_path: Path):
    source = tmp_path / "pkg.zip"
    _make_zip(source, {"Connections": b"not json at all"})
    dest = tmp_path / "pkg.out.zip"

    changed = zip_container.process_json_parts(
        source, dest, {"Connections"}, lambda text: text.upper()
    )

    assert changed == 0
    assert _read_member(dest, "Connections") == b"not json at all"
