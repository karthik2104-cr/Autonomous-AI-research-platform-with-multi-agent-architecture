import streamlit as st

from core.ingest import ingest_bytes, ingest_text
from core.vector_store import document_count, list_sources, query_documents
from ui.theme import empty_state, page_header, section_label

page_header(
    "Knowledge Base",
    "Upload documents for local RAG. Files are chunked, embedded with Ollama nomic-embed-text, "
    "and stored in ChromaDB — used only on your machine during research.",
)

section_label("Index summary")
chunk_count = document_count()
m1, m2 = st.columns(2)
m1.metric("Chunks in index", chunk_count)
sources = list_sources()
m2.metric("Source files", len(sources))
st.caption(
    f"{chunk_count} chunk(s) available for semantic retrieval. "
    "More chunks = finer-grained search; ingest time grows with file size."
)

st.divider()
section_label("Upload a file")
st.markdown('<div class="ri-upload-zone">', unsafe_allow_html=True)
st.caption("Supported formats: **.txt**, **.md**, **.pdf**, **.docx**. Text is extracted, chunked, and embedded locally.")
uploaded = st.file_uploader(
    "Choose a file",
    type=["txt", "md", "pdf", "docx"],
    label_visibility="collapsed",
)
if st.button("Ingest uploaded file", type="primary", disabled=uploaded is None):
    if uploaded is None:
        st.warning("Choose a file first.")
    else:
        try:
            with st.spinner("Extracting, chunking, and embedding…"):
                result = ingest_bytes(uploaded.getvalue(), uploaded.name)
            st.success(
                f"Ingested **{result['filename']}** → {result['chunks']} chunk(s) "
                f"(document id `{result['doc_id'][:8]}…`)"
            )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
st.markdown("</div>", unsafe_allow_html=True)

st.divider()
section_label("Paste text")
st.caption("Quick notes without a file — useful for meeting notes or copied articles.")
source = st.text_input(
    "Label / filename",
    value="notes.txt",
    help="Shown in retrieval results and source lists.",
)
text = st.text_area(
    "Document text",
    height=160,
    placeholder="Paste notes, specs, or article text here.",
)
if st.button("Add pasted text to index"):
    if not text.strip():
        st.warning("Paste some text before adding.")
    else:
        try:
            with st.spinner("Chunking and embedding…"):
                result = ingest_text(text.strip(), filename=source.strip() or "notes.txt")
            st.success(f"Indexed **{result['filename']}** → {result['chunks']} chunk(s)")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

st.divider()
section_label("Indexed documents")
if sources:
    rows = [{"Filename": s["filename"], "Chunks": s["chunks"]} for s in sources]
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    empty_state(
        "No documents indexed yet",
        "Upload a PDF, DOCX, Markdown, or text file — or paste notes above — to populate the knowledge base.",
    )

st.divider()
section_label("Test retrieval")
st.caption("Preview what the knowledge base returns — same retrieval path used during research.")
query = st.text_input("Test query", placeholder="What is Nimbus Cache?")
n_results = st.slider("Number of chunks to return", min_value=1, max_value=10, value=3)
if st.button("Search knowledge base", type="primary"):
    if not query.strip():
        st.warning("Enter a test query first.")
    else:
        try:
            with st.spinner("Embedding query and searching…"):
                hits = query_documents(query.strip(), n_results=n_results)
        except Exception as exc:
            st.error(str(exc))
            hits = []
        if not hits:
            st.info(
                "No matching chunks — the index may be empty or the query may not match your documents."
            )
        else:
            for i, hit in enumerate(hits, start=1):
                dist = hit.get("distance")
                dist_label = f"{dist:.3f}" if isinstance(dist, (int, float)) else "n/a"
                with st.expander(
                    f"#{i} · {hit.get('filename') or hit.get('source') or '(no source)'} · distance {dist_label}",
                    expanded=i == 1,
                ):
                    st.caption(
                        f"chunk `{hit.get('chunk_id')}` · index {hit.get('chunk_index')} · "
                        f"doc `{str(hit.get('doc_id') or '')[:8]}`"
                    )
                    st.write(hit.get("text") or "")
