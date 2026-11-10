"""Daily run: fetch every portal, keep new relevant notices, email a digest.

    python -m agent.main                 # full run (sends email, saves state)
    python -m agent.main --dry-run       # print digest to dist/digest.html, send nothing, save nothing
    python -m agent.main --dry-run --source egp --since 3
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

import yaml

from agent import control_panel, dates
from agent.filters import KeywordFilter
from agent.models import Notice
from agent.notify import SourceReport, build_html, build_text, send_email
from agent.scorer import Scorer
from agent.sources import REGISTRY
from agent.state import State

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("tenderwatch")


def load_env(path: Path) -> None:
    """Minimal .env loader for local runs; real secrets come from GitHub Actions."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def collect(cfg: dict, only: str | None, since, state: State, today) -> tuple[list[Notice], list[SourceReport], dict]:
    notices, reports, instances = [], [], {}
    for name, cls in REGISTRY.items():
        if (only and name != only) or (not only and not cfg["sources"].get(name, True)):
            continue
        src = cls()
        instances[name] = src
        try:
            got = src.fetch(since)
            streak = state.record_health(name, True, today)
            reports.append(SourceReport(name, src.label, True, scanned=src.scanned, new=0, fail_streak=streak))
            notices += got
            log.info("%s: %d scanned, %d in window", name, src.scanned, len(got))
        except Exception as e:  # one broken portal must never stop the others
            msg = f"{type(e).__name__}: {e}"
            streak = state.record_health(name, False, today, msg[:300])
            reports.append(SourceReport(name, src.label, False, error=msg, fail_streak=streak))
            log.error("%s failed: %s", name, msg)
    return notices, reports, instances


def dedupe(notices: list[Notice], state: State) -> list[Notice]:
    """Drop notices processed on earlier runs; merge the same UN notice seen on two portals."""
    fresh, by_ref = [], {}
    for n in notices:
        if state.is_seen(n.key, n.norm_ref):
            continue
        ref = n.norm_ref
        if ref and ref in by_ref:
            by_ref[ref].also_on.append(n.url)
            continue
        if ref:
            by_ref[ref] = n
        fresh.append(n)
    return fresh


def log_row(n: Notice, labels: dict) -> dict:
    """One row for the control panel's Opportunities tab."""
    return {"key": n.key, "score": n.score, "title": n.title, "org": n.org, "country": n.country,
            "deadline": n.deadline.astimezone(dates.DHAKA).strftime("%Y-%m-%d %H:%M") if n.deadline else "",
            "url": n.url, "reason": n.reason, "portal": labels.get(n.source, n.source)}


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="do not send email or save state")
    ap.add_argument("--save-state", action="store_true", help="with --dry-run: still save state")
    ap.add_argument("--source", choices=sorted(REGISTRY), help="run a single portal")
    ap.add_argument("--since", type=int, help="look back N days (default from config)")
    ap.add_argument("--config", default=str(ROOT / "config" / "profile.yaml"))
    ap.add_argument("--state", default=str(ROOT / "data" / "seen.json"))
    ap.add_argument("--once-per-day", action="store_true",
                    help="scheduled runs: do nothing if a scheduled run already succeeded today (Dhaka date)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_env(ROOT / ".env")
    state = State(Path(args.state))
    run_at = dates.now()
    today = run_at.astimezone(dates.DHAKA).date()
    if args.once_per_day and state.last_scheduled == today.isoformat():
        log.info("a scheduled run already succeeded today (%s); nothing to do", today)
        return 0
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    cfg, panel_note = control_panel.load_settings(cfg, ROOT / "data" / "settings_cache.json")
    since = run_at - timedelta(days=args.since or cfg.get("lookback_days", 2))

    notices, reports, sources = collect(cfg, args.source, since, state, today)
    fresh = dedupe(notices, state)
    kw = KeywordFilter(cfg["include_keywords"], cfg["exclude_keywords"], cfg.get("exclude_notice_types"))
    candidates = kw.apply(fresh)
    log.info("%d fetched, %d new, %d keyword candidates", len(notices), len(fresh), len(candidates))

    for n in candidates:
        try:
            n.detail_text = sources[n.source].fetch_detail(n)
        except Exception as e:
            log.warning("detail fetch failed for %s: %s", n.key, e)

    scorer = Scorer(cfg["company_profile"], feedback=cfg.get("feedback"))
    scorer.score(candidates, max_items=cfg.get("max_ai_items", 120))
    min_score = cfg.get("min_score", 6)
    matches = [n for n in candidates if n.score is not None and n.score >= min_score and n.deliverable is not False]
    unscored = [n for n in candidates if n.score is None]

    for r in reports:
        r.new = sum(1 for n in fresh if n.source == r.name)
        r.matched = sum(1 for n in matches + unscored if n.source == r.name)

    labels = {name: sources[name].label for name in sources}
    subject = (f"[Tender Watch] {len(matches)} new match{'es' if len(matches) != 1 else ''}"
               f"{f' + {len(unscored)} to review' if unscored else ''} · {today:%d %b %Y}")
    failed = [r for r in reports if not r.ok]
    if failed:
        subject += f" · ⚠ {len(failed)} portal{'s' if len(failed) > 1 else ''} failed"
    note = "; ".join(filter(None, [panel_note, scorer.error])) or None
    html = build_html(matches, unscored, reports, labels, run_at, note)
    text = build_text(matches, unscored, reports)

    should_send = bool(matches or unscored or failed or cfg.get("send_when_empty", True))
    if args.dry_run:
        out = ROOT / "dist" / "digest.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(subject)
        print(text)
        print(f"\nHTML preview written to {out}")
    elif should_send:
        # both raise on failure, so state is not saved and tomorrow's run retries
        if control_panel.configured():
            result = control_panel.send(subject, html, text, [log_row(n, labels) for n in matches + unscored])
            log.info("email sent via control panel: %s (%s)", subject, result)
        else:
            send_email(subject, html, text, cfg.get("recipients"))
            log.info("email sent via SMTP: %s", subject)

    all_failed = bool(reports) and all(not r.ok for r in reports)
    if not args.dry_run or args.save_state:
        for n in fresh:
            state.mark(n.key, n.norm_ref, today)
        state.prune(today)
        if args.once_per_day and not args.dry_run and not all_failed:
            state.last_scheduled = today.isoformat()   # later backup slots today will skip
        state.save()

    if all_failed:
        log.error("every portal failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
