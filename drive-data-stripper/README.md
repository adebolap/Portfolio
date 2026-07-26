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

## Install

```bash
pip install -e ".[dev]"
```

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
| `.jpg/.png/.tiff/.webp` | EXIF/GPS and other embedded info | no text layer |
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
from drive_stripper.pipeline import process_file

result = process_file(
    source=Path("report.docx"),
    destination=Path("report.sanitized.docx"),
    mode="scaffold",
    custom_terms=["Project Chimera"],
    mapping_destination=Path("report.sanitized.docx.scaffold-map.json"),
    passphrase="a strong local passphrase",
)
print(result.matches_found, result.mapping_path)
```

## Tests

```bash
pytest
```
