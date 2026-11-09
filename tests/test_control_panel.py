"""Control panel client with a fake Apps Script endpoint (no network)."""
import json

import pytest

from agent import control_panel
from agent.models import Notice
from agent.scorer import Provider, Scorer, Verdict

DEFAULTS = {"company_profile": "yaml profile", "include_keywords": ["training"], "exclude_keywords": ["hotel"],
            "min_score": 6, "sources": {"undp": True, "egp": True}}
SHEET = {"company_profile": "sheet profile", "include_keywords": ["LMS", "coaching"], "exclude_keywords": [],
         "recipients": ["nirjhara@buildnation.com.bd"], "min_score": 8, "sources": {"egp": False},
         "feedback": [{"title": "Supply of laptops", "relevant": False, "verdict": "Not relevant", "note": "goods only"}]}


class FakeResp:
    def __init__(self, data):
        self.data, self.text = data, json.dumps(data)

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


@pytest.fixture
def panel(monkeypatch):
    monkeypatch.setenv("APPS_SCRIPT_URL", "https://script.google.com/macros/s/x/exec")
    monkeypatch.setenv("APPS_SCRIPT_TOKEN", "secret")
    calls = []

    def fake_post(url, data, headers, timeout):
        body = json.loads(data)
        calls.append(body)
        if body["token"] != "secret":
            return FakeResp({"ok": False, "error": "bad token"})
        if body["action"] == "settings":
            return FakeResp({"ok": True, "settings": SHEET})
        return FakeResp({"ok": True, "sent_to": 1, "logged": len(body["matches"])})

    monkeypatch.setattr(control_panel.requests, "post", fake_post)
    return calls


def test_sheet_overrides_defaults_but_empty_columns_do_not_wipe(panel, tmp_path):
    cfg, note = control_panel.load_settings(DEFAULTS, tmp_path / "cache.json")
    assert note is None
    assert cfg["company_profile"] == "sheet profile" and cfg["min_score"] == 8
    assert cfg["include_keywords"] == ["LMS", "coaching"]
    assert cfg["exclude_keywords"] == ["hotel"]                 # sheet column empty -> keep default
    assert cfg["sources"] == {"undp": True, "egp": False}       # merged, not replaced
    assert cfg["recipients"] == ["nirjhara@buildnation.com.bd"]
    assert (tmp_path / "cache.json").exists()


def test_unreachable_sheet_uses_last_saved_copy(panel, tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    control_panel.load_settings(DEFAULTS, cache)                # saves a good copy

    def down(*a, **k):
        raise ConnectionError("no route")

    monkeypatch.setattr(control_panel.requests, "post", down)
    cfg, note = control_panel.load_settings(DEFAULTS, cache)
    assert cfg["min_score"] == 8 and "last saved settings" in note


def test_unreachable_sheet_without_cache_uses_yaml(monkeypatch, tmp_path, panel):
    monkeypatch.setattr(control_panel.requests, "post", lambda *a, **k: (_ for _ in ()).throw(ConnectionError()))
    cfg, note = control_panel.load_settings(DEFAULTS, tmp_path / "none.json")
    assert cfg == DEFAULTS and "profile.yaml" in note


def test_bad_token_is_an_error(panel, monkeypatch):
    monkeypatch.setenv("APPS_SCRIPT_TOKEN", "wrong")
    with pytest.raises(control_panel.ControlPanelError, match="bad token"):
        control_panel.send("s", "<p>h</p>", "t", [])


def test_send_passes_digest_and_matches(panel):
    result = control_panel.send("subject", "<p>html</p>", "text", [{"key": "egp:1", "title": "LMS"}])
    assert result["logged"] == 1
    assert panel[-1]["action"] == "send" and panel[-1]["html"] == "<p>html</p>"


def test_not_configured_means_yaml_only(monkeypatch, tmp_path):
    monkeypatch.delenv("APPS_SCRIPT_URL", raising=False)
    assert control_panel.load_settings(DEFAULTS, tmp_path / "c.json") == (DEFAULTS, None)


def test_reviewer_feedback_reaches_the_prompt():
    seen = {}

    class Capture(Provider):
        name = "Fake"

        @property
        def configured(self):
            return True

        def call(self, prompt):
            seen["prompt"] = prompt
            return [Verdict(key="egp:1", score=7, fit_category="x", deliverable_remote_or_bd=True, reason="r")]

    Scorer("profile", providers=[Capture()], feedback=SHEET["feedback"]).score(
        [Notice("egp", "1", "Training", "https://x", keyword_hits=["training"])], max_items=10)
    assert "NOT RELEVANT: Supply of laptops (note: goods only)" in seen["prompt"]
