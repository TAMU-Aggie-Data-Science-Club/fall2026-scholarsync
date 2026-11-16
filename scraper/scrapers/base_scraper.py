"""
Shared interface every site scraper follows.

Why this exists: "as many sites as possible" really means "many
individual scrapers," since every scholarship site has its own page
layout, pagination style, and (sometimes) anti-bot measures. This base
class is the one thing they all have in common, so main.py can run
every scraper the same way without knowing the details of any one site.

To add a new site:
1. Create scrapers/<sitename>.py
2. Make a class that inherits from BaseScraper
3. Implement scrape() to return a list of dicts matching the schema
   in db/schema.sql (name, link, amount_text, etc. -- see UnigoScraper
   for a full example)
4. Register it in main.py's SCRAPERS list
"""

from abc import ABC, abstractmethod
import time


class BaseScraper(ABC):
    # Override in each subclass: the value saved in the `source` column
    # (e.g. "unigo"), so we can tell scholarships apart by where they came from.
    source_name = None

    # Polite default delay (in seconds) between requests to the same site.
    # Override per-site based on that site's robots.txt Crawl-delay if it
    # specifies one -- Unigo's is 5 seconds, so UnigoScraper sets this to 5.
    request_delay = 2

    @abstractmethod
    def scrape(self) -> list[dict]:
        """
        Run the full scrape for this site and return a list of dicts.
        Each dict should have these keys (None is fine for any you can't find):
            name, amount_text, amount_value, num_awards,
            deadline_text, deadline_date, eligibility, description,
            link, category
        (`source` is added automatically by main.py, not by the scraper itself.)
        """
        raise NotImplementedError

    def polite_sleep(self):
        """Call this between page requests so we don't hammer the site's server."""
        time.sleep(self.request_delay)
