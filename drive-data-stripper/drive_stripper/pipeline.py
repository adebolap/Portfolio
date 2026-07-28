"""Wire metadata stripping, proprietary-content detection, and scaffolding
together into a single per-file operation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import content, metadata, ocr, powerbi, proprietary, scaffold
from .proprietary import Match

MODES = ("strip", "scaffold", "metadata-only")


@dataclass
class ProcessResult:
    output_path: Path
    metadata_stripped: bool
    matches_found: int
    mapping_path: Path | None = None
    pdf_text_sidecar: Path | None = None
    image_regions_redacted: int = 0
    ocr_warning: str | None = None
    matches_by_label: dict[str, int] = field(default_factory=dict)


def process_file(
    source: Path,
    destination: Path,
    mode: str = "strip",
    categories: tuple[str, ...] | None = None,
    custom_terms: list[str] | None = None,
    mapping_destination: Path | None = None,
    passphrase: str | None = None,
    key: bytes | None = None,
    match_filter: Callable[[str, list[Match]], list[Match]] | None = None,
) -> ProcessResult:
    """Sanitize ``source`` into ``destination``.

    ``mode``:
      - ``"strip"``: permanently redact proprietary content, remove metadata.
      - ``"scaffold"``: replace proprietary content with reversible
        placeholder tokens (requires ``mapping_destination``), remove metadata.
      - ``"metadata-only"``: strip metadata only, leave content untouched.

    ``match_filter``, if given, is called as ``match_filter(chunk, matches)``
    for every paragraph/cell/text chunk scanned and must return the subset of
    matches to actually act on - e.g. to drive an interactive review step.
    It does not apply to OCR-based image redaction.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode!r}, expected one of {MODES}")
    if mode == "scaffold" and mapping_destination is None:
        raise ValueError("scaffold mode requires mapping_destination")

    metadata_stripped = metadata.strip_metadata(source, destination)

    matches_found = 0
    mapping_path = None
    pdf_sidecar = None
    image_regions_redacted = 0
    ocr_warning = None
    label_counts: Counter[str] = Counter()

    if mode != "metadata-only":
        suffix = source.suffix.lower()
        offset = 0
        combined_mapping: dict[str, str] = {}

        def transform(chunk: str) -> str:
            nonlocal matches_found, offset
            matches = proprietary.detect(chunk, categories, custom_terms)
            if match_filter:
                matches = match_filter(chunk, matches)
            matches_found += len(matches)
            label_counts.update(m.label for m in matches)
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
        elif suffix in metadata.SUPPORTED_IMAGE_SUFFIXES:
            if mode == "scaffold":
                raise ValueError(
                    "scaffold mode isn't supported for images - there's no reversible "
                    "placeholder for pixels. Use mode='strip' instead."
                )
            if ocr.is_available():
                image_regions_redacted = ocr.redact_image_text(
                    destination, destination, categories, custom_terms
                )
                matches_found += image_regions_redacted
                if image_regions_redacted:
                    label_counts["image_ocr_region"] += image_regions_redacted
            else:
                ocr_warning = (
                    "Tesseract OCR is not installed - text baked into image pixels was "
                    "NOT scanned, only embedded EXIF/metadata was stripped."
                )
        elif content.is_text_extractable(source):
            text = destination.read_text(errors="replace")
            destination.write_text(transform(text))

        if mode == "scaffold" and combined_mapping:
            scaffold.save_mapping(combined_mapping, mapping_destination, passphrase, key)
            mapping_path = mapping_destination

    return ProcessResult(
        output_path=destination,
        metadata_stripped=metadata_stripped,
        matches_found=matches_found,
        mapping_path=mapping_path,
        pdf_text_sidecar=pdf_sidecar,
        image_regions_redacted=image_regions_redacted,
        ocr_warning=ocr_warning,
        matches_by_label=dict(label_counts),
    )


@dataclass
class BatchFileResult:
    source: Path
    result: ProcessResult | None = None
    error: str | None = None


def batch_process(
    input_dir: Path,
    output_dir: Path,
    mode: str = "strip",
    categories: tuple[str, ...] | None = None,
    custom_terms: list[str] | None = None,
    passphrase: str | None = None,
    key: bytes | None = None,
    recursive: bool = True,
    match_filter: Callable[[str, list[Match]], list[Match]] | None = None,
) -> list[BatchFileResult]:
    """Run :func:`process_file` over every file under ``input_dir``, mirroring
    the directory structure into ``output_dir``. Errors on individual files
    are caught and reported per-file rather than aborting the whole batch.
    """
    pattern = "**/*" if recursive else "*"
    results = []
    for source in sorted(p for p in input_dir.glob(pattern) if p.is_file()):
        rel = source.relative_to(input_dir)
        destination = output_dir / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        mapping_destination = (
            destination.with_suffix(destination.suffix + ".scaffold-map.json")
            if mode == "scaffold"
            else None
        )
        try:
            result = process_file(
                source,
                destination,
                mode=mode,
                categories=categories,
                custom_terms=custom_terms,
                mapping_destination=mapping_destination,
                passphrase=passphrase,
                key=key,
                match_filter=match_filter,
            )
            results.append(BatchFileResult(source=source, result=result))
        except Exception as exc:  # one bad file must not abort the whole batch
            results.append(BatchFileResult(source=source, error=str(exc)))
    return results
