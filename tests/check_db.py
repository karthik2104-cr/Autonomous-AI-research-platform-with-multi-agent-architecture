"""
Quick inspection script for planner / evidence / LLM logs.
Run from repo root: python -m tests.check_db
"""
import sqlite3
from pathlib import Path

from tests import ROOT

db_path = ROOT / "data" / "research.db"
if not db_path.exists():
    raise SystemExit(f"No database at {db_path}. Run the app once first.")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()


def show(title, query):
    print(f"\n=== {title} ===")
    try:
        cur.execute(query)
        rows = cur.fetchall()
        if not rows:
            print("(no rows)")
        for row in rows:
            print(dict(row))
    except Exception as e:
        print(f"Error: {e}")


show(
    "Runs",
    "SELECT id, status, substr(user_question,1,80) AS question "
    "FROM research_runs ORDER BY created_at DESC LIMIT 10;",
)
show("Plan Steps", "SELECT sub_question, tool_hint, status FROM plan_steps ORDER BY order_index;")
show("Evidence", "SELECT source_type, source_url, relevance_score FROM evidence LIMIT 10;")
show(
    "LLM Call Logs",
    "SELECT stage, prompt_tokens, completion_tokens, estimated_cost_usd FROM llm_call_logs;",
)

conn.close()
