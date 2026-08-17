# ScholarSync — Advanced

*ADSC Catalyst Project · Fall 2026*

## Overview

ScholarSync is an intelligent discovery platform that automatically collects scholarship opportunities from universities, organizations, and public funding websites via web scraping, then matches them to a student's resume through an interactive search dashboard.

## Objective

Build a scraper + matcher pipeline: crawl a curated set of scholarship sites, normalize listings into a unified schema, extract candidate profiles from resumes, and rank scholarships per student by fit.

## Suggested tech stack

- **Data processing:** Python, Selenium, `beautifulsoup4`, `httpx`, `pdfplumber` / `pypdf` for resume parsing
- **Modeling:** TF-IDF or embedding-based (sentence-transformers) matching, learning-to-rank as a stretch goal
- **Storage:** SQLite or DuckDB for the normalized listings
- **Visualization / dashboard:** Streamlit
- **Data sources:** Public scholarship listing sites (Fastweb, Scholarships.com, TAMU One Stop, Bold.org, etc.)

See [`DATA.md`](DATA.md) for concrete data sources and how to access them.

## What team members will gain

- Automated web scraping at real scale — scalable, resumable, respectful pipelines
- A functional platform that tracks scholarship applications
- Data-integration experience across heterogeneous sources

## Suggested scope (v1)

Scrape **5–10 well-structured scholarship sites** with a common normalized schema — not the whole web. Focus on quality of extraction and matching over breadth.

Build:

1. Per-site scrapers as small, isolated modules with retry + polite rate-limiting,
2. A normalized `scholarships` table (title, provider, amount, deadline, eligibility text, apply URL, source, scraped_at),
3. Resume parser: PDF → structured fields (major, GPA, grade level, activities, skills),
4. Matcher: embedding-based similarity between eligibility text and resume profile + hard filters (major/grade/citizenship),
5. Streamlit dashboard: upload resume → ranked scholarships with an "why this matched" explanation, deadline calendar, saved-scholarships list.

**Out of scope for v1:** paid databases, live application submission, browser-based automation of application forms, ML on application outcomes.

**Respect the target sites.** Read `robots.txt`, rate-limit, cache pages locally, identify with a proper `User-Agent`. Don't hammer.

See [`DELIVERABLES.md`](DELIVERABLES.md) for the suggested deliverable breakdown and rough timeline.

## Repository map

| File / folder | Purpose |
|---|---|
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | **Start here.** How the team runs the project on GitHub — PM vs. member roles, the issue → PR → `main` flow, branching, worktrees, reviews. |
| [`DELIVERABLES.md`](DELIVERABLES.md) | Suggested deliverables and rough timeline. A living plan, not a contract. |
| [`DATA.md`](DATA.md) | Suggested data sources, how to access them, and the source register. |
| [`data/`](data/) | Local working folder for datasets. **Git-ignored** — data is never committed. |
| [`AGENTS.md`](AGENTS.md) | Machine-facing workflow rules for AI coding agents. |

## Notes for PMs

This README, [`DELIVERABLES.md`](DELIVERABLES.md), and [`DATA.md`](DATA.md) are **suggestions**, not commitments. Rewrite them as the team scopes the real project.

## Notes for members

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before touching code. Then pick up an issue from the board.
