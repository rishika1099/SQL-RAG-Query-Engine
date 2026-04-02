import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

CSV_DIR = os.getenv("CSV_DIR", "./data")
DB_PATH = os.getenv("DB_PATH", "./apollo.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def seed_database():
    """Load CSVs into SQLite. Safe to run multiple times."""
    tables = {
        "athletes":    "athletes.csv",
        "sessions":    "sessions.csv",
        "gps_metrics": "gps_metrics.csv",
        "wellness":    "wellness.csv",
    }
    with engine.begin() as conn:
        for table, fname in tables.items():
            path = os.path.join(CSV_DIR, fname)
            if not os.path.exists(path):
                print(f"  [skip] {path} not found")
                continue
            df = pd.read_csv(path)
            df.to_sql(table, conn, if_exists="replace", index=False)
            print(f"  [ok] seeded {table} ({len(df)} rows)")
    print("[db] Seeding complete.")


def create_feedback_table():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS query_feedback (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                question  TEXT NOT NULL,
                sql       TEXT,
                verdict   TEXT,
                rating    INTEGER,
                comment   TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """))
    print("[db] query_feedback table ready.")


def log_feedback(question: str, sql: str, verdict: str, rating: int, comment: str = ""):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO query_feedback (question, sql, verdict, rating, comment)
            VALUES (:question, :sql, :verdict, :rating, :comment)
        """), {"question": question, "sql": sql, "verdict": verdict,
               "rating": rating, "comment": comment})


def get_schema_description() -> str:
    return """
TABLE: athletes
  athlete_id  INTEGER  -- primary key
  name        TEXT     -- full name e.g. 'James Smith'
  position    TEXT     -- 'Forward', 'Midfielder', 'Defender'
  team        TEXT     -- 'A' or 'B'

TABLE: sessions
  session_id       INTEGER  -- primary key
  athlete_id       INTEGER  -- FK → athletes.athlete_id
  session_date     TEXT     -- date string e.g. '1/5/2026'
  duration_minutes INTEGER
  session_type     TEXT     -- 'Training' or 'Match'

TABLE: gps_metrics
  session_id              INTEGER  -- FK → sessions.session_id
  total_distance          REAL     -- metres
  sprint_distance         REAL     -- metres at sprint speed
  high_intensity_efforts  INTEGER  -- count of high-intensity efforts

TABLE: wellness
  athlete_id    INTEGER  -- FK → athletes.athlete_id
  date          TEXT     -- date string e.g. '1/5/2026'
  sleep_score   INTEGER  -- 0-100, higher is better
  fatigue_score INTEGER  -- 0-100, higher is more fatigued

COMMON JOINS:
  sessions     JOIN athletes    ON sessions.athlete_id  = athletes.athlete_id
  sessions     JOIN gps_metrics ON sessions.session_id  = gps_metrics.session_id
  wellness     JOIN athletes    ON wellness.athlete_id   = athletes.athlete_id

NOTE: This is SQLite. Use date('now', '-7 days') instead of CURRENT_DATE - INTERVAL '7 days'.
Date format in DB is M/D/YYYY e.g. '1/5/2026'.
""".strip()


if __name__ == "__main__":
    seed_database()
    create_feedback_table()
