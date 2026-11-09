# Handover note for the next coding agent (Antigravity)

Read this first. It covers what exists, what was verified, what is left, and the decisions you should not undo.

## Goal
A free, production-grade daily agent for **BuildNation**, a Bangladesh edtech company (LMS, training, consultancy, IT/AI/coding, leadership, vocational). Every day it checks five tender portals, keeps new notices that fit BuildNation's scope and can be **delivered remotely or inside Bangladesh**, and emails one HTML digest. Email only for now; WhatsApp/Telegram may come later.

## Status (as of 2026-10-19)
| Item | State |
|---|---|
| All 5 portal adapters | ✅ Built, and verified live: 1,059 notices fetched, cross-portal dedup worked |
| Keyword filter, dedup, state, health tracking | ✅ Built and unit-tested |
| Offline test suite | ✅ 28 tests pass (`python -m pytest -q`) |
| Dry-run digest HTML | ✅ Generated and checked |
| AI scoring | ✅ Verified live 2026-11-10: provider chain **Gemini → Cohere → unscored**. Gemini's free tier was overloaded (503/504, some calls took 5+ min), so per-call timeouts plus a 2-failure circuit breaker were added. Cohere `command-a-03-2025` then scored all 40 candidates; the full run took about 5 min. Keys go in `.env` locally (git-ignored) and in the `GEMINI_API_KEY` / `COHERE_API_KEY` secrets on GitHub. |
| Control panel (Google Sheet + Apps Script) | ⚠️ `apps_script/Code.gs` written, **never run in Google**. The Python client (`agent/control_panel.py`) is unit-tested against a fake endpoint. This is now the default way settings are read and email is sent; Gmail SMTP remains as an optional fallback. |
| GitHub Actions workflow | ⚠️ Written and YAML-validated, **never run on GitHub** |
| Repos | ⏳ Not pushed anywhere yet (see "Repo plan") |

## Your first tasks
1. `python -m venv .venv`, activate it, then `pip install -r requirements.txt` and `python -m pytest -q`. All 17 tests should pass.
2. `.env` is NOT in the zip (it holds keys). Copy `.env.example` to `.env` and ask the user for the keys. Then run `python -m agent.main --dry-run --state dist/x.json`.
   - **Cohere trial keys are for evaluation only, not commercial production use.** For the company deployment, recommend replacing Cohere with **GitHub Models**: free, OpenAI-compatible endpoint `https://models.github.ai/inference/chat/completions`, called with the workflow's own `GITHUB_TOKEN` (add `permissions: models: read`). It needs no extra account and is org-owned. Add it as a `Provider` subclass in `agent/scorer.py`.
3. **Control panel (most important open item).** Follow README step 3 with the user: create the sheet, paste `apps_script/Code.gs`, run `setup()`, deploy it as a web app. Put `APPS_SCRIPT_URL` / `APPS_SCRIPT_TOKEN` in `.env`. Then run `python -m agent.main --state dist/x.json` (a real send, with throwaway state). Check that the email reaches `nirjhara@buildnation.com.bd` and the rows appear in the Opportunities tab. Then edit a keyword or service in the sheet and confirm the next dry run picks it up.
   - Apps Script web apps answer POST with a 302; `requests` follows it with a GET, which is the expected pattern. If the response isn't JSON, the deployment is probably not set to *Anyone*.
   - Never edit `Code.gs` in the sheet only: keep the repo copy in sync.
4. Repo setup (below), then trigger the workflow manually on GitHub, once as a dry run and once for real.

## Repo plan (user's decision)
- **Portfolio**: the user's personal GitHub, public. It must not run the schedule. The workflow job has `if: github.event_name == 'workflow_dispatch' || vars.TENDER_WATCH_ENABLED == 'true'`, so with no variable and no secrets it stays idle.
- **Company**: the BuildNation GitHub org, private, created as an **independent copy (import or `git push --mirror`), not a fork**. A fork stays tied to the personal account, and the user may leave the company. Set the secrets `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO`, `GEMINI_API_KEY` and the variable `TENDER_WATCH_ENABLED=true` **only in the company repo**. Workflow permissions: Read and write.
- **Requirement**: nothing may depend on the user's personal accounts or devices. See `HANDOVER.md` for org ownership (≥2 owners, role mailbox, Google Group recipients, org-owned GCP project).
- Before making the portfolio public, check that no `.env`, keys or real email addresses are committed. `.gitignore` already excludes `.env`, `.venv/` and `dist/`.

