"""
Scraper for Unigo's scholarship listing pages (unigo.com/scholarships/...).

Verified before writing this:
- robots.txt (unigo.com/robots.txt) allows scraping /scholarships/* listing
  pages, and asks for a 5-second crawl delay, which request_delay below respects.
  It disallows /scholarships/external/*/application and a few admin paths,
  which this scraper never touches.
- The listing pages are server-rendered HTML (view-source works, no login
  wall), so requests + BeautifulSoup is enough -- no Selenium/browser needed.
- Each page lists ~20 scholarships with pagination via a `?paged=N` query
  param.

Each category is a separate listing page. CATEGORY_URLS below has a
starter list; add more by browsing unigo.com/scholarships/by-major (or
/by-type, /merit-based, etc.) and copying the URL path.

v2 fixes (after a real run on 2026-10-22 surfaced two bugs):
1. The original link filter checked whether "/scholarships/" appeared
   ANYWHERE in an <a> tag's href, including its ?utm_term=... tracking
   query string. Nearly every nav/footer link on the page carries a
   utm_term matching the current category path, so almost all of them
   false-positived as "scholarships" (nav items like "Log In", "Weird
   Scholarships", etc. ended up in the database). Fixed by parsing the
   URL properly (urlparse) and checking only the PATH, and requiring it
   to be a child of this category's own listing path specifically.
2. The original description/eligibility extraction climbed a fixed
   number of DOM ancestor levels per entry, which sometimes pulled in
   text from a neighboring scholarship card, leaving some entries with
   a blank description. Fixed by bounding each entry's text to what's
   between its own heading link and the next literal "Read More" text
   node in the document, which is a reliable per-card boundary.
3. Added an early-stop when a page returns zero scholarships we haven't
   already seen in this category (instead of only the 50-page safety
   cap) -- some sites keep returning 200 OK with repeated content past
   the real last page, which wasted a lot of time blowing through the
   cap on every category.
"""

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

# Add more categories here as you want broader coverage. Each one is scraped
# as its own set of paginated pages, so more categories = more scholarships,
# but also more total requests (and more runtime, since we sleep 5s/request).
CATEGORY_URLS = {
    "computer-science": "https://www.unigo.com/scholarships/by-major/computer-science-scholarships",
    "stem": "https://www.unigo.com/scholarships/by-major/stem-scholarships",
    "engineering": "https://www.unigo.com/scholarships/by-major/engineering-scholarships",
}

HEADERS = {
    # A real browser User-Agent. Unigo's robots.txt doesn't require this,
    # but some sites block requests with no User-Agent at all.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Matches "$16,000" style amounts.
AMOUNT_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")
# Matches "8 Awards" or "1 Award" (but not "$16,000 Award Amount", hence \b before digit).
NUM_AWARDS_RE = re.compile(r"\b(\d+)\s+Awards?\b")
# Matches "Feb 15 Deadline" or "May 1 Deadline".
DEADLINE_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}\b"
)
READ_MORE_RE = re.compile(r"^\s*Read More\s*$")

# Telltale fragments that only show up when the per-entry text window has
# bled into page chrome (footer, ad scripts, the pagination/sidebar widget)
# instead of landing on real scholarship text. Different categories and
# different depths of pagination render Unigo's listing cards slightly
# differently, so this heuristic sometimes still fails -- rather than ship
# whatever garbage it grabbed, we null the field out instead.
GARBAGE_MARKERS = (
    "Our Scholarships", "footer-section-item", "googletag", "ALL RIGHTS RESERVED",
    "DFP SCRIPT", "jQuery", "wp-content", "adsbygoogle", "«", "»",
    "Scholarship Providers", "End Col-md", "End Row Here",
)


def clean_description(text: str | None) -> str | None:
    """Returns None instead of text that's clearly page chrome rather than
    a real scholarship description -- either a known garbage marker, or
    just the leftover "View Scholarships" button label with nothing else."""
    if not text:
        return None
    if text.strip() in ("View Scholarships", "View Scholarship"):
        return None
    if any(marker in text for marker in GARBAGE_MARKERS):
        return None
    return text


def parse_amount(text: str) -> float | None:
    match = AMOUNT_RE.search(text)
    if not match:
        return None
    return float(match.group(0).replace("$", "").replace(",", ""))


