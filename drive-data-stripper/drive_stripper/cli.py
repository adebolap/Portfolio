"""Guided command-line interface.

Run ``drive-strip strip`` with no options and it will walk you through every
choice - which file, whether to permanently strip or reversibly scaffold
proprietary content, which categories to scan for, and where to save the
result - so sharing a file with a frontier model safely doesn't require
reading documentation first.
"""

from __future__ import annotations

from pathlib import Path

import click

from . import audit, metadata, scaffold
from .pipeline import MODES, batch_process, process_file
from .proprietary import DEFAULT_CATEGORIES, Match


def _review_filter(chunk: str, matches: list[Match]) -> list[Match]:
    accepted = []
    for m in matches:
        start = max(0, m.start - 30)
        end = min(len(chunk), m.end + 30)
        context = chunk[start:end].replace("\n", " ")
        click.echo(f"\n  [{m.label}, {m.confidence} confidence] ...{context}...")
        if click.confirm(f"  Act on this match ({m.value!r})?", default=True):
            accepted.append(m)
    return accepted


@click.group()
@click.version_option(package_name="drive-data-stripper")
def cli() -> None:
    """Strip proprietary data and metadata from files before sharing them with an AI model."""


@cli.command()
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File to sanitize.",
)
@click.option(
    "--mode",
    type=click.Choice(["strip", "scaffold", "metadata-only"]),
    help=(
        "strip: permanently remove proprietary content. "
        "scaffold: replace it with reversible placeholder tokens. "
        "metadata-only: leave content untouched, only strip file metadata."
    ),
)
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Where to write the sanitized file.")
@click.option(
    "--category",
    "categories",
    multiple=True,
    type=click.Choice(DEFAULT_CATEGORIES),
    help="Restrict scanning to these built-in categories (repeatable). Default: all.",
)
@click.option("--term", "custom_terms", multiple=True, help="Custom proprietary term to redact, e.g. a codename (repeatable).")
@click.option("--mapping-out", type=click.Path(path_type=Path), help="Where to save the scaffold mapping (scaffold mode only).")
@click.option("--passphrase", help="Passphrase to encrypt the scaffold mapping file with.")
@click.option("--key-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Key file (from `drive-strip keygen`) to encrypt the scaffold mapping with, instead of a passphrase.")
@click.option("--review/--no-review", default=False, help="Show each detected match with context and confirm before acting on it.")
@click.option("--audit-log", type=click.Path(path_type=Path), help="Append a JSONL audit record to this file (never contains matched values).")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts, failing instead if required input is missing.")
def strip(
    file_path: Path | None,
    mode: str | None,
    output: Path | None,
    categories: tuple[str, ...],
    custom_terms: tuple[str, ...],
    mapping_out: Path | None,
    passphrase: str | None,
    key_file: Path | None,
    review: bool,
    audit_log: Path | None,
    yes: bool,
) -> None:
    """Guided: sanitize a file before sharing it with a frontier model."""
    if file_path is None:
        if yes:
            raise click.UsageError("--file is required with --yes")
        file_path = Path(click.prompt("File to sanitize", type=click.Path(exists=True, dir_okay=False)))

    if mode is None:
        if yes:
            mode = "strip"
        else:
            click.echo(
                "\nHow should proprietary content be handled?\n"
                "  strip         - permanently remove it (safest, not reversible)\n"
                "  scaffold      - swap it for placeholder tokens you can restore afterward\n"
                "  metadata-only - leave content as-is, only clean embedded file metadata\n"
            )
            mode = click.prompt(
                "Mode", type=click.Choice(["strip", "scaffold", "metadata-only"]), default="strip"
            )

    if mode == "scaffold" and file_path.suffix.lower() in metadata.SUPPORTED_IMAGE_SUFFIXES:
        raise click.UsageError(
            "scaffold mode isn't supported for images - there's no reversible placeholder "
            "for pixels. Use --mode strip or --mode metadata-only instead."
        )

    if not categories and mode != "metadata-only" and not yes:
        if click.confirm(
            f"Scan all built-in categories ({', '.join(DEFAULT_CATEGORIES)})?", default=True
        ):
            categories = ()
        else:
            chosen = click.prompt(
                "Comma-separated categories to scan", default=",".join(DEFAULT_CATEGORIES)
            )
            categories = tuple(c.strip() for c in chosen.split(",") if c.strip())

    if not custom_terms and mode != "metadata-only" and not yes:
        raw_terms = click.prompt(
            "Any custom terms to redact (company name, codenames), comma-separated",
            default="",
            show_default=False,
        )
        custom_terms = tuple(t.strip() for t in raw_terms.split(",") if t.strip())

    if output is None:
        default_output = file_path.with_name(f"{file_path.stem}.sanitized{file_path.suffix}")
        output = Path(click.prompt("Output path", default=str(default_output))) if not yes else default_output

    if mode == "scaffold" and mapping_out is None:
        default_mapping = output.with_suffix(output.suffix + ".scaffold-map.json")
        mapping_out = (
            Path(click.prompt("Scaffold mapping output path", default=str(default_mapping)))
            if not yes
            else default_mapping
        )

    if key_file and passphrase:
        raise click.UsageError("pass either --passphrase or --key-file, not both")

    if mode == "scaffold" and key_file is None and passphrase is None and not yes:
        if click.confirm("Encrypt the scaffold mapping file with a passphrase?", default=True):
            passphrase = click.prompt("Passphrase", hide_input=True, confirmation_prompt=True)

    key = scaffold.load_key_file(key_file) if key_file else None

    result = process_file(
        source=file_path,
        destination=output,
        mode=mode,
        categories=categories or None,
        custom_terms=list(custom_terms),
        mapping_destination=mapping_out,
        passphrase=passphrase,
        key=key,
        match_filter=_review_filter if review else None,
    )

    if audit_log:
        audit.log_event(
            audit_log,
            operation="strip",
            source=file_path,
            destination=result.output_path,
            mode=mode,
            categories=categories or None,
            matches_by_label=result.matches_by_label,
            mapping_path=result.mapping_path,
        )

    click.secho(f"\nSanitized file written to {result.output_path}", fg="green")
    click.echo(f"Metadata stripped: {result.metadata_stripped}")
    if mode != "metadata-only":
        click.echo(f"Proprietary matches found: {result.matches_found}")
    if result.pdf_text_sidecar:
        click.echo(
            f"PDF content can't be edited in place; a redacted text copy was written to "
            f"{result.pdf_text_sidecar}"
        )
    if result.image_regions_redacted:
        click.echo(f"Image regions blacked out via OCR: {result.image_regions_redacted}")
    if result.ocr_warning:
        click.secho(f"Warning: {result.ocr_warning}", fg="yellow")
    if result.mapping_path:
        click.secho(
            f"Scaffold mapping saved to {result.mapping_path} - keep this file local and "
            "never share it with the model. Use it later with `drive-strip restore`.",
            fg="yellow",
        )


