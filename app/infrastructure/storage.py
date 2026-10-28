"""Bounded validation and private filesystem storage for uploaded media."""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import shutil
import tempfile
import uuid
import warnings
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
from xml.etree import ElementTree

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

MAX_EPUB_BYTES = 25 * 1024 * 1024
MAX_COVER_BYTES = 5 * 1024 * 1024
MAX_ZIP_MEMBERS = 2000
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_MEMBER_BYTES = 20 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class StorageValidationError(ValueError):
    pass


def storage_root() -> Path:
    return Path(os.environ.get("STORAGE_DIR", "./data")).resolve()


def _category_dir(category: str) -> Path:
    if category not in ("epub", "covers", "staging"):
        raise StorageValidationError("Directorio de almacenamiento inválido")
    root = storage_root()
    directory = root / category
    if directory.is_symlink() or directory.resolve().parent != root:
        raise StorageValidationError("Directorio de almacenamiento inválido")
    return directory


def resolve_relative(relative: str, category: str) -> Path:
    """Resolve only an internally generated path inside the expected category."""
    p = PurePosixPath(relative)
    suffixes = {"epub": "epub", "covers": "(?:jpg|png|webp)"}
    pattern = suffixes.get(category)
    if (
        p.is_absolute()
        or len(p.parts) != 2
        or p.parts[0] != category
        or pattern is None
        or re.fullmatch(rf"[0-9a-f]{{32}}\.{pattern}", p.parts[1]) is None
    ):
        raise StorageValidationError("Ruta de archivo inválida")
    directory = _category_dir(category)
    resolved = (directory / p.parts[1]).resolve()
    if resolved.parent != directory.resolve():
        raise StorageValidationError("Ruta de archivo inválida")
    return resolved


def stage_upload(upload: UploadFile, max_bytes: int, suffix: str) -> tuple[Path, int, str]:
    """Stream an upload into a private temporary file with a hard byte limit."""
    staging = _category_dir("staging")
    staging.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    fd, name = tempfile.mkstemp(prefix="upload-", suffix=suffix, dir=staging)
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise StorageValidationError("El archivo supera el tamaño permitido")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise StorageValidationError("El archivo está vacío")
        return path, size, digest.hexdigest()
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _safe_zip_member(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and "\\" not in name and ".." not in p.parts


def validate_epub(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_ZIP_MEMBERS:
                raise StorageValidationError("EPUB inválido o con demasiados archivos")
            if members[0].filename != "mimetype" or members[0].compress_type != zipfile.ZIP_STORED:
                raise StorageValidationError("El EPUB requiere mimetype sin compresión como primer archivo")
            names = set()
            total = 0
            for member in members:
                if not _safe_zip_member(member.filename) or member.filename in names:
                    raise StorageValidationError("EPUB contiene rutas inválidas o duplicadas")
                names.add(member.filename)
                if member.flag_bits & 0x1 or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise StorageValidationError("EPUB contiene archivos cifrados o compresión no admitida")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise StorageValidationError("EPUB contiene enlaces simbólicos")
                total += member.file_size
                if total > MAX_EXPANDED_BYTES or member.file_size > MAX_MEMBER_BYTES:
                    raise StorageValidationError("EPUB descomprimido demasiado grande")
                if member.file_size and (not member.compress_size or member.file_size / member.compress_size > MAX_COMPRESSION_RATIO):
                    raise StorageValidationError("EPUB con relación de compresión insegura")
            if "META-INF/container.xml" not in names:
                raise StorageValidationError("EPUB sin container.xml")
            if archive.read("mimetype") != b"application/epub+zip":
                raise StorageValidationError("Tipo de archivo EPUB inválido")
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            opf_name = rootfile.get("full-path") if rootfile is not None else None
            if not opf_name or not _safe_zip_member(opf_name) or opf_name not in names:
                raise StorageValidationError("EPUB sin paquete OPF válido")
            opf = ElementTree.fromstring(archive.read(opf_name))
            if opf.tag.rsplit("}", 1)[-1] != "package":
                raise StorageValidationError("Paquete OPF inválido")
            manifest = opf.find("{*}manifest")
            spine = opf.find("{*}spine")
            items = {} if manifest is None else {
                item.get("id"): (item.get("href"), item.get("media-type"))
                for item in manifest.findall("{*}item")
                if item.get("id") and item.get("href")
            }
            refs = [] if spine is None else [ref.get("idref") for ref in spine.findall("{*}itemref")]
            if not items or not refs or any(ref not in items for ref in refs):
                raise StorageValidationError("EPUB sin manifiesto o secuencia de lectura válidos")
            base = str(PurePosixPath(opf_name).parent)
            for ref in refs:
                raw_href, media_type = items[ref]
                if media_type not in ("application/xhtml+xml", "image/svg+xml"):
                    raise StorageValidationError("Tipo de contenido de lectura no admitido")
                href = unquote(raw_href.split("#", 1)[0])
                document = posixpath.normpath(posixpath.join(base, href))
                if not _safe_zip_member(document) or document not in names:
                    raise StorageValidationError("EPUB con contenido de lectura faltante")
                root = ElementTree.fromstring(archive.read(document))
                expected = "html" if media_type == "application/xhtml+xml" else "svg"
                if root.tag.rsplit("}", 1)[-1] != expected:
                    raise StorageValidationError("Contenido de lectura inválido")
            # Read every entry to detect truncated or corrupt compressed data and CRC errors.
            for member in members:
                with archive.open(member) as stream:
                    while stream.read(1024 * 1024):
                        pass
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ElementTree.ParseError, KeyError, RuntimeError, EOFError, OSError, zlib.error) as exc:
        raise StorageValidationError("EPUB ilegible o dañado") from exc


def validate_cover(path: Path) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as img:
                if img.format not in ("JPEG", "PNG", "WEBP"):
                    raise StorageValidationError("La portada debe ser JPG, PNG o WebP")
                fmt = img.format
                img.verify()
            with Image.open(path) as img:
                img.load()
        return {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[fmt]
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise StorageValidationError("Portada ilegible o inválida") from exc


def publish(staged: Path, category: str, suffix: str) -> tuple[str, Path]:
    target_dir = _category_dir(category)
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{suffix}"
    target = target_dir / name
    shutil.move(str(staged), str(target))
    return f"{category}/{name}", target
