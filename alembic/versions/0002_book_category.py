"""Add optional book category for catalog filters.

Revision ID: 0002_book_category
Revises: 0001_initial
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_book_category"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("books", sa.Column("category", sa.String(32), nullable=True))
    op.create_index("ix_books_category", "books", ["category"])


def downgrade() -> None:
    op.drop_index("ix_books_category", table_name="books")
    op.drop_column("books", "category")
