import streamlit as st

from core.models import ResearchRunStatus
from pipeline import run_research, run_to_dict
from ui import render_plan_steps, render_report
from ui.theme import format_pipeline_progress, page_intro

page_intro(
    "New Research",
    "Submit a research question to run the full local pipeline: plan sub-questions, "
    "gather web and knowledge-base evidence, extract claims, verify each claim with an "
    "independent LLM judge, and generate a structured report. A fresh run typically takes "
    "**10–20+ minutes on CPU** with `qwen3:8b`.",
)

if "last_run" not in st.session_state:
    st.session_state.last_run = None

st.header("Ask a question")
question = st.text_area(
    "Research question",
    height=140,
    placeholder="e.g. Compare SQLite and PostgreSQL for a local-first desktop app with offline sync",
    help="Be specific — the planner will break this into sub-questions to research separately.",
)
start = st.button("Start Research Pipeline", type="primary")

if start:
    if not question.strip():
        st.warning("Enter a research question before starting.")
    else:
        with st.status("Research pipeline running…", expanded=True) as status:

            def _progress(msg: str) -> None:
                st.write(format_pipeline_progress(msg))

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
    st.header("Latest result")
    m1, m2 = st.columns([1, 3])
    m1.metric("Status", run.get("status") or "unknown")
    with m2:
        st.markdown(f"**Question:** {run.get('user_question')}")
        st.caption(f"Run ID `{run.get('id')}` · last updated {run.get('updated_at')}")
    if run.get("error_message"):
        st.error(run["error_message"])
    if run.get("report"):
        render_report(run)
        st.divider()
    st.subheader("Plan & evidence")
    st.caption("Expand each sub-question to inspect retrieved snippets, scores, and source URLs.")
    render_plan_steps(run)
    if run.get("status") == ResearchRunStatus.DONE.value and run.get("report"):
        st.success("Pipeline finished. Export the report above or open this run again from Run History.")
