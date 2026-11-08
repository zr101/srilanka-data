"""Bounded public-source requests; permanent denials must remain visible."""
import time
import requests

USER_AGENT = "srilanka-data (open-source dataset; github.com/zr101/srilanka-data)"
RETRYABLE = {408, 429, 500, 502, 503, 504}


def get(url: str, retries: int = 3, timeout: tuple[int, int] | int = (10, 45)) -> requests.Response:
    if retries < 1:
        raise ValueError("retries must be positive")
    for attempt in range(retries):
        try:
            res = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if res.status_code == 404:
                return res
            res.raise_for_status()
            return res
        except requests.RequestException as err:
            response = getattr(err, "response", None)
            if response is not None and response.status_code not in RETRYABLE:
                raise RuntimeError(f"GET {url}: HTTP {response.status_code}; source access failed") from err
            if attempt == retries - 1:
                raise RuntimeError(f"GET {url} failed after {retries} attempts: {err}") from err
            retry_after = response.headers.get("Retry-After", "") if response is not None else ""
            delay = min(float(retry_after), 30) if retry_after.isdigit() else 2 ** attempt
            time.sleep(delay)
    raise AssertionError("unreachable")


def get_pdf(url: str) -> bytes | None:
    res = get(url)
    if res.status_code == 404:
        return None
    if not res.content.startswith(b"%PDF"):
        raise ValueError(f"{url} did not return a PDF (magic bytes missing)")
    return res.content
