"""Wire metadata stripping, proprietary-content detection, and scaffolding
together into a single per-file operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import content, metadata, powerbi, proprietary, scaffold

MODES = ("strip", "scaffold", "metadata-only")


@dataclass
class ProcessResult:
    output_path: Path
    metadata_stripped: bool
    matches_found: int
    mapping_path: Path | None = None
    pdf_text_sidecar: Path | None = None


def process_file(
    source: Path,
    destination: Path,
    mode: str = "strip",
    categories: tuple[str, ...] | None = None,
    custom_terms: list[str] | None = None,
    mapping_destination: Path | None = None,
    passphrase: str | None = None,
) -> ProcessResult:
    """Sanitize ``source`` into ``destination``.

    ``mode``:
      - ``"strip"``: permanently redact proprietary content, remove metadata.
      - ``"scaffold"``: replace proprietary content with reversible
        placeholder tokens (requires ``mapping_destination``), remove metadata.
      - ``"metadata-only"``: strip metadata only, leave content untouched.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode!r}, expected one of {MODES}")
    if mode == "scaffold" and mapping_destination is None:
        raise ValueError("scaffold mode requires mapping_destination")

    metadata_stripped = metadata.strip_metadata(source, destination)

    matches_found = 0
    mapping_path = None
    pdf_sidecar = None

    if mode != "metadata-only":
        suffix = source.suffix.lower()
        offset = 0
        combined_mapping: dict[str, str] = {}

        def transform(chunk: str) -> str:
            nonlocal matches_found, offset
            matches = proprietary.detect(chunk, categories, custom_terms)
            matches_found += len(matches)
            if not matches:
                return chunk
            if mode == "scaffold":
                new_chunk, chunk_mapping, offset = scaffold.apply_scaffold(chunk, matches, offset)
                combined_mapping.update(chunk_mapping)
                return new_chunk
            return proprietary.redact(chunk, matches)

        if suffix == ".pdf":
            text = content.read_text(source)
            if text:
                new_text = transform(text)
                if matches_found:
                    pdf_sidecar = destination.with_suffix(".redacted.txt")
                    content.write_text(pdf_sidecar, new_text)
        elif suffix == ".docx":
            content.write_docx_text(destination, destination, transform)
        elif suffix == ".pptx":
            content.write_pptx_text(destination, destination, transform)
        elif suffix == ".xlsx":
            content.write_xlsx_text(destination, destination, transform)
        elif suffix in powerbi.SUFFIXES:
            powerbi.process_power_bi_package(destination, destination, transform)
        elif content.is_text_extractable(source):
            text = destination.read_text(errors="replace")
            destination.write_text(transform(text))

        if mode == "scaffold" and combined_mapping:
            scaffold.save_mapping(combined_mapping, mapping_destination, passphrase)
            mapping_path = mapping_destination

    return ProcessResult(
        output_path=destination,
        metadata_stripped=metadata_stripped,
        matches_found=matches_found,
        mapping_path=mapping_path,
        pdf_text_sidecar=pdf_sidecar,
    )
