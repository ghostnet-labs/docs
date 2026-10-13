#!/usr/bin/env python3
"""Builder and runner status page for the ghostnet-labs GitHub org.

One file, Python 3 standard library only. Two modes:

  serve  Dashboard. Polls the GitHub API with a read-only token, pulls machine
         stats from each machine's agent, and serves an auto-refreshing page.
  agent  Tiny read-only stats endpoint for one Mac (RAM, disk, load, Lima VMs).
         It runs a fixed set of read-only commands and takes no input.

Examples:
  python3 runner_status.py serve --port 8090
  python3 runner_status.py agent --port 8091
  python3 runner_status.py serve --demo          # fake data, no token needed
  python3 runner_status.py launchd serve         # print a LaunchAgent plist

See README.md next to this file for token and install steps.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API = "https://api.github.com"
DEFAULT_ORG = "ghostnet-labs"
TOKEN_FILE = os.path.expanduser("~/.config/runner-status/token")
PUSH_KEY_FILE = os.path.expanduser("~/.config/runner-status/push-key")
PUSH_MAX_BYTES = 64 * 1024
PUSH_STALE_SECONDS = 180  # a pushing Mac counts as silent after this long
CONFIG_FILE = os.path.expanduser("~/.config/runner-status/config.json")

# Machines shown on the page. A runner belongs to the first machine whose
# pattern matches its name; anything unmatched is listed under "Other runners"
# so nothing is hidden. "agent" is "local" (stats read in-process), "push"
# (that Mac runs `runner_status.py push` and sends its stats here, so it needs
# no listener of its own), or a URL of an agent started with
# `runner_status.py agent`.
DEFAULT_CONFIG = {
    "org": DEFAULT_ORG,
    "poll_seconds": 60,
    "queued_alert_minutes": 20,
    "hosted_stall_minutes": 15,
    "disk_paths": ["/", "/Volumes/NAS"],
    "machines": [
        {"name": "Mac Studio", "agent": "local",
         "runner_pattern": r"(?i)studio|gh-ubuntu|gh-build",
         # Lima VM name -> pattern for the runners that live inside it.
         "vms": {"gh-ubuntu": r"(?i)^gh-ubuntu", "gh-build": r"(?i)^studio-build-1$",
                 "gh-build-2": r"(?i)^studio-build-2$"}},
        {"name": "MacBook Pro", "agent": "push",
         "runner_pattern": r"(?i)macbook|mac-dev|\bdev\b",
         "vms": {"gh-build": r"(?i)^macbook-pro-build"}},
        {"name": "R620", "agent": "", "runner_pattern": r"(?i)r620"},
    ],
}

API_WORKERS = 6  # parallel GitHub calls; bounded to stay gentle on the API
ERROR_RETRY_SECONDS = 15  # retry sooner while GitHub can't be read at all (e.g. a new token)
ETAG_CACHE_MAX = 500  # cached responses kept for conditional requests
LOW_QUOTA_FRACTION = 0.2  # below this share of the hourly limit, poll slowly
LOW_QUOTA_POLL_SECONDS = 300
HISTORY_POINTS = 120  # sparkline samples kept per series (1 h at the spacing below)
HISTORY_SPACING = 30  # seconds between kept samples
PULLS_RETRY_SECONDS = 600  # after a refused PR list, wait this long before asking again

HOSTED_LABELS = re.compile(r"^(ubuntu|windows|macos)-", re.I)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_minutes(value: str | None, now: datetime) -> float | None:
    ts = parse_ts(value)
    if ts is None:
        return None
    return max(0.0, (now - ts).total_seconds() / 60)


def fmt_bytes(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def load_config(path: str | None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = path or CONFIG_FILE
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    return cfg


def read_token() -> tuple[str | None, str]:
    """Return (token, where it came from). The dedicated file wins over a
    stray GITHUB_TOKEN in the environment, which is often some other token."""
    if os.environ.get("RUNNER_STATUS_TOKEN", "").strip():
        return os.environ["RUNNER_STATUS_TOKEN"].strip(), "RUNNER_STATUS_TOKEN"
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            token = fh.read().strip()
        if token:
            return token, TOKEN_FILE
        return None, f"{TOKEN_FILE} (empty)"
    if os.environ.get("GITHUB_TOKEN", "").strip():
        return os.environ["GITHUB_TOKEN"].strip(), "GITHUB_TOKEN"
    return None, f"{TOKEN_FILE} (missing)"


def read_push_key() -> str | None:
    """Shared key for pushed stats. The dashboard refuses pushes without it."""
    if os.path.exists(PUSH_KEY_FILE):
        with open(PUSH_KEY_FILE, encoding="utf-8") as fh:
            return fh.read().strip() or None
    return None


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _text(value, limit: int = 128) -> str | None:
    return str(value)[:limit] if isinstance(value, (str, int, float)) else None


def sanitize_stats(data: dict) -> dict:
    """Keep only the known stats fields, typed and size-bounded, from a push."""
    mem = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    load = data.get("load") if isinstance(data.get("load"), list) else None
    out = {
        "host": _text(data.get("host")), "os": _text(data.get("os")),
        "cores": _num(data.get("cores")), "collected_at": _text(data.get("collected_at")),
        "uptime_s": _num(data.get("uptime_s")),
        "runner_processes": _num(data.get("runner_processes")),
        "load": [_num(x) or 0.0 for x in load[:3]] if load else None,
        "memory": {k: _num(mem.get(k)) for k in ("total", "used", "compressed")},
        "disks": [{"path": _text(d.get("path")), **{k: _num(d.get(k)) or 0
                                                     for k in ("total", "used", "free")}}
                  for d in (data.get("disks") or [])[:8] if isinstance(d, dict)],
        "vms": None,
    }
    if isinstance(data.get("vms"), list):
        out["vms"] = [{"name": _text(v.get("name")), "status": _text(v.get("status")),
                       **{k: _num(v.get(k)) for k in ("cpus", "memory", "disk")}}
                      for v in data["vms"][:16] if isinstance(v, dict)]
    return out


def token_kind(token: str) -> str:
    """Name the token type from its prefix, never showing the token itself."""
    kinds = {"github_pat_": "fine-grained personal token", "ghp_": "classic personal token",
             "gho_": "gh CLI / OAuth token", "ghs_": "GitHub Actions or app token (short-lived)",
             "ghu_": "GitHub app user token"}
    return next((v for k, v in kinds.items() if token.startswith(k)), "unrecognised token format")


class GitHubError(OSError):
    """An API failure with a plain-language cause."""


def explain_http_error(code: int, message: str, path: str, source: str, kind: str) -> str:
    low = message.lower()
    if code == 401:
        return (f"token rejected by GitHub (401 {message or 'Bad credentials'}). The {kind} in "
                f"{source} is wrong, expired or revoked; make a new one (README step 1).")
    if "fine-grained personal access token" in low and "forbid" in low:
        return ("the ghostnet-labs org does not allow fine-grained tokens: org Settings > "
                "Personal access tokens > allow access via fine-grained tokens.")
    if "pending" in low or "approv" in low:
        return ("the token is waiting for org-owner approval: approve it at "
                "https://github.com/organizations/ghostnet-labs/settings/personal-access-token-requests")
    if code in (403, 404) and ("not accessible" in low or code == 404):
        if "/actions/runner" in path:
            need = "Organization permissions > Self-hosted runners: Read-only"
        elif "/billing" in path:
            need = "org billing access (optional)"
        elif path.startswith("/orgs/") and path.endswith("/repos"):
            need = "Resource owner ghostnet-labs and Repository access: All repositories"
        else:
            need = "Repository permissions > Actions: Read-only, on All repositories"
        return (f"missing permission ({code} {message}). The {kind} in {source} needs: {need}. "
                "Edit the token, add it, and the page picks it up on the next poll.")
    if code in (403, 429) and "rate limit" in low:
        return f"GitHub rate limit hit ({code}); it clears within the hour."
    return f"HTTP {code}: {message}"


# --------------------------------------------------------------------------
# Machine stats (agent side)
# --------------------------------------------------------------------------

def _run(cmd: list[str], timeout: float = 5) -> str | None:
    exe = shutil.which(cmd[0]) or next(
        (p for p in (f"/opt/homebrew/bin/{cmd[0]}", f"/usr/local/bin/{cmd[0]}",
                     f"/usr/sbin/{cmd[0]}", f"/usr/bin/{cmd[0]}") if os.path.exists(p)),
        None)
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True,
                             timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def parse_vm_stat(text: str, total: int) -> dict:
    """Turn macOS `vm_stat` output into used/available bytes."""
    page = 16384
    m = re.search(r"page size of (\d+) bytes", text)
    if m:
        page = int(m.group(1))
    pages = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        v = v.strip().rstrip(".")
        if v.isdigit():
            pages[k.strip().strip('"')] = int(v)
    used = (pages.get("Pages active", 0) + pages.get("Pages wired down", 0)
            + pages.get("Pages occupied by compressor", 0)) * page
    return {"total": total, "used": min(used, total) if total else used,
            "compressed": pages.get("Pages occupied by compressor", 0) * page}


def parse_meminfo(text: str) -> dict:
    vals = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        parts = v.split()
        if parts and parts[0].isdigit():
            vals[k] = int(parts[0]) * 1024
    total = vals.get("MemTotal", 0)
    return {"total": total, "used": total - vals.get("MemAvailable", 0), "compressed": 0}


def parse_lima(text: str) -> list[dict]:
    """`limactl list --json` prints one JSON object per line."""
    vms = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        items = obj if isinstance(obj, list) else [obj]
        for vm in items:
            vms.append({"name": vm.get("name"), "status": vm.get("status"),
                        "cpus": vm.get("cpus"), "memory": vm.get("memory"),
                        "disk": vm.get("disk")})
    return vms


def collect_stats(disk_paths: list[str]) -> dict:
    stats: dict = {"host": platform.node(), "os": platform.system(),
                   "cores": os.cpu_count(), "collected_at": utcnow().isoformat()}
    try:
        stats["load"] = list(os.getloadavg())
    except OSError:
        stats["load"] = None
    if platform.system() == "Darwin":
        total = int((_run(["sysctl", "-n", "hw.memsize"]) or "0").strip() or 0)
        vm = _run(["vm_stat"])
        stats["memory"] = parse_vm_stat(vm, total) if vm else {"total": total}
        boot = _run(["sysctl", "-n", "kern.boottime"]) or ""
        m = re.search(r"sec = (\d+)", boot)
        stats["uptime_s"] = int(time.time()) - int(m.group(1)) if m else None
    elif os.path.exists("/proc/meminfo"):
        with open("/proc/meminfo", encoding="utf-8") as fh:
            stats["memory"] = parse_meminfo(fh.read())
        with open("/proc/uptime", encoding="utf-8") as fh:
            stats["uptime_s"] = int(float(fh.read().split()[0]))
    disks = []
    for path in disk_paths:
        if os.path.exists(path):
            du = shutil.disk_usage(path)
            disks.append({"path": path, "total": du.total, "used": du.used, "free": du.free})
    stats["disks"] = disks
    lima = _run(["limactl", "list", "--json"], timeout=10)
    stats["vms"] = parse_lima(lima) if lima else None
    ps = _run(["ps", "-axo", "command"]) or ""
    stats["runner_processes"] = sum(1 for line in ps.splitlines() if "Runner.Listener" in line)
    return stats


# --------------------------------------------------------------------------
# GitHub polling (dashboard side)
# --------------------------------------------------------------------------

class GitHub:
    """Read-only API client. Sends If-None-Match with the last ETag for each
    URL: GitHub answers 304 for unchanged data and does not count a 304
    against the rate limit, so idle repos cost nothing per poll."""

    def __init__(self, token: str, source: str = "environment"):
        self.token = token
        self.source = source
        self.kind = token_kind(token)
        self.mu = threading.Lock()  # protects the fields below (calls run in parallel)
        self.rate_remaining: int | None = None
        self.rate_limit: int | None = None
        self.rate_reset: int | None = None
        self.etags: OrderedDict[str, tuple[str, object]] = OrderedDict()  # url -> (etag, body)
        self.billed: deque[float] = deque(maxlen=20000)  # times of calls that counted
        self.free = 0  # 304 answers since start
        self.pulls_denied: dict[str, float] = {}  # repo -> time its PR list was refused

    def _note_rate(self, headers) -> None:
        with self.mu:
            for attr, name in (("rate_remaining", "X-RateLimit-Remaining"),
                               ("rate_limit", "X-RateLimit-Limit"),
                               ("rate_reset", "X-RateLimit-Reset")):
                value = headers.get(name) if headers else None
                if value is not None and value.isdigit():
                    setattr(self, attr, int(value))

    def usage(self) -> dict:
        """Rate-limit numbers for the page footer."""
        cutoff = time.time() - 3600
        with self.mu:
            while self.billed and self.billed[0] < cutoff:
                self.billed.popleft()
            return {"remaining": self.rate_remaining, "limit": self.rate_limit,
                    "reset": self.rate_reset, "used_by_page_last_hour": len(self.billed),
                    "free_304s": self.free}

    def get(self, path: str, params: dict | None = None):
        url = path if path.startswith("http") else API + path
        if params:
            url += ("&" if "?" in url else "?") + "&".join(f"{k}={v}" for k, v in params.items())
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ghostnet-runner-status",
        }
        with self.mu:
            cached = self.etags.get(url)
        if cached:
            headers["If-None-Match"] = cached[0]
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                self._note_rate(resp.headers)
                body = json.loads(resp.read().decode())
                etag = resp.headers.get("ETag")
            with self.mu:
                self.billed.append(time.time())
                if etag:
                    self.etags[url] = (etag, body)
                    self.etags.move_to_end(url)
                    while len(self.etags) > ETAG_CACHE_MAX:
                        self.etags.popitem(last=False)
            return body
        except urllib.error.HTTPError as exc:
            self._note_rate(exc.headers)
            if exc.code == 304 and cached:
                with self.mu:
                    self.free += 1
                    self.etags.move_to_end(url)
                return cached[1]
            with self.mu:
                self.billed.append(time.time())
            try:
                message = json.loads(exc.read().decode()).get("message", "")
            except (OSError, ValueError, AttributeError):
                message = exc.reason or ""
            short = url.removeprefix(API).split("?")[0]
            raise GitHubError(explain_http_error(exc.code, str(message), short, self.source,
                                                 self.kind)) from exc


class History:
    """Small bounded time series behind the page's sparklines: CPU and RAM
    per machine and the queued/running job counts. In memory only; one
    sample per HISTORY_SPACING seconds, HISTORY_POINTS samples per series."""

    def __init__(self):
        self.mu = threading.Lock()  # protects the fields below
        self.series: dict[str, deque] = {}  # key -> deque of (t, *values)
        self.last: dict[str, float] = {}  # key -> time of the newest sample

    def add(self, key: str, t: float, *values: float) -> None:
        with self.mu:
            if t - self.last.get(key, 0) < HISTORY_SPACING:
                return
            self.last[key] = t
            self.series.setdefault(key, deque(maxlen=HISTORY_POINTS)).append(
                (int(t), *(round(v, 3) for v in values)))

    def record(self, state: dict, t: float) -> None:
        for m in state.get("machines", []):
            st = m.get("stats") or {}
            mem, load, cores = st.get("memory") or {}, st.get("load"), st.get("cores")
            if st.get("error") or not (mem.get("total") and load and cores):
                continue
            self.add("machine:" + m["name"], t, load[0] / cores, (mem.get("used") or 0) / mem["total"])
        if not state.get("loading") and not state.get("errors"):
            c = state.get("counts") or {}
            self.add("jobs", t, c.get("queued", 0), c.get("running", 0))

    def export(self) -> dict:
        out: dict = {"machines": {}, "jobs": None}
        with self.mu:
            items = [(k, list(v)) for k, v in self.series.items()]
        for key, rows in items:
            cols = list(zip(*rows))
            if key == "jobs":
                out["jobs"] = {"t": cols[0], "queued": cols[1], "running": cols[2]}
            else:
                out["machines"][key.removeprefix("machine:")] = {
                    "t": cols[0], "cpu": cols[1], "mem": cols[2]}
        return out


class Poller:
    """Polls GitHub and agents on one background thread; the page reads a copy."""

    def __init__(self, cfg: dict, gh: GitHub | None, demo: bool = False,
                 token_source: str = ""):
        self.cfg = cfg
        self.gh = gh
        self.token_source = token_source
        self.demo = demo
        self.stop = threading.Event()
        self.mu = threading.Lock()  # protects the fields below
        self.state: dict = build_state({"loading": True}, cfg, utcnow())
        self.slow: dict = {}
        self.slow_at = 0.0
        self.last: dict = {}
        self.pushed: dict = {}  # name -> (stats, received unix time); guarded by mu
        self.last_raw: dict | None = None  # guarded by mu
        self.history = History()
        if demo:
            demo_history(self.history, cfg)

    def snapshot(self) -> dict:
        with self.mu:
            return self.state

    def poll_once(self) -> dict:
        """One poll. Publishes partial results as they arrive so the page
        paints within a couple of seconds instead of after the whole sweep."""
        raw = demo_raw() if self.demo else self.fetch(self.publish)
        self.publish(raw)
        return raw

    def publish(self, raw: dict) -> None:
        state = build_state(raw, self.cfg, utcnow())
        self.history.record(state, time.time())
        state["history"] = self.history.export()
        with self.mu:
            self.state = state
            self.last_raw = raw

    def accept_push(self, name: str, stats: dict) -> None:
        """Store stats pushed by a Mac and show them right away."""
        with self.mu:
            self.pushed[name] = (stats, time.time())
            raw = dict(self.last_raw) if self.last_raw else None
        if raw is not None:
            raw["machine_stats"] = {**raw.get("machine_stats", {}), name: stats}
            self.publish(raw)

    def push_names(self) -> set[str]:
        return {m["name"] for m in self.cfg["machines"] if m.get("agent") == "push"}

    def fetch(self, publish=lambda raw: None) -> dict:
        org = self.cfg["org"]
        errors: list[str] = []
        raw: dict = {"errors": errors}
        # Re-read the token every poll so replacing the file needs no restart.
        token, self.token_source = read_token()
        if not token:
            self.gh = None
        elif self.gh is None or self.gh.token != token:
            self.gh = GitHub(token, self.token_source)
        gh = self.gh
        if gh is None:
            errors.append(f"No GitHub token: {self.token_source}. Put a read-only token there "
                          "(README step 1).")
        else:
            raw["token"] = f"{gh.kind} from {gh.source}"
            try:
                raw["runners"] = gh.get(f"/orgs/{org}/actions/runners",
                                        {"per_page": 100}).get("runners", [])
            except (urllib.error.URLError, OSError, ValueError) as exc:
                errors.append(f"Runners: {exc}")
            if self.slow:
                raw.update(self.slow)  # last sweep's repos/groups/workflows
        raw["machine_stats"] = self.fetch_agents(errors)
        if gh is None or errors:
            raw["blocked"] = True  # GitHub unreadable: the loop retries soon
            if gh is not None:
                raw["rate"] = gh.usage()
            return raw
        if "jobs" not in self.last:
            raw["loading"] = True  # first sweep: show runners + machines now
            publish(dict(raw))
        else:
            raw["jobs"] = self.last["jobs"]
        # Slow-changing data (repos, groups, workflows, billing) every 10 min.
        stale = time.time() - self.slow_at > 600 or not self.slow
        if stale:
            self.slow.update(self.fetch_repos_groups(gh, org, errors))
            raw.update(self.slow)
        raw["jobs"] = self.fetch_jobs(gh, org, raw.get("repos", []), errors)
        raw.pop("loading", None)
        self.last = {"jobs": raw["jobs"]}
        if stale:
            publish(dict(raw))
            self.slow.update(self.fetch_workflows_billing(gh, org, raw.get("repos", [])))
            self.slow_at = time.time()
            raw.update(self.slow)
        raw["rate"] = gh.usage()  # takes gh.mu itself; never call it holding gh.mu
        return raw

    @staticmethod
    def fetch_repos_groups(gh: GitHub, org: str, errors: list[str]) -> dict:
        out: dict = {"repos": [], "groups": {}}
        try:
            repos = gh.get(f"/orgs/{org}/repos", {"per_page": 100, "type": "all"})
            out["repos"] = [r["name"] for r in repos if not r.get("archived")]
        except (urllib.error.URLError, OSError, ValueError) as exc:
            errors.append(f"Repos: {exc}")
        try:
            groups = gh.get(f"/orgs/{org}/actions/runner-groups").get("runner_groups", [])
            for g in groups:
                members = gh.get(f"/orgs/{org}/actions/runner-groups/{g['id']}/runners",
                                 {"per_page": 100}).get("runners", [])
                for r in members:
                    out["groups"][r["id"]] = g["name"]
        except (urllib.error.URLError, OSError, ValueError):
            pass  # needs org runner read; the runner list still works without it
        return out

    @staticmethod
    def fetch_workflows_billing(gh: GitHub, org: str, repos: list[str]) -> dict:
        def disabled(repo: str) -> list[dict]:
            try:
                wfs = gh.get(f"/repos/{org}/{repo}/actions/workflows",
                             {"per_page": 100}).get("workflows", [])
            except (urllib.error.URLError, OSError, ValueError):
                return []
            return [{"repo": repo, "name": wf.get("name"), "state": wf.get("state"),
                     "url": wf.get("html_url")}
                    for wf in wfs if wf.get("state", "active") != "active"]

        with ThreadPoolExecutor(max_workers=API_WORKERS) as pool:
            found = [wf for chunk in pool.map(disabled, repos) for wf in chunk]
        try:
            billing = gh.get(f"/orgs/{org}/settings/billing/actions")
        except (urllib.error.URLError, OSError, ValueError):
            billing = None  # needs billing access; the stall heuristic covers it
        return {"disabled_workflows": found, "billing": billing}

    @staticmethod
    def fetch_jobs(gh: GitHub, org: str, repos: list[str], errors: list[str]) -> list[dict]:
        """Active jobs across repos, fetched by a small bounded pool."""
        def runs_for(task):
            repo, status = task
            try:
                runs = gh.get(f"/repos/{org}/{repo}/actions/runs",
                              {"status": status, "per_page": 50}).get("workflow_runs", [])
            except (urllib.error.URLError, OSError, ValueError) as exc:
                return [], f"{repo} runs: {exc}"
            return [(repo, r) for r in runs], None

        def jobs_for(item):
            repo, run = item
            try:
                rjobs = gh.get(run["jobs_url"], {"per_page": 100}).get("jobs", [])
            except (urllib.error.URLError, OSError, ValueError):
                return []
            out = []
            for j in rjobs:
                if j.get("status") in ("queued", "in_progress", "waiting", "pending"):
                    j["repo"] = repo
                    j["workflow"] = run.get("name")
                    j["branch"] = run.get("head_branch")
                    j["prs"] = [pr["number"] for pr in run.get("pull_requests") or []
                                if isinstance(pr, dict) and "number" in pr]
                    if not j["prs"]:
                        j["prs"] = open_prs.get((repo, head_key(run)), [])
                    out.append(j)
            return out

        def head_key(run):
            head_repo = (run.get("head_repository") or {}).get("full_name")
            return f"{head_repo}:{run.get('head_branch')}"

        def pulls_for(repo):
            # The runs list often leaves pull_requests empty, so match open PRs
            # by head repo and branch. ETag caching makes unchanged lists free.
            with gh.mu:
                denied_at = gh.pulls_denied.get(repo, 0)
            if time.time() - denied_at < PULLS_RETRY_SECONDS:
                return {}  # token lacks "Pull requests: Read"; don't pay for a 403 every poll
            try:
                pulls = gh.get(f"/repos/{org}/{repo}/pulls", {"state": "open", "per_page": 100})
            except (urllib.error.URLError, OSError, ValueError):
                with gh.mu:
                    gh.pulls_denied[repo] = time.time()
                return {}
            found: dict = {}
            for pr in pulls if isinstance(pulls, list) else []:
                head = pr.get("head") or {}
                key = (repo, f"{(head.get('repo') or {}).get('full_name')}:{head.get('ref')}")
                found.setdefault(key, []).append(pr["number"])
            return found

        tasks = [(repo, st) for repo in repos for st in ("queued", "in_progress")]
        with ThreadPoolExecutor(max_workers=API_WORKERS) as pool:
            runs = []
            for found, err in pool.map(runs_for, tasks):
                runs.extend(found)
                if err and err not in errors:
                    errors.append(err)
            lookup = sorted({repo for repo, run in runs if not run.get("pull_requests")
                             and str(run.get("event", "")).startswith("pull_request")})
            open_prs: dict = {}
            for found in pool.map(pulls_for, lookup):
                open_prs.update(found)
            return [j for chunk in pool.map(jobs_for, runs) for j in chunk]

    def fetch_agents(self, errors: list[str]) -> dict:
        stats = {}
        for m in self.cfg["machines"]:
            agent = m.get("agent")
            if not agent:
                continue
            if agent == "local":
                stats[m["name"]] = collect_stats(self.cfg["disk_paths"])
                continue
            if agent == "push":
                with self.mu:
                    got = self.pushed.get(m["name"])
                if got is None:
                    stats[m["name"]] = {"error": "no stats pushed yet (runner_status.py push "
                                                 "not running on that Mac?)"}
                elif time.time() - got[1] > PUSH_STALE_SECONDS:
                    stats[m["name"]] = {"error": f"no stats pushed for {int(time.time() - got[1])}s"}
                else:
                    stats[m["name"]] = got[0]
                continue
            try:
                with urllib.request.urlopen(agent.rstrip("/") + "/stats", timeout=5) as resp:
                    stats[m["name"]] = json.loads(resp.read().decode())
            except (urllib.error.URLError, OSError, ValueError) as exc:
                stats[m["name"]] = {"error": str(exc)}
        return stats


def build_state(raw: dict, cfg: dict, now: datetime) -> dict:
    """Pure function: raw API data in, page model out. Tested directly."""
    groups = raw.get("groups", {})
    machines = [{"name": m["name"], "pattern": re.compile(m["runner_pattern"]),
                 "configured_agent": bool(m.get("agent")), "runners": [],
                 "stats": raw.get("machine_stats", {}).get(m["name"])}
                for m in cfg["machines"]]
    other = {"name": "Other runners", "runners": [], "stats": None, "configured_agent": False}
    org = cfg["org"]
    jobs = []
    for j in raw.get("jobs", []):
        labels = j.get("labels", [])
        hosted = any(HOSTED_LABELS.match(lbl) for lbl in labels) and "self-hosted" not in labels
        since = j.get("started_at") if j.get("status") == "in_progress" else j.get("created_at")
        prs = [{"number": n, "url": f"https://github.com/{org}/{j.get('repo')}/pull/{n}"}
               for n in j.get("prs") or []]
        jobs.append({"repo": j.get("repo"), "workflow": j.get("workflow"), "name": j.get("name"),
                     "status": j.get("status"), "labels": labels, "hosted": hosted,
                     "runner": j.get("runner_name"), "branch": j.get("branch"), "prs": prs,
                     "url": j.get("html_url"), "age_min": age_minutes(since, now)})
    jobs.sort(key=lambda j: (j["status"] != "queued", -(j["age_min"] or 0)))
    # What each runner is working on, from the job list already fetched (no extra calls).
    by_runner = {j["runner"]: j for j in jobs if j["runner"] and j["status"] == "in_progress"}
    for r in sorted(raw.get("runners", []), key=lambda r: r.get("name", "")):
        status = "offline" if r.get("status") != "online" else ("busy" if r.get("busy") else "idle")
        runner = {"name": r.get("name"), "status": status, "os": r.get("os"),
                  "labels": [lbl["name"] for lbl in r.get("labels", [])],
                  "group": groups.get(r.get("id"), "unknown"),
                  "job": by_runner.get(r.get("name"))}
        target = next((m for m in machines if m["pattern"].search(runner["name"] or "")), other)
        target["runners"].append(runner)
    shown = [m for m in machines if m["runners"] or m["stats"] or m["name"] == "Mac Studio"]
    if other["runners"]:
        shown.append(other)
    vm_cfg = {m["name"]: m.get("vms", {}) for m in cfg["machines"]}
    for m in shown:
        m.pop("pattern", None)
        st = m.get("stats") or {}
        if st.get("vms"):
            vms = []  # copies: stats dicts may be shared with the push thread
            for vm in st["vms"]:
                pattern = vm_cfg.get(m["name"], {}).get(vm.get("name"))
                rx = re.compile(pattern) if pattern else None
                inside = [r for r in m["runners"] if rx and rx.search(r["name"] or "")]
                vms.append({**vm, "runners": [r["name"] for r in inside],
                            "jobs": [r["job"] for r in inside if r["job"]]})
            m["stats"] = {**st, "vms": vms}
        counts = {"idle": 0, "busy": 0, "offline": 0}
        for r in m["runners"]:
            counts[r["status"]] += 1
        m["counts"] = counts


    alerts = [{"level": "crit", "text": f"GitHub: {e}"}
              for e in dict.fromkeys(raw.get("errors", []))]
    offline = [r["name"] for m in shown for r in m["runners"] if r["status"] == "offline"]
    if offline:
        alerts.append({"level": "warn", "text": f"Offline runners: {', '.join(offline)}"})
    stuck = [j for j in jobs if j["status"] == "queued"
             and (j["age_min"] or 0) >= cfg["queued_alert_minutes"]]
    if stuck:
        alerts.append({"level": "warn",
                       "text": f"{len(stuck)} job(s) queued for {cfg['queued_alert_minutes']}+ min"})
    hosted_stuck = [j for j in stuck if j["hosted"]
                    and (j["age_min"] or 0) >= cfg["hosted_stall_minutes"]]
    if hosted_stuck:
        alerts.append({"level": "crit", "text":
                       f"GitHub-hosted runners look stalled: {len(hosted_stuck)} hosted job(s) "
                       "waiting. Usually the Actions minutes or spending limit."})
    for wf in raw.get("disabled_workflows", []):
        alerts.append({"level": "warn", "text":
                       f"Workflow disabled: {wf['repo']} / {wf['name']} ({wf['state']})",
                       "url": wf.get("url")})
    rate = raw.get("rate") or {}
    if rate.get("remaining") is not None and rate.get("limit") and \
            rate["remaining"] < rate["limit"] * LOW_QUOTA_FRACTION:
        alerts.append({"level": "warn", "text":
                       f"GitHub API quota low: {rate['remaining']} of {rate['limit']} calls left "
                       f"this hour; polling every {LOW_QUOTA_POLL_SECONDS // 60} min until it resets"})
    billing = raw.get("billing")
    if billing and billing.get("included_minutes"):
        used = billing.get("total_minutes_used", 0)
        pct = 100 * used / billing["included_minutes"]
        if pct >= 90:
            alerts.append({"level": "crit" if pct >= 100 else "warn",
                           "text": f"Actions minutes {used:.0f} of {billing['included_minutes']} "
                                   f"({pct:.0f}%) used this month"})
    for m in shown:
        st = m.get("stats") or {}
        if st.get("error"):
            alerts.append({"level": "warn", "text": f"{m['name']} stats missing: {st['error']}"})
        for d in st.get("disks", []) or []:
            if d["total"] and d["free"] / d["total"] < 0.10:
                alerts.append({"level": "warn", "text":
                               f"{m['name']} disk {d['path']} low: {fmt_bytes(d['free'])} free"})
        for vm in st.get("vms") or []:
            if vm.get("status") != "Running":
                alerts.append({"level": "warn", "text":
                               f"{m['name']} VM {vm['name']} is {vm.get('status')}"})

    return {"updated": now.isoformat(), "org": cfg["org"], "machines": shown, "jobs": jobs,
            "alerts": alerts, "billing": billing, "rate": raw.get("rate"),
            "token": raw.get("token"), "loading": bool(raw.get("loading")),
            "errors": list(dict.fromkeys(raw.get("errors", []))),
            "counts": {"queued": sum(j["status"] == "queued" for j in jobs),
                       "running": sum(j["status"] == "in_progress" for j in jobs)}}


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Runner Status</title>
<script>(function(){var m="auto";try{m=localStorage.getItem("rs-theme")||"auto"}catch(e){}var q=matchMedia("(prefers-color-scheme:dark)");function a(){document.documentElement.setAttribute("data-theme",m==="auto"?(q.matches?"dark":"light"):m)}window.rsTheme=function(x){m=x;a()};a();q.addEventListener&&q.addEventListener("change",a)})()</script>
<style>
:root{--bg:#f4f5f7;--card:#fff;--card2:#f7f8fa;--text:#14171c;--muted:#566070;--faint:#5c6471;--line:#e1e4ea;--track:#e6e9ee;
--ok:#16704a;--okbg:#e4f3ea;--warn:#8f5400;--warnbg:#fff3d9;--crit:#c42b2b;--critbg:#fdeaea;--acc:#3351c9;--accbg:#eaeefc;
--okfill:#278a5c;--warnfill:#bb7500;--critfill:#d13434;--onfill:#fff;--accfill:#4c6ef5;--shadow:0 1px 2px rgba(16,24,40,.06);color-scheme:light}
:root[data-theme=dark]{--bg:#0c0e12;--card:#15181e;--card2:#1b1f26;--text:#eceef2;--muted:#9ba3af;--faint:#8b93a0;--line:#262b33;--track:#272c35;
--ok:#4ccf8a;--okbg:#10261b;--warn:#f2b24a;--warnbg:#2a1f0b;--crit:#ff7b7b;--critbg:#2c1214;--acc:#8ea2ff;--accbg:#181e36;
--okfill:#2fb56f;--warnfill:#e9a23b;--critfill:#ef5350;--onfill:#1a0a0a;--accfill:#6d84ff;--shadow:none;color-scheme:dark}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-padding-top:64px;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:3px solid var(--acc);outline-offset:2px;border-radius:6px}
h1,h2,h3{margin:0}
.wrap{max-width:1320px;margin:0 auto;padding:0 16px}
main.wrap{padding-bottom:40px}
svg.i{width:1em;height:1em;vertical-align:-.14em;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
code,.mono{font:13px/1.3 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
/* top bar (sticky, includes connection banners) */
.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 90%,transparent);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.bar1{display:flex;align-items:center;gap:8px;min-height:52px}
.brand{font-weight:650;font-size:16px;white-space:nowrap;margin-right:4px}
.brand span{color:var(--muted);font-weight:500}
.jump{display:flex;gap:2px}
.jump a{color:var(--text);min-height:40px;display:inline-flex;align-items:center;padding:0 10px;border-radius:8px;font-weight:550}
.jump a:hover{background:var(--card);text-decoration:none}
.fresh{margin-left:auto;min-width:0;overflow:hidden;display:flex;align-items:center;gap:7px;font-size:13px;color:var(--muted);white-space:nowrap;min-height:40px}
.pulse{width:8px;height:8px;border-radius:50%;background:var(--okfill);animation:p 2.4s infinite}
.fresh.stale{color:var(--warn)}.fresh.stale .pulse{background:var(--warnfill);animation:none}
.fresh.lost{color:var(--crit);font-weight:650}.fresh.lost .pulse{background:var(--critfill);animation:none}
@keyframes p{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--okfill) 60%,transparent)}70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
.btn{font:inherit;font-size:13px;color:var(--text);background:var(--card);border:1px solid var(--line);border-radius:8px;min-height:40px;min-width:40px;padding:0 10px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px}
.btn:hover{background:var(--card2)}
.lostbar{background:var(--critbg);color:var(--crit);border-top:1px solid color-mix(in srgb,var(--crit) 35%,transparent);font-size:14px}
.lostbar .wrap{padding:8px 16px;display:flex;gap:8px;align-items:center}
.lostbar[hidden]{display:none}.lostbar.stalebar{background:var(--warnbg);color:var(--warn)}
/* hero */
.hero{margin-top:16px;border-radius:12px;background:var(--card);border:1px solid var(--line);box-shadow:var(--shadow);position:relative;overflow:hidden;display:grid;grid-template-columns:minmax(0,1fr);gap:16px;padding:20px 20px 16px 24px}
.hero::before{content:"";position:absolute;inset:0 auto 0 0;width:6px;background:var(--tone)}
.hero.ok{--tone:var(--okfill);--tbg:var(--okbg);--tt:var(--ok)}.hero.warn{--tone:var(--warnfill);--tbg:var(--warnbg);--tt:var(--warn)}.hero.crit{--tone:var(--critfill);--tbg:var(--critbg);--tt:var(--crit)}.hero.wait{--tone:var(--faint);--tbg:var(--card2);--tt:var(--muted)}
.vrow{display:flex;gap:16px;align-items:center}
.vicon{width:52px;height:52px;border-radius:12px;background:var(--tbg);color:var(--tt);display:grid;place-items:center;flex:none}
.vicon svg{width:30px;height:30px;stroke-width:2.4}
.verdict{font-size:clamp(28px,5vw,44px);line-height:1.05;font-weight:750;letter-spacing:-.02em;color:var(--tt)}
.vsub{margin:4px 0 0;color:var(--muted)}
.top1{margin:14px 0 0;font-size:16px;line-height:1.4;font-weight:550;overflow-wrap:anywhere}
.top1 a{color:inherit;text-decoration:underline;text-decoration-color:color-mix(in srgb,var(--tt) 60%,transparent);text-underline-offset:3px;text-decoration-thickness:2px}
.must{margin:14px 0 0;border-radius:8px;background:var(--critbg);border:1.5px solid var(--critfill);padding:10px 12px}
.must .k{font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--crit);display:flex;gap:6px;align-items:center;margin-bottom:2px}
.must ul{list-style:none;margin:0;padding:0}
.must a{display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline;min-height:40px;padding:6px 0;color:var(--text);font-weight:600}
.must a span{font-weight:400;color:var(--muted)}
/* alert groups */
.ags{display:flex;flex-direction:column;gap:8px;align-self:start}
.ag{border:1px solid var(--line);border-radius:8px;background:var(--card2)}
.ag.crit{border-color:color-mix(in srgb,var(--critfill) 55%,var(--line))}.ag.warn{border-color:color-mix(in srgb,var(--warnfill) 40%,var(--line))}
.ag>summary,.more>summary{list-style:none;cursor:pointer;display:flex;gap:8px;align-items:center;min-height:44px;padding:6px 10px}
.ag>summary::-webkit-details-marker,.more>summary::-webkit-details-marker{display:none}
.ag .lv{flex:none}.ag.crit .lv{color:var(--crit)}.ag.warn .lv{color:var(--warn)}
.ag .nm{font-weight:650;white-space:nowrap}
.ag .pv{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--muted)}
.ag[open] .pv{visibility:hidden}
.ag .n{flex:none;font-size:12px;font-weight:700;color:var(--muted);background:var(--track);border-radius:999px;padding:1px 8px}
.chev{transition:transform .15s;flex:none;color:var(--muted)}
details[open]>summary .chev{transform:rotate(90deg)}
.ag ul{list-style:none;margin:0;padding:0 0 4px}
.al{display:flex;gap:8px;align-items:flex-start;padding:8px 10px 8px 34px;min-height:40px;color:var(--text);border-top:1px solid var(--line);overflow-wrap:anywhere}
a.al:hover{background:var(--card);text-decoration:none}
.al .tx{flex:1;min-width:0}.al .go{color:var(--faint);margin-top:3px}
.more>summary{color:var(--acc);min-height:40px}
/* tiles */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;min-height:96px;display:flex;flex-direction:column;gap:2px;color:var(--text);box-shadow:var(--shadow);min-width:0}
a.tile:hover{text-decoration:none;border-color:var(--faint)}
.tile .k{font-size:11px;color:var(--muted);font-weight:650;text-transform:uppercase;letter-spacing:.07em;display:flex;align-items:center;gap:6px}
.tile .n{font-size:28px;font-weight:720;line-height:1.1;letter-spacing:-.02em}
.tile .n small{font-size:14px;font-weight:500;color:var(--muted);letter-spacing:0}
.tile .d{font-size:13px;color:var(--muted)}
.tile .viz{margin-top:auto;padding-top:4px}
.tile.t-acc .n{color:var(--acc)}.tile.t-warn .n{color:var(--warn)}.tile.t-crit .n{color:var(--crit)}
.seg{display:flex;height:8px;border-radius:4px;overflow:hidden;gap:2px;background:var(--track)}
.seg i{display:block;height:100%}
.mini{width:100%;height:22px;display:block}
.mini .ln{stroke-width:1.5}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none;background:var(--faint)}
.dot.busy{background:var(--accfill)}.dot.ok{background:var(--okfill)}.dot.warn{background:var(--warnfill)}.dot.crit{background:var(--critfill)}
.tiles[data-fade=r]{-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 44px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 44px),transparent)}
.tiles[data-fade=l]{-webkit-mask-image:linear-gradient(270deg,#000 calc(100% - 44px),transparent);mask-image:linear-gradient(270deg,#000 calc(100% - 44px),transparent)}
.tiles[data-fade=lr]{-webkit-mask-image:linear-gradient(90deg,transparent,#000 36px,#000 calc(100% - 44px),transparent);mask-image:linear-gradient(90deg,transparent,#000 36px,#000 calc(100% - 44px),transparent)}
.okl{list-style:none;margin:0;padding:0;display:grid;gap:8px;align-self:center;font-size:16px}
.okl li{display:flex;gap:10px;align-items:center}.okl svg{color:var(--ok);width:18px;height:18px;stroke-width:2.6}
.igg+.igg{margin-top:6px}
/* layout */
.cols{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:20px;margin-top:20px;align-items:start}
.colA,.colB,.stk{display:flex;flex-direction:column;gap:12px;min-width:0}
.h2{display:flex;align-items:center;gap:10px;min-height:40px}
.h2 h2{font-size:18px;font-weight:700}
.h2 .c{color:var(--muted);font-size:13px}
.flt{margin-left:auto;display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:0 10px;min-height:40px;min-width:0;flex:0 1 220px;color:var(--muted)}
.flt input{font:inherit;color:var(--text);background:none;border:0;outline:0;min-width:0;width:100%;min-height:38px}
.flt:focus-within{border-color:var(--acc);outline:2px solid var(--acc)}
.flt kbd,kbd{font:11px ui-monospace,Menlo,monospace;border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;padding:0 5px;color:var(--muted);background:var(--card2)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);min-width:0;overflow:hidden}
.gh{display:flex;align-items:center;gap:8px;padding:12px 16px 6px;border-top:1px solid var(--line);scroll-margin-top:70px}
.gh:first-child{border-top:0}
.gh h3{font-size:14px;font-weight:700;display:flex;gap:7px;align-items:center}
.gh .c{font-size:12px;font-weight:700;color:var(--muted);background:var(--track);border-radius:999px;padding:0 8px}
.gh .hint{margin-left:auto;font-size:12px;color:var(--muted)}
.empty{padding:2px 16px 14px;color:var(--muted);margin:0}
.ul{list-style:none;margin:0;padding:0 0 4px}
.row{display:flex;gap:12px;padding:10px 16px;border-top:1px solid var(--line);align-items:flex-start;position:relative}
.ul>.row:first-child{border-top:0}
.ic{flex:none;width:28px;height:28px;border-radius:8px;display:grid;place-items:center;margin-top:1px;background:var(--card2);color:var(--muted)}
.ic.busy{background:var(--accbg);color:var(--acc)}.ic.q{background:var(--warnbg);color:var(--warn)}.ic.off{background:var(--critbg);color:var(--crit)}.ic.rec{background:var(--accbg);color:var(--acc)}
.m{flex:1;min-width:0}
.jt{font-weight:600;font-size:14px;overflow-wrap:anywhere}
.jt a{color:var(--text)}.jt a:hover{color:var(--acc)}
.jt .rn{font:13px ui-monospace,Menlo,monospace;color:var(--muted);font-weight:500}
.jt .ar{color:var(--faint);margin:0 5px}
.jt .sub{color:var(--muted);font-weight:500}
.meta{display:flex;flex-wrap:wrap;gap:3px 10px;align-items:center;margin-top:3px;font-size:13px;color:var(--muted)}
.repo{font-weight:650;color:var(--text)}
.pr{position:relative;z-index:1;display:inline-flex;align-items:center;gap:4px;font-weight:650;background:var(--accbg);color:var(--acc);border-radius:6px;padding:2px 8px;min-height:28px}
.pr:hover{text-decoration:none;filter:brightness(1.1)}
.tag{font-size:12px;border:1px solid var(--line);border-radius:6px;padding:0 6px;color:var(--muted)}
.tmw{flex:none;text-align:right;min-width:68px}
.tm{display:block;font-size:16px;font-weight:700;line-height:1.25}
.tmw small{font-size:12px;color:var(--muted)}
.tmw.long .tm{color:var(--warn)}.tmw.vlong .tm{color:var(--crit)}
.shimmer{display:inline-block;height:10px;width:160px;max-width:70%;border-radius:5px;background:linear-gradient(90deg,var(--track),var(--card2),var(--track));background-size:200% 100%;animation:sh 1.4s infinite linear;vertical-align:middle}
@keyframes sh{to{background-position:-200% 0}}
/* offline / why */
.row.k-gave{background:color-mix(in srgb,var(--critbg) 60%,transparent)}
.row[class*=k-]::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--ek)}
.k-gave{--ek:var(--critfill)}.k-fail{--ek:var(--critfill)}.k-down,.k-unk{--ek:var(--warnfill)}.k-rec{--ek:var(--accfill)}.k-plan{--ek:var(--faint)}
.st{font-size:11px;font-weight:750;letter-spacing:.05em;text-transform:uppercase;padding:2px 7px;border-radius:6px;display:inline-flex;align-items:center;gap:4px}
.st.gave{background:var(--critfill);color:var(--onfill)}.st.fail{background:var(--critbg);color:var(--crit);border:1px solid var(--critfill)}.st.down,.st.unk{background:var(--warnbg);color:var(--warn)}.st.rec{background:var(--accbg);color:var(--acc)}.st.plan{background:var(--card2);color:var(--muted);border:1px solid var(--line)}
.ln1{display:flex;flex-wrap:wrap;gap:4px 8px;align-items:center}
.why{margin-top:4px;overflow-wrap:anywhere}
.last{font-size:13px;color:var(--muted);margin-top:3px;overflow-wrap:anywhere}
.last .bad{color:var(--crit)}.last .good{color:var(--ok)}
.todo{margin-top:8px;border:1.5px solid var(--critfill);background:var(--critbg);border-radius:8px;padding:8px 10px;display:flex;gap:8px;align-items:flex-start}
.todo b{color:var(--crit)}
.ig{padding:0 16px 10px}
.igl{font-size:12px;color:var(--muted);display:block;margin:6px 0 4px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--card2);border-radius:8px;padding:4px 9px;min-height:32px;font-size:13px}
details.sec>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:8px;padding:12px 16px;min-height:48px;border-top:1px solid var(--line)}
details.sec>summary::-webkit-details-marker{display:none}
details.sec>summary h3{font-size:14px;font-weight:700;display:flex;gap:7px;align-items:center}
details.sec>summary .r{margin-left:auto;color:var(--muted);font-size:13px;display:flex;gap:6px;align-items:center}
details.sec>summary .sw::before{content:"show"}details.sec[open]>summary .sw::before{content:"hide"}
.note{margin:6px 16px 14px;padding:10px 12px;border-radius:8px;display:flex;gap:10px;align-items:flex-start;overflow-wrap:anywhere}
.note.warn{background:var(--warnbg);color:var(--warn)}.note.crit{background:var(--critbg);color:var(--crit)}.note.mut{background:var(--card2);color:var(--muted)}.note.ok{background:var(--okbg);color:var(--ok)}
.calm{margin:0;padding:6px 16px 16px;display:flex;gap:8px;align-items:center;color:var(--ok);font-weight:550}
/* hosts */
.mh{display:flex;align-items:center;gap:8px 12px;padding:14px 16px 4px;flex-wrap:wrap}
.mh h3{font-size:16px;font-weight:700}
.mh .r{margin-left:auto;font-size:13px;color:var(--muted);display:flex;gap:10px;flex-wrap:wrap}
.mh .r span{display:inline-flex;align-items:center;gap:5px}
.meters{padding:8px 16px 4px;display:grid;gap:12px}
.mt .l{display:flex;justify-content:space-between;gap:8px;align-items:baseline;flex-wrap:wrap}
.mt .l b{font-weight:650}.mt .l .v{color:var(--muted);text-align:right}
.mt em{font-style:normal;font-weight:750;margin-left:6px;font-size:11px;letter-spacing:.04em;text-transform:uppercase}
.mt em.warn{color:var(--warn)}.mt em.crit{color:var(--crit)}
.bar{height:12px;background:var(--track);border-radius:6px;overflow:hidden;margin-top:5px;position:relative;--fc:var(--accfill)}
.bar.ok{--fc:var(--okfill)}.bar.warn{--fc:var(--warnfill)}.bar.crit{--fc:var(--critfill)}
.bar i{position:absolute;top:0;bottom:0;left:0;background:var(--fc)}
.bar i.hat{background:repeating-linear-gradient(135deg,var(--fc) 0 2px,transparent 2px 5px)}
.bar s{position:absolute;top:0;bottom:0;width:2px;margin-left:-1px;background:var(--text);opacity:.45}
.bar s.c{opacity:.75}
.chr{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px 16px 4px}
.chh{display:flex;justify-content:space-between;gap:6px;font-size:12px;color:var(--muted);margin-bottom:3px;min-height:18px}
.chh b{font-weight:650;color:var(--text)}
.chh .ro{white-space:nowrap}
.ch{position:relative;height:56px;border:1px solid var(--line);border-radius:6px;background:var(--card2);touch-action:pan-y;cursor:crosshair}
.ch svg{width:100%;height:100%;display:block}
.ch .mx,.ch .mn{position:absolute;right:4px;font-size:11px;color:var(--faint);background:color-mix(in srgb,var(--card2) 80%,transparent);padding:0 3px;border-radius:3px;pointer-events:none}
.ch .mx{top:1px}.ch .mn{bottom:1px}
.ch.big{height:84px}
.ln{fill:none;stroke:var(--accfill);stroke-width:1.6;vector-effect:non-scaling-stroke;stroke-linejoin:round}
.ar{fill:var(--accfill);opacity:.22;stroke:none}.ar.w{fill:var(--warnfill);opacity:.28}
.ln.w{stroke:var(--warnfill)}
.refl{stroke:var(--warnfill);stroke-width:1;stroke-dasharray:3 3;vector-effect:non-scaling-stroke;opacity:.8}
.xh{stroke:var(--text);stroke-width:1;vector-effect:non-scaling-stroke;opacity:.8}
.ax{display:flex;justify-content:space-between;font-size:11px;color:var(--faint);margin-top:2px}
.vms{margin:12px 16px 16px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.vm{display:flex;gap:4px 10px;align-items:center;padding:8px 12px;border-top:1px solid var(--line);flex-wrap:wrap;min-height:40px}
.vm:first-child{border-top:0}.vm .s{font-size:13px;color:var(--muted)}.vm .w{margin-left:auto;font-size:13px;color:var(--muted);text-align:right}
.vm.stop{background:var(--warnbg)}.vm.stop .w{color:var(--warn);font-weight:650}
.gk{padding:4px 16px 14px;display:grid;gap:6px;font-size:13px;color:var(--muted)}
.gk b{color:var(--text);font-weight:600}
.foot{color:var(--faint);font-size:13px;margin-top:20px;line-height:1.6}
.foot p{margin:0 0 4px}
dialog{border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--text);padding:0;width:min(400px,calc(100vw - 32px))}
dialog::backdrop{background:rgba(0,0,0,.4)}
dialog h2{font-size:16px;padding:14px 18px;border-bottom:1px solid var(--line)}
dialog dl{margin:0;padding:10px 18px 14px;display:grid;grid-template-columns:1fr auto;gap:8px 16px;align-items:center}
dialog dd{margin:0;text-align:right}dialog form{padding:0 18px 14px}
@media (max-width:980px){.cols{grid-template-columns:minmax(0,1fr)}.hero{padding-right:16px}}
@media (min-width:981px){
 .cols.quiet{grid-template-columns:minmax(0,1fr)}
 .quiet #hostl{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));align-items:start}
 .quiet #extra{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}.quiet #extra:has(#hist:empty){grid-template-columns:minmax(0,1fr)}
 .quiet #extra .h2{grid-column:1/-1}
 .quiet .ig{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:2px 28px}.quiet .igg+.igg{margin-top:0}
}
@media (min-width:641px) and (max-width:900px){.tiles[data-n="5"]{grid-template-columns:repeat(6,1fr)}.tiles[data-n="5"] .tile{grid-column:span 2}.tiles[data-n="5"] .tile:nth-child(n+4){grid-column:span 3}}
@media (min-width:981px){.hero.two{grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:28px}.ch{height:64px}}
@media (min-width:1200px){.ch{height:72px}}
@media (max-width:640px){
 .wrap{padding:0 12px}main.wrap{padding-bottom:28px}
 .hero{margin-top:12px;padding:14px 12px 12px 18px;gap:12px}.vicon{width:42px;height:42px}.vicon svg{width:24px;height:24px}.vrow{gap:12px}
 .brand,.btn.hp{display:none}.jump a{padding:0 8px}.bar1{gap:4px}
 .tiles{display:flex;overflow-x:auto;scroll-snap-type:x proximity;scroll-padding:0 12px;margin:12px -12px 0;padding:0 12px 4px;gap:8px;-webkit-overflow-scrolling:touch;scrollbar-width:none}.tiles::-webkit-scrollbar{display:none}
 .tile{flex:0 0 40%;scroll-snap-align:start;min-height:88px;padding:8px 10px}.tile .n{font-size:24px}
 .row{padding:10px 12px;gap:10px}.row>.ic{display:none}.gh{padding:12px 12px 6px}.empty,.calm{padding-left:12px;padding-right:12px}.ig{padding:0 12px 10px}
 .mh{padding:12px 12px 4px}.meters{padding-left:12px;padding-right:12px}.chr{padding:10px 12px 4px;gap:8px}.vms{margin:10px 12px 12px}.note{margin-left:12px;margin-right:12px}.gk{padding-left:12px;padding-right:12px}
 .ch{height:44px}.flt{flex-basis:140px}.flt kbd{display:none}.flt input{min-height:40px}
 .jt a,.top1 a{padding:12px 0}
 .pr{min-height:40px;padding:0 12px;margin:-5px 0}.meta{gap:6px 10px}
 details.sec>summary{padding:12px}.tmw{min-width:60px}
 .ag .nm{max-width:42%;overflow:hidden;text-overflow:ellipsis}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}html{scroll-behavior:auto}}
</style></head><body>
<header class="top" id="top"><div class="wrap bar1">
 <div class="brand">Runners</div>
 <nav class="jump" aria-label="Jump to"><a href="#activity">Activity</a><a href="#hosts">Machines</a><a href="#github">GitHub</a></nav>
 <div class="fresh" id="fresh" role="status" aria-live="off"><i class="pulse"></i><span id="freshTx">Connecting…</span></div>
 <button class="btn" id="theme" type="button"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor"/></svg><span class="sr" id="themeTx">Auto</span></button>
 <button class="btn hp" id="helpb" type="button" aria-label="Keyboard shortcuts">?</button>
</div><div class="lostbar" id="lost" role="alert" hidden><div class="wrap"></div></div></header>
<main class="wrap">
 <section class="hero wait" id="hero" aria-label="Overall status"><div class="vrow"><div class="vicon"></div><div><h1 class="verdict">Checking…</h1><p class="vsub">Fetching the first status snapshot.</p></div></div></section>
 <nav class="tiles" id="tiles" aria-label="Summary"></nav>
 <div class="cols" id="cols">
  <div class="colA">
   <div class="h2" id="activity"><h2>Activity</h2><span class="c" id="actc"></span><label class="flt"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><span class="sr">Filter by runner, repo or PR</span><input id="flt" type="search" placeholder="Filter" autocomplete="off"><kbd>/</kbd></label></div>
   <div id="act"><div class="card"><p class="empty" style="padding-top:16px"><span class="shimmer"></span></p><p class="empty"><span class="shimmer" style="width:240px"></span></p></div></div>
  </div>
  <div class="colB">
   <div class="h2" id="hosts"><h2>Machines</h2><span class="c" id="hostc"></span></div>
   <div id="hostl" class="stk"></div>
   <div id="extra" class="stk"><div class="h2" id="github"><h2>GitHub</h2></div><div id="ghc"></div><div id="hist"></div></div>
  </div>
 </div>
 <footer class="foot" id="foot"></footer>
</main>
<dialog id="help" aria-labelledby="help-h"><h2 id="help-h">Keyboard shortcuts</h2><dl>
<dt>Filter activity</dt><dd><kbd>/</kbd></dd><dt>Open or close alerts</dt><dd><kbd>a</kbd></dd><dt>Show or hide idle runners</dt><dd><kbd>i</kbd></dd><dt>Change theme</dt><dd><kbd>t</kbd></dd><dt>Move a chart cursor</dt><dd><kbd>←</kbd> <kbd>→</kbd></dd><dt>This help</dt><dd><kbd>?</kbd></dd><dt>Clear filter or close</dt><dd><kbd>Esc</kbd></dd></dl>
<form method="dialog"><button class="btn">Close</button></form></dialog>
<script>
"use strict";
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
/* ===== RULES: the only places that interpret wording. Edit here. ===== */
/* Alert groups: first match wins (alert.runner always means "runners"). href = where an alert without its own url jumps. */
const AG=[
 {id:"gh",name:"GitHub access",re:/^GitHub:/,href:"#github"},
 {id:"queue",name:"Queue",re:/queued|stalled|hosted runner/i,href:"#sec-wait"},
 {id:"runners",name:"Runners",re:/^Offline runners/i,href:"#sec-off"},
 {id:"hosts",name:"Machines",re:/disk|VM |stats missing|memory|load/i,href:"#hosts"},
 {id:"limits",name:"Limits and workflows",re:/quota|minutes|workflow/i,href:"#tiles"}];
const OTHER={id:"other",name:"Other",href:""};
const GAVE_FALLBACK=/gave up/i;      /* used only when why.gave_up is undefined */
const RESULT_OK=/^ok\b/i;            /* a recovery result that is not "ok..." counts as failing */
const CAUSE={maintenance:["Planned maintenance",""],"vm-stopped":["VM stopped","Start the VM by hand"],"service-dead":["Runner service died","Restart the runner service by hand"],network:["Network","Check the machine's network"],registration:["Registration lost","Re-register the runner with a new token"],"disk-full":["Disk full","Free up disk space"],"no-service":["No runner service","Install the runner service"],"host-silent":["Machine not reporting","Wake or reconnect the machine"],unknown:["Unknown cause","Check it by hand"]};
/* ===== */
const P={check:'<path d="M20 6 9 17l-5-5"/>',alert:'<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',x:'<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',play:'<circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4z"/>',pr:'<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M6 8.5v7M18 15.5V9a3 3 0 0 0-3-3h-4"/>',chev:'<path d="m9 6 6 6-6 6"/>',off:'<path d="M2 2l20 20M8.5 16.5a5 5 0 0 1 7 0M5 13a10 10 0 0 1 5.2-2.8M19 13a10 10 0 0 0-2-1.6M12 20h.01"/>',pause:'<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',cloud:'<path d="M17.5 19H9a7 7 0 1 1 6.7-9h1.8a4.5 4.5 0 1 1 0 9z"/>',plug:'<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>',refresh:'<path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5"/>'};
const ic=(n,c)=>`<svg class="i${c?" "+c:""}" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-${n}"/></svg>`;
document.body.insertAdjacentHTML("afterbegin",`<svg width="0" height="0" style="position:absolute" aria-hidden="true">${Object.keys(P).map(k=>`<symbol id="i-${k}" viewBox="0 0 24 24">${P[k]}</symbol>`).join("")}</svg>`);
const bytes=n=>{if(n==null)return"?";const u=["B","KB","MB","GB","TB"];let i=0;while(n>=1024&&i<4){n/=1024;i++}return(n>=100||i<3?Math.round(n):n.toFixed(1))+" "+u[i]};
/* links from data: only http(s) or "#" */
const url=u=>/^(https?:\/\/|#)/i.test(String(u||""))?String(u):"#";
const pad=n=>String(n).padStart(2,"0");
function elapsed(sec){sec=Math.max(0,sec);const d=Math.floor(sec/86400),h=Math.floor(sec%86400/3600),m=Math.floor(sec%3600/60),s=Math.floor(sec%60);return d?d+"d "+h+"h":h?h+"h "+pad(m)+"m":m+"m "+pad(s)+"s"}
const dur=m=>m==null?"-":m<1?"<1m":elapsed(m*60).replace(/ \d\ds$/,"").replace(/^0/,"");
const ago=s=>s<10?"just now":s<60?Math.floor(s)+"s ago":s<3600?Math.floor(s/60)+" min ago":Math.floor(s/3600)+"h "+Math.floor(s%3600/60)+"m ago";
const clock=d=>d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
const pl=(n,w,p)=>n+" "+(n===1?w:(p||w+"s"));
const slug=s=>String(s).toLowerCase().replace(/[^a-z0-9]+/g,"-");
const pct=v=>Math.round(v*100)+"%";
/* persisted UI state: which <details> are open, theme */
let OP={};try{OP=JSON.parse(localStorage.getItem("rs-open")||"{}")}catch(e){}
document.addEventListener("toggle",e=>{const d=e.target;if(d.tagName==="DETAILS"&&d.id){OP[d.id]=d.open?1:0;try{localStorage.setItem("rs-open",JSON.stringify(OP))}catch(x){}}},true);
const op=(id,def)=>(id in OP?OP[id]:def)?" open":"";
/* tiny keyed DOM morph: untouched nodes keep focus/scroll/open state. data-js nodes are owned by JS (timers, chart readouts). */
function sync(o,n){for(const a of [...o.attributes])if(!n.hasAttribute(a.name))o.removeAttribute(a.name);for(const a of n.attributes)if(o.getAttribute(a.name)!==a.value)o.setAttribute(a.name,a.value)}
function morphEl(o,n){sync(o,n);if(!n.hasAttribute("data-js"))morphKids(o,n)}
function morphKids(o,n){const om=new Map();for(const c of o.childNodes)if(c.nodeType===1&&c.dataset.k)om.set(c.dataset.k,c);
 const keep=new Set();let pos=0;
 for(const c of [...n.childNodes]){const k=c.nodeType===1&&c.dataset.k;let t=k?om.get(k):o.childNodes[pos];
  if(!k&&t&&t.nodeType===1&&t.dataset.k)t=null;
  if(t&&t.nodeType===c.nodeType&&t.nodeName===c.nodeName){
   if(c.nodeType===3){if(t.nodeValue!==c.nodeValue)t.nodeValue=c.nodeValue}
   else if(c.nodeType===1){if(k){const h=c.outerHTML;if(t._h!==h){morphEl(t,c);t._h=h}}else morphEl(t,c)}}
  else{t=c.cloneNode(true);if(k)t._h=c.outerHTML}
  keep.add(t);if(o.childNodes[pos]!==t)o.insertBefore(t,o.childNodes[pos]||null);pos++}
 for(const c of [...o.childNodes])if(!keep.has(c))c.remove()}
function mount(el,html){const t=document.createElement("template");t.innerHTML=html;morphKids(el,t.content)}
/* theme */
const modes=["auto","light","dark"];let mode="auto";try{mode=localStorage.getItem("rs-theme")||"auto"}catch(e){}
function applyTheme(){window.rsTheme(mode);$("themeTx").textContent="Theme: "+mode;$("theme").title="Theme: "+mode+" (t)";$("theme").setAttribute("aria-label","Theme: "+mode+". Activate to change.")}
function cycleTheme(){mode=modes[(modes.indexOf(mode)+1)%3];try{localStorage.setItem("rs-theme",mode)}catch(e){}applyTheme()}
$("theme").onclick=cycleTheme;applyTheme();
/* state */
let quiet=false,S=null,TK={},CH={},HV=null,FLT="",skew=0,failing=0,lastErr="",updMs=0;
const lvlOf=(p,w,c)=>p>=c?"crit":p>=w?"warn":"";
/* ---- tolerate any missing or null field from older servers ---- */
const arr=v=>Array.isArray(v)?v:[],isO=v=>v!==null&&typeof v==="object"&&!Array.isArray(v),num=v=>typeof v==="number"&&isFinite(v)?v:null;
function norm(d){const s=isO(d)?d:{};
 s.machines=arr(s.machines).filter(isO).map(m=>{m.name=String(m.name??"Unnamed machine");m.runners=arr(m.runners).filter(isO).map(r=>{r.name=String(r.name??"?");r.job=isO(r.job)?normJob(r.job):null;r.why=isO(r.why)?r.why:null;return r});
  const c={idle:0,busy:0,offline:0};for(const r of m.runners)r.status==="busy"?c.busy++:r.status==="idle"?c.idle++:c.offline++;m.counts=isO(m.counts)?{...c,...m.counts}:c;
  const t=m.stats;if(isO(t)&&!t.error){t.disks=arr(t.disks).filter(isO);t.vms=t.vms==null?null:arr(t.vms).filter(isO).map(v=>{v.runners=arr(v.runners);v.jobs=arr(v.jobs);return v});if(!Array.isArray(t.load))t.load=null}
  else if(!isO(t))m.stats=null;return m});
 s.jobs=arr(s.jobs).filter(isO).map(normJob);s.errors=arr(s.errors).map(String);
 s.alerts=arr(s.alerts).filter(isO).map(a=>({...a,level:a.level==="crit"?"crit":"warn",text:String(a.text??"")}));
 const c=isO(s.counts)?s.counts:{};s.counts={queued:num(c.queued)??s.jobs.filter(j=>j.status!=="in_progress").length,running:num(c.running)??s.jobs.filter(j=>j.status==="in_progress").length};
 s.rate=isO(s.rate)?s.rate:null;s.billing=isO(s.billing)?s.billing:null;s.history=isO(s.history)?s.history:{};if(!isO(s.history.machines))s.history.machines={};
 const hj=s.history.jobs;if(!(isO(hj)&&arr(hj.t).length>1&&arr(hj.running).length===hj.t.length))s.history.jobs=null;else{hj.queued=arr(hj.queued).length===hj.t.length?hj.queued:hj.t.map(()=>0)}
 s.loading=!!s.loading;return s}
function normJob(j){j.prs=arr(j.prs).filter(isO);j.labels=arr(j.labels);j.url=j.url||"#";j.repo=String(j.repo??"");j.workflow=String(j.workflow??"");j.name=String(j.name??"");j.age_min=num(j.age_min);return j}
/* ---- structured helpers ---- */
function flat(s){const a=[];for(const m of s.machines||[]){const vmOf={};for(const v of(m.stats&&m.stats.vms)||[])for(const n of v.runners||[])vmOf[n]=v.name;for(const r of m.runners||[])a.push({r,m,vm:vmOf[r.name]||null})}return a}
const locOf=x=>esc(x.m.name)+(x.vm?" › "+esc(x.vm):"");
function kindOf(w){if(!w)return"unk";if(w.cause==="maintenance")return"plan";
 const gave=w.gave_up!==undefined&&w.gave_up!==null?w.gave_up===true:GAVE_FALLBACK.test(w.result||"");
 if(gave)return"gave";if(w.action)return w.result&&!RESULT_OK.test(w.result)?"fail":"rec";return"down"}
const KIND={gave:["Gave up · needs you","alert",0,"off"],fail:["Fix failed · retrying","x",1,"off"],down:["No auto-fix","off",2,"q"],unk:["Offline","off",2.5,"off"],rec:["Recovering","refresh",3,"rec"],plan:["Planned","pause",4,""]};
const blind=s=>(s.errors||[]).length&&!(s.machines||[]).some(m=>(m.runners||[]).length);
const match=(txt)=>!FLT||txt.toLowerCase().includes(FLT);
/* ---- alerts ---- */
function groupOf(a){if(a.runner)return AG[2];for(const g of AG)if(g.re.test(a.text))return g;return OTHER}
function alertText(a,offN){if(S&&a.text.startsWith("GitHub: ")&&(S.errors||[]).includes(a.text.slice(8)))return a.text.slice(8).split(/\.\s/)[0]+". Details under GitHub.";if(offN&&groupOf(a).id==="runners"&&!a.runner)return pl(offN,"runner")+" offline. Why and recovery status are under Activity.";return a.text.replace(/^GitHub:\s*/,"")}
function alertHref(a,s){if(a.url)return url(a.url);if(a.runner)return"#r-"+slug(a.runner);const g=groupOf(a);if(g.id==="hosts")for(const m of s.machines||[])if(a.text.indexOf(m.name)===0)return"#m-"+slug(m.name);return g.href}
/* distinct problems: one key per real-world thing, so one runner or one GitHub failure is never counted twice */
const alKey=a=>a.runner?"r:"+a.runner:/^GitHub:/.test(a.text)?"gh":groupOf(a).id==="runners"?"off":"t:"+a.text;
function heroData(s){const fl=flat(s),offN=fl.filter(x=>x.r.status==="offline").length;
 const al=[...s.alerts].sort((a,b)=>(a.level==="crit"?0:1)-(b.level==="crit"?0:1));
 const needs=fl.filter(x=>x.r.status==="offline"&&kindOf(x.r.why)==="gave");
 const P=new Set(),W=new Set();for(const a of al)(a.level==="crit"?P:W).add(alKey(a));
 for(const x of needs)P.add("r:"+x.r.name);
 for(const k of P)W.delete(k);if(offN>0)W.delete("off");
 const np=P.size,nw=W.size,nn=needs.length,oth=offN-nn,only=nn>0&&np===nn;
 const offTx=pl(oth,(nn?"other ":"")+"runner")+" offline",needTx=pl(nn,"runner")+" need"+(nn===1?"s":"")+" you";
 const down=blind(s);let tone,head,sub;
 if(down){tone="crit";head="GitHub unreachable";sub="Runner and job status unknown. Machine stats below are still live."}
 else if(np){tone="crit";head=only?needTx:pl(np,"problem");sub=[nn&&!only?needTx:"",oth>0?offTx:"",nw?pl(nw,"warning"):""].filter(Boolean).join(" · ")||(only?"Auto-recovery gave up":"Nothing else wrong")}
 else if(nw||oth>0){tone="warn";head=nw?pl(nw,"warning"):offTx;sub=nw?(oth>0?offTx+" too":"Nothing broken, a few things to watch"):"Nothing needs you right now"}
 else{tone="ok";head="All clear";sub="Every runner reachable, nothing stuck in the queue"}
 return{al,needs,offN,tone,head,sub,down,np,ok:tone==="crit"?"":okList(s,offN)}}
function okList(s,offN){const n=flat(s).length,q=s.jobs.filter(j=>j.status!=="in_progress"),old=q.length?Math.max(...q.map(j=>j.age_min||0)):0,ms=s.machines.filter(m=>isO(m.stats)&&!m.stats.error).length,r=s.rate,L=[];
 if(n&&!offN)L.push(`All ${pl(n,"runner")} reachable`);
 if(s.loading)L.push("Checking the queue");else if(!q.length)L.push("Nothing waiting for a runner");else if(old<20)L.push(pl(q.length,"job")+" waiting, oldest "+dur(old));
 if(s.machines.length&&ms===s.machines.length)L.push(`All ${pl(s.machines.length,"machine")} reporting`);
 if(!s.errors.length)L.push("GitHub is reachable"+(r&&num(r.limit)&&num(r.remaining)!=null?`, ${pct(r.remaining/r.limit)} of API calls left`:""));
 return L.length<2?"":`<ul class="okl" data-k="o" aria-label="What is fine">${L.map(t=>`<li>${ic("check")}${esc(t)}</li>`).join("")}</ul>`}
function alertGroups(h,s){const first=h.al[0],rest=h.al.slice(1),gs=new Map();
 for(const a of rest){const g=groupOf(a);if(!gs.has(g.id))gs.set(g.id,{g,items:[],crit:false});const e=gs.get(g.id);e.items.push(a);if(a.level==="crit")e.crit=true}
 const list=[...gs.values()].sort((a,b)=>b.crit-a.crit);
 const row=a=>{const href=alertHref(a,s),inner=`<span class="lv ${a.level}">${ic(a.level==="crit"?"x":"alert")}</span><span class="sr">${a.level==="crit"?"Critical":"Warning"}: </span><span class="tx">${esc(alertText(a,h.offN))}</span>${href?`<span class="go">${ic("chev")}</span>`:""}`;return`<li>${href?`<a class="al" href="${esc(href)}">${inner}</a>`:`<div class="al">${inner}</div>`}</li>`};
 const det=e=>{const id="ag-"+e.g.id,lv=e.crit?"crit":"warn";return`<details class="ag ${lv}" id="${id}" data-k="${id}"${op(id,0)}><summary>${ic("chev","chev")}<span class="lv">${ic(e.crit?"x":"alert")}</span><span class="nm">${esc(e.g.name)}</span><span class="pv">${esc(alertText(e.items[0],h.offN))}</span><span class="n">${e.items.length}</span></summary><ul>${e.items.map(row).join("")}</ul></details>`};
 const vis=list.slice(0,3),more=list.slice(3);
 return vis.map(det).join("")+(more.length?`<details class="more" id="ag-more" data-k="ag-more"${op("ag-more",0)}><summary>${ic("chev","chev")}${pl(more.length,"more area")}</summary><div class="ags">${more.map(det).join("")}</div></details>`:"")}
function heroHTML(s,h){const icon=h.tone==="ok"?"check":h.tone==="crit"?"x":"alert";
 const first=h.al[0];let left=`<div class="vrow" data-k="v"><div class="vicon">${ic(icon)}</div><div><h1 class="verdict">${esc(h.head)}</h1><p class="vsub">${esc(s.org||"")} · ${esc(h.sub)}</p></div></div>`;
 if(first){const href=alertHref(first,s),t=esc(alertText(first,h.offN));left+=`<p class="top1" data-k="t">${href?`<a href="${esc(href)}">${t}</a>`:t}</p>`}
 if(h.needs.length)left+=`<div class="must" role="note" data-k="m"><span class="k">${ic("alert")}Auto-recovery gave up · only you can fix ${h.needs.length>1?"these":"this"}</span><ul>${h.needs.map(x=>`<li><a href="#r-${slug(x.r.name)}">${esc(x.r.name)}<span>${locOf(x)} · ${esc((CAUSE[x.r.why.cause]||[x.r.why.cause])[0])}</span></a></li>`).join("")}</ul></div>`;
 const ags=alertGroups(h,s);
 return`<div data-k="l">${left}</div>`+(ags?`<div class="ags" data-k="r" role="region" aria-label="Warnings">${ags}</div>`:h.ok)}
/* ---- tiles ---- */
function mini(arr,max,cls){if(!arr||arr.length<2)return"";return`<svg class="mini" viewBox="0 0 200 22" preserveAspectRatio="none" aria-hidden="true">${plot([{v:arr,cls:cls||""}],0,max,22,true)}</svg>`}
function tilesHTML(s,h){const c=s.counts||{},ld=s.loading,fl=flat(s);let idle=0,busy=0,off=0;for(const x of fl){const st=x.r.status;st==="busy"?busy++:st==="idle"?idle++:off++}
 const jobs=s.jobs||[],q=jobs.filter(j=>j.status!=="in_progress"),oldest=q.length?Math.max(...q.map(j=>j.age_min||0)):0,total=idle+busy+off,none=blind(s);
 const T=(href,key,cls,lab,n,d,viz)=>`<a class="tile ${cls}" href="${href}" data-k="${key}"><span class="k">${lab}</span><span class="n">${n}</span><span class="d">${d}</span>${viz?`<span class="viz">${viz}</span>`:""}</a>`;
 const hj=s.history.jobs;let out="";
 out+=T("#sec-work","r","t-acc","Running",ld?"…":none?"?":c.running??0,ld?"Fetching jobs":none?"Unknown":"jobs in progress",hj?mini(hj.running,Math.max(1,...hj.running,...hj.queued.map((q,i)=>q+hj.running[i])),""):"");
 out+=T("#sec-wait","q",q.length&&oldest>=20?"t-warn":"","Queued",ld?"…":none?"?":c.queued??0,ld?"Fetching jobs":none?"Unknown":q.length?"oldest waiting "+dur(oldest):"nothing waiting",hj?mini(hj.queued,Math.max(1,...hj.queued),"w"):"");
 const seg=total?`<div class="seg" role="img" aria-label="${busy} busy, ${idle} idle, ${off} offline"><i style="flex:${busy};background:var(--accfill)"></i><i style="flex:${idle};background:var(--okfill)"></i><i style="flex:${off};background:var(--critfill)"></i></div>`:"";
 out+=T("#sec-off","u",off?"t-crit":"","Runners",none?"?":`${total-off}<small> of ${total} up</small>`,none?"Unknown":`${busy} busy · ${idle} idle · ${off} offline`,seg);
 const r=s.rate;if(r&&num(r.limit)&&num(r.remaining)!=null){const left=r.remaining/r.limit,lv=left<.1?"crit":left<.2?"warn":"ok";
  out+=T("#github","a",lv==="ok"?"":"t-"+lv,"API calls left",r.remaining.toLocaleString()+"<small> / "+r.limit.toLocaleString()+"</small>",(lv==="ok"?"":(lv==="crit"?"✕ Very low · ":"▲ Low · "))+(num(r.reset)?"resets "+clock(new Date(r.reset*1000)):""),`<div class="bar ${lv}" role="img" aria-label="${pct(left)} left"><i style="width:${(left*100).toFixed(1)}%"></i></div>`)}
 const b=s.billing;if(b&&num(b.included_minutes)&&num(b.total_minutes_used)!=null){const p=b.total_minutes_used/b.included_minutes,lv=lvlOf(p,.8,.95);
  out+=T("#github","b",lv?"t-"+lv:"","Build minutes used",b.total_minutes_used.toLocaleString()+"<small> / "+b.included_minutes.toLocaleString()+"</small>",(lv==="crit"?"✕ ":lv==="warn"?"▲ ":"")+pct(p)+" used this month",`<div class="bar ${lv||"ok"}" role="img" aria-label="${pct(p)} used"><i style="width:${Math.min(100,p*100).toFixed(1)}%"></i></div>`)}
 return out}
/* ---- charts ---- */
function plot(series,lo,hi,H,step){const n=series[0].v.length,X=i=>(i*200/(n-1)).toFixed(1),Y=v=>(H-1-Math.max(0,Math.min(1,(v-lo)/(hi-lo)))*(H-2)).toFixed(1);let out="";
 for(const s of series){let d="";s.v.forEach((v,i)=>{d+=i?(step?`H${X(i)}V${Y(v)}`:`L${X(i)} ${Y(v)}`):`M0 ${Y(v)}`});if(step)d+="H200";
  out+=`<path class="ar ${s.cls||""}" d="${d}L200 ${H}L0 ${H}Z"/><path class="ln ${s.cls||""}" d="${d}"/>`}
 return out}
function chart(key,grp,title,series,lo,hi,mxl,mnl,def,fmt,t,big,aria,step){const H=40;CH[key]={t,n:series[0].v.length,fmt,def};
 const ref=hi<=1.0001&&title==="CPU"?`<line class="refl" x1="0" x2="200" y1="1" y2="1"/>`:"";
 return`<div class="chw"><div class="chh"><b>${esc(title)}</b><span class="ro" data-js data-c="${key}"></span></div><div class="ch${big?" big":""}" tabindex="0" role="img" aria-label="${esc(aria)}" data-c="${key}" data-g="${grp}"><svg viewBox="0 0 200 ${H}" preserveAspectRatio="none" aria-hidden="true">${plot(series,lo,hi,H,step)}${ref}<line class="xh" data-js x1="-9" x2="-9" y1="0" y2="${H}"/></svg><span class="mx">${mxl}</span><span class="mn">${mnl}</span></div><div class="ax"><span>-60m</span><span>now</span></div></div>`}
function hostCharts(m,h){if(!isO(h)||!Array.isArray(h.t)||h.t.length<2)return"";const g="h-"+slug(m.name),n=h.t.length,cpu=arr(h.cpu).length===n?h.cpu:[],mem=arr(h.mem).length===n?h.mem:[];let out="";
 const tm=i=>clock(new Date(h.t[i]*1000));
 if(cpu.length>1){const pk=Math.max(1,...cpu),now=cpu[cpu.length-1];out+=chart(g+"-cpu",g,"CPU",[{v:cpu}],0,pk,pct(pk),"0%",`${pct(now)} now · peak ${pct(Math.max(...cpu))}`,i=>`${pct(cpu[i])} · ${tm(i)}`,h.t,0,`CPU load last hour, now ${pct(now)}, peak ${pct(Math.max(...cpu))} of cores`)}
 if(mem.length>1){let lo=Math.min(...mem)-.05,hi=Math.max(...mem)+.05;if(hi-lo<.2){const mid=(hi+lo)/2;lo=mid-.1;hi=mid+.1}lo=Math.max(0,lo);hi=Math.min(1,Math.max(hi,lo+.2));const now=mem[mem.length-1];
  out+=chart(g+"-mem",g,"RAM",[{v:mem}],lo,hi,pct(hi),pct(lo),`${pct(now)} now`,i=>`${pct(mem[i])} · ${tm(i)}`,h.t,0,`RAM used last hour, now ${pct(now)}, range ${pct(Math.min(...mem))} to ${pct(Math.max(...mem))}`)}
 return out?`<div class="chr">${out}</div>`:""}
function histHTML(s){const h=s.history.jobs;if(!h)return"";const r=h.running,q=h.queued,tot=r.map((v,i)=>v+(q[i]||0)),pk=Math.max(1,...tot),n=r.length;
 const tm=i=>clock(new Date(h.t[i]*1000)),f=i=>`${r[i]} running · ${q[i]||0} queued · ${tm(i)}`;
 const c=chart("q","q","",[{v:tot,cls:"w"},{v:r}],0,pk,pk,"0",`now ${r[n-1]} running · ${q[n-1]||0} queued · peak ${Math.max(...tot)}`,f,h.t,1,`Jobs last hour: now ${r[n-1]} running and ${q[n-1]||0} queued, peak ${Math.max(...tot)} total`,true);
 return`<section class="card" data-k="hist"><div class="mh"><h3>Jobs, last hour</h3><span class="r"><span><i class="dot busy"></i>running</span><span><i class="dot warn"></i>queued</span></span></div><div style="padding:6px 16px 14px">${c}</div></section>`}
function readout(c,i){const e=document.querySelector(`.ro[data-c="${c}"]`);if(e)e.textContent=CH[c].fmt(i)}
function setXH(g,f){for(const el of document.querySelectorAll(`.ch[data-g="${g}"]`)){const c=CH[el.dataset.c];if(!c)continue;const i=Math.round(f*(c.n-1)),x=(i*200/(c.n-1)).toFixed(1),l=el.querySelector(".xh");l.setAttribute("x1",x);l.setAttribute("x2",x);readout(el.dataset.c,i)}}
function clearXH(g){for(const el of document.querySelectorAll(g?`.ch[data-g="${g}"]`:".ch")){const l=el.querySelector(".xh");l.setAttribute("x1",-9);l.setAttribute("x2",-9)}refreshRo()}
function refreshRo(){for(const k in CH){const e=document.querySelector(`.ro[data-c="${k}"]`);if(e)e.textContent=CH[k].def}}
function applyHV(){refreshRo();if(HV&&document.querySelector(`.ch[data-g="${HV.g}"]`))setXH(HV.g,HV.f);else HV=null}
function hoverAt(e){const c=e.target.closest&&e.target.closest(".ch");if(!c){if(HV&&(e.type==="pointerdown"||e.pointerType==="mouse")){const g=HV.g;HV=null;clearXH(g)}return}
 const r=c.getBoundingClientRect(),f=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));if(HV&&HV.g!==c.dataset.g)clearXH(HV.g);HV={g:c.dataset.g,f};setXH(HV.g,f)}
document.addEventListener("pointermove",hoverAt);document.addEventListener("pointerdown",hoverAt);
document.addEventListener("keydown",e=>{const c=e.target.closest&&e.target.closest(".ch");if(!c||(e.key!=="ArrowLeft"&&e.key!=="ArrowRight"))return;e.preventDefault();const n=CH[c.dataset.c].n;let f=HV&&HV.g===c.dataset.g?HV.f:1;f=Math.max(0,Math.min(1,f+(e.key==="ArrowRight"?1:-1)/(n-1)));HV={g:c.dataset.g,f};setXH(HV.g,f)});
/* ---- bars ---- */
function meter(label,val,frac,warnAt,critAt,lv,extra){frac=Math.max(0,Math.min(1,frac));const cue=lv==="crit"?"✕ Critical":lv==="warn"?"▲ High":"";
 return`<div class="mt"><div class="l"><b>${label}</b><span class="v">${val}${cue?`<em class="${lv}">${cue}</em>`:""}</span></div><div class="bar ${lv||"ok"}" role="img" aria-label="${esc(label.replace(/<[^>]+>/g,""))} ${Math.round(frac*100)} percent full${cue?", "+cue.slice(2).toLowerCase():""}"><i style="width:${(frac*100).toFixed(1)}%"></i>${extra||""}<s style="left:${warnAt*100}%"></s><s class="c" style="left:${critAt*100}%"></s></div></div>`}
function hostHTML(m,s){const st=m.stats,h=s.history.machines[m.name],c=m.counts,id="m-"+slug(m.name);let body="";
 const head=`<div class="mh"><h3>${esc(m.name)}</h3><span class="r">${c.busy?`<span><i class="dot busy"></i>${c.busy} busy</span>`:""}${c.idle?`<span><i class="dot ok"></i>${c.idle} idle</span>`:""}${c.offline?`<span style="color:var(--crit)"><i class="dot crit"></i>${c.offline} offline</span>`:""}</span></div>`;
 if(!st)body=`<div class="note mut">${ic("plug")}<span>${m.configured_agent?"Waiting for the first report from this machine.":"This machine does not report stats."}</span></div>`;
 else if(st.error)body=`<div class="note warn">${ic("alert")}<span><b>No stats from this machine.</b> ${esc(st.error)}. Bars and charts come back when it reports again.</span></div>`;
 else{let ms="";const mem=st.memory;
  if(mem&&mem.total){const u=mem.used/mem.total,cp=(mem.compressed||0)/mem.total;
   ms+=meter("Memory",`${bytes(mem.used)} of ${bytes(mem.total)}${cp>.005?` · ${bytes(mem.compressed)} compressed`:""}`,u,.8,.92,lvlOf(u,.8,.92),cp>.005?`<i class="hat" style="left:${((u-cp)*100).toFixed(1)}%;width:${(cp*100).toFixed(1)}%"></i>`:"").replace(/<i style="width:([\d.]+)%"><\/i>/,(_,w)=>`<i style="width:${cp>.005?((u-cp)*100).toFixed(1):w}%"></i>`)}
  if(st.load&&num(st.load[0])!=null&&num(st.cores)){const r=st.load[0]/st.cores;ms+=meter("CPU load",`${st.load[0].toFixed(1)} on ${st.cores} cores`,r/1.25,.85/1.25,1/1.25,lvlOf(r,.85,1))}
  for(const d of st.disks){if(!num(d.total)||num(d.used)==null)continue;const u=d.used/d.total,f=(num(d.free)??d.total-d.used)/d.total;ms+=meter(`Disk <span class="mono" style="font-weight:500;color:var(--muted)">${esc(d.path)}</span>`,`${bytes(num(d.free)??d.total-d.used)} free of ${bytes(d.total)}`,u,.9,.95,f<.05?"crit":f<.1?"warn":"")}
  body=`<div class="meters">${ms}</div>`+hostCharts(m,h);
  const st2={};for(const r of m.runners||[])st2[r.name]=r.status;const inVm=new Set(),cnt=ns=>{let b=0,i=0,o=0;for(const n of ns){const x=st2[n];x==="busy"?b++:x==="idle"?i++:x==="offline"&&o++}return[b?b+" busy":"",i?i+" idle":"",o?`<span style="color:var(--crit)">✕ ${o} offline</span>`:""].filter(Boolean).join(" · ")};
  let vm="";for(const v of st.vms||[]){(v.runners||[]).forEach(n=>inVm.add(n));const run=v.status==="Running";
   vm+=`<div class="vm${run?"":" stop"}"><i class="dot ${run?(( v.jobs||[]).length?"busy":"ok"):"warn"}"></i><b>${esc(v.name)}</b><span class="s">${esc(v.cpus)} CPU · ${bytes(v.memory)}</span><span class="w">${run?(cnt(v.runners||[])||"no runners"):"▲ "+esc(v.status)+((v.runners||[]).length?" · "+pl(v.runners.length,"runner")+" down":"")}</span></div>`}
  const hostOnly=(m.runners||[]).filter(r=>!inVm.has(r.name)).map(r=>r.name);if(hostOnly.length)vm+=`<div class="vm"><i class="dot ok"></i><b>Not in a VM</b><span class="w">${cnt(hostOnly)}</span></div>`;
  body+=vm?`<div class="vms">${vm}</div>`:`<div style="height:12px"></div>`}
 return`<section class="card" id="${id}" data-k="${id}">${head}${body}</section>`}
function githubHTML(s){const r=s.rate,errs=(s.errors||[]).map(e=>`<div class="note crit" style="margin:0">${ic("x")}<span>${esc(e)}</span></div>`).join("");const k=[];
 if(r&&r.used_by_page_last_hour!=null)k.push(`<span><b>${esc(r.used_by_page_last_hour)}</b> calls to GitHub by this page in the last hour${r.free_304s!=null?`, plus ${esc(r.free_304s)} answered from cache at no cost`:""}.</span>`);
 if(r&&num(r.reset))k.push(`<span>API calls reset at <b>${clock(new Date(r.reset*1000))}</b>.</span>`);
 if(s.token)k.push(`<span>Reading GitHub with ${esc(s.token)}.</span>`);
 return`<section class="card" data-k="gh"><div style="padding:12px 16px 4px;display:grid;gap:8px">${errs||`<div class="note ok" style="margin:0">${ic("check")}<span>GitHub is reachable.</span></div>`}</div><div class="gk">${k.join("")||'<span>No usage data yet.</span>'}</div></section>`}
/* ---- activity ---- */
const prs=j=>(j.prs||[]).length?j.prs.map(x=>`<a class="pr" href="${esc(url(x.url))}">${ic("pr")}PR #${esc(x.number)}</a>`).join(""):(j.branch?`<code>${esc(j.branch)}</code>`:"");
const timeCls=(m,w,c)=>m==null?"":m>=c?" vlong":m>=w?" long":"";
function offRow(x){const r=x.r,w=r.why,k=kindOf(w),[lab,icn,,icc]=KIND[k],cz=w&&CAUSE[w.cause]||["",""];
 let b=`<div class="ln1"><span class="st ${k}">${ic(icn)}${lab}</span><b class="mono" style="font-size:13px">${esc(r.name)}</b></div><div class="meta" style="margin-top:2px">${locOf(x)}${cz[0]?" · "+esc(cz[0]):""}</div>`;
 if(!w){const vmo=x.vm&&arr(x.m.stats&&x.m.stats.vms).find(v=>v.name===x.vm),hint=vmo&&vmo.status!=="Running"?` Its VM ${esc(x.vm)} is ${esc(String(vmo.status).toLowerCase())}.`:x.m.stats&&x.m.stats.error?" This machine is not reporting stats either.":"";b+=`<div class="why">Offline, no cause reported yet.${hint}</div>`}
 else{b+=`<div class="why">${esc(w.detail)}</div>`;
  if(w.action)b+=`<div class="last">${w.at?esc(w.at)+" · ":""}auto-recovery ran <code>${esc(w.action)}</code> → <span class="${k==="rec"?"good":"bad"}">${esc(w.result||"no result yet")}</span>${w.tries?` · ${pl(w.tries,"try","tries")} this hour`:""}</div>`;
  else if(k==="down")b+=`<div class="last">No automatic fix. ${esc(cz[1])}.</div>`;
  if(k==="gave")b+=`<div class="todo">${ic("alert")}<span><b>Needs you.</b> The watchdog stopped retrying. ${esc(cz[1])}; it stays offline until then.</span></div>`}
 return`<li class="row k-${k}" id="r-${slug(r.name)}" data-k="o-${esc(r.name)}"><span class="ic ${icc}">${ic(icn==="refresh"?"clock":icn)}</span><div class="m">${b}</div></li>`}
function workRow(x,ld){const r=x.r,j=r.job;TK["w-"+r.name]=j&&j.age_min!=null?j.age_min*60:null;
 const head=j?`<div class="jt"><span class="rn">${esc(r.name)}</span><span class="ar" aria-hidden="true">→</span><a href="${esc(url(j.url))}">${esc(j.workflow)} <span class="sub">/ ${esc(j.name)}</span></a></div><div class="meta"><span class="repo">${esc(j.repo)}</span>${prs(j)}<span>${locOf(x)}</span></div>`
  :`<div class="jt"><span class="rn">${esc(r.name)}</span><span class="ar">→</span>${ld?'<span class="shimmer"></span>':"<span class=\"sub\">job not in the latest sweep</span>"}</div><div class="meta"><span>${locOf(x)}</span></div>`;
 return`<li class="row" data-k="w-${esc(r.name)}"><span class="ic busy">${ic("play")}</span><div class="m">${head}</div><div class="tmw${j?timeCls(j.age_min,60,180):""}"><b class="tm" data-js data-tk="w-${esc(r.name)}">${j?"":"…"}</b><small>running</small></div></li>`}
function waitRow(j,i){const key="q-"+i+"-"+j.repo+"-"+j.name;TK[key]=j.age_min!=null?j.age_min*60:null;
 return`<li class="row" data-k="${esc(key)}"><span class="ic ${(j.age_min||0)>=20?"q":""}">${ic(j.hosted?"cloud":"clock")}</span><div class="m"><div class="jt"><a href="${esc(url(j.url))}">${esc(j.workflow)} <span class="sub">/ ${esc(j.name)}</span></a></div><div class="meta"><span class="repo">${esc(j.repo)}</span>${prs(j)}${(j.labels||[]).map(l=>`<span class="tag">${esc(l)}</span>`).join("")}${j.hosted?'<span class="tag">GitHub-hosted</span>':""}${j.status!=="queued"?`<span class="tag">${esc(j.status)}</span>`:""}</div></div><div class="tmw${timeCls(j.age_min,20,60)}"><b class="tm" data-js data-tk="${esc(key)}"></b><small>waiting</small></div></li>`}
const GH=(id,icn,t,n,hint)=>`<div class="gh" id="${id}" data-k="${id}"><h3>${ic(icn)}${t}</h3><span class="c">${n}</span>${hint?`<span class="hint">${hint}</span>`:""}</div>`;
function actHTML(s){const fl=flat(s),ld=s.loading;TK={};let h="";
 const hit=x=>match([x.r.name,x.m.name,x.vm,(x.r.job||{}).repo,(x.r.job||{}).workflow,(x.r.job||{}).name,((x.r.job||{}).prs||[]).map(p=>"#"+p.number+" pr"+p.number).join(" "),(x.r.job||{}).branch].join(" "));
 if(blind(s))return`<div class="card"><div class="note crit" style="margin-top:14px">${ic("x")}<span><b>Unknown until GitHub can be read.</b> Fix the GitHub problem below; this fills in on the next refresh. Machine stats keep updating.</span></div></div>`;
 const off=fl.filter(x=>x.r.status==="offline"&&hit(x)).sort((a,b)=>KIND[kindOf(a.r.why)][2]-KIND[kindOf(b.r.why)][2]);
 const work=fl.filter(x=>x.r.status==="busy"&&hit(x)).sort((a,b)=>((b.r.job||{}).age_min||0)-((a.r.job||{}).age_min||0));
 const wait=(s.jobs||[]).filter(j=>j.status!=="in_progress"&&match([j.repo,j.workflow,j.name,(j.prs||[]).map(p=>"#"+p.number).join(" "),j.branch].join(" ")));
 const idle=fl.filter(x=>x.r.status==="idle"&&hit(x));
 const nothing=!FLT&&!ld&&!(s.jobs||[]).length&&!fl.some(x=>x.r.status==="busy");
 if(off.length)h+=GH("sec-off","off","Offline",off.length,"most urgent first")+`<ul class="ul">${off.map(offRow).join("")}</ul>`;
 if(nothing)h+=GH("sec-work","pause","Working",0,"")+`<p class="calm" id="sec-wait">${ic("check")}Nothing running, nothing waiting. ${pl(fl.filter(x=>x.r.status==="idle").length,"runner")} ready for the next push.</p>`;
 else{h+=GH("sec-work","play","Working",work.length,"longest first")+(work.length?`<ul class="ul">${work.map(x=>workRow(x,ld)).join("")}</ul>`:`<p class="empty">${FLT?"No match.":"Nothing running right now."}</p>`);
  h+=GH("sec-wait","clock","Waiting for a runner",ld?"…":wait.length,"oldest first")+(ld?`<p class="empty"><span class="shimmer"></span><br>Checking every repo for queued jobs. Runners and machines are already live.</p>`:wait.length?`<ul class="ul">${wait.map(waitRow).join("")}</ul>`:`<p class="empty">${FLT?"No match.":"Nothing waiting for a runner."}</p>`)}
 if(idle.length){const g=new Map();for(const x of idle){const k=locOf(x);if(!g.has(k))g.set(k,[]);g.get(k).push(x.r.name)}
  h+=`<details class="sec" id="sec-idle" data-k="sec-idle"${op("sec-idle",nothing?1:0)}><summary><h3>${ic("pause")}Idle</h3><span class="c" style="color:var(--muted)">${idle.length}</span><span class="r"><span class="sw"></span>${ic("chev","chev")}</span></summary><div class="ig">${[...g].map(([k,ns])=>`<div class="igg"><span class="igl">${k}</span><div class="chips">${ns.map(n=>`<span class="chip"><i class="dot ok"></i>${esc(n)}</span>`).join("")}</div></div>`).join("")}</div></details>`}
 if(FLT&&!off.length&&!work.length&&!wait.length&&!idle.length)h=`<p class="empty" style="padding-top:14px">Nothing matches "${esc(FLT)}".</p>`;
 return`<div class="card">${h}</div>`}
/* ---- render ---- */
/* a malformed section is dropped, never the whole page */
function safe(f){try{return f()}catch(e){console.warn("section skipped:",e&&e.message);return""}}
function render(s){S=s=norm(s);CH={};const h=heroData(s);
 updMs=s.updated?new Date(s.updated).getTime():NaN;if(isNaN(updMs))updMs=Date.now()-skew;
 const hero=$("hero"),two=h.al.length>1||!!h.ok;hero.className="hero "+h.tone+(two?" two":"");
 mount(hero,safe(()=>heroHTML(s,h)));mount($("tiles"),safe(()=>tilesHTML(s,h)));$("tiles").dataset.n=$("tiles").children.length;fade();
 mount($("act"),safe(()=>actHTML(s)));
 mount($("hostl"),s.machines.map(m=>safe(()=>hostHTML(m,s))).join(""));
 mount($("ghc"),safe(()=>githubHTML(s)));mount($("hist"),safe(()=>histHTML(s)));
 const fl=flat(s),bl=blind(s),bz=fl.filter(x=>x.r.status==="busy").length;
 $("actc").textContent=bl?"status unknown":bz+" working · "+(s.loading?"queue loading":s.jobs.filter(j=>j.status!=="in_progress").length+" waiting");
 $("hostc").textContent=pl(s.machines.length,"machine")+(bl?"":" · "+pl(fl.length,"runner"));
 document.title=(h.tone==="ok"?"":"("+h.head+") ")+"Runner Status";
 $("foot").innerHTML="<p>"+esc(s.org||"")+". Refreshes every 15 s.</p>";
 const fl2=flat(s);quiet=!s.loading&&!blind(s)&&!fl2.some(x=>x.r.status==="busy")&&!s.jobs.some(j=>j.status!=="in_progress");
 balance();tickAll()}
/* desktop: park GitHub + chart in whichever column is shorter (hysteresis avoids flip-flop) */
/* tiles: edge fade tells you the strip scrolls */
function fade(){const t=$("tiles"),m=t.scrollWidth-t.clientWidth;t.dataset.fade=(t.scrollLeft>4?"l":"")+(t.scrollLeft<m-4?"r":"")}
$("tiles").addEventListener("scroll",fade,{passive:true});
function balance(){const ex=$("extra"),A=document.querySelector(".colA"),B=document.querySelector(".colB"),two=matchMedia("(min-width:981px)").matches;
 $("cols").classList.toggle("quiet",quiet&&two);
 if(!two||quiet){if(ex.parentNode!==B)B.appendChild(ex);return}
 const cur=ex.parentNode,hA=A.offsetHeight-(cur===A?ex.offsetHeight+12:0),hB=B.offsetHeight-(cur===B?ex.offsetHeight+12:0);
 const want=hA+160<hB?A:hB+160<hA?B:cur===A?A:B;if(want!==cur)want.appendChild(ex)}
addEventListener("resize",()=>{if(S)balance();fade()});
function tickTimers(){const now=Date.now()-skew,base=Math.max(0,(now-updMs)/1000);for(const e of document.querySelectorAll("[data-tk]")){const a=TK[e.dataset.tk];if(a==null)continue;const t=elapsed(a+base);if(e.textContent!==t)e.textContent=t}}
function tickAll(){tickTimers();applyHV();tickFresh()}
function tickFresh(){const fr=$("fresh"),tx=$("freshTx");if(!S)return;
 const age=Math.max(0,(Date.now()-skew-updMs)/1000);let cls="",t;
 if(failing){cls="lost";t="Connection lost"}else if(age>360){cls="stale";t="Stale · "+ago(age).replace(" ago"," old")}else t="Live · "+ago(age);
 fr.className="fresh "+cls;if(tx.textContent!==t)tx.textContent=t;
 const lb=$("lost"),w=lb.firstElementChild;let m="";
 if(failing){lb.className="lostbar";m=`${ic("plug")}<span><b>Connection lost.</b> Retrying every 15 s. Showing the last data from ${updMs?clock(new Date(updMs)):"never"}${lastErr?" ("+esc(lastErr)+")":""}.</span>`}
 else if(age>600){lb.className="lostbar stalebar";m=`${ic("clock")}<span><b>This snapshot is ${ago(age).replace(" ago"," old")}.</b> The server answers but has not refreshed since ${clock(new Date(updMs))}. Treat everything as possibly out of date.</span>`}
 if(m){lb.hidden=false;if(w._h!==m){w._h=m;w.innerHTML=m}}else lb.hidden=true;
 document.documentElement.style.scrollPaddingTop=($("top").offsetHeight+8)+"px"}
async function tick(){try{const r=await fetch("api/state",{cache:"no-store"});if(!r.ok)throw new Error("HTTP "+r.status);
  const d=r.headers.get("Date"),s=await r.json();if(d){const sv=new Date(d).getTime();if(!isNaN(sv))skew=Date.now()-sv}
  failing=0;lastErr="";try{render(s)}catch(x){console.warn("render failed:",x&&x.message)}}
 catch(e){failing++;lastErr=e.message||"network error";
  if(!S){const hero=$("hero");hero.className="hero crit";hero.innerHTML=`<div class="vrow"><div class="vicon">${ic("plug")}</div><div><h1 class="verdict">Can't reach the status server</h1><p class="vsub">Retrying every 15 s.</p></div></div>`;S=null;$("freshTx").textContent="Connection lost";$("fresh").className="fresh lost";const lb=$("lost");lb.hidden=true}
  else tickFresh()}}
tick();setInterval(tick,15000);setInterval(tickAll,1000);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)tick()});
/* keyboard */
const flt=$("flt");flt.addEventListener("input",()=>{FLT=flt.value.trim().toLowerCase();if(S)mount($("act"),actHTML(S)),tickAll()});
flt.addEventListener("keydown",e=>{if(e.key==="Escape"){flt.value="";FLT="";if(S)mount($("act"),actHTML(S)),tickAll();flt.blur()}});
$("helpb").onclick=()=>$("help").showModal();
document.addEventListener("keydown",e=>{if(e.metaKey||e.ctrlKey||e.altKey)return;const t=e.target.tagName;if(t==="INPUT"||t==="TEXTAREA"||t==="SELECT")return;
 if(e.key==="/"){e.preventDefault();flt.focus();flt.select()}
 else if(e.key==="t")cycleTheme();
 else if(e.key==="?"){const d=$("help");d.open?d.close():d.showModal()}
 else if(e.key==="i"){const d=$("sec-idle");if(d){d.open=!d.open;if(d.open)d.scrollIntoView({block:"nearest"})}}
 else if(e.key==="a"){const more=$("ag-more");if(more&&!more.open)more.open=true;const all=[...document.querySelectorAll(".ags details.ag")],open=all.some(d=>!d.open);all.forEach(d=>d.open=open);$("hero").scrollIntoView({block:"start"})}});
</script></body></html>
"""


