"""
Fills in missing eligibility/description text by visiting each
scholarship's OWN detail page directly (its `link` column), instead of
relying on the shared listing page's text.

Why this exists: scrapers/unigo.py's listing-page parser only finds a
clean description for about a third of entries -- Unigo renders its
listing cards inconsistently across categories and how deep you are into
pagination, so the text window around an entry sometimes lands on real
content and sometimes lands on nothing usable (a null is written in that
case, never garbage -- see scrapers/unigo.py's clean_description()). A
scholarship's own page doesn't have that problem: it's one entity on the
page, not 20-25 interleaved cards plus a sidebar widget, so a generic
"strip the page chrome, keep the real paragraphs" approach is much more
reliable here even without hand-tuning it to Unigo's exact template.

This only touches rows that are CURRENTLY missing a description, so
re-running it later doesn't redo work that already succeeded, and running
scrapers/unigo.py (main.py) again afterward won't erase this (see the
COALESCE fix in db/database.py's upsert).

Usage:
    python enrich_descriptions.py              # fill in every missing row
    python enrich_descriptions.py --limit 5    # just the first 5 (quick test
                                                # before committing to a full run)
"""

import argparse
import time

import requests
from bs4 import BeautifulSoup

from db.database import get_connection

BASE_URL = "https://www.unigo.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
REQUEST_DELAY = 5  # same crawl-delay as scrapers/unigo.py's listing scraper

# Strip these outright -- they're never going to contain the scholarship's
# own description, only site chrome (nav bars, ad scripts, footers, etc).
NOISE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form"]

# Also strip any element whose class/id suggests it's chrome rather than
# article content. This is a generic heuristic (common across WordPress-
# style themes, which Unigo's markup looks like based on the "wp-content"
# paths seen in earlier garbage output) rather than something tuned to
# Unigo's exact template, since I can't see this page's raw HTML directly
# from here -- only you, running this on your own machine, can.
NOISE_CLASS_KEYWORDS = (
    "footer", "sidebar", "nav", "menu", "widget", "comment", "share",
    "social", "related", "advert", "breadcrumb", "cookie", "promo",
)

# Same backstop as scrapers/unigo.py -- if a noise element slips through
# anyway, don't let a paragraph containing one of these into the result.
GARBAGE_MARKERS = (
    "Our Scholarships", "footer-section-item", "googletag", "ALL RIGHTS RESERVED",
    "DFP SCRIPT", "jQuery", "wp-content", "adsbygoogle", "«", "»",
    # Seen on real detail pages: an ad-network legal disclaimer block and a
    # banner CTA, both boilerplate repeated on every page, not anything
    # about the specific scholarship.
    "EducationDynamics", "Sponsored Ad", "Sponsored Listings", "Sponsored Results",
    "Sign Up For Access to", "Your trust is our priority",
)

MIN_PARAGRAPH_CHARS = 40
MAX_DESCRIPTION_CHARS = 2000


def extract_main_text(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")

    for tag_name in NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # A second pass needs find_all(True) (every remaining tag) rather than
    # being folded into the loop above, since decomposing a parent while
    # iterating its ancestors' find_all results can skip siblings.
    # find_all(True) returns a list that includes descendants of tags we
    # may decompose earlier in this same loop -- decompose() recursively
    # detaches and blanks out its children too (their .attrs becomes
    # None), so a child visited later in this same list needs a guard,
    # otherwise tag.get(...) crashes on an already-decomposed tag.
    for tag in soup.find_all(True):
        if tag.attrs is None:
            continue
        classes = " ".join(tag.get("class") or []).lower()
        tag_id = (tag.get("id") or "").lower()
        if any(kw in classes or kw in tag_id for kw in NOISE_CLASS_KEYWORDS):
            tag.decompose()

    paragraphs = []
    for p in soup.find_all(["p", "li"]):
        text = p.get_text(" ", strip=True)
        if len(text) >= MIN_PARAGRAPH_CHARS and not any(m in text for m in GARBAGE_MARKERS):
            paragraphs.append(text)

    if not paragraphs:
        return None

    return " ".join(paragraphs)[:MAX_DESCRIPTION_CHARS]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only process this many rows -- use this first to sanity-check "
             "a handful of results before committing to a full run.",
    )
    args = parser.parse_args()

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, source, link FROM scholarships WHERE description IS NULL ORDER BY id"
    ).fetchall()
    if args.limit:
        rows = rows[: args.limit]

    print(f"{len(rows)} rows are missing a description. Visiting each one's own page...")
    print(f"(This is rate-limited to one request per {REQUEST_DELAY}s, same as the "
          f"listing scraper, so {len(rows)} rows will take roughly "
          f"{len(rows) * REQUEST_DELAY // 60} minutes.)\n")

    updated = 0
    for i, row in enumerate(rows, start=1):
        row_id, source, link = row["id"], row["source"], row["link"]
        url = BASE_URL + link if source == "unigo" else link
        print(f"[{i}/{len(rows)}] {url}")

        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
        except requests.exceptions.RequestException as e:
            print(f"  request failed: {e}, skipping this one")
            time.sleep(REQUEST_DELAY)
            continue

        if response.status_code != 200:
            print(f"  got status {response.status_code}, skipping this one")
            time.sleep(REQUEST_DELAY)
            continue

        text = extract_main_text(response.text)
        if text:
            conn.execute(
                "UPDATE scholarships SET description = ?, eligibility = ? WHERE id = ?",
                (text, text, row_id),
            )
            conn.commit()
            updated += 1
            print(f"  found it ({len(text)} chars)")
        else:
            print("  still nothing usable on this page")

        time.sleep(REQUEST_DELAY)

    print(f"\nDone. Filled in {updated} of {len(rows)} previously-missing descriptions.")
    conn.close()


if __name__ == "__main__":
    main()
