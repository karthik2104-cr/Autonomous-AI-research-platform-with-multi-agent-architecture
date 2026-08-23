"""
Standalone verifier sanity checks (LLM-as-judge).

1) Negative: claim that contradicts serverless/file-based evidence → expect supported=false
2) Positive: claim clearly backed by the same evidence → expect supported=true

Does not touch the research pipeline DB.
"""
from __future__ import annotations

import json
from time import perf_counter

import tests  # noqa: F401 — repo root on sys.path

from agents.verifier import VERIFY_SCHEMA, VERIFIER_SYSTEM, _sanitize_evidence
from core.llm import call_llm

EVIDENCE_SERVERLESS = _sanitize_evidence(
    "There are advantages and disadvantages to being serverless. The main advantage "
    "is that there is no separate server process to install, setup, configure, "
    "initialize, manage, or troubleshoot. SQLite does not need to be installed "
    "before it is used. There is no setup procedure. There is no server process "
    "that needs to be started, stopped, or configured."
)
EVIDENCE_FILE = _sanitize_evidence(
    "A complete database with multiple tables, indices, triggers, views, etc. "
    "is stored as a single ordinary disk file. The SQLite file format is "
    "cross-platform and can be freely copied between 32-bit and 64-bit systems."
)


def _judge(claim: str, evidence_blocks: list[str]) -> dict:
    user = f"Claim:\n{claim}\n\nCited evidence only:\n" + "\n".join(evidence_blocks)
    print("--- PROMPT (user) ---")
    print(user)
    print("--- END PROMPT ---")
    started = perf_counter()
    parsed = call_llm(
        VERIFIER_SYSTEM,
        user,
        json_schema=VERIFY_SCHEMA,
        max_retries=1,
        timeout_seconds=90,
        num_predict=400,
    )
    elapsed = perf_counter() - started
    print(f"[timing] {elapsed:.1f}s")
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected dict, got {type(parsed)}: {parsed!r}")
    return parsed


def main() -> None:
    evidence = [
        f"- id=ev-serverless\n  url=https://sqlite.org/different.html\n  content={EVIDENCE_SERVERLESS}",
        f"- id=ev-file\n  url=https://sqlite.org/features.html\n  content={EVIDENCE_FILE}",
    ]

    print("=== NEGATIVE CASE (expect supported=false) ===")
    negative_claim = "SQLite databases require a dedicated server process to run."
    negative = _judge(negative_claim, evidence)
    print("RAW JSON:")
    print(json.dumps(negative, indent=2))

    print("\n=== POSITIVE CASE (expect supported=true) ===")
    positive_claim = (
        "SQLite does not require a separate server process; a complete database "
        "can be stored as a single ordinary disk file."
    )
    positive = _judge(positive_claim, evidence)
    print("RAW JSON:")
    print(json.dumps(positive, indent=2))

    print("\n=== SUMMARY ===")
    print("negative.supported =", negative.get("supported"))
    print("positive.supported =", positive.get("supported"))

    assert negative.get("supported") is False, (
        f"Negative case should be supported=false, got: {negative}"
    )
    assert positive.get("supported") is True, (
        f"Positive case should be supported=true, got: {positive}"
    )
    print("VERIFIER_SANITY_OK")


if __name__ == "__main__":
    main()
