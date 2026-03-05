from __future__ import annotations

from pathlib import Path

MAX_FILE_MB = 10


def _safe_decode(data: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return ""


def parse_resume_bytes(filename: str, data: bytes) -> tuple[str, str]:
    """Return (extracted_text, parser_note). Best effort for pdf/docx/txt."""
    ext = Path(filename).suffix.lower()
    if ext == ".txt":
        return _safe_decode(data), "txt"

    if ext == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
            import io

            reader = PdfReader(io.BytesIO(data))
            text = "\n".join([(p.extract_text() or "") for p in reader.pages]).strip()
            return text, "pdf:pypdf"
        except Exception:
            return "", "pdf:parser_unavailable_or_failed"

    if ext == ".docx":
        try:
            import io
            from docx import Document  # type: ignore

            doc = Document(io.BytesIO(data))
            text = "\n".join([p.text for p in doc.paragraphs]).strip()
            return text, "docx:python-docx"
        except Exception:
            return "", "docx:parser_unavailable_or_failed"

    return "", "unsupported_file_type"
