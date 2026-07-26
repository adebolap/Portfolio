# Changelog

## 0.2.0

- Add PowerPoint (`.pptx`) metadata stripping and content redaction (shapes,
  tables, group shapes, speaker notes).
- Add Power BI package support: `.pbix`/`.pbit` (JSON parts only - the
  binary data model is left untouched) and `.pbids`.
- Add `.bim` (SSAS Tabular Model JSON) to plain-text scanning.
- Add OCR-based detection and visual redaction of text baked into image
  pixels (`drive_stripper.ocr`), gated on the optional `tesseract-ocr`
  system binary.
- Add Luhn checksum validation for credit card matches, cutting false
  positives on arbitrary digit runs. Fixed a regex bug that let a trailing
  separator leak into a matched credit card value.
- Add an interactive `--review` flow: confirm each match with context
  before it's redacted or scaffolded.
- Add an append-only JSONL audit log (`drive_stripper.audit`) that records
  operation metadata and match counts by category - never matched values.
- Add `drive-strip batch` to sanitize a whole directory tree in one run,
  mirroring structure into an output directory and reporting per-file
  results without aborting on a single bad file.
- Add key-file based encryption (`drive-strip keygen`, `--key-file`) as a
  team/automation-friendly alternative to a shared passphrase.
- Add a local web UI (`drive-strip web`).
- Packaging: LICENSE, classifiers, `python -m drive_stripper` entry point.

## 0.1.0

- Initial release: guided CLI (`drive-strip strip` / `restore`), metadata
  stripping and proprietary-content detection/redaction for `.docx`,
  `.xlsx`, `.pdf`, images, and plain text/JSON, with a reversible scaffold
  mode backed by passphrase-encrypted mapping files.
