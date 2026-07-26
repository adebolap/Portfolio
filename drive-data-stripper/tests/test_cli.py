from pathlib import Path

from click.testing import CliRunner

from drive_stripper.cli import cli
from drive_stripper import scaffold


def test_strip_non_interactive_with_yes_flag(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("email jane@acme.com")
    output = tmp_path / "notes.sanitized.txt"

    runner = CliRunner()
    result = runner.invoke(
        cli, ["strip", "--file", str(source), "--mode", "strip", "--output", str(output), "--yes"]
    )

    assert result.exit_code == 0, result.output
    assert output.exists()
    assert "jane@acme.com" not in output.read_text()


def test_strip_scaffold_then_restore_round_trip(tmp_path: Path):
    source = tmp_path / "notes.txt"
    original = "email jane@acme.com"
    source.write_text(original)
    output = tmp_path / "notes.sanitized.txt"
    mapping_out = tmp_path / "notes.map.json"

    runner = CliRunner()
    strip_result = runner.invoke(
        cli,
        [
            "strip",
            "--file",
            str(source),
            "--mode",
            "scaffold",
            "--output",
            str(output),
            "--mapping-out",
            str(mapping_out),
            "--yes",
        ],
    )
    assert strip_result.exit_code == 0, strip_result.output
    assert mapping_out.exists()

    # the "model response" is just the scaffolded text echoed back
    response_path = tmp_path / "response.txt"
    response_path.write_text(output.read_text())
    restored_out = tmp_path / "restored.txt"

    restore_result = runner.invoke(
        cli,
        [
            "restore",
            "--response",
            str(response_path),
            "--mapping",
            str(mapping_out),
            "--output",
            str(restored_out),
        ],
    )
    assert restore_result.exit_code == 0, restore_result.output
    assert restored_out.read_text() == original


def test_keygen_creates_key_file(tmp_path: Path):
    key_path = tmp_path / "team.key"
    runner = CliRunner()
    result = runner.invoke(cli, ["keygen", "--output", str(key_path)])

    assert result.exit_code == 0, result.output
    assert key_path.exists()
    assert scaffold.load_key_file(key_path) == key_path.read_bytes()


def test_strip_and_restore_with_key_file(tmp_path: Path):
    source = tmp_path / "notes.txt"
    original = "email jane@acme.com"
    source.write_text(original)
    output = tmp_path / "notes.sanitized.txt"
    mapping_out = tmp_path / "notes.map.json"
    key_path = tmp_path / "team.key"

    runner = CliRunner()
    keygen_result = runner.invoke(cli, ["keygen", "--output", str(key_path)])
    assert keygen_result.exit_code == 0, keygen_result.output

    strip_result = runner.invoke(
        cli,
        [
            "strip",
            "--file", str(source),
            "--mode", "scaffold",
            "--output", str(output),
            "--mapping-out", str(mapping_out),
            "--key-file", str(key_path),
            "--yes",
        ],
    )
    assert strip_result.exit_code == 0, strip_result.output

    response_path = tmp_path / "response.txt"
    response_path.write_text(output.read_text())
    restored_out = tmp_path / "restored.txt"

    restore_result = runner.invoke(
        cli,
        [
            "restore",
            "--response", str(response_path),
            "--mapping", str(mapping_out),
            "--key-file", str(key_path),
            "--output", str(restored_out),
        ],
    )
    assert restore_result.exit_code == 0, restore_result.output
    assert restored_out.read_text() == original


def test_strip_review_mode_can_reject_a_match(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("email jane@acme.com and phone 555-123-4567")
    output = tmp_path / "notes.sanitized.txt"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "strip",
            "--file", str(source),
            "--mode", "strip",
            "--output", str(output),
            "--category", "email",
            "--category", "phone",
            "--review",
            "--yes",
        ],
        input="n\ny\n",  # reject the email match, accept the phone match
    )

    assert result.exit_code == 0, result.output
    text = output.read_text()
    assert "jane@acme.com" in text  # rejected match survives untouched
    assert "555-123-4567" not in text  # accepted match is redacted


def test_strip_writes_audit_log_without_matched_values(tmp_path: Path):
    from drive_stripper import audit

    source = tmp_path / "notes.txt"
    source.write_text("email jane@acme.com")
    output = tmp_path / "notes.sanitized.txt"
    log_path = tmp_path / "audit.log"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "strip",
            "--file", str(source),
            "--mode", "strip",
            "--output", str(output),
            "--audit-log", str(log_path),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    events = audit.read_events(log_path)
    assert len(events) == 1
    assert events[0]["operation"] == "strip"
    assert events[0]["matches_by_label"] == {"email": 1}
    assert "jane@acme.com" not in log_path.read_text()


def test_batch_command_processes_directory(tmp_path: Path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    (input_dir / "a.txt").write_text("email jane@acme.com")
    (input_dir / "b.txt").write_text("nothing sensitive here")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "batch",
            "--input-dir", str(input_dir),
            "--output-dir", str(output_dir),
            "--mode", "strip",
            "--category", "email",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "jane@acme.com" not in (output_dir / "a.txt").read_text()
    assert (output_dir / "b.txt").read_text() == "nothing sensitive here"
    assert "2 files processed, 1 proprietary matches found, 0 errors" in result.output


def test_guided_interactive_prompts(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("email jane@acme.com")

    runner = CliRunner()
    # simulate: mode=strip, scan all categories, no custom terms, accept default output
    inputs = "strip\ny\n\n\n"
    result = runner.invoke(cli, ["strip", "--file", str(source)], input=inputs)

    assert result.exit_code == 0, result.output
    default_output = source.with_name("notes.sanitized.txt")
    assert default_output.exists()
    assert "jane@acme.com" not in default_output.read_text()