def make_handler(get_body, post_body=None):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 (stdlib name)
            if post_body is None:
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > PUSH_MAX_BYTES:
                self.send_error(413)
                return
            code, text = post_body(self.path.split("?")[0], self.headers, self.rfile.read(length))
            data = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 (stdlib name)
            path = self.path.split("?")[0]
            body, ctype = get_body(path)
            if body is None:
                self.send_error(404)
                return
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):  # quiet access log
            pass

    return Handler


class Notifier:
    """macOS banner on the machine running the dashboard when a new alert appears."""

    def __init__(self, enabled: bool):
        self.enabled = enabled and platform.system() == "Darwin"
        self.seen: set[str] = set()

    def update(self, alerts: list[dict]) -> None:
        current = {a["text"] for a in alerts}
        for text in sorted(current - self.seen):
            if self.enabled:
                script = f'display notification {json.dumps(text)} with title "Runner status"'
                subprocess.run(["/usr/bin/osascript", "-e", script], check=False,
                               capture_output=True, timeout=10)
        self.seen = current  # bounded: only alerts that are active right now


def push_receiver(poller: "Poller"):
    """POST /api/push handler: accepts stats only with the shared push key,
    only for machines configured as "push", and only known fields."""
    import hmac

    def handle(path: str, headers, body: bytes) -> tuple[int, str]:
        if path != "/api/push":
            return 404, "not found"
        key = read_push_key()
        if not key:  # fail closed: no key on the dashboard means pushes are off
            return 403, f"push disabled: no push key in {PUSH_KEY_FILE} on the dashboard"
        if not hmac.compare_digest(headers.get("X-Push-Key", "").encode(), key.encode()):
            return 403, "wrong or missing push key"
        try:
            data = json.loads(body.decode())
        except (UnicodeDecodeError, ValueError):
            return 400, "body must be JSON"
        name = data.get("name") if isinstance(data, dict) else None
        if name not in poller.push_names():
            return 403, f"machine {name!r} is not configured with \"agent\": \"push\""
        if not isinstance(data.get("stats"), dict):
            return 400, "missing stats"
        poller.accept_push(name, sanitize_stats(data["stats"]))
        return 200, "ok"

    return handle


