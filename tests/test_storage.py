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
