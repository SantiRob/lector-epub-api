"""File validation checks that do not require PostgreSQL."""

from pathlib import Path

import pytest

from app.infrastructure.storage import StorageValidationError, resolve_relative, validate_cover, validate_epub
from tests.test_catalog import epub_bytes, png_bytes


def test_epub_readability(tmp_path):
    good = tmp_path / "good.epub"
    good.write_bytes(epub_bytes())
    validate_epub(good)
    bad = tmp_path / "bad.epub"
    bad.write_bytes(epub_bytes(b"not xml"))
    with pytest.raises(StorageValidationError):
        validate_epub(bad)


def test_epub_accepts_xhtml_named_entities(tmp_path):
    doctype = b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
    book = tmp_path / "entities.epub"
    book.write_bytes(epub_bytes(doctype + b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Hola&nbsp;&mdash;&aacute;</p></body></html>'))
    validate_epub(book)
    unknown = tmp_path / "unknown.epub"
    unknown.write_bytes(epub_bytes(doctype + b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>&notanentity;</p></body></html>'))
    with pytest.raises(StorageValidationError):
        validate_epub(unknown)


def test_cover_content_and_path_containment(tmp_path, monkeypatch):
    image = tmp_path / "cover.bin"
    image.write_bytes(png_bytes())
    assert validate_cover(image) == ".png"
    image.write_bytes(b"not an image")
    with pytest.raises(StorageValidationError):
        validate_cover(image)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    with pytest.raises(StorageValidationError):
        resolve_relative("epub/../../outside.epub", "epub")
