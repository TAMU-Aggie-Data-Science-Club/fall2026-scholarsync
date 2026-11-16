"""
Scraper for Bold.org (bold.org/scholarships/<slug>/).

Verified before writing this (2026-11-06):
- robots.txt allows scholarship pages but has `Disallow: /*?*`, i.e. no
  URL with a query string. This scraper never adds "?" to any URL
  (pagination isn't needed because we use the sitemap instead).
- /sitemap.xml lists every scholarship page (~3,600), including many that
  have already CLOSED. We keep only scholarships that are still open.
- Bold.org is a Next.js site. The visible page is built from a JSON record
  that's embedded in the HTML inside `self.__next_f.push([1, "..."])`
  script chunks (Next.js's "RSC payload"). Reading that JSON gives us exact,
  structured data -- e.g. endDate "2026-11-24T23:59:59Z" and eligibility as
  label/value pairs ("Field of Study: Technology, arts, or business") --
  instead of guessing from page text. So: requests + json, no Selenium.

How the JSON is pulled out (see _extract_record):
1. Join all the __next_f chunks into one string.
2. Find `"slug":"<this page's slug>"` -- that sits inside the scholarship's
   own record.
3. Walk outward to the record's enclosing { ... } and json.loads() it.
4. The long write-up (`content`) is stored separately as a reference like
   "$54", which points at a text row "54:T<hex length>,<html>" elsewhere in
   the payload; _resolve_ref() follows it.
"""

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.http_utils import fetch

SITEMAP_URL = "https://bold.org/sitemap.xml"
# /scholarships/<slug>/ -- but NOT the /scholarships/by-major/... category
# pages, and NOT the numbered listing pages (/scholarships/10/, /100/, ...)
# that the sitemap also includes. Those are ~4MB pages listing many
# scholarships at once, not one scholarship's page.
DETAIL_PATH_RE = re.compile(r"^/scholarships/(?!by-)(?!\d+/$)[^/]+/$")
CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')


def _payload(html: str) -> str:
    return "".join(json.loads(f'"{m}"') for m in CHUNK_RE.findall(html))


