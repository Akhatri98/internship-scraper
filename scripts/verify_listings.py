from jobbot import db

def main():
    rows = db.select("listings", {
        "select": "ats_source,company_slug,company,pay,title,keywords_matched,location,country,first_seen_at,last_seen_at,canonical_url,raw_url",
        "order": "ats_source,title",
    })
    print(f"listings rows: {len(rows)}\n")
    for r in rows:
        print(f"[{r['ats_source']}/{r['company_slug']}] {r.get('company')!r} — {r['title']!r}")
        print(f"    kw:    {r['keywords_matched']}")
        print(f"    loc:   {r.get('location')!r}  country={r.get('country')!r}  pay={r.get('pay')!r}")
        print(f"    seen:  first={r['first_seen_at']}  last={r['last_seen_at']}")
        print(f"    canon: {r['canonical_url']}")
        print(f"    raw:   {r['raw_url']}")


if __name__ == "__main__":
    main()
