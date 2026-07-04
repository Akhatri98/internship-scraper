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
        "pace": 0.35,
    },
    "rippling": {
        "hosts": ("ats.rippling.com",),
        "slug_in": "path",
        "api": "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs",
        "pace": 0.75,
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
    "bamboohr": {
        "hosts": ("bamboohr.com",),
        "slug_in": "subdomain",
        "api": "https://{slug}.bamboohr.com/careers/list",
    },
    "jazzhr": {
        "hosts": ("applytojob.com",),
        "slug_in": "subdomain",
        "api": "https://{slug}.applytojob.com/apply/",
    },
    "jobvite": {
        "hosts": ("jobs.jobvite.com",),
        "slug_in": "path",
        "api": "https://jobs.jobvite.com/{slug}/search",
    },
    "workday": {
        "hosts": ("myworkdayjobs.com",),
        "slug_in": "subdomain",
        "api": "https://{slug}.myworkdayjobs.com/wday/cxs/",
    },
}
