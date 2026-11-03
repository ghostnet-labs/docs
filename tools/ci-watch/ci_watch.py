#!/usr/bin/env python3
"""Watch every ghostnet-labs repo for CI and PR problems and alert, with no Claude in the loop.

One file, Python 3 standard library only. Read-only on GitHub: it never
cancels, re-runs, pushes, merges or deletes anything. It replaces the cloud
"PR check watch" loop, the hourly "CI runner watchdog" and the read-only part
of the two-hourly "Stale-state sweep" (see README.md for the full list).

Each run (every 10 minutes from a LaunchAgent on the Mac Studio):

  1. Actions guard (actions_guard.py in tools/stale-runs): Actions off, a
     disabled workflow, a ready PR with no checks after 20 minutes, no new
     workflow run in 3 hours while PRs are open.
  2. Every open PR: check state on its current head (green, red, running,
     none), merge state (clean, behind, dirty, blocked), auto-merge, labels.
     Compared with the last run, it alerts on: a PR merged or closed, a PR
     opened, a head that turns red, a conflict, a PR behind its base with
     auto-merge on, checks running longer than --stuck-hours, a ready PR not
     touched for --idle-hours, and a red PR that recovers.
  3. Runner page alerts (optional, --runner-page): offline runners, jobs
     queued 20+ minutes, hosted stalls, minutes, disks. The page already
     detects these; this forwards them to the same alert channels.
  4. Once an hour: branches fully merged into the default branch that no open
     PR uses (listed only; deleting needs Justin's typed line).

A finding alerts once, when it first appears, and once more when it clears.
If GitHub cannot be read three runs in a row, that is an alert too.

Alert channels, any combination:

  --notify          macOS banner on this Mac
  --ntfy TOPIC      push to the ntfy phone app (https://ntfy.sh/TOPIC)
  --issue N         ghostnet-labs/setup issue N (Issues are off in the forks;
                    --issue-repo picks another repo): its body is kept as the live
                    report (a heartbeat: "Updated" changes every run) and each
                    new alert is added as a comment

The live report is also written to ~/.local/state/ci-watch/report.md.

  python3 ci_watch.py                     # one run, prints the report
  python3 ci_watch.py --notify --ntfy manet-ci-x7k2
  python3 ci_watch.py report              # print the last report, no API calls
  python3 ci_watch.py launchd --notify --runner-page http://localhost:8090
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stale-runs"))
import actions_guard as ag  # noqa: E402
import stale_runs as sr  # noqa: E402

ORG = sr.ORG
REPOS = sr.REPOS
STATE_DIR = os.path.expanduser("~/.local/state/ci-watch")
ETAG_FILE = os.path.expanduser("~/.cache/ci-watch/etags.json")
TOKEN_FILE = os.path.expanduser("~/.config/ci-watch/token")
ISSUE_TOKEN_FILE = os.path.expanduser("~/.config/ci-watch/issue-token")
LOG_FILE = os.path.expanduser("~/Library/Logs/ci-watch.log")
LABEL = "com.ghostnet.ci-watch"
INTERVAL_SECONDS = 600
HOLD_LABELS = {"hold", "do-not-merge", "blocked"}
BAD_CONCLUSIONS = {"failure", "timed_out", "action_required", "startup_failure"}
SWEEP = "Handle passing PRs"
LEVELS = {"info": 0, "warn": 1, "crit": 2}
ERROR_RUNS_ALERT = 3  # consecutive runs that could not read GitHub before alerting
MAX_COMPARES = 60  # branch comparisons per hourly scan
MAX_TEXT = 3500  # ntfy and banner bodies are cut here
DIGITS = re.compile(r"\d+")
UPDATED_LINE = re.compile(r"^Updated .*$", re.MULTILINE)
DEPENDS = re.compile(r"(?im)^Depends-on:\s*(https://github\.com/\S+/pull/\d+)\s*$")

sr.ETAG_MAX = 1500  # one cached answer per PR, head and branch; quiet runs are all 304s


def ts(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%MZ")


def minutes(delta: timedelta) -> str:
    total = int(delta.total_seconds() // 60)
    return f"{total}m" if total < 120 else f"{total / 60:.1f}h"


# ---------------------------------------------------------------- PR state


def summarize_checks(check_runs: list[dict], statuses: list[dict], now: datetime) -> dict:
    """Collapse a head commit's check runs and commit statuses into one state.

    Only the newest run of each check name counts, so a re-run that passed
    replaces the failure before it.
    """
    latest: dict[str, dict] = {}
    for run in check_runs:
        name = run.get("name") or "?"
        if name not in latest or (run.get("id") or 0) > (latest[name].get("id") or 0):
            latest[name] = run
    red, running, cancelled = [], [], []
    oldest_start = None
    for name, run in sorted(latest.items()):
        if run.get("status") != "completed":
            running.append(name)
            started = sr.parse_ts(run.get("started_at"))
            if started and (oldest_start is None or started < oldest_start):
                oldest_start = started
        elif run.get("conclusion") == "cancelled":
            cancelled.append(name)
        elif run.get("conclusion") in BAD_CONCLUSIONS:
            red.append(name if run.get("conclusion") == "failure" else f"{name} ({run['conclusion']})")
    for status in statuses:
        context = status.get("context") or "?"
        if status.get("state") in ("failure", "error"):
            red.append(context)
        elif status.get("state") == "pending":
            running.append(context)
    total = len(latest) + len(statuses)
    if red:
        state = "red"
    elif running:
        state = "running"
    elif cancelled:
        state = "cancelled"  # usually replaced by a newer run, but the gate does not count it as a pass
    elif total:
        state = "green"
    else:
        state = "none"
    running_for = (now - oldest_start) if oldest_start else None
    return {"state": state, "red": red, "running": running, "cancelled": cancelled, "total": total,
            "running_minutes": int(running_for.total_seconds() // 60) if running_for else 0}


def pr_status(pr: dict) -> tuple[str, str, str]:
    """(category, plain-words state, next step) for one PR row."""
    labels = set(pr["labels"])
    checks = pr["checks"]
    merge = pr.get("mergeable_state") or "unknown"
    if pr["draft"]:
        return "draft", "draft", "finish and mark ready"
    held = sorted(labels & HOLD_LABELS)
    if held:
        return "held", f"held ({', '.join(held)})", "waiting on the hold reason"
    if checks["state"] == "red":
        return "red", "red: " + ", ".join(checks["red"][:3]), "fix the failing check"
    if merge == "dirty":
        return "conflict", "merge conflict", "merge the base branch and resolve"
    if checks["state"] == "running":
        names = ", ".join(checks["running"][:2])
        return "running", f"running {checks['running_minutes']}m: {names}", "wait for checks"
    if checks["state"] == "cancelled":
        names = checks.get("cancelled", [])
        hint = f"re-run the latest '{SWEEP}' run in this repo" if SWEEP in names else "re-run the cancelled check"
        return "cancelled", "cancelled: " + ", ".join(names[:3]), hint
    if checks["state"] == "none":
        return "none", "no checks on head", "check Actions is on for this repo"
    if merge == "behind":
        if pr["auto_merge"]:
            return "behind", "green, behind base", "update the branch (auto-merge never does)"
        return "behind", "green, behind base", "update the branch, then enable auto-merge"
    if pr["depends_on"]:
        return "waiting", "green, waiting on Depends-on", "land " + pr["depends_on"][0]
    if merge == "blocked":
        return "blocked", "green, blocked by review or rules", "check reviews and conversations"
    if pr["auto_merge"]:
        return "green", "green, auto-merge on", "merges on its own"
    return "green", "green", "merge sweep should land it"


def collect_prs(gh, repo: str, now: datetime) -> list[dict]:
    full = f"/repos/{ORG}/{repo}"
    rows = []
    for pull in gh.get(f"{full}/pulls?state=open&per_page=100"):
        number = pull["number"]
        sha = pull["head"]["sha"]
        detail = gh.get(f"{full}/pulls/{number}")
        runs = gh.get(f"{full}/commits/{sha}/check-runs?per_page=100").get("check_runs", [])
        statuses = gh.get(f"{full}/commits/{sha}/status").get("statuses", [])
        row = {
            "repo": repo, "number": number, "title": pull.get("title", ""),
            "url": pull.get("html_url") or f"https://github.com/{ORG}/{repo}/pull/{number}",
            "author": (pull.get("user") or {}).get("login", ""),
            "draft": bool(pull.get("draft")), "sha": sha, "head_ref": pull["head"].get("ref", ""),
            "labels": [lb.get("name", "") for lb in pull.get("labels") or []],
            "auto_merge": bool(pull.get("auto_merge") or detail.get("auto_merge")),
            "mergeable_state": detail.get("mergeable_state"),
            "updated_at": pull.get("updated_at"),
            "depends_on": DEPENDS.findall(pull.get("body") or ""),
            "checks": summarize_checks(runs, statuses, now),
        }
        row["category"], row["status"], row["next"] = pr_status(row)
        rows.append(row)
    return rows


def pr_findings(prs: list[dict], now: datetime, stuck: timedelta, idle: timedelta) -> dict[str, dict]:
    """Ongoing problems, keyed so the same problem keeps the same key across runs."""
    found: dict[str, dict] = {}
    for pr in prs:
        ref = f"{ORG}/{pr['repo']} #{pr['number']}"
        base = {"url": pr["url"], "repo": pr["repo"]}
        cat = pr["category"]
        if cat == "red":
            found[f"red:{pr['repo']}#{pr['number']}:{pr['sha']}"] = {
                **base, "level": "crit", "text": f"{ref} is red: {', '.join(pr['checks']['red'][:3])}"}
        elif cat == "cancelled":
            found[f"cancelled:{pr['repo']}#{pr['number']}:{pr['sha']}"] = {
                **base, "level": "warn", "text": f"{ref} has a cancelled check ({pr['status']}); {pr['next']}"}
        elif cat == "conflict":
            found[f"conflict:{pr['repo']}#{pr['number']}"] = {
                **base, "level": "warn", "text": f"{ref} has a merge conflict"}
        elif cat == "behind" and pr["auto_merge"]:
            found[f"behind:{pr['repo']}#{pr['number']}:{pr['sha']}"] = {
                **base, "level": "warn",
                "text": f"{ref} is green with auto-merge on but behind its base; update the branch"}
        if cat == "running" and pr["checks"]["running_minutes"] >= stuck.total_seconds() / 60:
            found[f"stuck:{pr['repo']}#{pr['number']}:{pr['sha']}"] = {
                **base, "level": "warn",
                "text": f"{ref} checks running {minutes(timedelta(minutes=pr['checks']['running_minutes']))}: "
                        + ", ".join(pr["checks"]["running"][:2])}
        updated = sr.parse_ts(pr.get("updated_at"))
        if cat not in ("draft", "held") and updated and now - updated >= idle:
            found[f"idle:{pr['repo']}#{pr['number']}:{pr['updated_at']}"] = {
                **base, "level": "warn", "text": f"{ref} untouched for {minutes(now - updated)} ({pr['status']})"}
    return found


def pr_events(gh, previous: dict[str, dict], prs: list[dict], scanned: set[str],
              first_run: bool = False) -> list[dict]:
    """One-off news since the last run: opened, merged, closed, recovered."""
    events = []
    current = {f"{p['repo']}#{p['number']}": p for p in prs}
    for key, pr in current.items():
        old = previous.get(key)
        ref = f"{ORG}/{pr['repo']} #{pr['number']}"
        if old is None:
            if not first_run:  # first run ever: no flood of "opened"
                events.append({"level": "info", "url": pr["url"], "text": f"{ref} opened: {pr['title']}"})
        elif old.get("category") == "red" and pr["category"] != "red":
            events.append({"level": "info", "url": pr["url"], "text": f"{ref} is no longer red ({pr['status']})"})
    for key, old in previous.items():
        if key in current or old.get("repo") not in scanned:
            continue
        repo, number = old["repo"], old["number"]
        ref = f"{ORG}/{repo} #{number}"
        try:
            detail = gh.get(f"/repos/{ORG}/{repo}/pulls/{number}")
        except RuntimeError:
            continue
        if detail.get("merged_at"):
            events.append({"level": "info", "url": old["url"], "text": f"{ref} merged: {old.get('title', '')}"})
        elif detail.get("state") == "closed":
            events.append({"level": "info", "url": old["url"], "text": f"{ref} closed without merging"})
    return events


# ---------------------------------------------------------------- other sources


def guard_findings(gh, repo: str, now: datetime) -> dict[str, dict]:
    found = {}
    for f in ag.check_repo(gh, repo, now, timedelta(minutes=20), timedelta(hours=3)):
        detail = DIGITS.sub("#", f["detail"]) if f["kind"] == "runs-stale" else f["detail"]
        url = f"https://github.com/{ORG}/{repo}/actions"
        if f.get("pr"):
            url = f"https://github.com/{ORG}/{repo}/pull/{f['pr']}"
        found[f"guard:{repo}:{f['kind']}:{detail}"] = {
            "level": "crit", "repo": repo, "url": url, "text": f"{ORG}/{repo} {f['kind']}: {f['detail']}"}
    return found


def runner_findings(page: str, fetch=None) -> dict[str, dict]:
    """warn/crit alerts from the runner status page's /api/state (no token)."""
    url = page.rstrip("/") + "/api/state"
    if fetch is None:
        def fetch(u):
            with urllib.request.urlopen(u, timeout=15) as resp:
                return json.loads(resp.read())
    try:
        state = fetch(url)
    except (OSError, ValueError) as err:
        return {"runner-page:down": {"level": "warn", "url": page,
                                     "text": f"runner status page unreachable: {err}"}}
    found = {}
    for alert in state.get("alerts", []):
        if alert.get("level") not in ("warn", "crit"):
            continue
        text = alert.get("text", "")
        found["runner:" + DIGITS.sub("#", text)] = {
            "level": alert["level"], "url": alert.get("url") or page, "text": "runner: " + text}
    return found


