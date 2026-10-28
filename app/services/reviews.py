"""Review use cases and idempotent offline sync."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Review
from app.repositories import reviews as repository


class ReviewBookNotFound(Exception):
    """The book is unavailable to the public."""


class ReviewConflict(Exception):
    """A client UUID has already been used for another review payload."""


def _same_payload(existing: Review, book_id: int, payload, name: str, comment: str) -> bool:
    return (
        existing.book_id == book_id
        and existing.display_name == name
        and existing.rating == payload.rating
        and existing.comment == comment
    )


def create_review(session: Session, book_id: int, payload) -> tuple[Review, bool]:
    """Create once per client UUID, returning (review, newly_created).

    The unique database constraint is the concurrency arbiter.  A nested
    transaction lets the session recover from a simultaneous insert without
    losing the surrounding transaction.
    """
    name = payload.display_name.strip()
    comment = payload.comment.strip()
    if not name or not comment or len(name) > 80 or len(comment) > 2000:
        raise ValueError("Invalid review text")
    if not 1 <= payload.rating <= 5:
        raise ValueError("Rating must be between 1 and 5")

    existing = repository.get_by_client_id(session, payload.client_review_id)
    if existing is not None:
        if not _same_payload(existing, book_id, payload, name, comment):
            raise ReviewConflict
        if not repository.published_book_exists(session, book_id):
            raise ReviewBookNotFound
        return existing, False

    if not repository.published_book_exists(session, book_id):
        raise ReviewBookNotFound

    review = Review(
        book_id=book_id,
        client_review_id=payload.client_review_id,
        display_name=name,
        rating=payload.rating,
        comment=comment,
    )
    try:
        with session.begin_nested():
            session.add(review)
            session.flush()
    except IntegrityError:
        # PostgreSQL waits for an in-flight insert with the same unique UUID.
        # After its savepoint is rolled back, the committed winner is visible.
        existing = repository.get_by_client_id(session, payload.client_review_id)
        if existing is None:
            raise
        if _same_payload(existing, book_id, payload, name, comment):
            return existing, False
        raise ReviewConflict
    session.commit()
    session.refresh(review)
    return review, True


def list_reviews(
    session: Session, book_id: int, after_id: int | None = None, limit: int = 20
) -> tuple[list[Review], int | None]:
    """List reviews in stable creation order with an exclusive ID cursor."""
    if not repository.published_book_exists(session, book_id):
        raise ReviewBookNotFound
    if limit < 1 or limit > 50 or (after_id is not None and after_id < 0):
        raise ValueError("Invalid pagination")
    rows = repository.list_for_book(session, book_id, after_id, limit)
    has_more = len(rows) > limit
    page = rows[:limit]
    return page, page[-1].id if has_more else None
