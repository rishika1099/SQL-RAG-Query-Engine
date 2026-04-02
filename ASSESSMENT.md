# Assessment Writeup — Apollo MIS RAG Internship

---

## Task 1: Voice Query Pipeline

The core idea here is that a coach should not have to think about SQL or data structures at all. They should be able to ask a question the same way they would ask a colleague, and get a useful answer back.

Here is how the pipeline works:

**Voice to Text**

The browser's Web Speech API handles transcription. It is not perfect (background noise in a gym is a real problem) but it is fast, requires no server infrastructure, and works well enough for short analytical questions. For a production system I would move to Whisper on the server side, which handles noise better and supports more languages.

**Text to Structured Intent**

Rather than sending the raw transcript straight to SQL generation, I first run it through an intent classifier using Claude Haiku, which is cheap and fast. This step checks whether the question is actually answerable with the available data, extracts what metric the user is asking about, and decides whether a clarifying question is needed. The reason this matters is that "show me performance" means nothing without knowing which metric (fatigue, sprint distance, workload?) and generating SQL for an ambiguous question produces garbage.

**Intent to KPI Retrieval (the RAG part)**

Once we know what metric the user wants, I embed their question using `all-MiniLM-L6-v2` (a small, fast local embedding model) and do a cosine similarity search against a ChromaDB vector store containing all 10 KPI definitions. The top-3 most relevant KPI definitions get injected into the SQL generation prompt. This grounds the SQL in Apollo's actual metric definitions rather than letting the model guess what "workload" means.

**KPI Context to SQL**

Claude Sonnet generates the SQL query, but it is not working from scratch. It has the schema, the retrieved KPI definitions including their exact SQL expressions, and a library of proven query examples. The prompt also includes hard rules: no writes, no system tables, always LIMIT, one statement only. Even with all that, I run the output through an AST validator before it touches the database.

**SQL to Response**

After execution, three things happen in parallel rather than sequentially, which cuts latency by about 3x. A verification call checks whether the result actually answers the question, a chart suggestion call picks the right visualization type, and a follow-up generator produces three natural next questions a coach might ask. All three use Haiku rather than Sonnet since they are simpler tasks.

**Where LLMs are used:** intent classification, SQL generation, result verification, chart selection, follow-up generation.

**Where embeddings are used:** turning the user's question into a vector to retrieve the right KPI definitions.

**Where deterministic logic is used:** date arithmetic (converting "last week" to exact dates), SQL AST validation (pure rule-based, no LLM involved), row count enforcement, and LIMIT injection.

**Failure handling:**
- Low confidence on intent: return a clarifying question with clickable options rather than guessing
- SQL validation fails: return the error with the raw SQL visible so the user understands what went wrong
- Query returns 0 rows: explain why (date filter probably too narrow) and suggest an expanded range
- Verification verdict is "incorrect": show a warning badge so the user knows to double-check

---

## Task 2: SQL Generation

Here are the three queries from the assessment, written for SQLite.

**"Which athletes had the highest workload last week?"**

Workload is total distance covered. "Last week" is handled deterministically before the prompt, converted to `date('now', '-7 days')` rather than asking the LLM to figure out what "last week" means.

```sql
SELECT a.name, a.position, a.team,
       ROUND(SUM(g.total_distance), 0) AS total_workload,
       COUNT(s.session_id) AS sessions
FROM sessions s
JOIN athletes a ON s.athlete_id = a.athlete_id
JOIN gps_metrics g ON s.session_id = g.session_id
WHERE s.session_date >= date('now', '-7 days')
GROUP BY a.athlete_id, a.name, a.position, a.team
ORDER BY total_workload DESC
LIMIT 10
```

**"Show average sprint distance by position over the last 30 days"**

```sql
SELECT a.position,
       ROUND(AVG(g.sprint_distance), 1) AS avg_sprint_distance,
       COUNT(*) AS sessions
FROM sessions s
JOIN athletes a ON s.athlete_id = a.athlete_id
JOIN gps_metrics g ON s.session_id = g.session_id
WHERE s.session_date >= date('now', '-30 days')
GROUP BY a.position
ORDER BY avg_sprint_distance DESC
```

**"Who is trending below their baseline performance?"**

Baseline is the athlete's historical average. "Trending below" means the recent 7-day average is less than 90% of the all-time average. This uses a CTE to compute both values cleanly.

