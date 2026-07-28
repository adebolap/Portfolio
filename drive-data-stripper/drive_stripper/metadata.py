"""File-level metadata stripping.

Handles the metadata that lives outside a file's visible content - EXIF/GPS
tags on images, author/company fields on Office documents, and XMP/Info
dictionaries on PDFs - any of which can leak an organization's identity even
after the visible text has been sanitized.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}
SUPPORTED_PDF_SUFFIXES = {".pdf"}
SUPPORTED_DOCX_SUFFIXES = {".docx"}
SUPPORTED_XLSX_SUFFIXES = {".xlsx"}
SUPPORTED_PPTX_SUFFIXES = {".pptx"}

_OFFICE_CORE_PROPERTY_FIELDS = (
    "author",
    "category",
    "comments",
    "content_status",
    "identifier",
    "keywords",
    "language",
    "last_modified_by",
    "subject",
    "title",
    "version",
)


class UnsupportedFileTypeError(ValueError):
    """Raised when no metadata handler exists for a file's extension."""


def strip_image_metadata(source: Path, destination: Path) -> None:
    from PIL import Image

    with Image.open(source) as img:
        img.load()
        clean = img.copy()
        clean.info = {}
        clean.save(destination)


def strip_pdf_metadata(source: Path, destination: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({})
    with open(destination, "wb") as fh:
        writer.write(fh)


def strip_docx_metadata(source: Path, destination: Path) -> None:
    from docx import Document

    doc = Document(str(source))
    for field in _OFFICE_CORE_PROPERTY_FIELDS:
        setattr(doc.core_properties, field, "")
    doc.save(str(destination))


def strip_pptx_metadata(source: Path, destination: Path) -> None:
    from pptx import Presentation

    prs = Presentation(str(source))
    for field in _OFFICE_CORE_PROPERTY_FIELDS:
        setattr(prs.core_properties, field, "")
    prs.save(str(destination))


def strip_xlsx_metadata(source: Path, destination: Path) -> None:
    from openpyxl import load_workbook

    wb = load_workbook(str(source))
    props = wb.properties
    for field in (
        "creator",
        "lastModifiedBy",
        "company",
        "manager",
        "category",
        "subject",
        "keywords",
        "description",
        "title",
    ):
        setattr(props, field, "")
    wb.save(str(destination))


_HANDLERS = {
    **{suf: strip_image_metadata for suf in SUPPORTED_IMAGE_SUFFIXES},
    **{suf: strip_pdf_metadata for suf in SUPPORTED_PDF_SUFFIXES},
    **{suf: strip_docx_metadata for suf in SUPPORTED_DOCX_SUFFIXES},
    **{suf: strip_xlsx_metadata for suf in SUPPORTED_XLSX_SUFFIXES},
    **{suf: strip_pptx_metadata for suf in SUPPORTED_PPTX_SUFFIXES},
}


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in _HANDLERS


def strip_metadata(source: Path, destination: Path) -> bool:
    """Strip embedded metadata from ``source`` into ``destination``.

    Returns True if a metadata handler ran, False if the file type carries no
    known metadata (e.g. plain text) and was simply copied through.
    """
    handler = _HANDLERS.get(source.suffix.lower())
    if handler is None:
        shutil.copyfile(source, destination)
        return False
    handler(source, destination)
    return True
