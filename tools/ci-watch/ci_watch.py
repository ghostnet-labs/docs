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
  5. Every --upstream-hours (6): upstream drift. Each OpenMANET fork against
     its upstream branch, the firmware's OpenWrt 24.10 base (.openwrt-upstream)
     against openwrt-24.10, and every firmware feed pin against its branch.
     A repo or pin that falls behind is a warn until it is synced.
  6. Every --profile-hours (6): merge profile drift. Each repo's PR workflows
     (on.pull_request.paths) against project/scripts/merge_profiles.json, both
     the copy its merge gate pins and docs main. A profile path the workflow
     ignores is crit (the gate waits for a run that never starts); a workflow
     path or workflow the profile lacks is warn (the gate does not wait for it).
  7. Every scheduled workflow whose latest run failed (warn; crit for the
     firmware full build, which blocks releases). No PR shows those runs.
  8. This Mac's memory: swap in use (--swap-warn-gb 4 warn, --swap-crit-gb 8
     crit) or macOS memory pressure warn/critical, naming the biggest
     processes, so nobody has to open a dashboard to see the Studio swapping.

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
import base64
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
# Upstream drift. docs is not here (its history was rewritten, nothing to merge)
# and setup is not a fork.
UPSTREAMS = {
    "firmware": ("OpenMANET/firmware", "24.10"),
    "packages": ("OpenMANET/packages", "24.10"),
    "luci": ("OpenMANET/luci", "mm-23.05"),
    "openmanetd": ("OpenMANET/openmanetd", "main"),
    "OpenVLM": ("OpenMANET/OpenVLM", "main"),
    "protobufs": ("OpenMANET/protobufs", "main"),
}
OPENWRT = "openwrt/openwrt"
OPENWRT_BRANCH = "openwrt-24.10"
OPENWRT_MARKER = ".openwrt-upstream"  # "<sha> <branch> <revision>", written by each OpenWrt import
OPENWRT_TAG = re.compile(r"^v24\.10\.(\d+)$")
FIRMWARE_BRANCH = UPSTREAMS["firmware"][1]
# Feed repos whose pin in the firmware's feeds.conf.default is checked, and the branch it should follow.
FEED_BRANCHES = {
    "openwrt/packages": OPENWRT_BRANCH,
    "openwrt/routing": OPENWRT_BRANCH,
    "openwrt/telephony": OPENWRT_BRANCH,
    "OpenMANET/luci": "mm-23.05",
    f"{ORG}/packages": "24.10",
}
FEED_LINE = re.compile(
    r"^src-git\s+(\S+)\s+https://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?\^([0-9a-f]{7,40})\s*$", re.MULTILINE)
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
        text = f"{ORG}/{repo} {f['kind']}: {f['detail']}"
        if f.get("pr"):
            url = f"https://github.com/{ORG}/{repo}/pull/{f['pr']}"
        elif f["kind"] == "workflow-off":
            url, how = enable_link(repo, f.get("state", ""), f.get("path", ""))
            text += f"; {how}"
        found[f"guard:{repo}:{f['kind']}:{detail}"] = {"level": "crit", "repo": repo, "url": url, "text": text}
    return found


# A red scheduled run on the firmware full build blocks releases.
SCHEDULE_CRIT = ("firmware", ".github/workflows/build-full.yml")


def schedule_findings(gh, repo: str) -> dict[str, dict]:
    """Scheduled workflows whose latest finished run failed. Nobody watches those runs: no PR
    shows them, so a nightly or 6-hourly job can stay red for days. Clears on the next green run."""
    try:
        runs = gh.get(f"/repos/{ORG}/{repo}/actions/runs?event=schedule&status=completed&per_page=50")
    except RuntimeError as err:
        if "HTTP 404" in str(err):
            return {}
        raise
    found: dict[str, dict] = {}
    seen: set = set()
    for run in runs.get("workflow_runs", []) if isinstance(runs, dict) else []:
        wf = run.get("workflow_id") or run.get("path")
        if wf in seen:
            continue
        seen.add(wf)  # newest first: only each workflow's latest run counts
        if run.get("conclusion") not in ("failure", "timed_out", "startup_failure"):
            continue
        path = run.get("path", "")
        level = "crit" if (repo, path) == SCHEDULE_CRIT else "warn"
        found[f"schedule:{repo}:{path or wf}"] = {
            "level": level, "repo": repo, "url": run.get("html_url", f"https://github.com/{ORG}/{repo}/actions"),
            "text": f"{ORG}/{repo} scheduled run of {run.get('name', path)} failed "
                    f"({run.get('conclusion')}, {str(run.get('created_at', ''))[:16].replace('T', ' ')}Z)"}
    return found


def enable_link(repo: str, state: str, path: str) -> tuple[str, str]:
    """Where Justin clicks to turn a disabled workflow back on (we have no admin to do it).

    GitHub turns off every workflow in a fork until someone accepts them on the
    Actions tab; a single workflow disabled for inactivity or by hand has its
    own "Enable workflow" button on its page.
    """
    if state == "disabled_fork" or not path:
        return (f"https://github.com/{ORG}/{repo}/actions",
                "open the Actions tab and click \"I understand my workflows, go ahead and enable them\"")
    name = path.rsplit("/", 1)[-1]
    return (f"https://github.com/{ORG}/{repo}/actions/workflows/{name}",
            "open the workflow and click \"Enable workflow\"")


# Runners retired on purpose whose GitHub registrations are left to expire (Justin chose not
# to delete them, 2026-11-03): the gh-ubuntu VM's studio-ubuntu-1..5. One info line, not crit.
RETIRED_RUNNERS = (r"^studio-ubuntu-", r"^gh-ubuntu")
OFFLINE_PREFIX = "Offline runners: "


def is_retired(name: str, retired: list) -> bool:
    return any(p.search(name or "") for p in retired)


