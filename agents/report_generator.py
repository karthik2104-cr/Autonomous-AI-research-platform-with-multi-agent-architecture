from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.llm import LLMError, call_llm
from core.models import (
    Claim,
    Citation,
    Evidence,
    PlanStep,
    Report,
    ResearchRun,
    ResearchRunStatus,
)

logger = logging.getLogger(__name__)

NARRATIVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "key_findings": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
        },
        "conclusion": {"type": "string"},
    },
    "required": ["executive_summary", "key_findings", "limitations", "conclusion"],
}

NARRATIVE_SYSTEM = """You write concise research report narrative sections.
You are given the research question, verified/unverified claims, contradictions, and gaps.
Write an executive_summary, key_findings (short prose bullets), limitations, and conclusion.
Do NOT invent new claims, citations, URLs, or evidence. Only narrate what is provided.
Return JSON only."""


def _verification_label(is_supported: bool | None) -> str:
    if is_supported is True:
        return "supported"
    if is_supported is False:
        return "unsupported"
    return "uncertain"


def generate_report(session: Session, run: ResearchRun) -> Report:
    """GENERATING: DB-built structured sections + LLM narrative; persist Report.content_json."""
    # Avoid stale identity-map Claim rows loaded before VERIFYING finished.
    session.expire_all()
    steps = list(
        session.scalars(
            select(PlanStep)
            .where(PlanStep.research_run_id == run.id)
            .options(selectinload(PlanStep.evidence))
            .order_by(PlanStep.order_index)
            .execution_options(populate_existing=True)
        ).all()
    )
    claims = list(
        session.scalars(
            select(Claim)
            .where(Claim.research_run_id == run.id)
            .options(
                selectinload(Claim.citations).selectinload(Citation.evidence),
                selectinload(Claim.verification_result),
            )
            .execution_options(populate_existing=True)
        ).all()
    )
    if not claims:
        raise LLMError("No claims available for report generation.")

    analysis = run.analysis_json if isinstance(run.analysis_json, dict) else {}
    contradictions = list(analysis.get("contradictions") or [])
    gaps = list(analysis.get("gaps") or [])

    claims_with_verification: list[dict[str, Any]] = []
    claim_brief_for_llm: list[str] = []
    for claim in claims:
        vr = claim.verification_result
        status = _verification_label(None if vr is None else vr.is_supported)
        citations = []
        for cit in claim.citations or []:
            ev = cit.evidence
            if ev is None:
                continue
            citations.append(
                {
                    "evidence_id": str(ev.id),
                    "source_url": ev.source_url,
                    "source_type": ev.source_type.value
                    if hasattr(ev.source_type, "value")
                    else str(ev.source_type),
                    "snippet": (ev.raw_content or "")[:400],
                }
            )
        entry = {
            "claim_id": str(claim.id),
            "statement": claim.statement,
            "confidence_score": claim.confidence_score,
            "verification_status": status,
            "verification_reasoning": None if vr is None else vr.reasoning,
            "citations": citations,
        }
        claims_with_verification.append(entry)
        claim_brief_for_llm.append(
            f"- [{status}] (analysis_confidence={claim.confidence_score}) {claim.statement}"
        )

    # Sources list built from DB evidence — never LLM-invented.
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for step in steps:
        for ev in step.evidence or []:
            key = str(ev.id)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "evidence_id": str(ev.id),
                    "source_url": ev.source_url,
                    "source_type": ev.source_type.value
                    if hasattr(ev.source_type, "value")
                    else str(ev.source_type),
                    "relevance_score": ev.relevance_score,
                    "snippet": (ev.raw_content or "")[:300],
                }
            )

    user = (
        f"Research question:\n{run.user_question}\n\n"
        f"Claims with verification status:\n" + "\n".join(claim_brief_for_llm) + "\n\n"
        f"Contradictions:\n{contradictions or ['(none)']}\n\n"
        f"Gaps:\n{gaps or ['(none)']}\n\n"
        "Write narrative sections only. Do not invent sources or claims."
    )
    narrative = call_llm(
        NARRATIVE_SYSTEM,
        user,
        json_schema=NARRATIVE_SCHEMA,
        session=session,
        research_run_id=run.id,
        stage=ResearchRunStatus.GENERATING.value,
        max_retries=1,
        timeout_seconds=120,
        num_predict=1200,
    )
    if not isinstance(narrative, dict):
        raise LLMError("Report narrative was not a JSON object.")

    content: dict[str, Any] = {
        "research_question": run.user_question,
        "executive_summary": str(narrative.get("executive_summary") or "").strip(),
        "key_findings": [str(x).strip() for x in (narrative.get("key_findings") or []) if str(x).strip()],
        "claims_with_verification": claims_with_verification,
        "contradictions": contradictions,
        "gaps": gaps,
        "limitations": [str(x).strip() for x in (narrative.get("limitations") or []) if str(x).strip()],
        "sources": sources,
        "conclusion": str(narrative.get("conclusion") or "").strip(),
    }
    if not content["executive_summary"]:
        raise LLMError("Report generator returned an empty executive summary.")

    if run.report is not None:
        session.delete(run.report)
        session.flush()
    else:
        existing_report = session.scalar(
            select(Report).where(Report.research_run_id == run.id)
        )
        if existing_report is not None:
            session.delete(existing_report)
            session.flush()

    report = Report(research_run_id=run.id, content_json=content, content_pdf_path=None)
    session.add(report)
    session.commit()
    logger.info("Run %s report generated (%s sources)", run.id, len(sources))
    return report


def report_to_markdown(content: dict[str, Any]) -> str:
    """Format content_json as downloadable markdown (DB-structured + narrative)."""
    lines: list[str] = []
    lines.append(f"# Research Report\n")
    lines.append(f"**Question:** {content.get('research_question', '')}\n")
    lines.append("## Executive Summary\n")
    lines.append(f"{content.get('executive_summary', '')}\n")
    lines.append("## Key Findings\n")
    for item in content.get("key_findings") or []:
        lines.append(f"- {item}")
    lines.append("\n## Claims & Verification\n")
    for claim in content.get("claims_with_verification") or []:
        status = claim.get("verification_status") or "uncertain"
        conf = claim.get("confidence_score")
        conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "n/a"
        lines.append(f"- **[{status}]** (confidence {conf_s}) {claim.get('statement')}")
        if claim.get("verification_reasoning"):
            lines.append(f"  - Judge: {claim['verification_reasoning']}")
    contradictions = content.get("contradictions") or []
    if contradictions:
        lines.append("\n## Contradictions\n")
        for c in contradictions:
            if isinstance(c, dict):
                lines.append(f"- {c.get('description')}")
            else:
                lines.append(f"- {c}")
    gaps = content.get("gaps") or []
    if gaps:
        lines.append("\n## Gaps\n")
        for g in gaps:
            lines.append(f"- {g}")
    lines.append("\n## Limitations\n")
    for item in content.get("limitations") or []:
        lines.append(f"- {item}")
    lines.append("\n## Conclusion\n")
    lines.append(f"{content.get('conclusion', '')}\n")
    lines.append("## Sources\n")
    for src in content.get("sources") or []:
        url = src.get("source_url") or "(no url)"
        lines.append(f"- [{src.get('source_type')}] {url}")
        if src.get("snippet"):
            lines.append(f"  - {src['snippet']}")
    return "\n".join(lines)