def merged_branches(gh, repo: str, open_heads: set[str]) -> list[dict]:
    """Branches whose tip is already in the default branch and that no open PR uses."""
    full = f"/repos/{ORG}/{repo}"
    default = gh.get(full).get("default_branch", "main")
    out, compares = [], 0
    for br in gh.get(f"{full}/branches?per_page=100"):
        name = br.get("name", "")
        if name == default or name in open_heads or br.get("protected"):
            continue
        if compares >= MAX_COMPARES:
            break
        compares += 1
        quoted = urllib.parse.quote(f"{default}...{name}", safe=".")
        cmp = gh.get(f"{full}/compare/{quoted}")
        if cmp.get("ahead_by") == 0:
            out.append({"repo": repo, "branch": name,
                        "url": f"https://github.com/{ORG}/{repo}/tree/{name}"})
    return out


# ---------------------------------------------------------------- report


def render_report(now: datetime, prs: list[dict], active: dict[str, dict], branches: list[dict],
                  branches_at: str | None, errors: list[str]) -> str:
    lines = ["# CI watch", "", f"Updated {ts(now)} by `tools/ci-watch/ci_watch.py` (every 10 minutes).", ""]
    problems = sorted(active.values(), key=lambda a: (-LEVELS[a["level"]], a["text"]))
    lines.append("## Problems")
    lines.append("")
    if not problems:
        lines.append("None.")
    for a in problems:
        lines.append(f"- **{a['level'].upper()}** [{a['text']}]({a['url']})")
    if errors:
        lines += ["", "Could not read: " + "; ".join(errors)]
    lines += ["", "## Open PRs", ""]
    if not prs:
        lines.append("No open PRs.")
    else:
        lines.append("| PR | State | Next step | Auto-merge |")
        lines.append("|---|---|---|---|")
        order = {"red": 0, "conflict": 1, "none": 2, "cancelled": 3, "behind": 3, "running": 4, "blocked": 5,
                 "waiting": 6, "green": 7, "held": 8, "draft": 9}
        for pr in sorted(prs, key=lambda p: (order.get(p["category"], 5), p["repo"], p["number"])):
            title = pr["title"].replace("|", "/")[:60]
            lines.append(f"| [{ORG}/{pr['repo']} #{pr['number']}]({pr['url']}) {title} | {pr['status']} "
                         f"| {pr['next']} | {'on' if pr['auto_merge'] else 'off'} |")
    lines += ["", "## Merged branches with no open PR", ""]
    if branches_at is None:
        lines.append("Not scanned yet.")
    elif not branches:
        lines.append(f"None (scanned {branches_at}).")
    else:
        lines.append(f"Scanned {branches_at}. Listed only; deleting needs Justin's typed line.")
        lines.append("")
        lines += [f"- [{ORG}/{b['repo']} {b['branch']}]({b['url']})" for b in branches]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- alert channels


