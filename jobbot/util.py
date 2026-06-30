import html
import re
from datetime import datetime, timezone

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def ms_to_iso(ms) -> str | None:
    if ms in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return None

def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = _TAG.sub(" ", s)
    return _WS.sub(" ", s).strip()