def _enclosing_object(s: str, idx: int) -> str | None:
    """Return the text of the innermost {...} JSON object that contains s[idx]."""
    depth, i = 0, idx
    while i >= 0:
        c = s[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                break
            depth -= 1
        i -= 1
    if i < 0:
        return None
    start, depth, in_str, esc = i, 0, False, False
    for j in range(start, len(s)):
        c = s[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : j + 1]
    return None


def _extract_record(payload: str, slug: str) -> dict | None:
    """Find this scholarship's own JSON record. The page also embeds records
    for related scholarships, so we match on the exact slug and pick the
    candidate that actually has an endDate (the full record)."""
    best = None
    needle = re.compile(r'"slug"\s*:\s*"' + re.escape(slug) + '"')
    for m in needle.finditer(payload):
        text = _enclosing_object(payload, m.start())
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if "endDate" in obj and (best is None or len(obj) > len(best)):
            best = obj
    return best


def _resolve_ref(payload: str, value):
    """Follow an RSC text reference like "$54" to its text row."""
    if not (isinstance(value, str) and re.fullmatch(r"\$[0-9a-f]+", value)):
        return value
    ref = value[1:]
    m = re.search(rf"(?:^|\n){ref}:T([0-9a-f]+),", payload)
    if not m:
        return None
    n_bytes = int(m.group(1), 16)  # length is in UTF-8 bytes, not characters
    raw = payload[m.end():].encode("utf-8")[:n_bytes]
    return raw.decode("utf-8", errors="ignore")


def _html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    text = BeautifulSoup(html, "lxml").get_text(" ")
    return re.sub(r"\s+", " ", text).strip() or None


def _money(n) -> str:
    return f"${n:,.0f}" if float(n).is_integer() else f"${n:,.2f}"


def record_to_row(rec: dict, payload: str, link: str) -> dict:
    awards = [a for a in (rec.get("awardAmounts") or []) if isinstance(a, (int, float))]
    total = rec.get("totalAwardAmount") or rec.get("fundingRequestAmount")
    if awards:
        amount_value = float(max(awards))
        amount_text = _money(awards[0]) if len(set(awards)) == 1 else " / ".join(_money(a) for a in awards)
        num_awards = len(awards)
    elif isinstance(total, (int, float)):
        amount_value, amount_text, num_awards = float(total), _money(total), rec.get("numberOfAwards")
    else:
        amount_value = amount_text = num_awards = None

    end = rec.get("endDate")
    deadline_date = end[:10] if end else None
    if rec.get("isRollingDeadline"):
        deadline_text = "Rolling"
    elif end:
        deadline_text = datetime.fromisoformat(end.replace("Z", "+00:00")).strftime("%B %d, %Y")
    else:
        deadline_text = None

    elig_items = [
        f"{e.get('label')}: {e.get('value')}"
        for e in (rec.get("eligibility") or [])
        if isinstance(e, dict) and e.get("label") and e.get("value")
    ]
    eligibility = "; ".join(elig_items) or None

    summary = rec.get("description")
    full = _html_to_text(_resolve_ref(payload, rec.get("content")))
    description = " ".join(p for p in (summary, full) if p) or None

    return {
        "name": rec.get("name"),
        "amount_text": amount_text,
        "amount_value": amount_value,
        "num_awards": num_awards,
        "deadline_text": deadline_text,
        "deadline_date": deadline_date,
        "eligibility": eligibility,
        "description": description,
        "link": link,
        "category": rec.get("category"),
    }


def is_open(rec: dict, now: datetime) -> bool:
    if rec.get("status") not in (None, "_published"):
        return False
    if rec.get("isRollingDeadline"):
        return True
    end = rec.get("endDate")
    if not end:
        return False
    return datetime.fromisoformat(end.replace("Z", "+00:00")) >= now


class BoldOrgScraper(BaseScraper):
    source_name = "bold.org"
    request_delay = 2  # robots.txt sets no Crawl-delay; 2s is our polite default

    def __init__(self, max_items: int | None = None, include_closed: bool = False):
        # max_items: stop after visiting this many pages (quick test runs).
        # include_closed: also keep scholarships whose deadline has passed.
        self.max_items = max_items
        self.include_closed = include_closed

    def _get_sitemap_links(self) -> list[str]:
        resp = fetch(SITEMAP_URL, self.source_name, retries=4, retry_wait=10)
        if resp is None or resp.status_code != 200:
            raise RuntimeError(f"could not load sitemap ({resp.status_code if resp else 'network error'})")
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", resp.text)
        links = []
        for l in locs:
            path = urlparse(l).path
            if not path.endswith("/"):
                path += "/"
            if DETAIL_PATH_RE.match(path) and "?" not in l:
                links.append(f"https://bold.org{path}")
        return sorted(set(links))

    def scrape(self) -> list[dict]:
        links = self._get_sitemap_links()
        print(f"[{self.source_name}] sitemap lists {len(links)} scholarship pages (many are closed)")
        if self.max_items:
            links = links[: self.max_items]
            print(f"[{self.source_name}] --limit set: visiting only the first {len(links)}")

        now = datetime.now(timezone.utc)
        results, closed, failed = [], 0, 0
        for i, link in enumerate(links, 1):
            resp = fetch(link, self.source_name)
            self.polite_sleep()
            if resp is None or resp.status_code != 200:
                failed += 1
                status = resp.status_code if resp is not None else "network error"
                hint = " (blocked / rate-limited)" if status in (403, 429, 503) else ""
                print(f"[{self.source_name}]   got {status}{hint} on {link}")
                continue
            # If the page redirected (e.g. a renamed scholarship), the record
            # on the page uses the NEW slug, so read it from the final URL.
            slug = urlparse(resp.url).path.strip("/").split("/")[-1]
            try:
                payload = _payload(resp.text)
                rec = _extract_record(payload, slug)
                if rec is None:
                    failed += 1
                    print(f"[{self.source_name}]   couldn't find scholarship data on {link} (page layout may have changed)")
                    continue
                if not self.include_closed and not is_open(rec, now):
                    closed += 1
                    continue
                results.append(record_to_row(rec, payload, resp.url))
            except Exception as e:
                print(f"[{self.source_name}]   parse error on {link}: {e}")
                failed += 1
            if i % 25 == 0:
                print(f"[{self.source_name}]   {i}/{len(links)} pages done ({len(results)} open saved, {closed} closed skipped, {failed} failed)")

        print(f"[{self.source_name}] finished: {len(results)} open scholarships, {closed} closed skipped, {failed} failed")
        return results
