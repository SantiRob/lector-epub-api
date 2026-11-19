"""Seed the catalog with every EPUB found in SEED_DIR (default: /app/seed/books).

Idempotent: books whose SHA-256 already exists are skipped, so it is safe to run
on every container start. Metadata (title, author, language, description, cover)
comes from the EPUB's OPF package, falling back to "Title - Author.epub" filenames.
Category: public-domain books default to "classics", the rest to "novels"; override
per file in SEED_DIR/categories.json ({"file.epub": "poetry"}). Existing books with
no category are backfilled.

Usage:
    python -m scripts.seed_books            # seed the database (needs DATABASE_URL)
    python -m scripts.seed_books --check    # validate + print metadata, no database
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote
from xml.etree import ElementTree

from PIL import Image

DEFAULT_SEED_DIR = "/app/seed/books"
DEFAULT_RIGHTS_NOTE = "Copia privada usada solo para pruebas locales. No redistribuir."
MAX_COVER_BYTES = 5 * 1024 * 1024
COVER_MAX_SIDE = 1200


def _text(node) -> str | None:
    if node is None or node.text is None:
        return None
    value = re.sub(r"\s+", " ", node.text).strip()
    return value or None


def _clean_description(raw: str | None) -> str | None:
    if not raw:
        return None
    value = re.sub(r"<[^>]+>", " ", raw)
    value = re.sub(r"\s+", " ", html.unescape(value)).strip()
    return value[:4000] or None


def _language(raw: str | None) -> str:
    code = (raw or "").strip().lower().replace("_", "-").split("-")[0]
    return code if re.fullmatch(r"[a-z]{2,8}", code) else "es"


def _from_filename(path: Path) -> tuple[str, str | None]:
    stem = path.stem
    if " - " in stem:
        title, author = stem.rsplit(" - ", 1)
        return title.strip(), author.strip()
    return stem.strip(), None


def _find_cover(archive: zipfile.ZipFile, opf, opf_name: str) -> bytes | None:
    manifest = opf.find("{*}manifest")
    if manifest is None:
        return None
    items = manifest.findall("{*}item")
    by_id = {i.get("id"): i for i in items}
    candidate = None
    for item in items:  # EPUB 3
        if "cover-image" in (item.get("properties") or "").split():
            candidate = item
            break
    if candidate is None:  # EPUB 2 <meta name="cover" content="id">
        for meta in opf.iter():
            if meta.tag.rsplit("}", 1)[-1] == "meta" and meta.get("name") == "cover":
                candidate = by_id.get(meta.get("content"))
                break
    if candidate is None:  # heuristic
        for item in items:
            if (item.get("media-type") or "").startswith("image/") and "cover" in (
                (item.get("id") or "") + (item.get("href") or "")
            ).lower():
                candidate = item
                break
    if candidate is None or not (candidate.get("media-type") or "").startswith("image/"):
        return None
    href = unquote(candidate.get("href").split("#", 1)[0])
    name = posixpath.normpath(posixpath.join(posixpath.dirname(opf_name), href))
    try:
        return archive.read(name)
    except KeyError:
        return None


def normalize_cover(data: bytes | None) -> tuple[bytes, str] | None:
    """Return (bytes, filename) accepted by the API (JPG/PNG/WebP, <= 5 MB)."""
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            if fmt in ("JPEG", "PNG", "WEBP") and len(data) <= MAX_COVER_BYTES:
                img.verify()
                return data, {"JPEG": "cover.jpg", "PNG": "cover.png", "WEBP": "cover.webp"}[fmt]
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail((COVER_MAX_SIDE, COVER_MAX_SIDE))
            out = io.BytesIO()
            img.save(out, "JPEG", quality=85)
            return out.getvalue(), "cover.jpg"
    except Exception:
        return None


def extract_metadata(path: Path) -> dict:
    fallback_title, fallback_author = _from_filename(path)
    meta = {"title": fallback_title, "author": fallback_author, "language": "es", "description": None,
            "cover": None, "rights_note": None, "source_url": None}
    with zipfile.ZipFile(path) as archive:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        opf_name = container.find(".//{*}rootfile").get("full-path")
        opf = ElementTree.fromstring(archive.read(opf_name))
        md = opf.find("{*}metadata")
        if md is not None:
            title = _text(md.find("{*}title"))
            creator = _text(md.find("{*}creator"))
            meta["language"] = _language(_text(md.find("{*}language")))
            desc_node = md.find("{*}description")
            meta["description"] = _clean_description(desc_node.text if desc_node is not None else None)
            # Prefer OPF values (they usually keep accents); fall back to the filename.
            meta["title"] = (title or fallback_title).split(" / ")[0].strip()[:255]
            if creator in ("Anonymous", "Unknown"):
                creator = "Anónimo"
            author = re.sub(r"\b([A-Z])\.\s*(?=[A-Z]\.)", r"\1. ", creator or fallback_author or "Desconocido")
            meta["author"] = author[:255]
            rights = _text(md.find("{*}rights"))
            if rights and "public domain" in rights.lower():
                meta["rights_note"] = "Dominio público (Project Gutenberg)."
                for node in md.findall("{*}source") + md.findall("{*}identifier"):
                    value = _text(node) or ""
                    if value.startswith("http"):
                        meta["source_url"] = value
                        break
        meta["cover"] = normalize_cover(_find_cover(archive, opf, opf_name))
    return meta


def load_category_overrides(seed_dir: Path) -> dict[str, str]:
    path = seed_dir / "categories.json"
    if not path.is_file():
        return {}
    return {name: value.strip().lower() for name, value in json.loads(path.read_text(encoding="utf-8")).items()}


def category_for(path: Path, meta: dict, overrides: dict[str, str]) -> str:
    if path.name in overrides:
        return overrides[path.name]
    return "classics" if meta.get("rights_note") else "novels"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def check(seed_dir: Path) -> int:
    import tempfile

    from app.infrastructure.storage import StorageValidationError, validate_cover, validate_epub

    failures = 0
    overrides = load_category_overrides(seed_dir)
    for path in sorted(seed_dir.glob("*.epub")):
        try:
            validate_epub(path)
            m = extract_metadata(path)
            category = category_for(path, m, overrides)
            if m["cover"]:
                with tempfile.NamedTemporaryFile(suffix=".cover") as tmp:
                    tmp.write(m["cover"][0]); tmp.flush()
                    validate_cover(Path(tmp.name))
            cover = f"{m['cover'][1]} {len(m['cover'][0]) // 1024}KB" if m["cover"] else "SIN PORTADA"
            print(f"OK   {path.name}\n     -> {m['title']} | {m['author']} | {m['language']} | {category} | {cover} | desc={'sí' if m['description'] else 'no'} | {m['rights_note'] or 'privada'}")
        except StorageValidationError as exc:
            failures += 1
            print(f"FAIL {path.name}: {exc} ({exc.__cause__!r})")
    return 1 if failures else 0


def seed(seed_dir: Path) -> int:
    from sqlalchemy import select

    from app.infrastructure.database import get_session_factory
    from app.models import Book
    from app.repositories import books as repository
    from app.services import books as book_service

    rights_note = os.environ.get("SEED_RIGHTS_NOTE", DEFAULT_RIGHTS_NOTE)
    overrides = load_category_overrides(seed_dir)
    created = skipped = updated = failed = 0
    with get_session_factory()() as db:
        for path in sorted(seed_dir.glob("*.epub")):
            sha256 = _sha256(path)
            if repository.sha_exists(db, sha256):
                skipped += 1
                existing = db.scalar(select(Book).where(Book.sha256 == sha256))
                if existing is not None and existing.category is None:
                    existing.category = category_for(path, extract_metadata(path), overrides)
                    db.commit()
                    updated += 1
                continue
            try:
                m = extract_metadata(path)
                fields = dict(title=m["title"], author=m["author"], language=m["language"],
                              category=category_for(path, m, overrides),
                              rights_note=m["rights_note"] or rights_note, description=m["description"],
                              source_url=m["source_url"])
                with path.open("rb") as epub_fh:
                    cover = SimpleNamespace(file=io.BytesIO(m["cover"][0])) if m["cover"] else None
                    book = book_service.create_book(db, fields, SimpleNamespace(file=epub_fh), cover)
                created += 1
                print(f"[seed] +{book.id} {book.title}")
            except Exception as exc:  # keep seeding the rest
                failed += 1
                print(f"[seed] FAIL {path.name}: {getattr(exc, 'detail', exc)}", file=sys.stderr)
    print(f"[seed] creados={created} existentes={skipped} categorizados={updated} fallidos={failed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validar y mostrar metadatos sin base de datos")
    parser.add_argument("--dir", default=os.environ.get("SEED_DIR", DEFAULT_SEED_DIR))
    args = parser.parse_args()
    seed_dir = Path(args.dir)
    if not seed_dir.is_dir():
        print(f"[seed] {seed_dir} no existe; nada que sembrar")
        return 0
    return check(seed_dir) if args.check else seed(seed_dir)


if __name__ == "__main__":
    raise SystemExit(main())
