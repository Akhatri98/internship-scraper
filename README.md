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
| **Refresh** (Component B) | pull current listings, filter, dedup | each ATS's public JSON API (free) | hourly (FAST) + nightly DEEP |
| **Prune** (Component C) | drop listings a live board no longer serves | successful Refresh polls (no HTTP) | nightly, after DEEP |

- `companies` — every discovered `(company_slug, ats_source)` pair.
- `listings` — current student roles across tech, engineering, sciences, health,
  and finance/business, deduped by `canonical_url`.

## ATS coverage

**Pollable** (Refresh has an adapter/fetcher): greenhouse, lever, ashby,
smartrecruiters, workable, rippling, breezy, recruitee, teamtailor, bamboohr,
jazzhr, jobvite, workday.

- workable / smartrecruiters / workday / jobvite need multi-request fetchers
  (pagination or per-term server-side search) — see `FETCHERS` in
  `jobbot/ats/adapters.py`.
- workday uses a composite slug `tenant.wdN/Site` (the CXS API needs the
  datacenter host + career-site name, not just the tenant); bare-tenant rows
  were retired by `scripts/repair_workday.py`.
- jazzhr / jobvite have no public JSON — their server-rendered boards are
  parsed by regex (title + location only; the HARD intern-gate is title-only
  anyway).

**Discover-only** (client-rendered, no public feed — not pollable): icims,
zohorecruit.

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

- **freshness.yml** — Refresh FAST, hourly (skips 05–06 UTC for DEEP clearance) + manual dispatch.
- **freshness-deep.yml** — Refresh DEEP, nightly (05:00 UTC) + manual dispatch.
- **freshness-prune.yml** — Prune, chained after each successful DEEP run + manual dispatch.
- **discovery.yml** — Discover, monthly (1st, 06:00 UTC) + manual dispatch.
- **keepalive.yml** — weekly commit so scheduled workflows aren't auto-disabled
  after 60 days of repo inactivity.

### Required setup (do this after first push)

Add repository secrets under **Settings → Secrets and variables → Actions**:

| Secret | Required | Purpose |
|--------|----------|---------|
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | ✅ | service-role key (writes; bypasses RLS) |

Then trigger each workflow once via **Actions → (workflow) → Run workflow** to
confirm it's wired before relying on the schedule.

> The applied database schema and one-time helper scripts are kept locally in
> `archive/` (gitignored).
