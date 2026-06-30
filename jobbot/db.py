"""Thin Supabase PostgREST client (service-role key, server-side only).

We talk to Supabase's REST endpoint directly with `requests` rather than pull in
the full supabase-py SDK — keeps the dependency surface tiny for the Actions
runner and keeps every HTTP call visible/debuggable.

The service-role (secret) key bypasses RLS, so this module must never run
anywhere client-facing.
"""
import requests

from . import config

_REST = f"{config.SUPABASE_URL}/rest/v1"
_session = requests.Session()


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
    r = _session.get(
        f"{_REST}/{table}",
        headers=_headers(),
        params=params or {"select": "*"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


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