@cli.command()
@click.option(
    "--response",
    "response_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File containing the model's response (with scaffold tokens in it).",
)
@click.option(
    "--mapping",
    "mapping_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Scaffold mapping file produced by `drive-strip strip --mode scaffold`.",
)
@click.option("--passphrase", help="Passphrase, if the mapping file was encrypted with one.")
@click.option("--key-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Key file, if the mapping file was encrypted with `--key-file` instead of a passphrase.")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Where to write the restored text (default: stdout).")
@click.option("--audit-log", type=click.Path(path_type=Path), help="Append a JSONL audit record to this file.")
def restore(
    response_path: Path | None,
    mapping_path: Path | None,
    passphrase: str | None,
    key_file: Path | None,
    output: Path | None,
    audit_log: Path | None,
) -> None:
    """Restore original values into a model's response using a saved scaffold mapping."""
    if response_path is None:
        response_path = Path(click.prompt("File containing the model's response", type=click.Path(exists=True, dir_okay=False)))
    if mapping_path is None:
        mapping_path = Path(click.prompt("Scaffold mapping file", type=click.Path(exists=True, dir_okay=False)))

    if key_file and passphrase:
        raise click.UsageError("pass either --passphrase or --key-file, not both")

    key = scaffold.load_key_file(key_file) if key_file else None
    mapping_bytes_start = mapping_path.read_bytes()[:1]
    if key is None and passphrase is None and mapping_bytes_start not in (b"{", b""):
        passphrase = click.prompt("Passphrase", hide_input=True)

    mapping = scaffold.load_mapping(mapping_path, passphrase, key)
    response_text = response_path.read_text()
    restored = scaffold.restore(response_text, mapping)

    remaining = scaffold.find_remaining_tokens(restored)
    if remaining:
        click.secho(
            f"Warning: {len(remaining)} scaffold token(s) had no match in the mapping: "
            f"{', '.join(remaining[:5])}{'...' if len(remaining) > 5 else ''}",
            fg="yellow",
        )

    if output:
        output.write_text(restored)
        click.secho(f"Restored text written to {output}", fg="green")
    else:
        click.echo(restored)

    if audit_log:
        audit.log_event(
            audit_log,
            operation="restore",
            source=response_path,
            destination=output,
            mapping_path=mapping_path,
        )


