from __future__ import annotations

from datetime import datetime

from agent import dates
from agent.models import Notice, SourceError
from agent.sources.base import Source, clean

BASE = "https://tender.brac.net"


def parse_list(data: dict) -> list[Notice]:
    """Parse the JSON from /tender/loadTenderExternalList (jqGrid rows)."""
    notices = []
    for row in data.get("rows", []):
        c = row.get("cell", [])
        if len(c) < 8:
            continue
        tid = str(row.get("id") or c[0])
        notices.append(Notice(
            source="brac",
            id=tid,
            title=clean(c[2]),
            url=f"{BASE}/tender/tenderDetails?id={tid}",
            reference=clean(c[1]),
            org="BRAC",
            country="Bangladesh",
            notice_type=" · ".join(filter(None, [clean(c[3]), clean(c[4])])),
            published=dates.parse(c[5], "%d/%m/%Y %I:%M %p", dates.DHAKA),
            deadline=dates.parse(c[6], "%d/%m/%Y %I:%M %p", dates.DHAKA),
            bd_only=True,
        ))
    return notices


class BRAC(Source):
    name = "brac"
    label = "BRAC e-Tender"
    bd_only = True

    def fetch(self, since: datetime) -> list[Notice]:
        data = self.session.get(f"{BASE}/tender/loadTenderExternalList", params={
            "tenderState": "liveTender", "hubId": "", "_search": "false",
            "rows": "500", "page": "1", "sidx": "id", "sord": "desc",
        }).json()
        if "rows" not in data:
            raise SourceError("BRAC tender list JSON has no 'rows' (API changed?)")
        rows = parse_list(data)
        self.scanned = len(rows)
        return [n for n in rows if dates.is_since(n.published, since)]

    def fetch_detail(self, notice: Notice) -> str:
        # Detail pages redirect to the vendor login; the list title already carries the scope.
        return ""
