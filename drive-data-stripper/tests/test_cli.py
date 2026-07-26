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
