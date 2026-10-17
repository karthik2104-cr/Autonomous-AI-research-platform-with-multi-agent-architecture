import streamlit as st

from core.models import ResearchRunStatus
from pipeline import run_research, run_to_dict
from ui import render_plan_steps, render_report
from ui.theme import (
    example_questions,
    format_pipeline_progress,
    page_header,
    render_pipeline_stages,
    section_label,
    status_badge_html,
)

page_header(
    "New Research",
    "Compose a research question, run the five-stage local pipeline, and review a "
    "citation-backed report. Fresh runs typically take 10–20+ minutes on CPU with qwen3:8b.",
)

if "last_run" not in st.session_state:
    st.session_state.last_run = None
if "research_question_input" not in st.session_state:
    st.session_state.research_question_input = ""
if "pipeline_log" not in st.session_state:
    st.session_state.pipeline_log = []

section_label("Research composer")

examples = example_questions()
st.markdown(
    '<div class="ri-examples-hint">Example questions — click to fill the composer</div>',
    unsafe_allow_html=True,
)
ex_cols = st.columns(2)
for i, example in enumerate(examples):
    with ex_cols[i % 2]:
        if st.button(example, key=f"ex-{i}", use_container_width=True):
            st.session_state.research_question_input = example
            st.rerun()

question = st.text_area(
    "Research question",
    height=150,
    placeholder="e.g. Compare SQLite and PostgreSQL for a local-first desktop app with offline sync",
    help="Be specific — the planner will break this into sub-questions to research separately.",
    key="research_question_input",
)

st.caption(
    "Workflow: **Planning → Research (web + RAG) → Analysis → Verification → Report**. "
    "Evidence and claims are stored locally in SQLite."
)

start = st.button("Start Research", type="primary", use_container_width=False)

if start:
    if not question.strip():
        st.warning("Enter a research question before starting.")
    else:
        st.session_state.pipeline_log = []
        section_label("Execution")
        # Show pending pipeline before/during run; updates after completion from real status
        render_pipeline_stages("PLANNING")

        with st.status("Research pipeline running…", expanded=True) as status:

            def _progress(msg: str) -> None:
                label = format_pipeline_progress(msg)
                st.session_state.pipeline_log.append(label)
                st.write(label)

            run = run_research(question.strip(), on_progress=_progress)
            payload = run_to_dict(run)
            st.session_state.last_run = payload
            if payload.get("status") == ResearchRunStatus.DONE.value:
                status.update(label="Research complete — report ready", state="complete")
            else:
                status.update(label="Research failed — see error below", state="error")

run = st.session_state.last_run
if run:
    st.divider()
    section_label("Pipeline stages")
    render_pipeline_stages(run.get("status"))

    m1, m2, m3 = st.columns([1.2, 4, 1.5])
    with m1:
        st.markdown("**Status**")
        st.markdown(status_badge_html(run.get("status")), unsafe_allow_html=True)
    with m2:
        st.markdown(f"**Question**  \n{run.get('user_question')}")
    with m3:
        st.caption(f"Run ID")
        st.code(str(run.get("id") or "")[:8], language="text")
        st.caption(f"Updated {run.get('updated_at') or '—'}")

    # Live-ish stats from stored run data (not fabricated)
    steps = run.get("plan_steps") or []
    evidence_n = sum(len(s.get("evidence") or []) for s in steps)
    claims = run.get("claims") or []
    if evidence_n or claims:
        c1, c2, c3 = st.columns(3)
        c1.metric("Sub-questions", str(len(steps)))
        c2.metric("Evidence items", str(evidence_n))
        c3.metric("Claims", str(len(claims)))

    if run.get("error_message"):
        st.error(run["error_message"])

    with st.expander("Technical execution log", expanded=False):
        log = st.session_state.get("pipeline_log") or []
        if log:
            for line in log:
                st.markdown(f'<div class="ri-mono">› {line}</div>', unsafe_allow_html=True)
        else:
            st.caption(
                "No live log for this session. Progress messages appear here when you start a new run."
            )

    if run.get("report"):
        st.divider()
        render_report(run)

    st.divider()
    st.markdown("### Plan & evidence")
    st.caption("Expand each sub-question to inspect retrieved snippets, scores, and source URLs.")
    render_plan_steps(run)

    if run.get("status") == ResearchRunStatus.DONE.value and run.get("report"):
        st.success("Pipeline finished. Export the report above or reopen this run from Run History.")
