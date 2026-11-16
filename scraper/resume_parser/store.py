"""
Step 3: save parsed profiles into the same SQLite database as the
scholarships (data/processed/scholarships.db), in a `students` table.

Design choices:
- The fields the matching engine filters on (major, GPA, grad year, school
  year, home state, ...) are real columns, so Team 2 can query them with
  plain SQL: SELECT * FROM students WHERE gpa >= 3.0 AND home_state = 'TX'.
- Lists (skills, awards, ...) and nested sections (education, experience,
  projects, activities) are stored as JSON text. Read them back with
  json.loads(), or use get_student() below, which does it for you.
- One row per student: re-uploading a resume with the same email UPDATES
  that student's row instead of adding a duplicate. Resumes with no email
  are keyed by the file's contents instead.
- The table lives under data/, which git ignores -- resumes hold personal
  info, so parsed profiles never get committed (see DATA.md).
"""

import json
from datetime import datetime, timezone

STUDENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    student_key       TEXT NOT NULL UNIQUE,  -- email, or 'file:<hash>' if no email
    name              TEXT,
    email             TEXT,
    phone             TEXT,
    linkedin          TEXT,
    github            TEXT,
    home_city         TEXT,
    home_state        TEXT,                  -- 2-letter code, e.g. 'TX'
    home_country      TEXT,                  -- 'USA', or e.g. 'U.A.E.'
    school            TEXT,
    school_state      TEXT,
    degree            TEXT,                  -- e.g. 'Bachelor of Science'
    degree_level      TEXT,                  -- high_school / associate / bachelor / master / doctorate
    major             TEXT,                  -- first major
    majors            TEXT,                  -- JSON list (double majors)
    minors            TEXT,                  -- JSON list
    gpa               REAL,
    gpa_scale         REAL,                  -- usually 4.0
    grad_year         INTEGER,
    grad_month        INTEGER,
    school_year       TEXT,                  -- freshman / sophomore / junior / senior / high school senior / ...
    skills            TEXT,                  -- JSON list
    spoken_languages  TEXT,                  -- JSON list
    certifications    TEXT,                  -- JSON list
    awards            TEXT,                  -- JSON list (incl. honors like Dean's List, Eagle Scout)
    interests         TEXT,                  -- JSON list
    coursework        TEXT,                  -- JSON list
    education         TEXT,                  -- JSON list of every school entry
    experience        TEXT,                  -- JSON list of entries
    projects          TEXT,                  -- JSON list of entries
    activities        TEXT,                  -- JSON list of entries
    warnings          TEXT,                  -- JSON list: what the parser couldn't find
    raw_text          TEXT,                  -- full resume text, for keyword matching
    source_file       TEXT,
    resume_hash       TEXT,
    parser_version    TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_students_major ON students(major);
CREATE INDEX IF NOT EXISTS idx_students_home_state ON students(home_state);
"""

SCALAR_COLUMNS = [
    "name", "email", "phone", "linkedin", "github", "home_city", "home_state", "home_country",
    "school", "school_state", "degree", "degree_level", "major", "gpa", "gpa_scale",
    "grad_year", "grad_month", "school_year", "raw_text", "source_file", "resume_hash",
    "parser_version",
]
JSON_COLUMNS = [
    "majors", "minors", "skills", "spoken_languages", "certifications", "awards", "interests",
    "coursework", "education", "experience", "projects", "activities", "warnings",
]


def init_students_table(conn):
    conn.executescript(STUDENTS_SCHEMA)
    conn.commit()


def upsert_student(conn, profile: dict) -> int:
    """Insert or update one parsed profile. Returns the student's id."""
    init_students_table(conn)
    now = datetime.now(timezone.utc).isoformat()
    key = profile.get("email") or f"file:{profile['resume_hash']}"
    row = {c: profile.get(c) for c in SCALAR_COLUMNS}
    row.update({c: json.dumps(profile.get(c) or [], ensure_ascii=False) for c in JSON_COLUMNS})
    row.update({"student_key": key, "now": now})
    cols = ["student_key"] + SCALAR_COLUMNS + JSON_COLUMNS
    conn.execute(
        f"""INSERT INTO students ({", ".join(cols)}, created_at, updated_at)
            VALUES ({", ".join(":" + c for c in cols)}, :now, :now)
            ON CONFLICT(student_key) DO UPDATE SET
            {", ".join(f"{c} = excluded.{c}" for c in cols if c != "student_key")},
            updated_at = excluded.updated_at""",
        row,
    )
    conn.commit()
    return conn.execute("SELECT id FROM students WHERE student_key = ?", (key,)).fetchone()[0]


def _decode(row) -> dict:
    d = dict(row)
    for c in JSON_COLUMNS:
        if d.get(c) is not None:
            d[c] = json.loads(d[c])
    return d


def get_student(conn, student_id: int) -> dict | None:
    """One student as a dict, with the JSON columns already decoded into lists."""
    init_students_table(conn)
    row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    return _decode(row) if row else None


def get_all_students(conn) -> list[dict]:
    init_students_table(conn)
    return [_decode(r) for r in conn.execute("SELECT * FROM students ORDER BY id")]
