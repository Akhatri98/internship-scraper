import os
import csv
from datetime import datetime
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from serpapi import GoogleSearch

# =========================
# CONFIG
# =========================

CSV_PATH = "job_url.csv"
CSV_HEADER = ["source", "url", "title", "posted_time", "scraped_time"]

# Queries: (source, query_string)
QUERIES: List[Tuple[str, str]] = [
    ("ashbyhq", "intern site:jobs.ashbyhq.com"),
    ("lever", "intern site:jobs.lever.co"),
    ("greenhouse", "intern site:job-boards.greenhouse.io"),
]

# Date filter: None, "day", "week", or "month"
# Maps to Google's qdr: (past 24h / 7d / 30d)
DATE_RANGE = "week"

DATE_RANGE_TO_TBS = {
    None: None,
    "day": "qdr:d",
    "week": "qdr:w",
    "month": "qdr:m",
}


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
# CSV HANDLING
# =========================

def ensure_csv_and_load_existing_urls(path: str) -> Dict[str, None]:
    """
    - If CSV does not exist: return None to signal "abort".
    - If CSV exists but is empty: write header and return empty URL set.
    - If CSV has data: load existing 'url' values into a set and return it.

    Returns:
        existing_urls: set-like (actually dict keys) of URLs already present.
        If CSV missing, returns None.
    """
    if not os.path.exists(path):
        print(f"ERROR: '{path}' not found. Create an empty file named '{path}' first.")
        return None

    existing_urls = {}

    # Empty file → write header
    if os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)
        # No existing URLs yet
        return existing_urls

    # Non-empty → read URLs
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url")
            if url:
                existing_urls[url] = None

    return existing_urls


def append_rows_to_csv(path: str, rows: List[Dict[str, str]]) -> None:
    if not rows:
        print("No new rows to append.")
        return

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        for row in rows:
            writer.writerow(row)

    print(f"Appended {len(rows)} new rows to {path}.")


# =========================
# SERPAPI SEARCH
# =========================

def search_source(
    api_key: str,
    source: str,
    query: str,
    tbs: str = None,
    max_results: int = 300,
    page_size: int = 50,
) -> List[Dict]:
    """
    Run a Google Search via SerpAPI for a single source+query.

    Returns a list of normalized rows:
      {source, url, title, posted_time, scraped_time}
    """
    normalized_rows: List[Dict] = []
    start = 0

    while start < max_results:
        params = {
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "start": start,
        }

        # Ask for more results per page; you can bump to 100 once you confirm behavior.
        params["num"] = page_size

        if tbs:
            params["tbs"] = tbs

        search = GoogleSearch(params)
        data = search.get_dict()

        organic = data.get("organic_results", []) or []
        if not organic:
            break

        for res in organic:
            link = res.get("link")
            title = res.get("title")
            posted_time = res.get("date")  # Whatever Google shows: "3 days ago", "Nov 1, 2025", etc.

            if not link:
                continue

            # Extra safety to ensure the result matches the expected host.
            # This isn't strictly necessary since you're using site:, but it hard-filters noise.
            if source == "ashbyhq" and "jobs.ashbyhq.com" not in link:
                continue
            if source == "lever" and "jobs.lever.co" not in link:
                continue
            if source == "greenhouse" and "job-boards.greenhouse.io" not in link:
                continue

            row = {
                "source": source,
                "url": link,
                "title": title or "",
                "posted_time": posted_time or "",
                "scraped_time": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            normalized_rows.append(row)

        # If we got fewer than page_size results, we're at the end
        if len(organic) < page_size:
            break

        start += page_size

    return normalized_rows


# =========================
# MAIN
# =========================

def main():
    # 1) Check CSV exists before any API calls
    existing_urls = ensure_csv_and_load_existing_urls(CSV_PATH)
    if existing_urls is None:
        # CSV missing → abort early to avoid burning API calls
        return

    api_key = get_api_key()
    tbs = DATE_RANGE_TO_TBS.get(DATE_RANGE)

    all_new_rows: List[Dict[str, str]] = []

    # 2) Run all three site-specific queries
    for source, query in QUERIES:
        print(f"Searching {source} with query: {query!r}")
        rows = search_source(api_key, source, query, tbs=tbs)
        print(f"  Retrieved {len(rows)} candidates for {source} before dedup.")

        for row in rows:
            url = row["url"]
            if url in existing_urls:
                continue
            existing_urls[url] = None
            all_new_rows.append(row)

    # 3) Append any new rows to CSV
    append_rows_to_csv(CSV_PATH, all_new_rows)


if __name__ == "__main__":
    main()
