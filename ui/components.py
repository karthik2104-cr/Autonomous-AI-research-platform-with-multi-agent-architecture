"""Shared Streamlit presentation components for reports and evidence."""

from __future__ import annotations

import html
from typing import Any


def render_plan_steps(run: dict) -> None:
    import streamlit as st

    from ui.theme import status_badge_html

    steps = run.get("plan_steps") or []
    if not steps:
        st.caption("No plan steps yet.")
        return

    for step in sorted(steps, key=lambda item: item.get("order_index", 0)):
        evidence = step.get("evidence") or []
        scores = [
            item.get("relevance_score")
            for item in evidence
            if item.get("relevance_score") is not None
        ]
        top_score = max(scores) if scores else None
        status = step.get("status") or "PENDING"
        title = f"{step.get('order_index', 0) + 1}. {step.get('sub_question')}"
        with st.expander(title, expanded=False):
            cols = st.columns([1, 3])
            with cols[0]:
                st.markdown(status_badge_html(status), unsafe_allow_html=True)
            meta_parts = [f"{len(evidence)} evidence item(s)"]
            if top_score is not None:
                meta_parts.append(f"top relevance {top_score:.2f}")
            hint = step.get("tool_hint")
            if hint:
                meta_parts.append(f"tool: {hint}")
            st.caption(" · ".join(meta_parts))
            if not evidence:
                st.write("No evidence stored for this step.")
                continue
            for item in sorted(
                evidence,
                key=lambda ev: (
                    ev.get("relevance_score") is None,
                    -(ev.get("relevance_score") or 0),
                ),
            ):
                score = item.get("relevance_score")
                score_label = f"{score:.2f}" if isinstance(score, (int, float)) else "unscored"
                source_type = item.get("source_type") or ""
                url = item.get("source_url") or ""
                type_badge = f"`{source_type}`" if source_type else ""
                if url:
                    st.markdown(f"**[{score_label}]** {type_badge} {url}")
                else:
                    st.markdown(f"**[{score_label}]** {type_badge} (no url)")
                st.write(item.get("raw_content") or "")


def report_to_markdown(content: dict) -> str:
    from agents.report_generator import report_to_markdown as _md

    return _md(content)


def render_report(run: dict) -> None:
    import streamlit as st

    from ui.theme import section_label, status_badge, status_badge_html

    report = run.get("report")
    if not report:
        st.caption("No report yet for this run.")
        return

    question = report.get("research_question") or run.get("user_question") or ""
    st.markdown("## Research report")
    st.markdown(f"**Question**  \n{question}")

    # Export actions near the top for convenience
    md = report_to_markdown(report)
    run_id = run.get("id", "run")
    short_id = run_id[:8] if isinstance(run_id, str) else "run"
    dl1, dl2, _ = st.columns([1, 1, 2])
    with dl1:
        st.download_button(
            "Download Markdown",
            data=md,
            file_name=f"research_report_{short_id}.md",
            mime="text/markdown",
            key=f"dl-md-{short_id}",
        )
    with dl2:
        from utils.pdf_export import generate_pdf

        pdf_bytes = bytes(generate_pdf(report))
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"research_report_{short_id}.pdf",
            mime="application/pdf",
            key=f"dl-pdf-{short_id}",
        )

    section_label("Executive summary")
    summary = report.get("executive_summary") or ""
    st.markdown(
        f'<div class="ri-summary">{html.escape(summary)}</div>',
        unsafe_allow_html=True,
    )

    findings = report.get("key_findings") or []
    if findings:
        st.markdown("### Key findings")
        for item in findings:
            st.markdown(f"- {item}")

    claims = report.get("claims_with_verification") or run.get("claims") or []
    if claims:
        st.markdown("### Claims & verification")
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
                st.markdown(
                    f"{status_badge_html(status)} — {html.escape(str(claim.get('statement') or ''))}",
                    unsafe_allow_html=True,
                )
                st.caption(claim.get("verification_reasoning") or "(no reasoning recorded)")

    contradictions = (
        report.get("contradictions")
        or (run.get("analysis_json") or {}).get("contradictions")
        or []
    )
    if contradictions:
        st.markdown("### Contradictions")
        for item in contradictions:
            if isinstance(item, dict):
                st.warning(item.get("description") or str(item))
            else:
                st.warning(str(item))

    gaps = report.get("gaps") or (run.get("analysis_json") or {}).get("gaps") or []
    if gaps:
        st.markdown("### Gaps in evidence")
        for item in gaps:
            st.info(str(item))

    limitations = report.get("limitations") or []
    if limitations:
        st.markdown("### Limitations")
        for item in limitations:
            st.markdown(f"- {item}")

    if report.get("conclusion"):
        st.markdown("### Conclusion")
        st.write(report["conclusion"])

    sources = report.get("sources") or []
    if sources:
        st.markdown("### Sources")
        for src in sources:
            url = src.get("source_url")
            label = html.escape(str(src.get("source_type") or "source"))
            if url and str(url).startswith("http"):
                safe_url = html.escape(str(url))
                st.markdown(
                    f'<div class="ri-source"><span class="ri-badge ri-badge-neutral">'
                    f"{label}</span> "
                    f'<a href="{safe_url}" target="_blank" rel="noopener">{safe_url}</a></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="ri-source"><span class="ri-badge ri-badge-neutral">'
                    f"{label}</span> {html.escape(str(url or '(no url)'))}</div>",
                    unsafe_allow_html=True,
                )
