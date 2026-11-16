"""
Scraper for Scholarships.com (scholarships.com/scholarships/<slug>).

Verified before writing this (2026-11-06):
- robots.txt has NO Disallow rules and no Crawl-delay -- it only points to
  a sitemap. We still wait `request_delay` seconds between requests.
- Every scholarship page is listed in /scholarshipsitemap.xml (~4,700 URLs
  of the form https://www.scholarships.com/scholarships/<slug>).
- Pages are server-rendered HTML, so requests + BeautifulSoup is enough
  (no Selenium).
- The "by major" listing pages only ever show the top 25 scholarships and
  have no pagination, so listing pages alone would miss most of the site.
  That's why this scraper uses the sitemap to find every scholarship, and
  uses the by-major pages only to tag each scholarship with a category.

What each scholarship page gives us:
    <h1>Name</h1>
    Amount: $40,000   Deadline: January 05, 2027   Awards Available: Varies
    Eligibility Criteria: <short tags like "GPA", "Selected Major(s)">
    <h2>Scholarship Description</h2> <div> full write-up, which usually
        contains its own <h2>Eligibility Criteria</h2><ul>...</ul> </div>
The "Apply Now" button is behind a scholarships.com login, so `link` is the
scholarship's page on scholarships.com.
"""

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.http_utils import fetch

BASE = "https://www.scholarships.com"
SITEMAP_URL = f"{BASE}/scholarshipsitemap.xml"
DETAIL_PATH_RE = re.compile(r"^/scholarships/[^/]+/?$")

