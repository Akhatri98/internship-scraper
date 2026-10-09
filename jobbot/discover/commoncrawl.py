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


class IndexUnavailable(RuntimeError):
    """The CDX index couldn't answer for a pattern even after retries. Kept distinct
    from "0 pages" on purpose: returning 0 made an index outage look exactly like a
    quiet month ("+0 new" everywhere, green run) — see run_discover."""


def num_pages(pattern: str, index: str, session=None, retries=4) -> int:
    """Page count for a pattern. Retries transient failures so a hiccup doesn't
    silently skip a whole domain in the monthly run (CDX can be flaky); raises
    IndexUnavailable if the index still can't answer."""
    sess = session or requests
    last = "no response"
    for attempt in range(retries):
        try:
            r = sess.get(index, params={"url": pattern, "output": "json", "showNumPages": "true"},
                         headers=_UA, timeout=90)
        except (requests.ConnectionError, requests.Timeout) as e:
            last = type(e).__name__
            time.sleep(1.0 * (2 ** attempt))
            continue
        if r.status_code == 404:
            return 0  # genuinely no captures for this pattern
        if r.status_code == 429 or r.status_code >= 500:
            last = f"HTTP {r.status_code}"
            time.sleep(1.0 * (2 ** attempt))
            continue
        if r.status_code != 200:
            raise IndexUnavailable(f"{pattern}: page count got HTTP {r.status_code}")
        try:
            return int(r.json().get("pages", 0))
        except (ValueError, json.JSONDecodeError):
            raise IndexUnavailable(f"{pattern}: page count returned a non-JSON body") from None
    raise IndexUnavailable(f"{pattern}: page count failed after {retries} tries ({last})")


def iter_urls(pattern: str, index: str, max_pages=None, session=None, delay=0.5, retries=3):
    """Yield matching URLs for a domain pattern, paging through the index.

    A page that still fails after retries is skipped so the rest of the domain is
    read, but the generator raises IndexUnavailable once it's done — a partial
    sweep must not pass for a complete one."""
    sess = session or requests.Session()
    pages = num_pages(pattern, index, sess)
    if max_pages is not None:
        pages = min(pages, max_pages)

    failed = 0
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
            failed += 1
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
    if failed:
        raise IndexUnavailable(f"{pattern}: {failed}/{pages} pages unreadable")
