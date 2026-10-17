from uuid import UUID

import streamlit as st

from pipeline import list_runs, load_run, run_to_dict
from ui import render_plan_steps, render_report
from ui.theme import (
    empty_state,
    format_timestamp,
    page_header,
    render_pipeline_stages,
    section_label,
    status_badge_html,
)

page_header(
    "Run History",
    "Browse past research runs, open reports and evidence, and export Markdown or PDF. "
    "Select View on any run to inspect full detail.",
)

if "history_page" not in st.session_state:
    st.session_state.history_page = 1
if "selected_run_id" not in st.session_state:
    st.session_state.selected_run_id = None

page_size = 20
items, total = list_runs(page=st.session_state.history_page, page_size=page_size)
page = st.session_state.history_page
total_pages = max(1, (total + page_size - 1) // page_size)

section_label("All runs")
st.caption(f"{total} research run(s) stored locally.")

if not items:
    empty_state(
        "No research runs yet",
        "Start one from New Research to populate this history.",
    )
    st.page_link("pages/1_New_Research.py", label="Go to New Research", icon="🔍")
else:
    header = st.columns((1.4, 5.2, 1.6, 2.2, 1))
    header[0].markdown("**Run ID**")
    header[1].markdown("**Question**")
    header[2].markdown("**Status**")
    header[3].markdown("**Created**")
    header[4].markdown("")

    for item in items:
        cols = st.columns((1.4, 5.2, 1.6, 2.2, 1))
        run_id = str(item.id)
        status = item.status.value if hasattr(item.status, "value") else str(item.status)
        created = format_timestamp(item.created_at.isoformat() if item.created_at else None)
        cols[0].code(run_id[:8], language="text")
        q = item.user_question or ""
        cols[1].write(q if len(q) <= 140 else q[:137] + "…")
        cols[2].markdown(status_badge_html(status), unsafe_allow_html=True)
        cols[3].caption(created)
        if cols[4].button("View", key=f"view-{run_id}", help="Open report and evidence"):
            st.session_state.selected_run_id = run_id
            st.rerun()

    nav = st.columns(3)
    if nav[0].button("← Previous", disabled=page <= 1):
        st.session_state.history_page = max(1, page - 1)
        st.rerun()
    nav[1].markdown(f"<div style='text-align:center;padding-top:0.4rem'>Page **{page}** of **{total_pages}**</div>", unsafe_allow_html=True)
    if nav[2].button("Next →", disabled=page >= total_pages):
        st.session_state.history_page = page + 1
        st.rerun()

if st.session_state.selected_run_id:
    st.divider()
    section_label("Run detail")
    detail_run = load_run(UUID(st.session_state.selected_run_id))
    if detail_run is None:
        st.error("That run was not found — it may have been deleted.")
    else:
        detail = run_to_dict(detail_run)
        top1, top2 = st.columns([1, 4])
        with top1:
            st.markdown("**Status**")
            st.markdown(status_badge_html(detail.get("status")), unsafe_allow_html=True)
        with top2:
            st.markdown(f"**Question**  \n{detail.get('user_question')}")
            st.caption(f"Full run ID: `{detail.get('id')}`")

        render_pipeline_stages(detail.get("status"))

        if detail.get("error_message"):
            st.error(detail["error_message"])
        if detail.get("report"):
            render_report(detail)
            st.divider()
        st.markdown("### Plan & evidence")
        st.caption("Sub-questions from the planner and the evidence retrieved for each.")
        render_plan_steps(detail)
        with st.expander("Developer / raw JSON", expanded=False):
            st.json(detail)
