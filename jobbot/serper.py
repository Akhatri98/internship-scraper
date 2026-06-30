import time
import requests
from . import config

_URL = "https://google.serper.dev/search"


def search(q: str, page: int = 1, num: int | None = None, session=None, attempts: int = 3) -> dict:
    sess = session or requests
    payload: dict = {"q": q, "page": page}
    if num is not None:
        payload["num"] = num
    headers = {"X-API-KEY": config.require("SERPER_API_KEY"), "Content-Type": "application/json"}

    last = None
    for i in range(attempts):
        try:
            r = sess.post(_URL, json=payload, headers=headers, timeout=30)
        except (requests.ConnectionError, requests.Timeout) as e:
            last = e
            time.sleep(0.5 * (2 ** i))
            continue
        if r.status_code == 429:
            last = requests.HTTPError("429 rate limited", response=r)
            time.sleep(1.0 * (2 ** i))
            continue
        if r.status_code >= 500:
            last = requests.HTTPError(f"{r.status_code} server error", response=r)
            time.sleep(0.5 * (2 ** i))
            continue
        r.raise_for_status()
        return r.json()
    raise last
