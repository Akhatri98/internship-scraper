# Job-Bot

Free, cloud-hosted discovery of fresh **student** roles (intern / co-op / new-grad /
early-career, tech-focused) pulled **ATS-direct** from company job boards — including
obscure companies the big aggregators miss. $0 stack: GitHub Actions + Supabase, no
paid APIs in the steady state.

## How it works

Three phases, all writing into Supabase:

| Phase | What | Source | Cadence |
|-------|------|--------|---------|
| **Seed** | one-time cold-start fill of the company list | Serper (one-time free grant) | run once, manually |
| **Discover** (Component A) | grow the company list | Common Crawl URL index (free) | monthly |
| **Refresh** (Component B) | pull current listings, filter, dedup | each ATS's public JSON API (free) | 2×/day |

- `companies` — every discovered `(company_slug, ats_source)` pair.
- `listings` — current student-tech roles, deduped by `canonical_url`.

## ATS coverage

**Pollable** (Refresh has an adapter): greenhouse, lever, ashby, smartrecruiters,
workable, rippling, breezy, recruitee, teamtailor.

**Discover-only** (slugs captured, no clean public JSON yet): workday, icims,
jobvite, jazzhr, zohorecruit, bamboohr.

## Local usage

```bash
pip install -r requirements-dev.txt
pytest                                   # unit tests (parsers + filters)

python -m scripts.run_refresh            # poll all companies -> listings
python -m scripts.run_discover --only rippling --max-pages 1   # test discovery
python -m scripts.verify_listings        # inspect listings
```

Secrets live in `.env` (gitignored): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
The one-time seed lives in `scripts/seed_run.py` and needs `SERPER_API_KEY`.

## GitHub Actions (the $0 runner)

Workflows in `.github/workflows/`:

- **freshness.yml** — Refresh, 2×/day (09:00 & 21:00 UTC) + manual dispatch.
- **discovery.yml** — Discover, monthly (1st, 06:00 UTC) + manual dispatch.
- **keepalive.yml** — weekly commit so scheduled workflows aren't auto-disabled
  after 60 days of repo inactivity.

### Required setup (do this after first push)

Add repository secrets under **Settings → Secrets and variables → Actions**:

| Secret | Required | Purpose |
|--------|----------|---------|
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | ✅ | service-role key (writes; bypasses RLS) |
| `DISCORD_WEBHOOK_URL` | optional | ping on a failed run |

Then trigger each workflow once via **Actions → (workflow) → Run workflow** to
confirm it's wired before relying on the schedule.

> The applied database schema and one-time helper scripts are kept locally in
> `archive/` (gitignored).