def push(args) -> None:
    """Send this Mac's stats to the dashboard every --interval seconds.
    Outbound only: nothing listens on this machine."""
    cfg = load_config(args.config)
    url = args.to.rstrip("/") + "/api/push"
    stop = threading.Event()
    print(f"Pushing stats as {args.name!r} to {url} every {args.interval}s", flush=True)
    while not stop.is_set():
        payload = json.dumps({"name": args.name,
                              "stats": collect_stats(cfg["disk_paths"])}).encode()
        headers = {"Content-Type": "application/json"}
        key = read_push_key()
        if key:
            headers["X-Push-Key"] = key
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            print(f"push rejected: {exc.code} {exc.read().decode(errors='replace')}", flush=True)
        except (urllib.error.URLError, OSError) as exc:
            print(f"push failed: cannot reach the Studio page at {url} ({exc}). The page "
                  "must listen on the network (serve --bind 0.0.0.0, the default), not "
                  "only on 127.0.0.1, and the Studio must be awake and on the same LAN.",
                  flush=True)
        try:
            stop.wait(args.interval)
        except KeyboardInterrupt:
            break


def next_wait(raw: dict, poll_seconds: int) -> int:
    """Seconds until the next poll: soon while GitHub is unreadable (one call
    per try), slow when the hourly API quota is running low, else normal."""
    if raw.get("blocked"):
        return min(poll_seconds, ERROR_RETRY_SECONDS)
    rate = raw.get("rate") or {}
    if rate.get("remaining") is not None and rate.get("limit"):
        if rate["remaining"] < rate["limit"] * LOW_QUOTA_FRACTION:
            return max(poll_seconds, LOW_QUOTA_POLL_SECONDS)
    return poll_seconds


