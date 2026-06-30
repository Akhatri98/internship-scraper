import json
import time
import requests

# Fallback if collinfo lookup fails; latest_index() prefers the newest live crawl.
DEFAULT_INDEX = "https://index.commoncrawl.org/CC-MAIN-2026-25-index"
_COLLINFO = "https://index.commoncrawl.org/collinfo.json"
_UA = {"User-Agent": "job-bot/0.1 (+https://github.com/Akhatri98/Job-Bot)"}


def latest_index(session=None) -> str:
    """Newest crawl's CDX endpoint, so the monthly run auto-tracks new releases."""
    try:
        r = (session or requests).get(_COLLINFO, headers=_UA, timeout=30)
        r.raise_for_status()
        return r.json()[0]["cdx-api"]
    except Exception:  # noqa: BLE001
        return DEFAULT_INDEX


def num_pages(pattern: str, index: str, session=None, retries=4) -> int:
    """Page count for a pattern. Retries transient failures so a hiccup doesn't
    silently skip a whole domain in the monthly run (CDX can be flaky)."""
    sess = session or requests
    for attempt in range(retries):
        try:
            r = sess.get(index, params={"url": pattern, "output": "json", "showNumPages": "true"},
                         headers=_UA, timeout=90)
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(1.0 * (2 ** attempt))
            continue
        if r.status_code == 404:
            return 0  # genuinely no captures for this pattern
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(1.0 * (2 ** attempt))
            continue
        if r.status_code != 200:
            return 0
        try:
            return int(r.json().get("pages", 0))
        except (ValueError, json.JSONDecodeError):
            return 0
    return 0


def iter_urls(pattern: str, index: str, max_pages=None, session=None, delay=0.5, retries=3):
    """Yield matching URLs for a domain pattern, paging through the index."""
    sess = session or requests.Session()
    pages = num_pages(pattern, index, sess)
    if max_pages is not None:
        pages = min(pages, max_pages)

    for page in range(pages):
        r = None
        for attempt in range(retries):
            try:
                r = sess.get(index, params={"url": pattern, "output": "json", "fl": "url",
                                            "filter": "status:200", "page": page},
                             headers=_UA, timeout=120)
            except (requests.ConnectionError, requests.Timeout):
                time.sleep(1.0 * (2 ** attempt))
                continue
            if r.status_code >= 500:
                time.sleep(1.0 * (2 ** attempt))
                continue
            break
        if r is None or r.status_code != 200:
            continue
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                url = json.loads(line).get("url")
            except json.JSONDecodeError:
                continue
            if url:
                yield url
        time.sleep(delay)
