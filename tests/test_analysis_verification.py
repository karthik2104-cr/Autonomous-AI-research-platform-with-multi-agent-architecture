"""
Re-run VERIFYING → GENERATING on an existing research run that already has
Claim rows (skips slow planning/web/analysis).

Default run id: 9906d319-fc39-4f1f-8762-d54c886eaa8b

Pass --full to also re-run ANALYZING from Evidence.
"""
from __future__ import annotations

import json
import sys
from uuid import UUID

import tests  # noqa: F401 — repo root on sys.path

from agents.report_generator import report_to_markdown
from pipeline import continue_post_research, continue_verify_and_report, load_run, run_to_dict

DEFAULT_RUN_ID = "9906d319-fc39-4f1f-8762-d54c886eaa8b"


def main() -> None:
    args = [a for a in sys.argv[1:] if a]
    full = "--full" in args
    args = [a for a in args if a != "--full"]
    run_id = args[0] if args else DEFAULT_RUN_ID

    print("=== CONTINUE VERIFY + REPORT ===" if not full else "=== CONTINUE POST-RESEARCH (full) ===")
    print("run_id:", run_id)

    existing = load_run(UUID(run_id))
    if existing is None:
        raise SystemExit(f"Run not found: {run_id}")
    payload = run_to_dict(existing)
    evidence_n = sum(len(s.get("evidence") or []) for s in payload.get("plan_steps") or [])
    claims_n = len(payload.get("claims") or [])
    print(f"existing status={payload['status']} evidence_rows={evidence_n} claims={claims_n}")

    if full:
        if evidence_n == 0:
            raise SystemExit("No evidence on this run; cannot analyze.")
        runner = continue_post_research
    else:
        if claims_n == 0:
            raise SystemExit("No claims on this run; re-run with --full to analyze first.")
        runner = continue_verify_and_report

    def progress(msg: str) -> None:
        print(f"[progress] {msg}", flush=True)

    run = runner(run_id, on_progress=progress)
    out = run_to_dict(run)
    print("\n=== FINAL STATUS ===")
    print(out["status"], out.get("error_message"))

    print("\n=== CLAIMS ===")
    for i, claim in enumerate(out.get("claims") or [], start=1):
        print(f"\n--- claim {i} ---")
        print("id:", claim.get("id"))
        print("statement:", claim.get("statement"))
        print("confidence:", claim.get("confidence_score"))
        print("verification:", claim.get("verification_status"))
        print("reasoning:", claim.get("verification_reasoning"))
        print("citations:", claim.get("citations"))

    analysis = out.get("analysis_json") or {}
    print("\n=== CONTRADICTIONS ===")
    print(json.dumps(analysis.get("contradictions") or [], indent=2))
    print("\n=== GAPS ===")
    print(json.dumps(analysis.get("gaps") or [], indent=2))

    report = out.get("report") or {}
    print("\n=== REPORT (executive_summary) ===")
    print(report.get("executive_summary"))
    print("\n=== REPORT (key_findings) ===")
    for item in report.get("key_findings") or []:
        print("-", item)
    print("\n=== REPORT (conclusion) ===")
    print(report.get("conclusion"))
    print("\n=== REPORT (limitations) ===")
    for item in report.get("limitations") or []:
        print("-", item)
    print("\n=== REPORT markdown preview (first 2500 chars) ===")
    if report:
        md = report_to_markdown(report)
        print(md[:2500])
        print("\n... total markdown chars:", len(md))

    assert out["status"] == "DONE", out
    assert out.get("claims"), "expected claims"
    assert out.get("report"), "expected report"
    for claim in out["claims"]:
        assert claim.get("verification_status") in {"supported", "unsupported", "uncertain"}
    print("\nANALYSIS_VERIFY_REPORT_OK")


if __name__ == "__main__":
    main()
