import json

import streamlit as st

from evaluation.run_eval import RESULTS_PATH, load_results, run_evaluation
from ui.theme import format_pipeline_progress, page_intro

page_intro(
    "Evaluation",
    "Measure retrieval and verification quality against a **hand-built test question set** "
    "(`evaluation/test_questions.json`). Metrics are deliberately simple heuristics — keyword "
    "matches in evidence and verifier consistency — not semantic gold-standard scores.",
)

st.info(
    "**How to read these metrics:** "
    "**Retrieval hit** = at least one evidence snippet contains an expected keyword (not semantic similarity). "
    "**Unsupported rate** = claims the verifier marked false or inconclusive (internal consistency, not ground truth). "
    "A full eval run can take **several minutes per question** on CPU when runs are not reused."
)

results = load_results()

if results is None:
    st.warning(
        f"No evaluation results yet. Run the test set below — output is saved to `{RESULTS_PATH}`."
    )
else:
    agg = results.get("aggregate") or {}
    st.header("Aggregate (last run)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Questions evaluated", agg.get("questions_evaluated", "—"))
    if agg.get("questions_done") is not None:
        c1.caption(f"Done: {agg.get('questions_done')} · Failed: {agg.get('questions_failed', 0)}")
    uns = agg.get("avg_unsupported_rate")
    c2.metric(
        "Avg unsupported claim rate",
        f"{uns:.0%}" if isinstance(uns, (int, float)) else "—",
        help="Verifier returned false or inconclusive",
    )
    t = agg.get("avg_response_time_seconds")
    if agg.get("all_runs_reused"):
        c3.metric(
            "Avg response time",
            "—",
            help="Previous run reused existing DONE runs; use fresh runs to measure wall clock",
        )
    else:
        c3.metric(
            "Avg response time (s)",
            f"{t:.0f}" if isinstance(t, (int, float)) else "—",
        )
    rh = agg.get("retrieval_hit_rate")
    c4.metric(
        "Retrieval keyword hit rate",
        f"{rh:.0%}" if isinstance(rh, (int, float)) else "—",
        help="Basic keyword-in-evidence heuristic",
    )
    if results.get("disclaimer"):
        st.caption(results["disclaimer"])
    st.caption(f"Generated: {results.get('generated_at', 'unknown')}")

    rows = []
    for row in results.get("per_question") or []:
        sup = row.get("supported_rate")
        uns = row.get("unsupported_rate")
        rows.append(
            {
                "Question id": row.get("id"),
                "Retrieval hit": "yes" if row.get("retrieval_hit") else "no",
                "Supported rate": f"{sup:.0%}" if isinstance(sup, (int, float)) else "n/a",
                "Unsupported rate": f"{uns:.0%}" if isinstance(uns, (int, float)) else "n/a",
                "Time (s)": row.get("response_time_seconds"),
                "Status": row.get("run_status"),
                "Reused run": row.get("reused_run"),
            }
        )
    if rows:
        st.subheader("Per-question results")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("Full results JSON"):
        st.json(results)

st.divider()
st.header("Run evaluation set")
limit = st.number_input(
    "Limit questions (0 = entire set)",
    min_value=0,
    value=0,
    step=1,
    help="Use a small limit (e.g. 3) for a quicker check during development.",
)
reuse = st.checkbox(
    "Reuse matching completed runs when possible",
    value=True,
    help="Skips re-running the pipeline when a DONE run already exists for the same question.",
)

if st.button("Run Evaluation Set (~10–20 min per fresh question)", type="primary"):
    lim = int(limit) if limit and limit > 0 else None
    with st.status("Evaluation running…", expanded=True) as status:
        try:

            def _progress(msg: str) -> None:
                st.write(format_pipeline_progress(msg) if "pipeline" in msg.lower() else msg)

            payload = run_evaluation(
                limit=lim,
                reuse=reuse,
                on_progress=_progress,
            )
            st.session_state["eval_results"] = payload
            status.update(label="Evaluation complete", state="complete")
            st.rerun()
        except Exception as exc:
            status.update(label="Evaluation failed", state="error")
            st.error(str(exc))

if "eval_results" in st.session_state and st.session_state["eval_results"]:
    st.download_button(
        "Download results.json",
        data=json.dumps(st.session_state["eval_results"], indent=2),
        file_name="evaluation_results.json",
        mime="application/json",
    )
