"""Thin Supabase PostgREST client (service-role key, server-side only).

We talk to Supabase's REST endpoint directly with `requests` rather than pull in
the full supabase-py SDK — keeps the dependency surface tiny for the Actions
runner and keeps every HTTP call visible/debuggable.

The service-role (secret) key bypasses RLS, so this module must never run
anywhere client-facing.
"""
import time

import requests

from . import config

_REST = f"{config.SUPABASE_URL}/rest/v1"
_session = requests.Session()

# Reads are retried: a run opens with ~33 paged selects (see refresh.run_refresh),
# and a single transient blip there used to kill the whole workflow before any
# polling happened. Only conn/timeout/5xx are retried — a 4xx is our bug and must
# surface immediately.
_READ_ATTEMPTS = 4
_READ_TIMEOUT = 60


def _retryable(exc) -> bool:
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    resp = getattr(exc, "response", None)
    return resp is not None and resp.status_code >= 500


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": config.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def select(table: str, params: dict | None = None) -> list[dict]:
    for attempt in range(_READ_ATTEMPTS):
        try:
            r = _session.get(
                f"{_REST}/{table}",
                headers=_headers(),
                params=params or {"select": "*"},
                timeout=_READ_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == _READ_ATTEMPTS - 1 or not _retryable(e):
                raise
            time.sleep(1.5 * (2 ** attempt))


def select_all(table: str, params: dict | None = None, page_size: int = 1000) -> list[dict]:
    """Fetch every row, paging past PostgREST's per-response row cap (~1000).

    Uses limit/offset over a stable order. Supabase caps each response at
    db-max-rows regardless of the limit asked, so we page until a short page.
    """
    base = dict(params or {"select": "*"})
    base.setdefault("order", "id")
    out: list[dict] = []
    offset = 0
    while True:
        page = select(table, dict(base, limit=page_size, offset=offset))
        out.extend(page)
        if len(page) < page_size:
            return out
        offset += page_size


def insert(table: str, rows, prefer: str = "return=representation") -> list[dict]:
    r = _session.post(
        f"{_REST}/{table}",
        headers=_headers({"Prefer": prefer}),
        json=rows,
        timeout=30,
    )
    r.raise_for_status()
    return r.json() if r.text else []


def upsert(table: str, rows, on_conflict: str,
           prefer: str = "resolution=merge-duplicates,return=minimal") -> list[dict]:
    """Insert-or-update on a unique column.

    PostgREST merge-duplicates only touches columns present in the payload on
    conflict, so callers control which fields get refreshed vs preserved
    (e.g. omit first_seen_at to keep the original freshness clock, include
    last_seen_at to bump it).
    """
    r = _session.post(
        f"{_REST}/{table}",
        headers=_headers({"Prefer": prefer}),
        params={"on_conflict": on_conflict},
        json=rows,
        timeout=30,
    )
    r.raise_for_status()
    return r.json() if (r.text and "return=representation" in prefer) else []


def patch(table: str, match: dict, values: dict) -> None:
    r = _session.patch(
        f"{_REST}/{table}",
        headers=_headers({"Prefer": "return=minimal"}),
        params=match,
        json=values,
        timeout=30,
    )
    r.raise_for_status()


def delete(table: str, match: dict) -> None:
    r = _session.delete(
        f"{_REST}/{table}",
        headers=_headers({"Prefer": "return=minimal"}),
        params=match,
        timeout=30,
    )
    r.raise_for_status()
