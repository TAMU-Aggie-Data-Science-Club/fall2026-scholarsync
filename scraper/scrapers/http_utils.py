"""
Small shared HTTP helper used by the newer scrapers (scholarships_com.py,
bold_org.py). Same idea as the retry logic inside unigo.py, pulled out so
each new scraper doesn't have to copy it.
"""

import time

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_session = requests.Session()
_session.headers.update(HEADERS)


def fetch(url: str, tag: str, retries: int = 2, retry_wait: float = 3) -> requests.Response | None:
    """GET a URL with a retry on network errors. Returns the Response
    (any status code), or None if every attempt failed at the network level."""
    for attempt in range(1, retries + 1):
        try:
            return _session.get(url, timeout=30)
        except requests.exceptions.RequestException as e:
            print(f"[{tag}]   request failed (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(retry_wait)
    return None
