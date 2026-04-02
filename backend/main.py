import os
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from db import seed_database, engine, create_feedback_table, log_feedback, get_schema_description
from llm import classify_intent, generate_sql, suggest_chart, suggest_followups
from embeddings import warmup as warmup_embeddings
from validator import validate_sql, ValidationError
from verifier import verify_result
from dotenv import load_dotenv

load_dotenv()

# Thread pool for running blocking LLM calls concurrently
executor = ThreadPoolExecutor(max_workers=4)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        seed_database()
        create_feedback_table()
        warmup_embeddings()  # Pre-warm ChromaDB + embedding model
    except Exception as e:
        print(f"[warn] startup error: {e}")
    yield


app = FastAPI(title="Apollo AI Coach", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows Netlify + local dev
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ──────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    kpis_retrieved: list[dict] = []
    chart: Optional[dict] = None
    verification: Optional[dict] = None
    followups: list[str] = []
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None
    clarifying_options: list[str] = []
    error: Optional[str] = None

class FeedbackRequest(BaseModel):
    question: str
    sql: str
    verdict: str
    rating: int
    comment: str = ""


# ── Helpers ──────────────────────────────────────────────────────────

async def run_in_thread(fn, *args):
    """Run a blocking function in thread pool without blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, fn, *args)


# ── Routes ──────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "db": "sqlite"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # 1. Intent classification (fast, skip if obvious query)
    try:
        intent = await run_in_thread(classify_intent, question)
        if intent.get("intent") == "clarify" and intent.get("confidence", 1.0) < 0.4:
            return QueryResponse(
                question=question, sql="", columns=[], rows=[], row_count=0,
                needs_clarification=True,
                clarifying_question=intent.get("clarifying_question"),
                clarifying_options=intent.get("clarifying_options", []),
            )
    except Exception:
        pass  # If intent classification fails, proceed with query

    # 2. Generate SQL with RAG (includes KPI retrieval)
    try:
        raw_sql, kpis = await run_in_thread(generate_sql, question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    # 3. Validate SQL
    try:
        safe_sql = validate_sql(raw_sql)
    except ValidationError as e:
        return QueryResponse(
            question=question, sql=raw_sql, columns=[], rows=[], row_count=0,
            kpis_retrieved=kpis, error=f"SQL validation failed: {e}"
        )

    # 4. Execute query
    try:
        with engine.connect() as conn:
            result = conn.execute(text(safe_sql))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]
    except Exception as e:
        return QueryResponse(
            question=question, sql=safe_sql, columns=[], rows=[], row_count=0,
            kpis_retrieved=kpis, error=f"Query error: {e}"
        )

    # 5. Run verify + chart + followups IN PARALLEL (big latency win)
    async def _verify():
        try:
            return await run_in_thread(verify_result, question, safe_sql, columns, rows)
        except Exception:
            return {"verdict": "unknown", "confidence": 0.0, "explanation": "", "issues": []}

    async def _chart():
        try:
            return await run_in_thread(suggest_chart, question, columns, rows)
        except Exception:
            return None

    async def _followups():
        try:
            return await run_in_thread(suggest_followups, question, columns, rows)
        except Exception:
            return []

    verification, chart, followups = await asyncio.gather(
        _verify(), _chart(), _followups()
    )

    return QueryResponse(
        question=question, sql=safe_sql, columns=columns, rows=rows,
        row_count=len(rows), kpis_retrieved=kpis, chart=chart,
        verification=verification, followups=followups,
    )


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    try:
        log_feedback(req.question, req.sql, req.verdict, req.rating, req.comment)
        return {"status": "logged"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/schema")
def schema():
    return {"schema": get_schema_description()}


@app.get("/feedback/stats")
def feedback_stats():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) as thumbs_up,
                   SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END) as thumbs_down
            FROM query_feedback
        """))
        row = result.fetchone()
        return dict(zip(result.keys(), row)) if row else {}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)