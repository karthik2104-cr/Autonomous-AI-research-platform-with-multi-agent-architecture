from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.llm import LLMError, call_llm
from core.models import (
    Claim,
    Citation,
    Evidence,
    PlanStep,
    ResearchRun,
    ResearchRunStatus,
)

logger = logging.getLogger(__name__)

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "minItems": 3,
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "supporting_evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "confidence": {"type": "number"},
                },
                "required": ["statement", "supporting_evidence_ids", "confidence"],
            },
        },
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "conflicting_evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["description", "conflicting_evidence_ids"],
            },
        },
        "gaps": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["claims", "contradictions", "gaps"],
}

ANALYZER_SYSTEM = """You are a research analyst.
Synthesize 3-8 discrete factual claims that answer the research question using ONLY the
numbered evidence provided. Do not invent facts that are not supported by evidence.

For each claim:
- Write a clear standalone statement.
- List supporting_evidence_ids using the exact evidence id strings from the list.
- Set confidence in [0.0, 1.0] based on how directly the cited evidence supports it.

Also list contradictions (sources that conflict) and gaps (sub-questions or topics
with thin/missing evidence). Return JSON only."""


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _resolve_evidence_id(
    token: str,
    by_id: dict[str, Evidence],
    by_url: dict[str, Evidence],
    by_short: dict[str, Evidence],
) -> Evidence | None:
    token = (token or "").strip()
    if not token:
        return None
    if token in by_id:
        return by_id[token]
    if token in by_short:
        return by_short[token]
    if token in by_url:
        return by_url[token]
    # Fuzzy: id prefix or URL substring
    for key, ev in by_id.items():
        if key.startswith(token) or token in key:
            return ev
    for url, ev in by_url.items():
        if token in url or url in token:
            return ev
    return None


def analyze_evidence(session: Session, run: ResearchRun) -> dict[str, Any]:
    """ANALYZING: synthesize claims + citations; store contradictions/gaps on the run."""
    # Research stage may have committed Evidence in this same session; expire cache
    # so selectinload(PlanStep.evidence) sees rows already on disk.
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

    evidence_rows: list[Evidence] = []
    for step in steps:
        evidence_rows.extend(step.evidence or [])

    if not evidence_rows:
        raise LLMError("No evidence available to analyze.")

    # Clear prior analysis artifacts if re-running on the same run.
    existing_claims = list(
        session.scalars(select(Claim).where(Claim.research_run_id == run.id)).all()
    )
    for claim in existing_claims:
        session.delete(claim)
    session.flush()

    # Cap context for local 8B models: prefer higher-relevance / web evidence first.
    ranked = sorted(
        evidence_rows,
        key=lambda ev: (
            0 if (ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type)) == "web" else 1,
            -(ev.relevance_score or 0.0),
        ),
    )
    selected = ranked[:16]

    by_id: dict[str, Evidence] = {str(ev.id): ev for ev in evidence_rows}
    by_short: dict[str, Evidence] = {str(ev.id)[:8]: ev for ev in evidence_rows}
    by_url: dict[str, Evidence] = {}
    for ev in evidence_rows:
        if ev.source_url:
            by_url[ev.source_url] = ev

    sub_qs = "\n".join(f"- {s.sub_question}" for s in steps) or "(none)"
    numbered = []
    for ev in selected:
        numbered.append(
            f"[{ev.id}] type={ev.source_type.value if hasattr(ev.source_type, 'value') else ev.source_type}\n"
            f"url={ev.source_url or '(none)'}\n"
            f"content={(ev.raw_content or '')[:500]}"
        )

    user = (
        f"Research question:\n{run.user_question}\n\n"
        f"Sub-questions:\n{sub_qs}\n\n"
        f"Evidence ({len(selected)} of {len(evidence_rows)} items shown). "
        f"Cite using the exact [id] values:\n\n"
        + "\n\n".join(numbered)
    )

    parsed = call_llm(
        ANALYZER_SYSTEM,
        user,
        json_schema=ANALYSIS_SCHEMA,
        session=session,
        research_run_id=run.id,
        stage=ResearchRunStatus.ANALYZING.value,
        max_retries=1,
        timeout_seconds=300,
        num_predict=1200,
    )
    if not isinstance(parsed, dict):
        raise LLMError("Analyzer did not return a JSON object.")

    raw_claims = parsed.get("claims") or []
    if not raw_claims:
        raise LLMError("Analyzer returned no claims.")

    created: list[Claim] = []
    for raw in raw_claims:
        if not isinstance(raw, dict):
            continue
        statement = str(raw.get("statement") or "").strip()
        if not statement:
            continue
        try:
            confidence = _clamp(float(raw.get("confidence", 0.5)))
        except (TypeError, ValueError):
            confidence = 0.5

        claim = Claim(
            research_run_id=run.id,
            statement=statement,
            confidence_score=confidence,
        )
        session.add(claim)
        session.flush()

        tokens = raw.get("supporting_evidence_ids") or []
        linked: set[uuid.UUID] = set()
        for token in tokens:
            ev = _resolve_evidence_id(str(token), by_id, by_url, by_short)
            if ev is None or ev.id in linked:
                continue
            session.add(Citation(claim_id=claim.id, evidence_id=ev.id))
            linked.add(ev.id)
        created.append(claim)

    if not created:
        raise LLMError("Analyzer produced no persistable claims.")

    contradictions = []
    for raw in parsed.get("contradictions") or []:
        if not isinstance(raw, dict):
            continue
        desc = str(raw.get("description") or "").strip()
        if not desc:
            continue
        ids = []
        for token in raw.get("conflicting_evidence_ids") or []:
            ev = _resolve_evidence_id(str(token), by_id, by_url, by_short)
            if ev is not None:
                ids.append(str(ev.id))
        contradictions.append({"description": desc, "conflicting_evidence_ids": ids})

    gaps = [str(g).strip() for g in (parsed.get("gaps") or []) if str(g).strip()]

    analysis_payload = {
        "contradictions": contradictions,
        "gaps": gaps,
        "claim_count": len(created),
    }
    run.analysis_json = analysis_payload
    session.commit()
    logger.info(
        "Run %s analyzed: %s claim(s), %s contradiction(s), %s gap(s)",
        run.id,
        len(created),
        len(contradictions),
        len(gaps),
    )
    return analysis_payload
