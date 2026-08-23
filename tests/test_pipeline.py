"""End-to-end research pipeline smoke test (calls Ollama + ddgs + SQLite)."""
from __future__ import annotations

import sqlite3

import tests  # noqa: F401 — repo root on sys.path

from core.config import DATA_DIR
from pipeline import run_research, run_to_dict


def main() -> None:
    question = (
        "What are the main benefits of using SQLite for local desktop applications?"
    )
    print("=== RUN RESEARCH ===")
    print("question:", question)

    def progress(msg: str) -> None:
        print(f"[progress] {msg}")

    run = run_research(question, on_progress=progress)
    payload = run_to_dict(run)
    print("\nstatus:", payload["status"])
    print("error:", payload.get("error_message"))
    print("run_id:", payload["id"])

    print("\n=== PLAN SUB-QUESTIONS ===")
    for step in payload.get("plan_steps") or []:
        print(f"  [{step['order_index']}] ({step['status']}) {step['sub_question']}")
        for ev in step.get("evidence") or []:
            print(
                f"      evidence type={ev.get('source_type')} "
                f"score={ev.get('relevance_score')} url={ev.get('source_url')}"
            )
            print(f"      snippet={(ev.get('raw_content') or '')[:160]!r}")

    assert payload["status"] == "DONE", payload
    assert payload.get("plan_steps"), "Expected planner to create plan steps"
    web_urls = [
        ev.get("source_url")
        for step in payload["plan_steps"]
        for ev in step.get("evidence") or []
        if ev.get("source_type") == "web" and ev.get("source_url")
    ]
    print("\n=== WEB URLS ===")
    for url in web_urls[:15]:
        print(" ", url)
    assert web_urls, "Expected at least one web evidence URL from ddgs"

    db = DATA_DIR / "research.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS n FROM evidence WHERE plan_step_id IN "
        "(SELECT id FROM plan_steps WHERE research_run_id = ?)",
        (payload["id"].replace("-", ""),),
    )
    n = cur.fetchone()["n"]
    if n == 0:
        cur.execute(
            "SELECT COUNT(*) AS n FROM evidence e "
            "JOIN plan_steps p ON e.plan_step_id = p.id "
            "WHERE CAST(p.research_run_id AS TEXT) LIKE ?",
            (payload["id"][:8] + "%",),
        )
        n = cur.fetchone()["n"]
    if n == 0:
        cur.execute("SELECT COUNT(*) AS n FROM evidence")
        n = cur.fetchone()["n"]
    print("\nSQLite evidence rows (approx):", n)
    cur.execute(
        "SELECT source_type, source_url, substr(raw_content,1,120) AS snippet "
        "FROM evidence ORDER BY retrieved_at DESC LIMIT 8"
    )
    for row in cur.fetchall():
        print(dict(row))
    conn.close()
    assert n > 0, "Expected Evidence rows in SQLite"
    print("\nPIPELINE_E2E_OK")


if __name__ == "__main__":
    main()
