from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from agent import dates
from agent.models import Notice, SourceError
from agent.sources.base import PARSER, Source, clean

BASE = "https://procurement-notices.undp.org"


def parse_list(html: str) -> list[Notice]:
    """Parse the public UNDP notices page (mirror of every UNDP Quantum negotiation)."""
    soup = BeautifulSoup(html, PARSER)
    notices = []
    for row in soup.select("a.vacanciesTableLink"):
        m = re.search(r"nego_id=(\d+)", row.get("href", ""))
        if not m:
            continue
        fields = {}
        for cell in row.select(".vacanciesTable__cell"):
            label = cell.select_one(".vacanciesTable__cell__label")
            key = clean(label.get_text()).lower() if label else ""
            if label:
                label.extract()
            fields[key] = clean(cell.get_text(" "))
        office = fields.get("undp office/country", "")
        deadline = re.sub(r"\s*\(New York time\)", "", fields.get("deadline", ""))
        notices.append(Notice(
            source="undp",
            id=m.group(1),
            title=fields.get("title", ""),
            url=f"{BASE}/view_negotiation.cfm?nego_id={m.group(1)}",
            reference=fields.get("ref no", ""),
            org="UNDP " + office.split("/")[0].replace("UNDP-", "") if office else "UNDP",
            country=office.split("/", 1)[1].title() if "/" in office else office,
            notice_type=fields.get("process", ""),
            deadline=dates.parse(deadline, "%d-%b-%y %I:%M %p", dates.NEW_YORK),
            published=dates.parse(fields.get("posted", ""), "%d-%b-%y", dates.NEW_YORK),
        ))
    return notices


class UNDP(Source):
    name = "undp"
    label = "UNDP (Quantum)"

    def fetch(self, since: datetime) -> list[Notice]:
        rows = parse_list(self.session.get(f"{BASE}/").text)
        if not rows:
            raise SourceError("UNDP notices page returned no rows (layout changed?)")
        self.scanned = len(rows)
        return [n for n in rows if dates.is_since(n.published, since)]
