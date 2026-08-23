"""Generate a sample PDF from a completed research run (no LLM)."""
from __future__ import annotations

import sys
from uuid import UUID

from pypdf import PdfReader

import tests  # noqa: F401 — repo root on sys.path
from tests import ROOT

from pipeline import load_run
from utils.pdf_export import generate_pdf

RUN_ID = "9906d319-fc39-4f1f-8762-d54c886eaa8b"
OUT_DIR = ROOT / "data" / "reports"
OUT_PATH = OUT_DIR / f"research_report_{RUN_ID[:8]}.pdf"


def main() -> int:
    run = load_run(UUID(RUN_ID))
    if run is None:
        print(f"Run {RUN_ID} not found.", file=sys.stderr)
        return 1
    if run.report is None or not isinstance(run.report.content_json, dict):
        print(f"Run {RUN_ID} has no report content_json.", file=sys.stderr)
        return 1

    pdf_bytes = generate_pdf(run.report)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_bytes(pdf_bytes)

    reader = PdfReader(str(OUT_PATH))
    page_count = len(reader.pages)
    first_page_text = reader.pages[0].extract_text() or ""

    print(f"Wrote PDF: {OUT_PATH.resolve()}")
    print(f"Size: {len(pdf_bytes):,} bytes, pages: {page_count}")
    print("\n--- First page text (extracted) ---")
    print(first_page_text[:2000])
    if page_count > 1:
        print(f"\n(... {page_count - 1} more page(s) ...)")

    checks = [
        ("Research Report" in first_page_text, "title present"),
        ("Executive Summary" in first_page_text, "executive summary section"),
        ("Claims" in first_page_text or page_count > 1, "claims section"),
        (
            "[OK]" in first_page_text or "[WARN]" in first_page_text or "[?]" in first_page_text,
            "ASCII status labels",
        ),
    ]
    print("\n--- Validation ---")
    ok = True
    for passed, label in checks:
        status = "OK" if passed else "FAIL"
        print(f"  [{status}] {label}")
        ok = ok and passed

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
