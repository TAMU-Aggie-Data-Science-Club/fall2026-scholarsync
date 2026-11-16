# ScholarSync Scraper

Scrapes scholarship listings (name, amount, deadline, eligibility, description, link)
into a local SQLite database, with CSV export for anyone who wants a spreadsheet.

## Setup

1. Install Python 3.10+ if you don't have it.
2. In this folder, install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Running it

```
python main.py
```

This scrapes every registered site and saves results into `data/processed/scholarships.db`:

| Source | How it finds scholarships | What it keeps |
|---|---|---|
| `unigo` | CS, STEM and Engineering listing pages | everything listed |
| `scholarships.com` | the site's sitemap (~4,700 scholarship pages) | deadline not yet passed (or no fixed date) |
| `bold.org` | the site's sitemap (~3,500 pages, most already closed) | still-open scholarships only |

A full run visits thousands of pages with a polite 2-second pause between
requests, so it takes a few hours. Useful options:

```
python main.py --only bold.org --limit 10       # quick test: 10 pages of one site
python main.py --only scholarships.com          # one site, full scrape
python main.py --include-closed                 # also keep past-deadline scholarships
```

Re-running `main.py` later is safe -- it won't create duplicate rows. It
updates existing scholarships (in case an amount or deadline changed) and
adds new ones.

## Checking the results

Before trusting a full run, sanity-check the parser against the real page:

```
python inspect_page.py
```

This scrapes just one page and prints the first 5 results so you can compare
them against what's actually on unigo.com in your browser. See "A note on
how this was built" below for why this check matters.

To get a spreadsheet of everything in the database:

```
python export_csv.py
```

## Project structure

```
scholarsync-scraper/
├── scrapers/
│   ├── base_scraper.py      # shared interface every site scraper follows
│   ├── http_utils.py        # shared request + retry helper
│   ├── unigo.py             # Unigo (requests + BeautifulSoup)
│   ├── scholarships_com.py  # Scholarships.com (sitemap + detail pages)
│   └── bold_org.py          # Bold.org (sitemap + JSON embedded in each page)
├── db/
│   ├── schema.sql        # table definition
│   ├── database.py       # SQLite read/write helpers
├── main.py                # runs all registered scrapers, saves to db
├── export_csv.py          # dumps the db to CSV
├── enrich_descriptions.py # fills in missing Unigo descriptions from detail pages
├── filter_scholarships.py # filters the db (e.g. by deadline window)
└── inspect_page.py        # sanity-check tool, see above
```

## Why SQLite instead of Selenium / a bigger database

- **SQLite, not a server database:** it's a single file, nothing to install
  or run, and still queryable later from a matching engine. `export_csv.py`
  covers anyone who just wants a spreadsheet.
- **requests + BeautifulSoup, not Selenium, for Unigo specifically:**
  Unigo's scholarship listing pages are server-rendered HTML with no
  login wall, so a real browser isn't needed -- it's slower and more
  fragile than it needs to be. Selenium is still in `requirements.txt`
  for when the team adds a site that's JavaScript-rendered or needs
  clicking through a login/search flow.

## Adding a new site

1. Check that site's `robots.txt` (e.g. `sitename.com/robots.txt`) to see
   what's allowed, and note any `Crawl-delay`.
2. Look at a listing page in your browser's "View Page Source" (not just
   the rendered page) to see if the data is in the raw HTML (use requests
   + BeautifulSoup) or only appears after JavaScript runs (use Selenium).
3. Create `scrapers/<sitename>.py`, subclass `BaseScraper` (see
   `base_scraper.py`), and implement `scrape()` to return a list of dicts
   matching the columns in `db/schema.sql`.
4. Register your new scraper in `main.py`'s `SCRAPERS` list.

## A note on how this was built

The Unigo parser was written from page content I'd already fetched through
a text-extraction tool, not from the site's raw HTML -- so rather than
targeting exact CSS class names (which break the moment a site tweaks its
design), it finds each scholarship by its link pattern and then reads the
surrounding text with regular expressions, matching the literal labels
Unigo uses ("Award Amount", "Awards", "Deadline"). This should be more
resilient to small layout changes, but it hasn't been run end-to-end
against the live site yet. **Run `inspect_page.py` first** and check the
first few results against the real page before kicking off a full scrape,
and let me know what you see if anything looks off (missing fields, wrong
amounts, etc.) so the parsing can be adjusted.

## Known gaps / things to decide as a team

- `deadline_date` (a clean ISO date) is left blank on purpose: Unigo's
  listing pages show deadlines like "Feb 15" with no year, and guessing
  the year wrong is worse than leaving it blank. The scholarship's own
  detail page (linked in `link`) usually has the full date if you need it.
- `eligibility` and `description` currently hold the same text, since
  Unigo's listing page gives one paragraph that serves as both. If you
  want them split apart (e.g. "must be a CS major, GPA 3.0+" pulled out
  separately from a general description), that would need scraping each
  scholarship's own detail page too, which means ~20x more requests per
  category page. Worth discussing with your team given the 5-second
  crawl delay.
- Only 3 categories are registered right now (`scrapers/unigo.py`'s
  `CATEGORY_URLS`). Add more by browsing unigo.com/scholarships/by-major
  or /by-type and copying category URLs in.
