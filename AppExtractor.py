import os
import csv
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set

from dotenv import load_dotenv
from serpapi import GoogleSearch

# =========================
# CONFIG
# =========================

CSV_PATH = "job_url.csv"
CSV_HEADER = ["source", "url", "title", "posted_time", "scraped_time"]

# (source, query)
QUERIES: List[Tuple[str, str]] = [
    ("ashbyhq", "intern site:jobs.ashbyhq.com"),
    ("lever", "intern site:jobs.lever.co"),
    ("greenhouse", "intern site:job-boards.greenhouse.io"),
]

# Date filter: None, "day", "week", or "month"
# Maps to Google's qdr: (past 24h / 7d / 30d)
DATE_RANGE: Optional[str] = "month"

DATE_RANGE_TO_TBS = {
    None: None,
    "day": "qdr:d",
    "week": "qdr:w",
    "month": "qdr:m",
}

# Google organic is always 10 results per page
PAGE_SIZE = 10

# You said you already ran 10 pages per query (0..9).
# This script will start at page index 10 by default.
# If you ever want to start from the beginning again, set this to 0.
ALREADY_SCRAPED_PAGES_PER_QUERY = 10

# Global API call budget for this run.
# With 3 sources, 210 calls ≈ 70 new pages per source (if they exist).
MAX_TOTAL_API_CALLS = 200


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

def ensure_csv_and_load_existing_urls(path: str) -> Optional[Set[str]]:
    """
    - If CSV does not exist: print error and return None (caller aborts).
    - If CSV exists but is empty: write header and return empty URL set.
    - If CSV has data: load existing 'url' values into a set.

    Returns:
        existing_urls: set of URLs already present in CSV (or None if file missing).
    """
    if not os.path.exists(path):
        print(f"ERROR: '{path}' not found. Create an empty file named '{path}' first.")
        return None

    existing_urls: Set[str] = set()

    # Empty file → write header
    if os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)
        return existing_urls

    # Non-empty → read URLs
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url")
            if url:
                existing_urls.add(url)

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

def search_single_page(
    api_key: str,
    source: str,
    query: str,
    tbs: Optional[str],
    page_index: int,
) -> Tuple[List[Dict[str, str]], int]:
    """
    Fetch a single page (10 organic results) for a given (source, query, page_index).

    Returns:
        (normalized_rows, organic_count)
        - normalized_rows: [{source, url, title, posted_time, scraped_time}, ...]
        - organic_count: number of items in organic_results (before host filtering)
    """
    start = page_index * PAGE_SIZE

    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "start": start,
        # Google caps organic at 10; num > 10 is ignored, but we set 10 explicitly.
        "num": PAGE_SIZE,
    }

    if tbs:
        params["tbs"] = tbs

    print(f"    Calling SerpAPI for {source}, page_index={page_index}, start={start}")
    search = GoogleSearch(params)
    data = search.get_dict()

    organic = data.get("organic_results", []) or []
    organic_count = len(organic)

    normalized_rows: List[Dict[str, str]] = []

    for res in organic:
        link = res.get("link")
        title = res.get("title") or ""
        posted_time = res.get("date") or ""

        if not link:
            continue

        # Safety: enforce correct host despite using site:
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

    print(
        f"      organic_count={organic_count}, "
        f"kept_after_host_filter={len(normalized_rows)}"
    )
    return normalized_rows, organic_count


# =========================
# MAIN
# =========================

def main():
    # 1) Ensure CSV exists and load existing URLs
    existing_urls = ensure_csv_and_load_existing_urls(CSV_PATH)
    if existing_urls is None:
        # CSV missing → abort to avoid burning API calls
        return

    api_key = get_api_key()
    tbs = DATE_RANGE_TO_TBS.get(DATE_RANGE)

    all_new_rows: List[Dict[str, str]] = []

    # Track which sources still have pages left
    active_sources: Set[str] = {src for src, _ in QUERIES}

    calls_used = 0
    page_index = ALREADY_SCRAPED_PAGES_PER_QUERY

    print(f"Starting budgeted scrape with MAX_TOTAL_API_CALLS={MAX_TOTAL_API_CALLS}")
    print(f"Already scraped pages per query (0-based): 0..{ALREADY_SCRAPED_PAGES_PER_QUERY - 1}")
    print(f"Continuing from page_index={page_index}")

    while calls_used < MAX_TOTAL_API_CALLS and active_sources:
        print(f"\n=== Global page_index={page_index} ===")

        for source, query in QUERIES:
            if calls_used >= MAX_TOTAL_API_CALLS:
                break

            if source not in active_sources:
                continue

            print(f"  Source={source}, remaining_call_budget={MAX_TOTAL_API_CALLS - calls_used}")
            rows, organic_count = search_single_page(
                api_key=api_key,
                source=source,
                query=query,
                tbs=tbs,
                page_index=page_index,
            )
            calls_used += 1

            # Dedup by URL against existing + new in this run
            new_rows_this_call = 0
            for row in rows:
                url = row["url"]
                if url in existing_urls:
                    continue
                existing_urls.add(url)
                all_new_rows.append(row)
                new_rows_this_call += 1

            print(f"      New unique rows appended (in-memory): {new_rows_this_call}")
            print(f"      Total calls_used so far: {calls_used}")

            if organic_count == 0:
                print(f"      No organic results; removing {source} from active_sources.")
                active_sources.remove(source)
                continue

            if organic_count < PAGE_SIZE:
                print(
                    f"      organic_count < {PAGE_SIZE}; "
                    f"assuming last page for {source} and removing from active_sources."
                )
                active_sources.remove(source)

        page_index += 1

    print(
        f"\nDone. Total API calls used this run: {calls_used} "
        f"(max allowed {MAX_TOTAL_API_CALLS})."
    )
    print(f"New unique rows collected in memory: {len(all_new_rows)}")

    # 3) Append new rows to CSV
    append_rows_to_csv(CSV_PATH, all_new_rows)


if __name__ == "__main__":
    main()
