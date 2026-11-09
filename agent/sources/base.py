from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from agent.http import PoliteSession
from agent.models import Notice

PARSER = "html.parser"  # stdlib parser: no native dependency to break on CI or Windows


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def page_text(html: str, selector: str | None = None, limit: int = 4000) -> str:
    """Visible text of a page (or of `selector` inside it), without scripts and navigation."""
    soup = BeautifulSoup(html, PARSER)
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "svg"]):
        tag.decompose()
    root = (soup.select_one(selector) if selector else None) or soup.body or soup
    return clean(root.get_text(" "))[:limit]


class Source:
    """One tender portal. Subclasses implement `fetch` and optionally `fetch_detail`."""

    name: str = ""
    label: str = ""
    bd_only: bool = False  # every notice is for work in Bangladesh
    extra_ca: bool = False

    def __init__(self, session: PoliteSession | None = None) -> None:
        self.session = session or PoliteSession(extra_ca=self.extra_ca)
        self.scanned = 0  # rows read from the portal during the last fetch

    def fetch(self, since: datetime) -> list[Notice]:
        raise NotImplementedError

    def fetch_detail(self, notice: Notice) -> str:
        return page_text(self.session.get(notice.url).text)
