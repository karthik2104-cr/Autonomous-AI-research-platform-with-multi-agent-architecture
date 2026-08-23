from uuid import UUID

import streamlit as st

from pipeline import list_runs, load_run, run_to_dict
from ui import render_plan_steps, render_report
from ui.theme import page_intro

page_intro(
    "Run History",
    "Browse past research runs, inspect the plan and evidence collected for each one, and "
    "read or export completed reports. Select **View** on any run to open its full detail "
    "including claims, verification status, and download buttons.",
)

if "history_page" not in st.session_state:
    st.session_state.history_page = 1
if "selected_run_id" not in st.session_state:
    st.session_state.selected_run_id = None

page_size = 20
items, total = list_runs(page=st.session_state.history_page, page_size=page_size)
page = st.session_state.history_page
total_pages = max(1, (total + page_size - 1) // page_size)

st.header("All runs")
st.caption(f"{total} research run(s) stored locally.")

if not items:
    st.info("No research runs yet. Start one from **New Research**.")
else:
    header = st.columns((2, 6, 2, 3, 1))
    header[0].markdown("**Run ID**")
    header[1].markdown("**Question**")
    header[2].markdown("**Status**")
    header[3].markdown("**Created**")
    header[4].markdown("")

    for item in items:
        cols = st.columns((2, 6, 2, 3, 1))
        run_id = str(item.id)
        status = item.status.value if hasattr(item.status, "value") else str(item.status)
        created = item.created_at.isoformat() if item.created_at else ""
        cols[0].code(run_id[:8], language="text")
        cols[1].write(item.user_question)
        cols[2].write(status)
        cols[3].caption(created.replace("T", " ")[:19] if created else "")
        if cols[4].button("View", key=f"view-{run_id}", help="Open report and evidence"):
            st.session_state.selected_run_id = run_id
            st.rerun()

    nav = st.columns(3)
    if nav[0].button("← Previous page", disabled=page <= 1):
        st.session_state.history_page = max(1, page - 1)
        st.rerun()
    nav[1].write(f"Page **{page}** of **{total_pages}**")
    if nav[2].button("Next page →", disabled=page >= total_pages):
        st.session_state.history_page = page + 1
        st.rerun()

if st.session_state.selected_run_id:
    st.divider()
    st.header("Run detail")
    detail_run = load_run(UUID(st.session_state.selected_run_id))
    if detail_run is None:
        st.error("That run was not found — it may have been deleted.")
    else:
        detail = run_to_dict(detail_run)
        st.markdown(f"**Status:** `{detail.get('status')}`")
        st.markdown(f"**Question:** {detail.get('user_question')}")
        st.caption(f"Full run ID: `{detail.get('id')}`")
        if detail.get("error_message"):
            st.error(detail["error_message"])
        if detail.get("report"):
            render_report(detail)
            st.divider()
        st.subheader("Plan & evidence")
        st.caption("Sub-questions from the planner and the evidence retrieved for each.")
        render_plan_steps(detail)
        with st.expander("Raw run JSON (debug)"):
            st.json(detail)
