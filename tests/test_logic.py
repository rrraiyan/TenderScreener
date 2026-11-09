from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from agent import dates
from agent.filters import KeywordFilter
from agent.main import dedupe
from agent.models import Notice
from agent.state import State

CFG = yaml.safe_load((Path(__file__).parent.parent / "config" / "profile.yaml").read_text(encoding="utf-8"))


def n(title, source="ungm", id_="1", ref="", type_="Request for proposal"):
    return Notice(source=source, id=id_, title=title, url="https://x", reference=ref, notice_type=type_)


# ---- dates -------------------------------------------------------------------

def test_bangla_digits():
    assert dates.bn_to_ascii("১৭-১০-২০২৬") == "17-10-2026"


def test_ungm_gmt_offset():
    d = dates.parse_gmt_offset("02-Nov-2026 13:00\n (GMT 3.00) 15.03")
    assert d == datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    assert dates.parse_gmt_offset("18-Oct-2026 06:00 (GMT -4.00)").utcoffset() == timedelta(hours=-4)


def test_is_since_compares_dhaka_dates():
    since = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)
    assert dates.is_since(datetime(2026, 10, 18, 0, 0, tzinfo=dates.DHAKA), since)
    assert not dates.is_since(datetime(2026, 10, 17, 23, 0, tzinfo=dates.DHAKA), since)
    assert dates.is_since(None, since)


# ---- keyword filter ------------------------------------------------------------

def kf():
    return KeywordFilter(CFG["include_keywords"], CFG["exclude_keywords"], CFG.get("exclude_notice_types"))


def test_relevant_titles_pass():
    for t in ["Development of an LMS for TVET teachers",
              "Training of trainers on digital skills",
              "Consultancy for capacity building of youth on AI and coding",
              "প্রশিক্ষণ কর্মসূচি পরিচালনা"]:
        assert kf().apply([n(t)]), t


def test_irrelevant_titles_dropped():
    for t in ["Hotel services for training participants",       # exclude wins
              "Construction of training centre building",
              "Supply of cement",                                # no include keyword
              "Is it possible to supply rice"]:                  # lowercase 'it' is not IT
        assert not kf().apply([n(t)]), t


def test_acronyms_case_sensitive():
    assert kf().apply([n("Supply of IT equipment for school")])
    assert not kf().apply([n("Humanitarian aid kits")])


def test_works_type_excluded():
    assert not kf().apply([n("Training hall", source="egp", type_="Works · NCT · OTM")])
    assert kf().apply([n("Training programme", source="egp", type_="Services · ICT · QCBS")])


# ---- state + dedup ----------------------------------------------------------------

def test_cross_portal_dedup_and_memory(tmp_path):
    state = State(tmp_path / "seen.json")
    a = n("Training", source="undp", id_="50822", ref="UNDP-GTM-00219")
    b = n("Training", source="ungm", id_="318000", ref="UNDP-GTM-00219,1")
    c = n("Other", source="egp", id_="9", ref="GD/2026/1")
    fresh = dedupe([a, b, c], state)
    assert fresh == [a, c] and a.also_on == ["https://x"]

    today = date(2026, 10, 19)
    for x in fresh:
        state.mark(x.key, x.norm_ref, today)
    state.save()
    reloaded = State(tmp_path / "seen.json")
    again = n("Training", source="ungm", id_="318001", ref="UNDP-GTM-00219")
    assert dedupe([a, c, again], reloaded) == []


def test_local_refs_do_not_merge():
    # e-GP re-tenders reuse free-text references; only UN-style refs are merged
    assert n("x", ref="GD/2026/1").norm_ref is None
    assert n("x", ref="UNDP-AFG-00886,1").norm_ref == "UNDP-AFG-00886"


def test_prune_and_health(tmp_path):
    state = State(tmp_path / "s.json")
    state.mark("old:1", None, date(2026, 1, 1))
    state.mark("new:1", None, date(2026, 10, 1))
    state.prune(date(2026, 10, 19))
    assert list(state.seen) == ["new:1"]
    assert state.record_health("egp", False, date(2026, 10, 19)) == 1
    assert state.record_health("egp", False, date(2026, 10, 20)) == 2
    assert state.record_health("egp", True, date(2026, 10, 21)) == 0
