"""Provider chain: fallback, circuit breaker, fail-open, and tolerant JSON parsing (no network)."""
from agent.models import Notice
from agent.scorer import Provider, Scorer, Verdict, parse_verdicts


class Fake(Provider):
    def __init__(self, name, fail=False):
        super().__init__()
        self.name, self.fail, self.calls = name, fail, 0

    @property
    def configured(self):
        return True

    def call(self, prompt):
        self.calls += 1
        if self.fail:
            raise TimeoutError("503 high demand")
        keys = [line[5:] for line in prompt.splitlines() if line.startswith("key: ")]
        return [Verdict(key=k, score=8, fit_category="Training", deliverable_remote_or_bd=True, reason="ok") for k in keys]


def notices(count):
    return [Notice("egp", str(i), f"Training {i}", "https://x", keyword_hits=["training"]) for i in range(count)]


def test_falls_back_and_skips_broken_provider():
    primary, backup = Fake("Gemini", fail=True), Fake("Cohere")
    s = Scorer("profile", providers=[primary, backup])
    items = notices(24)  # 3 batches
    s.score(items, max_items=100)
    assert all(n.score == 8 for n in items)
    assert primary.calls == 2          # skipped after MAX_FAILURES
    assert backup.calls == 3
    assert "Cohere (3 batches)" in s.error


def test_all_providers_down_is_fail_open():
    s = Scorer("profile", providers=[Fake("Gemini", fail=True), Fake("Cohere", fail=True)])
    items = notices(5)
    s.score(items, max_items=100)
    assert all(n.score is None for n in items)
    assert "failed" in s.error


def test_healthy_primary_leaves_no_footer_note():
    s = Scorer("profile", providers=[Fake("Gemini"), Fake("Cohere")])
    s.score(notices(3), max_items=100)
    assert s.error is None


def test_parse_verdicts_tolerates_fences_and_bad_items():
    text = '```json\n{"verdicts": [{"key": "egp:1", "score": 7, "fit_category": "LMS", ' \
           '"deliverable_remote_or_bd": true, "reason": "fits"}, {"key": "egp:2", "score": 99}]}\n```'
    out = parse_verdicts(text)
    assert [v.key for v in out] == ["egp:1"]
