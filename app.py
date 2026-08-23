import streamlit as st

from core.health import chroma_status, ollama_status, sqlite_status
from core.vector_store import document_count
from ui.theme import inject_custom_css, ollama_model_lines, sidebar_branding

st.set_page_config(
    page_title="AI Research Assistant",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
sidebar_branding()


def render_home() -> None:
    st.title("AI Research Assistant")
    st.markdown(
        """
This is a **local, fully offline AI research assistant**. Ask a research question and
the system will:

1. **Plan** — split your question into focused sub-questions
2. **Research** — search the web (DuckDuckGo) and retrieve from documents you uploaded
3. **Analyze** — extract claims and link each one to evidence
4. **Verify** — run a separate LLM check on every claim against its cited sources
5. **Report** — produce a structured, citation-backed summary you can export as Markdown or PDF

Everything runs on your machine through **Ollama** — no cloud API keys required.
        """
    )

    st.header("What can I use this for?")
    st.markdown(
        """
- **Technical comparisons with citations** — e.g. *Compare SQLite vs PostgreSQL for a
  local-first desktop app* and see which claims are backed by retrieved evidence.
- **Questions over your own material** — upload PDFs or notes to the Knowledge Base, then
  ask questions answered from **your documents plus optional web search**.
- **Claim-level fact checking** — read the verification table to see which statements
  the judge marked supported, unsupported, or inconclusive relative to cited snippets.
- **Repeatable quality checks** — run the Evaluation page against a small test question
  set to spot weak retrieval or inconsistent verification.
        """
    )

    st.divider()
    st.header("System Status")

    sqlite_ok, sqlite_detail = sqlite_status()
    chroma_ok, chroma_detail = chroma_status()
    ollama_ok, ollama_detail = ollama_status()
    chat_model, embed_model = ollama_model_lines()
    doc_count = document_count() if chroma_ok else 0

    c1, c2, c3 = st.columns(3)

    with c1:
        st.subheader("SQLite")
        if sqlite_ok:
            st.success("Connected")
            st.caption("Stores research runs, plan steps, evidence, claims, and reports at `data/research.db`.")
        else:
            st.error("Unavailable")
            st.caption(sqlite_detail)

    with c2:
        st.subheader("ChromaDB")
        if chroma_ok:
            st.success("Connected")
            st.metric("Indexed chunks", doc_count)
            st.caption(f"{doc_count} text chunk(s) indexed for knowledge-base retrieval during research.")
        else:
            st.error("Unavailable")
            st.caption(chroma_detail)

    with c3:
        st.subheader("Ollama")
        if ollama_ok:
            st.success("Ready")
            st.markdown(f"**Chat model** — `{chat_model}`  \nPlans, analyzes, verifies, and writes reports.")
            st.markdown(f"**Embedding model** — `{embed_model}`  \nEmbeds KB chunks for semantic retrieval.")
        else:
            st.error("Not ready")
            st.caption(ollama_detail)

    st.divider()
    st.header("Quick Start")
    st.markdown(
        """
1. **Knowledge Base** *(optional)* — upload `.txt`, `.md`, `.pdf`, or `.docx` files you want included in RAG searches.
2. **New Research** — enter a question and start the pipeline (expect **10–20+ minutes** on CPU).
3. **Run History** — open a completed run, read the report, and download **Markdown** or **PDF**.
        """
    )
    st.caption("Use **Evaluation** to batch-test retrieval quality; **Settings** to change Ollama model names.")


nav = st.navigation(
    [
        st.Page(render_home, title="Home", icon="🏠", default=True),
        st.Page("pages/1_New_Research.py", title="New Research", icon="🔍"),
        st.Page("pages/2_Knowledge_Base.py", title="Knowledge Base", icon="📚"),
        st.Page("pages/3_Run_History.py", title="Run History", icon="🕘"),
        st.Page("pages/4_Settings.py", title="Settings", icon="⚙️"),
        st.Page("pages/5_Evaluation.py", title="Evaluation", icon="📊"),
    ]
)
nav.run()
