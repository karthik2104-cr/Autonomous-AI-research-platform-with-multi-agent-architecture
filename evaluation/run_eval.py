"""
Run the hand-built evaluation set against the full research pipeline.

Metrics (honest heuristics — see evaluation/metrics.py and DECISIONS.md):
  - retrieval_keyword_hit: substring match on evidence (NOT semantic)
  - supported_rate / unsupported_rate: verifier LLM-as-judge (internal consistency)
  - response_time_seconds: wall clock for pipeline run (or reused run metadata)

Usage:
  python -m evaluation.run_eval
  python -m evaluation.run_eval --limit 3
  python -m evaluation.run_eval --no-reuse   # always run fresh
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import UUID

from sqlalchemy import select

from core.db import SessionLocal, init_db
from core.ingest import ingest_file
from core.models import ResearchRun, ResearchRunStatus
from evaluation.metrics import (
    all_evidence_from_run,
    citation_verifier_metrics,
    domain_in_evidence,
    retrieval_keyword_hit,
)
from pipeline import load_run, run_research, run_to_dict

ROOT = Path(__file__).resolve().parent
TEST_SET = ROOT / "test_questions.json"
RESULTS_PATH = ROOT / "results.json"
KB_FIXTURE = ROOT.parent / "testdata" / "aurora_notes.txt"


def _load_test_set() -> list[dict]:
    raw = json.loads(TEST_SET.read_text(encoding="utf-8"))
    return list(raw.get("questions") or [])


def _ensure_kb_fixture() -> None:
    """Ingest aurora_notes.txt so KB-targeted eval questions can hit RAG."""
    if not KB_FIXTURE.exists():
        print(f"[eval] KB fixture missing: {KB_FIXTURE}", flush=True)
        return
    try:
        result = ingest_file(KB_FIXTURE)
        print(
            f"[eval] KB fixture ingested: {result['filename']} ({result['chunks']} chunk(s))",
            flush=True,
        )
    except Exception as exc:
        print(f"[eval] KB ingest skipped/failed: {exc}", flush=True)


def _find_reusable_run(question: str) -> ResearchRun | None:
    """Reuse a completed run with the exact same question text (dev speedup)."""
    init_db()
    session = SessionLocal()
    try:
        return session.scalars(
            select(ResearchRun)
            .where(
                ResearchRun.user_question == question.strip(),
                ResearchRun.status == ResearchRunStatus.DONE,
            )
            .order_by(ResearchRun.updated_at.desc())
        ).first()
    finally:
        session.close()


def _format_row(cols: list[str], widths: list[int]) -> str:
    return " | ".join(c.ljust(w)[:w] for c, w in zip(cols, widths))


def _print_summary_table(results: dict) -> None:
    per_q = results.get("per_question") or []
    if not per_q:
        print("(no results)")
        return

    headers = ["id", "retrieval", "supp%", "unsupp%", "time_s", "status"]
    widths = [22, 8, 7, 8, 8, 8]
    print(_format_row(headers, widths))
    print("-" * (sum(widths) + 3 * (len(widths) - 1)))
    for row in per_q:
        rel = "yes" if row.get("retrieval_hit") else "no"
        sup = row.get("supported_rate")
        uns = row.get("unsupported_rate")
        print(
            _format_row(
                [
                    str(row.get("id", ""))[:22],
                    rel,
                    f"{sup:.0%}" if isinstance(sup, (int, float)) else "n/a",
                    f"{uns:.0%}" if isinstance(uns, (int, float)) else "n/a",
                    "reuse" if row.get("reused_run") else f"{row.get('response_time_seconds', 0):.0f}",
                    str(row.get("run_status", ""))[:8],
                ],
                widths,
            )
        )

    agg = results.get("aggregate") or {}
    print("\nAggregate:")
    print(f"  questions_evaluated: {agg.get('questions_evaluated')}")
    print(f"  retrieval_hit_rate:  {agg.get('retrieval_hit_rate')}")
    print(f"  avg_supported_rate:  {agg.get('avg_supported_rate')}")
    print(f"  avg_unsupported_rate:{agg.get('avg_unsupported_rate')}")
    print(f"  avg_response_time_s: {agg.get('avg_response_time_seconds')}"
          + (" (all reused — run fresh with --no-reuse to measure)" if agg.get('all_runs_reused') else ""))


def evaluate_one(
    item: dict,
    *,
    reuse: bool = True,
    on_progress=None,
) -> dict:
    qid = str(item.get("id") or "unknown")
    question = str(item.get("question") or "").strip()
    keywords = list(item.get("expected_keywords") or [])
    domains = list(item.get("expected_source_domains") or [])

    note = on_progress or (lambda _msg: None)
    reused = False
    elapsed = 0.0

    existing = _find_reusable_run(question) if reuse else None
    if existing is not None:
        note(f"[{qid}] Reusing DONE run {existing.id}")
        run_dict = run_to_dict(load_run(existing.id) or existing)
        reused = True
        if existing.created_at and existing.updated_at:
            elapsed = max(
                0.0,
                (existing.updated_at - existing.created_at).total_seconds(),
            )
    else:
        note(f"[{qid}] Running full pipeline...")
        started = perf_counter()
        run = run_research(question, on_progress=note)
        elapsed = perf_counter() - started
        run_dict = run_to_dict(run)

    evidence = all_evidence_from_run(run_dict)
    retrieval = retrieval_keyword_hit(evidence, keywords)
    domain_check = domain_in_evidence(evidence, domains)
    verifier = citation_verifier_metrics(run_dict.get("claims") or [])

    return {
        "id": qid,
        "question": question,
        "run_id": run_dict.get("id"),
        "run_status": run_dict.get("status"),
        "reused_run": reused,
        "response_time_seconds": round(elapsed, 1),
        "retrieval_hit": retrieval["hit"],
        "retrieval_matched_keywords": retrieval["matched_keywords"],
        "retrieval_method": retrieval["method"],
        "domain_hit": domain_check.get("hit"),
        "domain_matched": domain_check.get("matched_domains"),
        "claim_count": verifier.get("claim_count"),
        "supported_rate": verifier.get("supported_rate"),
        "unsupported_rate": verifier.get("unsupported_rate"),
        "supported_count": verifier.get("supported_count"),
        "unsupported_count": verifier.get("unsupported_count"),
        "inconclusive_count": verifier.get("inconclusive_count"),
        "metrics_notes": {
            "retrieval": retrieval.get("note"),
            "verifier": verifier.get("note"),
            "domain": domain_check.get("note"),
        },
        "error_message": run_dict.get("error_message"),
    }


def run_evaluation(
    *,
    limit: int | None = None,
    reuse: bool = True,
    on_progress=None,
) -> dict:
    _ensure_kb_fixture()
    items = _load_test_set()
    if limit is not None:
        items = items[: max(0, limit)]

    started_at = datetime.now(timezone.utc).isoformat()
    per_question: list[dict] = []

    for item in items:
        try:
            per_question.append(evaluate_one(item, reuse=reuse, on_progress=on_progress))
        except Exception as exc:
            per_question.append(
                {
                    "id": item.get("id"),
                    "question": item.get("question"),
                    "run_status": "ERROR",
                    "error_message": str(exc),
                    "retrieval_hit": False,
                    "supported_rate": None,
                    "unsupported_rate": None,
                    "response_time_seconds": 0,
                }
            )

    done_rows = [r for r in per_question if r.get("run_status") == "DONE"]
    retrieval_hits = sum(1 for r in per_question if r.get("retrieval_hit"))
    sup_rates = [r["supported_rate"] for r in done_rows if r.get("supported_rate") is not None]
    uns_rates = [r["unsupported_rate"] for r in done_rows if r.get("unsupported_rate") is not None]
    # Average wall-clock only for freshly executed runs (reused runs use DB timestamps).
    fresh_times = [
        r["response_time_seconds"]
        for r in per_question
        if r.get("response_time_seconds") and not r.get("reused_run")
    ]
    reused_only = all(r.get("reused_run") for r in done_rows) if done_rows else False

    aggregate = {
        "questions_evaluated": len(per_question),
        "questions_done": len(done_rows),
        "questions_failed": len(per_question) - len(done_rows),
        "retrieval_hit_rate": round(retrieval_hits / len(per_question), 4) if per_question else None,
        "avg_supported_rate": round(sum(sup_rates) / len(sup_rates), 4) if sup_rates else None,
        "avg_unsupported_rate": round(sum(uns_rates) / len(uns_rates), 4) if uns_rates else None,
        "avg_response_time_seconds": round(sum(fresh_times) / len(fresh_times), 1) if fresh_times else None,
        "all_runs_reused": reused_only,
    }

    payload = {
        "generated_at": started_at,
        "test_set": str(TEST_SET.name),
        "reuse_runs": reuse,
        "per_question": per_question,
        "aggregate": aggregate,
        "disclaimer": (
            "Retrieval uses keyword substring matching (basic heuristic). "
            "Verifier rates measure internal consistency, not ground-truth correctness."
        ),
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_results() -> dict | None:
    if not RESULTS_PATH.exists():
        return None
    try:
        return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 6 evaluation set.")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only first N questions.")
    parser.add_argument(
        "--no-reuse",
        action="store_true",
        help="Always run the full pipeline (do not reuse matching DONE runs).",
    )
    args = parser.parse_args()

    def progress(msg: str) -> None:
        print(msg, flush=True)

    print("=== EVALUATION RUN ===")
    print(f"test_set: {TEST_SET}")
    print(f"limit: {args.limit or 'all'}")
    print(f"reuse: {not args.no_reuse}")
    print()

    results = run_evaluation(limit=args.limit, reuse=not args.no_reuse, on_progress=progress)
    print("\n=== SUMMARY TABLE ===")
    _print_summary_table(results)
    print(f"\nSaved: {RESULTS_PATH}")
    print("EVAL_OK")


if __name__ == "__main__":
    main()
