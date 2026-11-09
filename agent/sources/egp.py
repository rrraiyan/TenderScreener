from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from agent import dates
from agent.models import Notice, SourceError
from agent.sources.base import PARSER, Source, clean, page_text

BASE = "https://www.eprocure.gov.bd"
PAGE_SIZE = 100
MAX_PAGES = 15


def _parts(td) -> list[str]:
    return [clean(p).strip(",").strip() for p in td.get_text("\n").split("\n") if clean(p).strip(",")]


def parse_page(html: str) -> list[Notice]:
    """Parse the <tr> fragment returned by POST /TenderDetailsServlet (funName=AllTenders)."""
    soup = BeautifulSoup(f"<table>{html}</table>", PARSER)
    notices = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        id_input = tr.find("input", attrs={"name": "id"})
        if len(tds) < 6 or not id_input:
            continue
        ids = _parts(tds[1])            # [tender id, reference..., status]
        nature_title = _parts(tds[2])   # [Goods|Works|Services, title...]
        org = _parts(tds[3])            # [ministry, division, organization, procuring entity]
        method = _parts(tds[4])         # [NCT|ICT, OTM|LTM|...]
        when = _parts(tds[5])           # [published, closing]
        tid = id_input["value"]
        notices.append(Notice(
            source="egp",
            id=tid,
            title=" ".join(nature_title[1:]) or (nature_title[0] if nature_title else ""),
            url=f"{BASE}/resources/common/ViewTender.jsp?id={tid}&h=t",
            reference=", ".join(ids[1:-1]) if len(ids) > 2 else "",
            org=" / ".join(org[-2:]),
            country="Bangladesh",
            notice_type=" · ".join(filter(None, [nature_title[0] if nature_title else "", *method])),
            published=dates.parse(when[0], "%d-%b-%Y %H:%M", dates.DHAKA) if when else None,
            deadline=dates.parse(when[1], "%d-%b-%Y %H:%M", dates.DHAKA) if len(when) > 1 else None,
            bd_only=True,
        ))
    return notices


class EGP(Source):
    name = "egp"
    label = "Bangladesh e-GP"
    bd_only = True

    def fetch(self, since: datetime) -> list[Notice]:
        found: dict[str, Notice] = {}
        for page in range(1, MAX_PAGES + 1):
            html = self.session.post(f"{BASE}/TenderDetailsServlet", data={
                "funName": "AllTenders", "keyword": "", "pageNo": str(page), "size": str(PAGE_SIZE),
                "homeWSearch": "homeWSearch", "approve": "false", "h": "t",
            }).text
            rows = parse_page(html)
            if page == 1 and not rows:
                raise SourceError("e-GP tender list returned no rows (layout changed?)")
            self.scanned += len(rows)
            found.update({n.id: n for n in rows})
            # newest first: stop once the whole page is older than the window
            if not rows or not any(dates.is_since(n.published, since) for n in rows):
                break
        return [n for n in found.values() if dates.is_since(n.published, since)]

    def fetch_detail(self, notice: Notice) -> str:
        return page_text(self.session.get(notice.url).text, ".contentArea_1, .pageContent, #content")
