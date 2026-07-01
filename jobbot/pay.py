"""Best-effort pay signal for a listing (non-normalized by design).

Pay is reported inconsistently across ATSs — a structured object here, buried in
description prose there, absent everywhere else — so we don't try to normalize it.
The `pay` column holds, in priority order:

  1. a structured comp string when the feed gives one (Ashby compensationTierSummary,
     Recruitee salary object) — see the adapters;
  2. the literal "Unpaid" when the text CLEARLY says so (this module);
  3. NULL otherwise (unknown — NOT "assume paid").

`is_unpaid` is deliberately CONSERVATIVE: a false positive hides a real paid job,
which is worse than missing an unpaid one. So bare "unpaid" is NOT enough (it fires
on benefits boilerplate like "unpaid leave" / "unpaid time off"); we require it
anchored to the role, or an unambiguous no-comp phrase.
"""
import re

UNPAID = "Unpaid"

_UNPAID = re.compile(
    r"\bunpaid\s+(intern(ship)?s?|co-?ops?|positions?|roles?|opportunit(y|ies)|placements?)\b"
    r"|\b(intern(ship)?s?|positions?|roles?)\s+(is|are)\s+unpaid\b"
    r"|\bno\s+(compensation|monetary compensation|salary)\b"
    r"|\bwithout\s+(compensation|pay)\b"
    r"|\b(for|academic|course)\s+credit\s+only\b"
    r"|\bvolunteer\s+(intern(ship)?|position|role|opportunity)\b",
    re.I,
)


def is_unpaid(*texts) -> bool:
    """True only on a strong unpaid signal in title/description (see module note)."""
    blob = " ".join(t for t in texts if t)
    return bool(_UNPAID.search(blob))


def format_salary(minv=None, maxv=None, period=None, currency=None) -> str | None:
    """Format a structured salary (e.g. Recruitee's) into a raw display string:
    2400/3000 EUR month -> "EUR 2400–3000/month". Non-normalized; None if empty."""
    def _num(v):
        v = str(v).strip() if v is not None else ""
        return "" if v in ("", "0", "0.0") else v

    lo, hi = _num(minv), _num(maxv)
    if not lo and not hi:
        return None
    if lo and hi and lo != hi:
        amount = f"{lo}–{hi}"
    else:
        amount = lo or hi  # single value, or collapse an identical min==max range
    out = f"{(currency or '').strip()} {amount}".strip()
    per = (period or "").strip()
    return f"{out}/{per}" if per else out
