"""Validation helpers for document uploads."""

import math
import os
import re
import unicodedata

from fastapi import HTTPException, UploadFile, status

PDF_MAGIC = b"%PDF-"
DEFAULT_MAX_UPLOAD_MB = 25
MAX_FILENAME_LENGTH = 200
MULTIPART_OVERHEAD_BYTES = 64 * 1024


def max_upload_bytes() -> int:
    raw = os.getenv("MAX_UPLOAD_MB", "").strip()
    megabytes = float(raw) if raw else DEFAULT_MAX_UPLOAD_MB
    if not math.isfinite(megabytes) or megabytes <= 0:
        raise ValueError("MAX_UPLOAD_MB must be a positive finite number")
    return int(megabytes * 1024 * 1024)


def _too_large() -> HTTPException:
    limit_mb = max_upload_bytes() / (1024 * 1024)
    return HTTPException(
        status_code=413,
        detail=f"File is too large. The limit is {limit_mb:g} MB.",
    )


def reject_oversized_request(content_length: str | None) -> None:
    """Reject a request whose declared size exceeds the file limit plus framing."""
    if not content_length:
        return
    try:
        declared = int(content_length)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Content-Length header.")
    if declared < 0:
        raise HTTPException(status_code=400, detail="Invalid Content-Length header.")
    if declared > max_upload_bytes() + MULTIPART_OVERHEAD_BYTES:
        raise _too_large()


def sanitize_filename(name: str | None) -> str:
    """Strip paths and control characters before using a client filename."""
    candidate = (name or "").replace("\\", "/").split("/")[-1]
    candidate = unicodedata.normalize("NFKC", candidate)
    candidate = "".join(ch for ch in candidate if ch.isprintable())
    candidate = re.sub(r"\s+", " ", candidate).strip(" .")
    candidate = re.sub(r"[^\w.\- ()]", "_", candidate)
    if len(candidate) > MAX_FILENAME_LENGTH:
        stem, ext = os.path.splitext(candidate)
        candidate = stem[: MAX_FILENAME_LENGTH - len(ext)] + ext
    return candidate or "document.pdf"


def validate_pdf_upload(file: UploadFile) -> int:
    """Check file size and PDF signature, returning the file size in bytes."""
    stream = file.file
    stream.seek(0, 2)
    size_bytes = stream.tell()
    stream.seek(0)

    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if size_bytes > max_upload_bytes():
        raise _too_large()

    header = stream.read(len(PDF_MAGIC))
    stream.seek(0)
    if header != PDF_MAGIC:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are accepted.",
        )
    return size_bytes
