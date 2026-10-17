"""Premium dark design system for the Research Intelligence workspace."""

from __future__ import annotations

import html
import re
from typing import Any

import streamlit as st

from core.config import DEFAULT_OLLAMA_EMBED_MODEL, DEFAULT_OLLAMA_MODEL
from core.llm import ollama_embed_model, ollama_model

# ── Palette ──────────────────────────────────────────────────────────────────
BG = "#0B1020"
SIDEBAR_BG = "#080D19"
CARD = "#111A2B"
SURFACE = "#162238"
BORDER = "#25334A"
ACCENT = "#5B8CFF"
ACCENT_VIOLET = "#8B7CFF"
TEXT = "#F1F5F9"
MUTED = "#94A3B8"
SUCCESS = "#34D399"
WARNING = "#FBBF24"
ERROR = "#F87171"

PIPELINE_STAGES = [
    ("PLANNING", "Planning", "Break the question into sub-questions"),
    ("RESEARCHING", "Research", "Gather web + knowledge-base evidence"),
    ("ANALYZING", "Analysis", "Extract claims and citations"),
    ("VERIFYING", "Verification", "LLM-as-judge per claim"),
    ("GENERATING", "Report", "Build structured citation-backed report"),
]

_STAGE_ORDER = [s[0] for s in PIPELINE_STAGES]


