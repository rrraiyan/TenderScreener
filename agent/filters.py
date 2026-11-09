from __future__ import annotations

import re

from agent.models import Notice


def _compile(words: list[str]) -> list[tuple[str, re.Pattern]]:
    pats = []
    for w in words:
        w = w.strip()
        if not w:
            continue
        if not w.isascii():
            pats.append((w, re.compile(re.escape(w))))  # Bangla: plain substring
            continue
        # Whole word with optional plural 's'. ALL-CAPS acronyms (IT, AI, LMS) match case-sensitively
        # so that the English words "it" / "ai" do not count as hits.
        flags = 0 if (w.isupper() and len(w) <= 5) else re.IGNORECASE
        pats.append((w, re.compile(rf"(?<![A-Za-z]){re.escape(w)}s?(?![A-Za-z])", flags)))
    return pats


class KeywordFilter:
    """Cheap first pass: keep notices whose title/type mention BuildNation's scope, drop clear mismatches."""

    def __init__(self, include: list[str], exclude: list[str], exclude_types: list[str] | None = None) -> None:
        self.include = _compile(include)
        self.exclude = _compile(exclude)
        self.exclude_types = _compile(exclude_types or [])

    def hits(self, text: str) -> list[str]:
        return [w for w, p in self.include if p.search(text)]

    def blocked(self, n: Notice) -> str | None:
        return (next((w for w, p in self.exclude if p.search(n.title)), None)
                or next((w for w, p in self.exclude_types if p.search(n.notice_type)), None))

    def apply(self, notices: list[Notice]) -> list[Notice]:
        kept = []
        for n in notices:
            if self.blocked(n):
                continue
            hits = self.hits(n.match_text())
            if hits:
                n.keyword_hits = hits
                kept.append(n)
        return kept
