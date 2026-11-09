# TenderScreener

**An autonomous agent that screens public procurement portals every day and emails only the tenders worth bidding on.**

Organisations that bid for consulting and training contracts lose hours scanning tender portals, and most of what they read is irrelevant (fuel, vehicles, construction…). TenderScreener reads roughly **1,000 new notices a day** from several international and national portals, narrows them to a few dozen candidates, has an LLM judge each one against the organisation's service list, and delivers a short ranked digest by email.

Non-technical staff control what it looks for (services, keywords, recipients, thresholds) from a **Google Sheet**, with no code changes. Their *Relevant / Not relevant* verdicts on past results are fed back to the model, so the screening adapts to the organisation over time.

---

## How it works

```
GitHub Actions (daily cron, serverless)
  │
  ├─ Settings    pull services, keywords, recipients from the Google Sheet control panel
  │              (falls back to the last saved copy if the sheet is unreachable)
  ├─ Fetch       one adapter per portal: HTML scraping, JSON APIs, token-protected search endpoints
  ├─ Dedupe      persistent memory of processed notices + cross-portal merge of the same tender
  ├─ Filter      keyword pre-filter on titles (English and Bangla)  ~1,000 → ~40
  ├─ Enrich      fetch detail pages for the shortlist only
  ├─ Score       LLM rates fit 0-10, checks deliverability, writes a one-line reason
  │              provider chain: Gemini → Cohere → "unscored" (fail-open: nothing is lost)
  ├─ Deliver     HTML digest sent by Google Apps Script; matches logged to the sheet
  └─ Remember    commit state back to the repo for the next run
```

## Engineering highlights

- **Fault isolation:** each portal is independent. One broken or slow site never stops the run, and per-portal health with failure streaks is reported in every email.
- **Resilient LLM layer:** batched structured-JSON prompts, per-call timeouts, a circuit breaker that drops a failing provider for the rest of the run, and automatic fallback between free-tier providers. Built after observing real overload behaviour: 503/504 errors and five-minute responses.
- **No-code control and a feedback loop:** a Google Sheet plus Apps Script web app serves settings, sends email from an organisational account (no stored mailbox passwords) and logs results. Reviewers' verdicts become few-shot examples in the scoring prompt.
- **Exactly-once reporting:** a 2-day overlapping lookback plus persistent dedup means a missed run never loses notices and nothing is reported twice. State is saved only after a successful send.
- **Real-world scraping quirks handled:** anti-forgery tokens, fixed page-size APIs, User-Agent filtering, a server with an incomplete TLS chain (fixed by bundling the missing public intermediate certificate, keeping verification on), Bangla-numeral dates and mixed time zones.
- **Tested offline:** 28 pytest tests run against recorded real portal responses and fake LLM and email endpoints, and gate every scheduled run.
- **Zero cost:** GitHub Actions, free LLM tiers and Google Workspace. Secrets live only in GitHub Actions secrets, and the schedule is disabled unless explicitly enabled per repository.

## Tech stack

Python 3.12 · requests · BeautifulSoup · Pydantic · Google Gemini & Cohere APIs · Google Apps Script · GitHub Actions · pytest

## Project structure

```
agent/
  main.py            pipeline orchestration and CLI (--dry-run, --source, --since)
  sources/           one adapter per portal behind a common Source interface
  scorer.py          LLM provider chain, prompts, JSON validation, feedback examples
  control_panel.py   Google Sheet settings + delivery client, with cache fallback
  filters.py         keyword pre-filter
  state.py           dedup memory and portal health
  notify.py          HTML/text digest rendering
apps_script/Code.gs  Google Sheet control panel, mailer and results log
config/profile.yaml  default settings (overridden by the sheet)
tests/               offline tests with recorded portal fixtures
```

## Run locally

```bash
python -m venv .venv && .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
cp .env.example .env                             # add API keys
python -m agent.main --dry-run                   # writes dist/digest.html, sends nothing
```
