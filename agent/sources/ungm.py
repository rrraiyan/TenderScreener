from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from agent import dates
from agent.models import Notice, SourceError
from agent.sources.base import PARSER, Source, clean, page_text

BASE = "https://www.ungm.org"
PAGE_SIZE = 15  # the endpoint answers 400 Bad Request for any other page size
MAX_PAGES = 80


def parse_search(html: str) -> list[Notice]:
    """Parse the HTML fragment returned by POST /Public/Notice/Search."""
    soup = BeautifulSoup(html, PARSER)
    notices = []
    for row in soup.select("div[data-noticeid]"):
        cells = row.find_all(attrs={"role": "cell"}, recursive=False)
        if len(cells) < 8:
            continue
        nid = row["data-noticeid"]
        title_el = cells[1].select_one(".ungm-title") or cells[1]
        notices.append(Notice(
            source="ungm",
            id=nid,
            title=clean(title_el.get_text(" ")),
            url=f"{BASE}/Public/Notice/{nid}",
            deadline=dates.parse_gmt_offset(clean(cells[2].get_text(" "))),
            published=dates.parse(clean(cells[3].get_text()), "%d-%b-%Y", timezone.utc),
            org=clean(cells[4].get_text(" ")),
            notice_type=clean(cells[5].get_text(" ")),
            reference=clean(cells[6].get_text(" ")),
            country=clean(cells[7].get_text(" ")),
        ))
    return notices


class UNGM(Source):
    name = "ungm"
    label = "UNGM"

    def _token(self) -> str:
        html = self.session.get(f"{BASE}/Public/Notice").text
        el = BeautifulSoup(html, PARSER).select_one("input[name=__RequestVerificationToken]")
        if not el or not el.get("value"):
            raise SourceError("UNGM anti-forgery token not found (page layout changed or access blocked)")
        return el["value"]

    def fetch(self, since: datetime) -> list[Notice]:
        token = self._token()
        body = {
            "PageIndex": 0, "PageSize": PAGE_SIZE, "Title": "", "Description": "", "Reference": "",
            "PublishedFrom": since.strftime("%d-%b-%Y"), "PublishedTo": dates.now().strftime("%d-%b-%Y"),
            "DeadlineFrom": "", "DeadlineTo": "", "Countries": [], "Agencies": [], "UNSPSCs": [],
            "NoticeTypes": [], "SortField": "DatePublished", "SortAscending": False, "isPicker": False,
            "IsSustainable": False, "IsActive": True, "NoticeDisplayType": None,
            "NoticeSearchTotalLabelId": "noticeSearchTotal", "TypeOfCompetitions": [],
        }
        headers = {"RequestVerificationToken": token, "X-Requested-With": "XMLHttpRequest"}
        found: dict[str, Notice] = {}
        for page in range(MAX_PAGES):
            body["PageIndex"] = page
            html = self.session.post(f"{BASE}/Public/Notice/Search", json=body, headers=headers).text
            rows = parse_search(html)
            if page == 0 and not rows and "data-noticeid" not in html and "noticeSearchTotal" not in html:
                raise SourceError("UNGM search returned an unexpected page (layout changed?)")
            new = [n for n in rows if n.id not in found]
            if not new:
                break
            found.update({n.id: n for n in new})
            self.scanned += len(rows)
        return [n for n in found.values() if dates.is_since(n.published, since)]

    def fetch_detail(self, notice: Notice) -> str:
        html = self.session.get(notice.url).text
        soup = BeautifulSoup(html, PARSER)
        full_title = soup.select_one(".ungm-title--large, h1, .title")
        if full_title and len(clean(full_title.get_text())) > len(notice.title):
            notice.title = clean(full_title.get_text())
        return page_text(html, "main, #content, .content")
