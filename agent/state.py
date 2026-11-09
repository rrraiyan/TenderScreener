from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

RETENTION_DAYS = 90


class State:
    """Persistent memory of notices already processed, stored as JSON in the repo."""

    def __init__(self, path: Path) -> None:
        self.path = path
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.seen: dict[str, str] = data.get("seen", {})
        self.refs: dict[str, str] = data.get("refs", {})
        self.health: dict[str, dict] = data.get("health", {})

    def is_seen(self, key: str, norm_ref: str | None) -> bool:
        return key in self.seen or (norm_ref is not None and norm_ref in self.refs)

    def mark(self, key: str, norm_ref: str | None, today: date) -> None:
        self.seen.setdefault(key, today.isoformat())
        if norm_ref:
            self.refs.setdefault(norm_ref, today.isoformat())

    def record_health(self, source: str, ok: bool, today: date, detail: str = "") -> int:
        """Update the source's failure streak; returns the new streak length."""
        h = self.health.setdefault(source, {"fail_streak": 0, "last_ok": None})
        if ok:
            h["fail_streak"] = 0
            h["last_ok"] = today.isoformat()
        else:
            h["fail_streak"] = h.get("fail_streak", 0) + 1
        h["last_detail"] = detail
        return h["fail_streak"]

    def prune(self, today: date) -> None:
        cutoff = (today - timedelta(days=RETENTION_DAYS)).isoformat()
        self.seen = {k: v for k, v in self.seen.items() if v >= cutoff}
        self.refs = {k: v for k, v in self.refs.items() if v >= cutoff}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seen": dict(sorted(self.seen.items())), "refs": dict(sorted(self.refs.items())), "health": self.health}
        self.path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
