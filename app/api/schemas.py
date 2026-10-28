from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ErrorResponse(BaseModel):
    detail: str | list


class BookOut(BaseModel):
    id: int
    title: str
    author: str
    language: str
    description: str | None
    file_size_bytes: int
    sha256: str
    source_url: str | None
    rights_note: str
    created_at: datetime
    updated_at: datetime
    average_rating: float | None
    review_count: int
    has_cover: bool
    cover_url: str | None
    download_url: str


class BookPage(BaseModel):
    items: list[BookOut]
    next_cursor: int | None


class ReviewCreate(BaseModel):
    client_review_id: UUID
    display_name: str = Field(min_length=1, max_length=80)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=1, max_length=2000)

    @field_validator("display_name", "comment")
    @classmethod
    def trim_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("No puede estar vacío")
        return value


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    book_id: int
    client_review_id: UUID
    display_name: str
    rating: int
    comment: str
    created_at: datetime


class ReviewPage(BaseModel):
    items: list[ReviewOut]
    next_cursor: int | None
