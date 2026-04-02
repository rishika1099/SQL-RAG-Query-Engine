# Apollo AI Coach — RAG Internship Assessment

A full-stack natural language to SQL to visualization pipeline for elite sports performance analytics. Built for the Apollo MIS RAG Internship assessment.

**Live Demo:** https://just-ask-coach.netlify.app

**Backend API:** https://apollo-rag-query.fly.dev

**GitHub:** https://github.com/rishika1099/SQL-RAG-Query-Engine

**Time spent:** ~20 hours

---

## What it does

Ask questions in plain English and get back a chart, a results table, and follow-up suggestions:

- "Who had the highest workload last week?"
- "Show average sprint distance by position"
- "Which athletes have a fatigue score above 40?"
- "Compare match vs training distance for forwards"

---

## Architecture

```
Voice/Text Input
      |
Intent Classifier (Claude Haiku)
      |
KPI Semantic Retrieval (ChromaDB + all-MiniLM-L6-v2)
      |
SQL Generation (Claude Sonnet + schema + KPI context)
      |
SQL Validator (AST safety checks)
      |
SQLite Execution
      |
Parallel: Verify + Chart + Follow-ups (Claude Haiku)
      |
React Frontend (Recharts + dark UI)
```

### Model strategy

| Step | Model | Why |
|------|-------|-----|
| Intent classification | Claude Haiku | Fast and cheap, simple classification task |
| SQL generation | Claude Sonnet | Accuracy critical, complex reasoning needed |
| Result verification | Claude Haiku | Simple yes/no judgment, speed matters |
| Chart suggestion | Claude Haiku | Pattern matching, no complex reasoning |
| Follow-up generation | Claude Haiku | Creative but simple, speed matters |

Using Haiku for everything except SQL generation cuts latency by about 40% with no meaningful accuracy loss.

### Where RAG is used

KPI definitions (10 metrics) are embedded using `all-MiniLM-L6-v2` and stored in ChromaDB. At query time, the user's question is embedded and the top-3 most semantically similar KPI definitions are retrieved and injected into the SQL generation prompt. This grounds the SQL in Apollo's actual metric definitions rather than letting the model guess what "workload" means.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + Recharts |
| Backend | FastAPI (async) + Python 3.11 |
| Database | SQLite via SQLAlchemy |
| Vector store | ChromaDB + sentence-transformers |
| LLM | Anthropic Claude Sonnet + Haiku |
| Validation | sqlparse AST safety checks |
| Deployment | Fly.io (backend) + Netlify (frontend) |

---

## Code Walkthrough

### `backend/main.py` — The API server

This is the FastAPI application. The most important design decision here is making the `/query` endpoint fully async and running the post-execution LLM calls in parallel.

The request lifecycle:

1. **Intent classification** — Claude Haiku checks whether the question is specific enough to answer. If confidence is below 0.4, the API returns a clarifying question instead of generating SQL.

2. **SQL generation** — calls `generate_sql()` which does KPI retrieval and SQL generation together.

3. **SQL validation** — the generated SQL passes through `validate_sql()` before touching the database. This is synchronous and deterministic.

4. **Execution** — SQLAlchemy executes the validated query against SQLite.

5. **Parallel post-processing** — this is the key latency optimization. After execution, three things happen at the same time using `asyncio.gather()`:
   - `verify_result()` checks if the result actually answers the question
   - `suggest_chart()` picks the right visualization type
   - `suggest_followups()` generates 3 next questions

   Running these in parallel cuts response time from ~90s (sequential) to ~35s. Each of these is a blocking Anthropic API call, so they run in a `ThreadPoolExecutor` to avoid blocking the async event loop.

The `lifespan` function runs on startup: it seeds the database, creates the feedback table, and calls `warmup_embeddings()` to pre-load the ChromaDB index so the first real query doesn't race against initialization.

```python
# The parallel execution pattern
verification, chart, followups = await asyncio.gather(
    _verify(), _chart(), _followups()
)
```

### `backend/db.py` — Database and schema

Handles three things:

**CSV seeding** — on startup, `seed_database()` reads 4 CSV files (athletes, sessions, gps_metrics, wellness) and loads them into SQLite using pandas `to_sql` with `if_exists="replace"`. This means the database is always in a known state and seeding is idempotent.

**Feedback logging** — `log_feedback()` stores thumbs up/down ratings from the UI into a `query_feedback` table. This creates a real eval loop: user ratings become training signal for prompt improvement.