```sql
WITH baseline AS (
    SELECT s.athlete_id,
           AVG(g.total_distance) AS hist_avg
    FROM sessions s
    JOIN gps_metrics g ON s.session_id = g.session_id
    GROUP BY s.athlete_id
),
recent AS (
    SELECT s.athlete_id,
           AVG(g.total_distance) AS recent_avg
    FROM sessions s
    JOIN gps_metrics g ON s.session_id = g.session_id
    WHERE s.session_date >= date('now', '-7 days')
    GROUP BY s.athlete_id
)
SELECT a.name, a.position,
       ROUND(b.hist_avg, 0) AS baseline_distance,
       ROUND(r.recent_avg, 0) AS recent_distance,
       ROUND((r.recent_avg / b.hist_avg) * 100, 1) AS pct_of_baseline
FROM recent r
JOIN baseline b ON r.athlete_id = b.athlete_id
JOIN athletes a ON r.athlete_id = a.athlete_id
WHERE (r.recent_avg / b.hist_avg) < 0.90
ORDER BY pct_of_baseline ASC
```

**Prompt Design**

The SQL generation prompt does several things to reduce the risk of bad output.

First, it pastes the exact schema into the prompt. Without it, the model invents column names based on what sounds plausible, which breaks silently (the query runs but returns wrong data, which is worse than an error).

Second, date ranges are resolved before the prompt is constructed. The model never sees "last week", it sees `2026-03-25`. This removes an entire class of errors where the model's interpretation of relative dates disagrees with what the user meant.

Third, there are hard rules in the prompt: no writes, no DDL, one statement only, always LIMIT 100. These are not foolproof (you cannot rely on prompts alone to enforce security), which is why there is also an AST validator running after. The prompt rules and the validator together create two independent layers.

Fourth, the prompt includes 12 proven query examples. Few-shot examples are more reliable than instructions for SQL generation because they show the model the exact patterns that work on this specific schema.

---

## Task 3: KPI Retrieval

**How retrieval works**

Each KPI is stored as a document containing its name, description, the SQL expression it maps to, synonyms coaches commonly use, and example phrasings from real queries. The document is embedded using `all-MiniLM-L6-v2` and stored in ChromaDB with cosine similarity indexing.

When a query comes in, the user's question is embedded the same way and the top-3 most similar KPI documents are retrieved. The similarity score tells us how confident to be:
- Above 0.8: auto-select and inject into the SQL prompt
- 0.6 to 0.8: select but flag as uncertain
- Below 0.6: ask the user which metric they meant

**Why this chunking approach**

Embedding the KPI name alone would miss synonyms ("HIE" vs "high-intensity efforts"). Embedding just the description misses the SQL expression, which is what actually matters for generation. By combining everything into one document, the embedding captures the full semantic space of what this KPI is and how people talk about it.

**Ranking and filtering**

Pure cosine similarity is the primary ranking signal. I looked at adding BM25 keyword search as a secondary signal, but the KPI corpus is small enough (10 KPIs) that vector search alone works well. For a larger corpus with 100+ KPIs, hybrid retrieval with RRF fusion would be worth the added complexity.

One non-obvious filter: if the query mentions a specific session type (match-only or training sessions), KPIs without a session_type dimension get down-weighted. This prevents "average sprint distance" from being retrieved for a question specifically about match sprints when "match vs training comparison" is the more relevant KPI.

**Tradeoffs**

The main tradeoff is between recall and precision. Embedding everything into one document improves recall (you find the right KPI even when the user uses an unusual phrasing) but can reduce precision (two similar KPIs might both score highly when only one is correct). In practice, with 10 KPIs, precision has not been a problem. The evaluation results show 75-100% KPI retrieval P@3 depending on ChromaDB warmup state.

The other tradeoff is model size vs speed. `all-MiniLM-L6-v2` is 80MB and runs in about 50ms on CPU. A larger model like `all-mpnet-base-v2` would give better embeddings but doubles the latency. For this use case where the latency budget is already dominated by LLM calls, the smaller model is the right choice.

---

## Task 4: Visualizations

The project generates charts automatically using Claude to select the chart type, then renders with Recharts in React.

**Bar chart: athlete comparisons**

Used when comparing a metric across athletes, positions, or teams. The most common output. Each bar gets a distinct color so athletes are visually separable even when the chart is small on a mobile screen.

**Horizontal bar chart: many items**

Standard bar charts get crowded with more than 6 items on the x-axis. When that happens, the chart switches to horizontal layout automatically so labels do not overlap.

**Line chart: trends over time**

Used only when the x-axis is a date column. The rule is strict: if it is not a date, it is not a line chart. Connecting non-sequential categories with a line implies a relationship that does not exist.

**Scatter chart: two numeric metrics**

Used when the question involves correlating two measurements, like fatigue vs sprint distance. Useful for identifying athletes who are working hard but showing early signs of fatigue.

**Why automatic chart selection**

