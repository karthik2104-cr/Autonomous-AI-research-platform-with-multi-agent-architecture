import os
from pathlib import Path

import streamlit as st

from core.config import DEFAULT_OLLAMA_EMBED_MODEL, DEFAULT_OLLAMA_MODEL, ENV_FILE
from core.llm import ollama_available, ollama_embed_model, ollama_model
from ui.theme import page_intro


def _write_env_value(path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    found = False
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}=") and not line.lstrip().startswith("#"):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


page_intro(
    "Settings",
    "Configure which **Ollama models** this app uses for chat and embeddings. Changes are "
    "saved to `.env` on disk. Models must already be pulled locally (`ollama pull …`) before "
    "research or knowledge-base ingest will work.",
)

st.header("Ollama connection")
ok, detail = ollama_available()
if ok:
    st.success("Ollama is reachable and required models are available.")
    st.caption(detail)
else:
    st.error("Ollama is not ready.")
    st.caption(detail)
    st.markdown(
        f"Install [Ollama](https://ollama.com), start it, then run:\n\n"
        f"```\nollama pull {DEFAULT_OLLAMA_MODEL}\nollama pull {DEFAULT_OLLAMA_EMBED_MODEL}\n```"
    )

st.divider()
st.header("Model names")
st.caption(
    "Chat model powers planning, analysis, verification, and report narrative. "
    "Embedding model powers knowledge-base retrieval."
)
chat_model = st.text_input("Chat model (`OLLAMA_MODEL`)", value=ollama_model())
embed_model = st.text_input("Embedding model (`OLLAMA_EMBED_MODEL`)", value=ollama_embed_model())
if st.button("Save model settings", type="primary"):
    chosen_chat = chat_model.strip() or DEFAULT_OLLAMA_MODEL
    chosen_embed = embed_model.strip() or DEFAULT_OLLAMA_EMBED_MODEL
    os.environ["OLLAMA_MODEL"] = chosen_chat
    os.environ["OLLAMA_EMBED_MODEL"] = chosen_embed
    _write_env_value(ENV_FILE, "OLLAMA_MODEL", chosen_chat)
    _write_env_value(ENV_FILE, "OLLAMA_EMBED_MODEL", chosen_embed)
    st.success(f"Saved to `{ENV_FILE.name}` — chat=`{chosen_chat}`, embed=`{chosen_embed}`.")
    st.rerun()

st.divider()
st.header("Data locations")
st.markdown(
    f"""
| Store | Path | Contents |
| --- | --- | --- |
| SQLite | `data/research.db` | Runs, evidence, claims, reports |
| ChromaDB | `data/chroma/` | Embedded knowledge-base chunks |
| Environment | `{ENV_FILE.name}` | Model names and timeouts |
"""
)
