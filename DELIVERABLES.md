# Deliverables & Timeline

> **How to read this file.** This is the PMs' best current estimate of what ScholarSync needs to ship and roughly when. It is a **living plan, not a contract**. The authoritative picture lives in **GitHub Issues and the Project board**.

## Milestones (suggested)

| # | Deliverable | Description | Owner (role) | Target |
|---|-------------|-------------|--------------|--------|
| 1 | Project scoping | Pick target sites. Read every site's `robots.txt` + ToS before committing. Define the normalized scholarship schema. | PM | Week 1 |
| 2 | Scraper skeleton | Shared scraping framework: retries, polite rate-limiting, per-source caching, structured errors. | Members | Weeks 1–2 |
| 3 | Per-site scrapers | 5–10 site-specific scrapers producing the normalized schema. Rotated across members. | Members | Weeks 2–4 |
| 4 | Storage layer | SQLite or DuckDB with schema, migrations, and a `scholarships` table + `sources` audit table. | Members | Week 4 |
| 5 | Resume parser | PDF → structured fields (major, GPA, grade level, activities, skills). Test on synthetic resumes. | Members | Weeks 4–5 |
| 6 | Matching engine | Embedding-based similarity + hard filters; produce an explanation string per match. | Members | Weeks 5–6 |
| 7 | Streamlit dashboard | Resume upload, ranked list, "why this matched" panel, deadline calendar, saved-scholarships list. | Members + PM | Weeks 6–7 |
| 8 | Handoff & retro | Reproducibility check, short writeup with sample matches, lessons learned. | PM | Week 8 |

## Timeline (rough)

```
Week:   1     2     3     4     5     6     7     8
        |-----|-----|-----|-----|-----|-----|-----|
Scope   ██
Framework     ████
Scrapers          ████████
Storage                   ██
Resume                    ████
Match                           ████
Dashboard                                  ████
Retro                                              ██
```

## Working agreements

- **Each deliverable maps to one or more GitHub Issues.** The board is the source of truth; this file is the summary.
- **Dates are estimates.** When reality diverges, update the issue and this file if the shift is material.
- **"Done" is defined per issue** via acceptance criteria — not by a date passing.
- **Reprioritize openly.** If a deliverable changes, a PM notes why in the issue so the decision is auditable.