def offline_findings(state: dict, retired: list, crit_minutes: int = 30) -> dict[str, dict]:
    """The page's offline-runner alert, rebuilt so retired runners do not turn it red."""
    runners = [r for m in state.get("machines", []) for r in m.get("runners", [])]
    down = [r for r in runners if r.get("status") == "offline"
            and (r.get("why") or {}).get("cause") != "maintenance"]
    live = [r for r in down if not is_retired(r.get("name"), retired)]
    gone = sorted(r.get("name") or "?" for r in down if r not in live)
    found = {}
    if live:
        def describe(r):
            off = r.get("offline_min")
            detail = (r.get("why") or {}).get("detail")
            parts = ([minutes(timedelta(minutes=off))] if off else []) + ([detail] if detail else [])
            return r.get("name", "?") + (f" ({'; '.join(parts)})" if parts else "")
        level = "crit" if any((r.get("offline_min") or 0) >= crit_minutes for r in live) else "warn"
        found["runner:offline"] = {"level": level, "url": RUNNERS_SETTINGS,
                                   "text": "runner: " + OFFLINE_PREFIX + ", ".join(map(describe, live))}
    if gone:
        found["runner:retired"] = {"level": "info", "url": RUNNERS_SETTINGS,
                                   "text": f"{len(gone)} retired runner registration(s) still listed, left for "
                                           f"GitHub to expire: {', '.join(gone)}"}
    return found


def runner_findings(page: str, fetch=None, stale_hours: float = 12.0, retired=None) -> dict[str, dict]:
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
    retired = [re.compile(p) for p in (RETIRED_RUNNERS if retired is None else retired)]
    found = offline_findings(state, retired)
    for alert in state.get("alerts", []):
        if alert.get("level") not in ("warn", "crit"):
            continue
        text = alert.get("text", "")
        if text.startswith(OFFLINE_PREFIX):
            continue  # rebuilt above without the retired runners
        found["runner:" + DIGITS.sub("#", text)] = {
            "level": alert["level"], "url": alert.get("url") or page, "text": "runner: " + text}
    found.update(stale_registrations(state, stale_hours, retired))
    found.update(starved_labels(state, retired=retired))
    return found


STARVED_MINUTES = 15  # a queued self-hosted job this old with no online runner for its labels


def starved_labels(state: dict, min_age: int = STARVED_MINUTES, retired=()) -> dict[str, dict]:
    """Queued self-hosted jobs whose labels no online runner carries.

    The page's queue alert only says jobs are waiting. This names the label set,
    the runs that wait, and which runners could take them (offline) or that none
    is registered, e.g. openwrt-build with studio-build-1 down.
    """
    runners = [r for m in state.get("machines", []) for r in m.get("runners", [])]
    waiting: dict[tuple, list] = {}
    for j in state.get("jobs", []):
        if j.get("status") != "queued" or j.get("hosted") or (j.get("age_min") or 0) < min_age:
            continue
        want = tuple(sorted({lbl.lower() for lbl in j.get("labels") or []} - {"self-hosted"}))
        if want:
            waiting.setdefault(want, []).append(j)
    found = {}
    for want, jobs in waiting.items():
        able = [r for r in runners if set(want) <= {lbl.lower() for lbl in r.get("labels") or []}]
        if any(r.get("status") != "offline" for r in able):
            continue  # a runner is up; the queue alert covers a busy pool
        names = ", ".join(sorted(r.get("name") or "?" for r in able))
        if able and all(is_retired(r.get("name"), retired) for r in able):
            who = f"only retired runners carry these labels ({names}); point the workflow at a live label"
        elif able:
            who = f"its runners are offline: {names}"
        else:
            who = "no runner with these labels is registered"
        links = " ".join(j.get("url") or "" for j in jobs[:3])
        more = f" (+{len(jobs) - 3} more)" if len(jobs) > 3 else ""
        oldest = minutes(timedelta(minutes=max(j.get("age_min") or 0 for j in jobs)))
        found["starved:" + ",".join(want)] = {
            "level": "crit", "url": jobs[0].get("url") or RUNNERS_SETTINGS,
            "text": f"{len(jobs)} job(s) for label {'+'.join(want)} queued {oldest} and nothing can run them; "
                    f"{who}. Runs: {links}{more}. Runners: {RUNNERS_SETTINGS}"}
    return found


HOSTED_LABELS = re.compile(r"^(ubuntu|windows|macos)-", re.I)  # same rule as runner_status.py
IDLE_CONFIRM_MINUTES = 5   # an idle runner must stay idle across two runs before it alerts (not between jobs)
STALLED_MINUTES = 30       # without a runner list: a self-hosted label queued this long with nothing running
GAP_WINDOW = timedelta(hours=24)


def want_labels(job: dict) -> tuple:
    return tuple(sorted({lbl.lower() for lbl in job.get("labels") or []} - {"self-hosted"}))


def queue_state(gh, repos: list[str], now: datetime) -> dict:
    """Runners and active jobs read straight from GitHub, in the runner page's /api/state shape.

    Lets the starved and idle-runner checks run with the runner page off. Listing
    org runners needs "Self-hosted runners: read"; without it "runners_error" is
    set and only the job-based stall check runs.
    """
    state: dict = {"jobs": [], "machines": [{"name": "GitHub", "runners": []}]}
    try:
        for r in gh.get(f"/orgs/{ORG}/actions/runners?per_page=100").get("runners", []):
            status = "offline" if r.get("status") != "online" else ("busy" if r.get("busy") else "idle")
            state["machines"][0]["runners"].append({
                "name": r.get("name"), "id": r.get("id"), "status": status,
                "labels": [lbl.get("name", "") for lbl in r.get("labels") or []]})
    except RuntimeError as err:
        state["runners_error"] = str(err)[:160]
    seen: set = set()
    for repo in repos:
        for status in ("queued", "in_progress"):
            path = f"/repos/{ORG}/{repo}/actions/runs?status={status}&per_page=50"
            for run in gh.get(path).get("workflow_runs", []):
                if run.get("id") in seen:
                    continue
                seen.add(run.get("id"))
                for j in gh.get(f"/repos/{ORG}/{repo}/actions/runs/{run['id']}/jobs?per_page=100").get("jobs", []):
                    if j.get("status") not in ("queued", "in_progress"):
                        continue
                    labels = j.get("labels") or []
                    since = sr.parse_ts(j.get("started_at") if j["status"] == "in_progress" else j.get("created_at"))
                    state["jobs"].append({
                        "repo": repo, "name": j.get("name"), "status": j["status"], "labels": labels,
                        "hosted": any(HOSTED_LABELS.match(lbl) for lbl in labels) and "self-hosted" not in labels,
                        "runner": j.get("runner_name"), "url": j.get("html_url"),
                        "age_min": max(0.0, (now - since).total_seconds() / 60) if since else 0})
    return state


