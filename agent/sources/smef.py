from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from agent import dates
from agent.models import Notice, SourceError
from agent.sources.base import PARSER, Source, clean, page_text

BASE = "https://smef.gov.bd"

# The SME Foundation notice board mixes HR/admin notices with procurement; keep procurement only.
PROCUREMENT = re.compile(
    r"\b(rfq|rfp|eoi|reoi|tender|quotation|proposal|expression of interest|bid|procurement)\b"
    r"|দরপত্র|কোটেশন|আগ্রহপত্র|দর প্রস্তাব|ক্রয়",
    re.IGNORECASE,
)


def parse_list(html: str) -> list[Notice]:
    soup = BeautifulSoup(html, PARSER)
    notices = []
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        link = tr.select_one('a[href*="/pages/notices/"]')
        if len(tds) < 5 or not link:
            continue
        href = link["href"]
        title = clean(tds[1].get_text(" "))
        attachment = next((a["href"] for a in tr.select("a[href]") if "/pages/notices/" not in a["href"]), "")
        notices.append(Notice(
            source="smef",
            id=href.rstrip("/").rsplit("-", 1)[-1],
            title=title,
            url=urljoin(BASE, href),
            org="SME Foundation",
            country="Bangladesh",
            notice_type="Notice",
            published=dates.parse(dates.bn_to_ascii(clean(tds[4].get_text())), "%d-%m-%Y", dates.DHAKA),
            bd_only=True,
            also_on=[attachment] if attachment else [],
        ))
    return notices


class SMEF(Source):
    name = "smef"
    label = "SME Foundation"
    bd_only = True
    extra_ca = True  # smef.gov.bd serves an incomplete TLS chain; see agent/http.py

    def fetch(self, since: datetime) -> list[Notice]:
        rows = parse_list(self.session.get(f"{BASE}/pages/notices").text)
        if not rows:
            raise SourceError("SME Foundation notice table returned no rows (layout changed?)")
        self.scanned = len(rows)
        return [n for n in rows if dates.is_since(n.published, since) and PROCUREMENT.search(n.title)]

    def fetch_detail(self, notice: Notice) -> str:
        return page_text(self.session.get(notice.url).text, ".content-viewer-widget")
