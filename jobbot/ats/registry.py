ATS: dict[str, dict] = {
    "greenhouse": {
        "hosts": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
        "slug_in": "path",
        "api": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    },
    "lever": {
        "hosts": ("jobs.lever.co",),
        "slug_in": "path",
        "api": "https://api.lever.co/v0/postings/{slug}?mode=json",
    },
    "ashby": {
        "hosts": ("jobs.ashbyhq.com",),
        "slug_in": "path",
        "api": "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
    },
    # --- Stage 6 long-tail (verified live; `method` GET unless noted) ---
    "smartrecruiters": {
        "hosts": ("jobs.smartrecruiters.com",),
        "slug_in": "path",
        "api": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
    },
    "workable": {
        "hosts": ("apply.workable.com",),
        "slug_in": "path",
        "api": "https://apply.workable.com/api/v3/accounts/{slug}/jobs",
        "method": "POST",
    },
    "rippling": {
        "hosts": ("ats.rippling.com",),
        "slug_in": "path",
        "api": "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs",
    },
    "breezy": {
        "hosts": ("breezy.hr",),
        "slug_in": "subdomain",
        "api": "https://{slug}.breezy.hr/json",
    },
    "recruitee": {
        "hosts": ("recruitee.com",),
        "slug_in": "subdomain",
        "api": "https://{slug}.recruitee.com/api/offers/",
    },
    "teamtailor": {
        "hosts": ("teamtailor.com",),
        "slug_in": "subdomain",
        "api": "https://{slug}.teamtailor.com/jobs.json",
    },
}