AMOUNT_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")
# The label/value pairs in the page's summary box, read from the page text.
SUMMARY_RE = re.compile(
    r"Amount:\s*(?P<amount>.*?)\s*Deadline:\s*(?P<deadline>.*?)\s*"
    r"Awards Available:\s*(?P<awards>.*?)\s*Eligibility Criteria:\s*(?P<criteria>.*?)\s*(?:Share:|You May Also Like)",
    re.S,
)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_deadline_date(text: str | None) -> str | None:
    """'January 05, 2027' -> '2027-01-05'. None for 'Varies', 'Rolling', etc."""
    if not text:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def parse_detail_page(html: str, link: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    h1 = soup.find("h1")
    name = _clean(h1.get_text(" ")) if h1 else None
    if not name:
        return None

    page_text = re.sub(r"\s+", " ", soup.get_text(" "))
    # Only look at text after the name, so header/login boilerplate can't match.
    after_name = page_text[page_text.find(name):] if name in page_text else page_text
    summary = SUMMARY_RE.search(after_name)

    amount_text = deadline_text = awards_text = criteria_tags = None
    if summary:
        amount_text = _clean(summary.group("amount"))
        deadline_text = _clean(summary.group("deadline"))
        awards_text = _clean(summary.group("awards"))
        criteria_tags = _clean(summary.group("criteria"))

    amount_value = None
    if amount_text:
        m = AMOUNT_RE.search(amount_text)
        if m:
            amount_value = float(m.group(0).replace("$", "").replace(",", ""))

    num_awards = int(awards_text) if awards_text and awards_text.isdigit() else None

    # Full description: the block right after the "Scholarship Description" heading.
    description = eligibility = None
    desc_h2 = soup.find(lambda t: t.name == "h2" and t.get_text(strip=True) == "Scholarship Description")
    if desc_h2:
        desc_block = desc_h2.find_next_sibling("div")
        if desc_block:
            description = _clean(desc_block.get_text(" "))
            elig_h2 = desc_block.find(lambda t: t.name in ("h2", "h3") and "eligibility" in t.get_text(strip=True).lower())
            if elig_h2:
                elig_list = elig_h2.find_next_sibling(["ul", "ol", "p"])
                if elig_list:
                    items = [_clean(li.get_text(" ")) for li in elig_list.find_all("li")] or [_clean(elig_list.get_text(" "))]
                    eligibility = "; ".join(i for i in items if i) or None

    # Fall back to the short criteria tags ("GPA, Selected Major(s), ...")
    # when the write-up has no eligibility section of its own.
    if not eligibility and criteria_tags:
        eligibility = f"Criteria considered: {criteria_tags}"

    return {
        "name": name,
        "amount_text": amount_text,
        "amount_value": amount_value,
        "num_awards": num_awards,
        "deadline_text": deadline_text,
        "deadline_date": parse_deadline_date(deadline_text),
        "eligibility": eligibility,
        "description": description,
        "link": link,
        "category": None,  # filled in from the by-major pages, see scrape()
    }


class ScholarshipsComScraper(BaseScraper):
    source_name = "scholarships.com"
    request_delay = 2  # robots.txt sets no Crawl-delay; 2s is our polite default

    def __init__(self, max_items: int | None = None, include_closed: bool = False):
        # max_items: stop after this many scholarship pages (handy for a
        # quick test run). None = scrape everything in the sitemap.
        # include_closed: also keep scholarships whose deadline has passed.
        # (Ones with no parseable date, like "Varies", are always kept.)
        self.max_items = max_items
        self.include_closed = include_closed

    def _get_sitemap_links(self) -> tuple[list[str], list[str]]:
        resp = fetch(SITEMAP_URL, self.source_name, retries=4, retry_wait=10)
        if resp is None or resp.status_code != 200:
            raise RuntimeError(f"could not load sitemap ({resp.status_code if resp else 'network error'})")
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", resp.text)
        detail_links = sorted({l.rstrip("/") for l in locs if DETAIL_PATH_RE.match(urlparse(l).path)})
        major_pages = sorted({l for l in locs if "/scholarships-by-major/" in l})
        return detail_links, major_pages

    def _category_map(self, major_pages: list[str]) -> dict[str, str]:
        """Visit each 'by major' page (top 25 per major) and remember which
        major each scholarship showed up under."""
        mapping: dict[str, str] = {}
        for url in major_pages:
            category = urlparse(url).path.rstrip("/").split("/")[-1].replace("-scholarships", "")
            resp = fetch(url, self.source_name)
            self.polite_sleep()
            if resp is None or resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                path = urlparse(a["href"]).path
                if DETAIL_PATH_RE.match(path) and a.find("h2"):
                    full = urljoin(BASE, path).rstrip("/")
                    # Keep the first major we saw it under; append others.
                    if full in mapping and category not in mapping[full].split(", "):
                        mapping[full] += f", {category}"
                    else:
                        mapping.setdefault(full, category)
        return mapping

    def scrape(self) -> list[dict]:
        detail_links, major_pages = self._get_sitemap_links()
        print(f"[{self.source_name}] sitemap lists {len(detail_links)} scholarships, {len(major_pages)} major pages")
        if self.max_items:
            detail_links = detail_links[: self.max_items]
            major_pages = major_pages[:3]
            print(f"[{self.source_name}] --limit set: scraping only the first {len(detail_links)}")

        print(f"[{self.source_name}] tagging categories from {len(major_pages)} by-major pages...")
        categories = self._category_map(major_pages)

        today = datetime.now().date().isoformat()
        results, failed, closed = [], 0, 0
        for i, link in enumerate(detail_links, 1):
            resp = fetch(link, self.source_name)
            self.polite_sleep()
            if resp is None or resp.status_code != 200:
                failed += 1
                if resp is not None and resp.status_code in (403, 429):
                    print(f"[{self.source_name}]   got {resp.status_code} (blocked / rate-limited) on {link}")
                continue
            try:
                row = parse_detail_page(resp.text, link)
            except Exception as e:
                print(f"[{self.source_name}]   parse error on {link}: {e}")
                row = None
            if row is None:
                failed += 1
                continue
            if not self.include_closed and row["deadline_date"] and row["deadline_date"] < today:
                closed += 1
                continue
            row["category"] = categories.get(link)
            results.append(row)
            if i % 25 == 0:
                print(f"[{self.source_name}]   {i}/{len(detail_links)} pages done ({len(results)} saved, {closed} past-deadline skipped, {failed} failed)")

        print(f"[{self.source_name}] finished: {len(results)} scholarships, {closed} past-deadline skipped, {failed} failed")
        return results
