import csv
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

INPUT_CSV = "job_url.csv"
OUTPUT_CSV = "job_enriched.csv"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; JobScraper/1.0; +https://example.com)"
})


# =========================
# Utilities
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
    """
    Look for schema.org JobPosting in <script type="application/ld+json">.
    Works across Lever, Greenhouse, Ashby in most cases.
    """
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")

    for tag in scripts:
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue

        # data can be dict, list, or @graph wrapper
        objects: List[Any]
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
    """
    Parse a date/time string into YYYY-MM-DD.
    Returns None if parsing fails.
    """
    try:
        dt = dateparser.parse(s)
        return dt.date().isoformat()
    except Exception:
        return None


def normalize_day_from_relative(relative: str, scraped_iso: str) -> Optional[str]:
    """
    relative: e.g., '3 days ago', '5 hours ago', etc.
    scraped_iso: ISO timestamp like '2025-11-29T12:34:56Z'
    """
    if not relative or "ago" not in relative:
        return None

    # Grab first integer we see
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
        # crude approximation
        dt = scraped_dt - timedelta(days=30 * n)
    elif unit == "year":
        dt = scraped_dt - timedelta(days=365 * n)
    else:
        dt = scraped_dt - timedelta(days=n)

    return dt.date().isoformat()


US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


def infer_country_from_joblocation(job_location: Any) -> Optional[str]:
    """
    job_location is whatever sits under JobPosting['jobLocation'].
    We try to read addressCountry; if missing, we fall back on addressRegion, etc.
    """
    if not job_location:
        return None

    locations: List[Dict[str, Any]] = []
    if isinstance(job_location, list):
        locations = [loc for loc in job_location if isinstance(loc, dict)]
    elif isinstance(job_location, dict):
        locations = [job_location]
    else:
        return None

    # Prefer addressCountry when present
    for loc in locations:
        addr = loc.get("address") or {}
        country = addr.get("addressCountry")
        if country:
            return str(country)

    # Fallback: look at addressRegion and guess US vs other
    for loc in locations:
        addr = loc.get("address") or {}
        region = addr.get("addressRegion")
        if not region:
            continue
        region_str = str(region).strip()
        if region_str.upper() in US_STATE_CODES:
            return "United States"
        # If region itself looks like a country name, return it
        if len(region_str) > 3:
            return region_str

    return None


def infer_country_from_text(html: str) -> Optional[str]:
    """
    Dumb fallback: look for some common country names in raw HTML.
    This is a last resort.
    """
    text = html[:100000].lower()  # cap to avoid giant pages
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
    # can extend list later
    return None


# =========================
# Simple rule-based classifier
# =========================

TECH_KEYWORDS = [
    "software", "developer", "engineer", "data scientist", "machine learning",
    "ml engineer", "backend", "frontend", "full stack", "cloud", "devops",
    "ai ", "artificial intelligence", "python", "java", "c++", "golang",
    "golang", "typescript", "react", "node", "sre", "site reliability",
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


# =========================
# Core enrichment
# =========================

def enrich_row(row: Dict[str, str]) -> Dict[str, str]:
    url = row.get("url", "").strip()
    source = row.get("source", "").strip()
    title_csv = row.get("title", "").strip()
    posted_time_csv = row.get("posted_time", "").strip()
    scraped_time_csv = row.get("scraped_time", "").strip()

    day_posted: Optional[str] = None
    country: Optional[str] = None
    title_page: Optional[str] = None
    description_page: Optional[str] = None

    html = safe_get(url)
    if html:
        jobposting = extract_jsonld_jobposting(html)
        if jobposting:
            title_page = jobposting.get("title") or None
            description_page = jobposting.get("description") or None

            date_posted_raw = jobposting.get("datePosted")
            if isinstance(date_posted_raw, str):
                day_posted = normalize_day_from_date_string(date_posted_raw)

            job_location = jobposting.get("jobLocation")
            country = infer_country_from_joblocation(job_location)

        # Fallback country from text if JSON-LD failed
        if not country:
            country = infer_country_from_text(html)

    # If we still don't have day_posted, try to derive from CSV's posted_time + scraped_time
    if not day_posted and posted_time_csv and scraped_time_csv:
        # posted_time_csv might be '3 days ago' or 'Nov 7, 2025'
        if "ago" in posted_time_csv:
            day_posted = normalize_day_from_relative(posted_time_csv, scraped_time_csv)
        else:
            tmp = normalize_day_from_date_string(posted_time_csv)
            if tmp:
                day_posted = tmp

    # Last resort: treat scraped date as day_posted
    if not day_posted and scraped_time_csv:
        try:
            dt = dateparser.parse(scraped_time_csv)
            day_posted = dt.date().isoformat()
        except Exception:
            day_posted = ""

    # Choose title preference: page > csv
    final_title = (title_page or title_csv or "").strip()

    # Classify category
    category = classify_category(final_title, description_page)

    return {
        "source": source,
        "url": url,
        "title": final_title,
        "day_posted": day_posted or "",
        "country": country or "",
        "category": category,
    }


def main():
    # Read input CSV
    try:
        with open(INPUT_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"[ERROR] Input CSV '{INPUT_CSV}' not found.")
        return

    print(f"Loaded {len(rows)} rows from {INPUT_CSV}")

    enriched_rows: List[Dict[str, str]] = []

    for idx, row in enumerate(rows, start=1):
        url = row.get("url", "")
        print(f"[{idx}/{len(rows)}] Enriching {url}")
        enriched = enrich_row(row)
        enriched_rows.append(enriched)

    # Write output CSV
    fieldnames = ["source", "url", "title", "day_posted", "country", "category"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in enriched_rows:
            writer.writerow(r)

    print(f"Wrote {len(enriched_rows)} enriched rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
