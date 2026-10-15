#!/usr/bin/env python3
"""Find, and optionally cancel, dead GitHub Actions runs in the ghostnet-labs repos.

One file, Python 3 standard library only. A run is "dead" only when it is
provably wasted work:

  closed      a pull_request run whose PR is merged or closed
  superseded  a pull_request run on an old head of a still-open PR, when a run
              of the same workflow already exists for the PR's current head

Everything else is only reported, never cancelled:

  zombie      queued or running longer than --stale-hours (shows its job count;
              0 jobs means GitHub never created any)
  stuck-push  a push run on a branch that has a newer push run of the same
              workflow (the old head no longer matters to the gate, but push
              runs can publish artifacts, so a person decides)

Safety rules, enforced in code:

  * never touches the current-head run of an open PR;
  * never touches workflow_dispatch, schedule or push runs;
  * a run whose workflow name matches --protect (default: Build Kernel) is
    cancelled only after its matrix has expanded (more than one job), because
    cancelling the placeholder job leaves a "skipped" check the merge gate
    treats as final on that commit;
  * --skip-pr REPO#N and --skip-run ID always win;
  * at most --max-cancel cancels per invocation (default 10).

Default is a dry run. Examples:

  python3 stale_runs.py                       # report only
  python3 stale_runs.py --cancel              # cancel what is provably dead
  python3 stale_runs.py --json                # machine-readable report
  python3 stale_runs.py launchd --cancel      # print a LaunchAgent plist

API cost: per repo one open-PR list plus one run list per status (queued,
in_progress, waiting). Requests carry the last ETag, kept in
~/.cache/stale-runs/etags.json, and GitHub does not count "304 not changed"
answers against the hourly limit, so a quiet org costs almost nothing.
Job lists are fetched only for protected or zombie runs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
ORG = "ghostnet-labs"
REPOS = ["firmware", "packages", "luci", "openmanetd", "OpenVLM", "protobufs", "docs", "setup"]
ACTIVE_STATUSES = ("queued", "in_progress", "waiting")
PR_EVENTS = ("pull_request", "pull_request_target")
TOKEN_FILE = os.path.expanduser("~/.config/stale-runs/token")
ETAG_FILE = os.path.expanduser("~/.cache/stale-runs/etags.json")
ETAG_MAX = 200  # cached responses kept between invocations
DEFAULT_PROTECT = r"(?i)kernel"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def read_token() -> str | None:
    tok = os.environ.get("STALE_RUNS_TOKEN")
    if tok:
        return tok.strip()
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            return fh.read().strip() or None
    return os.environ.get("GITHUB_TOKEN")


class GitHub:
    """Minimal API client with an on-disk ETag cache for GET requests."""

    def __init__(self, token: str, etag_file: str | None = ETAG_FILE):
        self.token = token
        self.etag_file = etag_file
        self.cache: dict[str, dict] = {}
        self.calls = 0  # requests GitHub counted (not 304s)
        self.not_modified = 0
        if etag_file and os.path.exists(etag_file):
            try:
                with open(etag_file, encoding="utf-8") as fh:
                    self.cache = json.load(fh)
            except (OSError, json.JSONDecodeError):
                self.cache = {}

    def _request(self, method: str, path: str, headers: dict) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(API + path, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as err:
            return err.code, dict(err.headers or {}), err.read() or b""

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ghostnet-stale-runs"}

    def get(self, path: str):
        headers = self._headers()
        cached = self.cache.get(path)
        if cached and cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        code, resp_headers, body = self._request("GET", path, headers)
        if code == 304 and cached:
            self.not_modified += 1
            return cached["data"]
        self.calls += 1
        if code != 200:
            raise RuntimeError(f"GET {path}: HTTP {code}: {body[:200].decode(errors='replace')}")
        data = json.loads(body)
        etag = resp_headers.get("ETag") or resp_headers.get("Etag")
        if etag:
            self.cache.pop(path, None)
            self.cache[path] = {"etag": etag, "data": data}
            while len(self.cache) > ETAG_MAX:
                self.cache.pop(next(iter(self.cache)))
        return data

    def cancel(self, repo: str, run_id: int) -> str:
        self.calls += 1
        code, _, body = self._request(
            "POST", f"/repos/{ORG}/{repo}/actions/runs/{run_id}/cancel", self._headers())
        if code in (202, 200):
            return "cancelled"
        return f"HTTP {code}: {body[:120].decode(errors='replace')}"

    def save(self) -> None:
        if not self.etag_file:
            return
        try:
            os.makedirs(os.path.dirname(self.etag_file), exist_ok=True)
            with open(self.etag_file, "w", encoding="utf-8") as fh:
                json.dump(self.cache, fh)
        except OSError:
            pass  # the cache only saves API calls; losing it is harmless


def run_prs(run: dict) -> list[int]:
    return [p["number"] for p in run.get("pull_requests") or [] if "number" in p]


def find_pr(run: dict, open_prs: dict[int, dict], by_branch: dict[str, dict]) -> dict | None:
    """The open PR a run belongs to, or None when it belongs to no open PR."""
    for num in run_prs(run):
        if num in open_prs:
            return open_prs[num]
    if run.get("event") == "pull_request" and not run_prs(run):
        # Fork PRs carry no pull_requests entries; match by head branch.
        return by_branch.get(run.get("head_branch") or "")
    return None


def classify(repo: str, runs: list[dict], open_prs: dict[int, dict], now: datetime,
             stale_hours: float, head_runs: set[tuple] | None = None) -> list[dict]:
    """Label every active run. Pure function: no API calls.

    head_runs holds (workflow_id, sha) pairs known to have a run, in any state;
    the active runs are added to it here."""
    by_branch = {pr["head"]["ref"]: pr for pr in open_prs.values()}
    head_runs = set(head_runs or ()) | {(r.get("workflow_id"), r.get("head_sha")) for r in runs}
    newest_push: dict[tuple, dict] = {}
    for r in runs:
        if r.get("event") == "push":
            key = (r.get("workflow_id"), r.get("head_branch"))
            if key not in newest_push or r["created_at"] > newest_push[key]["created_at"]:
                newest_push[key] = r

    out = []
    for r in runs:
        created = parse_ts(r.get("created_at"))
        age_h = (now - created).total_seconds() / 3600 if created else 0.0
        item = {"repo": repo, "id": r["id"], "workflow": r.get("name") or "",
                "event": r.get("event"), "branch": r.get("head_branch"),
                "sha": (r.get("head_sha") or "")[:7], "status": r.get("status"),
                "age_h": round(age_h, 1), "prs": run_prs(r), "url": r.get("html_url"),
                "class": "live", "reason": "", "cancel": False}
        event = r.get("event")
        pr = find_pr(r, open_prs, by_branch)
        if event in PR_EVENTS:
            if pr is None:
                if run_prs(r) or event == "pull_request":
                    item["class"] = "closed"
                    nums = ", ".join(f"#{n}" for n in run_prs(r)) or r.get("head_branch")
                    item["reason"] = f"PR {nums} is no longer open"
                    item["cancel"] = True
            elif event == "pull_request" and r.get("head_sha") != pr["head"]["sha"]:
                if (r.get("workflow_id"), pr["head"]["sha"]) in head_runs:
                    item["class"] = "superseded"
                    item["reason"] = (f"PR #{pr['number']} moved to {pr['head']['sha'][:7]}, "
                                      "which has its own run of this workflow")
                    item["cancel"] = True
            if pr is not None:
                item["prs"] = item["prs"] or [pr["number"]]
        elif event == "push":
            newest = newest_push.get((r.get("workflow_id"), r.get("head_branch")))
            if newest is not None and newest["id"] != r["id"]:
                item["class"] = "stuck-push"
                item["reason"] = f"newer push run {newest['id']} exists on {r.get('head_branch')}"
        if item["class"] == "live" and age_h >= stale_hours:
            item["class"] = "zombie"
            item["reason"] = f"{r.get('status')} for {age_h:.1f} h"
        out.append(item)
    return out


def apply_guards(items: list[dict], gh: GitHub | None, protect: re.Pattern,
                 skip_prs: set[str], skip_runs: set[int]) -> None:
    """Drop cancel flags the safety rules forbid; fetch jobs only when needed."""
    for it in items:
        tag = f"{it['repo']}#"
        if it["id"] in skip_runs or any(f"{tag}{n}" in skip_prs for n in it["prs"]):
            if it["cancel"] or it["class"] != "live":
                it["reason"] += " (off limits)"
            it["cancel"] = False
            it["class"] = "off-limits" if it["class"] != "live" else "live"
            continue
        needs_jobs = (it["cancel"] and protect.search(it["workflow"])) or it["class"] == "zombie"
        if needs_jobs and gh is not None:
            try:
                jobs = gh.get(f"/repos/{ORG}/{it['repo']}/actions/runs/{it['id']}/jobs?per_page=100")
            except RuntimeError as err:
                it["jobs"] = None
                it["reason"] += f"; jobs unreadable ({err})"
                if protect.search(it["workflow"]):
                    it["cancel"] = False
                continue
            it["jobs"] = jobs.get("total_count", 0)
            waiting = sorted({",".join(j.get("labels") or []) for j in jobs.get("jobs", [])
                              if j.get("status") == "queued"})
            if waiting:
                it["waiting_labels"] = waiting
            if it["cancel"] and protect.search(it["workflow"]) and it["jobs"] <= 1:
                it["cancel"] = False
                it["reason"] += "; kernel matrix not expanded yet, left alone"


def scan(gh: GitHub, repos: list[str], now: datetime, stale_hours: float) -> list[dict]:
    items: list[dict] = []
    for repo in repos:
        pulls = gh.get(f"/repos/{ORG}/{repo}/pulls?state=open&per_page=100")
        open_prs = {pr["number"]: pr for pr in pulls}
        runs: dict[int, dict] = {}
        for status in ACTIVE_STATUSES:
            data = gh.get(f"/repos/{ORG}/{repo}/actions/runs?status={status}&per_page=100")
            for r in data.get("workflow_runs", []):
                runs[r["id"]] = r
        active = list(runs.values())
        # An old-head run is superseded only if the current head has its own run
        # of that workflow. Completed head runs are not in the active lists, so
        # look them up, once per PR, only for PRs that have an old-head run.
        known = {(r.get("workflow_id"), r.get("head_sha")) for r in active}
        by_branch = {pr["head"]["ref"]: pr for pr in open_prs.values()}
        heads: set[str] = set()
        for r in active:
            pr = find_pr(r, open_prs, by_branch)
            if (r.get("event") == "pull_request" and pr is not None
                    and r.get("head_sha") != pr["head"]["sha"]
                    and (r.get("workflow_id"), pr["head"]["sha"]) not in known):
                heads.add(pr["head"]["sha"])
        for sha in sorted(heads):
            data = gh.get(f"/repos/{ORG}/{repo}/actions/runs?head_sha={sha}&per_page=100")
            known |= {(r.get("workflow_id"), sha) for r in data.get("workflow_runs", [])}
        items.extend(classify(repo, active, open_prs, now, stale_hours, known))
    return items


def render(items: list[dict]) -> str:
    if not items:
        return "No queued or running workflow runs."
    lines = []
    order = {"closed": 0, "superseded": 1, "zombie": 2, "stuck-push": 3, "off-limits": 4, "live": 5}
    for it in sorted(items, key=lambda i: (order.get(i["class"], 9), i["repo"], -i["age_h"])):
        prs = ",".join(f"#{n}" for n in it["prs"]) or "-"
        jobs = f" jobs={it['jobs']}" if "jobs" in it else ""
        act = f" -> {it['action']}" if it.get("action") else ""
        lines.append(f"{it['class']:<11} {it['repo']:<10} {it['workflow'][:34]:<34} {it['event']:<19} "
                     f"{prs:<6} {it['status']:<11} {it['age_h']:>6.1f}h{jobs}  {it['url']}"
                     f"{('  ' + it['reason']) if it['reason'] else ''}{act}")
    return "\n".join(lines)


def launchd_plist(args: list[str], interval: int) -> str:
    script = os.path.abspath(__file__)
    argv = "".join(f"<string>{a}</string>" for a in ["/usr/bin/python3", script, *args])
    log = os.path.expanduser("~/Library/Logs/stale-runs.log")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.ghostnet.stale-runs</string>
<key>ProgramArguments</key><array>{argv}</array>
<key>StartInterval</key><integer>{interval}</integer>
<key>StandardOutPath</key><string>{log}</string>
<key>StandardErrorPath</key><string>{log}</string>
</dict></plist>
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["launchd"]:
        rest = argv[1:]
        print(launchd_plist(rest, 900), end="")
        return 0
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--cancel", action="store_true", help="cancel runs classed closed/superseded")
    p.add_argument("--repos", default=",".join(REPOS), help="comma-separated repo names")
    p.add_argument("--stale-hours", type=float, default=3.0, help="age that makes a live run a zombie")
    p.add_argument("--max-cancel", type=int, default=10, help="cap on cancels per invocation")
    p.add_argument("--protect", default=DEFAULT_PROTECT,
                   help="regex of workflow names cancelled only after their matrix expands")
    p.add_argument("--skip-pr", action="append", default=[], help="REPO#N never touched (repeatable)")
    p.add_argument("--skip-run", action="append", type=int, default=[], help="run id never touched")
    p.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = p.parse_args(argv)

    token = read_token()
    if not token:
        print(f"No token: set STALE_RUNS_TOKEN or write one to {TOKEN_FILE}", file=sys.stderr)
        return 2
    gh = GitHub(token)
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    try:
        items = scan(gh, repos, utcnow(), args.stale_hours)
        apply_guards(items, gh, re.compile(args.protect), set(args.skip_pr), set(args.skip_run))
    except RuntimeError as err:
        print(f"error: {err}", file=sys.stderr)
        gh.save()
        return 1
    if args.cancel:
        budget = args.max_cancel
        for it in items:
            if not it["cancel"]:
                continue
            if budget <= 0:
                it["action"] = "skipped (max-cancel reached)"
                continue
            it["action"] = gh.cancel(it["repo"], it["id"])
            budget -= 1
    gh.save()
    if args.json:
        print(json.dumps({"at": utcnow().isoformat(), "api_calls": gh.calls,
                          "not_modified": gh.not_modified, "runs": items}, indent=1))
    else:
        print(f"{utcnow():%Y-%m-%d %H:%MZ}  api calls {gh.calls} (+{gh.not_modified} free 304s)")
        print(render(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
