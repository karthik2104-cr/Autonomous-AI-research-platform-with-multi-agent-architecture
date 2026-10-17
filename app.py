import html

import streamlit as st

from core.health import chroma_status, ollama_status, sqlite_status
from core.vector_store import document_count
from pipeline import list_runs
from ui.theme import (
    empty_state,
    format_timestamp,
    inject_custom_css,
    metric_row,
    page_header,
    section_label,
    sidebar_branding,
    sidebar_system_status,
    status_badge_html,
)

st.set_page_config(
    page_title="Research Intelligence",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()

from pathlib import Path

_logo = Path(__file__).resolve().parent / "assets" / "logo.svg"
if _logo.exists():
    st.logo(str(_logo), size="large")

sidebar_branding()

sqlite_ok, sqlite_detail = sqlite_status()
chroma_ok, chroma_detail = chroma_status()
ollama_ok, ollama_detail = ollama_status()
sidebar_system_status(sqlite_ok, chroma_ok, ollama_ok)


def render_home() -> None:
    page_header(
        "Research Intelligence",
        "A local multi-agent workspace that plans, researches, verifies, and reports — "
        "with citation-backed claims and no cloud API keys.",
    )

    header_l, header_r = st.columns([3, 1])
    with header_l:
        st.markdown(
            "Run multi-step research against the web and your uploaded documents. "
            "Each claim is checked by an independent LLM judge before it appears in the report."
        )
    with header_r:
        st.page_link("pages/1_New_Research.py", label="New Research", icon="🔍")

    # Metrics from real data
    recent_items, total_runs = list_runs(page=1, page_size=8)
    completed = sum(
        1
        for item in recent_items
        if (item.status.value if hasattr(item.status, "value") else str(item.status)) == "DONE"
    )
    # completed count above is only among recent page — get accurate completed if total is small
    # For accurate completed across all runs when we only have page 1, use total when all fit.
    if total_runs <= len(recent_items):
        completed_count = completed
    else:
        # Avoid inventing: show completed among loaded recent runs with a clear label,
        # or count DONE from a wider fetch that still uses existing API.
        more_items, _ = list_runs(page=1, page_size=min(100, max(total_runs, 1)))
        completed_count = sum(
            1
            for item in more_items
            if (item.status.value if hasattr(item.status, "value") else str(item.status)) == "DONE"
        )

    doc_count = document_count() if chroma_ok else None
    health_parts = []
    if sqlite_ok:
        health_parts.append("SQLite")
    if chroma_ok:
        health_parts.append("Chroma")
    if ollama_ok:
        health_parts.append("Ollama")
    health_label = f"{len(health_parts)}/3 ready" if health_parts else "Unavailable"

    section_label("Workspace metrics")
    metric_items: list[tuple[str, str, str | None]] = [
        ("Total research runs", str(total_runs), "Runs stored in local SQLite"),
        (
            "Completed runs",
            str(completed_count),
            "Status = DONE (counted from up to 100 most recent runs)",
        ),
        (
            "Indexed chunks",
            str(doc_count) if doc_count is not None else "—",
            "Knowledge-base chunks in ChromaDB" if chroma_ok else "ChromaDB unavailable",
        ),
        ("System health", health_label, "SQLite · ChromaDB · Ollama"),
    ]
    metric_row(metric_items)

    st.divider()
    section_label("System health")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            f'<div class="ri-card"><div class="ri-card-title">SQLite</div>'
            f'<div class="ri-card-body">'
            f'{status_badge_html("done" if sqlite_ok else "failed")} '
            f'{html.escape(sqlite_detail if not sqlite_ok else "Connected · data/research.db")}'
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        chroma_body = (
            f'{status_badge_html("done" if chroma_ok else "failed")} '
            + (
                f"{doc_count} chunk(s) indexed for retrieval"
                if chroma_ok
                else html.escape(chroma_detail)
            )
        )
        st.markdown(
            f'<div class="ri-card"><div class="ri-card-title">ChromaDB</div>'
            f'<div class="ri-card-body">{chroma_body}</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="ri-card"><div class="ri-card-title">Ollama</div>'
            f'<div class="ri-card-body">'
            f'{status_badge_html("done" if ollama_ok else "failed")} '
            f"{html.escape(ollama_detail)}"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    st.divider()
    section_label("Recent activity")
    if not recent_items:
        empty_state(
            "No research runs yet",
            "Start from New Research to plan, search, verify, and generate your first citation-backed report.",
        )
        st.page_link("pages/1_New_Research.py", label="Go to New Research", icon="🔍")
    else:
        header = st.columns((1.2, 5, 1.4, 2.2))
        header[0].markdown("**ID**")
        header[1].markdown("**Question**")
        header[2].markdown("**Status**")
        header[3].markdown("**Created**")
        for item in recent_items[:6]:
            cols = st.columns((1.2, 5, 1.4, 2.2))
            run_id = str(item.id)
            status = item.status.value if hasattr(item.status, "value") else str(item.status)
            created = format_timestamp(item.created_at.isoformat() if item.created_at else None)
            cols[0].markdown(f'`{run_id[:8]}`')
            q = item.user_question or ""
            cols[1].write(q if len(q) <= 120 else q[:117] + "…")
            cols[2].markdown(status_badge_html(status), unsafe_allow_html=True)
            cols[3].caption(created)

        st.caption("Open Run History for full detail, reports, and exports.")
        st.page_link("pages/3_Run_History.py", label="Open Run History", icon="🕘")


nav = st.navigation(
    [
        st.Page(render_home, title="Overview", icon="🏠", default=True),
        st.Page("pages/1_New_Research.py", title="New Research", icon="🔍"),
        st.Page("pages/2_Knowledge_Base.py", title="Knowledge Base", icon="📚"),
        st.Page("pages/3_Run_History.py", title="Run History", icon="🕘"),
        st.Page("pages/5_Evaluation.py", title="Evaluation", icon="📊"),
        st.Page("pages/4_Settings.py", title="Settings", icon="⚙️"),
    ]
)
nav.run()