def parse_num_awards(text: str) -> int | None:
    match = NUM_AWARDS_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def parse_deadline(text: str) -> tuple[str | None, str | None]:
    """Returns (deadline_text, deadline_date). deadline_date is None if we
    can't confidently resolve a year (Unigo's listing text has no year,
    e.g. just "Feb 15"), since guessing the year wrong is worse than
    leaving it blank -- open the scholarship's own page to confirm the year."""
    match = DEADLINE_RE.search(text)
    if not match:
        return None, None
    return match.group(0), None


class UnigoScraper(BaseScraper):
    source_name = "unigo"
    request_delay = 5  # matches Unigo's robots.txt Crawl-delay: 5

    def scrape(self) -> list[dict]:
        results = []
        for category, base_url in CATEGORY_URLS.items():
            print(f"[unigo] Scraping category: {category}")
            try:
                results.extend(self._scrape_category(category, base_url))
            except Exception as e:
                # Don't let one bad category (a parsing bug, an unexpected
                # page structure, etc.) throw away everything already
                # collected from the other categories.
                print(f"[unigo]   category '{category}' failed unexpectedly: {e}, skipping it, keeping other categories' results")
        return results

    def _scrape_category(self, category: str, base_url: str) -> list[dict]:
        results = []
        seen_links = set()  # tracks every scholarship link already found in this category
        page = 1
        while True:
            url = base_url if page == 1 else f"{base_url}?paged={page}"
            print(f"[unigo]   page {page}: {url}")

            # Network hiccups (slow page, dropped connection) shouldn't throw
            # away everything already collected for this category -- retry
            # once, then give up on just this category and keep whatever
            # pages already succeeded.
            response = None
            for attempt in (1, 2):
                try:
                    response = requests.get(url, headers=HEADERS, timeout=30)
                    break
                except requests.exceptions.RequestException as e:
                    print(f"[unigo]   request failed (attempt {attempt}/2): {e}")
                    if attempt == 2:
                        print(f"[unigo]   giving up on this category after 2 failed attempts, keeping {len(results)} already collected")
                    else:
                        self.polite_sleep()

            if response is None:
                break

            if response.status_code != 200:
                print(f"[unigo]   got status {response.status_code}, stopping this category")
                break

            page_results = self._parse_listing_page(response.text, category, base_url)

            # Only keep results we haven't already seen in this category.
            new_results = [r for r in page_results if r["link"] not in seen_links]

            if not page_results:
                print(f"[unigo]   no scholarships found on this page, stopping this category")
                break

            if not new_results:
                # Every scholarship on this page was already collected from
                # an earlier page -- this means we've gone past the real
                # last page and the site is just re-serving old content.
                print(f"[unigo]   page {page} had no NEW scholarships (likely past the last real page), stopping this category")
                break

            for r in new_results:
                seen_links.add(r["link"])
            results.extend(new_results)

            page += 1
            self.polite_sleep()

            # Safety valve in case the "no new results" check above somehow
            # doesn't trigger -- stops this category from looping forever.
            if page > 50:
                print("[unigo]   hit the 50-page safety limit, stopping this category")
                break

        return results

    def _parse_listing_page(self, html: str, category: str, base_url: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")

        # Only accept links that are children of THIS category's own listing
        # path, e.g. "/scholarships/by-major/engineering-scholarships/<slug>".
        # This is checked against the URL PATH only (via urlparse), not the
        # full href string -- the earlier version accidentally matched on
        # tracking query params (?utm_term=/scholarships/...), which caused
        # nearly every nav/footer link on the page to be misread as a
        # scholarship. That bug is why v1 picked up junk rows like "Log In"
        # and "Weird Scholarships".
        category_path = urlparse(base_url).path.rstrip("/") + "/"

        heading_links = []
        for a in soup.find_all("a", href=True):
            href_path = urlparse(a["href"]).path
            if not href_path.startswith(category_path):
                continue
            if href_path == category_path.rstrip("/"):
                continue  # this is a link back to the category page itself
            text = a.get_text(strip=True)
            if text in ("", "Read More", "View Scholarship"):
                continue  # we want the heading link (real name), not a generic button
            heading_links.append((href_path, a))

        # De-duplicate by path: a scholarship's name can appear as both a
        # heading link and (sometimes) a linked image, pointing to the same page.
        seen_paths = set()
        unique_entries = []
        for href_path, a in heading_links:
            if href_path in seen_paths:
                continue
            seen_paths.add(href_path)
            unique_entries.append((href_path, a))

        # Hard cap on how much text one entry's block_text can ever hold.
        # This is a backstop, not the real boundary logic below -- if the
        # real boundary (next heading link, or Read More as a fallback)
        # somehow still fails to match, this keeps a bug from dumping
        # the entire rest of the page (footer links, legal text, ad
        # scripts) into one row instead of just corrupting one field.
        MAX_BLOCK_CHARS = 1500

        results = []
        for i, (link, a) in enumerate(unique_entries):
            name = a.get_text(strip=True)

            # Bound this entry's text to what's between its own heading
            # link and the START of the NEXT entry's heading link -- that
            # next heading link is the real, reliable end of this card,
            # since unique_entries is already in document order. v2 tried
            # to bound on the literal "Read More" text instead, but that
            # button's text isn't always one clean exact string (it can be
            # split across nested elements), so find_next() sometimes
            # skipped right past it and matched some unrelated "Read More"
            # occurrence much further down the page -- which is how one
            # entry's description ended up containing other scholarships,
            # the pagination widget, footer links, and ad script code.
            # Only the LAST entry on a page has no next entry to bound
            # against, so for that one case we fall back to the literal
            # "Read More" node, with the character cap above as a backstop
            # in case that fallback also doesn't find a match.
            next_a = unique_entries[i + 1][1] if i + 1 < len(unique_entries) else None
            stop_node = next_a if next_a is not None else a.find_next(string=READ_MORE_RE)

            # a.next_elements is a raw, unfiltered walk through every
            # subsequent node (both tags and text) in document order --
            # unlike find_all_next(), which (with no `string=True`) only
            # ever hands back tags and silently skips every text node,
            # which is why this returned nothing at all on the first try.
            texts = []
            total_len = 0
            for node in a.next_elements:
                if stop_node is not None and node is stop_node:
                    break
                if isinstance(node, str):
                    stripped = node.strip()
                    if stripped:
                        texts.append(stripped)
                        total_len += len(stripped)
                        if total_len > MAX_BLOCK_CHARS:
                            break
            block_text = " ".join(texts)[:MAX_BLOCK_CHARS]

            amount_text_match = AMOUNT_RE.search(block_text)
            deadline_text, deadline_date = parse_deadline(block_text)

            # The description is whatever text remains after the deadline
            # marker (since everything before that is just the name/amount/
            # awards labels we already parsed out separately).
            description = None
            if deadline_text:
                idx = block_text.find(deadline_text)
                if idx != -1:
                    remainder = block_text[idx + len(deadline_text):].strip(" .")
                    # Unigo's card layout puts the literal caption word
                    # "Deadline" AFTER the date itself (e.g. "Feb 15
                    # Deadline This award is available..."), so once we've
                    # sliced past the date, that leftover label word is
                    # still sitting at the very front of the description.
                    remainder = re.sub(r"^Deadline\s*", "", remainder, flags=re.IGNORECASE)
                    # Trailing boilerplate from the card's own buttons,
                    # now included since we bound on the next heading
                    # link rather than on "Read More" itself.
                    remainder = re.sub(r"\s*Read More\s*View Scholarship\s*$", "", remainder, flags=re.IGNORECASE)
                    description = remainder.strip(" .") or None
            elif block_text:
                # No deadline found -- fall back to the whole block, minus the name.
                description = block_text.replace(name, "", 1).strip(" .") or None

            description = clean_description(description)

            results.append({
                "name": name,
                "amount_text": amount_text_match.group(0) if amount_text_match else None,
                "amount_value": parse_amount(block_text),
                "num_awards": parse_num_awards(block_text),
                "deadline_text": deadline_text,
                "deadline_date": deadline_date,
                "eligibility": description,  # Unigo's listing description IS the eligibility blurb
                "description": description,
                "link": link,
                "category": category,
            })

        return results