def alert_text(new: list[dict], cleared: list[dict], events: list[dict]) -> str:
    lines = [a["text"] for a in sorted(new, key=lambda a: -LEVELS[a["level"]])]
    lines += [e["text"] for e in events]
    lines += ["cleared: " + c["text"] for c in cleared]
    return "\n".join(lines)


def notify_macos(title: str, text: str, run=subprocess.run) -> None:
    if platform.system() != "Darwin":
        return
    first = text.splitlines()
    body = first[0] if len(first) == 1 else f"{first[0]} (+{len(first) - 1} more)"
    script = f"display notification {json.dumps(body[:240])} with title {json.dumps(title)}"
    run(["/usr/bin/osascript", "-e", script], check=False, capture_output=True, timeout=10)


def notify_ntfy(server: str, topic: str, title: str, text: str, level: str, url: str | None,
                opener=urllib.request.urlopen) -> None:
    priority = {"crit": "high", "warn": "default", "info": "low"}[level]
    tags = {"crit": "rotating_light", "warn": "warning", "info": "white_check_mark"}[level]
    headers = {"Title": title, "Priority": priority, "Tags": tags}
    if url:
        headers["Click"] = url
    req = urllib.request.Request(f"{server.rstrip('/')}/{topic}", data=text[:MAX_TEXT].encode(),
                                 headers=headers, method="POST")
    with opener(req, timeout=15):
        pass


