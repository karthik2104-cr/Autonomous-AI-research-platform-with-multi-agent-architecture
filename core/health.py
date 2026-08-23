from sqlalchemy import text

from core.db import engine, init_db
from core.llm import ollama_available
from core.vector_store import document_count, get_chroma_client


def sqlite_status() -> tuple[bool, str]:
    try:
        init_db()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def chroma_status() -> tuple[bool, str]:
    try:
        get_chroma_client().heartbeat()
        return True, f"ok ({document_count()} document(s))"
    except Exception as exc:
        return False, str(exc)


def ollama_status() -> tuple[bool, str]:
    return ollama_available()
