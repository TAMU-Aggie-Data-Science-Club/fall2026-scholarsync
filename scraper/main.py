"""
Run the registered scrapers and save results to the SQLite database.

Usage:
    python main.py                          # run every scraper, full scrape
    python main.py --only bold.org          # run just one site
    python main.py --only scholarships.com --limit 10   # quick test: 10 pages
    python main.py --include-closed         # also keep past-deadline scholarships

Sources: unigo, scholarships.com, bold.org

To add a new site scraper: write it in scrapers/<name>.py following
scrapers/base_scraper.py's interface, then add it to build_scrapers() below.
"""

import argparse

from db.database import init_db, get_connection, upsert_scholarship, count_scholarships
from scrapers.unigo import UnigoScraper
from scrapers.scholarships_com import ScholarshipsComScraper
from scrapers.bold_org import BoldOrgScraper


def build_scrapers(limit: int | None, include_closed: bool):
    return [
        UnigoScraper(),
        ScholarshipsComScraper(max_items=limit, include_closed=include_closed),
        BoldOrgScraper(max_items=limit, include_closed=include_closed),
    ]


def main():
    parser = argparse.ArgumentParser(description="ScholarSync scholarship scrapers")
    parser.add_argument("--only", action="append",
                        help="run only this source (repeatable): unigo, scholarships.com, bold.org")
    parser.add_argument("--limit", type=int, default=None,
                        help="max scholarship pages per site (for quick test runs; unigo ignores this)")
    parser.add_argument("--include-closed", action="store_true",
                        help="also save scholarships whose deadline has passed")
    args = parser.parse_args()

    scrapers = build_scrapers(args.limit, args.include_closed)
    if args.only:
        wanted = {name.lower() for name in args.only}
        unknown = wanted - {s.source_name for s in scrapers}
        if unknown:
            parser.error(f"unknown source(s): {', '.join(sorted(unknown))}")
        scrapers = [s for s in scrapers if s.source_name in wanted]

    init_db()
    conn = get_connection()

    total_scraped = 0
    for scraper in scrapers:
        print(f"\n=== Running {scraper.source_name} scraper ===")
        try:
            scholarships = scraper.scrape()
        except Exception as e:
            print(f"[{scraper.source_name}] FAILED: {e}")
            continue

        for s in scholarships:
            upsert_scholarship(conn, {**s, "source": scraper.source_name})
        conn.commit()

        print(f"[{scraper.source_name}] saved {len(scholarships)} scholarships")
        total_scraped += len(scholarships)

    total_in_db = count_scholarships(conn)
    by_source = conn.execute("SELECT source, COUNT(*) FROM scholarships GROUP BY source").fetchall()
    conn.close()

    print(f"\nDone. Scraped {total_scraped} scholarship entries this run.")
    print(f"Database now holds {total_in_db} total scholarships (data/processed/scholarships.db):")
    for source, n in by_source:
        print(f"  {source}: {n}")


if __name__ == "__main__":
    main()
