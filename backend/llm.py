import os, re, json
import anthropic
from dotenv import load_dotenv
from db import get_schema_description
from embeddings import retrieve_kpis, format_kpi_context, warmup as warmup_embeddings

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

INTENT_SYSTEM = """You are an intent classifier for a sports analytics chatbot.
Respond ONLY with JSON:
{
  "intent": "query" | "clarify",
  "confidence": 0.0-1.0,
  "metric_mentions": ["<metric>"],
  "clarifying_question": "<question or null>",
  "clarifying_options": ["<option 1>", "<option 2>", "<option 3>"]
}
Set intent="clarify" ONLY when completely ambiguous (e.g. "show me performance" with zero specifics).
Default to intent="query" for anything with a recognisable sports metric."""

SQL_SYSTEM = """You are a read-only SQL assistant for Apollo, a sports performance analytics platform.
Translate natural language into safe, correct SQLite queries.

{schema}

{kpi_context}

STRICT RULES:
1. Output ONLY the raw SQL query. No markdown fences, no explanation, no comments.
2. NEVER use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, ATTACH.
3. Only reference tables and columns listed in the schema above.
4. Always add LIMIT 100 unless the question explicitly asks for all rows.
5. This is SQLite — use date('now', '-7 days') for relative dates, NOT INTERVAL syntax.
6. Dates in the DB are stored as TEXT in M/D/YYYY format e.g. '1/5/2026'.
7. Use ROUND(value, 1) for all float results.
8. Use descriptive aliases: avg_sprint_distance, total_distance, sleep_score etc.
9. GROUP BY every non-aggregated column in SELECT.
10. Output exactly ONE SQL statement — no semicolons mid-query, no stacked statements.
11. When comparing session types, GROUP BY session_type to get one row per type.
12. For "average X per athlete" queries: GROUP BY athlete_id, name and use AVG().
13. For "who had highest/lowest" queries: ORDER BY the metric DESC/ASC with LIMIT 1 or 10.

PROVEN QUERY PATTERNS:

Q: Average sprint distance by position
SQL:
SELECT a.position,
       ROUND(AVG(g.sprint_distance), 1) AS avg_sprint_distance,
       COUNT(*) AS sessions
FROM sessions s
JOIN athletes a ON s.athlete_id = a.athlete_id
JOIN gps_metrics g ON s.session_id = g.session_id
GROUP BY a.position
ORDER BY avg_sprint_distance DESC

Q: Who had the highest total distance?
SQL:
SELECT a.name, a.position, a.team,
       ROUND(SUM(g.total_distance), 0) AS total_distance
FROM sessions s
JOIN athletes a ON s.athlete_id = a.athlete_id
JOIN gps_metrics g ON s.session_id = g.session_id
GROUP BY a.athlete_id, a.name, a.position, a.team
ORDER BY total_distance DESC
LIMIT 10

Q: Compare match vs training total distance
SQL:
SELECT s.session_type,
       ROUND(AVG(g.total_distance), 1) AS avg_distance,
       COUNT(*) AS session_count
FROM sessions s
JOIN gps_metrics g ON s.session_id = g.session_id
GROUP BY s.session_type
ORDER BY avg_distance DESC

Q: Show fatigue scores for all athletes
SQL:
SELECT a.name, a.position, w.date,
       w.fatigue_score, w.sleep_score
FROM wellness w
JOIN athletes a ON w.athlete_id = a.athlete_id
ORDER BY w.fatigue_score DESC
LIMIT 50

Q: What is the average sleep score per athlete?
SQL:
SELECT a.name, a.position,
       ROUND(AVG(w.sleep_score), 1) AS avg_sleep_score,
       ROUND(AVG(w.fatigue_score), 1) AS avg_fatigue_score
FROM wellness w
JOIN athletes a ON w.athlete_id = a.athlete_id
GROUP BY a.athlete_id, a.name, a.position
ORDER BY avg_sleep_score ASC

Q: Show total high intensity efforts per athlete
SQL:
SELECT a.name, a.position,
       SUM(g.high_intensity_efforts) AS total_hie,
       COUNT(*) AS sessions
FROM sessions s
JOIN athletes a ON s.athlete_id = a.athlete_id
JOIN gps_metrics g ON s.session_id = g.session_id
GROUP BY a.athlete_id, a.name, a.position
ORDER BY total_hie DESC

Q: Which athletes are on team A?
SQL:
SELECT name, position, team
FROM athletes
WHERE team = 'A'
ORDER BY name

Q: Show all athletes and their positions
SQL:
SELECT name, position, team
FROM athletes
ORDER BY position, name

Q: Show sprint distance for forwards only
SQL:
SELECT a.name,
       ROUND(SUM(g.sprint_distance), 0) AS sprint_distance,
       COUNT(*) AS sessions
FROM sessions s
JOIN athletes a ON s.athlete_id = a.athlete_id
JOIN gps_metrics g ON s.session_id = g.session_id
WHERE a.position = 'Forward'
GROUP BY a.athlete_id, a.name
ORDER BY sprint_distance DESC

Q: High intensity rate per athlete
SQL:
SELECT a.name, a.position,
       ROUND(
         CAST(SUM(g.high_intensity_efforts) AS FLOAT) /
         NULLIF(SUM(s.duration_minutes), 0),
       3) AS hie_per_minute
FROM sessions s
JOIN athletes a ON s.athlete_id = a.athlete_id
JOIN gps_metrics g ON s.session_id = g.session_id
GROUP BY a.athlete_id, a.name, a.position
ORDER BY hie_per_minute DESC

Q: Who had the highest total distance?
SQL:
SELECT a.name, a.position, a.team,
       ROUND(SUM(g.total_distance), 0) AS total_distance
FROM sessions s
JOIN athletes a ON s.athlete_id = a.athlete_id
JOIN gps_metrics g ON s.session_id = g.session_id
GROUP BY a.athlete_id, a.name, a.position, a.team
ORDER BY total_distance DESC
LIMIT 10

Q: Who slept the worst on average?
SQL:
SELECT a.name, a.position,
       ROUND(AVG(w.sleep_score), 1) AS avg_sleep_score
FROM wellness w
JOIN athletes a ON w.athlete_id = a.athlete_id
GROUP BY a.athlete_id, a.name, a.position
ORDER BY avg_sleep_score ASC
LIMIT 5

Q: Which session type has more high intensity efforts on average?
SQL:
SELECT s.session_type,
       ROUND(AVG(g.high_intensity_efforts), 1) AS avg_hie,
       COUNT(*) AS session_count
FROM sessions s
JOIN gps_metrics g ON s.session_id = g.session_id
GROUP BY s.session_type
ORDER BY avg_hie DESC

Q: Total workload per team
SQL:
SELECT a.team,
       ROUND(SUM(g.total_distance), 0) AS total_workload,
       COUNT(DISTINCT a.athlete_id) AS athletes,
       COUNT(*) AS sessions
FROM sessions s
JOIN athletes a ON s.athlete_id = a.athlete_id
JOIN gps_metrics g ON s.session_id = g.session_id
GROUP BY a.team
ORDER BY total_workload DESC"""

