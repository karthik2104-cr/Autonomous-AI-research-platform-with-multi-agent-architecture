import json

import streamlit as st

from evaluation.run_eval import RESULTS_PATH, load_results, run_evaluation
from ui.theme import (
    empty_state,
    format_pipeline_progress,
    metric_row,
    page_header,
    section_label,
)

page_header(
    "Evaluation",
    "Measure retrieval and verification against a hand-built test set "
    "(evaluation/test_questions.json). Metrics are honest heuristics — not ground-truth accuracy.",
)

st.info(
    "**How to read these metrics:** "
    "**Retrieval hit** = at least one evidence snippet contains an expected keyword "
    "(not semantic similarity). "
    "**Unsupported rate** = claims the verifier marked false or inconclusive "
    "(internal consistency, not ground truth). "
    "A full eval run can take several minutes per fresh question on CPU."
)

results = load_results()

if results is None:
    empty_state(
        "Evaluation has not been run yet",
        f"Run the test set below. Results are saved to {RESULTS_PATH}.",
    )
else:
    agg = results.get("aggregate") or {}
    section_label("Aggregate (last run)")

    uns = agg.get("avg_unsupported_rate")
    uns_s = f"{uns:.0%}" if isinstance(uns, (int, float)) else "—"
    t = agg.get("avg_response_time_seconds")
    if agg.get("all_runs_reused"):
        time_s = "—"
        time_help = "Last run reused DONE runs; use fresh runs for wall-clock time"
    else:
        time_s = f"{t:.0f}" if isinstance(t, (int, float)) else "—"
        time_help = "Average end-to-end seconds across evaluated questions"

    rh = agg.get("retrieval_hit_rate")
    rh_s = f"{rh:.0%}" if isinstance(rh, (int, float)) else "—"

    metric_row(
        [
            ("Questions evaluated", str(agg.get("questions_evaluated", "—")), None),
            ("Avg unsupported rate", uns_s, "Verifier false or inconclusive"),
            ("Avg response time (s)", time_s, time_help),
            ("Retrieval keyword hit", rh_s, "Keyword-in-evidence heuristic"),
        ]
    )
    if agg.get("questions_done") is not None:
        st.caption(
            f"Completed: {agg.get('questions_done')} · Failed: {agg.get('questions_failed', 0)}"
        )
    if results.get("disclaimer"):
        st.caption(results["disclaimer"])
    st.caption(f"Generated: {results.get('generated_at', 'unknown')}")

    rows = []
    for row in results.get("per_question") or []:
        sup = row.get("supported_rate")
        uns_r = row.get("unsupported_rate")
        rows.append(
            {
                "Question id": row.get("id"),
                "Retrieval hit": "yes" if row.get("retrieval_hit") else "no",
                "Supported rate": f"{sup:.0%}" if isinstance(sup, (int, float)) else "n/a",
                "Unsupported rate": f"{uns_r:.0%}" if isinstance(uns_r, (int, float)) else "n/a",
                "Time (s)": row.get("response_time_seconds"),
                "Status": row.get("run_status"),
                "Reused": row.get("reused_run"),
            }
        )
    if rows:
        st.markdown("### Per-question results")
        # Lightweight bar chart only when numeric rates exist
        chart_data = []
        for row in results.get("per_question") or []:
            uns_v = row.get("unsupported_rate")
            if isinstance(uns_v, (int, float)):
                chart_data.append(
                    {
                        "question": str(row.get("id") or "")[:24],
                        "unsupported_rate": float(uns_v),
                    }
                )
        if chart_data:
            import pandas as pd

            st.caption("Unsupported claim rate by question (verifier heuristic)")
            st.bar_chart(
                pd.DataFrame(chart_data).set_index("question"),
                color="#5B8CFF",
                height=220,
            )

        st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("Full results JSON"):
        st.json(results)

st.divider()
section_label("Run evaluation set")
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
