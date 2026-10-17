import html
import os
from pathlib import Path

import streamlit as st

from core.config import DEFAULT_OLLAMA_EMBED_MODEL, DEFAULT_OLLAMA_MODEL, ENV_FILE
from core.llm import ollama_available, ollama_embed_model, ollama_model
from ui.theme import page_header, section_label, status_badge_html


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


page_header(
    "Settings",
    "Configure Ollama chat and embedding models. Changes are saved to .env. "
    "Models must already be pulled locally before research or knowledge-base ingest will work.",
)

section_label("Ollama connection")
ok, detail = ollama_available()
st.markdown(
    f'<div class="ri-card"><div class="ri-card-title">Connection status</div>'
    f'<div class="ri-card-body">{status_badge_html("done" if ok else "failed")} '
    f"{html.escape(detail)}</div></div>",
    unsafe_allow_html=True,
)
if not ok:
    st.markdown(
        f"Install [Ollama](https://ollama.com), start it, then run:\n\n"
        f"```\nollama pull {DEFAULT_OLLAMA_MODEL}\nollama pull {DEFAULT_OLLAMA_EMBED_MODEL}\n```"
    )

st.divider()
section_label("Chat model")
st.caption("Powers planning, analysis, verification, and report narrative.")
chat_model = st.text_input("OLLAMA_MODEL", value=ollama_model())

st.divider()
section_label("Embedding model")
st.caption("Powers knowledge-base chunk embeddings and retrieval queries.")
embed_model = st.text_input("OLLAMA_EMBED_MODEL", value=ollama_embed_model())

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
section_label("Data locations")
st.markdown(
    f"""
| Store | Path | Contents |
| --- | --- | --- |
| SQLite | `data/research.db` | Runs, evidence, claims, reports |
| ChromaDB | `data/chroma/` | Embedded knowledge-base chunks |
| Environment | `{ENV_FILE.name}` | Model names and timeouts |
"""
)
st.caption("Secrets are not displayed. Only model names and paths are configured here.")
