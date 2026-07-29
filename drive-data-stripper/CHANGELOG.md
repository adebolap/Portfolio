# Changelog

## 0.3.0

- Add `high_entropy_secret` detection: a Shannon-entropy check (separate
  hex vs. general thresholds, tuned against real token shapes vs. common
  false positives like UUIDs/camelCase identifiers) that catches
  random-looking custom tokens with no known prefix - the biggest gap
  pure pattern-matching had. Medium confidence, ported identically to the
  browser extension's JS engine with matching parity tests.

## browser-extension/ (concept, unversioned - not part of the pip package)

- Added a Manifest V3 browser extension proof of concept: intercepts
  sensitive text before it reaches an AI chat's send action, offering
  Strip / Scaffold / Send anyway, with click-to-restore for scaffold
  tokens echoed back in a reply. See `browser-extension/README.md` for
  architecture, scope, and how it was tested (a real bug - an infinite
  MutationObserver loop - was caught and fixed via the Playwright test).
- Interactive UX mockup published as a private Claude artifact (visible to
  the account that generated it, not publicly accessible):
  https://claude.ai/code/artifact/4bedc402-5dec-4e52-9fe2-b2d4cc4c72e9

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
