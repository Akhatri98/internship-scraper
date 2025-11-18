import requests
from bs4 import BeautifulSoup
import csv
import os
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

CSV_FILE = "jobs.csv"

QUERIES = [
    'intern site:jobs.lever.co',
    'intern site:jobs.ashbyhq.com',
    'intern site:job-boards.greenhouse.io'
]

DUCK_URL = "https://html.duckduckgo.com/html/"


# ----------------------------
# 1. Ensure CSV header exists
# ----------------------------
def ensure_csv_header():
    if not os.path.exists(CSV_FILE) or os.stat(CSV_FILE).st_size == 0:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["url", "title", "posted_date", "days_since_update"])


# ----------------------------
# 2. Load existing URLs
# ----------------------------
def load_existing_urls():
    if not os.path.exists(CSV_FILE):
        return set()
    existing = set()
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing.add(row["url"])
    return existing


# ----------------------------
# 3. DuckDuckGo pagination
# ----------------------------
def duck_search(query, pages=3):
    """Scrape DuckDuckGo HTML results with pagination."""
    results = []
    next_form = None

    for _ in range(pages):
        payload = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0"}

        if next_form:
            payload.update(next_form)

        r = requests.post(DUCK_URL, data=payload, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")

        for a in soup.select(".result__a"):
            href = a["href"]
            final_url = clean_duck_link(href)
            results.append(final_url)

        # Find next page form
        next_btn = soup.find("form", {"id": "links_more"})
        if not next_btn:
            break

        next_form = {}
        for inp in next_btn.find_all("input"):
            next_form[inp.get("name")] = inp.get("value")

    return results


def clean_duck_link(url):
    """DuckDuckGo wraps external links. Extract real URL."""
    if "duckduckgo.com" in url and "uddg=" in url:
        parsed = parse_qs(urlparse(url).query)
        return parsed.get("uddg", [url])[0]
    return url


# ----------------------------
# 4. Scrape REAL job page title + date
# ----------------------------
def scrape_job_page(url):
    """Extract job title + posted date from real job page."""
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")

        # ---- title extraction ----
        if soup.title:
            title = soup.title.text.strip()
        else:
            h1 = soup.find("h1")
            title = h1.text.strip() if h1 else ""

        # ---- date extraction ----
        date = extract_date(soup)

        return title, date
    
    except Exception:
        return "", None


def extract_date(soup):
    """Handle Lever, Greenhouse, Ashby structured metadata."""
    # Lever
    lever = soup.find("meta", {"itemprop": "datePosted"})
    if lever and lever.get("content"):
        return lever["content"]

    # Greenhouse
    gh = soup.find("meta", {"name": "gh:created_at"})
    if gh and gh.get("content"):
        return gh["content"]

    # Ashby
    ash = soup.find("meta", {"property": "article:published_time"})
    if ash and ash.get("content"):
        return ash["content"]

    return None


# ----------------------------
# 5. Convert date → days-since-update
# ----------------------------
def calc_days_since(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except:
        return ""


# ----------------------------
# 6. Append new entries
# ----------------------------
def append_to_csv(data):
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for row in data:
            w.writerow(row)


# ----------------------------
# 7. Main script
# ----------------------------
def main():
    ensure_csv_header()
    existing = load_existing_urls()

    new_entries = []

    for q in QUERIES:
        print("Searching:", q)
        urls = duck_search(q, pages=4)

        for url in urls:
            if url in existing:
                continue

            title, posted = scrape_job_page(url)
            days = calc_days_since(posted)

            new_entries.append([url, title, posted or "", days])

    if new_entries:
        print("Adding", len(new_entries), "new jobs...")
        append_to_csv(new_entries)
    else:
        print("No new jobs found.")

    print("Done.")


if __name__ == "__main__":
    main()
