import os
import csv
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional, Set

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from dotenv import load_dotenv
from serpapi import GoogleSearch

# =========================
# CONFIG
# =========================

JOB_URL_CSV = "job_url.csv"
JOB_URL_HEADER = ["source", "url", "title", "posted_time", "scraped_time"]

ENRICHED_CSV = "job_enriched.csv"
ERROR_CSV = "error.csv"

# (source, query)
QUERIES: List[Tuple[str, str]] = [
    ("ashbyhq", "intern site:jobs.ashbyhq.com"),
    ("lever", "intern site:jobs.lever.co"),
    ("greenhouse", "intern site:job-boards.greenhouse.io"),
]

# Past WEEK, 1 page per site
DATE_RANGE: Optional[str] = "week"
DATE_RANGE_TO_TBS = {
    None: None,
    "day": "qdr:d",
    "week": "qdr:w",
    "month": "qdr:m",
}
MAX_PAGES_PER_QUERY = 1  # only page 0
PAGE_SIZE = 10  # Google organic cap

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; JobScraper/1.0; +https://example.com)"
})

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

TECH_KEYWORDS = [
    "software", "developer", "engineer", "data scientist", "machine learning",
    "ml engineer", "backend", "frontend", "full stack", "cloud", "devops",
    "ai ", "artificial intelligence", "python", "java", "c++", "golang",
    "typescript", "react", "node", "sre", "site reliability",
]

FINANCE_KEYWORDS = [
    "trader", "trading", "quant", "quantitative", "risk", "portfolio",
    "investment", "asset management", "hedge fund", "equity research",
    "investment banking", "private equity", "market making", "derivatives",
    "fixed income", "structured products",
]

BUSINESS_KEYWORDS = [
    "business analyst", "operations", "strategy", "consultant", "consulting",
    "marketing", "product manager", "project manager", "bizops",
    "sales", "account executive", "customer success",
]

# =========================
# ENV / API KEY
# =========================

def get_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "SERPAPI_API_KEY not set. "
            "Create a .env file with SERPAPI_API_KEY=your_key_here."
        )
    return api_key

# =========================
# PHASE 1: URL DISCOVERY
# =========================

def ensure_job_url_csv_and_load_existing(path: str) -> Optional[Set[str]]:
    """
    - If CSV doesn't exist: print error and return None (abort).
    - If exists but empty: write header and return empty URL set.
    - Else: load existing URLs into a set.
    """
    if not os.path.exists(path):
        print(f"ERROR: '{path}' not found. Create an empty file named '{path}' first.")
        return None

    existing_urls: Set[str] = set()

    if os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(JOB_URL_HEADER)
        return existing_urls

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url")
            if url:
                existing_urls.add(url)

    return existing_urls


def append_job_url_rows(path: str, rows: List[Dict[str, str]]) -> None:
    if not rows:
        print("No new job_url rows to append.")
        return

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOB_URL_HEADER)
        for row in rows:
            writer.writerow(row)

    print(f"Appended {len(rows)} new rows to {path}.")


