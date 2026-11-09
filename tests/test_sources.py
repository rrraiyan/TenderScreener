"""Parsers against real portal responses saved in tests/fixtures/ (refresh them when a portal changes)."""
import json
from pathlib import Path

from agent.sources import brac, egp, smef, undp, ungm

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def assert_complete(notices, min_rows):
    assert len(notices) >= min_rows
    for n in notices:
        assert n.id and n.title and n.url.startswith("https://")
        assert n.published is not None and n.published.tzinfo is not None


def test_ungm():
    rows = ungm.parse_search(read("ungm_search.html"))
    assert_complete(rows, 10)
    n = rows[0]
    assert n.url == f"https://www.ungm.org/Public/Notice/{n.id}"
    assert n.org and n.country and n.deadline is not None
    assert "Open in a new window" not in n.title


def test_undp():
    rows = undp.parse_list(read("undp_list.html"))
    assert_complete(rows, 100)
    n = rows[0]
    assert "nego_id=" in n.url
    assert n.reference.startswith("UNDP-") and n.norm_ref == n.reference
    assert n.deadline is not None and n.country


def test_egp():
    rows = egp.parse_page(read("egp_page.html"))
    assert_complete(rows, 100)
    n = rows[0]
    assert n.id.isdigit() and f"id={n.id}" in n.url
    assert n.bd_only and n.country == "Bangladesh"
    assert n.notice_type.split(" · ")[0] in {"Goods", "Works", "Services"}
    assert n.deadline > n.published
    # newest first, which the pager relies on
    assert rows[0].published >= rows[-1].published


def test_brac():
    rows = brac.parse_list(json.loads(read("brac_live.json")))
    assert_complete(rows, 10)
    assert all(n.bd_only and n.reference for n in rows)
    assert rows[0].url == f"https://tender.brac.net/tender/tenderDetails?id={rows[0].id}"


def test_smef():
    rows = smef.parse_list(read("smef_notices.html"))
    assert_complete(rows, 5)
    assert len({n.id for n in rows}) == len(rows)
    procurement = [n for n in rows if smef.PROCUREMENT.search(n.title)]
    assert procurement, "fixture should contain at least one RFQ/REOI notice"
    assert not smef.PROCUREMENT.search("নিয়োগ বিজ্ঞপ্তি (ব্যবস্থাপনা পরিচালক)")  # a job notice is not a tender
