"""PostgreSQL queries for the published catalog and its rating aggregates."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Book, Review


def list_published(db: Session, q: str | None, language: str | None, cursor: int | None, limit: int):
    query = (
        select(Book, func.avg(Review.rating), func.count(Review.id))
        .outerjoin(Review, Review.book_id == Book.id)
        .where(Book.is_published.is_(True))
        .group_by(Book.id)
        .order_by(Book.id)
        .limit(limit)
    )
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(or_(Book.title.ilike(pattern, escape="\\"), Book.author.ilike(pattern, escape="\\")))
    if language:
        query = query.where(Book.language == language)
    if cursor is not None:
        query = query.where(Book.id > cursor)
    return db.execute(query).all()


def get_published(db: Session, book_id: int):
    query = (
        select(Book, func.avg(Review.rating), func.count(Review.id))
        .outerjoin(Review, Review.book_id == Book.id)
        .where(Book.id == book_id, Book.is_published.is_(True))
        .group_by(Book.id)
    )
    return db.execute(query).one_or_none()


def sha_exists(db: Session, sha256: str) -> bool:
    return db.scalar(select(Book.id).where(Book.sha256 == sha256).limit(1)) is not None