class IssueSink:
    """Keeps a GitHub issue's body as the live report and comments new alerts."""

    def __init__(self, token: str, number: int, repo: str = "setup", opener=urllib.request.urlopen):
        self.token, self.number, self.repo, self.opener = token, number, repo, opener

    def _send(self, method: str, path: str, payload: dict) -> None:
        req = urllib.request.Request(
            f"{sr.API}/repos/{ORG}/{self.repo}/issues/{self.number}{path}", method=method,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ghostnet-ci-watch",
                     "Content-Type": "application/json"})
        with self.opener(req, timeout=30):
            pass

    def update_body(self, report: str) -> None:
        self._send("PATCH", "", {"body": report})

    def comment(self, text: str, items: list[dict]) -> None:
        by_text = {i["text"]: i.get("url") for i in items}
        lines = []
        for line in text.splitlines():
            url = by_text.get(line.removeprefix("cleared: "))
            lines.append(f"- [{line}]({url})" if url else f"- {line}")
        self._send("POST", "/comments", {"body": "\n".join(lines)})


# ---------------------------------------------------------------- main loop


def load_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)


def read_token(path: str, env: str) -> str | None:
    if os.environ.get(env):
        return os.environ[env]
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def run_once(gh, args, now: datetime, state: dict, runner_fetch=None) -> tuple[dict, str, dict]:
    """One pass. Returns (new state, report text, alert batch)."""
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    prs: list[dict] = []
    found: dict[str, dict] = {}
    errors: list[str] = []
    scanned: set[str] = set()
    for repo in repos:
        try:
            found.update(guard_findings(gh, repo, now))
            prs += collect_prs(gh, repo, now)
            scanned.add(repo)
        except RuntimeError as err:
            errors.append(f"{repo}: {str(err)[:160]}")
    found.update(pr_findings(prs, now, timedelta(hours=args.stuck_hours), timedelta(hours=args.idle_hours)))
    if args.runner_page:
        found.update(runner_findings(args.runner_page, runner_fetch))

    error_runs = state.get("error_runs", 0) + 1 if errors else 0
    if error_runs >= ERROR_RUNS_ALERT:
        found["watch:api-error"] = {"level": "crit", "url": "https://www.githubstatus.com/",
                                    "text": f"ci-watch could not read GitHub {error_runs} runs in a row: "
                                            + errors[0]}
    # A repo we failed to read keeps its old findings instead of "clearing" them.
    previous_active: dict[str, dict] = state.get("active", {})
    for key, item in previous_active.items():
        if item.get("repo") and item["repo"] not in scanned and item["repo"] in repos:
            found.setdefault(key, item)

    previous_prs = state.get("prs", {})
    events = pr_events(gh, previous_prs, prs, scanned, first_run=not state.get("initialized"))
    for key, old in previous_prs.items():  # unread repo: keep its PRs for next time
        if old.get("repo") not in scanned:
            prs.append(old)

    branches = state.get("branches", [])
    branches_at = state.get("branches_at")
    last_scan = sr.parse_ts(state.get("branches_scan_iso"))
    if args.branch_hours > 0 and (last_scan is None or now - last_scan >= timedelta(hours=args.branch_hours)):
        fresh = []
        try:
            for repo in repos:
                open_heads = {p.get("head_ref", "") for p in prs if p["repo"] == repo}
                fresh += merged_branches(gh, repo, open_heads)
            branches, branches_at = fresh, ts(now)
            state["branches_scan_iso"] = now.isoformat()
        except RuntimeError as err:
            errors.append(f"branches: {str(err)[:160]}")

    new = [dict(v, key=k) for k, v in found.items() if k not in previous_active]
    cleared = [dict(v, key=k) for k, v in previous_active.items() if k not in found]
    if not state.get("initialized"):
        cleared = []  # first run: everything is "new", nothing has "cleared"
    report = render_report(now, prs, found, branches, branches_at, errors)
    new_state = {
        "initialized": True, "at": now.isoformat(), "error_runs": error_runs,
        "active": found, "branches": branches, "branches_at": branches_at,
        "branches_scan_iso": state.get("branches_scan_iso"),
        "prs": {f"{p['repo']}#{p['number']}": p for p in prs},
    }
    return new_state, report, {"new": new, "cleared": cleared, "events": events}


