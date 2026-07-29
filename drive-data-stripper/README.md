# drive-data-stripper

A Python CLI that strips proprietary data and file metadata from a document
before it's shared with a frontier model (ChatGPT, Claude, Gemini, ...) -
walking you through the decisions with guided prompts instead of requiring a
config file up front.

## Why

Sharing a file with an external AI model means sharing everything embedded in
it: EXIF/GPS tags on a photo, the author and company name baked into a Word
document's properties, and any emails, API keys, IP addresses, or internal
codenames sitting in the visible text. This tool scans for both categories
and lets you either strip them permanently or **scaffold** them - swap each
sensitive value for a placeholder token so the model still sees a
structurally intact document, then restore the real values afterward once
the model's response comes back.

There's also a browser extension proof of concept (`browser-extension/`)
that applies the same idea directly at the point of risk - intercepting
text pasted into a chat's compose box - rather than requiring you to run
the CLI first. See `browser-extension/README.md` for scope and status.

## Install

```bash
pip install -e ".[dev]"          # core + test dependencies
pip install -e ".[ocr]"          # + OCR support for images (also needs the tesseract-ocr system package)
pip install -e ".[web]"          # + the local web UI
```

OCR needs the Tesseract OCR engine installed separately - it's a system
binary, not a Python package: `apt install tesseract-ocr` (Debian/Ubuntu) or
`brew install tesseract` (macOS). Without it, image files still get their
EXIF/metadata stripped, but text baked into the pixels isn't scanned; the
CLI prints a clear warning when that happens rather than silently skipping it.

## Guided usage

```bash
drive-strip strip --file report.docx
```

With no other flags, you'll be walked through:

1. **Mode** - `strip` (permanent redaction), `scaffold` (reversible
   placeholders), or `metadata-only` (leave text as-is, just clean file
   metadata).
2. **Categories** - which built-in patterns to scan for: emails, AWS/API
   keys, bearer tokens, PEM private key blocks, IPv4 addresses, phone
   numbers, credit card numbers - or restrict to a subset.
3. **Custom terms** - your own vocabulary to redact: company name, client
   names, project codenames.
4. **Output paths** - where the sanitized file (and, in scaffold mode, the
   mapping file) get written.
5. **Passphrase** - optionally encrypt the scaffold mapping file so it's
   useless if it leaks.

Every flag can also be passed directly (`--mode`, `--category`, `--term`,
`--output`, `--mapping-out`, `--passphrase`, `--yes` to skip prompts).

### Reviewing matches before they're acted on

Regex-based detection is inherently approximate - a phone-shaped ID or an
internal reference number can look like a match. Add `--review` to see each
detected match with ~30 characters of surrounding context and confirm it
individually before it's redacted or scaffolded:

```bash
drive-strip strip --file report.docx --review
```

Credit card matches are already filtered through a Luhn checksum so
arbitrary digit runs aren't flagged in the first place; phone matches are
marked `medium` confidence in review since that pattern is intentionally
broad.

### Sanitizing a whole directory

```bash
drive-strip batch --input-dir ./to_share --output-dir ./sanitized --mode strip
```

Mirrors the input directory's structure into `--output-dir`, processing
every file it finds (recursively by default - use `--no-recursive` to stay
in the top level). Scaffold-mode mappings are written next to each
sanitized file as `<file>.scaffold-map.json`. A file that fails to process
(corrupt, unsupported, whatever) is reported and skipped - it doesn't abort
the rest of the batch.

### A local web UI

```bash
drive-strip web
```

Opens a form at `http://127.0.0.1:5000` - upload a file, pick a mode and
categories, download the sanitized result (scaffold mode downloads a zip
with the mapping file included). It's a single-user, stateless alternative
to the CLI wizard for anyone who'd rather use a browser: no auth, no
persisted history, meant for localhost only, not for hosting as a shared
service.

### Sharing scaffold mappings with a team

A passphrase works for one person. For a team or an automated pipeline,
generate a key file instead and distribute it through your existing secrets
manager:

```bash
drive-strip keygen --output team.key
drive-strip strip --file report.docx --mode scaffold --key-file team.key
drive-strip restore --response model_reply.txt --mapping report.sanitized.docx.scaffold-map.json --key-file team.key
```

`--key-file` and `--passphrase` are mutually exclusive - use whichever
matches how the mapping was encrypted.

### Audit log

