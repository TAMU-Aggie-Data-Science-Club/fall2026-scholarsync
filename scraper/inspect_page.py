"""
Sanity-check tool: scrapes just ONE page of ONE category and prints what
it found, so you can compare it against the real page in your browser
before trusting a full run across all categories and pages.

Why this exists: I built the Unigo parser from text I'd already pulled
from the site, not from its raw HTML, so it's pattern-matching on labels
like "Award Amount" and "Deadline" rather than exact CSS classes. That's
more resilient to small site changes, but you should still check its
first results against the real page once, which is exactly what this
script is for.

Usage:
    python inspect_page.py
"""

from scrapers.unigo import UnigoScraper, CATEGORY_URLS

import requests

category = "computer-science"
url = CATEGORY_URLS[category]

scraper = UnigoScraper()
response = requests.get(url, headers={
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
})
print(f"Fetched {url} -> status {response.status_code}\n")

results = scraper._parse_listing_page(response.text, category, url)
print(f"Found {len(results)} scholarships on this page.\n")

for i, r in enumerate(results[:5], start=1):
    print(f"--- #{i} ---")
    for key, value in r.items():
        print(f"  {key}: {value}")
    print()

if len(results) > 5:
    print(f"... and {len(results) - 5} more (not printed here)")

print(
    "\nOpen the URL above in your browser and compare these first few "
    "entries against what's really there. If names/amounts/deadlines look "
    "right, the full scrape (python main.py) should be trustworthy. If "
    "something's off (missing deadlines, wrong amounts, etc.), tell me "
    "what you're seeing and I'll fix the parsing."
)
