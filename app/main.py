import logging

from fastapi import FastAPI, HTTPException, Depends, File, Form, UploadFile, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.api.upload_boundary import UploadBoundaryMiddleware
from app.api.schemas import BookOut, BookPage, ErrorResponse, ReviewCreate, ReviewOut, ReviewPage
from app.infrastructure.config import cors_origins
from app.infrastructure.database import get_db
from app.services import books as book_service, reviews as review_service

app = FastAPI(title="Lector EPUB API", version="1.0.0", description="Catálogo público, descargas EPUB y reseñas anónimas. La carga requiere HTTP Basic y HTTPS fuera de localhost.")
app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])
app.add_middleware(UploadBoundaryMiddleware)
logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def unexpected_error(_request, exc: Exception):
    logger.error("Unhandled server error: %s", type(exc).__name__)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


def book_out(row: tuple) -> BookOut:
    book, average, count = row
    prefix = f"/api/v1/books/{book.id}"
    return BookOut(
        id=book.id, title=book.title, author=book.author, language=book.language,
        description=book.description, file_size_bytes=book.file_size_bytes,
        sha256=book.sha256, source_url=book.source_url, rights_note=book.rights_note,
        created_at=book.created_at, updated_at=book.updated_at,
        average_rating=round(float(average), 2) if average is not None else None,
        review_count=count, has_cover=bool(book.cover_path),
        cover_url=f"{prefix}/cover" if book.cover_path else None,
        download_url=f"{prefix}/download",
    )


@app.get("/api/v1/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/books", response_model=BookPage, tags=["books"])
def list_books(q: str | None = Query(None, max_length=255), language: str | None = Query(None, pattern=r"^[a-z]{2,8}$"), cursor: int | None = Query(None, ge=0), limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    rows = book_service.list_books(db, q, language, cursor, limit + 1)
    has_more = len(rows) > limit
    page = rows[:limit]
    return BookPage(items=[book_out(row) for row in page], next_cursor=page[-1][0].id if has_more else None)


@app.get("/api/v1/books/{book_id}", response_model=BookOut, responses={404: {"model": ErrorResponse}}, tags=["books"])
def get_book(book_id: int, db: Session = Depends(get_db)):
    row = book_service.get_book(db, book_id)
    if row is None:
        raise HTTPException(404, "Book not found")
    return book_out(row)


@app.get("/api/v1/books/{book_id}/cover", response_class=FileResponse, responses={200: {"content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}, "image/png": {"schema": {"type": "string", "format": "binary"}}, "image/webp": {"schema": {"type": "string", "format": "binary"}}}}, 404: {"model": ErrorResponse}}, tags=["books"])
def get_cover(book_id: int, db: Session = Depends(get_db)):
    row = book_service.get_book(db, book_id)
    if row is None or not row[0].cover_path:
        raise HTTPException(404, "Cover not found")
    path = book_service.get_cover_path(row[0])
    if path is None or not path.is_file():
        raise HTTPException(404, "Cover not found")
    media = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg"}.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media)


@app.get("/api/v1/books/{book_id}/download", response_class=FileResponse, responses={200: {"content": {"application/epub+zip": {"schema": {"type": "string", "format": "binary"}}}}, 404: {"model": ErrorResponse}}, tags=["books"])
def download_book(book_id: int, db: Session = Depends(get_db)):
    row = book_service.get_book(db, book_id)
    if row is None:
        raise HTTPException(404, "Book not found")
    path = book_service.get_epub_path(row[0])
    if not path.is_file():
        raise HTTPException(404, "Book file not found")
    return FileResponse(path, media_type="application/epub+zip", filename=f"book-{book_id}.epub")


@app.post("/api/v1/books", response_model=BookOut, status_code=201, responses={401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}, tags=["books"], dependencies=[Depends(require_admin)])
def create_book(title: str = Form(..., min_length=1, max_length=255), author: str = Form(..., min_length=1, max_length=255), language: str = Form(..., pattern=r"^[a-z]{2,8}$"), rights_note: str = Form(..., min_length=1), description: str | None = Form(None), source_url: str | None = Form(None), epub: UploadFile = File(...), cover: UploadFile | None = File(None), db: Session = Depends(get_db)):
    title, author, rights_note = title.strip(), author.strip(), rights_note.strip()
    if not title or not author or not rights_note:
        raise HTTPException(422, "Title, author and rights_note cannot be blank")
    fields = dict(title=title, author=author, language=language, rights_note=rights_note, description=description, source_url=source_url)
    try:
        book = book_service.create_book(db, fields, epub, cover)
    except book_service.DuplicateBookError as exc:
        raise HTTPException(409, str(exc)) from exc
    except book_service.BookValidationError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    return book_out((book, None, 0))


@app.get("/api/v1/books/{book_id}/reviews", response_model=ReviewPage, responses={404: {"model": ErrorResponse}}, tags=["reviews"])
def list_reviews(book_id: int, cursor: int | None = Query(None, ge=0), limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    try:
        reviews, next_cursor = review_service.list_reviews(db, book_id, cursor, limit)
    except review_service.ReviewBookNotFound as exc:
        raise HTTPException(404, "Book not found") from exc
    return ReviewPage(items=[ReviewOut.model_validate(x) for x in reviews], next_cursor=next_cursor)


@app.post("/api/v1/books/{book_id}/reviews", response_model=ReviewOut, status_code=201, responses={200: {"model": ReviewOut}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}, tags=["reviews"])
def create_review(book_id: int, payload: ReviewCreate, response: Response, db: Session = Depends(get_db)):
    try:
        review, created = review_service.create_review(db, book_id, payload)
    except review_service.ReviewBookNotFound as exc:
        raise HTTPException(404, "Book not found") from exc
    except review_service.ReviewConflict as exc:
        raise HTTPException(409, "Client review ID already used with different data") from exc
    if not created:
        response.status_code = 200
    return ReviewOut.model_validate(review)
