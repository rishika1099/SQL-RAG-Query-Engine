import os
import json
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

KPI_DEFINITIONS = [
    {
        "kpi_id": "avg_total_distance",
        "display_name": "Average total distance",
        "description": "Average total distance covered per session",
        "sql_expression": "AVG(g.total_distance)",
        "unit": "metres",
        "required_tables": ["gps_metrics", "sessions"],
        "aggregation": "AVG",
        "synonyms": ["avg distance", "mean distance", "average distance covered"],
        "example_queries": ["average distance per session", "average total distance by athlete", "how far do athletes run on average"],
    },
    {
        "kpi_id": "avg_sprint_distance",
        "display_name": "Average sprint distance",
        "description": "Average sprint distance per session",
        "sql_expression": "AVG(g.sprint_distance)",
        "unit": "metres",
        "required_tables": ["gps_metrics", "sessions"],
        "aggregation": "AVG",
        "synonyms": ["sprint avg", "average sprinting", "mean sprint"],
        "example_queries": ["who sprints the most on average", "average sprint distance by position"],
    },
    {
        "kpi_id": "total_high_intensity",
        "display_name": "Total high-intensity efforts",
        "description": "Total count of high-intensity efforts over a period",
        "sql_expression": "SUM(g.high_intensity_efforts)",
        "unit": "count",
        "required_tables": ["gps_metrics", "sessions"],
        "aggregation": "SUM",
        "synonyms": ["HIE", "high intensity runs", "intense efforts", "hard efforts"],
        "example_queries": ["who had the most high intensity efforts", "total HIE per athlete"],
    },
    {
        "kpi_id": "distance_per_minute",
        "display_name": "Distance per minute",
        "description": "Total distance divided by session duration — work rate",
        "sql_expression": "SUM(g.total_distance) / NULLIF(SUM(s.duration_minutes), 0)",
        "unit": "m/min",
        "required_tables": ["gps_metrics", "sessions"],
        "aggregation": "derived",
        "synonyms": ["work rate", "metres per minute", "distance rate"],
        "example_queries": ["who has the highest work rate", "distance per minute by athlete"],
    },
    {
        "kpi_id": "fatigue_trend",
        "display_name": "Fatigue trend",
        "description": "Fatigue score over time — rising score means increasing fatigue",
        "sql_expression": "w.fatigue_score",
        "unit": "score 0-100",
        "required_tables": ["wellness"],
        "aggregation": "trend",
        "synonyms": ["fatigue", "tiredness", "fatigue score", "how tired", "exhaustion"],
        "example_queries": ["who is most fatigued", "show fatigue scores", "which athletes are tired"],
    },
    {
        "kpi_id": "sleep_quality_avg",
        "display_name": "Average sleep quality",
        "description": "Average sleep score — higher is better",
        "sql_expression": "AVG(w.sleep_score)",
        "unit": "score 0-100",
        "required_tables": ["wellness"],
        "aggregation": "AVG",
        "synonyms": ["sleep score", "sleep quality", "recovery", "rest score"],
        "example_queries": ["who is sleeping well", "average sleep score", "poor sleep athletes"],
    },
    {
        "kpi_id": "workload",
        "display_name": "Total workload",
        "description": "Total distance aggregated per athlete — overall physical load",
        "sql_expression": "SUM(g.total_distance)",
        "unit": "metres",
        "required_tables": ["gps_metrics", "sessions"],
        "aggregation": "SUM",
        "synonyms": ["load", "total load", "physical load", "volume"],
        "example_queries": ["who had the highest workload", "total load per athlete", "highest volume"],
    },
    {
        "kpi_id": "position_sprint_profile",
        "display_name": "Sprint profile by position",
        "description": "Average sprint distance grouped by playing position",
        "sql_expression": "AVG(g.sprint_distance)",
        "unit": "metres",
        "required_tables": ["gps_metrics", "sessions", "athletes"],
        "aggregation": "AVG GROUP BY position",
        "synonyms": ["position sprint", "sprint by role", "forwards vs defenders"],
        "example_queries": ["which position sprints the most", "sprint profile by position"],
    },
    {
        "kpi_id": "high_intensity_rate",
        "display_name": "High-intensity rate",
        "description": "High-intensity efforts per minute — normalised intensity",
        "sql_expression": "SUM(g.high_intensity_efforts) / NULLIF(SUM(s.duration_minutes), 0)",
        "unit": "efforts/min",
        "required_tables": ["gps_metrics", "sessions"],
        "aggregation": "derived",
        "synonyms": ["HIE rate", "intensity rate", "normalised intensity", "efforts per minute"],
        "example_queries": ["highest intensity rate", "efforts per minute by athlete"],
    },
    {
        "kpi_id": "match_vs_training",
        "display_name": "Match vs training distance",
        "description": "Comparison of total distance between match and training sessions",
        "sql_expression": "AVG(CASE WHEN s.session_type='Match' THEN g.total_distance END)",
        "unit": "metres",
        "required_tables": ["gps_metrics", "sessions"],
        "aggregation": "conditional AVG",
        "synonyms": ["game vs training", "match load", "session type comparison"],
        "example_queries": ["match vs training comparison", "do athletes run more in matches"],
    },
]