def search_source(
    api_key: str,
    source: str,
    query: str,
    tbs: Optional[str],
    max_pages: int,
) -> List[Dict[str, str]]:
    """
    Google Search via SerpAPI for a single (source, query).
    Past WEEK, only 1 page (max_pages=1) but generic enough to extend.

    Returns rows: {source, url, title, posted_time, scraped_time}
    """
    normalized_rows: List[Dict[str, str]] = []

    for page in range(max_pages):
        start = page * PAGE_SIZE
        print(f"  [{source}] Page {page+1}/{max_pages} (start={start})")

        params = {
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "start": start,
            "num": PAGE_SIZE,
        }

        if tbs:
            params["tbs"] = tbs

        search = GoogleSearch(params)
        data = search.get_dict()
        organic = data.get("organic_results", []) or []

        if not organic:
            print("    No organic_results; stopping for this source.")
            break

        for res in organic:
            link = res.get("link")
            title = res.get("title") or ""
            posted_time = res.get("date") or ""

            if not link:
                continue

            # extra host safety
            if source == "ashbyhq" and "jobs.ashbyhq.com" not in link:
                continue
            if source == "lever" and "jobs.lever.co" not in link:
                continue
            if source == "greenhouse" and "job-boards.greenhouse.io" not in link:
                continue

            row = {
                "source": source,
                "url": link,
                "title": title,
                "posted_time": posted_time,
                "scraped_time": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            normalized_rows.append(row)

        # Google caps organic at 10; any non-empty page is full or real last page
        if len(organic) < PAGE_SIZE:
            print("    Fewer than 10 organic results; assuming last page.")
            break

    return normalized_rows


def phase1_update_job_urls() -> None:
    existing_urls = ensure_job_url_csv_and_load_existing(JOB_URL_CSV)
    if existing_urls is None:
        return

    api_key = get_api_key()
    tbs = DATE_RANGE_TO_TBS.get(DATE_RANGE)

    all_new_rows: List[Dict[str, str]] = []

    for source, query in QUERIES:
        print(f"Searching {source} with query {query!r} (past {DATE_RANGE})")
        rows = search_source(
            api_key=api_key,
            source=source,
            query=query,
            tbs=tbs,
            max_pages=MAX_PAGES_PER_QUERY,
        )
        print(f"  Retrieved {len(rows)} candidates for {source} before dedup.")

        for row in rows:
            url = row["url"]
            if url in existing_urls:
                continue
            existing_urls.add(url)
            all_new_rows.append(row)

    append_job_url_rows(JOB_URL_CSV, all_new_rows)

# =========================
# PHASE 2: ENRICHMENT
# =========================

def safe_get(url: str, timeout: int = 15) -> Optional[str]:
    try:
        resp = SESSION.get(url, timeout=timeout)
        if not resp.ok:
            print(f"[WARN] {url} -> HTTP {resp.status_code}")
            return None
        return resp.text
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return None


def extract_jsonld_jobposting(html: str) -> Optional[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")

    for tag in scripts:
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue

        if isinstance(data, list):
            objects = data
        elif isinstance(data, dict) and "@graph" in data:
            objects = data["@graph"]
        else:
            objects = [data]

        for obj in objects:
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type")
            if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                return obj

    return None


def normalize_day_from_date_string(s: str) -> Optional[str]:
    try:
        dt = dateparser.parse(s)
        return dt.date().isoformat()
    except Exception:
        return None


def normalize_day_from_relative(relative: str, scraped_iso: str) -> Optional[str]:
    if not relative or "ago" not in relative:
        return None

    m = re.search(r"(\d+)", relative)
    if not m:
        return None

    n = int(m.group(1))
    unit = "day"
    if "hour" in relative:
        unit = "hour"
    elif "week" in relative:
        unit = "week"
    elif "month" in relative:
        unit = "month"
    elif "year" in relative:
        unit = "year"

    try:
        scraped_dt = dateparser.parse(scraped_iso)
    except Exception:
        return None

    if unit == "hour":
        dt = scraped_dt - timedelta(hours=n)
    elif unit == "week":
        dt = scraped_dt - timedelta(weeks=n)
    elif unit == "month":
        dt = scraped_dt - timedelta(days=30 * n)
    elif unit == "year":
        dt = scraped_dt - timedelta(days=365 * n)
    else:
        dt = scraped_dt - timedelta(days=n)

    return dt.date().isoformat()


def infer_country_from_joblocation(job_location: Any) -> Optional[str]:
    if not job_location:
        return None

    locations: List[Dict[str, Any]] = []
    if isinstance(job_location, list):
        locations = [loc for loc in job_location if isinstance(loc, dict)]
    elif isinstance(job_location, dict):
        locations = [job_location]
    else:
        return None

    for loc in locations:
        addr = loc.get("address") or {}
        country = addr.get("addressCountry")
        if country:
            return str(country)

    for loc in locations:
        addr = loc.get("address") or {}
        region = addr.get("addressRegion")
        if not region:
            continue
        region_str = str(region).strip()
        if region_str.upper() in US_STATE_CODES:
            return "United States"
        if len(region_str) > 3:
            return region_str

    return None


def infer_country_from_text(html: str) -> Optional[str]:
    text = html[:100000].lower()
    if "united states" in text or "usa" in text:
        return "United States"
    if "canada" in text:
        return "Canada"
    if "united kingdom" in text or "uk" in text:
        return "United Kingdom"
    if "germany" in text:
        return "Germany"
    if "france" in text:
        return "France"
    if "australia" in text:
        return "Australia"
    if "singapore" in text:
        return "Singapore"
    return None


def classify_category(title: str, description: Optional[str]) -> str:
    text = (title or "") + " " + (description or "")
    text = text.lower()

    def contains_any(keywords: List[str]) -> bool:
        return any(k in text for k in keywords)

    if contains_any(TECH_KEYWORDS):
        return "tech"
    if contains_any(FINANCE_KEYWORDS):
        return "finance"
    if contains_any(BUSINESS_KEYWORDS):
        return "business"
    return "other"


def has_apply_button(html: str) -> bool:
    """
    Heuristic: if we see a <button>, <a>, or <input> whose text/value
    contains 'apply', treat it as having an apply button.
    """
    soup = BeautifulSoup(html, "html.parser")

    # buttons and links
    for tag in soup.find_all(["button", "a"]):
        text = (tag.get_text(" ", strip=True) or "").lower()
        if "apply" in text:
            return True

    # inputs with value
    for tag in soup.find_all("input"):
        val = (tag.get("value") or "").lower()
        if "apply" in val:
            return True

    return False


def enrich_row(row: Dict[str, str]) -> Tuple[Optional[Dict[str, str]], Optional[Dict[str, str]]]:
    """
    Returns:
      (enriched_row, error_row)

    enriched_row: dict for job_enriched.csv
    error_row: dict for error.csv
    """
    url = row.get("url", "").strip()
    source = row.get("source", "").strip()
    title_csv = row.get("title", "").strip()
    posted_time_csv = row.get("posted_time", "").strip()
    scraped_time_csv = row.get("scraped_time", "").strip()

    html = safe_get(url)
    if not html:
        return None, {
            "source": source,
            "url": url,
            "title": title_csv,
            "note": "fetch_failed",
        }

    jobposting = extract_jsonld_jobposting(html)

    day_posted: Optional[str] = None
    country: Optional[str] = None
    title_page: Optional[str] = None
    description_page: Optional[str] = None

    if jobposting:
        title_page = jobposting.get("title") or None
        description_page = jobposting.get("description") or None

        date_posted_raw = jobposting.get("datePosted")
        if isinstance(date_posted_raw, str):
            day_posted = normalize_day_from_date_string(date_posted_raw)

        job_location = jobposting.get("jobLocation")
        country = infer_country_from_joblocation(job_location)

    if not country:
        country = infer_country_from_text(html)

    # derive day_posted from CSV if needed
    if not day_posted and posted_time_csv and scraped_time_csv:
        if "ago" in posted_time_csv:
            day_posted = normalize_day_from_relative(posted_time_csv, scraped_time_csv)
        else:
            tmp = normalize_day_from_date_string(posted_time_csv)
            if tmp:
                day_posted = tmp

    if not day_posted and scraped_time_csv:
        try:
            dt = dateparser.parse(scraped_time_csv)
            day_posted = dt.date().isoformat()
        except Exception:
            day_posted = ""

    final_title = (title_page or title_csv or "").strip()
    category = classify_category(final_title, description_page)

    # Apply button gating: if no apply button, treat as error.
    if not has_apply_button(html):
        return None, {
            "source": source,
            "url": url,
            "title": final_title,
            "note": "no_apply_button_detected",
        }

    enriched_row = {
        "source": source,
        "url": url,
        "title": final_title,
        "day_posted": day_posted or "",
        "country": country or "",
        "category": category,
    }
    return enriched_row, None


def phase2_enrich_jobs() -> None:
    # Read all job_url rows
    try:
        with open(JOB_URL_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"[ERROR] Input CSV '{JOB_URL_CSV}' not found.")
        return

    print(f"Loaded {len(rows)} rows from {JOB_URL_CSV} for enrichment.")

    enriched_rows: List[Dict[str, str]] = []
    error_rows: List[Dict[str, str]] = []

    for idx, row in enumerate(rows, start=1):
        url = row.get("url", "")
        print(f"[{idx}/{len(rows)}] Enriching {url}")
        enriched, error = enrich_row(row)
        if enriched:
            enriched_rows.append(enriched)
        if error:
            error_rows.append(error)

    # Write enriched CSV (overwrite)
    with open(ENRICHED_CSV, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["source", "url", "title", "day_posted", "country", "category"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in enriched_rows:
            writer.writerow(r)

    # Write error CSV (overwrite)
    with open(ERROR_CSV, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["source", "url", "title", "note"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in error_rows:
            writer.writerow(r)

    print(f"Wrote {len(enriched_rows)} rows to {ENRICHED_CSV}")
    print(f"Wrote {len(error_rows)} rows to {ERROR_CSV}")

# =========================
# MAIN
# =========================

def main():
    print("=== Phase 1: update job_url.csv from SerpAPI (past week, 1 page/site) ===")
    phase1_update_job_urls()
    print("=== Phase 2: enrich all jobs into job_enriched.csv and error.csv ===")
    phase2_enrich_jobs()


if __name__ == "__main__":
    main()
