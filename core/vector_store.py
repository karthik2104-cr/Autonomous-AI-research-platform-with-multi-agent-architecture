from __future__ import annotations

from typing import Any
from uuid import uuid4

import chromadb
from chromadb.config import Settings as ChromaSettings

from core.config import DATA_DIR
from core.llm import embed_texts

COLLECTION_NAME = "knowledge_base"
_CHROMA_PATH = DATA_DIR / "chroma"

# Chunking defaults for local RAG.
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120

_client: Any = None


def get_chroma_client() -> Any:
    global _client
    if _client is None:
        _CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(_CHROMA_PATH),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_collection() -> Any:
    # Embeddings are supplied explicitly (Ollama nomic-embed-text). Do not let
    # Chroma invent a default embedding function — that would mismatch dimensions.
    return get_chroma_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection() -> None:
    """Drop and recreate the knowledge_base collection (useful after embed model change)."""
    client = get_chroma_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    get_collection()


def document_count() -> int:
    return int(get_collection().count())


def list_sources() -> list[dict[str, Any]]:
    """Return unique source filenames with chunk counts."""
    collection = get_collection()
    if collection.count() == 0:
        return []
    raw = collection.get(include=["metadatas"])
    metas = raw.get("metadatas") or []
    counts: dict[str, int] = {}
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        name = str(meta.get("filename") or meta.get("source") or "unknown")
        counts[name] = counts.get(name, 0) + 1
    return [{"filename": name, "chunks": n} for name, n in sorted(counts.items())]


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    cleaned = " ".join((text or "").lstrip("\ufeff").split())
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - chunk_overlap)
    return chunks


def add_document(text: str, source: str = "manual") -> str:
    """Backward-compatible helper: ingest one blob as chunked RAG docs. Returns doc_id prefix."""
    result = ingest_text(text, filename=source or "manual")
    return result["doc_id"]


def ingest_text(
    text: str,
    *,
    filename: str = "manual",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> dict[str, Any]:
    """Parse-ready text → chunk → embed (Ollama) → Chroma. Returns summary dict."""
    chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        raise ValueError("No text to ingest after cleaning.")

    doc_id = str(uuid4())
    ids = [f"{doc_id}:{i}" for i in range(len(chunks))]
    embeddings = embed_texts(chunks)
    metadatas = [
        {
            "filename": filename,
            "source": filename,
            "doc_id": doc_id,
            "chunk_id": i,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]
    get_collection().add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    return {"doc_id": doc_id, "filename": filename, "chunks": len(chunks), "ids": ids}


def query_documents(query: str, n_results: int = 3) -> list[dict[str, Any]]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    n_results = max(1, min(n_results, collection.count()))
    query_embedding = embed_texts([query])[0]
    raw = collection.query(query_embeddings=[query_embedding], n_results=n_results)
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    ids = (raw.get("ids") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]
    results: list[dict[str, Any]] = []
    for text, meta, chunk_id, distance in zip(documents, metadatas, ids, distances):
        meta = meta if isinstance(meta, dict) else {}
        results.append(
            {
                "text": str(text or ""),
                "source": str(meta.get("filename") or meta.get("source") or ""),
                "filename": str(meta.get("filename") or meta.get("source") or ""),
                "chunk_id": str(chunk_id),
                "chunk_index": meta.get("chunk_id", meta.get("chunk_index")),
                "doc_id": str(meta.get("doc_id") or ""),
                "distance": distance,
            }
        )
    return results
