from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from agents.analyzer import analyze_evidence
from agents.planner import generate_plan as _generate_plan
from agents.report_generator import generate_report
from agents.research_agent import gather_evidence
from agents.verifier import verify_claims
from core.db import SessionLocal, init_db
from core.llm import LLMError
from core.models import (
    Claim,
    Citation,
    PlanStep,
    ResearchRun,
    ResearchRunStatus,
)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]


def _enum_value(value) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def run_to_dict(run: ResearchRun) -> dict:
    """Detach a run (plan/evidence/claims/report) into plain dicts for Streamlit."""
    analysis = run.analysis_json if isinstance(run.analysis_json, dict) else {}
    report = None
    if run.report is not None and isinstance(run.report.content_json, dict):
        report = dict(run.report.content_json)

    claims = []
    for claim in run.claims or []:
        vr = claim.verification_result
        if vr is None:
            v_status = None
            v_reason = None
            v_supported = None
        else:
            v_supported = vr.is_supported
            if vr.is_supported is True:
                v_status = "supported"
            elif vr.is_supported is False:
                v_status = "unsupported"
            else:
                v_status = "uncertain"
            v_reason = vr.reasoning
        claims.append(
            {
                "id": str(claim.id),
                "statement": claim.statement,
                "confidence_score": claim.confidence_score,
                "verification_status": v_status,
                "is_supported": v_supported,
                "verification_reasoning": v_reason,
                "citations": [
                    {
                        "evidence_id": str(c.evidence_id),
                        "source_url": c.evidence.source_url if c.evidence else None,
                    }
                    for c in (claim.citations or [])
                ],
            }
        )

    return {
        "id": str(run.id),
        "user_question": run.user_question,
        "status": _enum_value(run.status),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "error_message": run.error_message,
        "analysis_json": analysis,
        "claims": claims,
        "report": report,
        "plan_steps": [
            {
                "id": str(step.id),
                "sub_question": step.sub_question,
                "tool_hint": _enum_value(step.tool_hint),
                "status": _enum_value(step.status),
                "order_index": step.order_index,
                "evidence": [
                    {
                        "id": str(item.id),
                        "source_url": item.source_url,
                        "source_type": _enum_value(item.source_type),
                        "raw_content": item.raw_content,
                        "relevance_score": item.relevance_score,
                    }
                    for item in (step.evidence or [])
                ],
            }
            for step in (run.plan_steps or [])
        ],
    }


def _set_status(session, run: ResearchRun, status: ResearchRunStatus) -> None:
    run.status = status
    run.updated_at = datetime.now(timezone.utc)
    run.error_message = None
    session.commit()


def _fail_run(session, run_id: UUID, message: str) -> ResearchRun | None:
    failed = session.get(ResearchRun, run_id)
    if failed is None:
        return None
    failed.status = ResearchRunStatus.FAILED
    failed.error_message = message
    failed.updated_at = datetime.now(timezone.utc)
    session.commit()
    return failed


def create_research_run(question: str) -> ResearchRun:
    init_db()
    session = SessionLocal()
    try:
        run = ResearchRun(user_question=question.strip(), status=ResearchRunStatus.PENDING)
        session.add(run)
        session.commit()
        session.refresh(run)
        return run
    finally:
        session.close()


def generate_plan(run: ResearchRun) -> list[PlanStep]:
    init_db()
    session = SessionLocal()
    try:
        db_run = session.get(ResearchRun, run.id)
        if db_run is None:
            raise RuntimeError(f"Research run {run.id} was not found.")
        return _generate_plan(session, db_run)
    finally:
        session.close()


def load_run(run_id: UUID | str) -> ResearchRun | None:
    init_db()
    session = SessionLocal()
    try:
        return session.scalars(
            select(ResearchRun)
            .options(
                selectinload(ResearchRun.plan_steps).selectinload(PlanStep.evidence),
                selectinload(ResearchRun.claims)
                .selectinload(Claim.citations)
                .selectinload(Citation.evidence),
                selectinload(ResearchRun.claims).selectinload(Claim.verification_result),
                selectinload(ResearchRun.report),
            )
            .where(ResearchRun.id == UUID(str(run_id)))
        ).one_or_none()
    finally:
        session.close()