FOLLOWUP_SYSTEM = """You are a sports analytics assistant.
Given a question and query result, suggest 3 concise follow-up questions a coach would ask.
Respond ONLY with a valid JSON array of exactly 3 strings, each under 10 words.
Example: ["Which position sprints the most?", "Compare match vs training load", "Show fatigue trend over time"]
No explanation, just the JSON array."""

CHART_SYSTEM = """You are a data visualization assistant for sports analytics.
Given a question and SQL result, pick the best Chart.js chart type.

Respond ONLY with valid JSON:
{
  "chart_type": "bar" | "line" | "scatter" | null,
  "x_key": "<exact column name from result>",
  "y_key": "<exact column name from result>",
  "title": "<short descriptive title>",
  "reasoning": "<one sentence>"
}

Rules:
- "bar": best for comparing athletes, positions, or teams (most common)
- "line": only when x_key is a date/time column showing a trend
- "scatter": only when plotting two numeric metrics against each other
- null: if only 1 data point, or data is not visual
- x_key and y_key MUST exactly match column names returned in the result
- For "bar" with many items (>6), pick the most important numeric column as y_key"""


def classify_intent(question: str) -> dict:
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=200,
            system=INTENT_SYSTEM,
            messages=[{"role": "user", "content": question}]
        )
        return json.loads(re.sub(r"```json|```", "", msg.content[0].text).strip())
    except Exception:
        return {"intent": "query", "confidence": 0.8, "metric_mentions": [],
                "clarifying_question": None, "clarifying_options": []}


def generate_sql(question: str) -> tuple:
    import time
    # Retry KPI retrieval up to 3 times if empty
    kpis = []
    for attempt in range(3):
        try:
            kpis = retrieve_kpis(question, top_k=3)
            if kpis:
                break
            time.sleep(1.5)
        except Exception:
            time.sleep(1.5)

    kpi_context = format_kpi_context(kpis)
    schema = get_schema_description()
    system = SQL_SYSTEM.format(schema=schema, kpi_context=kpi_context)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": question}]
    )
    sql = re.sub(r"```sql|```", "", msg.content[0].text, flags=re.IGNORECASE).strip()
    sql = sql.rstrip(";").strip()
    return sql, kpis


def suggest_followups(question: str, columns: list, rows: list) -> list:
    if not rows:
        return []
    sample = [columns] + rows[:3]
    sample_str = "\n".join(["\t".join(str(v) for v in r) for r in sample])
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=150,
            system=FOLLOWUP_SYSTEM,
            messages=[{"role": "user", "content": f"Question: {question}\n\nResult:\n{sample_str}"}]
        )
        text = re.sub(r"```json|```", "", msg.content[0].text).strip()
        result = json.loads(text)
        return result[:3] if isinstance(result, list) else []
    except Exception:
        return []


def suggest_chart(question: str, columns: list, rows: list) -> dict | None:
    if not rows or len(rows) < 2:
        return None
    sample = [columns] + rows[:5]
    sample_str = "\n".join(["\t".join(str(v) for v in r) for r in sample])
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=200,
            system=CHART_SYSTEM,
            messages=[{"role": "user", "content": f"Question: {question}\n\nResult columns and data:\n{sample_str}"}]
        )
        text = re.sub(r"```json|```", "", msg.content[0].text).strip()
        result = json.loads(text)
        return result if result.get("chart_type") else None
    except Exception:
        return None