"""End-to-end Knowledge Base: ingest → embed → query."""
from __future__ import annotations

import tests  # noqa: F401 — repo root on sys.path
from tests import ROOT

from core.ingest import ingest_file
from core.vector_store import document_count, list_sources, query_documents, reset_collection

SAMPLE = ROOT / "testdata" / "aurora_notes.txt"


def main() -> None:
    reset_collection()
    print("=== INGEST ===")
    result = ingest_file(SAMPLE)
    print(result)
    print("chunk_count", document_count())
    print("sources", list_sources())

    print("\n=== QUERY: What is Nimbus Cache? ===")
    hits = query_documents("What is Nimbus Cache and how fast can it rebuild indexes?", n_results=3)
    for i, hit in enumerate(hits, start=1):
        print(f"\n--- hit {i} ---")
        print("filename:", hit.get("filename"))
        print("chunk_id:", hit.get("chunk_id"))
        print("chunk_index:", hit.get("chunk_index"))
        print("distance:", hit.get("distance"))
        print("text:", (hit.get("text") or "")[:400])

    assert hits, "Expected at least one retrieved chunk"
    joined = " ".join(h.get("text") or "" for h in hits).lower()
    assert "nimbus" in joined, f"Expected 'nimbus' in retrieved text, got: {joined[:200]}"
    assert any(h.get("filename") == "aurora_notes.txt" for h in hits)
    print("\nKB_E2E_OK")


if __name__ == "__main__":
    main()
