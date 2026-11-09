from __future__ import annotations

import tempfile
import time
from functools import lru_cache
from pathlib import Path

import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# UNGM answers 403 to any User-Agent carrying a bot/library token, so a plain browser UA is used.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
TIMEOUT = 30
POLITE_DELAY = 1.0  # seconds between requests to the same portal


CERTS_DIR = Path(__file__).parent / "certs"


@lru_cache(maxsize=1)
def ca_bundle_with_extras() -> str:
    """certifi's CA bundle plus the intermediates in agent/certs/.

    Some portals (e.g. smef.gov.bd) serve an incomplete TLS chain. Browsers repair this on the fly;
    Python does not, so the missing public intermediate is shipped here and verification stays on.
    """
    parts = [Path(certifi.where()).read_text(encoding="utf-8")]
    parts += [p.read_text(encoding="utf-8") for p in sorted(CERTS_DIR.glob("*.pem"))]
    path = Path(tempfile.gettempdir()) / "tenderwatch-ca-bundle.pem"
    path.write_text("\n".join(parts), encoding="utf-8")
    return str(path)


class PoliteSession(requests.Session):
    """requests.Session with retries, a default timeout and a small delay between calls."""

    def __init__(self, extra_ca: bool = False) -> None:
        super().__init__()
        if extra_ca:
            self.verify = ca_bundle_with_extras()
        retry = Retry(
            total=4,
            backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.mount("https://", adapter)
        self.mount("http://", adapter)
        self.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._last = 0.0

    def request(self, method, url, **kwargs):  # type: ignore[override]
        wait = POLITE_DELAY - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        kwargs.setdefault("timeout", TIMEOUT)
        try:
            resp = super().request(method, url, **kwargs)
        finally:
            self._last = time.monotonic()
        resp.raise_for_status()
        return resp
