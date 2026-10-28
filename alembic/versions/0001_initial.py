"""Initial book catalogue and reviews.

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("author", sa.String(255), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("epub_path", sa.String(512), nullable=False),
        sa.Column("cover_path", sa.String(512), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("rights_note", sa.Text(), nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("sha256", name="uq_books_sha256"),
    )
    op.create_index("ix_books_published_id", "books", ["is_published", "id"])
    op.create_table(
        "reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("book_id", sa.BigInteger(), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("client_review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating"),
        sa.CheckConstraint("char_length(display_name) BETWEEN 1 AND 80", name="ck_reviews_display_name_length"),
        sa.CheckConstraint("char_length(comment) BETWEEN 1 AND 2000", name="ck_reviews_comment_length"),
        sa.UniqueConstraint("client_review_id", name="uq_reviews_client_review_id"),
    )
    op.create_index("ix_reviews_book_id_id", "reviews", ["book_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_reviews_book_id_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_books_published_id", table_name="books")
    op.drop_table("books")
