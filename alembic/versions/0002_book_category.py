"""Add category to books and backfill existing rows.

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
    op.add_column(
        "books",
        sa.Column("category", sa.String(80), nullable=False, server_default="Sin categoría"),
    )
    op.create_check_constraint(
        "ck_books_category_length",
        "books",
        "char_length(btrim(category)) BETWEEN 1 AND 80",
    )


def downgrade() -> None:
    op.drop_constraint("ck_books_category_length", "books", type_="check")
    op.drop_column("books", "category")
