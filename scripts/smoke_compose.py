"""Small HTTP smoke and persistence check for a running Compose stack."""

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx

from tests.test_catalog import epub_bytes, png_bytes

BASE = "http://127.0.0.1:8000"
STATE = Path(".smoke-state.json")


def run() -> None:
    with httpx.Client(base_url=BASE, timeout=20) as client:
        if sys.argv[1] == "create":
            chapter = f'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>{uuid4()}</p></body></html>'.encode()
            epub = epub_bytes(chapter)
            result = client.post(
                "/api/v1/books",
                data={"title": "Prueba persistente", "author": "Prueba", "language": "es", "rights_note": "Archivo de prueba generado"},
                files={"epub": ("sample.epub", epub, "application/epub+zip"), "cover": ("sample.png", png_bytes(), "image/png")},
                auth=(os.environ["ADMIN_USERNAME"], os.environ["ADMIN_PASSWORD"]),
            )
            assert result.status_code == 201, result.text
            book = result.json()
            result = client.post(
                f"/api/v1/books/{book['id']}/reviews",
                json={"client_review_id": str(uuid4()), "display_name": "Prueba", "rating": 5, "comment": "Persiste"},
            )
            assert result.status_code == 201, result.text
            STATE.write_text(json.dumps({"book_id": book["id"], "review_id": result.json()["id"], "sha256": hashlib.sha256(epub).hexdigest()}))
        else:
            state = json.loads(STATE.read_text())
            result = client.get(f"/api/v1/books/{state['book_id']}")
            assert result.status_code == 200, result.text
            book = result.json()
            assert book["sha256"] == state["sha256"] and book["review_count"] >= 1
            result = client.get(book["download_url"])
            assert result.status_code == 200 and hashlib.sha256(result.content).hexdigest() == state["sha256"]
            result = client.get(book["cover_url"])
            assert result.status_code == 200 and result.headers["content-type"] == "image/png"
            result = client.get(f"/api/v1/books/{state['book_id']}/reviews")
            assert result.status_code == 200 and any(x["id"] == state["review_id"] for x in result.json()["items"])
        print(json.dumps({"mode": sys.argv[1], "status": "ok"}))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("create", "verify"):
        raise SystemExit("Usage: python scripts/smoke_compose.py create|verify")
    run()
