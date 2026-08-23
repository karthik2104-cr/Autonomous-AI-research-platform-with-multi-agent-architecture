"""
Non-destructive post-cleanup smoke test.

Does NOT wipe Chroma or SQLite — safe to run with interview demo data intact.
Run from repo root: python -m tests.smoke_test
"""
from __future__ import annotations

import importlib
import sys
from uuid import UUID

import tests  # noqa: F401
from tests import ROOT


def _check(name: str, ok: bool, detail: str = "") -> bool:
    status = "OK" if ok else "FAIL"
    line = f"  [{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    print("=== SMOKE TEST (non-destructive) ===\n")
    all_ok = True

    print("Health checks:")
    from core.health import chroma_status, ollama_status, sqlite_status

    for label, fn in [
        ("SQLite", sqlite_status),
        ("ChromaDB", chroma_status),
        ("Ollama", ollama_status),
    ]:
        ok, detail = fn()
        all_ok &= _check(label, ok, detail)

    print("\nStreamlit app imports:")
    try:
        importlib.import_module("app")
        for page in (
            "pages.1_New_Research",
            "pages.2_Knowledge_Base",
            "pages.3_Run_History",
            "pages.4_Settings",
            "pages.5_Evaluation",
        ):
            importlib.import_module(page)
        all_ok &= _check("app + pages", True)
    except Exception as exc:
        all_ok &= _check("app + pages", False, str(exc))

    print("\nDemo run + exports (9906d319...):")
    from agents.report_generator import report_to_markdown
    from pipeline import load_run, run_to_dict
    from utils.pdf_export import generate_pdf

    run = load_run(UUID("9906d319-fc39-4f1f-8762-d54c886eaa8b"))
    if run is None:
        all_ok &= _check("load demo run", False, "run not found")
    else:
        payload = run_to_dict(run)
        all_ok &= _check("load demo run", True, payload.get("status", ""))
        report = payload.get("report") or {}
        md = report_to_markdown(report) if report else ""
        all_ok &= _check("markdown export", bool(md) and md.startswith("# Research Report"))
        if run.report:
            pdf = generate_pdf(run.report)
            all_ok &= _check(
                "pdf export",
                isinstance(pdf, (bytes, bytearray)) and pdf[:4] == b"%PDF",
                f"{len(pdf)} bytes",
            )

    print("\nKnowledge base query (no reset):")
    from core.vector_store import document_count, query_documents

    count = document_count()
    all_ok &= _check("kb document count", count >= 0, str(count))
    if count > 0:
        hits = query_documents("Nimbus Cache", n_results=2)
        all_ok &= _check("kb retrieval", len(hits) > 0, f"{len(hits)} hit(s)")
    else:
        print("  [SKIP] kb retrieval — empty collection (run python -m tests.test_kb to populate)")

    print("\nData directories:")
    for sub in ("chroma", "documents", "reports"):
        path = ROOT / "data" / sub
        all_ok &= _check(f"data/{sub}/ exists", path.is_dir())

    print()
    if all_ok:
        print("SMOKE_TEST_OK")
        return 0
    print("SMOKE_TEST_FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