def stalled_labels(state: dict, min_age: int = STALLED_MINUTES) -> dict[str, dict]:
    """Without a runner list: self-hosted label sets with old queued jobs and nothing running."""
    running = [set(want_labels(j)) for j in state.get("jobs", []) if j.get("status") == "in_progress"]
    waiting: dict[tuple, list] = {}
    for j in state.get("jobs", []):
        if j.get("status") == "queued" and not j.get("hosted") and (j.get("age_min") or 0) >= min_age:
            if want_labels(j):
                waiting.setdefault(want_labels(j), []).append(j)
    found = {}
    for want, jobs in waiting.items():
        if any(set(want) <= have for have in running):
            continue
        links = " ".join(j.get("url") or "" for j in jobs[:3])
        oldest = minutes(timedelta(minutes=max(j.get("age_min") or 0 for j in jobs)))
        found["stalled:" + ",".join(want)] = {
            "level": "crit", "url": jobs[0].get("url") or RUNNERS_SETTINGS,
            "text": f"{len(jobs)} job(s) for label {'+'.join(want)} queued {oldest} and nothing with that label "
                    f"is running (ci-watch cannot list runners: {state.get('runners_error', '?')}). "
                    f"Runs: {links}. Runners: {RUNNERS_SETTINGS}"}
    return found


def idle_runners(state: dict, track: dict, now: datetime, min_age: int = STARVED_MINUTES,
                 confirm: int = IDLE_CONFIRM_MINUTES) -> tuple[dict, dict]:
    """Online, idle runners that carry every label of a job queued min_age+ minutes.

    That runner is not picking jobs up (firmware #86's board jobs waited three hours
    with studio-build-1 online). It alerts once the runner has been seen idle with
    work waiting for `confirm` minutes, so the moment between two jobs never counts.
    Also keeps the idle-while-queued gaps of the last 24 h for one info line.
    Returns (findings, track to store for the next run).
    """
    queued = [j for j in state.get("jobs", []) if j.get("status") == "queued" and not j.get("hosted")
              and want_labels(j)]
    idle_now: dict[str, list] = {}
    for m in state.get("machines", []):
        for r in m.get("runners", []):
            have = {lbl.lower() for lbl in r.get("labels") or []}
            match = [j for j in queued if set(want_labels(j)) <= have]
            if r.get("status") == "idle" and match and r.get("name"):
                idle_now[r["name"]] = match
    since = dict(track.get("idle_since", {}))
    gaps = [g for g in track.get("gaps", []) if (sr.parse_ts(g.get("end")) or now) >= now - GAP_WINDOW]
    for name in [n for n in since if n not in idle_now]:
        start = sr.parse_ts(since.pop(name)) or now
        gaps.append({"runner": name, "start": start.isoformat(), "end": now.isoformat(),
                     "min": round((now - start).total_seconds() / 60)})
    found = {}
    for name, jobs in sorted(idle_now.items()):
        start = sr.parse_ts(since.setdefault(name, now.isoformat())) or now
        idle = now - start
        old = sorted((j for j in jobs if (j.get("age_min") or 0) >= min_age), key=lambda j: -(j.get("age_min") or 0))
        if not old or idle < timedelta(minutes=confirm):
            continue
        labels = "+".join(want_labels(old[0]))
        links = " ".join(j.get("url") or "" for j in old[:3])
        more = f" (+{len(old) - 3} more)" if len(old) > 3 else ""
        found[f"idle-runner:{name}"] = {
            "level": "crit", "url": old[0].get("url") or RUNNERS_SETTINGS,
            "text": f"{name} is online but idle for {minutes(idle)}+ while {len(old)} job(s) for label {labels} "
                    f"wait (oldest {minutes(timedelta(minutes=old[0].get('age_min') or 0))}); it is not picking "
                    f"jobs up, restart its runner service. Runs: {links}{more}. Runners: {RUNNERS_SETTINGS}"}
    spans = gaps + [{"runner": n, "start": v, "end": now.isoformat(),
                     "min": round((now - (sr.parse_ts(v) or now)).total_seconds() / 60)} for n, v in since.items()]
    long_ = [g for g in spans if g["min"] >= min_age]
    if long_:
        worst = max(long_, key=lambda g: g["min"])
        found["idle-runner:gaps"] = {
            "level": "info", "url": RUNNERS_SETTINGS,
            "text": f"Idle while jobs waited, last 24 h: longest {worst['min']} min on {worst['runner']} "
                    f"(from {ts(sr.parse_ts(worst['start']))}); {len(long_)} gap(s) of {min_age}+ min"}
    return found, {"idle_since": since, "gaps": gaps[-200:]}


RUNNERS_SETTINGS = f"https://github.com/organizations/{ORG}/settings/actions/runners"
GONE_CAUSES = {"no-service", "registration"}  # watchdog: nothing on this Mac runs it any more


def stale_registrations(state: dict, stale_hours: float, retired=()) -> dict[str, dict]:
    """Self-hosted runners still registered with GitHub after their VM or service is gone.

    A retired VM leaves its runner listed as offline forever. The watchdog says
    "no-service" when nothing on the Mac runs it; otherwise a long offline spell
    is the sign. Removing a registration needs org admin, so this only links it.
    """
    found = {}
    for machine in state.get("machines", []):
        for r in machine.get("runners", []):
            if r.get("status") != "offline" or is_retired(r.get("name"), retired):
                continue  # retired ones get the single info line from offline_findings
            minutes_off = r.get("offline_min") or 0
            cause = (r.get("why") or {}).get("cause", "")
            if cause == "maintenance":
                continue
            if not (cause in GONE_CAUSES and minutes_off >= 60) and minutes_off < stale_hours * 60:
                continue
            url = f"{RUNNERS_SETTINGS}/{r['id']}" if r.get("id") else RUNNERS_SETTINGS
            why = f", {cause}" if cause else ""
            found[f"stale-runner:{r.get('name')}"] = {
                "level": "warn", "url": url,
                "text": f"runner {r.get('name')} looks retired (offline {minutes(timedelta(minutes=minutes_off))}"
                        f"{why}); remove its registration: open the link and click Remove"}
    return found


# ---------------------------------------------------------------- deployed tools

REPO_ROOT = HERE.parent.parent  # this clone of ghostnet-labs/docs
DEFAULT_CLONES = [os.path.expanduser(p) for p in ("~/ci-watch-src", "~/runner-status-src", "~/stale-runs-src")]
DRIFT_GRACE = timedelta(hours=1)  # a deploy that pulls hourly gets this long before it counts as broken
SELF_UPDATE_EVERY = timedelta(hours=1)


