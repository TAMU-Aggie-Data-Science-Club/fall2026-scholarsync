"""
SQLite helpers for the ScholarSync scraper.

Why SQLite: it's a single file (scholarships.db) with no server to run,
so it works the same on your machine or a teammate's. It's also easy to
query later from the matching engine, and you can always export to CSV
for anyone who just wants a spreadsheet (see export_csv.py).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Lives in data/processed/, which the club repo's .gitignore keeps out of git
# (repo rule: commit the pipeline, never the data). Re-create it with
# `python main.py`, or share it with teammates via `python export_csv.py`.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "scholarships.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection():
    """Open a connection to the database, creating the file if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn


def init_db():
    """Create the scholarships table if it doesn't already exist. Safe to call every run."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def upsert_scholarship(conn, scholarship: dict):
    """
    Insert a scholarship, or update it if we've already seen this
    (source, link) pair. This is what makes it safe to re-run a scraper
    every day without creating duplicate rows -- it just refreshes
    last_seen_at and any changed fields on existing scholarships.
    """
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        INSERT INTO scholarships (
            source, name, amount_text, amount_value, num_awards,
            deadline_text, deadline_date, eligibility, description,
            link, category, first_seen_at, last_seen_at
        ) VALUES (
            :source, :name, :amount_text, :amount_value, :num_awards,
            :deadline_text, :deadline_date, :eligibility, :description,
            :link, :category, :now, :now
        )
        ON CONFLICT(source, link) DO UPDATE SET
            name = excluded.name,
            amount_text = excluded.amount_text,
            amount_value = excluded.amount_value,
            num_awards = excluded.num_awards,
            deadline_text = excluded.deadline_text,
            deadline_date = excluded.deadline_date,
            -- COALESCE, not a plain overwrite: the listing-page scraper
            -- often can't find a clean description at all (it returns
            -- NULL rather than guess). Without this, re-running the
            -- scraper later would blank out any description that
            -- enrich_descriptions.py had already filled in by visiting
            -- the scholarship's own page. A fresh non-NULL value from
            -- the listing page still wins, since that's just as current.
            eligibility = COALESCE(excluded.eligibility, scholarships.eligibility),
            description = COALESCE(excluded.description, scholarships.description),
            category = excluded.category,
            last_seen_at = excluded.last_seen_at
        """,
        {**scholarship, "now": now},
    )


def get_all_scholarships(conn):
    """Return every scholarship in the database as a list of dicts."""
    rows = conn.execute("SELECT * FROM scholarships ORDER BY last_seen_at DESC").fetchall()
    return [dict(row) for row in rows]


def count_scholarships(conn):
    return conn.execute("SELECT COUNT(*) FROM scholarships").fetchone()[0]
