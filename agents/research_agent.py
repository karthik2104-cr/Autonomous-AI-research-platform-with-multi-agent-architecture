from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.llm import call_llm
from core.models import (
    Evidence,
    PlanStep,
    PlanStepStatus,
    ResearchRun,
    ResearchRunStatus,
    SourceType,
)
from core.vector_store import query_documents
from tools.web_search import web_search

logger = logging.getLogger(__name__)

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "relevance_score": {"type": "number"},
                },
                "required": ["index", "relevance_score"],
            },
        }
    },
    "required": ["scores"],
}

SCORER_SYSTEM = """You score snippets for a research sub-question.
Return one relevance_score in [0.0, 1.0] per result index.
JSON only."""


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _score_results(
    session: Session,
    run: ResearchRun,
    sub_question: str,
    results: list[dict[str, str]],
) -> dict[int, float]:
    numbered = "\n".join(
        f"[{i}] {item.get('title') or item.get('source') or '(no title)'}\n"
        f"{item.get('url') or ''}\n{item.get('snippet') or item.get('text') or ''}"
        for i, item in enumerate(results)
    )
    user = f"Sub-question:\n{sub_question}\n\nScore indexes 0..{len(results) - 1}.\n\n{numbered}"
    try:
        parsed = call_llm(
            SCORER_SYSTEM,
            user,
            json_schema=SCORE_SCHEMA,
            session=session,
            research_run_id=run.id,
            stage=ResearchRunStatus.RESEARCHING.value,
        )
    except Exception:
        logger.warning("Relevance scoring failed for run %s", run.id, exc_info=True)
        return {}
    if not isinstance(parsed, dict):
        return {}
    mapped: dict[int, float] = {}
    for raw in parsed.get("scores") or []:
        if not isinstance(raw, dict):
            continue
        try:
            mapped[int(raw["index"])] = _clamp(float(raw["relevance_score"]))
        except (KeyError, TypeError, ValueError):
            continue
    return mapped


def gather_evidence(session: Session, run: ResearchRun, on_progress=None) -> None:
    steps = list(
        session.scalars(
            select(PlanStep)
            .where(PlanStep.research_run_id == run.id)
            .options(selectinload(PlanStep.evidence))
            .order_by(PlanStep.order_index)
        ).all()
    )

    for step in steps:
        if on_progress:
            on_progress(f"Researching: {step.sub_question}")
        step.status = PlanStepStatus.IN_PROGRESS
        session.commit()
        try:
            web_hits = web_search(step.sub_question, max_results=5)
            rag_hits = query_documents(step.sub_question, n_results=3)

            rows: list[Evidence] = []
            score_inputs: list[dict[str, str]] = []

            for hit in web_hits:
                evidence = Evidence(
                    plan_step_id=step.id,
                    source_url=hit.get("url") or None,
                    source_type=SourceType.WEB,
                    raw_content=(hit.get("snippet") or hit.get("title") or "").strip() or "(no snippet)",
                    retrieved_at=datetime.now(timezone.utc),
                )
                session.add(evidence)
                rows.append(evidence)
                score_inputs.append(hit)

            for hit in rag_hits:
                evidence = Evidence(
                    plan_step_id=step.id,
                    source_url=hit.get("source") or None,
                    source_type=SourceType.DOCUMENT,
                    raw_content=(hit.get("text") or "").strip() or "(empty document)",
                    retrieved_at=datetime.now(timezone.utc),
                )
                session.add(evidence)
                rows.append(evidence)
                score_inputs.append(
                    {"title": hit.get("source") or "knowledge base", "url": "", "snippet": hit.get("text") or ""}
                )

            if not rows:
                logger.warning("No evidence for step %s", step.id)
                step.status = PlanStepStatus.FAILED
                session.commit()
                continue

            session.flush()
            scores = _score_results(session, run, step.sub_question, score_inputs)
            for index, evidence in enumerate(rows):
                evidence.relevance_score = scores.get(index)
            step.status = PlanStepStatus.DONE
            session.commit()
        except Exception:
            logger.exception("Research step %s failed; continuing", step.id)
            session.rollback()
            failed = session.get(PlanStep, step.id)
            if failed is not None:
                failed.status = PlanStepStatus.FAILED
                session.commit()