def inject_custom_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}

        .stApp {{
            background: {BG};
            color: {TEXT};
        }}

        /* ── Sidebar ── */
        section[data-testid="stSidebar"] {{
            background: {SIDEBAR_BG} !important;
            border-right: 1px solid {BORDER};
        }}
        section[data-testid="stSidebar"] > div {{
            background: {SIDEBAR_BG};
        }}
        [data-testid="stSidebarNav"] {{
            padding-top: 0.25rem;
        }}
        [data-testid="stSidebarNav"] a {{
            border-radius: 8px !important;
            margin: 2px 6px !important;
            padding: 0.55rem 0.75rem !important;
            color: {MUTED} !important;
            font-weight: 500 !important;
            font-size: 0.9rem !important;
            transition: background 0.15s ease, color 0.15s ease;
        }}
        [data-testid="stSidebarNav"] a:hover {{
            background: {SURFACE} !important;
            color: {TEXT} !important;
        }}
        [data-testid="stSidebarNav"] a[aria-current="page"] {{
            background: rgba(91, 140, 255, 0.14) !important;
            color: {ACCENT} !important;
            border: 1px solid rgba(91, 140, 255, 0.28) !important;
        }}

        /* Hide default Streamlit chrome noise */
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{
            background: transparent;
        }}

        /* ── Main content ── */
        .block-container {{
            padding-top: 1.6rem !important;
            padding-bottom: 3rem !important;
            max-width: 1180px;
        }}

        h1, h2, h3 {{
            color: {TEXT} !important;
            font-weight: 600 !important;
            letter-spacing: -0.02em;
        }}
        h1 {{ font-size: 1.75rem !important; margin-bottom: 0.35rem !important; }}
        h2 {{ font-size: 1.2rem !important; margin-top: 0.5rem !important; }}
        h3 {{ font-size: 1.05rem !important; }}

        p, label, .stMarkdown {{
            color: {TEXT};
        }}
        .stCaption, [data-testid="stCaptionContainer"] {{
            color: {MUTED} !important;
        }}

        /* ── Cards / surfaces ── */
        [data-testid="stMetric"] {{
            background: {CARD};
            border: 1px solid {BORDER};
            border-radius: 10px;
            padding: 0.9rem 1.1rem;
        }}
        [data-testid="stMetricLabel"] {{
            color: {MUTED} !important;
            font-weight: 500 !important;
            font-size: 0.8rem !important;
        }}
        [data-testid="stMetricValue"] {{
            color: {TEXT} !important;
            font-weight: 600 !important;
        }}

        div[data-testid="stExpander"] {{
            background: {CARD};
            border: 1px solid {BORDER};
            border-radius: 10px;
        }}

        /* ── Inputs ── */
        .stTextInput input, .stTextArea textarea, .stNumberInput input,
        [data-baseweb="select"] > div {{
            background: {SURFACE} !important;
            border: 1px solid {BORDER} !important;
            border-radius: 8px !important;
            color: {TEXT} !important;
        }}
        .stTextInput input:focus, .stTextArea textarea:focus {{
            border-color: {ACCENT} !important;
            box-shadow: 0 0 0 1px {ACCENT} !important;
        }}

        /* ── Buttons ── */
        .stButton > button {{
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease;
        }}
        .stButton > button[kind="primary"],
        .stButton > button[data-testid="baseButton-primary"] {{
            background: {ACCENT} !important;
            border: 1px solid {ACCENT} !important;
            color: #fff !important;
        }}
        .stButton > button[kind="primary"]:hover,
        .stButton > button[data-testid="baseButton-primary"]:hover {{
            background: #4A7AEF !important;
            border-color: #4A7AEF !important;
        }}
        .stButton > button[kind="secondary"],
        .stButton > button:not([kind="primary"]) {{
            background: {SURFACE} !important;
            border: 1px solid {BORDER} !important;
            color: {TEXT} !important;
        }}
        .stDownloadButton > button {{
            background: {SURFACE} !important;
            border: 1px solid {BORDER} !important;
            color: {TEXT} !important;
            border-radius: 8px !important;
        }}
        .stDownloadButton > button:hover {{
            border-color: {ACCENT} !important;
            color: {ACCENT} !important;
        }}

        /* ── Alerts ── */
        [data-testid="stAlert"] {{
            border-radius: 10px;
            border: 1px solid {BORDER};
        }}

        /* ── Dataframes / tables ── */
        [data-testid="stDataFrame"] {{
            border: 1px solid {BORDER};
            border-radius: 10px;
            overflow: hidden;
        }}

        /* ── Divider ── */
        hr {{
            border-color: {BORDER} !important;
            margin: 1.25rem 0 !important;
        }}

        /* ── Status / code ── */
        code {{
            font-family: 'JetBrains Mono', ui-monospace, monospace !important;
            font-size: 0.82em !important;
            background: {SURFACE} !important;
            color: {ACCENT} !important;
            padding: 0.1em 0.35em;
            border-radius: 4px;
        }}

        /* ── Custom component classes ── */
        .ri-brand {{
            padding: 0.85rem 0.85rem 1rem 0.85rem;
            margin-bottom: 0.5rem;
            border-bottom: 1px solid {BORDER};
        }}
        .ri-brand-mark {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border-radius: 8px;
            background: rgba(91, 140, 255, 0.15);
            border: 1px solid rgba(91, 140, 255, 0.3);
            color: {ACCENT};
            font-size: 0.95rem;
            margin-bottom: 0.55rem;
        }}
        .ri-brand-title {{
            font-size: 1rem;
            font-weight: 600;
            color: {TEXT};
            letter-spacing: -0.01em;
            line-height: 1.25;
        }}
        .ri-brand-sub {{
            font-size: 0.72rem;
            color: {MUTED};
            margin-top: 0.2rem;
            line-height: 1.35;
        }}
        .ri-sidebar-health {{
            margin: 0.75rem 0.85rem 1rem 0.85rem;
            padding: 0.7rem 0.75rem;
            background: {CARD};
            border: 1px solid {BORDER};
            border-radius: 10px;
            font-size: 0.75rem;
        }}
        .ri-sidebar-health-title {{
            color: {MUTED};
            font-weight: 500;
            margin-bottom: 0.45rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            font-size: 0.65rem;
        }}
        .ri-health-row {{
            display: flex;
            align-items: center;
            gap: 0.4rem;
            margin: 0.28rem 0;
            color: {TEXT};
        }}
        .ri-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            flex-shrink: 0;
        }}
        .ri-dot-ok {{ background: {SUCCESS}; }}
        .ri-dot-err {{ background: {ERROR}; }}

        .ri-page-sub {{
            color: {MUTED};
            font-size: 0.95rem;
            line-height: 1.55;
            margin-bottom: 0.25rem;
            max-width: 52rem;
        }}
        .ri-section-label {{
            color: {MUTED};
            font-size: 0.72rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.65rem;
        }}

        .ri-card {{
            background: {CARD};
            border: 1px solid {BORDER};
            border-radius: 12px;
            padding: 1.1rem 1.2rem;
            margin-bottom: 0.75rem;
        }}
        .ri-card-title {{
            font-size: 0.85rem;
            font-weight: 600;
            color: {TEXT};
            margin-bottom: 0.35rem;
        }}
        .ri-card-body {{
            color: {MUTED};
            font-size: 0.85rem;
            line-height: 1.5;
        }}

        .ri-badge {{
            display: inline-block;
            padding: 0.15rem 0.55rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 500;
            letter-spacing: 0.01em;
            white-space: nowrap;
        }}
        .ri-badge-done, .ri-badge-supported {{
            background: rgba(52, 211, 153, 0.12);
            color: {SUCCESS};
            border: 1px solid rgba(52, 211, 153, 0.28);
        }}
        .ri-badge-failed, .ri-badge-unsupported {{
            background: rgba(248, 113, 113, 0.12);
            color: {ERROR};
            border: 1px solid rgba(248, 113, 113, 0.28);
        }}
        .ri-badge-pending, .ri-badge-inconclusive, .ri-badge-uncertain {{
            background: rgba(251, 191, 36, 0.12);
            color: {WARNING};
            border: 1px solid rgba(251, 191, 36, 0.28);
        }}
        .ri-badge-active {{
            background: rgba(91, 140, 255, 0.14);
            color: {ACCENT};
            border: 1px solid rgba(91, 140, 255, 0.3);
        }}
        .ri-badge-neutral {{
            background: {SURFACE};
            color: {MUTED};
            border: 1px solid {BORDER};
        }}

        .ri-pipeline {{
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin: 0.75rem 0 1rem 0;
        }}
        .ri-stage {{
            flex: 1 1 140px;
            min-width: 120px;
            background: {CARD};
            border: 1px solid {BORDER};
            border-radius: 10px;
            padding: 0.75rem 0.85rem;
        }}
        .ri-stage-active {{
            border-color: {ACCENT};
            background: rgba(91, 140, 255, 0.08);
            box-shadow: inset 0 0 0 1px rgba(91, 140, 255, 0.2);
        }}
        .ri-stage-done {{
            border-color: rgba(52, 211, 153, 0.35);
        }}
        .ri-stage-failed {{
            border-color: rgba(248, 113, 113, 0.4);
        }}
        .ri-stage-name {{
            font-size: 0.82rem;
            font-weight: 600;
            color: {TEXT};
            margin-bottom: 0.2rem;
        }}
        .ri-stage-desc {{
            font-size: 0.72rem;
            color: {MUTED};
            line-height: 1.35;
        }}
        .ri-stage-status {{
            font-size: 0.68rem;
            font-weight: 500;
            margin-top: 0.45rem;
        }}

        .ri-empty {{
            background: {CARD};
            border: 1px dashed {BORDER};
            border-radius: 12px;
            padding: 1.75rem 1.5rem;
            text-align: center;
        }}
        .ri-empty-title {{
            font-weight: 600;
            color: {TEXT};
            margin-bottom: 0.35rem;
        }}
        .ri-empty-body {{
            color: {MUTED};
            font-size: 0.9rem;
            line-height: 1.5;
        }}

        .ri-summary {{
            background: linear-gradient(135deg, rgba(91, 140, 255, 0.08), rgba(139, 124, 255, 0.06));
            border: 1px solid rgba(91, 140, 255, 0.22);
            border-radius: 12px;
            padding: 1.15rem 1.25rem;
            margin: 0.5rem 0 1rem 0;
            color: {TEXT};
            line-height: 1.6;
            font-size: 0.95rem;
        }}

        .ri-source {{
            background: {CARD};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 0.65rem 0.85rem;
            margin-bottom: 0.4rem;
            font-size: 0.85rem;
        }}
        .ri-source a {{
            color: {ACCENT} !important;
            word-break: break-all;
        }}
        .ri-mono {{
            font-family: 'JetBrains Mono', ui-monospace, monospace;
            font-size: 0.8rem;
            color: {MUTED};
        }}

        .ri-chip {{
            display: inline-block;
            background: {SURFACE};
            border: 1px solid {BORDER};
            color: {MUTED};
            border-radius: 999px;
            padding: 0.25rem 0.7rem;
            font-size: 0.78rem;
            margin: 0.2rem 0.25rem 0.2rem 0;
            cursor: default;
        }}
        .ri-chip:hover {{
            border-color: {ACCENT};
            color: {ACCENT};
        }}

        .ri-upload-zone {{
            background: {CARD};
            border: 1px dashed {BORDER};
            border-radius: 12px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.5rem;
        }}

        /* Example question buttons row */
        .ri-examples-hint {{
            color: {MUTED};
            font-size: 0.8rem;
            margin-bottom: 0.4rem;
        }}

        a {{ color: {ACCENT}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_branding() -> None:
    st.sidebar.markdown(
        f"""
        <div class="ri-brand">
          <div class="ri-brand-mark">◉</div>
          <div class="ri-brand-title">Research Intelligence</div>
          <div class="ri-brand-sub">Autonomous AI Research Workspace</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_system_status(
    sqlite_ok: bool,
    chroma_ok: bool,
    ollama_ok: bool,
) -> None:
    def row(label: str, ok: bool) -> str:
        cls = "ri-dot-ok" if ok else "ri-dot-err"
        return (
            f'<div class="ri-health-row">'
            f'<span class="ri-dot {cls}"></span>'
            f'<span>{html.escape(label)}</span></div>'
        )

    st.sidebar.markdown(
        f"""
        <div class="ri-sidebar-health">
          <div class="ri-sidebar-health-title">System status</div>
          {row("SQLite", sqlite_ok)}
          {row("ChromaDB", chroma_ok)}
          {row("Ollama", ollama_ok)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"# {html.escape(title)}")
    if subtitle:
        st.markdown(
            f'<p class="ri-page-sub">{html.escape(subtitle)}</p>',
            unsafe_allow_html=True,
        )
    st.divider()


def section_label(text: str) -> None:
    st.markdown(
        f'<div class="ri-section-label">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="ri-empty">
          <div class="ri-empty-title">{html.escape(title)}</div>
          <div class="ri-empty-body">{html.escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge_html(status: str | None) -> str:
    raw = (status or "uncertain").strip().lower()
    mapping = {
        "supported": ("Supported", "ri-badge-supported"),
        "unsupported": ("Unsupported", "ri-badge-unsupported"),
        "uncertain": ("Inconclusive", "ri-badge-inconclusive"),
        "inconclusive": ("Inconclusive", "ri-badge-inconclusive"),
        "done": ("Done", "ri-badge-done"),
        "failed": ("Failed", "ri-badge-failed"),
        "pending": ("Pending", "ri-badge-pending"),
        "planning": ("Planning", "ri-badge-active"),
        "researching": ("Researching", "ri-badge-active"),
        "analyzing": ("Analyzing", "ri-badge-active"),
        "verifying": ("Verifying", "ri-badge-active"),
        "generating": ("Generating", "ri-badge-active"),
    }
    label, cls = mapping.get(raw, (raw.title() or "Unknown", "ri-badge-neutral"))
    return f'<span class="ri-badge {cls}">{html.escape(label)}</span>'


def status_badge(status: str | None) -> str:
    """Plain-text badge for dataframes (emoji-compatible)."""
    raw = (status or "uncertain").strip().lower()
    if raw == "supported":
        return "● Supported"
    if raw == "unsupported":
        return "● Unsupported"
    if raw in {"uncertain", "inconclusive"}:
        return "● Inconclusive"
    if raw == "done":
        return "● Done"
    if raw == "failed":
        return "● Failed"
    return f"● {raw.title()}"


def render_status_badge(status: str | None) -> None:
    st.markdown(status_badge_html(status), unsafe_allow_html=True)


def metric_row(items: list[tuple[str, str, str | None]]) -> None:
    """items: (label, value, help_or_none)"""
    cols = st.columns(len(items))
    for col, (label, value, help_text) in zip(cols, items):
        with col:
            if help_text:
                st.metric(label, value, help=help_text)
            else:
                st.metric(label, value)


def infer_pipeline_stages(run_status: str | None) -> list[dict[str, str]]:
    """Map a ResearchRun status to five pipeline stage visual states (no fabrication)."""
    status = (run_status or "PENDING").upper()
    stages: list[dict[str, str]] = []

    if status == "FAILED":
        # Mark all as muted; highlight that the run failed overall.
        for key, name, desc in PIPELINE_STAGES:
            stages.append({"key": key, "name": name, "desc": desc, "state": "failed"})
        return stages

    if status == "DONE":
        for key, name, desc in PIPELINE_STAGES:
            stages.append({"key": key, "name": name, "desc": desc, "state": "done"})
        return stages

    if status == "PENDING":
        for key, name, desc in PIPELINE_STAGES:
            stages.append({"key": key, "name": name, "desc": desc, "state": "pending"})
        return stages

    try:
        active_idx = _STAGE_ORDER.index(status)
    except ValueError:
        for key, name, desc in PIPELINE_STAGES:
            stages.append({"key": key, "name": name, "desc": desc, "state": "pending"})
        return stages

    for i, (key, name, desc) in enumerate(PIPELINE_STAGES):
        if i < active_idx:
            state = "done"
        elif i == active_idx:
            state = "active"
        else:
            state = "pending"
        stages.append({"key": key, "name": name, "desc": desc, "state": state})
    return stages


def render_pipeline_stages(run_status: str | None) -> None:
    stages = infer_pipeline_stages(run_status)
    state_label = {
        "done": ("Complete", SUCCESS),
        "active": ("In progress", ACCENT),
        "pending": ("Pending", MUTED),
        "failed": ("Failed", ERROR),
    }
    parts: list[str] = ['<div class="ri-pipeline">']
    for stage in stages:
        state = stage["state"]
        cls = f"ri-stage ri-stage-{state}" if state != "pending" else "ri-stage"
        label, color = state_label[state]
        parts.append(
            f'<div class="{cls}">'
            f'<div class="ri-stage-name">{html.escape(stage["name"])}</div>'
            f'<div class="ri-stage-desc">{html.escape(stage["desc"])}</div>'
            f'<div class="ri-stage-status" style="color:{color}">{html.escape(label)}</div>'
            f"</div>"
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def format_pipeline_progress(message: str) -> str:
    """Map pipeline progress strings to clearer UI labels (presentation only)."""
    msg = message.strip()
    if not msg:
        return msg

    if msg == "Creating research run...":
        return "Setting up a new research run in the local database…"
    if msg == "Planning...":
        return "Planning: breaking your question into focused sub-questions…"
    if msg.startswith("Created ") and "sub-question" in msg:
        return f"Planning complete — {msg.replace('Created ', '')}"
    if msg == "Researching (web + knowledge base)...":
        return "Researching: searching the web and your knowledge base for evidence…"
    if msg.startswith("Researching:"):
        return f"Researching sub-question — {msg.split(':', 1)[1].strip()}"
    if msg == "Analyzing evidence into claims...":
        return "Analyzing: extracting claims, citations, gaps, and contradictions from evidence…"
    if msg.startswith("Created ") and "claim(s)" in msg:
        return f"Analysis complete — {msg}"
    if msg == "Verifying claims (independent LLM-as-judge)...":
        return "Verifying: each claim is checked independently against its cited evidence…"
    if msg.startswith("Verifying claim "):
        m = re.match(r"Verifying claim (\d+)/(\d+)", msg)
        if m:
            return f"Verifying claim {m.group(1)} of {m.group(2)} with a separate LLM check…"
    if msg.startswith("Verified "):
        return f"Verification finished — {msg.replace('Verified ', '')}"
    if msg == "Generating report...":
        return "Generating report: structured sections plus narrative summary…"
    if msg == "Report saved":
        return "Report saved — ready to view and export"
    return msg


def progress_to_stage(message: str) -> str | None:
    """Heuristic: map a live progress message to a pipeline stage key."""
    msg = message.lower()
    if "planning" in msg or "sub-question" in msg and "created" in msg:
        return "PLANNING"
    if "research" in msg:
        return "RESEARCHING"
    if "analyz" in msg or "claim(s)" in msg and "created" in msg:
        return "ANALYZING"
    if "verif" in msg:
        return "VERIFYING"
    if "generat" in msg or "report" in msg:
        return "GENERATING"
    return None


def ollama_model_lines() -> tuple[str, str]:
    chat = ollama_model() or DEFAULT_OLLAMA_MODEL
    embed = ollama_embed_model() or DEFAULT_OLLAMA_EMBED_MODEL
    return chat, embed


def format_timestamp(iso: str | None) -> str:
    if not iso:
        return "—"
    return iso.replace("T", " ")[:19]


def example_questions() -> list[str]:
    return [
        "Compare SQLite and PostgreSQL for a local-first desktop app",
        "What are the main benefits of using SQLite for local desktop applications?",
        "How does SQLite WAL mode affect concurrent reads and writes?",
        "Summarize what Nimbus Cache is and its rebuild latency from the knowledge base",
    ]


# Back-compat alias used by older pages
def page_intro(title: str, body: str) -> None:
    page_header(title, body)
