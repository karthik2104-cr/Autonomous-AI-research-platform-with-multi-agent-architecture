from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
ENV_FILE = ROOT_DIR / ".env"

load_dotenv(ENV_FILE)
DATA_DIR.mkdir(parents=True, exist_ok=True)
for _subdir in ("chroma", "documents", "reports"):
    (DATA_DIR / _subdir).mkdir(parents=True, exist_ok=True)

# Defaults match the local Ollama models already pulled for this project.
DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_OLLAMA_EMBED_MODEL = "nomic-embed-text"
