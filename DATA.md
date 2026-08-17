# Data

This file explains **ScholarSync's** suggested data sources.

> **`DATA.md` is tracked in git. The `data/` folder is not.** Cached HTML and PII-bearing resumes must never be committed. Clone the repo, then populate `data/` locally.

## Suggested sources (starting point)

Pick 5–10 sites for v1. **Verify each site's `robots.txt` and Terms of Service before scraping.**

| Source | Origin / URL | Access method | License / ToS | Sensitivity | Notes |
|--------|--------------|---------------|---------------|-------------|-------|
| Fastweb | https://www.fastweb.com/ | Requires account | Personal use — **check ToS carefully** | Medium (site) / None (data) | Massive listing volume; scraping may be against ToS. Verify. |
| Scholarships.com | https://www.scholarships.com/ | Public listings + registration for details | ToS — check | Low | Popular aggregator |
| TAMU One Stop | https://onestop.tamu.edu/scholarships/ | Public | University page | None | Aggie-specific — high value for TAMU students |
| Bold.org | https://bold.org/ | Public listings | ToS — check | Low | Modern platform with structured listings |
| CareerOneStop | https://www.careeronestop.org/Toolkit/Training/find-scholarships.aspx | Public | US Dept. of Labor | None | Government-run — permissive |
| Sample resumes (development only) | (BYO or synthetic) | Local | Personal | **High** — PII | Real resumes contain PII. Never commit. Use synthetic resumes for CI. |

## How to think about using each source

- **`robots.txt` first.** Every site. Every time. Some sites forbid scraping entirely — don't work around it.
- **Rate-limit and cache.** One request per few seconds per host, minimum. Cache every response to `data/raw/` so re-runs don't re-hit the site.
- **Identify yourself.** Set a descriptive `User-Agent` like `ADSC-ScholarSync/0.1 (student research; contact: <pm-email>)`.
- **ToS.** Some aggregators explicitly forbid scraping. If ToS says no, **it's a no.** Route the project to a permissive source instead — surface this to the PM.
- **Resume PII.** Names, addresses, phone numbers, and school IDs are all sensitive. Store parsed resumes in memory or in `data/raw/resumes/` (ignored) — never anywhere Git can see.

Choosing and vetting a source is a **judgment call** — surface it to a PM rather than deciding a major data direction alone.

## Local layout convention

```
data/
├── raw/
│   ├── html/         # cached scraped HTML per source per day
│   └── resumes/      # local resume PDFs — NEVER commit
├── interim/          # per-source extracted listings
└── processed/        # normalized scholarships table + resume profiles
```

Because `data/` isn't in git, the **pipeline that fetches and builds these folders** is what must be committed and reproducible — not the data itself.