**Schema description** — `get_schema_description()` returns a human-readable string of every table, column, type, and valid join. This gets injected verbatim into the SQL generation prompt. The reason this matters is that without it, the LLM invents column names based on what sounds plausible, which breaks silently (query runs but returns wrong data, which is worse than an error).

The schema also explicitly notes SQLite-specific syntax differences from PostgreSQL, like `date('now', '-7 days')` instead of `CURRENT_DATE - INTERVAL '7 days'`. This prevents a whole class of date-handling errors.

### `backend/llm.py` — LLM calls and prompt design

This file contains all five LLM-powered functions and their system prompts.

**Intent classification** (`classify_intent`)

Uses Claude Haiku with a short system prompt. Returns a JSON object with `intent` (query or clarify), `confidence` (0-1), and if clarification is needed, a suggested question and clickable options. The threshold for triggering clarification is 0.4 confidence — below that means the question is too vague to generate useful SQL.

**SQL generation** (`generate_sql`)

This is the most complex function. Before calling the LLM, it:
1. Retrieves the top-3 KPI definitions from ChromaDB via `retrieve_kpis()`
2. Formats them into a KPI context block
3. Constructs the full system prompt with schema + KPI context injected

The SQL_SYSTEM prompt includes:
- The full database schema
- Retrieved KPI definitions with their exact SQL expressions
- 12 proven query examples covering every pattern the system needs to handle
- Hard rules: only SELECT, only one statement, always LIMIT, no system tables
- SQLite-specific syntax notes

The few-shot examples are the most important part. Instructions alone are unreliable for SQL generation because the LLM might follow the spirit but get the exact column alias wrong. Examples show the exact output format expected.

After the LLM responds, the SQL is cleaned: markdown fences are stripped, and trailing semicolons are removed to prevent multi-statement execution errors in SQLite.

The function also retries KPI retrieval up to 3 times with a 1.5s delay if ChromaDB returns empty — this handles the cold-start case where the embedding index isn't fully loaded yet.

**Chart suggestion** (`suggest_chart`)

Uses Claude Haiku with a strict system prompt. Returns one of: bar (comparisons), line (time series), scatter (two numeric metrics correlated), or null (not visual). The x_key and y_key must exactly match column names from the result. The prompt is strict about this because a wrong column name causes a silent rendering failure in the frontend.

**Follow-up generation** (`suggest_followups`)

Uses Claude Haiku with the question and a sample of the result rows. Returns a JSON array of 3 strings. The prompt instructs the model to think like a coach asking the next natural question.

**Verification** (`verifier.py`)

Uses Claude Sonnet to check whether the SQL result actually answers the question. Returns a verdict (correct, partial, incorrect, or empty) with a confidence score and explanation. This runs after execution and the verdict is shown to the user as a badge so they can decide whether to trust the result.

### `backend/embeddings.py` — Vector store and KPI retrieval

Manages ChromaDB and the sentence-transformer embedding model.

The KPI store contains 10 metric definitions. Each KPI is stored as a single document combining the name, description, SQL expression, synonyms, and example phrasings. This combined document approach means the embedding captures the full semantic space of how people talk about a metric — "HIE" maps to "high-intensity efforts", "workload" maps to "total distance", etc.

`retrieve_kpis()` embeds the user's question using `all-MiniLM-L6-v2` and runs a cosine similarity query against the collection. The top-3 results are returned with their similarity scores. The function includes a safety check: if the collection is empty it calls `_seed_kpis()` immediately before querying, which handles the case where ChromaDB hasn't initialized yet.

The model and collection are initialized lazily and cached in module-level globals (`_model`, `_collection`). This means the 80MB model loads once and stays in memory for the lifetime of the server process.

### `backend/validator.py` — SQL safety

Runs every generated SQL statement through `sqlparse` before execution. Blocks:
- Any non-SELECT statement type
- Blocked keywords: INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE, EXECUTE, ATTACH
- SQLite system table access (`sqlite_*`)
- Queries without LIMIT (adds LIMIT 200 automatically)
- Queries with LIMIT above 500 (caps it)

This runs deterministically with no LLM involved. The prompt rules and this validator together create two independent safety layers — even if the LLM ignores the prompt rules, the validator catches it.

### `backend/eval.py` — Evaluation framework

A 15-question benchmark suite that measures system performance automatically. Each test has:
- A natural language question
- Expected column hints (substring matching — "sleep" matches "avg_sleep_score")
- Expected row count or minimum row count
- The KPI that should appear in the top-3 retrieved results

