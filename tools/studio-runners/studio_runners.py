#!/usr/bin/env python3
"""Tell jobs whether the Mac Studio's runner pools are online, and rescue runs stuck on them.

Same-repository CI runs on Justin's Mac Studio: the macOS runners on the host,
the ARC pods in the ci-k3s VM, and the OpenWrt builders. When the Studio is
off, those jobs wait 24 hours and GitHub cancels them, so no PR can merge
(docs #197 waited from 2026-11-22 until it was cancelled). This picks a
GitHub-hosted runner instead while a pool is offline, so hosted minutes are
spent only during an outage.

  pick    writes mac=, arc= and build= ("true" or "false") to $GITHUB_OUTPUT for
          the docs action .github/actions/studio-runners. Workflows route a job
          with `needs.studio.outputs.<pool> != 'false' && <self-hosted> || <hosted>`,
          so a missing or failed answer keeps today's self-hosted route.
          Never exits non-zero.
  rescue  cancels and re-runs this repository's runs that have waited 30+
          minutes on an offline pool, so they start again on hosted runners.
          Used by the hosted "Handle passing PRs" job. Only touches runs whose
          workflow has a "Studio runners" job (others would only queue on the
          Studio again). Runs GitHub already cancelled are merge_policy's
          rerun_cancelled() job.

How a pool counts as offline:

  * With RUNNER_READ_TOKEN (fine-grained PAT owned by ghostnet-labs with the
    organization permission "Self-hosted runners: Read-only"), the org runner
    list decides: mac and build are offline when none of their runners is
    online. ARC pods exist only while they run a job, so arc is online while
    any ARC pod or any macOS runner (same host) is online, and offline when
    neither is and an ARC job has waited 30+ minutes, or the macOS runners are
    offline too.
  * Without it (or when GitHub rejects it), this repository's own jobs decide:
    a pool is offline when one of its jobs has waited 30+ minutes, or was
    cancelled after waiting 30+ minutes without a runner, and no job on that
    pool got a runner after it was queued. Earlier attempts of a run count, so
    a run re-run after its jobs waited goes to the hosted fallback. A pool with no evidence of its own
    follows another Studio pool that is offline.

Python 3.9 standard library only (the Studio runs stock Python 3.9).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

API = "https://api.github.com"
ORG = "ghostnet-labs"
POOLS = ("mac", "arc", "build")
ARC_LABELS = frozenset({"ghostnet-linux-arm64", "ghostnet-linux-arm64-large", "ghostnet-gate"})
# Retired VMs stay listed as offline forever; they say nothing about the Studio.
RETIRED = (re.compile(r"^studio-ubuntu-"), re.compile(r"^gh-ubuntu"))
STUCK = timedelta(minutes=30)     # a queued job this old means its pool is not taking work
LOOKBACK = timedelta(hours=48)
SELECTOR_JOB = "studio runners"   # the caller job's name, lower case
MAX_ATTEMPTS = 3                  # never re-run a run more often than this
TOKEN_PAGE = "https://github.com/settings/personal-access-tokens"
SECRET_PAGE = f"https://github.com/organizations/{ORG}/settings/secrets/actions"


class HTTPError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class GitHub:
    def __init__(self, token: str, user_agent: str = "studio-runners"):
        self.token = token
        self.user_agent = user_agent
        self.calls = 0

    def request(self, method: str, path: str, body: Optional[dict] = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": self.user_agent,
        })
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as err:
            raise HTTPError(err.code, f"{method} {path}: HTTP {err.code}") from err
        except (urllib.error.URLError, OSError) as err:
            raise HTTPError(0, f"{method} {path}: {err}") from err
        return json.loads(raw) if raw else None

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, body: Optional[dict] = None):
        return self.request("POST", path, body or {})


def parse_time(value) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def pool_of(labels) -> Optional[str]:
    names = {str(label).lower() for label in (labels or [])}
    if names & ARC_LABELS:
        return "arc"
    if "openwrt-build" in names:
        return "build"
    if "self-hosted" in names and "macos" in names:
        return "mac"
    return None


def runner_names(runner: dict) -> List[str]:
    return [label.get("name", "") if isinstance(label, dict) else str(label)
            for label in runner.get("labels") or []]


def count_online(runners: List[dict]) -> Dict[str, int]:
    """Online runners per pool, leaving out retired registrations."""
    online = {pool: 0 for pool in POOLS}
    for r in runners:
        if any(p.search(r.get("name") or "") for p in RETIRED):
            continue
        pool = pool_of(runner_names(r))
        if pool and r.get("status") == "online":
            online[pool] += 1
    return online


def job_evidence(jobs: List[dict], now: datetime) -> Dict[str, dict]:
    """Per pool: when a job last got a runner, and the oldest unanswered wait.

    A wait is a job still queued for STUCK or longer, or one cancelled after
    waiting STUCK or longer without ever getting a runner (GitHub's 24-hour
    expiry, or the attempt the rescue cancelled before re-running it). Its time is when it was
    queued, so a runner that took any job on the pool after that clears it.
    """
    ev: Dict[str, dict] = {pool: {"alive": None, "waits": []} for pool in POOLS}
    for job in jobs:
        pool = pool_of(job.get("labels"))
        if pool is None:
            continue
        created = parse_time(job.get("created_at"))
        started = parse_time(job.get("started_at"))
        if job.get("runner_name") and started:
            alive = ev[pool]["alive"]
            ev[pool]["alive"] = started if alive is None or started > alive else alive
            continue
        if created is None:
            continue
        status, conclusion = job.get("status"), job.get("conclusion")
        if status in ("queued", "waiting", "pending") and now - created >= STUCK:
            ev[pool]["waits"].append({"since": created, "url": job.get("html_url"), "live": True})
        elif status == "completed" and conclusion == "cancelled":
            done = parse_time(job.get("completed_at"))
            if done and done - created >= STUCK:
                ev[pool]["waits"].append({"since": created, "url": job.get("html_url"), "live": False})
    return ev


def unanswered(pool_ev: dict) -> List[dict]:
    alive = pool_ev["alive"]
    return [w for w in pool_ev["waits"] if alive is None or alive < w["since"]]


def decide(online: Optional[Dict[str, int]], ev: Dict[str, dict]) -> Dict[str, dict]:
    """{pool: {"online": bool, "why": str}}. online is None when the runner list is unreadable."""
    out: Dict[str, dict] = {}
    if online is not None:
        out["mac"] = {"online": online["mac"] > 0,
                      "why": f"{online['mac']} macOS runner(s) online"}
        out["build"] = {"online": online["build"] > 0,
                        "why": f"{online['build']} OpenWrt build runner(s) online"}
        waits = [w for w in unanswered(ev["arc"]) if w["live"]]
        if online["arc"] > 0:
            out["arc"] = {"online": True, "why": f"{online['arc']} ARC pod(s) online"}
        elif online["mac"] == 0:
            out["arc"] = {"online": False, "why": "no ARC pod and no macOS runner online (same host)"}
        elif waits:
            out["arc"] = {"online": False, "why": f"no ARC pod online and a job has waited 30+ minutes: {waits[0]['url']}"}
        else:
            out["arc"] = {"online": True, "why": "macOS runners online (ARC runs on the same host)"}
        return out
    for pool in POOLS:
        waits = unanswered(ev[pool])
        if waits:
            w = min(waits, key=lambda x: x["since"])
            kind = "has waited 30+ minutes" if w["live"] else "was cancelled after waiting 30+ minutes"
            out[pool] = {"online": False, "why": f"a job {kind} without a runner: {w['url']}"}
        elif ev[pool]["alive"] is not None or ev[pool]["waits"]:
            out[pool] = {"online": True, "why": "its jobs are getting runners"}
        else:
            out[pool] = {"online": True, "why": "no recent jobs; assumed online"}
    # A pool with no evidence of its own follows the host it shares.
    no_evidence = {p for p in POOLS if ev[p]["alive"] is None and not ev[p]["waits"]}
    down = [p for p in POOLS if not out[p]["online"]]
    for pool in no_evidence:
        if down:
            out[pool] = {"online": False, "why": f"no recent jobs, and the Studio's {down[0]} pool is offline"}
    return out


def list_runs(gh: GitHub, repo: str, status: str, now: datetime, per_page: int) -> List[dict]:
    since = (now - LOOKBACK).strftime("%Y-%m-%dT%H:%M:%SZ")
    q = urllib.parse.urlencode({"status": status, "per_page": per_page, "created": f">={since}"})
    return (gh.get(f"/repos/{repo}/actions/runs?{q}") or {}).get("workflow_runs", [])


def run_jobs(gh: GitHub, repo: str, run_id) -> List[dict]:
    # filter=all: a re-run's earlier attempt shows the jobs that waited for a runner.
    return (gh.get(f"/repos/{repo}/actions/runs/{run_id}/jobs?filter=all&per_page=100") or {}).get("jobs", [])


def collect(gh: GitHub, repo: str, now: datetime, deep: bool) -> List[dict]:
    """Recent runs with their jobs attached. deep adds cancelled and successful runs.

    A push cancels the runs it supersedes within seconds, so in a busy repo the
    newest cancelled runs say nothing about the Studio. Cancelled runs are read
    30 at a time and only those that lasted 30+ minutes have their jobs fetched.
    """
    wanted = [("queued", 5), ("in_progress", 5)]
    if deep:
        wanted += [("cancelled", 30), ("success", 3)]
    runs: List[dict] = []
    seen = set()
    for status, per_page in wanted:
        for run in list_runs(gh, repo, status, now, per_page):
            if run["id"] in seen or (status == "cancelled" and not lasted(run, STUCK)):
                continue
            seen.add(run["id"])
            run["jobs"] = run_jobs(gh, repo, run["id"])
            runs.append(run)
    return runs


def lasted(run: dict, span: timedelta) -> bool:
    """Whether a run was open for at least span (unknown times count as yes)."""
    created, updated = parse_time(run.get("created_at")), parse_time(run.get("updated_at"))
    return created is None or updated is None or updated - created >= span


def read_runners(token: str, fetch: Optional[Callable] = None):
    """(online counts, problem). counts is None when the list could not be read."""
    if not token:
        return None, "RUNNER_READ_TOKEN is not set"
    gh = fetch or GitHub(token)
    runners: List[dict] = []
    try:
        for page in range(1, 6):
            data = gh.get(f"/orgs/{ORG}/actions/runners?per_page=100&page={page}") or {}
            batch = data.get("runners", [])
            runners += batch
            if len(batch) < 100:
                break
    except HTTPError as err:
        if err.code in (401, 403):
            return None, (f"GitHub rejected RUNNER_READ_TOKEN (HTTP {err.code}); renew it at {TOKEN_PAGE} "
                          f"and save it as RUNNER_READ_TOKEN at {SECRET_PAGE}")
        return None, f"could not read the runner list: {err}"
    return count_online(runners), None


def status(gh: GitHub, repo: str, runner_token: str, now: datetime, runner_fetch=None):
    online, problem = read_runners(runner_token, runner_fetch)
    runs = collect(gh, repo, now, deep=online is None)
    jobs = [job for run in runs for job in run.get("jobs", [])]
    return decide(online, job_evidence(jobs, now)), problem, runs


def write_outputs(verdict: Dict[str, dict], problem: Optional[str]) -> str:
    lines = [f"{pool}={'true' if verdict[pool]['online'] else 'false'}" for pool in POOLS]
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write("\n".join(lines) + "\n")
    down = [p for p in POOLS if not verdict[p]["online"]]
    summary = ["### Studio runners", "", "| Pool | Route | Why |", "|---|---|---|"]
    for pool in POOLS:
        route = "Studio" if verdict[pool]["online"] else "GitHub-hosted fallback"
        summary.append(f"| {pool} | {route} | {verdict[pool]['why']} |")
    if problem:
        summary += ["", f"Note: {problem}."]
    text = "\n".join(summary) + "\n"
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(text)
    if down:
        print(f"::warning title=Studio runners offline::{', '.join(down)} offline, so jobs that use "
              "them run on GitHub-hosted runners (hosted minutes in use). "
              + "; ".join(f"{p}: {verdict[p]['why']}" for p in down))
    if problem and problem != "RUNNER_READ_TOKEN is not set":
        print(f"::warning title=Studio runners check::{problem}")
    return "\n".join(lines)


def pick(repo: str, now: datetime, gh=None, runner_fetch=None) -> Dict[str, dict]:
    """Never raises: any failure keeps every pool on the Studio, as before this existed."""
    verdict = {pool: {"online": True, "why": "check failed; kept on the Studio"} for pool in POOLS}
    problem = None
    try:
        gh = gh or GitHub(os.environ.get("GITHUB_TOKEN", ""))
        verdict, problem, _ = status(gh, repo, os.environ.get("RUNNER_READ_TOKEN", ""), now, runner_fetch)
    except Exception as err:  # noqa: BLE001 - a crash must never block or skip a gate
        problem = f"studio runner check failed: {err}"
    print(write_outputs(verdict, problem))
    return verdict


def has_selector(run: dict) -> bool:
    return any((job.get("name") or "").strip().lower().startswith(SELECTOR_JOB) for job in run.get("jobs", []))


def offline_waits(run: dict, offline: set, now: datetime) -> List[dict]:
    """Jobs of a live run that have waited STUCK or longer on an offline pool."""
    found = []
    for job in run.get("jobs", []):
        if pool_of(job.get("labels")) not in offline or job.get("runner_name"):
            continue
        created = parse_time(job.get("created_at"))
        if created and job.get("status") in ("queued", "waiting", "pending") and now - created >= STUCK:
            found.append(job)
    return found


def wait_completed(gh: GitHub, repo: str, run_id, sleep=time.sleep, tries: int = 12) -> bool:
    for _ in range(tries):
        if (gh.get(f"/repos/{repo}/actions/runs/{run_id}") or {}).get("status") == "completed":
            return True
        sleep(5)
    return False


def rescue(gh: GitHub, repo: str, now: datetime, runner_token: str = "", dry_run: bool = False,
           limit: int = 5, runner_fetch=None, sleep=time.sleep) -> List[str]:
    verdict, problem, runs = status(gh, repo, runner_token, now, runner_fetch)
    if problem and problem != "RUNNER_READ_TOKEN is not set":
        print(f"::warning::{problem}")
    offline = {p for p in POOLS if not verdict[p]["online"]}
    done: List[str] = []
    if not offline:
        print("Studio runner pools are online; nothing to rescue.")
        return done
    for run in runs:
        if len(done) >= limit:
            break
        if not has_selector(run) or (run.get("run_attempt") or 1) >= MAX_ATTEMPTS:
            continue
        url = run.get("html_url") or str(run["id"])
        if run.get("status") not in ("queued", "in_progress", "waiting", "pending"):
            continue
        if not offline_waits(run, offline, now):
            continue
        if dry_run:
            done.append(f"would cancel and re-run {url}")
            continue
        gh.post(f"/repos/{repo}/actions/runs/{run['id']}/cancel")
        if not wait_completed(gh, repo, run["id"], sleep=sleep):
            # merge_policy's rerun_cancelled() picks it up on a later sweep.
            print(f"::warning::{url} did not finish cancelling; a later sweep re-runs it")
            continue
        try:
            gh.post(f"/repos/{repo}/actions/runs/{run['id']}/rerun")
        except HTTPError as err:
            print(f"::warning::could not re-run {url}: {err}")
            continue
        done.append(f"re-ran {url} on GitHub-hosted runners")
    for line in done:
        print(line)
    if not done:
        print(f"{', '.join(sorted(offline))} offline; no run with a Studio runners job is waiting on them.")
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("pick", "rescue"))
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/name")
    ap.add_argument("--dry-run", action="store_true", help="rescue: say what would be re-run")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    if args.mode == "pick":
        pick(args.repo, now)
        return 0
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token or not args.repo:
        print("::warning::rescue needs GITHUB_TOKEN and --repo")
        return 0
    try:
        rescue(GitHub(token), args.repo, now, os.environ.get("RUNNER_READ_TOKEN", ""), args.dry_run)
    except HTTPError as err:
        print(f"::warning::studio runner rescue stopped: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
