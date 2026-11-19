"""Catalog use cases and upload transaction orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.storage import (
    MAX_COVER_BYTES,
    MAX_EPUB_BYTES,
    StorageValidationError,
    publish,
    resolve_relative,
    stage_upload,
    validate_cover,
    validate_epub,
)
from app.models import Book
from app.repositories import books as repository


class BookValidationError(Exception):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class DuplicateBookError(BookValidationError):
    def __init__(self):
        super().__init__("El EPUB ya existe", 409)


def list_books(db: Session, q: str | None, language: str | None, cursor: int | None, limit: int):
    return repository.list_published(db, q, language, cursor, limit)


def get_book(db: Session, book_id: int):
    return repository.get_published(db, book_id)


def get_epub_path(book: Book) -> Path:
    return resolve_relative(book.epub_path, "epub")


def get_cover_path(book: Book) -> Path | None:
    if book.cover_path is None:
        return None
    return resolve_relative(book.cover_path, "covers")


def create_book(db: Session, fields: dict[str, Any], epub: UploadFile, cover: UploadFile | None) -> Book:
    staged: list[Path] = []
    published: list[Path] = []
    committed = False
    try:
        epub_temp, epub_size, sha256 = stage_upload(epub, MAX_EPUB_BYTES, ".epub")
        staged.append(epub_temp)
        validate_epub(epub_temp)
        if repository.sha_exists(db, sha256):
            raise DuplicateBookError()

        cover_temp = None
        cover_suffix = None
        if cover is not None:
            cover_temp, _, _ = stage_upload(cover, MAX_COVER_BYTES, ".cover")
            staged.append(cover_temp)
            cover_suffix = validate_cover(cover_temp)

        epub_relative, epub_final = publish(epub_temp, "epub", ".epub")
        published.append(epub_final)
        cover_relative = None
        if cover_temp is not None and cover_suffix is not None:
            cover_relative, cover_final = publish(cover_temp, "covers", cover_suffix)
            published.append(cover_final)

        book = Book(
            title=fields["title"],
            author=fields["author"],
            language=fields["language"],
            description=fields.get("description"),
            epub_path=epub_relative,
            cover_path=cover_relative,
            file_size_bytes=epub_size,
            sha256=sha256,
            source_url=fields.get("source_url"),
            rights_note=fields["rights_note"],
            is_published=True,
        )
        db.add(book)
        db.commit()
        committed = True
        db.refresh(book)
        return book
    except StorageValidationError as exc:
        db.rollback()
        raise BookValidationError(str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        if repository.sha_exists(db, sha256):
            raise DuplicateBookError() from exc
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        # Files are published before commit; remove them unless the DB row exists.
        # A completed commit leaves the returned book persistent.
        for path in staged:
            path.unlink(missing_ok=True)
        if not committed:
            for path in published:
                path.unlink(missing_ok=True)