def deliver(args, batch: dict, report: str, report_changed: bool, issue: IssueSink | None) -> list[str]:
    """Send the batch to every configured channel. Returns failures (never raises)."""
    failures = []
    items = batch["new"] + batch["events"] + batch["cleared"]
    if not items and not (issue and report_changed):
        return failures
    min_level = LEVELS[args.min_level]
    loud = [i for i in batch["new"] + batch["events"] if LEVELS[i["level"]] >= min_level]
    text = alert_text([i for i in batch["new"] if i in loud], batch["cleared"],
                      [e for e in batch["events"] if e in loud])
    level = max((i["level"] for i in batch["new"]), key=LEVELS.get, default="info")
    title = f"CI watch: {len(batch['new'])} new problem(s)" if batch["new"] else "CI watch"
    first_url = next((i.get("url") for i in batch["new"] + batch["events"] if i.get("url")), None)
    if text and args.notify:
        try:
            notify_macos(title, text)
        except (OSError, subprocess.SubprocessError) as err:
            failures.append(f"macOS banner: {err}")
    if text and args.ntfy:
        try:
            notify_ntfy(args.ntfy_server, args.ntfy, title, text, level, first_url)
        except (OSError, urllib.error.URLError) as err:
            failures.append(f"ntfy: {err}")
    if issue:
        try:
            if report_changed:
                issue.update_body(report)
            all_text = alert_text(batch["new"], batch["cleared"], batch["events"])
            if all_text:
                issue.comment(all_text, items)
        except (OSError, urllib.error.URLError) as err:
            failures.append(f"issue: {err}")
    return failures


