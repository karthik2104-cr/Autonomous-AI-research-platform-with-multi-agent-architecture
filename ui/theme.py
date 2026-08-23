"""Shared Streamlit presentation helpers (copy, CSS, progress labels)."""

from __future__ import annotations

import re

import streamlit as st

from core.config import DEFAULT_OLLAMA_EMBED_MODEL, DEFAULT_OLLAMA_MODEL
from core.llm import ollama_embed_model, ollama_model


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        /* Slightly tighter status cards on Home */
        div[data-testid="stMetric"] {
            background: rgba(49, 51, 63, 0.06);
            border-radius: 0.5rem;
            padding: 0.75rem 1rem;
        }
        /* Sidebar branding block */
        .sidebar-brand {
            padding: 0.25rem 0 0.75rem 0;
            margin-bottom: 0.25rem;
            border-bottom: 1px solid rgba(128, 128, 128, 0.25);
        }
        .sidebar-brand-title {
            font-size: 1.05rem;
            font-weight: 600;
            line-height: 1.3;
        }
        .sidebar-brand-sub {
            font-size: 0.8rem;
            opacity: 0.75;
            margin-top: 0.15rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_branding() -> None:
    st.sidebar.markdown(
        """
        <div class="sidebar-brand">
          <div class="sidebar-brand-title">🔬 AI Research Assistant</div>
          <div class="sidebar-brand-sub">Local, citation-backed research</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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


def status_badge(status: str | None) -> str:
    if status == "supported":
        return "✅ Supported"
    if status == "unsupported":
        return "⚠️ Unsupported"
    return "❓ Inconclusive"


def page_intro(title: str, body: str) -> None:
    st.title(title)
    st.markdown(body)
    st.divider()


def ollama_model_lines() -> tuple[str, str]:
    chat = ollama_model() or DEFAULT_OLLAMA_MODEL
    embed = ollama_embed_model() or DEFAULT_OLLAMA_EMBED_MODEL
    return chat, embed
