import time

import requests

USER_AGENT = "srilanka-data (open-source dataset; github.com/zr101/srilanka-data)"


def get(url: str, retries: int = 3, timeout: int = 30) -> requests.Response:
    """GET with an honest UA and exponential backoff."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            res = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if res.status_code == 404:
                return res  # a valid "does not exist" answer; let callers decide
            res.raise_for_status()
            return res
        except requests.RequestException as err:
            last_err = err
            time.sleep(2**attempt)
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_err}")


def get_pdf(url: str) -> bytes | None:
    """Download a PDF, returning None on 404 and raising on non-PDF payloads."""
    res = get(url)
    if res.status_code == 404:
        return None
    if not res.content.startswith(b"%PDF"):
        raise ValueError(f"{url} did not return a PDF (magic bytes missing)")
    return res.content
