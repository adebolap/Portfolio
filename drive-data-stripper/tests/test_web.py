import io
import zipfile

import pytest

flask = pytest.importorskip("flask")

from drive_stripper.web import create_app


@pytest.fixture
def client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_index_renders_form(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"drive-data-stripper" in response.data


def test_submit_without_file_shows_error(client):
    response = client.post("/", data={"mode": "strip"}, content_type="multipart/form-data")
    assert response.status_code == 200
    assert b"Choose a file first" in response.data


def test_strip_mode_returns_sanitized_file_download(client):
    data = {
        "file": (io.BytesIO(b"email jane@acme.com"), "notes.txt"),
        "mode": "strip",
        "categories": "email",
        "custom_terms": "",
        "passphrase": "",
    }
    response = client.post("/", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("attachment")
    assert b"jane@acme.com" not in response.data


def test_scaffold_mode_returns_zip_with_mapping(client):
    data = {
        "file": (io.BytesIO(b"email jane@acme.com"), "notes.txt"),
        "mode": "scaffold",
        "categories": "email",
        "custom_terms": "",
        "passphrase": "",
    }
    response = client.post("/", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(response.data)) as zf:
        names = zf.namelist()
        assert "scaffold-map.json" in names
        sanitized_name = [n for n in names if n != "scaffold-map.json"][0]
        assert b"jane@acme.com" not in zf.read(sanitized_name)
