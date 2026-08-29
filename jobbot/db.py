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

# Supabase reads and writes both blip intermittently: a run opens with ~33 paged
# selects (see refresh.run_refresh), and one transient timeout there used to kill
# the whole workflow before any polling happened. Only conn/timeout/5xx retry — a
# 4xx is our bug and must surface immediately.
#
# Retrying is safe for select/upsert/patch/delete because every one of them is
# idempotent (merge-duplicates, a keyed PATCH, a delete of already-gone rows). A
# timeout does NOT mean the write was lost, so a replay must be harmless — which
# is exactly why plain insert() is NOT retried: replaying it would duplicate rows.
_ATTEMPTS = 4
_TIMEOUT = 60


def _retryable(exc) -> bool:
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    resp = getattr(exc, "response", None)
    return resp is not None and resp.status_code >= 500


def _send(method: str, url: str, **kw):
    """One idempotent PostgREST call, retried through transient failures."""
    kw.setdefault("timeout", _TIMEOUT)
    for attempt in range(_ATTEMPTS):
        try:
            r = _session.request(method, url, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt == _ATTEMPTS - 1 or not _retryable(e):
                raise
            time.sleep(1.5 * (2 ** attempt))


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
    return _send("GET", f"{_REST}/{table}", headers=_headers(),
                 params=params or {"select": "*"}).json()


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
    r = _send("POST", f"{_REST}/{table}",
              headers=_headers({"Prefer": prefer}),
              params={"on_conflict": on_conflict}, json=rows)
    return r.json() if (r.text and "return=representation" in prefer) else []


def patch(table: str, match: dict, values: dict) -> None:
    _send("PATCH", f"{_REST}/{table}",
          headers=_headers({"Prefer": "return=minimal"}),
          params=match, json=values)


def delete(table: str, match: dict) -> None:
    _send("DELETE", f"{_REST}/{table}",
          headers=_headers({"Prefer": "return=minimal"}), params=match)
