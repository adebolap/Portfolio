"""Local, single-user web UI - a browser form alternative to the CLI wizard.

This is not a hosted multi-tenant service: there's no authentication, no
persisted sessions, and no upload history. Each request is processed
entirely inside a temporary directory that's deleted before the response is
sent, and the sanitized file (plus any scaffold mapping / PDF sidecar) comes
back as a single download. It's meant to be run on localhost by whoever is
at the keyboard, same trust model as the CLI.

Requires the optional `web` extra: `pip install -e ".[web]"`.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from .pipeline import process_file
from .proprietary import DEFAULT_CATEGORIES

_PAGE_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>drive-data-stripper</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 3rem auto; color: #1a1a1a; }
    h1 { font-size: 1.4rem; }
    fieldset { border: 1px solid #ccc; border-radius: 6px; margin-bottom: 1rem; }
    label { display: block; margin: 0.4rem 0; }
    .categories label { display: inline-block; margin-right: 1rem; }
    input[type=submit] { padding: 0.5rem 1.2rem; font-size: 1rem; }
    .error { color: #b00020; }
    .hint { color: #555; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>drive-data-stripper</h1>
  <p class="hint">Strip proprietary data and metadata from a file before sharing it with an AI model.</p>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post" enctype="multipart/form-data">
    <fieldset>
      <legend>File</legend>
      <input type="file" name="file" required>
    </fieldset>
    <fieldset>
      <legend>Mode</legend>
      <label><input type="radio" name="mode" value="strip" checked> strip - permanently remove proprietary content</label>
      <label><input type="radio" name="mode" value="scaffold"> scaffold - reversible placeholder tokens (downloads a mapping file too)</label>
      <label><input type="radio" name="mode" value="metadata-only"> metadata-only - leave content as-is, only clean file metadata</label>
    </fieldset>
    <fieldset class="categories">
      <legend>Categories to scan (none checked = all)</legend>
      {% for c in categories %}
      <label><input type="checkbox" name="categories" value="{{ c }}"> {{ c }}</label>
      {% endfor %}
    </fieldset>
    <fieldset>
      <legend>Custom terms (comma-separated, e.g. company name or codename)</legend>
      <input type="text" name="custom_terms" style="width: 100%;">
    </fieldset>
    <fieldset>
      <legend>Passphrase (scaffold mode only, optional)</legend>
      <input type="password" name="passphrase" style="width: 100%;">
    </fieldset>
    <input type="submit" value="Sanitize and download">
  </form>
</body>
</html>
"""


def _render(error: str | None = None) -> str:
    from flask import render_template_string

    return render_template_string(_PAGE_TEMPLATE, categories=DEFAULT_CATEGORIES, error=error)


def create_app():
    from flask import Flask, request, send_file

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

    @app.get("/")
    def index():
        return _render()

    @app.post("/")
    def submit():
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return _render(error="Choose a file first.")

        mode = request.form.get("mode", "strip")
        categories = tuple(request.form.getlist("categories")) or None
        custom_terms = [t.strip() for t in request.form.get("custom_terms", "").split(",") if t.strip()]
        passphrase = request.form.get("passphrase") or None

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / uploaded.filename
            uploaded.save(source)
            destination = tmp_path / f"sanitized_{uploaded.filename}"
            mapping_destination = tmp_path / "scaffold-map.json" if mode == "scaffold" else None

            try:
                result = process_file(
                    source,
                    destination,
                    mode=mode,
                    categories=categories,
                    custom_terms=custom_terms,
                    mapping_destination=mapping_destination,
                    passphrase=passphrase,
                )
            except Exception as exc:
                return _render(error=str(exc))

            extras = []
            if result.pdf_text_sidecar and result.pdf_text_sidecar.exists():
                extras.append(result.pdf_text_sidecar)
            if result.mapping_path and result.mapping_path.exists():
                extras.append(result.mapping_path)

            if extras:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(destination, arcname=destination.name)
                    for path in extras:
                        zf.write(path, arcname=path.name)
                buffer.seek(0)
                return send_file(
                    buffer,
                    as_attachment=True,
                    download_name=f"{destination.name}.zip",
                    mimetype="application/zip",
                )

            return send_file(
                io.BytesIO(destination.read_bytes()),
                as_attachment=True,
                download_name=destination.name,
            )

    return app


def run(host: str = "127.0.0.1", port: int = 5000) -> None:
    create_app().run(host=host, port=port)
