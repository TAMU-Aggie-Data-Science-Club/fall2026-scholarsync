-- ScholarSync scholarship database schema
-- One row per scholarship. `source` + `source_url` together let us
-- re-run scrapers without creating duplicate rows (see INSERT ... ON CONFLICT
-- in db/database.py).

CREATE TABLE IF NOT EXISTS scholarships (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT NOT NULL,          -- e.g. "unigo"
    name                TEXT NOT NULL,
    amount_text         TEXT,                   -- raw text, e.g. "$16,000"
    amount_value        REAL,                   -- parsed numeric amount, e.g. 16000.0
    num_awards          INTEGER,                -- how many awards are given, e.g. 8
    deadline_text       TEXT,                   -- raw text, e.g. "Feb 15"
    deadline_date       TEXT,                   -- ISO date if we could parse one, e.g. "2027-02-15"
    eligibility         TEXT,                   -- eligibility criteria description
    description         TEXT,                   -- general description / summary
    link                TEXT NOT NULL,           -- URL to the scholarship's own page
    category            TEXT,                   -- which listing page it came from, e.g. "computer-science"
    first_seen_at       TEXT NOT NULL,           -- ISO timestamp, first time we scraped this
    last_seen_at        TEXT NOT NULL,           -- ISO timestamp, most recent time we scraped this
    UNIQUE(source, link)
);

CREATE INDEX IF NOT EXISTS idx_scholarships_source ON scholarships(source);
CREATE INDEX IF NOT EXISTS idx_scholarships_category ON scholarships(category);
CREATE INDEX IF NOT EXISTS idx_scholarships_deadline ON scholarships(deadline_date);
