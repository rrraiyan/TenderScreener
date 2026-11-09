"""End-to-end run with fake portals: no network, no email, no AI key."""
import json
import shutil

import pytest

from agent import dates, main
from agent.models import Notice, SourceError
from agent.sources.base import Source


class Good(Source):
    name, label = "good", "Good portal"

    def __init__(self):
        self.scanned = 0

    def fetch(self, since):
        self.scanned = 2
        return [
            Notice("good", "1", "Training on AI for teachers", "https://p/1", published=dates.now()),
            Notice("good", "2", "Supply of cement", "https://p/2", published=dates.now()),
        ]

    def fetch_detail(self, notice):
        return "details"


class Broken(Source):
    name, label = "broken", "Broken portal"

    def __init__(self):
        self.scanned = 0

    def fetch(self, since):
        raise SourceError("layout changed")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    shutil.copy(main.ROOT / "config" / "profile.yaml", tmp_path / "config" / "profile.yaml")
    monkeypatch.setattr(main, "ROOT", tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.delenv("APPS_SCRIPT_URL", raising=False)
    return tmp_path


def test_one_broken_portal_does_not_stop_the_run(isolated, monkeypatch, capsys):
    monkeypatch.setattr(main, "REGISTRY", {"good": Good, "broken": Broken})
    state = isolated / "seen.json"
    code = main.run(["--dry-run", "--save-state", "--state", str(state)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Training on AI for teachers" in out and "Supply of cement" not in out
    assert "unscored" in out                      # fail-open without an API key
    assert "Broken portal: FAILED" in out
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert {"good:1", "good:2"} <= set(saved["seen"])
    assert saved["health"]["broken"]["fail_streak"] == 1

    # second run: everything already seen
    main.run(["--dry-run", "--state", str(state)])
    assert "Training on AI for teachers" not in capsys.readouterr().out


def test_all_portals_failing_exits_nonzero(isolated, monkeypatch):
    monkeypatch.setattr(main, "REGISTRY", {"broken": Broken})
    assert main.run(["--dry-run", "--state", str(isolated / "s.json")]) == 1