def serve(args) -> None:
    cfg = load_config(args.config)
    token, source = (None, "") if args.demo else read_token()
    poller = Poller(cfg, GitHub(token, source) if token else None, demo=args.demo,
                    token_source=source)
    notifier = Notifier(args.notify)

    def loop():
        while not poller.stop.is_set():
            raw = poller.poll_once()
            notifier.update(poller.snapshot().get("alerts", []))
            wait = next_wait(raw, cfg["poll_seconds"])
            poller.stop.wait(wait)

    threading.Thread(target=loop, daemon=True, name="poller").start()

    def body(path):
        if path in ("/", "/index.html"):
            return PAGE, "text/html; charset=utf-8"
        if path == "/api/state":
            return json.dumps(poller.snapshot()), "application/json"
        return None, ""

    srv = ThreadingHTTPServer((args.bind, args.port),
                              make_handler(body, push_receiver(poller)))
    print(f"Runner status page on http://{args.bind}:{args.port}/", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop.set()
        srv.server_close()


def agent(args) -> None:
    cfg = load_config(args.config)
    cache: dict = {"at": 0.0, "body": ""}
    mu = threading.Lock()  # protects cache

    def body(path):
        if path != "/stats":
            return None, ""
        with mu:
            if time.time() - cache["at"] > 10:  # at most one collection per 10s
                cache["body"] = json.dumps(collect_stats(cfg["disk_paths"]))
                cache["at"] = time.time()
            return cache["body"], "application/json"

    srv = ThreadingHTTPServer((args.bind, args.port), make_handler(body))
    print(f"Stats agent on http://{args.bind}:{args.port}/stats", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


LAUNCHD = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.ghostnet.runner-status.{mode}</string>
  <key>ProgramArguments</key><array>
    <string>{python}</string><string>{script}</string>{extra}
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{home}/Library/Logs/runner-status-{mode}.log</string>
  <key>StandardErrorPath</key><string>{home}/Library/Logs/runner-status-{mode}.log</string>
</dict></plist>
"""


def launchd(args) -> None:
    extra = "".join(f"<string>{html.escape(a)}</string>" for a in [args.mode, *args.extra])
    print(LAUNCHD.format(mode=args.mode, python=sys.executable, script=os.path.abspath(__file__), extra=extra,
                         home=os.path.expanduser("~")))


def demo_raw() -> dict:
    """Fake but realistic data for the screenshot and for trying the page."""
    now = utcnow()

    def ago(minutes):
        return datetime.fromtimestamp(now.timestamp() - minutes * 60, timezone.utc).isoformat()

    def runner(i, name, status, busy, labels):
        return {"id": i, "name": name, "os": "macOS" if "macOS" in labels else "Linux",
                "status": status, "busy": busy, "labels": [{"name": x} for x in labels]}

    mac = ["self-hosted", "macOS", "ARM64"]
    lin = ["self-hosted", "Linux", "ARM64"]
    bld = ["self-hosted", "openwrt-build"]
    runners = [runner(i, f"studio-mac-{i}", "online", i < 3, mac) for i in range(1, 6)]
    runners += [runner(10 + i, f"gh-ubuntu-{i}", "online", i == 1, lin) for i in range(1, 6)]
    runners += [runner(20, "studio-build-1", "online", True, bld),
                runner(21, "studio-build-2", "offline", False, bld),
                runner(30, "macbook-pro-build-1", "online", False, bld)]
    jobs = [
        {"repo": "firmware", "workflow": "Build firmware (Mac pilot)", "name": "build (bcm27xx)",
         "status": "in_progress", "labels": bld, "runner_name": "studio-build-1",
         "head_branch": "main", "started_at": ago(74), "html_url": "#", "prs": [56]},
        {"repo": "firmware", "workflow": "Build PR", "name": "build (mediatek/filogic)",
         "status": "queued", "labels": ["ubuntu-latest"], "created_at": ago(41), "html_url": "#"},
        {"repo": "luci", "workflow": "Manet merge gate", "name": "gate", "status": "in_progress",
         "labels": mac, "runner_name": "studio-mac-1", "started_at": ago(3), "html_url": "#",
         "prs": [7]},
        {"repo": "openmanetd", "workflow": "CodeQL", "name": "Analyze (go)",
         "status": "in_progress", "labels": lin, "runner_name": "gh-ubuntu-1",
         "started_at": ago(9), "html_url": "#"},
    ]
    for j in jobs:
        j["branch"] = j.pop("head_branch", "claude/pr-branch")
    gib = 1024 ** 3
    stats = {"Mac Studio": {
        "cores": 12, "load": [7.4, 6.1, 5.0],
        "memory": {"total": 32 * gib, "used": 27.5 * gib, "compressed": 3 * gib},
        "disks": [{"path": "/", "total": 994 * gib, "used": 906 * gib, "free": 88 * gib},
                  {"path": "/Volumes/NAS", "total": 7.3 * 1024 * gib, "used": 4.8 * 1024 * gib,
                   "free": 2.5 * 1024 * gib}],
        "vms": [{"name": "gh-ubuntu", "status": "Running", "cpus": 6, "memory": 6 * gib, "disk": 100 * gib},
                {"name": "gh-build", "status": "Running", "cpus": 6, "memory": 9 * gib, "disk": 60 * gib},
                {"name": "gh-build-2", "status": "Stopped", "cpus": 6, "memory": 9 * gib, "disk": 60 * gib}],
        "runner_processes": 12},
        "MacBook Pro": {
            "cores": 12, "load": [1.2, 1.5, 1.4],
            "memory": {"total": 36 * gib, "used": 19.0 * gib, "compressed": 1 * gib},
            "disks": [{"path": "/", "total": 994 * gib, "used": 610 * gib, "free": 384 * gib}],
            "vms": [{"name": "gh-build", "status": "Running", "cpus": 6, "memory": 9 * gib,
                     "disk": 60 * gib}],
            "runner_processes": 1}}
    return {"runners": runners, "jobs": jobs, "machine_stats": stats, "errors": [],
            "groups": {r["id"]: "Default" for r in runners}, "disabled_workflows": [],
            "billing": None,
            "rate": {"remaining": 4890, "limit": 5000, "reset": int(now.timestamp()) + 1800,
                     "used_by_page_last_hour": 64, "free_304s": 912}}


def demo_history(history: History, cfg: dict) -> None:
    """An hour of plausible samples so the demo's sparklines are not empty."""
    now = time.time()
    shape = {"Mac Studio": (0.55, 0.8), "MacBook Pro": (0.12, 0.5)}
    for i in range(HISTORY_POINTS - 1):
        t = now - (HISTORY_POINTS - 1 - i) * HISTORY_SPACING
        wave = math.sin(i / 9) * 0.5 + math.sin(i / 3.7) * 0.2
        for name, (cpu, mem) in shape.items():
            history.add("machine:" + name, t, max(0.02, cpu + wave * cpu * 0.6),
                        min(0.98, mem + wave * 0.04))
        history.add("jobs", t, max(0, round(1.5 + wave * 2)), max(0, round(3 + wave * 2)))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the dashboard")
    s.add_argument("--port", type=int, default=8090)
    s.add_argument("--bind", default="0.0.0.0")
    s.add_argument("--config")
    s.add_argument("--demo", action="store_true", help="fake data, no token")
    s.add_argument("--notify", action="store_true", help="macOS banner on new alerts")
    a = sub.add_parser("agent", help="serve read-only machine stats")
    a.add_argument("--port", type=int, default=8091)
    a.add_argument("--bind", default="0.0.0.0")
    a.add_argument("--config")
    pu = sub.add_parser("push", help="send this Mac's stats to the dashboard")
    pu.add_argument("--to", required=True, help="dashboard URL, e.g. http://studio.local:8090")
    pu.add_argument("--name", default="MacBook Pro", help="machine name in the dashboard config")
    pu.add_argument("--interval", type=int, default=30)
    pu.add_argument("--config")
    lp = sub.add_parser("launchd", help="print a LaunchAgent plist")
    lp.add_argument("mode", choices=["serve", "agent", "push"])
    args, extra = p.parse_known_args(argv)
    if extra and args.cmd != "launchd":
        p.error(f"unrecognized arguments: {' '.join(extra)}")
    args.extra = extra  # launchd passes these through, e.g. --notify
    {"serve": serve, "agent": agent, "push": push, "launchd": launchd}[args.cmd](args)


if __name__ == "__main__":
    main(sys.argv[1:])
