"""Database operations for public reviews."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, Review


def published_book_exists(session: Session, book_id: int) -> bool:
    return session.scalar(
        select(Book.id).where(Book.id == book_id, Book.is_published.is_(True))
    ) is not None


def get_by_client_id(session: Session, client_review_id: UUID) -> Review | None:
    return session.scalar(
        select(Review).where(Review.client_review_id == client_review_id)
    )


def list_for_book(
    session: Session, book_id: int, after_id: int | None, limit: int
) -> list[Review]:
    statement = select(Review).where(Review.book_id == book_id)
    if after_id is not None:
        statement = statement.where(Review.id > after_id)
    return list(session.scalars(statement.order_by(Review.id).limit(limit + 1)))
