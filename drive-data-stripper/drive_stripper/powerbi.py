"""Power BI package (.pbix / .pbit) support.

.pbix (Power BI Desktop report) and .pbit (Power BI template) are both ZIP
packages. Most of a .pbix is the compressed Vertipaq/xVelocity data model -
proprietary binary that this tool cannot safely parse, so imported table
data is **not** scanned or redacted. What *is* plain JSON text, and
routinely leaks server names, connection strings, and workspace details, is
a small set of well-documented parts:

- ``Report/Layout`` - the report's visuals, including bookmarks and any
  static text.
- ``Connections`` - data source connection strings.
- ``DataModelSchema`` - table/column/measure definitions (present in .pbit
  templates and newer .pbix files that use the JSON-based model schema
  instead of the binary data model).
- ``Metadata`` - package-level metadata.

Only these parts are ever rewritten; everything else, including the binary
data model in a .pbix, is copied through unchanged.
"""

from __future__ import annotations

from pathlib import Path

from . import zip_container

TEXT_PARTS = {"Report/Layout", "Connections", "DataModelSchema", "Metadata"}

SUFFIXES = {".pbix", ".pbit"}


def process_power_bi_package(source: Path, destination: Path, transform) -> int:
    return zip_container.process_json_parts(source, destination, TEXT_PARTS, transform)
