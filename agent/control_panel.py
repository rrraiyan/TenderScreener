"""Google Sheet control panel (see apps_script/Code.gs).

The sheet's Apps Script web app gives the agent its settings and sends the digest from a
BuildNation Google account, so no mailbox password is stored anywhere. Env:
APPS_SCRIPT_URL (web app URL) and APPS_SCRIPT_TOKEN (secret printed by setup()).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests

log = logging.getLogger(__name__)

# Settings the sheet may override; anything else stays as in config/profile.yaml.
SHEET_KEYS = ("company_profile", "include_keywords", "exclude_keywords", "exclude_notice_types",
              "recipients", "min_score", "lookback_days", "send_when_empty", "sources", "feedback")


class ControlPanelError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("APPS_SCRIPT_URL") and os.environ.get("APPS_SCRIPT_TOKEN"))


def _call(action: str, **payload) -> dict:
    # Apps Script answers POST with a 302 to the result; requests follows it with a GET, which is what Google expects.
    resp = requests.post(os.environ["APPS_SCRIPT_URL"],
                         data=json.dumps({"action": action, "token": os.environ["APPS_SCRIPT_TOKEN"], **payload}),
                         headers={"Content-Type": "application/json"}, timeout=90)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        raise ControlPanelError(f"control panel did not return JSON (is the web app deployed for 'Anyone'?): {resp.text[:150]}")
    if not data.get("ok"):
        raise ControlPanelError(f"control panel refused '{action}': {data.get('error')}")
    return data


def merge(cfg: dict, sheet: dict) -> dict:
    """Overlay non-empty sheet values on the YAML defaults (an emptied sheet column never wipes the defaults)."""
    out = dict(cfg)
    for key in SHEET_KEYS:
        value = sheet.get(key)
        if value in (None, "", [], {}):
            continue
        out[key] = {**cfg.get(key, {}), **value} if key == "sources" else value
    return out


def load_settings(cfg: dict, cache: Path) -> tuple[dict, str | None]:
    """Return (settings, note). Falls back to the last good copy if the sheet cannot be reached."""
    if not configured():
        return cfg, None
    try:
        sheet = _call("settings")["settings"]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
        return merge(cfg, sheet), None
    except Exception as e:
        note = f"Control panel unreachable ({type(e).__name__}: {str(e)[:120]})"
        if cache.exists():
            log.warning("%s; using last saved settings", note)
            return merge(cfg, json.loads(cache.read_text(encoding="utf-8"))), note + "; used last saved settings"
        log.warning("%s; using config/profile.yaml", note)
        return cfg, note + "; used config/profile.yaml defaults"


def send(subject: str, html: str, text: str, matches: list[dict]) -> dict:
    """Email the digest to the sheet's recipients and log the matches in its Opportunities tab."""
    return _call("send", subject=subject, html=html, text=text, matches=matches)