Pass `--audit-log path/to/audit.log` to `strip`, `restore`, or `batch` to
append a JSON-lines record of each operation: timestamp, source/output
paths, mode, categories, and match counts *by category* - never the matched
values themselves, since the point of the tool is to keep that content from
ending up anywhere it doesn't need to.

## Restoring a scaffolded response

Once you've sent the scaffolded file to a model and gotten a response back
(the response will still contain the `[[SCAFFOLD:label:n]]` tokens for
anything it echoed), restore the real values locally:

```bash
drive-strip restore --response model_reply.txt --mapping report.sanitized.docx.scaffold-map.json
```

**The mapping file is the one thing that must never be shared with the
model** - it's the only place the original sensitive values are kept.

## What gets handled per file type

| Type          | Metadata stripped           | Content scanned/redacted |
|---------------|------------------------------|---------------------------|
| `.txt/.md/.csv/.json/.py/.log/.yaml/.yml/.bim/.pbids` | n/a | yes, in place |
| `.docx`       | author, title, company, ...  | yes, per paragraph |
| `.pptx`       | author, title, company, ...  | yes: shape text, table cells, group shapes, speaker notes |
| `.xlsx`       | creator, company, ...        | yes, per cell |
| `.pbix/.pbit` | n/a                          | yes, but only the plain-JSON parts of the package (see below) - not the imported data model |
| `.jpg/.png/.tiff/.webp` | EXIF/GPS and other embedded info | yes, visually: text baked into the pixels is found via OCR and blacked out (requires Tesseract; `strip`/`metadata-only` only, no scaffold mode for pixels) |
| `.pdf`        | document info dictionary      | read-only: redacted text is written to a `.redacted.txt` sidecar, since rewriting a PDF's content streams in place is out of scope |

`.bim` is treated as plain JSON text (SSAS Tabular Model files are JSON since
Analysis Services 2016+). Older XML-format `.bim` files aren't parsed
specially, but are still scanned as raw text. `.pbids` (a Power BI data
source file) is also plain JSON and is scanned the same way - useful since
it's where a server/database connection string usually lives.

### Power BI (`.pbix`/`.pbit`) scope

A `.pbix`/`.pbit` is a ZIP package. Most of a `.pbix` is the compressed
Vertipaq/xVelocity data model holding the actual imported table data - a
proprietary binary format this tool can't safely parse, so **imported data
is never scanned or redacted**. What it does scan and redact, in place
inside the package, is the small set of parts documented (via community
reverse-engineering) to be plain JSON: `Report/Layout` (visual titles and
any static report text), `Connections` (data source connection strings -
where server/database names usually leak), `DataModelSchema` (table/measure
definitions in `.pbit` templates and JSON-schema `.pbix` files), and
`Metadata`. Every other part of the package, including the binary data
model, is copied through byte-for-byte unchanged - and each JSON part is
only written back if it still parses as valid JSON after redaction, so a
malformed rewrite can never corrupt the package.

## Library usage

```python
from pathlib import Path
from drive_stripper.pipeline import process_file, batch_process

result = process_file(
    source=Path("report.docx"),
    destination=Path("report.sanitized.docx"),
    mode="scaffold",
    custom_terms=["Project Chimera"],
    mapping_destination=Path("report.sanitized.docx.scaffold-map.json"),
    passphrase="a strong local passphrase",
)
print(result.matches_found, result.mapping_path)

# or process a whole directory at once
results = batch_process(Path("to_share"), Path("sanitized"), mode="strip")
```

## Known limitations

Being upfront about scope, since a redaction tool that overstates its
coverage is worse than one that's honest about the gaps:

- **Detection is regex/OCR-based, not semantic.** It will miss
  context-dependent secrets that don't match a pattern, and can flag
  look-alikes (mitigated for credit cards via a Luhn check, and generally
  via `--review`).
- **PDF content isn't rewritten in place** - redacted text goes to a
  `.redacted.txt` sidecar.
- **Power BI's binary data model is never scanned** - only the JSON parts
  of a `.pbix`/`.pbit` package.
- **Image scaffolding isn't supported** - there's no reversible placeholder
  for pixels, so images only support `strip`/`metadata-only`.
- **OCR needs Tesseract installed separately**; without it, image pixel
  text isn't scanned (metadata still is, and the CLI warns explicitly).
- **The web UI and audit log are local, single-user tooling** - no auth, no
  multi-tenant story, not meant to be exposed beyond localhost.

## Tests

```bash
pytest
```
