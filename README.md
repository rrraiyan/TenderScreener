# BuildNation Tender Watch

Every morning at about 08:00 (Dhaka time) this agent checks five tender portals. It finds new opportunities that fit BuildNation's edtech scope (LMS, training, consultancy, IT/AI/coding, leadership, vocational) and sends one email digest to the team.

| Portal | What it reads |
|---|---|
| **UNGM**: ungm.org | Public notices from all UN agencies |
| **UNDP (Quantum)**: procurement-notices.undp.org | The public copy of every UNDP Quantum negotiation |
| **Bangladesh e-GP**: eprocure.gov.bd | All live government e-tenders |
| **BRAC e-Tender**: tender.brac.net | Live BRAC tenders (Head Office and Cox's Bazar) |
| **SME Foundation**: smef.gov.bd | Procurement notices (RFQ / REOI / tender) |

The whole setup is free. It runs on GitHub Actions, free AI tiers (Gemini, with Cohere as fallback) and a Google Sheet in BuildNation's Google Workspace. Managers change what it looks for in that sheet, with no code. All accounts belong to the organisation, not to an individual (see [HANDOVER.md](HANDOVER.md)).

---

## How it works

```
GitHub Actions (daily cron, GitHub's servers — no office PC needed)
  │
  ├─ 1. Fetch      each portal adapter reads notices published in the last 2 days
  │                (one portal failing never stops the others)
  ├─ 2. Dedupe     skip anything processed before (data/seen.json in this repo);
  │                merge the same UNDP notice listed on both UNGM and UNDP
  ├─ 0. Settings   read services, keywords, recipients from the control panel (Google Sheet)
  ├─ 3. Keywords   cheap filter on titles: include/exclude lists from the sheet
  ├─ 4. Details    fetch the notice page for the shortlist only
  ├─ 5. AI score   rates fit 0-10 against the sheet's Services list + reviewers' past verdicts,
  │                checks "remote or in Bangladesh", writes a one-line reason
  │                (Gemini → Cohere fallback → "unscored": nothing is ever lost)
  ├─ 6. Email      sent by the sheet's Apps Script; matches also logged in its Opportunities tab
  └─ 7. Remember   commit data/seen.json so tomorrow only new notices are reported
```

A typical day: about 1,000 notices scanned, about 50 keyword candidates, 7 AI calls, and 5–15 matches emailed.

---

## Setup, step by step (about 45 minutes, once)

Use **organisation role accounts** for everything below, not personal ones. This is what lets the tool keep running after any one person leaves.

### Step 1: Create the BuildNation GitHub organisation (free)
1. Sign up at https://github.com/signup using a role address such as `it@<your-domain>` or `admin@<your-domain>`. Store the password in the organisation's password manager.
2. Go to **Profile picture → Your organizations → New organization → Free**. Name it, e.g. `buildnation`.
3. **People → Invite member**: invite a second person (a director or IT lead) and set their role to **Owner**. Always keep at least 2 owners.
4. **Settings → Authentication security**: tick **Require two-factor authentication**.

### Step 2: Put the code in a private repository
1. In the organisation: **Repositories → New**, name it `tender-watch`, choose **Private**, and create it.
2. Upload this folder. The easiest way is Git:
   ```bash
   git init && git add . && git commit -m "Tender watch" && git branch -M main
   git remote add origin https://github.com/buildnation/tender-watch.git && git push -u origin main
   ```
   Or use **Add file → Upload files** in the browser. Include the hidden `.github` folder.
3. **Settings → Actions → General → Workflow permissions**: choose **Read and write permissions** and save. The job needs this to save its memory file.

#### Two copies of the repo: portfolio and company
The code lives in two places:
- **Portfolio (public, personal GitHub)**: a showcase only. It has no secrets and no `TENDER_WATCH_ENABLED` variable, so the schedule never runs there.
- **Company (private, BuildNation org)**: the copy that actually runs. Make it an **independent copy, not a fork**. A fork stays linked to the personal repo, can't be made private, and follows the original if it is deleted. To create the copy, either use **Import repository** (github.com/new/import) with the portfolio URL, or mirror-push:
  ```bash
  git clone --bare https://github.com/<you>/buildnation-tender-watch.git
  cd buildnation-tender-watch.git && git push --mirror https://github.com/buildnation/tender-watch.git
  ```
  After that, the company repo is the source of truth. Pull later improvements from the portfolio by hand, if you want them at all.

### Step 3: Create the control panel (a Google Sheet that also sends the email)
This one sheet replaces both the mailbox password and code edits. Managers change what the agent looks for here, and it sends the digest from the Google account that owns the sheet.

1. **Choose the owner account.** Signed in as a BuildNation account that will stay, e.g. the manager (`nirjhara@buildnation.com.bd`) or a role account, create a new Google Sheet named **Tender Watch – Control Panel**. Ideally put it in a **Shared drive**, so it survives anyone leaving.
2. In the sheet: **Extensions → Apps Script**. Delete the sample code, paste in the whole of [apps_script/Code.gs](apps_script/Code.gs) and click **Save**.
3. Choose the function **`setup`** in the toolbar and click **Run**. Approve the permissions Google asks for (read/write this sheet, send email as you). It creates the tabs and pre-fills them with BuildNation's services and keywords. The **secret token** it shows (also under *Execution log*) is needed in step 5.
4. **Deploy → New deployment → ⚙ → Web app**. Set *Execute as*: **Me** and *Who has access*: **Anyone**, then click **Deploy** and copy the **Web app URL**. "Anyone" only means the URL can be called; every request must carry the secret token, and the sheet itself stays private.
   - If "Anyone" is not offered, a Workspace admin has restricted it. In Admin console → *Apps → Google Workspace → Drive and Docs → Sharing settings*, sharing outside the organisation must be allowed.
5. Recipients are set in the **Settings** tab (pre-filled with `nirjhara@buildnation.com.bd`). Add more addresses separated by commas, or a Google Group address.

The emails come **from the owner account**, so nobody shares a password. Workspace allows about 1,500 recipients a day, and this uses one email a day.

> **Alternative (not needed if you use the sheet):** send through Gmail SMTP with a dedicated mailbox's App Password. Set `GMAIL_USER`, `GMAIL_APP_PASSWORD` and `EMAIL_TO`, and leave `APPS_SCRIPT_URL` empty.

### Step 4: Get the AI keys (free)
The agent tries **Gemini** first and falls back to **Cohere** when Gemini is overloaded. Either one alone is enough; both make it more reliable.
1. **Gemini**: signed in as a BuildNation account, open https://aistudio.google.com/apikey → **Create API key** in a Google Cloud project that sits under the BuildNation organisation (not a personal Gmail project). Add a second org admin as Owner of that project.
2. **Cohere** (fallback): https://dashboard.cohere.com/api-keys. Cohere's free *trial* keys are meant for evaluation, not commercial production use. For long-term use, upgrade the key, or replace Cohere with another provider (see AGENT_HANDOVER.md).

> On free tiers, providers may use prompts to improve their products. That is acceptable here because the prompts contain only public tender text and BuildNation's public service list.

### Step 5: Add the secrets to the repository
In the company repo: **Settings → Secrets and variables → Actions → New repository secret**. Add:

| Name | Value |
|---|---|
| `APPS_SCRIPT_URL` | the Web app URL from step 3 |
| `APPS_SCRIPT_TOKEN` | the secret token from step 3 |
| `GEMINI_API_KEY` | from step 4 |
| `COHERE_API_KEY` | from step 4 |

Then open the **Variables** tab and add `TENDER_WATCH_ENABLED` = `true`. Without this variable the daily schedule stays off, which is how the public portfolio copy stays idle.

Optional variables: `GEMINI_MODEL` (default `gemini-flash-latest`) and `COHERE_MODEL` (default `command-a-03-2025`).

### Step 6: Decide what counts as relevant (no code)
Everything is in the control panel sheet and applies from the next morning's run:

| Tab | What to change |
|---|---|
| **Services** | What BuildNation offers or wants to grow into. Add a row, describe it, and tick **Active**; untick a service to stop looking for it. The AI judges every notice against this list. |
| **Keywords** | **Include**: a title must contain one of these to be considered. **Exclude**: titles containing these are dropped. Add words in English or Bangla. When you add a new service, add 2–3 words for it here too. |
| **Settings** | Recipients, `min_score` (raise to 7–8 for fewer, stronger leads), the portals to check, and the company intro and delivery area. |
| **Opportunities** | Every match is logged here. Set **Your verdict** to *Relevant* or *Not relevant* and add a short note if useful. The 30 most recent verdicts are shown to the AI as examples, so it learns BuildNation's taste over time. |

If the sheet can't be reached on some day, the agent uses the last settings it saved, and the email footer says so.

### Step 7: First run
**Actions → Daily tender watch → Run workflow**.
- Tick *Dry run* first. The log should show each portal's count, and no email is sent.
- Then run it again without *Dry run*. The first real digest arrives within a few minutes, and the matches appear in the **Opportunities** tab. It is larger than usual because nothing has been seen yet.

After that it runs by itself every day. GitHub emails the org owners if a run ever fails.

### Running on a computer (optional, for testing changes)
```bash
python -m venv .venv
.venv/Scripts/activate        # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env          # fill in values; .env is git-ignored
python -m pytest -q
python -m agent.main --dry-run                 # all portals, writes dist/digest.html, sends nothing
python -m agent.main --dry-run --source egp    # one portal
```

---

## Reading the email
- **Score badge (0–10)**: the AI's judgement of fit. **Unscored** means the AI was unavailable, so review those by hand.
- **"also here"**: the same notice on another portal, or the notice's attachment.
- **Portal health** (bottom): every portal with its count. A ✖ means that portal could not be read today; red means it has failed 2 or more runs in a row. The subject line also shows ⚠ when a portal fails.
- A day with no matches still sends a short email (`send_when_empty: true`), so a quiet inbox never hides a broken job.

## Maintenance
| Symptom | What to do |
|---|---|
| One portal shows ✖ for a day | Usually the portal being down. Nothing to do; the 2-day lookback catches up the missed day. |
| A portal is red (2+ failures) | The portal probably changed its page layout. Open `agent/sources/<portal>.py`, compare it with the live page, save a fresh response into `tests/fixtures/`, fix the selectors, and run `pytest`. |
| Email stopped arriving | Check *Actions* for a red run. "bad token" means `APPS_SCRIPT_TOKEN` is wrong. "did not return JSON" means the web app was not deployed for *Anyone*, or the owner account was removed: redeploy from a current account and update `APPS_SCRIPT_URL`. |
| Too many or too few leads | In the control panel, change `min_score` (Settings tab) and the Keywords tab, and mark results in Opportunities. |
| Changed the sheet but nothing changed | Changes apply from the next run. The tab names and the first column of Settings must stay as created. |
| AI errors in the footer | Usually Gemini being overloaded; Cohere takes over automatically. If both fail daily, check the keys. If a model was retired, set the `GEMINI_MODEL` / `COHERE_MODEL` variable. |
| SME Foundation TLS error after 2036 | `agent/certs/` holds a public intermediate certificate that smef.gov.bd does not send itself. Replace it with the current one from the issuing CA. |

**Adding another portal:** copy `agent/sources/brac.py` (JSON API) or `agent/sources/smef.py` (HTML table), adapt the parsing, register it in `agent/sources/__init__.py`, add it under `sources:` in `config/profile.yaml` and as a `portal_<name>` row in the sheet's Settings tab, and add a fixture test.

**Adding WhatsApp or Telegram later:** `agent/notify.py` already builds a plain-text body (`build_text`). Add a `send_whatsapp()` (Meta WhatsApp Cloud API) or `send_telegram()` (Telegram Bot API, free) next to `send_email()`, call it from `agent/main.py`, and put its token in a repository secret.

## Notes on fair use
- The agent only reads **public** listing pages, once a day, with retries, back-off and a delay between requests (under 100 requests per run in total). UNGM's robots.txt allows `/Public/Notice`.
- UNGM rejects requests that identify as scripts, so the agent sends a standard browser User-Agent.
- BRAC tender detail pages need a supplier login. The digest links to them, and BuildNation's BRAC supplier account opens them.