def launchd_plist(args: list[str]) -> str:
    argv = "".join(f"<string>{a}</string>" for a in ["/usr/bin/python3", str(Path(__file__).resolve()), *args])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{LABEL}</string>
<key>ProgramArguments</key><array>{argv}</array>
<key>StartInterval</key><integer>{INTERVAL_SECONDS}</integer>
<key>RunAtLoad</key><true/>
<key>StandardOutPath</key><string>{LOG_FILE}</string>
<key>StandardErrorPath</key><string>{LOG_FILE}</string>
</dict></plist>
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repos", default=",".join(REPOS), help="comma-separated repo names")
    p.add_argument("--notify", action="store_true", help="macOS banner for new alerts")
    p.add_argument("--ntfy", metavar="TOPIC", help="ntfy topic for phone push (keep it hard to guess)")
    p.add_argument("--ntfy-server", default="https://ntfy.sh")
    p.add_argument("--issue", type=int, metavar="N", help="issue kept as the live report")
    p.add_argument("--issue-repo", default="setup", help="repo holding --issue (Issues are off in the forks)")
    p.add_argument("--min-level", choices=list(LEVELS), default="info",
                   help="lowest level that makes a banner or push (the issue gets everything)")
    p.add_argument("--runner-page", metavar="URL", help="runner status page to forward alerts from")
    p.add_argument("--stuck-hours", type=float, default=3.0, help="checks running this long alert")
    p.add_argument("--idle-hours", type=float, default=24.0, help="a ready PR untouched this long alerts")
    p.add_argument("--branch-hours", type=float, default=1.0, help="merged-branch scan interval (0 = off)")
    p.add_argument("--state-dir", default=STATE_DIR)
    p.add_argument("--json", action="store_true", help="print the run's alert batch as JSON")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["launchd"]:
        print(launchd_plist(argv[1:]), end="")
        return 0
    if argv[:1] == ["report"]:
        args = parse_args(argv[1:])
        try:
            print(Path(args.state_dir, "report.md").read_text(encoding="utf-8"), end="")
        except OSError:
            print("No report yet; run ci_watch.py once.", file=sys.stderr)
            return 2
        return 0
    args = parse_args(argv)
    token = read_token(TOKEN_FILE, "CI_WATCH_TOKEN") or sr.read_token()
    if not token:
        print(f"No token: set CI_WATCH_TOKEN or write one to {TOKEN_FILE}", file=sys.stderr)
        return 2
    issue = None
    if args.issue:
        issue_token = read_token(ISSUE_TOKEN_FILE, "CI_WATCH_ISSUE_TOKEN") or token
        issue = IssueSink(issue_token, args.issue, args.issue_repo)

    state_file = os.path.join(args.state_dir, "state.json")
    report_file = os.path.join(args.state_dir, "report.md")
    state = load_json(state_file, {})
    gh = sr.GitHub(token, ETAG_FILE)
    now = sr.utcnow()
    new_state, report, batch = run_once(gh, args, now, state)
    gh.save()

    old_report = Path(report_file).read_text(encoding="utf-8") if os.path.exists(report_file) else ""
    strip = UPDATED_LINE
    # The issue body is refreshed when something changed and at least hourly, as a heartbeat.
    last_body = sr.parse_ts(state.get("issue_body_at"))
    changed = strip.sub("", old_report) != strip.sub("", report) or last_body is None \
        or now - last_body >= timedelta(hours=1)
    failures = deliver(args, batch, report, changed, issue)
    new_state["issue_body_at"] = now.isoformat() if (issue and changed and not failures) \
        else state.get("issue_body_at")
    save_json(state_file, new_state)
    Path(report_file).write_text(report, encoding="utf-8")

    summary = (f"{ts(now)} api {gh.calls} (+{gh.not_modified} free 304s) prs {len(new_state['prs'])} "
               f"problems {len(new_state['active'])} new {len(batch['new'])} cleared {len(batch['cleared'])} "
               f"events {len(batch['events'])}")
    print(summary)
    for item in batch["new"] + batch["events"]:
        print(f"  {item['level']:<4} {item['text']}")
    for item in batch["cleared"]:
        print(f"  ok   cleared: {item['text']}")
    for failure in failures:
        print(f"  alert channel failed: {failure}", file=sys.stderr)
    if args.json:
        print(json.dumps(batch, indent=1))
    return 1 if new_state["active"] else 0


if __name__ == "__main__":
    sys.exit(main())