def run_git(path: str, *args: str) -> tuple[int, str]:
    try:
        done = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as err:
        return 1, str(err)
    return done.returncode, (done.stdout if done.returncode == 0 else done.stderr).strip()


def deploy_drift(gh, clones: list[str], now: datetime, previous: dict, git=None) -> tuple[dict, dict]:
    """Alert when a deployed clone of the docs repo misses tool changes that are on main.

    The runner status page once stopped updating and nobody noticed. Any clone
    whose tools/ differ from main for more than DRIFT_GRACE is a deploy that is
    not running, whatever does the pulling.
    """
    git = git or run_git
    found, seen = {}, {}
    if not clones:
        return found, seen
    main = gh.get(f"/repos/{ORG}/docs/commits/main")["sha"]
    for path in clones:
        code, head = git(path, "rev-parse", "HEAD")
        short = path.replace(os.path.expanduser("~"), "~", 1)
        if code != 0:
            text = f"deploy: cannot read {short}: {head[:120]}"
            found[f"deploy:{path}:git"] = {"level": "warn", "url": f"https://github.com/{ORG}/docs", "text": text}
            continue
        if head == main:
            continue
        cmp = gh.get(f"/repos/{ORG}/docs/compare/{head}...{main}")
        tools = sorted({"/".join(f["filename"].split("/")[:2]) for f in cmp.get("files", [])
                        if f.get("filename", "").startswith("tools/")})
        if not tools:
            continue
        since = sr.parse_ts((previous.get(path) or {}).get("since")) or now
        seen[path] = {"since": since.isoformat()}
        if now - since < DRIFT_GRACE:
            continue
        found[f"deploy:{path}"] = {
            "level": "warn", "url": cmp.get("html_url") or f"https://github.com/{ORG}/docs/compare/{head}...main",
            "text": f"deploy: {short} is {cmp.get('ahead_by', '?')} commits behind docs main and misses "
                    f"{', '.join(tools)} (for {minutes(now - since)}); its update is not running: "
                    f"run git -C {short} pull --ff-only and restart its LaunchAgent"}
    return found, seen


DEPLOY_STATUS = os.path.expanduser("~/.config/runner-status/deploy-status.json")
DEPLOY_STATUS_CLONE = os.path.expanduser("~/runner-status-src")
DEPLOY_STATUS_STALE = timedelta(minutes=30)  # autodeploy writes it every 2 min


def deploy_status(path: str, clone: str, now: datetime, git=None) -> dict[str, dict]:
    """Alert when the runner-status autodeploy says it failed, lies, or has stopped.

    It once failed on local edits yet kept writing ok:true. So trust nothing it
    says alone: ok must be true, its commit must be the clone's HEAD, and the
    file must have been written recently.
    """
    if not path or not os.path.exists(path):
        return {}
    git = git or run_git
    url = f"https://github.com/{ORG}/docs/commits/main/tools/runner-status"
    short = path.replace(os.path.expanduser("~"), "~", 1)
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError) as err:
        return {"deploy-status": {"level": "warn", "url": url,
                                  "text": f"runner-status autodeploy: cannot read {short}: {str(err)[:120]}"}}
    problems = []
    if st.get("ok") is not True:
        problems.append(f"it reports a failure ({str(st.get('reason') or 'no reason given')[:120]})")
    at = sr.parse_ts(st.get("at"))
    if at is None:
        problems.append("it has no time stamp")
    elif now - at > DEPLOY_STATUS_STALE:
        problems.append(f"it last ran {minutes(now - at)} ago")
    code, head = git(clone, "rev-parse", "HEAD")
    if code == 0 and st.get("commit") and st["commit"] != head:
        problems.append(f"it says {str(st['commit'])[:7]} but the clone is at {head[:7]}")
    if not problems:
        return {}
    return {"deploy-status": {
        "level": "warn", "url": url,
        "text": "runner-status autodeploy is not working: " + "; ".join(problems)
                + ". On the Studio check ~/Library/Logs and launchctl list com.ghostnet.runner-status.autodeploy"}}


IDLE_RESTART = os.path.expanduser("~/.config/ci-k3s-idle-restart/status.json")
IDLE_RESTART_AGENT = "com.ghostnet.ci-k3s-idle-restart"
IDLE_RESTART_STALE = timedelta(hours=2)


def agent_loaded(label: str) -> bool:
    """True when launchd has this LaunchAgent loaded (macOS only)."""
    try:
        done = subprocess.run(["launchctl", "list", label], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def idle_restart_status(path: str, now: datetime, loaded=None) -> dict[str, dict]:
    """Heartbeat of the ci-k3s idle-restart agent on the Studio.

    Same idea as deploy_status: a stopped agent must not look like a quiet one.
    Before the LaunchAgent is loaded there is one info line; after, a failure
    or a status file older than IDLE_RESTART_STALE is crit, and each restart
    is reported once as info.
    """
    if not path:
        return {}
    if loaded is None:
        if platform.system() != "Darwin":
            return {}
        loaded = agent_loaded(IDLE_RESTART_AGENT)
    url = f"https://github.com/{ORG}/docs/commits/main"
    if not loaded:
        return {"idle-restart:agent": {"level": "info", "url": url,
                                       "text": f"idle-restart agent not loaded ({IDLE_RESTART_AGENT})"}}
    short = path.replace(os.path.expanduser("~"), "~", 1)
    hint = f"; on the Studio check launchctl list {IDLE_RESTART_AGENT} and its log"
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError) as err:
        return {"idle-restart": {"level": "crit", "url": url,
                                 "text": f"ci-k3s idle-restart: cannot read {short}: {str(err)[:120]}{hint}"}}
    problems = []
    if st.get("ok") is not True:
        problems.append(f"it reports {st.get('action') or 'a failure'} ({str(st.get('reason') or 'no reason')[:120]})")
    at = sr.parse_ts(st.get("at"))
    if at is None:
        problems.append("it has no time stamp")
    elif now - at > IDLE_RESTART_STALE:
        problems.append(f"it last ran {minutes(now - at)} ago")
    found = {}
    if problems:
        found["idle-restart"] = {"level": "crit", "url": url,
                                 "text": "ci-k3s idle-restart is not working: " + "; ".join(problems) + hint}
    elif st.get("action") == "restarted":
        found[f"idle-restart:restarted:{st.get('at')}"] = {
            "level": "info", "url": url,
            "text": f"ci-k3s idle-restart restarted the cluster: {str(st.get('reason') or 'no reason given')[:160]}"}
    return found


