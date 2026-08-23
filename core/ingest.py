"""Document ingestion: parse files → chunk → embed → Chroma."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from core.vector_store import ingest_text


def _extract_docx_text(source: Path | io.BytesIO, *, label: str) -> str:
    """Extract paragraph and table text from a DOCX file in document order."""
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise RuntimeError(
            "DOCX support requires python-docx. Install with: pip install python-docx"
        ) from exc

    try:
        doc = Document(source)
    except Exception as exc:
        raise ValueError(f"Could not read DOCX file '{label}': {exc}") from exc

    parts: list[str] = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            text = Paragraph(child, doc).text.strip()
            if text:
                parts.append(text)
        elif child.tag == qn("w:tbl"):
            table = Table(child, doc)
            rows: list[str] = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                parts.append("\n".join(rows))

    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError(f"No extractable text in DOCX: {label}")
    return text


def parse_file(path: Path | str) -> tuple[str, str]:
    """Return (text, filename). Supports .txt, .md, .pdf, and .docx."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    filename = path.name
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".log"}:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return text, filename
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF support requires pypdf. Install with: pip install pypdf"
            ) from exc
        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise ValueError(f"Could not read PDF file '{filename}': {exc}") from exc
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if not text:
            raise ValueError(f"No extractable text in PDF: {filename}")
        return text, filename
    if suffix == ".docx":
        return _extract_docx_text(path, label=filename), filename
    raise ValueError(
        f"Unsupported file type: {suffix}. Use .txt, .md, .pdf, or .docx."
    )


def ingest_file(path: Path | str, **kwargs: Any) -> dict[str, Any]:
    text, filename = parse_file(path)
    return ingest_text(text, filename=filename, **kwargs)


def ingest_bytes(data: bytes, filename: str, **kwargs: Any) -> dict[str, Any]:
    """Ingest uploaded bytes from Streamlit (txt/md/pdf/docx by extension)."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            return ingest_file(tmp_path, **kwargs)
        finally:
            tmp_path.unlink(missing_ok=True)

    if suffix == ".docx":
        label = filename or "upload.docx"
        text = _extract_docx_text(io.BytesIO(data), label=label)
        return ingest_text(text, filename=label, **kwargs)

    text = data.decode("utf-8-sig", errors="replace")
    return ingest_text(text, filename=filename or "upload.txt", **kwargs)
