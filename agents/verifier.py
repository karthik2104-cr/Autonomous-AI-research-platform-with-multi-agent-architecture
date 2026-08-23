from __future__ import annotations

import logging
import re
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.llm import LLMError, LLMTimeoutError, call_llm
from core.models import Claim, Citation, Evidence, ResearchRun, ResearchRunStatus, VerificationResult

logger = logging.getLogger(__name__)

VERIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["supported", "reasoning", "confidence"],
}

VERIFIER_SYSTEM = """You are a strict fact-checker (LLM-as-judge).
You are given ONE claim and ONLY the evidence snippets cited for it.
Decide whether that evidence actually supports the claim.
Rules:
- Answer strictly based on what is written in the evidence.
- Do not use outside knowledge.
- Do not assume facts that are not stated.
- If the evidence is related but does not actually support the claim, mark supported=false.
Return JSON only."""

MAX_EVIDENCE_CHARS = 2000


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _sanitize_evidence(text: str, max_chars: int = MAX_EVIDENCE_CHARS) -> str:
    cleaned = (text or "").replace("\x00", " ")
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_chars:
        return cleaned[: max_chars - 3] + "..."
    return cleaned


def _log(msg: str) -> None:
    print(msg, flush=True)
    logger.info(msg)


def verify_claims(session: Session, run: ResearchRun, on_progress=None) -> list[VerificationResult]:
    """VERIFYING: independent per-claim LLM-as-judge calls. Keep unsupported claims.

    Per-claim failures/timeouts produce is_supported=None (inconclusive) and do not
    abort the rest of the run.
    """
    claims = list(
        session.scalars(
            select(Claim)
            .where(Claim.research_run_id == run.id)
            .options(
                selectinload(Claim.citations).selectinload(Citation.evidence),
                selectinload(Claim.verification_result),
            )
        ).all()
    )
    if not claims:
        raise LLMError("No claims to verify.")

    results: list[VerificationResult] = []
    for index, claim in enumerate(claims, start=1):
        claim_id = str(claim.id)
        if on_progress:
            on_progress(f"Verifying claim {index}/{len(claims)} (id={claim_id[:8]})...")

        # Replace any prior verification when re-running.
        if claim.verification_result is not None:
            session.delete(claim.verification_result)
            session.flush()

        evidence_blocks: list[str] = []
        total_chars = 0
        for citation in claim.citations or []:
            ev: Evidence | None = citation.evidence
            if ev is None:
                continue
            content = _sanitize_evidence(ev.raw_content or "", MAX_EVIDENCE_CHARS)
            total_chars += len(content)
            evidence_blocks.append(
                f"- id={ev.id}\n  url={ev.source_url or '(none)'}\n  content={content}"
            )

        if not evidence_blocks:
            vr = VerificationResult(
                claim_id=claim.id,
                is_supported=False,
                reasoning="No cited evidence was linked to this claim, so it cannot be verified.",
            )
            session.add(vr)
            results.append(vr)
            session.commit()
            _log(f"[verify] claim {index}/{len(claims)} id={claim_id} SKIP no evidence")
            continue

        user = (
            f"Claim:\n{claim.statement}\n\n"
            f"Cited evidence only:\n" + "\n".join(evidence_blocks)
        )
        _log(
            f"[verify] START claim {index}/{len(claims)} id={claim_id} "
            f"evidence_blocks={len(evidence_blocks)} prompt_chars={len(user)} "
            f"evidence_chars={total_chars}"
        )
        started = perf_counter()
        try:
            parsed = call_llm(
                VERIFIER_SYSTEM,
                user,
                json_schema=VERIFY_SCHEMA,
                session=session,
                research_run_id=run.id,
                stage=ResearchRunStatus.VERIFYING.value,
                max_retries=1,  # 1 initial + 1 retry max
                timeout_seconds=90,
                num_predict=400,
            )
            elapsed = perf_counter() - started
            if not isinstance(parsed, dict):
                raise LLMError("Verifier did not return a JSON object.")

            supported = parsed.get("supported")
            if not isinstance(supported, bool):
                supported = None
            reasoning = str(parsed.get("reasoning") or "").strip() or "(no reasoning)"
            try:
                conf = _clamp(float(parsed.get("confidence", 0.0)))
                reasoning = f"{reasoning}\n[judge_confidence={conf:.2f}]"
            except (TypeError, ValueError):
                pass

            vr = VerificationResult(
                claim_id=claim.id,
                is_supported=supported,
                reasoning=reasoning,
            )
            session.add(vr)
            results.append(vr)
            session.commit()
            label = (
                "supported"
                if supported is True
                else "unsupported"
                if supported is False
                else "uncertain"
            )
            _log(
                f"[verify] DONE  claim {index}/{len(claims)} id={claim_id} "
                f"result={label} elapsed={elapsed:.1f}s"
            )
        except (LLMTimeoutError, LLMError, Exception) as exc:
            elapsed = perf_counter() - started
            # Never abort the whole VERIFYING stage for one claim.
            session.rollback()
            # Re-bind claim after rollback
            claim = session.get(Claim, claim.id) or claim
            if claim.verification_result is not None:
                session.delete(claim.verification_result)
                session.flush()
            vr = VerificationResult(
                claim_id=claim.id,
                is_supported=None,
                reasoning=f"verification failed: {exc}",
            )
            session.add(vr)
            results.append(vr)
            session.commit()
            _log(
                f"[verify] FAIL  claim {index}/{len(claims)} id={claim_id} "
                f"elapsed={elapsed:.1f}s error={exc}"
            )

    logger.info("Run %s verified %s claim(s)", run.id, len(results))
    return results