## Architecture
```
agent/main.py        orchestrates: fetch → dedupe → keyword filter → detail fetch → Gemini → email → save state
agent/sources/*.py   one adapter per portal (Source subclass: fetch(since), fetch_detail(notice))
agent/sources/__init__.py  REGISTRY; ORDER MATTERS (UNDP before UNGM so the UNDP copy wins dedup)
agent/filters.py     include/exclude keyword matching (titles only)
agent/scorer.py      Gemini, batched 8 per call, 13 s spacing, JSON schema, fail-open
agent/notify.py      HTML/text digest (+ optional Gmail SMTP fallback)
agent/control_panel.py  Google Sheet web app client: settings (cached in data/settings_cache.json) + send
apps_script/Code.gs  the sheet's script: settings tabs, MailApp sending, Opportunities log, reviewer feedback
agent/state.py       data/seen.json: seen keys, UN refs, per-source fail streaks; 90-day prune
agent/http.py        PoliteSession: retries/backoff, timeout, 1 s delay, browser UA, extra-CA bundle
agent/dates.py       per-portal date parsing, Bangla digits, Asia/Dhaka
config/profile.yaml  company profile for the AI, keywords, thresholds, source toggles
tests/fixtures/      real saved responses from each portal (refresh when a portal changes)
.github/workflows/daily.yml  02:00 UTC daily; pytest → run → commit data/seen.json
```

## Portal facts discovered (don't re-learn these the hard way)
| Portal | Endpoint | Gotchas |
|---|---|---|
| UNGM | GET `/Public/Notice` for the `__RequestVerificationToken` and cookies, then POST JSON `/Public/Notice/Search` with header `RequestVerificationToken` | **PageSize must be 15** (any other value returns 400). It **returns 403 to any User-Agent containing a bot or library token**, so a plain Chrome UA is used. List titles are truncated; the full title comes from the detail page. |
| UNDP (Quantum) | GET `https://procurement-notices.undp.org/` (about 500 rows, one page) | The Quantum supplier portal itself needs a login; this public site mirrors it. Dates are in New York time, `dd-Mon-yy`. |
| e-GP | POST form `TenderDetailsServlet` with `funName=AllTenders`, `size=100`, `pageNo=N` | Returns `<tr>` fragments, newest first. The RSS feed is dead (404). The type column "ICT" means *International Competitive Tendering*, so keywords match **titles only**. "Works" tenders are excluded via `exclude_notice_types`. Detail page: GET `ViewTender.jsp?id=…&h=t`. |
| BRAC | GET `/tender/loadTenderExternalList?tenderState=liveTender&rows=500…` returns jqGrid JSON | **Detail pages redirect to login**, so `fetch_detail` returns "" and scoring uses the title. |
| SME Foundation | GET `https://smef.gov.bd/pages/notices` (10 latest) | **The server sends an incomplete TLS chain**, so `agent/certs/sectigo-dv-r36.pem` (public intermediate, valid to 2036) is appended to certifi. Never set `verify=False`. Dates use Bangla digits. Procurement notices are filtered by regex. Detail content lives in `.content-viewer-widget`. |

## Decisions to keep
- **Managers change scope in the Google Sheet, never in code.** The sheet overrides `config/profile.yaml`; YAML is only the fallback default. An emptied sheet column never wipes the defaults (`control_panel.merge`).
- **Reviewer verdicts in the Opportunities tab are fed back to the AI** as examples (`scorer.feedback_block`). This is how relevance adapts over time.
- **No mailbox passwords.** Email is sent by the sheet owner's Apps Script.
- **Stdlib `html.parser`, not lxml.** lxml and charset_normalizer DLLs failed to load on the user's Windows machine because of a deep path ("filename too long"). The `RequestsDependencyWarning` you may see locally comes from the same issue and is harmless.
- **Fail-open everywhere.** One portal failing never stops the others, and an AI failure never drops items. State is saved **only after the email is sent**, so a failed send is retried the next day.
- **Cross-portal dedup** only on UN-style references (`AGENCY-CCC-NNNN`). e-GP re-tenders reuse free-text references.
- **2-day lookback** plus dedup, so one missed run never loses notices.

## Possible next work (only if the user asks)
- WhatsApp (Meta Cloud API) or Telegram alerts: add a sender in `agent/notify.py` and use `build_text()` for the body.
- Tune `config/profile.yaml` once real Gemini scores come in.
- More portals: copy `brac.py` (JSON) or `smef.py` (HTML), register it, and add a fixture test.