@cli.command()
@click.option("--output", "-o", type=click.Path(path_type=Path), required=True, help="Where to save the generated key file.")
def keygen(output: Path) -> None:
    """Generate a key file for encrypting scaffold mappings without a shared passphrase.

    Useful for teams or automation: distribute the key file via your
    existing secrets manager, then use `--key-file` (instead of
    `--passphrase`) with `strip` and `restore`.
    """
    key = scaffold.generate_key()
    output.write_bytes(key)
    click.secho(f"Key written to {output} - keep it as secret as the data it protects.", fg="green")


@cli.command()
@click.option("--input-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True, help="Directory of files to sanitize.")
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), required=True, help="Directory to write sanitized files into (structure is mirrored).")
@click.option("--mode", type=click.Choice(MODES), default="strip", show_default=True)
@click.option("--category", "categories", multiple=True, type=click.Choice(DEFAULT_CATEGORIES), help="Restrict scanning to these built-in categories (repeatable). Default: all.")
@click.option("--term", "custom_terms", multiple=True, help="Custom proprietary term to redact (repeatable).")
@click.option("--passphrase", help="Passphrase to encrypt every scaffold mapping with (scaffold mode only).")
@click.option("--key-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Key file to encrypt every scaffold mapping with, instead of a passphrase.")
@click.option("--recursive/--no-recursive", default=True, show_default=True, help="Recurse into subdirectories.")
@click.option("--audit-log", type=click.Path(path_type=Path), help="Append one JSONL audit record per file to this log.")
def batch(
    input_dir: Path,
    output_dir: Path,
    mode: str,
    categories: tuple[str, ...],
    custom_terms: tuple[str, ...],
    passphrase: str | None,
    key_file: Path | None,
    recursive: bool,
    audit_log: Path | None,
) -> None:
    """Sanitize every file in a directory, mirroring its structure into --output-dir.

    Each scaffold-mode mapping is saved next to its sanitized file as
    ``<file>.scaffold-map.json``. A file that fails to process is reported
    and skipped - it does not stop the rest of the batch.
    """
    if key_file and passphrase:
        raise click.UsageError("pass either --passphrase or --key-file, not both")
    key = scaffold.load_key_file(key_file) if key_file else None

    results = batch_process(
        input_dir,
        output_dir,
        mode=mode,
        categories=categories or None,
        custom_terms=list(custom_terms),
        passphrase=passphrase,
        key=key,
        recursive=recursive,
    )

    total_matches = 0
    error_count = 0
    for item in results:
        rel = item.source.relative_to(input_dir)
        if item.error:
            error_count += 1
            click.secho(f"  ERROR  {rel}: {item.error}", fg="red")
            continue
        total_matches += item.result.matches_found
        click.echo(f"  ok     {rel}  matches={item.result.matches_found}")
        if item.result.ocr_warning:
            click.secho(f"         warning: {item.result.ocr_warning}", fg="yellow")
        if audit_log:
            audit.log_event(
                audit_log,
                operation="batch-strip",
                source=item.source,
                destination=item.result.output_path,
                mode=mode,
                categories=categories or None,
                matches_by_label=item.result.matches_by_label,
                mapping_path=item.result.mapping_path,
            )

    summary_color = "yellow" if error_count else "green"
    click.secho(
        f"\n{len(results)} files processed, {total_matches} proprietary matches found, "
        f"{error_count} errors",
        fg=summary_color,
    )


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=5000, show_default=True, type=int)
def web(host: str, port: int) -> None:
    """Launch a local single-user web UI as an alternative to the CLI wizard.

    Requires the optional 'web' extra: `pip install -e ".[web]"`.
    """
    from . import web as web_module

    click.echo(f"Serving on http://{host}:{port} - local use only, Ctrl+C to stop.")
    try:
        web_module.run(host=host, port=port)
    except ImportError as exc:
        raise click.UsageError(
            "The web UI requires Flask. Install it with `pip install -e \".[web]\"`."
        ) from exc


if __name__ == "__main__":
    cli()
