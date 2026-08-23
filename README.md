# Autonomous AI Research & Intelligence Platform

A local, multi-agent research assistant that takes a natural-language question,
plans sub-queries, gathers evidence from the web and an uploaded knowledge base,
extracts cited claims, verifies each claim with an LLM-as-judge, and produces a
structured report with Markdown and PDF export. An evaluation module measures
retrieval and verification quality against a hand-built test set. Everything
runs in a single Streamlit process on your machine — no Docker, no FastAPI, no
cloud API keys required.

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         Streamlit UI (app.py)       │
                    │  New Research · KB · History · Eval │
                    └─────────────────┬───────────────────┘
                                      │ direct Python calls
                                      ▼
                    ┌─────────────────────────────────────┐
                    │           pipeline.py               │
                    │  PLAN → RESEARCH → ANALYZE →        │
                    │  VERIFY → GENERATE REPORT           │
                    └──────┬──────────┬──────────┬────────┘
                           │          │          │
              ┌────────────▼──┐  ┌────▼────┐  ┌──▼──────────────┐
              │ agents/       │  │ tools/  │  │ core/           │
              │ planner       │  │ ddgs    │  │ db (SQLite)     │
              │ research      │  │ web     │  │ llm (Ollama)    │
              │ analyzer      │  │ search  │  │ vector_store    │
              │ verifier      │  └─────────┘  │ (ChromaDB)      │
              │ report_gen    │               └─────────────────┘
              └───────────────┘
                           │
              Ollama: qwen3:8b (chat) + nomic-embed-text (embeddings)
              Storage: data/research.db + data/chroma/
```

## Features

- **Planning** — LLM breaks a research question into ordered sub-questions with tool hints
- **Web search** — DuckDuckGo (`ddgs`) retrieves live web evidence with URLs
- **RAG / Knowledge Base** — upload `.txt`, `.md`, `.pdf`, or `.docx`; chunk, embed, and retrieve via ChromaDB
- **Analysis** — extract claims, citations, contradictions, and gaps from evidence
- **Verification** — independent LLM-as-judge per claim (supported / unsupported / inconclusive)
- **Report generation** — DB-structured sections + LLM narrative; view in Run History
- **Export** — download reports as Markdown or PDF (`fpdf2`, no headless browser)
- **Evaluation** — run a hand-built test set; keyword retrieval hit rate + verifier consistency metrics

## Tech stack

| Layer | Choice | Notes |
| --- | --- | --- |
| UI | Streamlit | Single process, direct function calls |
| Orchestration | `pipeline.py` | Sync, in-process |
| LLM | Ollama `qwen3:8b` | Local chat + JSON schema |
| Embeddings | Ollama `nomic-embed-text` | Explicit embed → Chroma |
| Vector store | ChromaDB (embedded) | `data/chroma/` persistent folder |
| Database | SQLite + SQLAlchemy (sync) | `data/research.db` |
| Web search | `ddgs` | Free DuckDuckGo wrapper |
| PDF export | `fpdf2` | Pure Python, pip-only |
| PDF ingest | `pypdf` | KB upload text extraction |
| DOCX ingest | `python-docx` | KB upload text + table extraction |

## Setup (clean clone)

**1. Install Ollama** and pull the models:

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

**2. Python environment:**

```bash
git clone <repo-url>
cd "<repo-directory>"

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
```

**3. Configure environment:**

```bash
copy .env.example .env
# Unix: cp .env.example .env
```

**4. Run the app:**

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501). The Home page shows health checks for SQLite, ChromaDB, and Ollama.

All dependencies are **pip-installable** — no wkhtmltopdf, Docker, or system services beyond Ollama.

## How to use

| Page | What it does |
| --- | --- |
| **New Research** | Submit a question; watch the pipeline progress; view the report when done |
| **Knowledge Base** | Upload documents for RAG; test retrieval queries |
| **Run History** | Browse past runs, inspect plan/evidence/claims, download Markdown or PDF |
| **Evaluation** | Run the test question set; view retrieval and verifier metrics |
| **Settings** | Confirm Ollama model names and connectivity |

## Tests & smoke check

From repo root (after activating venv):

```bash
python -m tests.smoke_test          # non-destructive; safe with demo data
python -m tests.test_pdf_export     # PDF from demo run 9906d319...
python -m tests.test_kb             # resets Chroma, re-ingests testdata/
python -m tests.test_kb_docx        # DOCX ingest + retrieval test
python -m tests.test_pipeline       # full pipeline (slow; needs Ollama + network)
python -m evaluation.run_eval --limit 3
python -m tests.check_db            # inspect SQLite rows
```

## Known limitations

- **Evaluation retrieval metric** — keyword substring match on evidence, not semantic similarity
- **Verifier supported rate** — measures internal consistency (LLM judge vs cited evidence), not ground truth
- **CPU inference** — full pipeline can take 10–20+ minutes per fresh question on CPU
- **Single-user** — no authentication, no concurrent job queue
- **Schema migrations** — `create_all` + lightweight `ALTER TABLE`; no Alembic yet

See `DECISIONS.md` for engineering rationale and upgrade paths.

## Future improvements

- Embedding-based evaluation (cosine similarity) and/or LLM grader scoring 1–5
- Expand the evaluation test set with human-labeled gold answers
- Multi-turn query rewriting and conversational research sessions
- Postgres + job queue (Celery/Redis) if multi-user or API access is needed
- FastAPI layer if a separate client (mobile, external frontend) is required

## Project structure

```
app.py                      Streamlit home + health checks
pages/                      Streamlit multipage UI
  1_New_Research.py
  2_Knowledge_Base.py
  3_Run_History.py
  4_Settings.py
  5_Evaluation.py
pipeline.py                 run_research() orchestration
ui.py                       Shared report / plan rendering + download buttons
core/
  config.py                 Paths, .env loading, data dirs
  db.py                     Sync SQLAlchemy + SQLite
  models.py                 ResearchRun, Evidence, Claim, Report, …
  llm.py                    Ollama chat + embeddings wrapper
  vector_store.py           ChromaDB persistent client
  ingest.py                 File parse → chunk → embed → store
  health.py                 SQLite / Chroma / Ollama status
agents/
  planner.py                PLANNING stage
  research_agent.py         RESEARCH (web + RAG)
  analyzer.py               ANALYZING
  verifier.py               VERIFYING (LLM-as-judge)
  report_generator.py       GENERATING + report_to_markdown()
tools/
  web_search.py             DuckDuckGo wrapper
utils/
  pdf_export.py             content_json → PDF bytes
evaluation/
  test_questions.json       Hand-built eval set (expand over time)
  metrics.py                Keyword + verifier metrics
  run_eval.py               CLI runner → results.json
tests/                      Dev / smoke tests (see above)
testdata/
  aurora_notes.txt          Sample KB document for eval + tests
data/                       Runtime data (gitignored except .gitkeep)
  chroma/                   ChromaDB vectors
  documents/                Reserved for uploaded file copies
  reports/                  Generated PDF exports
  research.db               SQLite state
DECISIONS.md                  Architecture and trade-off notes
.env.example                  Ollama model + timeout defaults
requirements.txt
```
