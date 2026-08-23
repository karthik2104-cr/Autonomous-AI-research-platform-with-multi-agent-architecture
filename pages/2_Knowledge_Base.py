import streamlit as st

from core.ingest import ingest_bytes, ingest_text
from core.vector_store import document_count, list_sources, query_documents
from ui.theme import page_intro

page_intro(
    "Knowledge Base",
    "Upload documents that the research agent can retrieve during **Research**. Files are "
    "chunked, embedded with Ollama `nomic-embed-text`, and stored in local ChromaDB. "
    "They are **only used on your machine** for RAG searches — nothing is sent to a cloud service.",
)

st.header("Indexed documents")
chunk_count = document_count()
st.metric("Chunks in index", chunk_count)
st.caption(
    f"{chunk_count} chunk(s) available for semantic retrieval. "
    "More chunks = finer-grained search, but ingest time increases with file size."
)

sources = list_sources()
if sources:
    for item in sources:
        st.markdown(f"- **{item['filename']}** — {item['chunks']} chunk(s)")
else:
    st.info("No documents indexed yet. Upload a file or paste text below to get started.")

st.divider()
st.header("Upload a file")
st.caption("Supported formats: **`.txt`**, **`.md`**, **`.pdf`**, **`.docx`**. Text is extracted, chunked, and embedded locally.")
uploaded = st.file_uploader("Choose a file", type=["txt", "md", "pdf", "docx"], label_visibility="collapsed")
if st.button("Ingest uploaded file", type="primary", disabled=uploaded is None):
    if uploaded is None:
        st.warning("Choose a file first.")
    else:
        try:
            result = ingest_bytes(uploaded.getvalue(), uploaded.name)
            st.success(
                f"Ingested **{result['filename']}** → {result['chunks']} chunk(s) "
                f"(document id `{result['doc_id'][:8]}…`)"
            )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

st.divider()
st.header("Paste text")
st.caption("Use this for quick notes without a file — useful for meeting notes or copied articles.")
source = st.text_input("Label / filename", value="notes.txt", help="Shown in retrieval results and source lists.")
text = st.text_area("Document text", height=180, placeholder="Paste notes, specs, or article text here.")
if st.button("Add pasted text to index"):
    if not text.strip():
        st.warning("Paste some text before adding.")
    else:
        try:
            result = ingest_text(text.strip(), filename=source.strip() or "notes.txt")
            st.success(f"Indexed **{result['filename']}** → {result['chunks']} chunk(s)")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

st.divider()
st.header("Test retrieval")
st.caption("Preview what the knowledge base returns for a query — same retrieval used during research.")
query = st.text_input("Test query", placeholder="What is Nimbus Cache?")
n_results = st.slider("Number of chunks to return", min_value=1, max_value=10, value=3)
if st.button("Search knowledge base"):
    if not query.strip():
        st.warning("Enter a test query first.")
    else:
        try:
            hits = query_documents(query.strip(), n_results=n_results)
        except Exception as exc:
            st.error(str(exc))
            hits = []
        if not hits:
            st.info("No matching chunks — the index may be empty or the query may not match your documents.")
        for i, hit in enumerate(hits, start=1):
            dist = hit.get("distance")
            dist_label = f"{dist:.3f}" if isinstance(dist, (int, float)) else "n/a"
            st.markdown(
                f"**{i}. {hit.get('filename') or hit.get('source') or '(no source)'}** "
                f"· chunk `{hit.get('chunk_id')}` · distance {dist_label}"
            )
            st.write(hit.get("text") or "")