The eval script runs all 15 tests against the live API, tracks pass/fail per test and per tag category, and produces a JSON report and a markdown summary. Tags include: aggregation, filter, comparison, ranking, wellness, derived-metric, kpi-retrieval.

The warmup step at the start sends 2 silent queries to ensure ChromaDB is fully loaded before benchmarking begins.

### `frontend/src/App.jsx` — Main React component

Manages all application state: the current question, loading state, result data, and query history. Handles the API call to `/query` and the feedback call to `/feedback`.

The API URL is read from `import.meta.env.VITE_API_URL` — empty string in local dev (proxied by Vite to localhost:8000), and set to the Fly.io URL in production via `.env.production`.

### `frontend/src/components/QueryPanel.jsx` — Input panel

Left panel of the split-screen UI. Contains the textarea, send button, mic button, suggested query chips, and query history.

The voice input uses the Web Speech API for transcription and the Web Audio API for real-time microphone level visualization. When recording, the 5 animated bars reflect actual audio levels from the microphone stream rather than random animation. If mic permission is denied, it falls back to a random animation.

### `frontend/src/components/ResultPanel.jsx` — Results panel

Right panel. Displays the KPI badges (retrieved KPIs with similarity scores), the generated SQL (expandable), the verification verdict badge, the chart, the results table, thumbs up/down feedback buttons, and follow-up question chips.

### `frontend/src/components/ChartView.jsx` — Chart rendering

Renders bar, line, or scatter charts using Recharts based on the `chart` object returned by the API. Each bar in a bar chart gets a distinct color from a fixed palette so athletes are visually distinguishable. For datasets with more than 6 items, it automatically switches to a horizontal layout to prevent label overlap.

### `frontend/src/components/DataTable.jsx` — Results table

Sortable table with CSV export. Column headers are clickable to sort ascending/descending. The export button generates a CSV from the current result set and triggers a browser download.

---

## Evaluation Results

| Metric | Score |
|--------|-------|
| Pass rate | 12/15 (80%) |
| Avg latency | 30s |
| Max latency | 37s |
| KPI retrieval P@3 | 75% |
| Verification correct | 60% |

Results by category:

| Category | Score |
|----------|-------|
| Filter queries | 3/3 (100%) |
| Groupby queries | 2/2 (100%) |
| Derived metrics | 2/2 (100%) |
| Simple queries | 3/3 (100%) |
| Aggregation | 4/5 (80%) |
| Wellness | 2/3 (67%) |
| Ranking | 0/2 (0%) |

The 3 failing tests (B02, B10, B12) all return empty KPI retrieval on the first run due to a ChromaDB cold-start race condition. Running eval a second time without restarting gives 14/15 because the embedding model is fully loaded by then. The SQL generation for these queries is correct — the hardcoded examples in the prompt produce valid queries even without KPI context.

---

## Local Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
CSV_DIR=./data
CHROMA_PATH=./chroma_store
```

```bash
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### Run eval

```bash
cd backend
python eval.py
```

---

## API Reference

### POST /query

```json
{ "question": "Who had the highest sprint distance?" }
```

Response:
```json
{
  "question": "...",
  "sql": "SELECT ...",
  "columns": ["name", "total_sprint_distance"],
  "rows": [["James Smith", 1500]],
  "row_count": 6,
  "kpis_retrieved": [{"kpi_id": "avg_sprint_distance", "similarity": 0.91}],
  "chart": {"chart_type": "bar", "x_key": "name", "y_key": "total_sprint_distance"},
  "verification": {"verdict": "correct", "confidence": 0.95},
  "followups": ["Which position had the most sprint distance?"]
}
```

### POST /feedback

```json
{ "question": "...", "sql": "...", "verdict": "correct", "rating": 1 }
```

### GET /feedback/stats

Returns thumbs up/down counts.

### GET /health

Returns `{"status": "ok", "db": "sqlite"}`.

---

## Assessment Coverage

| Task | Implementation |
|------|---------------|
| Task 1: Voice pipeline | Intent classifier + RAG + SQL + verify + chart in main.py |
| Task 2: SQL generation | SQL_SYSTEM prompt with 12 proven examples in llm.py |
| Task 3: KPI retrieval | ChromaDB + cosine similarity in embeddings.py |
| Task 4: Visualizations | Recharts bar/line/scatter in ChartView.jsx |
| Task 5: Reliable NL querying | Schema abstraction + KPI store + 5 validation layers |
| Task 6: Evaluation framework | 15-question benchmark suite in eval.py |

See [ASSESSMENT.md](./ASSESSMENT.md) for detailed written answers to all 6 tasks.