Coaches should not have to think about chart types. The system looks at the result columns and the question to infer the right visualization. This fails in edge cases but the fallback is always a table, which is always correct even if not the most visually clear option.

---

## Task 5: Reliable Natural Language Querying

The honest answer is that you cannot make NL querying reliable with a single approach. You need layers.

**Layer 1: Schema abstraction**

The LLM never sees the raw database schema. It sees a curated, human-readable version that describes each table's purpose, documents every column with its unit and meaning, and explicitly lists which joins are valid. This is maintained as a separate artifact that gets versioned alongside schema migrations.

**Layer 2: KPI definitions**

Metrics like "high-intensity rate" require a join, a division, a NULLIF guard, and specific column names. If you let the LLM derive this from scratch every time, you get inconsistent results. Instead, the exact SQL expression for each KPI is stored in the KPI definition store and injected into the prompt verbatim. The LLM's job is to select the right KPI and build a query around it, not to invent metric logic.

**Layer 3: Precomputed views**

For common query patterns (7-day rolling averages, team totals, position summaries), materialised views refreshed nightly collapse complex multi-join queries into simple single-table lookups. A question like "show the team's average workload this week" can hit a view with 3 columns rather than a 4-table join, which dramatically reduces the surface area for SQL generation errors.

**Layer 4: Validation**

Every generated SQL statement passes through an AST parser before execution. Blocked: any write statement, system table access, more than one statement, LIMIT above 500. This is not optional and not configurable. No prompt instruction or claimed permission can bypass it.

**Layer 5: Verification**

After execution, a second LLM call checks whether the result actually answers the question. This catches the worst category of failure: queries that execute successfully and return plausible data but answer a slightly different question than what was asked. The verification verdict is shown to the user so they can decide whether to trust the result.

**What still breaks**

Relative date handling is the most common source of errors. The DB stores dates as text in M/D/YYYY format, which SQLite's date functions handle differently than PostgreSQL. These are pre-resolved deterministically before prompt construction, but edge cases still slip through.

Complex multi-hop questions (which athletes who performed above baseline last week also had low sleep scores the previous night?) require subqueries or CTEs that the LLM sometimes gets wrong. The verification layer catches most of these failures.

---

## Task 6: Evaluation Framework

The eval framework is implemented in `eval.py` and runs 15 benchmark tests automatically.

**Measuring SQL correctness**

Three levels, each catching different failure types:

*Execution accuracy:* does the query run without error? This is the baseline check. Anything below 90% means the prompt or schema context is broken.

*Column accuracy:* do the result columns match what was expected? Substring matching is used ("sleep" matches "avg_sleep_score") rather than exact matching, because aliases vary. Exact matching was causing false negatives where the query was correct but the alias differed slightly.

*Row count validation:* does the result have the right number of rows? For questions with a known answer ("show all athletes" should return exactly 15), this is a hard check. For open-ended questions, the check is just >= 1.

**Measuring response usefulness**

*Thumbs up/down:* already implemented and logged to SQLite. Low-effort signal but the most honest one because it reflects whether the coach actually got what they needed.

*Verification verdict:* Claude checks its own output and classifies it as correct, partial, incorrect, or empty. This runs on every query automatically. Current distribution is roughly 60% correct, 20% partial, 20% unknown (usually empty results).

*Follow-up rate:* if a user immediately rewrites the same question, the first answer failed. This is implicit feedback that requires no user action.

**Most likely failure modes**

*Empty results:* the most common failure in the eval. Usually caused by ChromaDB not being warmed up on server start (the embedding model loads lazily and the first few queries race against initialization). Mitigation: warmup call on server startup, 3-retry logic on KPI retrieval.

*Wrong aggregation:* the query runs and returns data, but uses SUM when the question asked for AVG or vice versa. The verification layer catches most of these. The KPI definition also includes the correct aggregation type to guide generation.

*Column hallucination:* the LLM references a column that does not exist. Caught immediately by the AST validator. Mitigation: schema is pasted verbatim into the prompt; few-shot examples only use real columns.

*Stacked SQL statements:* SQLite does not allow multiple statements in one execute call. Claude occasionally generates two statements separated by a comment. Mitigation: strip semicolons before execution, explicit rule in prompt.

**Current eval results**

| Metric | Score |
|--------|-------|
| Pass rate | 12/15 (80%) |
| Avg latency | 30s |
| KPI retrieval P@3 | 75% |
| Verification correct | 60% |

The 3 remaining failures (B02, B10, B12) all show empty KPI retrieval on the first attempt due to ChromaDB cold start. Running eval a second time without restarting the server gives 14/15 because the embedding model is fully loaded by then.
