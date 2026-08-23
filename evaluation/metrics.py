"""Evaluation helpers: keyword relevance, verifier-based citation metrics."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def keyword_in_text(keyword: str, text: str) -> bool:
    return keyword.lower() in (text or "").lower()


def retrieval_keyword_hit(
    evidence_rows: list[dict[str, Any]],
    expected_keywords: list[str],
) -> dict[str, Any]:
    """Basic retrieval relevance: did any Evidence snippet contain an expected keyword?

    This is a cheap substring heuristic — NOT semantic similarity. A production
    eval would use embedding cosine similarity (question vs evidence) or an LLM
    grader scoring relevance 1-5.
    """
    if not expected_keywords:
        return {
            "hit": False,
            "matched_keywords": [],
            "matched_evidence_ids": [],
            "method": "keyword_substring",
            "note": "No expected_keywords configured.",
        }
    if not evidence_rows:
        return {
            "hit": False,
            "matched_keywords": [],
            "matched_evidence_ids": [],
            "method": "keyword_substring",
            "note": "No evidence rows to check.",
        }

    matched_keywords: set[str] = set()
    matched_ids: set[str] = set()
    for ev in evidence_rows:
        blob = " ".join(
            [
                str(ev.get("raw_content") or ""),
                str(ev.get("source_url") or ""),
                str(ev.get("source_type") or ""),
            ]
        )
        for kw in expected_keywords:
            if keyword_in_text(kw, blob):
                matched_keywords.add(kw)
                matched_ids.add(str(ev.get("id") or ""))

    return {
        "hit": len(matched_keywords) > 0,
        "matched_keywords": sorted(matched_keywords),
        "matched_evidence_ids": sorted(x for x in matched_ids if x),
        "method": "keyword_substring",
        "note": "True if any expected keyword appears in any evidence snippet (case-insensitive).",
    }


def domain_in_evidence(evidence_rows: list[dict[str, Any]], domains: list[str]) -> dict[str, Any]:
    """Optional check: did any evidence URL contain an expected domain?"""
    if not domains:
        return {"hit": None, "matched_domains": [], "note": "No expected_source_domains configured."}
    matched: set[str] = set()
    for ev in evidence_rows:
        url = str(ev.get("source_url") or "")
        if not url.startswith("http"):
            continue
        host = urlparse(url).netloc.lower()
        for domain in domains:
            if domain.lower() in host:
                matched.add(domain)
    return {
        "hit": len(matched) > 0 if domains else None,
        "matched_domains": sorted(matched),
        "note": "Optional domain substring check on evidence URLs.",
    }


def citation_verifier_metrics(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Citation / internal-consistency metrics from the LLM-as-judge verifier.

    - supported_rate: % of claims where verifier returned supported=true
      (proxy for internal consistency — NOT ground-truth correctness)
    - unsupported_rate: % where supported=false OR inconclusive (null/uncertain)
    """
    total = len(claims)
    if total == 0:
        return {
            "claim_count": 0,
            "supported_count": 0,
            "unsupported_count": 0,
            "inconclusive_count": 0,
            "supported_rate": None,
            "unsupported_rate": None,
            "method": "verifier_llm_judge",
            "note": "No claims to score.",
        }

    supported = sum(1 for c in claims if c.get("verification_status") == "supported")
    unsupported = sum(1 for c in claims if c.get("verification_status") == "unsupported")
    inconclusive = sum(1 for c in claims if c.get("verification_status") == "uncertain")

    return {
        "claim_count": total,
        "supported_count": supported,
        "unsupported_count": unsupported,
        "inconclusive_count": inconclusive,
        "supported_rate": round(supported / total, 4),
        "unsupported_rate": round((unsupported + inconclusive) / total, 4),
        "method": "verifier_llm_judge",
        "note": (
            "supported_rate = verifier said evidence supports claim (internal consistency, "
            "not ground truth). unsupported_rate = false + inconclusive claims."
        ),
    }


def all_evidence_from_run(run_dict: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in run_dict.get("plan_steps") or []:
        rows.extend(step.get("evidence") or [])
    return rows
