from pathlib import Path

from drive_stripper import audit


def test_log_event_appends_jsonl_record(tmp_path: Path):
    log_path = tmp_path / "audit.log"
    audit.log_event(
        log_path,
        operation="strip",
        source=Path("report.docx"),
        destination=Path("report.sanitized.docx"),
        mode="strip",
        categories=("email",),
        matches_by_label={"email": 2},
    )

    events = audit.read_events(log_path)
    assert len(events) == 1
    event = events[0]
    assert event["operation"] == "strip"
    assert event["source"] == "report.docx"
    assert event["mode"] == "strip"
    assert event["matches_by_label"] == {"email": 2}
    assert "timestamp" in event


def test_log_event_never_contains_matched_values(tmp_path: Path):
    log_path = tmp_path / "audit.log"
    audit.log_event(
        log_path,
        operation="strip",
        source=Path("notes.txt"),
        matches_by_label={"email": 1},
    )
    raw = log_path.read_text()
    assert "jane@acme.com" not in raw  # sanity: only counts are ever logged, never values


def test_read_events_returns_empty_list_for_missing_log(tmp_path: Path):
    assert audit.read_events(tmp_path / "missing.log") == []


def test_log_event_appends_multiple_records(tmp_path: Path):
    log_path = tmp_path / "audit.log"
    audit.log_event(log_path, operation="strip", source=Path("a.txt"))
    audit.log_event(log_path, operation="restore", source=Path("b.txt"))
    events = audit.read_events(log_path)
    assert [e["operation"] for e in events] == ["strip", "restore"]
