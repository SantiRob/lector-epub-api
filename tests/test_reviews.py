"""Review semantics against the migrated PostgreSQL schema."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models import Book
from app.services.reviews import ReviewBookNotFound, ReviewConflict, create_review, list_reviews


def _book(session, *, published=True):
    book = Book(
        title="A public domain book",
        author="An Author",
        language="en",
        epub_path="epubs/test.epub",
        file_size_bytes=123,
        sha256=uuid4().hex.ljust(64, "0"),
        rights_note="Public domain edition",
        is_published=published,
    )
    session.add(book)
    session.commit()
    session.refresh(book)
    return book


def _payload(*, uuid=None, name=" Reader ", rating=5, comment=" Excellent "):
    return SimpleNamespace(
        client_review_id=uuid or uuid4(),
        display_name=name,
        rating=rating,
        comment=comment,
    )


def test_create_retry_conflict_and_pagination(db_session):
    book = _book(db_session)
    first_payload = _payload()
    first, created = create_review(db_session, book.id, first_payload)
    assert created and first.display_name == "Reader" and first.comment == "Excellent"

    same, created = create_review(
        db_session,
        book.id,
        _payload(uuid=first_payload.client_review_id, name="Reader", comment="Excellent"),
    )
    assert not created and same.id == first.id

    with pytest.raises(ReviewConflict):
        create_review(
            db_session, book.id, _payload(uuid=first_payload.client_review_id, comment="Changed")
        )
    with pytest.raises(ReviewConflict):
        create_review(db_session, book.id + 999, first_payload)

    second, _ = create_review(db_session, book.id, _payload())
    page, cursor = list_reviews(db_session, book.id, limit=1)
    assert [review.id for review in page] == [first.id]
    assert cursor == first.id
    page, cursor = list_reviews(db_session, book.id, after_id=cursor, limit=1)
    assert [review.id for review in page] == [second.id]
    assert cursor is None


def test_validation_and_unpublished_book(db_session):
    book = _book(db_session)
    for invalid in (
        _payload(name="  "),
        _payload(comment=" "),
        _payload(comment="x" * 2001),
        _payload(name="x" * 81),
        _payload(rating=0),
        _payload(rating=6),
    ):
        with pytest.raises(ValueError):
            create_review(db_session, book.id, invalid)

    unpublished = _book(db_session, published=False)
    with pytest.raises(ReviewBookNotFound):
        create_review(db_session, unpublished.id, _payload())
    with pytest.raises(ReviewBookNotFound):
        list_reviews(db_session, unpublished.id)


def test_public_review_http_contract(client, db_session):
    book = _book(db_session)
    payload = {
        "client_review_id": str(uuid4()),
        "display_name": " Ana ",
        "rating": 4,
        "comment": " Buen libro ",
    }
    url = f"/api/v1/books/{book.id}/reviews"
    created = client.post(url, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["display_name"] == "Ana"
    assert created.json()["comment"] == "Buen libro"

    retry = client.post(url, json=payload)
    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == created.json()["id"]

    changed = client.post(url, json={**payload, "rating": 1})
    assert changed.status_code == 409, changed.text

    listed = client.get(url)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 1
    assert listed.json()["items"][0]["id"] == created.json()["id"]

    invalid = client.post(url, json={**payload, "client_review_id": str(uuid4()), "comment": " "})
    assert invalid.status_code == 422, invalid.text
