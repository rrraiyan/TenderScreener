from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from html import escape

from agent import dates
from agent.models import Notice


@dataclass
class SourceReport:
    name: str
    label: str
    ok: bool
    scanned: int = 0
    new: int = 0
    matched: int = 0
    error: str = ""
    fail_streak: int = 0


def _days_left(deadline: datetime | None) -> str:
    if not deadline:
        return ""
    days = (deadline - dates.now()).days
    return "closes today" if days <= 0 else f"{days} day{'s' if days != 1 else ''} left"


def _fmt(d: datetime | None) -> str:
    return d.astimezone(dates.DHAKA).strftime("%d %b %Y %H:%M") + " BDT" if d else "—"


def _card(n: Notice) -> str:
    score = (f'<span style="background:#0b6b3a;color:#fff;border-radius:4px;padding:1px 6px;font-weight:600">{n.score:g}/10</span>'
             if n.score is not None else
             '<span style="background:#777;color:#fff;border-radius:4px;padding:1px 6px">unscored</span>')
    cat = f" · {escape(n.fit_category)}" if n.fit_category else ""
    extra = "".join(f' · <a href="{escape(u)}">also here</a>' for u in n.also_on)
    reason = f'<div style="margin-top:4px;color:#333">{escape(n.reason)}</div>' if n.reason else ""
    hits = f'<div style="color:#888;font-size:12px">keywords: {escape(", ".join(n.keyword_hits))}</div>' if n.keyword_hits else ""
    return f"""
<tr><td style="padding:10px 0;border-bottom:1px solid #eee">
  <div>{score}{cat}</div>
  <div style="margin-top:4px;font-size:15px"><a href="{escape(n.url)}" style="color:#0645ad;text-decoration:none"><b>{escape(n.title)}</b></a></div>
  <div style="color:#555;font-size:13px">{escape(n.org)} · {escape(n.country)} · {escape(n.notice_type)}{' · Ref ' + escape(n.reference) if n.reference else ''}</div>
  <div style="color:#555;font-size:13px">Deadline: <b>{_fmt(n.deadline)}</b> {('(' + _days_left(n.deadline) + ')') if n.deadline else ''}{extra}</div>
  {reason}{hits}
</td></tr>"""


def build_html(matches: list[Notice], unscored: list[Notice], reports: list[SourceReport],
               labels: dict[str, str], run_at: datetime, scorer_note: str | None) -> str:
    sections = []
    for src, label in labels.items():
        items = sorted((n for n in matches if n.source == src), key=lambda n: (-(n.score or 0), n.deadline or run_at))
        if items:
            sections.append(f'<h3 style="margin:22px 0 4px">{escape(label)} ({len(items)})</h3><table width="100%">{"".join(map(_card, items))}</table>')
    if unscored:
        sections.append('<h3 style="margin:22px 0 4px">Keyword matches not scored by AI</h3>'
                        '<p style="color:#777;font-size:12px;margin:0">Review manually.</p>'
                        f'<table width="100%">{"".join(map(_card, unscored))}</table>')
    if not sections:
        sections.append('<p>No new relevant opportunities today. All checked portals are listed below.</p>')

    rows = []
    for r in reports:
        if r.ok:
            status = f'<span style="color:#0b6b3a">✔</span> {r.scanned} scanned · {r.new} new · {r.matched} matched'
        else:
            colour = "#b00020" if r.fail_streak >= 2 else "#c77700"
            status = f'<span style="color:{colour}">✖ failed{" " + str(r.fail_streak) + " runs in a row" if r.fail_streak >= 2 else ""}</span> — {escape(r.error[:200])}'
        rows.append(f'<tr><td style="padding:2px 12px 2px 0">{escape(r.label)}</td><td>{status}</td></tr>')
    note = f'<p style="color:#c77700;font-size:12px">AI scoring: {escape(scorer_note)}</p>' if scorer_note else ""

    return f"""<!doctype html><html><body style="font-family:Segoe UI,Arial,sans-serif;max-width:760px;margin:auto;color:#111">
<h2 style="margin-bottom:0">BuildNation Tender Watch</h2>
<div style="color:#777">{run_at.astimezone(dates.DHAKA).strftime('%A %d %B %Y, %H:%M')} (Dhaka)</div>
{''.join(sections)}
<h4 style="margin:28px 0 4px;color:#555">Portal health</h4>
<table style="font-size:13px;color:#333">{''.join(rows)}</table>{note}
<p style="color:#aaa;font-size:11px;margin-top:24px">Automated digest. To change what is searched for, edit the Tender Watch control panel (Google Sheet).</p>
</body></html>"""


def build_text(matches: list[Notice], unscored: list[Notice], reports: list[SourceReport]) -> str:
    lines = []
    for n in sorted(matches, key=lambda n: -(n.score or 0)) + unscored:
        score = f"{n.score:g}/10" if n.score is not None else "unscored"
        lines.append(f"[{score}] {n.title}\n  {n.org} | {n.country} | deadline {_fmt(n.deadline)}\n  {n.url}\n  {n.reason}\n")
    lines.append("Portal health:")
    lines += [f"  {r.label}: {'OK ' + str(r.scanned) + ' scanned' if r.ok else 'FAILED ' + r.error[:120]}" for r in reports]
    return "\n".join(lines)


def send_email(subject: str, html: str, text: str, recipients: list[str] | None = None) -> None:
    """Alternative to the control panel: Gmail / Workspace SMTP with an App Password.

    Env: GMAIL_USER, GMAIL_APP_PASSWORD, and EMAIL_TO (used when no recipients are given).
    """
    user = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
    to = recipients or [a.strip() for a in os.environ["EMAIL_TO"].split(",") if a.strip()]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"BuildNation Tender Watch <{user}>"
    msg["To"] = ", ".join(to)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)

# To add WhatsApp/Telegram later: write send_whatsapp(text) / send_telegram(text) here and
# call it from agent/main.py next to send_email(). build_text() already gives a plain-text body.
