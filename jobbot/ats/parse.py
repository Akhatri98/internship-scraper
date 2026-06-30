from urllib.parse import parse_qsl, urlsplit, urlunsplit
from .registry import ATS

def _host(netloc: str) -> str:
    """Lowercased hostname with any userinfo / port stripped."""
    netloc = netloc.lower()
    if "@" in netloc:
        netloc = netloc.split("@", 1)[1]
    if ":" in netloc:
        netloc = netloc.split(":", 1)[0]
    return netloc


def ats_from_url(url: str) -> str | None:
    """Which ATS (if any) a URL belongs to."""
    host = _host(urlsplit(url).netloc)
    for key, cfg in ATS.items():
        for h in cfg["hosts"]:
            if cfg["slug_in"] == "path":
                if host == h:
                    return key
            else:
                if host == h or host.endswith("." + h):
                    return key
    return None


def slug_from_url(url: str) -> str | None:
    ats = ats_from_url(url)
    if ats is None:
        return None
    cfg = ATS[ats]
    parts = urlsplit(url)

    if cfg["slug_in"] == "path":
        segs = [s for s in parts.path.split("/") if s]
        if not segs:
            return None
        first = segs[0].lower()
        # Greenhouse embed form: boards.greenhouse.io/embed/job_board?for=<slug>
        if ats == "greenhouse" and first == "embed":
            forv = dict(parse_qsl(parts.query)).get("for")
            return forv.lower() if forv else None
        return first

    #subdomain
    host = _host(parts.netloc)
    base = cfg["hosts"][0]
    if host.endswith("." + base):
        return host[: -(len(base) + 1)].split(".")[0]
    return None


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    p = urlsplit(url.strip())
    host = _host(p.netloc)
    path = p.path.rstrip("/")
    return urlunsplit(("https", host, path, "", ""))