def list_runs(page: int = 1, page_size: int = 20) -> tuple[list[ResearchRun], int]:
    init_db()
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    session = SessionLocal()
    try:
        total = int(session.scalar(select(func.count()).select_from(ResearchRun)) or 0)
        items = list(
            session.scalars(
                select(ResearchRun)
                .order_by(ResearchRun.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total
    finally:
        session.close()


def _run_analysis_verification_report(
    session,
    run: ResearchRun,
    note: ProgressFn,
) -> ResearchRun:
    run_id = run.id

    note("Analyzing evidence into claims...")
    _set_status(session, run, ResearchRunStatus.ANALYZING)
    analysis = analyze_evidence(session, run)
    note(
        f"Created {analysis.get('claim_count', 0)} claim(s); "
        f"{len(analysis.get('contradictions') or [])} contradiction(s); "
        f"{len(analysis.get('gaps') or [])} gap(s)"
    )

    run = session.get(ResearchRun, run_id)
    if run is None:
        raise RuntimeError("Research run disappeared during analysis.")

    note("Verifying claims (independent LLM-as-judge)...")
    _set_status(session, run, ResearchRunStatus.VERIFYING)
    results = verify_claims(session, run, on_progress=note)
    supported = sum(1 for r in results if r.is_supported is True)
    unsupported = sum(1 for r in results if r.is_supported is False)
    note(f"Verified {len(results)} claim(s): {supported} supported, {unsupported} unsupported")

    run = session.get(ResearchRun, run_id)
    if run is None:
        raise RuntimeError("Research run disappeared during verification.")

    note("Generating report...")
    _set_status(session, run, ResearchRunStatus.GENERATING)
    generate_report(session, run)
    note("Report saved")

    run = session.get(ResearchRun, run_id)
    if run is None:
        raise RuntimeError("Research run disappeared during report generation.")
    _set_status(session, run, ResearchRunStatus.DONE)
    loaded = load_run(run_id)
    if loaded is None:
        raise RuntimeError("Research run disappeared after completion.")
    return loaded


def continue_post_research(
    run_id: UUID | str,
    on_progress: ProgressFn | None = None,
) -> ResearchRun:
    """Run ANALYZING → VERIFYING → GENERATING on an existing run that already has evidence."""
    init_db()
    note = on_progress or (lambda _msg: None)
    session = SessionLocal()
    try:
        run = session.scalars(
            select(ResearchRun)
            .options(selectinload(ResearchRun.plan_steps).selectinload(PlanStep.evidence))
            .where(ResearchRun.id == UUID(str(run_id)))
        ).one_or_none()
        if run is None:
            raise RuntimeError(f"Research run {run_id} not found.")
        evidence_count = sum(len(step.evidence or []) for step in run.plan_steps)
        if evidence_count == 0:
            raise LLMError("This run has no evidence rows; cannot analyze.")
        return _run_analysis_verification_report(session, run, note)
    except (LLMError, Exception) as exc:
        logger.exception("Post-research stages failed")
        session.rollback()
        failed = _fail_run(session, UUID(str(run_id)), str(exc))
        if failed is not None:
            loaded = load_run(failed.id)
            if loaded is not None:
                return loaded
        raise
    finally:
        session.close()


def continue_verify_and_report(
    run_id: UUID | str,
    on_progress: ProgressFn | None = None,
) -> ResearchRun:
    """Run VERIFYING → GENERATING on a run that already has Claim rows."""
    init_db()
    note = on_progress or (lambda _msg: None)
    session = SessionLocal()
    try:
        run = session.scalars(
            select(ResearchRun)
            .options(
                selectinload(ResearchRun.claims),
                selectinload(ResearchRun.plan_steps).selectinload(PlanStep.evidence),
            )
            .where(ResearchRun.id == UUID(str(run_id)))
        ).one_or_none()
        if run is None:
            raise RuntimeError(f"Research run {run_id} not found.")
        if not run.claims:
            raise LLMError("This run has no claims; run analysis first.")

        run_id_uuid = run.id
        note("Verifying claims (independent LLM-as-judge)...")
        _set_status(session, run, ResearchRunStatus.VERIFYING)
        results = verify_claims(session, run, on_progress=note)
        supported = sum(1 for r in results if r.is_supported is True)
        unsupported = sum(1 for r in results if r.is_supported is False)
        inconclusive = sum(1 for r in results if r.is_supported is None)
        note(
            f"Verified {len(results)} claim(s): {supported} supported, "
            f"{unsupported} unsupported, {inconclusive} inconclusive"
        )

        run = session.get(ResearchRun, run_id_uuid)
        if run is None:
            raise RuntimeError("Research run disappeared during verification.")

        note("Generating report...")
        _set_status(session, run, ResearchRunStatus.GENERATING)
        generate_report(session, run)
        note("Report saved")

        run = session.get(ResearchRun, run_id_uuid)
        if run is None:
            raise RuntimeError("Research run disappeared during report generation.")
        _set_status(session, run, ResearchRunStatus.DONE)
        loaded = load_run(run_id_uuid)
        if loaded is None:
            raise RuntimeError("Research run disappeared after completion.")
        return loaded
    except (LLMError, Exception) as exc:
        logger.exception("Verify/report stages failed")
        session.rollback()
        failed = _fail_run(session, UUID(str(run_id)), str(exc))
        if failed is not None:
            loaded = load_run(failed.id)
            if loaded is not None:
                return loaded
        raise
    finally:
        session.close()


def run_research(question: str, on_progress: ProgressFn | None = None) -> ResearchRun:
    """Full pipeline: PLANNING → RESEARCHING → ANALYZING → VERIFYING → GENERATING → DONE."""
    init_db()
    note = on_progress or (lambda _msg: None)
    session = SessionLocal()
    run: ResearchRun | None = None
    try:
        note("Creating research run...")
        run = ResearchRun(user_question=question.strip(), status=ResearchRunStatus.PENDING)
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

        note("Planning...")
        _set_status(session, run, ResearchRunStatus.PLANNING)
        steps = _generate_plan(session, run)
        note(f"Created {len(steps)} sub-questions")

        note("Researching (web + knowledge base)...")
        _set_status(session, run, ResearchRunStatus.RESEARCHING)
        gather_evidence(session, run, on_progress=note)

        run = session.get(ResearchRun, run_id)
        if run is None:
            raise RuntimeError("Research run disappeared during pipeline.")

        return _run_analysis_verification_report(session, run, note)
    except LLMError as exc:
        logger.error("Research failed: %s", exc)
        session.rollback()
        if run is not None:
            _fail_run(session, run.id, str(exc))
            loaded = load_run(run.id)
            if loaded is not None:
                return loaded
        raise
    except Exception as exc:
        logger.exception("Research failed")
        session.rollback()
        if run is not None:
            _fail_run(session, run.id, str(exc))
            loaded = load_run(run.id)
            if loaded is not None:
                return loaded
        raise
    finally:
        session.close()
