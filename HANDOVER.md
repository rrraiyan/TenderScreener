# Handover and ownership

This tool must keep running no matter who joins or leaves BuildNation. Nothing depends on a personal account, a personal device or anyone's hard drive. Keep this table up to date.

## What it depends on

| Piece | Where it lives | Owned by | Who can manage it |
|---|---|---|---|
| Code, schedule, run history | GitHub org `buildnation`, repo `tender-watch` (private) | BuildNation org, signed up with `it@…` | Org **Owners** (keep ≥ 2) |
| Memory of processed notices | `data/seen.json` in the repo (committed daily by the bot) | the repo | anyone with write access |
| Runtime | GitHub-hosted runners (free plan, about 90 of 2,000 min/month) | GitHub | — |
| **Control panel** (settings + sending + Opportunities log) | Google Sheet *Tender Watch – Control Panel* with its Apps Script, ideally in a Shared drive | the Google account that deployed the script | sheet editors change settings; only the owner can redeploy the script |
| Recipients | `recipients` row in the sheet's Settings tab (address list or a Google Group) | Workspace | sheet editors |
| AI key | Google Cloud project `buildnation-tender-watch` under the Workspace organisation | Workspace org | Project Owners (keep ≥ 2) |

Fill in the actual names when you set it up:

- GitHub org owners: `__________`, `__________`
- Control panel sheet (link): `__________` · script owner account: `__________`
- Recipients: `__________`
- Google Cloud project ID: `__________` · owners: `__________`, `__________`

## Secrets (GitHub → repo Settings → Secrets and variables → Actions)

| Secret | Comes from | How to rotate |
|---|---|---|
| `APPS_SCRIPT_URL` | the sheet's Apps Script → Deploy → Manage deployments → Web app URL | changes only if the script is redeployed as a *new* deployment |
| `APPS_SCRIPT_TOKEN` | printed by `setup()`; stored in Apps Script → Project settings → Script properties → `TOKEN` | edit the `TOKEN` script property, then update the secret |
| `COHERE_API_KEY` | dashboard.cohere.com/api-keys (fallback AI) | create a new key, update the secret, then delete the old one |
| `GEMINI_API_KEY` | aistudio.google.com/apikey, in the org project | create a new key, update the secret, then delete the old key |

No personal access tokens are used. The workflow commits with the built-in `GITHUB_TOKEN`.

## When someone leaves (checklist)
1. ☐ Confirm at least 2 *other* people are Owners of the GitHub org. Then remove the leaver from the org.
2. ☐ Confirm at least 2 *other* people are Owners of the Google Cloud project. Then remove the leaver.
3. ☐ If the leaver ever knew the app password or the Gemini key, rotate them (see the table above).
4. ☐ **If the leaver owns the control panel script**: transfer the sheet to another account (or a Shared drive). That account then reruns *Deploy → New deployment*, and you update `APPS_SCRIPT_URL`. Emails are sent as the script owner, so this matters.
5. ☐ Remove the leaver from the `recipients` row in Settings, if they are listed.
6. ☐ Trigger **Actions → Daily tender watch → Run workflow** once and confirm the email arrives.
7. ☐ Update the names in this file.

## When something breaks
See the *Maintenance* table in [README.md](README.md). Any developer can fix a portal adapter: each one is a single small file in `agent/sources/` with a matching saved page in `tests/fixtures/`.
