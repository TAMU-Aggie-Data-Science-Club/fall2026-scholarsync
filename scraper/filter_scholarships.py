"""
Filter scraped scholarships by deadline/availability and other criteria,
then write the result to Excel (and optionally back into the database as
a "shortlist" view).

This is separate from main.py (which just scrapes and stores everything)
because filtering is a judgment call your team will want to tune --
what counts as "still available," which majors/eligibility terms count
as a match -- so it's its own script you can re-run with different
arguments without re-scraping.

Usage examples:
    # Everything with a deadline in the next 90 days (or no deadline listed)
    python filter_scholarships.py --days-until-deadline 90

    # Only scholarships whose eligibility/description text mentions these terms
    python filter_scholarships.py --keyword "computer science" --keyword "engineering"

    # Both together, min amount, output to a specific file
    python filter_scholarships.py --days-until-deadline 120 --keyword "women" --min-amount 1000 --output shortlist.xlsx
"""

import argparse
from datetime import date, datetime, timedelta

from db.database import get_connection, get_all_scholarships

try:
    import pandas as pd
except ImportError:
    pd = None


def parse_deadline_text_to_date(deadline_text: str, today: date) -> date | None:
    """
    Unigo's listing deadlines have no year (e.g. "Feb 15"), so we guess
    the most sensible upcoming year: if that month/day has already
    passed this year, assume it means next year instead.
    Returns None if the text can't be parsed at all.
    """
    if not deadline_text:
        return None
    # Parse with an explicit placeholder year up front (rather than passing
    # a year-less string to strptime) to avoid Python's deprecation warning
    # about ambiguous day-of-month-without-year parsing, and to not crash
    # on "Feb 29" when the placeholder year isn't a leap year.
    for fmt in ("%b %d %Y", "%B %d %Y"):
        try:
            parsed = datetime.strptime(f"{deadline_text} {today.year}", fmt).date()
            candidate = parsed.replace(year=today.year)
            if candidate < today:
                candidate = candidate.replace(year=today.year + 1)
            return candidate
        except ValueError:
            continue
    return None


def passes_filters(row: dict, today: date, days_until_deadline: int | None,
                    keywords: list[str], min_amount: float | None) -> bool:
    # Deadline / availability filter: keep it if its deadline is still in
    # the future and within the window, OR if we simply don't know its
    # deadline (better to show it to a human than silently drop it).
    if days_until_deadline is not None:
        deadline_date = parse_deadline_text_to_date(row.get("deadline_text"), today)
        if deadline_date is not None:
            days_away = (deadline_date - today).days
            if days_away < 0:
                return False  # deadline already passed
            if days_away > days_until_deadline:
                return False  # too far out to be "available" yet, per your window

    # Keyword filter: match against eligibility + description + name,
    # case-insensitive, OR'd together (row passes if ANY keyword matches).
    if keywords:
        haystack = " ".join(filter(None, [
            row.get("name"), row.get("eligibility"), row.get("description"),
        ])).lower()
        if not any(kw.lower() in haystack for kw in keywords):
            return False

    # Minimum award amount filter.
    if min_amount is not None:
        if row.get("amount_value") is None or row["amount_value"] < min_amount:
            return False

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-until-deadline", type=int, default=None,
                         help="Keep only scholarships due within this many days (or with an unknown deadline).")
    parser.add_argument("--keyword", action="append", default=[],
                         help="Keep only scholarships whose name/eligibility/description mentions this term. Repeatable.")
    parser.add_argument("--min-amount", type=float, default=None,
                         help="Keep only scholarships with an award amount at or above this value.")
    parser.add_argument("--output", default="shortlist.xlsx",
                         help="Output Excel filename.")
    args = parser.parse_args()

    conn = get_connection()
    rows = get_all_scholarships(conn)
    conn.close()

    today = date.today()
    filtered = [
        r for r in rows
        if passes_filters(r, today, args.days_until_deadline, args.keyword, args.min_amount)
    ]

    print(f"{len(rows)} total scholarships in the database.")
    print(f"{len(filtered)} pass the filters you gave.")

    if pd is None:
        print("\npandas/openpyxl aren't installed, so I can't write an .xlsx file.")
        print("Run: pip install pandas openpyxl")
        return

    df = pd.DataFrame(filtered)
    # Put the most useful columns first for anyone skimming the spreadsheet.
    preferred_order = [
        "name", "amount_text", "num_awards", "deadline_text", "eligibility",
        "description", "link", "category", "source",
    ]
    cols = [c for c in preferred_order if c in df.columns] + \
           [c for c in df.columns if c not in preferred_order]
    df = df[cols] if not df.empty else df

    df.to_excel(args.output, index=False)
    print(f"\nWrote {len(filtered)} rows to {args.output}")


if __name__ == "__main__":
    main()
