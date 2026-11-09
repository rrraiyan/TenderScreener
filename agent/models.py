from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

_UN_REF = re.compile(r"^([A-Z]{2,8}-[A-Z]{3}-\d{4,})")


@dataclass
class Notice:
    source: str
    id: str
    title: str
    url: str
    org: str = ""
    country: str = ""
    notice_type: str = ""
    reference: str = ""
    published: datetime | None = None
    deadline: datetime | None = None
    bd_only: bool = False  # source only publishes Bangladesh-based work
    detail_text: str = ""
    keyword_hits: list[str] = field(default_factory=list)
    score: float | None = None
    fit_category: str = ""
    deliverable: bool | None = None
    reason: str = ""
    also_on: list[str] = field(default_factory=list)  # extra URLs of the same notice elsewhere

    @property
    def key(self) -> str:
        return f"{self.source}:{self.id}"

    @property
    def norm_ref(self) -> str | None:
        """UN-style reference used for cross-portal dedup: 'UNDP-AFG-00886,1' -> 'UNDP-AFG-00886'.

        Only this agency-country-number shape is used; local portals (e.g. e-GP re-tenders)
        reuse free-text references, so matching on those would hide genuinely new notices.
        """
        m = _UN_REF.match(re.sub(r"\s+", "", self.reference.upper()))
        return m.group(1) if m else None

    def match_text(self) -> str:
        # Title only. Organisation names would match a "Training Institute" buying chairs, and
        # type codes collide with keywords (e-GP "ICT" = International Competitive Tendering).
        return self.title


class SourceError(RuntimeError):
    """A portal could not be read or its page layout changed."""
