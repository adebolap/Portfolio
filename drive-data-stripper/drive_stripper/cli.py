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

from . import scaffold
from .pipeline import process_file
from .proprietary import DEFAULT_CATEGORIES


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
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts, failing instead if required input is missing.")
def strip(
    file_path: Path | None,
    mode: str | None,
    output: Path | None,
    categories: tuple[str, ...],
    custom_terms: tuple[str, ...],
    mapping_out: Path | None,
    passphrase: str | None,
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

    if mode == "scaffold" and passphrase is None and not yes:
        if click.confirm("Encrypt the scaffold mapping file with a passphrase?", default=True):
            passphrase = click.prompt("Passphrase", hide_input=True, confirmation_prompt=True)

    result = process_file(
        source=file_path,
        destination=output,
        mode=mode,
        categories=categories or None,
        custom_terms=list(custom_terms),
        mapping_destination=mapping_out,
        passphrase=passphrase,
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
@click.option("--passphrase", help="Passphrase, if the mapping file was encrypted.")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Where to write the restored text (default: stdout).")
def restore(response_path: Path | None, mapping_path: Path | None, passphrase: str | None, output: Path | None) -> None:
    """Restore original values into a model's response using a saved scaffold mapping."""
    if response_path is None:
        response_path = Path(click.prompt("File containing the model's response", type=click.Path(exists=True, dir_okay=False)))
    if mapping_path is None:
        mapping_path = Path(click.prompt("Scaffold mapping file", type=click.Path(exists=True, dir_okay=False)))

    mapping_bytes_start = mapping_path.read_bytes()[:1]
    if passphrase is None and mapping_bytes_start not in (b"{", b""):
        passphrase = click.prompt("Passphrase", hide_input=True)

    mapping = scaffold.load_mapping(mapping_path, passphrase)
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


if __name__ == "__main__":
    cli()
