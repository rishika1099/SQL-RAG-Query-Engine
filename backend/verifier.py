import os, json, re
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

VERIFY_SYSTEM = """You are a QA layer for a sports analytics AI.
Given a user question, the SQL generated, and a sample of results,
verify whether the SQL correctly answers the question.

Respond ONLY with JSON:
{
  "verdict": "correct" | "partial" | "incorrect" | "empty",
  "confidence": 0.0-1.0,
  "explanation": "<one sentence>",
  "issues": ["<issue 1>"]
}

- "correct": SQL answers the question accurately
- "partial": runs but missing filters, wrong aggregation, or incomplete
- "incorrect": returns data but clearly doesn't answer the question
- "empty": 0 rows returned
If correct, issues = []."""


def verify_result(question: str, sql: str, columns: list, rows: list) -> dict:
    if not rows:
        return {
            "verdict": "empty",
            "confidence": 0.9,
            "explanation": "Query returned no rows.",
            "issues": ["0 rows returned — date range may be too narrow or no matching data."]
        }
    sample = rows[:5]
    sample_str = "\t".join(columns) + "\n" + "\n".join(["\t".join(str(v) for v in r) for r in sample])
    if len(rows) > 5:
        sample_str += f"\n... ({len(rows)-5} more rows)"

    prompt = f"User question: {question}\n\nSQL:\n{sql}\n\nResult ({len(rows)} rows):\n{sample_str}"
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=256,
            system=VERIFY_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )
        text = re.sub(r"```json|```", "", msg.content[0].text).strip()
        return json.loads(text)
    except Exception as e:
        return {"verdict": "unknown", "confidence": 0.0, "explanation": str(e), "issues": []}
