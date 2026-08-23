from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from core.llm import LLMError, call_llm
from core.models import PlanStep, ResearchRun, ResearchRunStatus, PlanStepStatus, ToolHint

logger = logging.getLogger(__name__)

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "sub_questions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {"sub_question": {"type": "string"}},
                "required": ["sub_question"],
            },
        }
    },
    "required": ["sub_questions"],
}

PLANNER_SYSTEM = """You are a research planner.
Break the user's question into 3-5 focused sub-questions that a web search can answer.
Each sub-question should be self-contained and short enough to use as a search query.
Return JSON only. Do not answer the research question yourself."""


def _extract_sub_questions(payload: dict) -> list[str]:
    raw = payload.get("sub_questions") or payload.get("steps") or []
    questions: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            questions.append(item.strip())
        elif isinstance(item, dict):
            text = str(item.get("sub_question") or item.get("question") or "").strip()
            if text:
                questions.append(text)
    return questions[:5]


def generate_plan(session: Session, run: ResearchRun) -> list[PlanStep]:
    parsed = call_llm(
        PLANNER_SYSTEM,
        run.user_question,
        json_schema=PLAN_SCHEMA,
        session=session,
        research_run_id=run.id,
        stage=ResearchRunStatus.PLANNING.value,
    )
    if not isinstance(parsed, dict):
        raise LLMError("Planner did not return a JSON object.")
    questions = _extract_sub_questions(parsed)
    if not questions:
        raise LLMError("Planner returned an empty plan.")

    steps: list[PlanStep] = []
    for index, question in enumerate(questions):
        step = PlanStep(
            research_run_id=run.id,
            sub_question=question,
            tool_hint=ToolHint.WEB_SEARCH,
            status=PlanStepStatus.PENDING,
            order_index=index,
        )
        session.add(step)
        steps.append(step)
    session.commit()
    logger.info("Research run %s planned %s step(s)", run.id, len(steps))
    return steps
