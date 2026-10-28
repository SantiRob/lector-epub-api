"""HTTP integration tests against migrated PostgreSQL and isolated storage."""

from io import BytesIO
from base64 import b64encode
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from PIL import Image


def epub_bytes(chapter: bytes = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Hola</p></body></html>') -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            compress_type=ZIP_DEFLATED,
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">test</dc:identifier></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>',
            compress_type=ZIP_DEFLATED,
        )
        archive.writestr("OEBPS/chapter.xhtml", chapter, compress_type=ZIP_DEFLATED)
    return stream.getvalue()


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(stream, format="PNG")
    return stream.getvalue()


def upload(client, *, title="Libro", author="Autora", language="es", epub=None, cover=True):
    files = {"epub": ("anything.epub", epub if epub is not None else epub_bytes(), "application/octet-stream")}
    if cover:
        files["cover"] = ("anything.png", png_bytes(), "application/octet-stream")
    return client.post(
        "/api/v1/books",
        data={"title": title, "author": author, "language": language, "rights_note": "Distribución permitida"},
        files=files,
        auth=("test-admin", "test-password"),
    )


def test_auth_upload_detail_cover_download(client):
    fields = {"title": "Libro", "author": "Autora", "language": "es", "rights_note": "Distribución permitida"}
    files = {"epub": ("test.epub", epub_bytes(), "application/epub+zip")}
    assert client.post("/api/v1/books", data=fields, files=files).status_code == 401
    assert client.post("/api/v1/books", data=fields, files=files, auth=("bad", "bad")).status_code == 401
    response = upload(client)
    assert response.status_code == 201, response.text
    book = response.json()
    assert book["has_cover"] and book["cover_url"].startswith("/api/v1/")
    assert "epub_path" not in book and "cover_path" not in book
    assert client.get(f"/api/v1/books/{book['id']}").status_code == 200
    cover = client.get(book["cover_url"])
    assert cover.status_code == 200 and cover.headers["content-type"] == "image/png"
    download = client.get(book["download_url"])
    assert download.status_code == 200 and download.headers["content-type"] == "application/epub+zip"
    assert download.content == epub_bytes()


def test_search_filter_cursor_and_aggregates(client):
    assert upload(client, title="Árbol", author="Ana").status_code == 201
    assert upload(client, title="Mar", author="Beto", epub=epub_bytes(b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Adios</p></body></html>'), cover=False).status_code == 201
    assert upload(client, title="Sol", author="Ana", language="en", epub=epub_bytes(b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Mundo</p></body></html>'), cover=False).status_code == 201
    result = client.get("/api/v1/books", params={"q": "Ana", "language": "es"}).json()
    assert [book["title"] for book in result["items"]] == ["Árbol"]
    first = client.get("/api/v1/books", params={"limit": 1}).json()
    assert len(first["items"]) == 1 and first["next_cursor"] is not None
    second = client.get("/api/v1/books", params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert second["items"][0]["id"] > first["items"][0]["id"]
    assert first["items"][0]["review_count"] == 0
    review = client.post(f"/api/v1/books/{first['items'][0]['id']}/reviews", json={"client_review_id": str(uuid4()), "display_name": "Lector", "rating": 4, "comment": "Bueno"})
    assert review.status_code == 201, review.text
    detail = client.get(f"/api/v1/books/{first['items'][0]['id']}").json()
    assert detail["review_count"] == 1 and detail["average_rating"] == 4


def test_invalid_oversized_duplicate_and_malformed_spine(client):
    assert upload(client, epub=b"not a zip").status_code == 422
    assert upload(client, epub=b"x" * (25 * 1024 * 1024 + 1)).status_code == 422
    assert upload(client, epub=epub_bytes(b"not xml")).status_code == 422
    assert upload(client).status_code == 201
    assert upload(client).status_code == 409


def test_request_body_boundary_before_parsing(client):
    huge = b"x" * (31 * 1024 * 1024 + 1)
    fields = {"title": "T", "author": "A", "language": "es", "rights_note": "Permitido"}
    files = {"epub": ("huge.epub", huge, "application/epub+zip")}
    assert client.post("/api/v1/books", data=fields, files=files).status_code == 401
    assert client.post("/api/v1/books", data=fields, files=files, auth=("test-admin", "test-password")).status_code == 413
    auth = "Basic " + b64encode(b"test-admin:test-password").decode()
    streamed = client.post("/api/v1/books", content=iter([b"x" * (16 * 1024 * 1024), b"x" * (16 * 1024 * 1024)]), headers={"Authorization": auth, "Content-Type": "application/octet-stream"})
    assert streamed.status_code == 413
    assert client.post("/api/v1/books/1/reviews", content=b"x" * 65537, headers={"Content-Type": "application/json"}).status_code == 413
