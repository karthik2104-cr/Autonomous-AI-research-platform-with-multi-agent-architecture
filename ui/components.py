def render_plan_steps(run: dict) -> None:
    import streamlit as st

    steps = run.get("plan_steps") or []
    if not steps:
        st.caption("No plan steps yet.")
        return

    for step in sorted(steps, key=lambda item: item.get("order_index", 0)):
        evidence = step.get("evidence") or []
        scores = [item.get("relevance_score") for item in evidence if item.get("relevance_score") is not None]
        top_score = max(scores) if scores else None
        title = f"{step.get('order_index', 0) + 1}. {step.get('sub_question')}  —  {step.get('status')}"
        with st.expander(title, expanded=False):
            meta = f"{len(evidence)} evidence item(s)"
            if top_score is not None:
                meta += f" · top relevance {top_score:.2f}"
            hint = step.get("tool_hint")
            if hint:
                meta += f" · tool: {hint}"
            st.caption(meta)
            if not evidence:
                st.write("No evidence stored for this step.")
                continue
            for item in sorted(
                evidence,
                key=lambda ev: (ev.get("relevance_score") is None, -(ev.get("relevance_score") or 0)),
            ):
                score = item.get("relevance_score")
                score_label = f"{score:.2f}" if isinstance(score, (int, float)) else "unscored"
                source_type = item.get("source_type") or ""
                url = item.get("source_url") or ""
                prefix = f"**[{score_label}]**"
                if source_type:
                    prefix += f" `{source_type}`"
                if url:
                    st.markdown(f"{prefix} {url}")
                else:
                    st.markdown(f"{prefix} (no url)")
                st.write(item.get("raw_content") or "")


def report_to_markdown(content: dict) -> str:
    from agents.report_generator import report_to_markdown as _md

    return _md(content)


def render_report(run: dict) -> None:
    import streamlit as st

    from ui.theme import status_badge

    report = run.get("report")
    if not report:
        st.caption("No report yet for this run.")
        return

    st.header("Research report")
    st.markdown(f"**Question:** {report.get('research_question') or run.get('user_question')}")

    st.subheader("Executive summary")
    st.write(report.get("executive_summary") or "")

    findings = report.get("key_findings") or []
    if findings:
        st.subheader("Key findings")
        for item in findings:
            st.markdown(f"- {item}")

    claims = report.get("claims_with_verification") or run.get("claims") or []
    if claims:
        st.subheader("Claims & verification")
        st.caption("Each claim was checked independently against its cited evidence snippets.")
        rows = []
        for claim in claims:
            status = claim.get("verification_status") or (
                "supported"
                if claim.get("is_supported") is True
                else "unsupported"
                if claim.get("is_supported") is False
                else "uncertain"
            )
            conf = claim.get("confidence_score")
            rows.append(
                {
                    "Status": status_badge(status),
                    "Claim": claim.get("statement") or "",
                    "Confidence": conf if isinstance(conf, (int, float)) else None,
                }
            )
        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Claim": st.column_config.TextColumn("Claim", width="large"),
                "Confidence": st.column_config.NumberColumn(
                    "Confidence",
                    format="%.2f",
                    width="small",
                ),
            },
        )
        with st.expander("Verification reasoning (per claim)"):
            for claim in claims:
                status = claim.get("verification_status") or "uncertain"
                st.markdown(f"**{status_badge(status)}** — {claim.get('statement')}")
                st.caption(claim.get("verification_reasoning") or "(no reasoning recorded)")

    contradictions = report.get("contradictions") or (run.get("analysis_json") or {}).get("contradictions") or []
    if contradictions:
        st.subheader("Contradictions")
        for item in contradictions:
            if isinstance(item, dict):
                st.warning(item.get("description") or str(item))
            else:
                st.warning(str(item))

    gaps = report.get("gaps") or (run.get("analysis_json") or {}).get("gaps") or []
    if gaps:
        st.subheader("Gaps in evidence")
        for item in gaps:
            st.info(str(item))

    limitations = report.get("limitations") or []
    if limitations:
        st.subheader("Limitations")
        for item in limitations:
            st.markdown(f"- {item}")

    if report.get("conclusion"):
        st.subheader("Conclusion")
        st.write(report["conclusion"])

    sources = report.get("sources") or []
    if sources:
        st.subheader("Sources")
        for src in sources:
            url = src.get("source_url")
            label = src.get("source_type") or "source"
            if url and str(url).startswith("http"):
                st.markdown(f"- `{label}` — [{url}]({url})")
            else:
                st.markdown(f"- `{label}` — {url or '(no url)'}")

    st.divider()
    st.subheader("Export")
    md = report_to_markdown(report)
    run_id = run.get("id", "run")
    short_id = run_id[:8] if isinstance(run_id, str) else "run"
    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        st.download_button(
            "Download Markdown",
            data=md,
            file_name=f"research_report_{short_id}.md",
            mime="text/markdown",
            key=f"dl-md-{short_id}",
        )
    with dl_col2:
        from utils.pdf_export import generate_pdf

        pdf_bytes = generate_pdf(report)
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"research_report_{short_id}.pdf",
            mime="application/pdf",
            key=f"dl-pdf-{short_id}",
        )
