from pathlib import Path

import pytest

from drive_stripper import proprietary, scaffold


def test_apply_and_restore_roundtrip():
    text = "reach jane@acme.com or john@acme.com for access"
    matches = proprietary.detect(text, categories=("email",))
    scaffolded, mapping, next_offset = scaffold.apply_scaffold(text, matches)

    assert "jane@acme.com" not in scaffolded
    assert "john@acme.com" not in scaffolded
    assert next_offset == 2

    restored = scaffold.restore(scaffolded, mapping)
    assert restored == text


def test_index_offset_keeps_tokens_unique_across_chunks():
    chunk_a = "jane@acme.com"
    chunk_b = "john@acme.com"

    matches_a = proprietary.detect(chunk_a, categories=("email",))
    scaffolded_a, mapping_a, offset = scaffold.apply_scaffold(chunk_a, matches_a, index_offset=0)

    matches_b = proprietary.detect(chunk_b, categories=("email",))
    scaffolded_b, mapping_b, offset = scaffold.apply_scaffold(chunk_b, matches_b, index_offset=offset)

    combined = {**mapping_a, **mapping_b}
    assert len(combined) == 2  # no token collision between chunks
    assert scaffold.restore(scaffolded_a, combined) == chunk_a
    assert scaffold.restore(scaffolded_b, combined) == chunk_b


def test_find_remaining_tokens_reports_unmapped_tokens():
    text = "value is [[SCAFFOLD:email:0]] here"
    assert scaffold.find_remaining_tokens(text) == ["[[SCAFFOLD:email:0]]"]
    assert scaffold.find_remaining_tokens("no tokens here") == []


def test_mapping_roundtrip_plaintext(tmp_path: Path):
    mapping = {"[[SCAFFOLD:email:0]]": "jane@acme.com"}
    path = tmp_path / "map.json"
    scaffold.save_mapping(mapping, path)
    assert scaffold.load_mapping(path) == mapping


def test_mapping_roundtrip_encrypted(tmp_path: Path):
    mapping = {"[[SCAFFOLD:email:0]]": "jane@acme.com"}
    path = tmp_path / "map.enc"
    scaffold.save_mapping(mapping, path, passphrase="correct horse battery staple")
    assert scaffold.load_mapping(path, passphrase="correct horse battery staple") == mapping


def test_wrong_passphrase_raises(tmp_path: Path):
    mapping = {"[[SCAFFOLD:email:0]]": "jane@acme.com"}
    path = tmp_path / "map.enc"
    scaffold.save_mapping(mapping, path, passphrase="right-passphrase")
    with pytest.raises(ValueError):
        scaffold.load_mapping(path, passphrase="wrong-passphrase")