_model = None
_chroma_client = None
_collection = None
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_store")


def _get_model():
    global _model
    if _model is None:
        print("[embeddings] Loading model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[embeddings] Model ready.")
    return _model


def _get_collection():
    global _chroma_client, _collection
    if _collection is not None:
        return _collection
    _chroma_client = chromadb.PersistentClient(
        path=CHROMA_PATH,
        settings=Settings(anonymized_telemetry=False)
    )
    _collection = _chroma_client.get_or_create_collection(
        name="kpi_definitions",
        metadata={"hnsw:space": "cosine"}
    )
    if _collection.count() == 0:
        _seed_kpis()
    return _collection


def _seed_kpis():
    model = _get_model()
    print("[embeddings] Seeding KPI vector store...")
    for kpi in KPI_DEFINITIONS:
        doc = (f"{kpi['display_name']}. {kpi['description']}. "
               f"Synonyms: {', '.join(kpi['synonyms'])}. "
               f"Examples: {'. '.join(kpi['example_queries'])}")
        embedding = model.encode(doc).tolist()
        _collection.upsert(
            ids=[kpi["kpi_id"]],
            embeddings=[embedding],
            documents=[doc],
            metadatas=[{
                "kpi_id": kpi["kpi_id"],
                "display_name": kpi["display_name"],
                "description": kpi["description"],
                "sql_expression": kpi["sql_expression"],
                "unit": kpi["unit"],
                "aggregation": kpi["aggregation"],
                "required_tables": json.dumps(kpi["required_tables"]),
            }]
        )
    print(f"[embeddings] Seeded {len(KPI_DEFINITIONS)} KPIs.")


def retrieve_kpis(question: str, top_k: int = 3) -> list[dict]:
    model = _get_model()
    collection = _get_collection()
    query_embedding = model.encode(question).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["metadatas", "distances"]
    )
    retrieved = []
    for i, metadata in enumerate(results["metadatas"][0]):
        score = 1 - results["distances"][0][i]
        retrieved.append({
            "kpi_id": metadata["kpi_id"],
            "display_name": metadata["display_name"],
            "description": metadata["description"],
            "sql_expression": metadata["sql_expression"],
            "unit": metadata["unit"],
            "aggregation": metadata["aggregation"],
            "required_tables": json.loads(metadata["required_tables"]),
            "similarity": round(score, 3),
        })
    return retrieved


def format_kpi_context(kpis: list[dict]) -> str:
    if not kpis:
        return ""
    lines = ["RELEVANT KPI DEFINITIONS (retrieved by semantic search):"]
    for kpi in kpis:
        lines.append(
            f"- {kpi['display_name']} (score: {kpi['similarity']:.2f}): "
            f"{kpi['description']}. SQL: {kpi['sql_expression']}. Unit: {kpi['unit']}."
        )
    return "\n".join(lines)


def warmup():
    """Pre-warm ChromaDB and the embedding model by running a test query."""
    try:
        retrieve_kpis("show athlete performance metrics", top_k=3)
        print("[embeddings] Warmup complete.")
    except Exception as e:
        print(f"[embeddings] Warmup failed: {e}")