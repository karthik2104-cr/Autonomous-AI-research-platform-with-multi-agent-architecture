# Decisions

## Why we dropped FastAPI

The previous layout was Streamlit in one process talking over HTTP to FastAPI
in another, both on localhost. For a **single-user local student project** that
HTTP layer did not earn its keep:

- Two processes to start, two virtualenvs, CORS, health polling, and
  `requests.post` wrappers around functions that already lived in Python.
- Live status needed SSE or `st.rerun()` polling because the UI could not see
  the pipeline's local variables.
- Async SQLAlchemy existed only because FastAPI is async — not because the
  workload required it.

The replacement is one Streamlit app calling `pipeline.run_research()` directly.
Progress is `st.status()` / `st.write()` in the same script. Sync SQLAlchemy is
enough.

Interview framing: *I chose the simplest architecture that fit the actual
requirements — one user, local, synchronous is fine — instead of keeping an
API because "real apps have APIs."*

**Tradeoff / evolution path:** if this needed multiple concurrent users, a
mobile client, or any other process that is not Streamlit, FastAPI would come
back. The schema (`ResearchRun`, `PlanStep`, `Evidence`, …) would stay; we
would put an HTTP boundary around the same pipeline function.

## Why we simplified the rest of the infra

This is a student/portfolio project. The interesting work is agents, RAG, and
verification — not operating Postgres, Redis, Celery, Qdrant, and Docker.

| Concern | Now | Production swap |
| --- | --- | --- |
| UI + pipeline | One Streamlit process | FastAPI + workers if multi-user or multi-client |
| Relational state | SQLite (stdlib sqlite3 via SQLAlchemy) | PostgreSQL |
| Background jobs | None — run in the Streamlit script | Celery + Redis |
| Vectors | ChromaDB persistent local folder | Qdrant service |
| LLM | Ollama `qwen3:8b` + `nomic-embed-text` on localhost | Hosted API if you need SLAs |

Interview framing: *I chose the simplest stack that let me focus on the AI
engineering, and I know what I would swap in at production scale.*

## create_all vs Alembic

Tables are created with `Base.metadata.create_all` on first `init_db()`.

- **Pro:** no migration tool, no Docker, wipe `data/research.db` after a model
  change and restart.
- **Con:** you cannot evolve a populated database in place.

Alembic is the natural upgrade once schema changes must be applied without
deleting data. Same models, extra migration files.

SQLite has no native ENUM or JSONB, so enums are stored as strings
(`native_enum=False`) and report JSON uses SQLAlchemy `JSON`. The Python enums
and relationships are the same as before.

## Live updates: st.status vs SSE / polling

The database is still the source of truth for history. During a live run, the
UI does not poll:

1. **WebSockets / SSE** — unnecessary when the pipeline runs in the same
   process as the page.
2. **`st.rerun()` polling** — was required when FastAPI owned the job.
3. **`st.status()` + `st.write()`** — the pipeline calls `on_progress` as each
   stage finishes; Streamlit redraws that container. One script, top to bottom.

## Schema (unchanged intent)

- UUID v4 primary keys.
- Python `enum.Enum` for status and tool fields (string values in SQLite).
- `Report` one-to-one with `ResearchRun`.
- `VerificationResult` one-to-one with `Claim`; many `Citation`s per claim.
- `ResearchRun.analysis_json` holds analysis-stage contradictions/gaps so later
  stages can read them before a Report exists.
- PLANNING / RESEARCHING / ANALYZING / VERIFYING / GENERATING are all real
  LLM+tool stages. `LLMCallLog` records each Ollama call (tokens, latency;
  `estimated_cost_usd` is 0 for local).

## Evidence vs Claim vs Citation

These are three different things on purpose:

| Entity | What it is |
| --- | --- |
| **Evidence** | Raw retrieved material (web snippet or RAG chunk) with a URL/source |
| **Claim** | A synthesized statement the analyst asserts answers (part of) the question |
| **Citation** | The join row linking a Claim to the Evidence that supposedly supports it |

Interview framing: *Evidence is what we found; claims are what we concluded;
citations are the provenance links. Mixing them into one blob makes verification
and “show your work” impossible.*

## Why contradictions/gaps live on `ResearchRun.analysis_json`

Claims/citations have first-class tables because they are queried and joined
often (verification, report tables, UI). Contradictions and gaps are analysis
meta that the report consumes as a list — not entities that need their own
FK graph yet. Storing them as JSON on the run keeps them available between
ANALYZING and GENERATING without inventing extra tables. If they later need
querying/filtering, promote them to tables the same way claims were.

## Why verification is a separate LLM call (LLM-as-judge)

The analysis model already assigns a `confidence` score when it *creates* a
claim. That score is self-assessment from the same context that produced the
claim — the model has an incentive (implicitly) to rate its own synthesis as
reasonable, and it has seen *all* evidence, not just the cited subset.

