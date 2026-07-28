from pathlib import Path

from drive_stripper import scaffold
from drive_stripper.pipeline import batch_process


def test_batch_process_mirrors_directory_and_redacts_each_file(tmp_path: Path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    (input_dir / "sub").mkdir(parents=True)
    (input_dir / "notes.txt").write_text("email jane@acme.com")
    (input_dir / "sub" / "more.txt").write_text("email john@acme.com")

    results = batch_process(input_dir, output_dir, mode="strip", categories=("email",))

    assert len(results) == 2
    assert all(r.error is None for r in results)
    assert (output_dir / "notes.txt").exists()
    assert "jane@acme.com" not in (output_dir / "notes.txt").read_text()
    assert (output_dir / "sub" / "more.txt").exists()
    assert "john@acme.com" not in (output_dir / "sub" / "more.txt").read_text()


def test_batch_process_non_recursive_skips_subdirectories(tmp_path: Path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    (input_dir / "sub").mkdir(parents=True)
    (input_dir / "notes.txt").write_text("hello")
    (input_dir / "sub" / "more.txt").write_text("hello")

    results = batch_process(input_dir, output_dir, mode="strip", recursive=False)

    assert len(results) == 1
    assert results[0].source == input_dir / "notes.txt"


def test_batch_process_scaffold_mode_writes_per_file_mapping(tmp_path: Path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    (input_dir / "notes.txt").write_text("email jane@acme.com")

    results = batch_process(input_dir, output_dir, mode="scaffold", categories=("email",))

    assert len(results) == 1
    result = results[0].result
    assert result.mapping_path == output_dir / "notes.txt.scaffold-map.json"
    mapping = scaffold.load_mapping(result.mapping_path)
    restored = scaffold.restore((output_dir / "notes.txt").read_text(), mapping)
    assert restored == "email jane@acme.com"


def test_batch_process_reports_error_for_one_bad_file_without_aborting(tmp_path: Path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    (input_dir / "good.txt").write_text("email jane@acme.com")
    # a .docx that isn't actually a valid docx - triggers an error in that file's handler
    (input_dir / "bad.docx").write_bytes(b"not a real docx")

    results = batch_process(input_dir, output_dir, mode="strip", categories=("email",))

    by_name = {r.source.name: r for r in results}
    assert by_name["good.txt"].error is None
    assert by_name["bad.docx"].error is not None
    assert "jane@acme.com" not in (output_dir / "good.txt").read_text()
