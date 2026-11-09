"""AI relevance scoring with a provider chain: Gemini first, Cohere as fallback, then fail-open.

Each batch goes to the first provider still healthy; a provider that fails or times out
twice is skipped for the rest of the run, so one slow/overloaded service cannot stall the job.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import requests
from pydantic import BaseModel, Field, ValidationError

from agent.models import Notice

log = logging.getLogger(__name__)

BATCH_SIZE = 8
DETAIL_CHARS = 1500
MAX_FAILURES = 2        # per provider per run, then it is skipped


class Verdict(BaseModel):
    key: str = Field(description="The notice key exactly as given")
    score: int = Field(ge=0, le=10, description="Fit for the company, 0 = irrelevant, 10 = perfect")
    fit_category: str = Field(description="Short label, e.g. 'LMS', 'Training', 'Consultancy', 'Not a fit'")
    deliverable_remote_or_bd: bool = Field(description="Can be delivered remotely or within Bangladesh")
    reason: str = Field(description="One sentence, max 25 words, why it fits or not")


PROMPT = """You screen public tenders for this company:

{profile}

Rules:
- Score 0-10 for how well the company could bid as the lead or a partner. Nearby scope it could grow into counts (score 5-7).
- deliverable_remote_or_bd is true only if the work can be done remotely/online or physically inside Bangladesh.
  Notices marked [BANGLADESH] are already in Bangladesh. Work requiring presence in another country is false.
- Goods-only supply, construction, travel, hotels, logistics and medical items score 0-2.
- Be strict and concise. Return one verdict per notice, using its key.
{feedback}
Notices:
{items}
"""

JSON_INSTRUCTIONS = """
Reply with JSON only, exactly this shape:
{"verdicts": [{"key": "...", "score": 0, "fit_category": "...", "deliverable_remote_or_bd": true, "reason": "..."}]}
"""


def _describe(n: Notice) -> str:
    parts = [
        f"key: {n.key}",
        f"title: {n.title}",
        f"organization: {n.org}",
        f"country: {n.country}{' [BANGLADESH]' if n.bd_only else ''}",
        f"type: {n.notice_type}",
    ]
    if n.detail_text:
        parts.append(f"details: {n.detail_text[:DETAIL_CHARS]}")
    return "\n".join(parts)


def feedback_block(feedback: list[dict] | None) -> str:
    """Reviewer verdicts from the control panel, shown to the AI as calibration examples."""
    if not feedback:
        return ""
    lines = ["", "Past notices the company's reviewers judged (follow this taste):"]
    for f in feedback[:30]:
        mark = "RELEVANT" if f.get("relevant") else "NOT RELEVANT"
        note = f" (note: {f['note']})" if f.get("note") else ""
        lines.append(f"- {mark}: {f.get('title', '')[:140]}{note}")
    return "\n".join(lines) + "\n"


def parse_verdicts(text: str) -> list[Verdict]:
    """Parse {"verdicts": [...]} or a bare list, tolerating ```json fences; skip invalid items."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(text)
    items = data.get("verdicts", []) if isinstance(data, dict) else data
    out = []
    for item in items:
        try:
            out.append(Verdict.model_validate(item))
        except ValidationError:
            continue
    return out


class Provider:
    name = ""
    min_interval = 0.0  # seconds between calls (free-tier rate limits)
    timeout = 60        # seconds per call; Gemini was seen taking 5+ minutes under load

    def __init__(self) -> None:
        self.failures = 0
        self._last = 0.0

    @property
    def configured(self) -> bool:
        raise NotImplementedError

    def call(self, prompt: str) -> list[Verdict]:
        raise NotImplementedError

    def run(self, prompt: str) -> list[Verdict]:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            return self.call(prompt)
        finally:
            self._last = time.monotonic()


class Gemini(Provider):
    name = "Gemini"
    min_interval = 13  # under 5 requests/minute, the lowest free-tier limit seen

    def __init__(self) -> None:
        super().__init__()
        self.key = os.environ.get("GEMINI_API_KEY", "")
        self.model = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def call(self, prompt: str) -> list[Verdict]:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=self.key, http_options=types.HttpOptions(timeout=self.timeout * 1000))
        resp = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[Verdict],
                temperature=0.1,
            ),
        )
        return resp.parsed or []


class Cohere(Provider):
    name = "Cohere"
    min_interval = 4  # trial keys allow 20 chat calls/minute
    timeout = 150     # command-a is slow (~45 s for a small batch) but reliable

    def __init__(self) -> None:
        super().__init__()
        self.key = os.environ.get("COHERE_API_KEY", "")
        self.model = os.environ.get("COHERE_MODEL") or "command-a-03-2025"

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def call(self, prompt: str) -> list[Verdict]:
        resp = requests.post(
            "https://api.cohere.com/v2/chat",
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt + JSON_INSTRUCTIONS}],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return parse_verdicts("".join(part.get("text", "") for part in content))


class Scorer:
    def __init__(self, profile: str, providers: list[Provider] | None = None,
                 feedback: list[dict] | None = None) -> None:
        self.profile = profile
        self.feedback = feedback_block(feedback)
        self.providers = [p for p in (providers or [Gemini(), Cohere()]) if p.configured]
        self.used: dict[str, int] = {}   # provider -> batches scored, for the email footer
        self.errors: list[str] = []

    @property
    def error(self) -> str | None:
        """Short note for the email footer; None when everything went smoothly."""
        if not self.providers:
            return "no AI key set (GEMINI_API_KEY / COHERE_API_KEY)"
        notes = []
        if self.used:
            notes.append("scored by " + ", ".join(f"{k} ({v} batch{'es' if v != 1 else ''})" for k, v in self.used.items()))
        notes += self.errors[-3:]
        return "; ".join(notes) if self.errors else None

    def _score_batch(self, batch: list[Notice]) -> list[Verdict]:
        prompt = PROMPT.format(profile=self.profile.strip(), feedback=self.feedback, items="\n\n---\n\n".join(_describe(n) for n in batch))
        for p in self.providers:
            if p.failures >= MAX_FAILURES:
                continue
            try:
                verdicts = p.run(prompt)
                if verdicts:
                    self.used[p.name] = self.used.get(p.name, 0) + 1
                    return verdicts
                raise ValueError("empty response")
            except Exception as e:  # overloaded, timed out, bad JSON...: try the next provider
                p.failures += 1
                msg = f"{p.name} failed: {type(e).__name__}: {str(e)[:120]}"
                self.errors.append(msg)
                log.warning(msg)
        return []

    def score(self, notices: list[Notice], max_items: int) -> None:
        """Fill score/fit/reason in place. Notices left unscored keep score=None (fail-open)."""
        if not self.providers:
            return
        todo = sorted(notices, key=lambda n: -len(n.keyword_hits))[:max_items]
        for i in range(0, len(todo), BATCH_SIZE):
            batch = todo[i:i + BATCH_SIZE]
            verdicts = {v.key: v for v in self._score_batch(batch)}
            for n in batch:
                v = verdicts.get(n.key)
                if v:
                    n.score = v.score
                    n.fit_category = v.fit_category
                    n.deliverable = v.deliverable_remote_or_bd
                    n.reason = v.reason