Verification is a **separate, independent** Ollama call per claim that receives
**only** the claim text and its cited `raw_content`. No planner chat history, no
other evidence, no “you already said this was 0.9 confident.” The model is
asked: *does this evidence actually support this statement, based only on what
is written?*

That pattern is **LLM-as-judge**: one model (or call) proposes; another call
grades the proposal under a narrower rubric. It is not perfect (the judge can
still err), but it is a meaningfully different check than trusting the
producer’s own confidence. Unsupported claims are **kept and flagged**, not
deleted — the report must show what we could not verify.

## Why structured report parts come from the DB, not the LLM

The GENERATING stage asks the LLM only for **narrative** fields (executive
summary, key findings prose, limitations, conclusion). Structured lists —
claims with verification status, contradictions, gaps, and the full source
list with URLs — are assembled in Python from SQLite.

If the LLM regenerated the citation list, it could invent plausible URLs or
drop real ones. Building those sections from `Claim` / `Citation` / `Evidence`
rows makes hallucination of provenance a *code* bug, not a *model* bug.

## Phase 2: DuckDuckGo vs Tavily / SerpAPI

`web_search()` wraps the free `ddgs` package (formerly `duckduckgo-search`).
No API key, fine for a portfolio demo. DDG rate-limits: we retry once, then
return `[]` and mark that **plan step** FAILED without killing the run.

Paid search APIs (Tavily, SerpAPI) are the production swap: more stable
quotas, richer metadata (`published_date`, favicon, score), and fewer empty
result sets. The function signature (`query, max_results → [{title, url,
snippet}]`) is the seam.

## Phase 2: batched relevance scoring

One Ollama call per **plan step**, with all snippets for that step in a single
prompt, returning a score per index via `json_schema`. Versus one call per
search hit: 3–5× fewer round trips and lower token overhead. Scores are
slightly less independent; that is acceptable at this stage.

## Structured output: Ollama json_schema

JSON-in-a-text-blob is easy to get slightly wrong (markdown fences, extra
keys). `call_llm(..., json_schema=...)` passes the schema to Ollama's `format`
parameter so agents return schema-shaped objects. That is the same idea as the
earlier Anthropic forced-tool pattern, on a local model.

**qwen3:8b reliability:** structured calls usually succeed, but open-source
models occasionally return empty/malformed JSON or soft-fail schema fields.
`call_llm` therefore retries structured calls (default 2 extra attempts) with
an explicit “previous reply was invalid JSON” repair hint. Markdown fences are
stripped before `json.loads`. Interview framing: *I treated schema adherence as
a reliability problem, not a one-shot prompt problem.*

## Phase 6: evaluation metrics (honest heuristics)

The evaluation module (`evaluation/run_eval.py`) runs a small hand-built test
set (`evaluation/test_questions.json`) and reports **real measured numbers** —
nothing is fabricated in the UI.

| Metric | What it actually measures | Limitation |
| --- | --- | --- |
| **Retrieval keyword hit** | Any `expected_keywords` substring appears in any Evidence row | Not semantic relevance; misses paraphrases |
| **Supported rate** | % of Claims where verifier returned `supported=true` | Internal consistency, not ground truth |
| **Unsupported rate** | % of Claims where verifier returned false or inconclusive | Same |
| **Response time** | Wall clock (or reused run timestamps) for PLANNING→DONE | Depends on CPU, reuse, and cache |

**Why keyword matching first:** it is free, fast, deterministic, and needs no
extra models or embedding calls — fine for a student starter set you expand
over time.

**Production upgrade path:**

1. **Embedding similarity** — cosine similarity between question embedding and
   each evidence chunk (`nomic-embed-text` already available); threshold e.g.
   > 0.75 counts as relevant.
2. **LLM grader** — separate prompt: “Rate relevance 1–5” per evidence snippet.
3. **Human labels** — gold answers for a fixed eval set; compute precision/recall
   on claims vs human rubric.

Interview framing: *I shipped a measurable baseline and documented what better
eval would look like, instead of pretending keyword hits are semantic quality.*

## DOCX ingestion (Knowledge Base)

**Library:** `python-docx` — pure Python, pip-installable, no LibreOffice headless.

**Table handling:** paragraphs and tables are walked in **document order** via
the DOCX body XML (`w:p` then `w:tbl` as they appear). Table rows are flattened
to `cell | cell` lines and appended inline where the table sits — not moved to
a separate appendix. That keeps resume/report tables near the prose that
introduces them without building a full layout engine.

**Tradeoff:** nested tables, headers/footers, text boxes, and tracked changes are
not extracted. Good enough for notes and reports; a production path would add
`mammoth` or a dedicated converter if complex Word layouts matter.

**Metadata:** same as TXT/PDF — `filename`, `doc_id`, `chunk_id` / `chunk_index`.
No page numbers (DOCX has no fixed pages pre-render).
