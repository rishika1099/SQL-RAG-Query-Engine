# Apollo AI Coach — RAG Internship Assessment

A full-stack natural language to SQL to visualization pipeline for elite sports performance analytics. Built for the Apollo MIS RAG Internship assessment.

**Live Demo:** https://just-ask-coach.netlify.app

**Backend API:** https://apollo-rag-query.fly.dev

---

## What it does

Ask questions in plain English:
- "Who had the highest workload last week?"
- "Show average sprint distance by position"
- "Which athletes have a fatigue score above 40?"
- "Compare match vs training distance for forwards"

The system retrieves relevant KPI definitions via semantic search, generates SQL with Claude, validates and executes it against a real database, and returns a chart + table + follow-up suggestions.

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

### Where LLMs are used

| Step | Model | Purpose |
|------|-------|---------|
| Intent classification | Claude Haiku | Is this a clear query or does it need clarification? |
| SQL generation | Claude Sonnet | NL to SQLite query with schema + KPI context |
| Result verification | Claude Haiku | Does the result actually answer the question? |
| Chart suggestion | Claude Haiku | Best chart type for this data |
| Follow-up generation | Claude Haiku | 3 natural next questions a coach would ask |

### Where RAG is used

KPI definitions (10 metrics) are embedded using `all-MiniLM-L6-v2` and stored in ChromaDB. At query time, the user's question is embedded and the top-3 most semantically similar KPI definitions are retrieved and injected into the SQL generation prompt. This grounds the SQL in Apollo's actual metric definitions rather than letting the model guess.

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

## Local Setup

### Prerequisites
- Python 3.11
- Node.js 18+
- Anthropic API key

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:
```
ANTHROPIC_API_KEY=sk-ant-...
CSV_DIR=./data
CHROMA_PATH=./chroma_store
```

Start the server:
```bash
uvicorn main:app --reload --port 8000
```

On first start the server seeds 4 CSV files into SQLite, loads the embedding model, seeds 10 KPI definitions into ChromaDB, and runs a warmup query.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## Evaluation

Run the benchmark suite (requires backend running):

```bash
cd backend
python eval.py
```

Runs 15 benchmark tests covering aggregation, filtering, comparison, ranking, wellness, and derived metrics.

| Metric | Score |
|--------|-------|
| Pass rate | 12-14/15 (80-93%) |
| Avg latency | ~30s |
| KPI retrieval P@3 | 75-100% |
| Verification correct | ~60% |

---

## Features

- Natural language queries: plain English to SQL via Claude
- KPI semantic retrieval: RAG over 10 metric definitions using ChromaDB
- SQL safety validation: blocks writes, system table access, enforces LIMIT
- Self-verification: Claude checks whether its own result answers the question
- Parallel LLM calls: verify + chart + followups run concurrently (3x faster)
- Voice input: Web Speech API with real-time audio level visualization
- Follow-up suggestions: Claude generates 3 natural next questions
- Feedback logging: thumbs up/down stored in SQLite for eval loop
- CSV export: download any result set
- Dark split-screen UI: query panel left, results right

---

## Project Structure

```
apollo-react/
├── backend/
│   ├── main.py          # FastAPI app, async /query endpoint
│   ├── db.py            # SQLite connection + CSV seeding
│   ├── llm.py           # Claude NL to SQL + chart + followup + intent
│   ├── embeddings.py    # ChromaDB KPI vector store + retrieval
│   ├── validator.py     # SQL AST safety validation
│   ├── verifier.py      # Claude self-verification layer
│   ├── eval.py          # 15-question benchmark suite
│   ├── requirements.txt
│   └── data/
│       ├── athletes.csv
│       ├── sessions.csv
│       ├── gps_metrics.csv
│       └── wellness.csv
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   └── components/
    │       ├── QueryPanel.jsx
    │       ├── ResultPanel.jsx
    │       ├── ChartView.jsx
    │       └── DataTable.jsx
    ├── public/favicon.svg
    ├── index.html
    └── package.json
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

Returns thumbs up/down counts for monitoring.

---

## Assessment Coverage

| Task | Implementation |
|------|---------------|
| Task 1: Voice pipeline | Intent classifier + RAG + SQL + verify + chart pipeline |
| Task 2: SQL generation | SQL_SYSTEM prompt with 12 proven query examples |
| Task 3: KPI retrieval | ChromaDB + cosine similarity in embeddings.py |
| Task 4: Visualizations | Recharts bar/line/scatter in ChartView.jsx |
| Task 5: Reliable NL querying | Schema abstraction + KPI store + validation layers |
| Task 6: Evaluation framework | 15-question benchmark suite in eval.py |

---

## Written Assessment

See [ASSESSMENT.md](./ASSESSMENT.md) for detailed answers to all 6 tasks.