GIB = 1024 ** 3
SWAP_FULL = 0.9            # swap files this full are crit ...
SWAP_FULL_MIN = 2 * GIB    # ... once there is real swap (macOS grows the file to fit, so small is always "full")
MEMORY_CLEAR_RATIO = 0.75  # an active swap alert clears only below this share of its threshold (4 GiB -> 3 GiB)
PRESSURE = {1: "normal", 2: "warn", 4: "critical"}  # kern.memorystatus_vm_pressure_level
SWAP_FIELD = re.compile(r"(total|used)\s*=\s*([\d.]+)([KMGT])")
UNIT = {"K": 1024, "M": 1024 ** 2, "G": GIB, "T": 1024 ** 4}
MEMORY_URL = f"https://github.com/{ORG}/docs/tree/main/tools/ci-watch#host-memory"


def run_cmd(*cmd: str) -> str:
    try:
        done = subprocess.run(list(cmd), capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def gib(n: float) -> str:
    return f"{n / GIB:.1f} GiB"


def biggest_processes(run) -> list[str]:
    """The four biggest processes by memory footprint, as top shows them."""
    lines = run("top", "-l", "1", "-o", "mem", "-n", "4", "-stats", "command,mem").strip().splitlines()
    head = next((i for i, ln in enumerate(lines) if ln.split()[:1] == ["COMMAND"]), None)
    if head is None:
        return []
    # top cuts names at 16 characters; every Lima and Docker VM shows as this one.
    return [" ".join(ln.split()).replace("com.apple.Virtua", "VM", 1) for ln in lines[head + 1:] if ln.strip()]


def host_memory(previous: dict | None = None, warn_gib: float = 4.0, crit_gib: float = 8.0,
                idle_status: str = "", run=None) -> dict[str, dict]:
    """Swap and memory pressure of the Mac running ci-watch, read with sysctl and top.

    Replaces the runner page's swap alerts, so nobody has to open a dashboard.
    Read-only. warn at warn_gib of swap or pressure "warn"; crit at crit_gib,
    a swap file 90% full, or pressure "critical". An active alert holds until
    swap drops below MEMORY_CLEAR_RATIO of its threshold, so it does not flap.
    warn_gib 0 turns the check off; crit_gib 0 means swap alone never makes it crit.
    """
    if warn_gib <= 0:
        return {}
    if run is None:
        if platform.system() != "Darwin":
            return {}
        run = run_cmd
    previous = previous or {}
    swap = {k: float(v) * UNIT[u] for k, v, u in SWAP_FIELD.findall(run("sysctl", "-n", "vm.swapusage"))}
    used, total = swap.get("used", 0.0), swap.get("total", 0.0)
    try:
        level = int(run("sysctl", "-n", "kern.memorystatus_vm_pressure_level").strip() or 0)
    except ValueError:
        level = 0

    def limit(gib_: float, *keys: str) -> float:
        return gib_ * GIB * (MEMORY_CLEAR_RATIO if any(f"host:memory:{k}" in previous for k in keys) else 1)

    full = crit_gib > 0 and total > 0 and used >= SWAP_FULL_MIN and used / total >= SWAP_FULL
    if (crit_gib > 0 and used >= limit(crit_gib, "crit")) or level >= 4 or full:
        severity = "crit"
    elif used >= limit(warn_gib, "warn", "crit") or level >= 2:
        severity = "warn"
    else:
        return {}
    top = ", ".join(biggest_processes(run)) or "unknown"
    text = (f"Mac is swapping: {gib(used)} of {gib(total)} swap in use, memory pressure {PRESSURE.get(level, level)}. "
            f"Biggest: {top}. The ci-k3s idle restart frees its VM when ARC is idle; "
            "Docker Desktop and idle apps are the other usual causes")
    if idle_status and os.path.exists(idle_status):
        try:
            with open(idle_status, encoding="utf-8") as f:
                st = json.load(f)
            text += f". Idle restart last said {st.get('action')} ({str(st.get('reason') or '')[:80]})"
        except (OSError, ValueError):
            pass
    return {f"host:memory:{severity}": {"level": severity, "url": MEMORY_URL, "text": text}}


def update_self(now: datetime, previous: dict, git=None, root: str | None = None) -> tuple[dict, dict]:
    """Pull this clone hourly so new checks reach the Studio without anyone typing a line.

    Only fast-forwards a clean checkout of protected main; anything else is an
    alert, never a forced update. The next run uses the new code.
    """
    git = git or run_git
    root = root or str(REPO_ROOT)
    last = sr.parse_ts(previous.get("at"))
    if last and now - last < SELF_UPDATE_EVERY:
        return previous.get("found", {}), previous
    found = {}
    code, dirty = git(root, "status", "--porcelain", "--untracked-files=no")
    if code != 0:
        found["self-update"] = {"level": "warn", "url": f"https://github.com/{ORG}/docs",
                                "text": f"ci-watch cannot update itself: {dirty[:160]}"}
    elif dirty:
        found["self-update"] = {"level": "warn", "url": f"https://github.com/{ORG}/docs",
                                "text": "ci-watch cannot update itself: its clone has local edits"}
    else:
        code, out = git(root, "pull", "--ff-only", "--quiet")
        if code != 0:
            found["self-update"] = {"level": "warn", "url": f"https://github.com/{ORG}/docs/commits/main",
                                    "text": f"ci-watch cannot update itself: git pull failed: {out[:160]}"}
    return found, {"at": now.isoformat(), "found": found}


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


def behind_by(gh, repo: str, base: str, head: str) -> int:
    """Commits on head that base lacks (compare base...head in repo)."""
    quoted = urllib.parse.quote(f"{base}...{head}", safe=".:")
    return int(gh.get(f"/repos/{repo}/compare/{quoted}?per_page=1").get("ahead_by", 0))


def repo_file(gh, repo: str, path: str, ref: str) -> str | None:
    """A file's text on ref, or None when it does not exist there."""
    try:
        data = gh.get(f"/repos/{repo}/contents/{path}?ref={urllib.parse.quote(ref, safe='')}")
    except RuntimeError as err:
        if "HTTP 404" in str(err):
            return None
        raise
    return base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")


def latest_openwrt_release(gh) -> str | None:
    best = None
    for tag in gh.get(f"/repos/{OPENWRT}/tags?per_page=100"):
        m = OPENWRT_TAG.match(tag.get("name", ""))
        if m and (best is None or int(m.group(1)) > best):
            best = int(m.group(1))
    return None if best is None else f"v24.10.{best}"


def upstream_drift(gh, repos: list[str]) -> tuple[list[dict], dict[str, dict]]:
    """Rows for the report and a warn finding for everything behind its upstream."""
    rows: list[dict] = []
    found: dict[str, dict] = {}

    def add(key: str, what: str, upstream: str, behind: int | None, url: str, note: str = "") -> None:
        rows.append({"what": what, "upstream": upstream, "behind": behind, "url": url, "note": note})
        if behind:
            text = f"upstream: {what} is {behind} commit{'s' if behind != 1 else ''} behind {upstream}"
            found["upstream:" + key] = {"level": "warn", "url": url, "text": text + (f" ({note})" if note else "")}

    for repo in repos:
        if repo not in UPSTREAMS:
            continue
        upstream, branch = UPSTREAMS[repo]
        owner, name = upstream.split("/")
        head = f"{owner}:{name}:{branch}"
        add(repo, f"{ORG}/{repo} {branch}", f"{upstream} {branch}", behind_by(gh, f"{ORG}/{repo}", branch, head),
            f"https://github.com/{ORG}/{repo}/compare/{branch}...{head}")

    if "firmware" not in repos:
        return rows, found
    fw = f"{ORG}/firmware"
    release = latest_openwrt_release(gh)
    note = f"latest release {release}" if release else ""
    marker = repo_file(gh, fw, OPENWRT_MARKER, FIRMWARE_BRANCH)
    synced = marker.split()[0] if marker and marker.split() else None
    if synced:
        add("openwrt-base", f"firmware OpenWrt base ({synced[:10]})", f"{OPENWRT} {OPENWRT_BRANCH}",
            behind_by(gh, OPENWRT, synced, OPENWRT_BRANCH),
            f"https://github.com/{OPENWRT}/compare/{synced}...{OPENWRT_BRANCH}", note)
    else:
        url = f"https://github.com/{fw}/blob/{FIRMWARE_BRANCH}/{OPENWRT_MARKER}"
        rows.append({"what": "firmware OpenWrt base", "upstream": f"{OPENWRT} {OPENWRT_BRANCH}", "behind": None,
                     "url": url, "note": f"{OPENWRT_MARKER} missing; {note or 'no release found'}"})
        found["upstream:openwrt-base"] = {
            "level": "warn", "url": url,
            "text": f"upstream: firmware has no {OPENWRT_MARKER}, so its OpenWrt base is unknown ({note})"}

    feeds = repo_file(gh, fw, "feeds.conf.default", FIRMWARE_BRANCH) or ""
    for feed, repo, pin in FEED_LINE.findall(feeds):
        branch = FEED_BRANCHES.get(repo)
        if not branch:
            continue
        add(f"feed:{feed}", f"firmware feed {feed} ({pin[:10]})", f"{repo} {branch}",
            behind_by(gh, repo, pin, branch), f"https://github.com/{repo}/compare/{pin}...{branch}")
    return rows, found


# ---------------------------------------------------------------- merge profile drift
#
# merge_profiles.json (project/scripts) copies each PR workflow's on.pull_request.paths so
# the merge gate knows which workflows a PR must wait for. When a repo edits a workflow's
# paths and the copy is not updated, the gate either waits for a run that never starts
# (the profile lists a path the workflow ignores: the PR sits until the gate times out)
# or merges without a check that did run (the workflow lists a path the profile lacks).
# firmware #82 narrowed build-pr-nanopc-t6.yml and the profile kept the old paths.

PROFILE_FILE = HERE.parents[1] / "project" / "scripts" / "merge_profiles.json"
PROFILE_PATH = "project/scripts/merge_profiles.json"
GATE_WORKFLOW = ".github/workflows/manet-merge-gate.yml"
# Workflows the gate itself ignores (merge_policy.py: the gate, LABEL_WORKFLOWS).
GATE_IGNORED = {GATE_WORKFLOW, ".github/workflows/label-kernel.yml", ".github/workflows/label-target.yml"}
GATE_PIN = re.compile(r"repository:\s*['\"]?" + re.escape(ORG) + r"/docs['\"]?\s*\n\s*ref:\s*['\"]?([0-9a-f]{40})")
YAML_KEY = re.compile(r"^(\s*)(['\"]?)([\w-]+)\2:\s*(.*)$")


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _flow_list(value: str) -> list[str]:
    return [_scalar(v) for v in value.strip()[1:-1].split(",") if v.strip()]


def _block(lines: list[str], start: int, indent: int) -> list[str]:
    """Lines after start that are indented deeper than indent (blank lines dropped)."""
    out = []
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        out.append(line)
    return out


def _sequence(lines: list[str], start: int, indent: int) -> list[str]:
    """A block sequence under the key at lines[start]; YAML allows its "- " items at the key's own indent."""
    items = []
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        depth = len(line) - len(line.lstrip())
        if depth < indent or (depth == indent and not line.lstrip().startswith("- ")):
            break
        if line.lstrip().startswith("- "):
            items.append(_scalar(line.strip()[2:]))
    return items


def pr_trigger(text: str) -> tuple[bool, list[str] | None]:
    """(runs on pull_request, its paths filter or None for every change) for a workflow file.

    A small reader for the block-style YAML these workflows use, so the Mac needs no PyYAML.
    Only on.pull_request.paths is read; pull_request_target does not count.
    """
    lines = [_strip_comment(line) for line in text.splitlines()]
    for i, line in enumerate(lines):
        m = YAML_KEY.match(line)
        if not m or m.group(1) or m.group(3) != "on":
            continue
        inline = m.group(4).strip()
        if inline:
            names = _flow_list(inline) if inline.startswith("[") else [_scalar(inline)]
            return "pull_request" in names, None
        body = _block(lines, i, 0)
        if not body:
            return False, None
        child = len(body[0]) - len(body[0].lstrip())
        if body[0].lstrip().startswith("- "):
            return "pull_request" in [_scalar(b.strip()[2:]) for b in body if b.strip().startswith("- ")], None
        for j, b in enumerate(body):
            k = YAML_KEY.match(b)
            if not k or len(k.group(1)) != child or k.group(3) != "pull_request":
                continue
            rest = k.group(4).strip()
            if rest and rest not in ("{}", "null", "~"):
                return True, None
            sub = _block(body, j, child)
            if not sub:
                return True, None
            grand = len(sub[0]) - len(sub[0].lstrip())
            for n, s in enumerate(sub):
                km = YAML_KEY.match(s)
                if not km or len(km.group(1)) != grand or km.group(3) != "paths":
                    continue
                val = km.group(4).strip()
                if val.startswith("["):
                    return True, _flow_list(val)
                return True, _sequence(sub, n, grand)
            return True, None
        return False, None
    return False, None


def profile_gaps(profile: dict, workflows: dict[str, str]) -> dict[str, tuple[str, str]]:
    """{workflow path: (level, problem)} where profile and workflow files disagree."""
    gaps: dict[str, tuple[str, str]] = {}
    listed = {w["path"]: w["paths"] for w in profile.get("workflows", [])}
    for path, expected in listed.items():
        if path not in workflows:
            gaps[path] = ("crit", "is in the profile but the workflow file is gone, so the gate waits for it forever")
            continue
        runs, actual = pr_trigger(workflows[path])
        if not runs:
            gaps[path] = ("crit", "is in the profile but no longer runs on pull_request, so the gate waits for it")
            continue
        if expected is None and actual is None:
            continue
        if expected is None or actual is None:
            what = "every change" if actual is None else "only some paths"
            gaps[path] = ("crit" if actual is not None else "warn",
                          f"runs on {what} but the profile says {'every change' if expected is None else 'some paths'}")
            continue
        extra = sorted(set(expected) - set(actual))
        missing = sorted(set(actual) - set(expected))
        if extra:
            gaps[path] = ("crit", "profile lists paths the workflow ignores, so the gate waits for a run that "
                                  "never starts: " + ", ".join(extra))
        elif missing:
            gaps[path] = ("warn", "workflow runs on paths the profile lacks, so the gate does not wait for it: "
                                  + ", ".join(missing))
    for path, text in workflows.items():
        if path in listed or path in GATE_IGNORED:
            continue
        runs, _ = pr_trigger(text)
        if runs:
            gaps[path] = ("warn", "runs on pull requests but is not in the profile, so the gate does not wait for it")
    return gaps


def repo_workflows(gh, repo: str, ref: str) -> dict[str, str]:
    listing = gh.get(f"/repos/{repo}/contents/.github/workflows?ref={urllib.parse.quote(ref, safe='')}")
    out: dict[str, str] = {}
    for item in listing:
        if item.get("type") == "file" and item.get("name", "").endswith((".yml", ".yaml")):
            out[item["path"]] = repo_file(gh, repo, item["path"], ref) or ""
    return out


def profile_drift(gh, repos: list[str], local: dict | None = None) -> dict[str, dict]:
    """Findings for each repo whose workflows disagree with the profile its gate uses or with docs main."""
    if local is None:
        local = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    found: dict[str, dict] = {}
    pinned_cache: dict[str, dict] = {}
    for repo in repos:
        if repo not in local:
            continue
        full = f"{ORG}/{repo}"
        branch = local[repo]["branch"]
        try:
            workflows = repo_workflows(gh, full, branch)
        except RuntimeError:
            continue  # unreadable this time (the PR scan reports read errors); try again next interval
        sources = [("docs main", local[repo], f"https://github.com/{ORG}/docs/blob/main/{PROFILE_PATH}")]
        pin = GATE_PIN.search(workflows.get(GATE_WORKFLOW, ""))
        if pin:
            sha = pin.group(1)
            if sha not in pinned_cache:
                pinned_cache[sha] = json.loads(repo_file(gh, f"{ORG}/docs", PROFILE_PATH, sha) or "{}")
            if repo in pinned_cache[sha]:
                sources.insert(0, (f"the gate's pinned docs {sha[:7]}", pinned_cache[sha][repo],
                                   f"https://github.com/{ORG}/docs/blob/{sha}/{PROFILE_PATH}"))
        merged: dict[str, list] = {}
        for label, profile, url in sources:
            for path, (level, problem) in profile_gaps(profile, workflows).items():
                merged.setdefault(path, []).append((level, problem, label, url))
        for path, hits in merged.items():
            level = max((h[0] for h in hits), key=LEVELS.get)
            name = path.rsplit("/", 1)[-1]
            problems: dict[str, list[str]] = {}
            for _, problem, label, _ in hits:
                problems.setdefault(problem, []).append(label)
            detail = "; ".join(f"{problem} (merge_profiles.json in {' and '.join(labels)})"
                               for problem, labels in problems.items())
            found[f"profile:{repo}:{name}"] = {
                "level": level, "repo": repo, "url": f"https://github.com/{full}/blob/{branch}/{path}",
                "text": f"merge gate: {repo} {name}: {detail}"}
    return found


# ---------------------------------------------------------------- report


def render_report(now: datetime, prs: list[dict], active: dict[str, dict], branches: list[dict],
                  branches_at: str | None, errors: list[str], upstream: dict | None = None) -> str:
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
    if upstream is not None:
        lines += ["", "## Upstream drift", ""]
        if not upstream.get("at"):
            lines.append("Not scanned yet." + (f" Last try failed: {upstream['error']}" if upstream.get("error") else ""))
        else:
            lines.append(f"Scanned {upstream['at']}. Behind = upstream commits we do not have yet.")
            if upstream.get("error"):
                lines += ["", f"Last scan failed, showing the one before: {upstream['error']}"]
            lines += ["", "| Ours | Upstream | Behind | Note |", "|---|---|---|---|"]
            for r in upstream.get("rows", []):
                behind = "?" if r["behind"] is None else str(r["behind"])
                lines.append(f"| {r['what']} | {r['upstream']} | [{behind}]({r['url']}) | {r.get('note', '')} |")
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
            found.update(schedule_findings(gh, repo))
            prs += collect_prs(gh, repo, now)
            scanned.add(repo)
        except RuntimeError as err:
            errors.append(f"{repo}: {str(err)[:160]}")
    found.update(pr_findings(prs, now, timedelta(hours=args.stuck_hours), timedelta(hours=args.idle_hours)))
    retired_patterns = list(RETIRED_RUNNERS) + (args.retired_runner or [])
    if args.runner_page:
        found.update(runner_findings(args.runner_page, runner_fetch, args.stale_runner_hours, retired_patterns))
    idle_track = state.get("idle_runners", {})
    if getattr(args, "queue_check", True):
        try:
            queue = queue_state(gh, repos, now)
            if queue.get("runners_error"):
                found["queue:runners-unreadable"] = {
                    "level": "info", "url": "https://github.com/settings/personal-access-tokens",
                    "text": "ci-watch cannot list org runners, so the idle-runner check is off and only the stall "
                            "check runs. Give its token Organization permissions > Self-hosted runners: Read-only "
                            f"({queue['runners_error']})"}
                found.update(stalled_labels(queue))
            else:
                found.update(starved_labels(queue, retired=[re.compile(p) for p in retired_patterns]))
                idle_found, idle_track = idle_runners(queue, idle_track, now)
                found.update(idle_found)
        except RuntimeError as err:
            errors.append(f"runner queue: {str(err)[:160]}")

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

    upstream = state.get("upstream", {})
    last_up = sr.parse_ts(upstream.get("scan_iso"))
    if args.upstream_hours > 0 and (last_up is None or now - last_up >= timedelta(hours=args.upstream_hours)):
        try:
            rows, drift = upstream_drift(gh, repos)
            upstream = {"scan_iso": now.isoformat(), "at": ts(now), "rows": rows, "found": drift}
        except RuntimeError as err:
            # Keep the last scan's rows and findings and try again next interval. Not counted
            # as a GitHub read error: upstream repos are not ours and a failure here is no outage.
            upstream = dict(upstream, scan_iso=now.isoformat(), error=f"{ts(now)}: {str(err)[:200]}")
    if args.upstream_hours > 0:
        found.update(upstream.get("found", {}))
    else:
        upstream = {}

    profiles = state.get("profiles", {})
    profile_hours = getattr(args, "profile_hours", 0)
    last_prof = sr.parse_ts(profiles.get("scan_iso"))
    if profile_hours > 0 and (last_prof is None or now - last_prof >= timedelta(hours=profile_hours)):
        try:
            profiles = {"scan_iso": now.isoformat(), "found": profile_drift(gh, repos)}
        except (RuntimeError, OSError, ValueError) as err:
            # Keep the last scan's findings and try again next interval, like the upstream scan.
            profiles = dict(profiles, scan_iso=now.isoformat(), error=f"{ts(now)}: {str(err)[:200]}")
    if profile_hours > 0:
        found.update(profiles.get("found", {}))
    else:
        profiles = {}

    clones = args.clone if args.clone is not None else [c for c in DEFAULT_CLONES if os.path.isdir(c)]
    drift_state = state.get("deploy", {})
    try:
        drift_found, drift_state = deploy_drift(gh, clones, now, drift_state, git=getattr(args, "git", None))
        found.update(drift_found)
    except RuntimeError as err:
        errors.append(f"deploy check: {str(err)[:160]}")
    found.update(deploy_status(getattr(args, "deploy_status", DEPLOY_STATUS), DEPLOY_STATUS_CLONE, now,
                               git=getattr(args, "git", None)))
    found.update(idle_restart_status(getattr(args, "idle_restart_status", IDLE_RESTART), now,
                                     loaded=getattr(args, "idle_restart_loaded", None)))
    found.update(host_memory(previous_active, getattr(args, "swap_warn_gb", 4.0), getattr(args, "swap_crit_gb", 8.0),
                             getattr(args, "idle_restart_status", IDLE_RESTART), run=getattr(args, "run", None)))
    self_update = state.get("self_update", {})
    if args.self_update:
        self_found, self_update = update_self(now, self_update, git=getattr(args, "git", None))
        found.update(self_found)

    new = [dict(v, key=k) for k, v in found.items() if k not in previous_active]
    cleared = [dict(v, key=k) for k, v in previous_active.items() if k not in found]
    if not state.get("initialized"):
        cleared = []  # first run: everything is "new", nothing has "cleared"
    report = render_report(now, prs, found, branches, branches_at, errors,
                           upstream if args.upstream_hours > 0 else None)
    new_state = {
        "initialized": True, "at": now.isoformat(), "error_runs": error_runs,
        "active": found, "branches": branches, "branches_at": branches_at,
        "branches_scan_iso": state.get("branches_scan_iso"), "upstream": upstream,
        "deploy": drift_state, "self_update": self_update, "profiles": profiles,
        "idle_runners": idle_track,
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
    p.add_argument("--clone", action="append", metavar="PATH",
                   help="deployed docs clone to check against main (default: the usual ~/*-src clones)")
    p.add_argument("--deploy-status", default=DEPLOY_STATUS, metavar="PATH",
                   help="runner-status autodeploy status file to check ('' = off)")
    p.add_argument("--idle-restart-status", default=IDLE_RESTART, metavar="PATH",
                   help="ci-k3s idle-restart status file to check ('' = off)")
    p.add_argument("--swap-warn-gb", type=float, default=4.0,
                   help="warn when this Mac has this much swap in use or memory pressure is warn (0 = off)")
    p.add_argument("--swap-crit-gb", type=float, default=8.0,
                   help="crit at this much swap in use or memory pressure critical (0 = no crit from swap)")
    p.add_argument("--no-queue-check", dest="queue_check", action="store_false",
                   help="skip reading runners and queued jobs from GitHub (starved label, idle runner)")
    p.add_argument("--no-self-update", dest="self_update", action="store_false",
                   help="do not fast-forward this clone of docs every hour")
    p.add_argument("--retired-runner", action="append", metavar="REGEX",
                   help="runner name pattern retired on purpose: one info line, never an alert "
                        "(adds to ^studio-ubuntu-, ^gh-ubuntu)")
    p.add_argument("--stale-runner-hours", type=float, default=12.0,
                   help="an offline runner this long counts as a leftover registration")
    p.add_argument("--stuck-hours", type=float, default=3.0, help="checks running this long alert")
    p.add_argument("--idle-hours", type=float, default=24.0, help="a ready PR untouched this long alerts")
    p.add_argument("--branch-hours", type=float, default=1.0, help="merged-branch scan interval (0 = off)")
    p.add_argument("--upstream-hours", type=float, default=6.0,
                   help="upstream drift scan interval: forks vs OpenMANET, firmware vs OpenWrt 24.10 (0 = off)")
    p.add_argument("--profile-hours", type=float, default=6.0,
                   help="merge profile check interval: merge_profiles.json vs each repo's PR workflow paths (0 = off)")
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
