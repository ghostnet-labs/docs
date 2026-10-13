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
WATCHDOG_FILE = os.path.expanduser("~/.config/runner-status/watchdog.json")
WATCHDOG_MAX_AGE_SECONDS = 600  # an older watchdog report is ignored

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
    # Fleet hygiene alerts (see README "Alerts").
    "disk_alert_free_pct": 10,      # warn when a disk has less than this share free
    "stuck_run_hours": 4,           # a job running longer than this is called stuck
    "offline_crit_minutes": 30,     # an offline runner turns red after this long
    "flap_changes_per_hour": 4,     # online/offline flips in an hour that count as flapping
    "swap_alert_gb": 4,             # swap in use above this many GiB
    "vm_disk_alert_pct": 85,        # Lima disk image filled past this share of its size
    "no_sleep_machines": ["Mac Studio", "MacBook Pro"],  # must not sleep on power
    "runner_roots": ["~"],          # where to look for runner dirs (version check)
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
PULLS_RETRY_SECONDS = 600  # after a refused PR list, wait this long before asking again
PR_STATE_MAX = 20  # PRs whose open/closed state is checked per sweep (busy jobs only)
RUNNER_SCAN_SECONDS = 600  # rescan local runner dirs for versions this often
FLAP_WINDOW_SECONDS = 3600
RUNNER_UPDATE_GRACE_MIN = 2 * 24 * 60  # how long a new runner release may go unapplied

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
        "pressure": _num(data.get("pressure")), "sleep_ac": _num(data.get("sleep_ac")),
    }
    swap = data.get("swap")
    if isinstance(swap, dict):
        out["swap"] = {k: _num(swap.get(k)) for k in ("total", "used")}
    if isinstance(data.get("vms"), list):
        out["vms"] = [{"name": _text(v.get("name")), "status": _text(v.get("status")),
                       **{k: _num(v.get(k)) for k in ("cpus", "memory", "disk", "disk_used")}}
                      for v in data["vms"][:16] if isinstance(v, dict)]
    if isinstance(data.get("runner_services"), list):
        out["runner_services"] = [
            {"label": _text(x.get("label")), "running": bool(x.get("running")),
             "exit": _num(x.get("exit"))}
            for x in data["runner_services"][:32] if isinstance(x, dict)]
    if isinstance(data.get("runner_versions"), list):
        out["runner_versions"] = [
            {"dir": _text(x.get("dir")), "version": _text(x.get("version"), 32)}
            for x in data["runner_versions"][:32] if isinstance(x, dict)]
    orphans = data.get("orphans")
    if isinstance(orphans, list):
        out["orphans"] = [_text(x, 160) for x in orphans[:5]]
    wd = data.get("watchdog")
    if isinstance(wd, dict) and isinstance(wd.get("runners"), dict):
        out["watchdog"] = {
            "checked_at": _text(wd.get("checked_at")), "error": _text(wd.get("error"), 300),
            "runners": {str(k)[:64]: {f: _text(v.get(f), 300) for f in
                                      ("cause", "detail", "action", "result", "at")}
                        for k, v in list(wd["runners"].items())[:64] if isinstance(v, dict)}}
    return out


def read_watchdog(path: str = WATCHDOG_FILE) -> dict | None:
    """The runner watchdog's last report on this machine, if recent."""
    try:
        if time.time() - os.path.getmtime(path) > WATCHDOG_MAX_AGE_SECONDS:
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


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
                        "disk": vm.get("disk"), "dir": vm.get("dir")})
    return vms


def parse_swapusage(text: str) -> dict | None:
    """`sysctl -n vm.swapusage`: total = 2048.00M  used = 1024.50M  free = ..."""
    units = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}
    out = {}
    for key in ("total", "used"):
        m = re.search(rf"{key} = ([\d.]+)([KMGT])", text)
        if not m:
            return None
        out[key] = float(m.group(1)) * units[m.group(2)]
    return out


def parse_pmset_sleep(text: str) -> int | None:
    """System sleep minutes on AC power from `pmset -g custom` (0 = never).
    Desktops print one "AC Power:" block; laptops print battery and AC."""
    block = re.split(r"(?m)^(?=\S.*Power:)", text)
    for part in block:
        if part.startswith("AC Power:"):
            m = re.search(r"(?m)^\s+sleep\s+(\d+)", part)
            return int(m.group(1)) if m else None
    return None


def parse_launchctl(text: str) -> list[dict]:
    """Runner services from `launchctl list` (PID, last exit, label)."""
    out = []
    for line in text.splitlines():
        parts = line.split("\t") if "\t" in line else line.split()
        if len(parts) != 3 or not parts[2].startswith("actions.runner."):
            continue
        pid, status, label = parts
        out.append({"label": label, "running": pid.strip().isdigit(),
                    "exit": int(status) if status.strip().lstrip("-").isdigit() else None})
    return out


def etime_seconds(text: str) -> int:
    """ps etime: [[dd-]hh:]mm:ss -> seconds."""
    days, _, rest = text.strip().rpartition("-")
    parts = [int(p) for p in rest.split(":") if p.isdigit()]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs + (int(days) * 86400 if days.isdigit() else 0)


def find_orphans(ps_text: str, min_age_s: int = 3600) -> list[str]:
    """Job processes left behind by a finished job: re-parented to launchd or
    init (ppid 1), running from a runner _work dir, older than min_age_s."""
    found = []
    for line in ps_text.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4 or parts[1] != "1" or "/_work/" not in parts[3]:
            continue
        if "Runner." in parts[3] or etime_seconds(parts[2]) < min_age_s:
            continue
        found.append(f"pid {parts[0]} up {parts[2]}: {parts[3]}")
    return found


VERSION_RX = re.compile(rb"Version: (\d+\.\d+\.\d+)")
_runner_scan = {"at": 0.0, "found": []}
_runner_scan_mu = threading.Lock()  # protects _runner_scan


def runner_versions(roots: list[str]) -> list[dict]:
    """Version of each runner dir under roots (newest _diag/Runner_*.log).
    Walks at most 4 levels, skips ~/Library, and is cached for 10 minutes."""
    with _runner_scan_mu:
        if time.time() - _runner_scan["at"] < RUNNER_SCAN_SECONDS:
            return _runner_scan["found"]
    found = []
    for root in roots:
        root = os.path.expanduser(root)
        base = root.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath.count(os.sep) - base
            dirnames[:] = [] if depth >= 4 else [
                d for d in dirnames if d not in ("Library", "_work", "node_modules")
                and not d.startswith(".")]
            if ".runner" not in filenames:
                continue
            dirnames[:] = []
            diag = os.path.join(dirpath, "_diag")
            try:
                logs = sorted((os.path.join(diag, f) for f in os.listdir(diag)
                               if f.startswith("Runner_")), key=os.path.getmtime)
            except OSError:
                logs = []
            version = None
            if logs:
                try:
                    with open(logs[-1], "rb") as fh:
                        m = VERSION_RX.search(fh.read(8192))
                    version = m.group(1).decode() if m else None
                except OSError:
                    pass
            found.append({"dir": dirpath.replace(os.path.expanduser("~"), "~"),
                          "version": version})
            if len(found) >= 32:
                break
    with _runner_scan_mu:
        _runner_scan.update(at=time.time(), found=found)
    return found


def lima_disk_used(vm: dict) -> int | None:
    """Bytes the VM's sparse disk image really takes on the host. It grows with
    the guest's writes and only shrinks after fstrim inside the VM."""
    vm_dir = vm.get("dir") or os.path.expanduser(f"~/.lima/{vm.get('name')}")
    try:
        return os.stat(os.path.join(vm_dir, "diffdisk")).st_blocks * 512
    except OSError:
        return None


def collect_stats(disk_paths: list[str], runner_roots: list[str] | None = None) -> dict:
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
        stats["swap"] = parse_swapusage(_run(["sysctl", "-n", "vm.swapusage"]) or "")
        level = (_run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]) or "").strip()
        stats["pressure"] = int(level) if level.isdigit() else None  # 1 ok, 2 warn, 4 critical
        stats["sleep_ac"] = parse_pmset_sleep(_run(["pmset", "-g", "custom"]) or "")
        stats["runner_services"] = parse_launchctl(_run(["launchctl", "list"]) or "")
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
    for vm in stats["vms"] or []:
        vm["disk_used"] = lima_disk_used(vm)
        vm.pop("dir", None)
    ps = _run(["ps", "-axo", "pid,ppid,etime,command"]) or ""
    stats["runner_processes"] = sum(1 for line in ps.splitlines() if "Runner.Listener" in line)
    stats["orphans"] = find_orphans(ps)[:5]
    stats["runner_versions"] = runner_versions(runner_roots or ["~"])
    stats["watchdog"] = read_watchdog()
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
        # Poller thread only: runner name -> {"status", "since", "flips": deque}.
        self.history: dict[str, dict] = {}

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
                raw["runner_history"] = self.track_runners(raw["runners"], time.time())
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

    def track_runners(self, runners: list[dict], now: float) -> dict:
        """Remember when each runner went offline and how often it flipped
        between online and offline in the last hour. No extra API calls."""
        seen = set()
        for r in runners:
            name = r.get("name")
            seen.add(name)
            status = "online" if r.get("status") == "online" else "offline"
            h = self.history.get(name)
            if h is None:
                self.history[name] = {"status": status, "since": now, "flips": deque(maxlen=64)}
                continue
            if h["status"] != status:
                h.update(status=status, since=now)
                h["flips"].append(now)
            while h["flips"] and h["flips"][0] < now - FLAP_WINDOW_SECONDS:
                h["flips"].popleft()
        for name in set(self.history) - seen:  # deregistered (e.g. one-job runners)
            del self.history[name]
        return {name: {"offline_since": datetime.fromtimestamp(h["since"], timezone.utc)
                       .isoformat() if h["status"] == "offline" else None,
                       "flips_last_hour": len(h["flips"])}
                for name, h in self.history.items()}

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
        try:  # public repo, one call per 10 min, 304 when unchanged
            rel = gh.get("/repos/actions/runner/releases/latest")
            latest = {"version": str(rel.get("tag_name", "")).lstrip("v"),
                      "published_at": rel.get("published_at")}
        except (urllib.error.URLError, OSError, ValueError, AttributeError):
            latest = None
        return {"disabled_workflows": found, "billing": billing, "runner_latest": latest}

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

        def open_by_number(found: dict) -> set:
            return {(repo, n) for (repo, _), nums in found.items() for n in nums}

        def pr_state(repo, number):
            with gh.mu:
                denied_at = gh.pulls_denied.get(repo, 0)
            if time.time() - denied_at < PULLS_RETRY_SECONDS:
                return None
            try:
                pr = gh.get(f"/repos/{org}/{repo}/pulls/{number}")
            except (urllib.error.URLError, OSError, ValueError):
                with gh.mu:
                    gh.pulls_denied[repo] = time.time()
                return None
            if not isinstance(pr, dict):
                return None
            return "merged" if pr.get("merged_at") else pr.get("state")

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
            jobs = [j for chunk in pool.map(jobs_for, runs) for j in chunk]
            # A busy runner working for a PR that already merged or closed is
            # wasted (a gate waiting for checks that never come). One cached
            # call per PR; unchanged PRs answer 304 for free.
            known_open = open_by_number(open_prs)
            check = sorted({(j["repo"], n) for j in jobs if j.get("status") == "in_progress"
                            and j.get("runner_name") for n in j["prs"]
                            if (j["repo"], n) not in known_open})[:PR_STATE_MAX]
            states = dict(zip(check, pool.map(lambda rn: pr_state(*rn), check)))
            for j in jobs:
                j["closed_prs"] = [n for n in j["prs"] if states.get((j["repo"], n))
                                   in ("closed", "merged")]
            return jobs

    def fetch_agents(self, errors: list[str]) -> dict:
        stats = {}
        for m in self.cfg["machines"]:
            agent = m.get("agent")
            if not agent:
                continue
            if agent == "local":
                stats[m["name"]] = collect_stats(self.cfg["disk_paths"],
                                                 self.cfg.get("runner_roots"))
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


def offline_reason(runner: str, machine: str, st: dict, vms: dict) -> dict:
    """Why a runner is offline: the watchdog's diagnosis when it has one,
    else what the page itself can see (machine silent, VM stopped)."""
    wd = (st.get("watchdog") or {}).get("runners") or {}
    if runner in wd:
        return {k: wd[runner].get(k) for k in ("cause", "detail", "action", "result", "at")}
    if st.get("error"):
        return {"cause": "host-silent", "detail": f"{machine} is not reporting (asleep, off, or "
                "off the network): " + str(st["error"])}
    vm = next((v for v, p in vms.items() if re.search(p, runner)), None)
    status = next((x.get("status") for x in st.get("vms") or [] if x.get("name") == vm), None)
    if vm and status and status != "Running":
        return {"cause": "vm-stopped", "detail": f"VM {vm} is {status}"}
    if not st:
        return {"cause": "unknown", "detail": "no stats from that machine"}
    return {"cause": "unknown", "detail": "no watchdog report yet (is runner_watchdog.py "
            "installed on that Mac?)"}


def runner_alerts(runners: list[dict], cfg: dict) -> list[dict]:
    """Offline (red once it has lasted), and flapping runners."""
    alerts = []
    offline = [r for r in runners if r["status"] == "offline"]
    if offline:
        def describe(r):
            parts = [fmt_minutes(r["offline_min"])] if r.get("offline_min") else []
            why = r.get("why") or {}
            if why.get("detail"):
                parts.append(why["detail"])
            if why.get("action"):
                parts.append(f"auto-recovery: {why['action']} -> {why.get('result') or 'pending'}")
            return r["name"] + (f" ({'; '.join(parts)})" if parts else "")

        drained = [r for r in offline if (r.get("why") or {}).get("cause") == "maintenance"]
        faulty = [r for r in offline if r not in drained]
        if faulty:
            long_gone = [r for r in faulty
                         if (r.get("offline_min") or 0) >= cfg["offline_crit_minutes"]]
            alerts.append({"level": "crit" if long_gone else "warn",
                           "text": "Offline runners: " + ", ".join(map(describe, faulty))})
        if drained:
            alerts.append({"level": "info",
                           "text": "Draining for maintenance: " + ", ".join(map(describe, drained))})
    flapping = [r["name"] for r in runners if r.get("flips", 0) >= cfg["flap_changes_per_hour"]]
    if flapping:
        alerts.append({"level": "warn", "text":
                       f"Flapping runners (went offline and back {cfg['flap_changes_per_hour']}+ "
                       f"times in an hour): {', '.join(flapping)}"})
    return alerts


def job_alerts(jobs: list[dict], cfg: dict) -> list[dict]:
    """Jobs stuck for hours, and runners held by a job whose PR is closed."""
    alerts = []
    limit = cfg["stuck_run_hours"] * 60
    for j in jobs:
        if j["closed_prs"] and j["runner"]:
            prs = ", ".join(f"#{n}" for n in j["closed_prs"])
            alerts.append({"level": "crit", "url": j["url"], "text":
                           f"{j['runner']} is still running {j['repo']} / {j['workflow']} for "
                           f"closed or merged PR {prs} ({fmt_minutes(j['age_min'])}); "
                           "cancel the run to free the runner"})
        elif j["status"] == "in_progress" and (j["age_min"] or 0) >= limit:
            alerts.append({"level": "warn", "url": j["url"], "text":
                           f"Stuck run: {j['repo']} / {j['workflow']} / {j['name']} running "
                           f"{fmt_minutes(j['age_min'])} on {j['runner'] or '?'}"})
    return alerts


def _version_tuple(v: str | None) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])


def machine_alerts(name: str, st: dict, cfg: dict, latest: dict | None) -> list[dict]:
    """Disk, swap, memory pressure, sleep, VM disk growth, runner services,
    orphan job processes and runner version drift for one machine."""
    gib = 1024 ** 3
    alerts = []

    def warn(text, level="warn"):
        alerts.append({"level": level, "text": f"{name} {text}"})

    if st.get("error"):
        warn(f"stats missing: {st['error']}")
    for d in st.get("disks") or []:
        if d["total"] and 100 * d["free"] / d["total"] < cfg["disk_alert_free_pct"]:
            warn(f"disk {d['path']} low: {fmt_bytes(d['free'])} free")
    swap = st.get("swap") or {}
    if (swap.get("used") or 0) >= cfg["swap_alert_gb"] * gib:
        warn(f"is swapping: {fmt_bytes(swap['used'])} of swap in use")
    if st.get("pressure") in (2, 4):
        warn("memory pressure is " + ("critical" if st["pressure"] == 4 else "high"),
             "crit" if st["pressure"] == 4 else "warn")
    if name in cfg["no_sleep_machines"] and st.get("sleep_ac"):
        warn(f"sleeps after {st['sleep_ac']:.0f} min on power, which takes its runners "
             "offline; fix with: sudo pmset -c sleep 0")
    for vm in st.get("vms") or []:
        if vm.get("status") != "Running":
            warn(f"VM {vm['name']} is {vm.get('status')}")
        if vm.get("disk") and vm.get("disk_used") and \
                100 * vm["disk_used"] / vm["disk"] >= cfg["vm_disk_alert_pct"]:
            warn(f"VM {vm['name']} disk image is {fmt_bytes(vm['disk_used'])} of "
                 f"{fmt_bytes(vm['disk'])}; run the cleanup (it trims the VM disk)")
    down = [s["label"].removeprefix("actions.runner.") for s in st.get("runner_services") or []
            if not s.get("running")]
    if down:
        warn(f"runner service(s) not running: {', '.join(down)}")
    if st.get("orphans"):
        warn(f"has {len(st['orphans'])} leftover job process(es) from finished jobs: "
             f"{st['orphans'][0]}")
    newest = (latest or {}).get("version")
    old = [v for v in st.get("runner_versions") or []
           if newest and v.get("version") and _version_tuple(v["version"]) < _version_tuple(newest)]
    if old:
        warn(f"runner version behind {newest}: " +
             ", ".join(f"{v['dir']} {v['version']}" for v in old[:5]))
    return alerts


def fmt_minutes(m: float | None) -> str:
    if m is None:
        return "?"
    if m < 60:
        return f"{m:.0f}m"
    return f"{m // 60:.0f}h {m % 60:.0f}m" if m < 2880 else f"{m / 1440:.0f}d"


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
                     "closed_prs": list(j.get("closed_prs") or []),
                     "url": j.get("html_url"), "age_min": age_minutes(since, now)})
    jobs.sort(key=lambda j: (j["status"] != "queued", -(j["age_min"] or 0)))
    # What each runner is working on, from the job list already fetched (no extra calls).
    by_runner = {j["runner"]: j for j in jobs if j["runner"] and j["status"] == "in_progress"}
    history = raw.get("runner_history") or {}
    for r in sorted(raw.get("runners", []), key=lambda r: r.get("name", "")):
        status = "offline" if r.get("status") != "online" else ("busy" if r.get("busy") else "idle")
        hist = history.get(r.get("name")) or {}
        runner = {"name": r.get("name"), "status": status, "os": r.get("os"),
                  "offline_min": age_minutes(hist.get("offline_since"), now)
                  if status == "offline" else None,
                  "flips": hist.get("flips_last_hour", 0),
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
        for r in m["runners"]:
            if r["status"] == "offline":
                r["why"] = offline_reason(r["name"], m["name"], st, vm_cfg.get(m["name"], {}))
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
    alerts += runner_alerts([r for m in shown for r in m["runners"]], cfg)
    alerts += job_alerts(jobs, cfg)
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
    # Idle runners update themselves only when their next job arrives, so a new
    # release counts as drift only after it has been out for two days.
    latest = raw.get("runner_latest") or {}
    released = age_minutes(latest.get("published_at"), now)
    latest = latest if released is not None and released >= RUNNER_UPDATE_GRACE_MIN else None
    for m in shown:
        alerts += machine_alerts(m["name"], m.get("stats") or {}, cfg, latest)

    return {"updated": now.isoformat(), "org": cfg["org"], "machines": shown, "jobs": jobs,
            "alerts": alerts, "billing": billing, "rate": raw.get("rate"),
            "token": raw.get("token"), "loading": bool(raw.get("loading")),
            "errors": list(dict.fromkeys(raw.get("errors", []))),
            "counts": {"queued": sum(j["status"] == "queued" for j in jobs),
                       "running": sum(j["status"] == "in_progress" for j in jobs)}}


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Runner Status</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--text:#16181d;--muted:#5f6673;--line:#e2e5ea;
--ok:#1a7f37;--busy:#0b62d6;--warn:#9a6700;--crit:#c62828;--warnbg:#fff8e1;--critbg:#fdecea}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a20;--text:#e7e9ee;
--muted:#9aa1ad;--line:#2a2f38;--ok:#3fb950;--busy:#58a6ff;--warn:#d29922;--crit:#f85149;
--warnbg:#2b2410;--critbg:#2d1414}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1200px;margin:0 auto;padding:16px}
header{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;justify-content:space-between}
h1{font-size:20px;margin:0}h2{font-size:16px;margin:0 0 8px}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px;margin:12px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.pills{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 10px}
.pill{border-radius:99px;padding:2px 9px;font-size:12px;font-weight:600;border:1px solid var(--line)}
.idle{color:var(--ok)}.busy{color:var(--busy)}.offline{color:var(--crit)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:currentColor}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:5px 6px;
border-top:1px solid var(--line);vertical-align:top}th{font-size:12px;color:var(--muted);font-weight:600}
.labels{color:var(--muted);font-size:12px}.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--busy)}.bar>i.hot{background:var(--crit)}
.stat{display:grid;grid-template-columns:90px 1fr auto;gap:8px;align-items:center;margin:4px 0;font-size:13px}
.alert{border-radius:8px;padding:8px 12px;margin:6px 0;border:1px solid var(--line)}
.alert.warn{background:var(--warnbg);border-color:var(--warn)}.alert.crit{background:var(--critbg);border-color:var(--crit)}
.allgood{color:var(--ok);font-weight:600}a{color:var(--busy)}
.scroll{overflow-x:auto}.queued{color:var(--warn);font-weight:600}.running{color:var(--busy);font-weight:600}
</style></head><body><main>
<header><h1>Builders and runners</h1><span class="muted" id="meta"></span></header>
<div id="alerts"></div><div class="grid" id="machines"></div>
<div class="card"><h2 id="jobs-title">Jobs</h2><div class="scroll" id="jobs"></div></div>
<p class="muted" id="foot"></p></main>
<script>
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const bytes=n=>{if(n==null)return"?";const u=["B","KB","MB","GB","TB"];let i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toFixed(i<2?0:1)+" "+u[i]};
const age=m=>m==null?"?":m<1?"<1m":m<60?Math.floor(m)+"m":m<2880?Math.floor(m/60)+"h "+Math.floor(m%60)+"m":Math.floor(m/1440)+"d";
const bar=(used,total)=>{const p=total?Math.min(100,100*used/total):0;return `<div class="bar"><i class="${p>90?"hot":""}" style="width:${p}%"></i></div>`};
function jobLine(j){
  const prs=(j.prs||[]).map(p=>`<a href="${esc(p.url)}">PR #${esc(p.number)}</a>`).join(", ");
  return `<a href="${esc(j.url)}">${esc(j.workflow)} / ${esc(j.name)}</a><br><span class="labels">${esc(j.repo)} · ${prs||esc(j.branch)} · ${age(j.age_min)}</span>`}
function machine(m){
  const c=m.counts,st=m.stats||{};let h=`<div class="card"><h2>${esc(m.name)}</h2><div class="pills">
  <span class="pill idle">${c.idle} idle</span><span class="pill busy">${c.busy} busy</span>
  <span class="pill offline">${c.offline} offline</span></div>`;
  if(st.error)h+=`<p class="offline">Stats missing: ${esc(st.error)}</p>`;
  if(st.memory&&st.memory.total)h+=`<div class="stat"><span>RAM</span>${bar(st.memory.used,st.memory.total)}<span>${bytes(st.memory.used)} / ${bytes(st.memory.total)}</span></div>`;
  if(st.swap&&st.swap.total)h+=`<div class="stat"><span>Swap</span>${bar(st.swap.used,st.swap.total)}<span>${bytes(st.swap.used)} / ${bytes(st.swap.total)}</span></div>`;
  if(st.load&&st.cores)h+=`<div class="stat"><span>CPU load</span>${bar(st.load[0],st.cores)}<span>${st.load[0].toFixed(1)} / ${st.cores} cores</span></div>`;
  for(const d of st.disks||[])h+=`<div class="stat"><span>Disk ${esc(d.path)}</span>${bar(d.used,d.total)}<span>${bytes(d.free)} free</span></div>`;
  if(st.vms&&st.vms.length){h+=`<table><tr><th>VM</th><th>State</th><th>CPU</th><th>RAM</th><th>Disk</th><th>Working on</th></tr>`;
    for(const v of st.vms){const js=v.jobs||[];const busy=js.length?js.map(jobLine).join("<br>"):v.status!=="Running"?`<span class="muted">–</span>`:(v.runners&&v.runners.length?`<span class="muted">idle</span>`:`<span class="muted">–</span>`);
      h+=`<tr><td>${esc(v.name)}</td><td class="${v.status==="Running"?"idle":"offline"}">${esc(v.status)}</td><td>${esc(v.cpus)}</td><td>${bytes(v.memory)}</td><td>${v.disk_used!=null?bytes(v.disk_used)+" / ":""}${bytes(v.disk)}</td><td>${busy}</td></tr>`}
    h+=`</table>`}
  if(!m.stats&&!m.configured_agent&&m.name!=="Other runners")h+=`<p class="muted">No stats agent configured.</p>`;
  if(m.runners.length){h+=`<table style="margin-top:8px"><tr><th>Runner</th><th>State</th><th>Working on</th></tr>`;
    for(const r of m.runners){const doing=r.job?jobLine(r.job):r.status==="busy"?`<span class="muted">busy (job not in the latest sweep)</span>`:`<span class="muted">${r.status==="offline"?"offline":"idle"}</span>`;
      const w=r.why||{};const flag=(r.job&&r.job.closed_prs&&r.job.closed_prs.length?`<br><span class="offline">PR closed: cancel this run</span>`:"")+(w.detail?`<br><span class="labels">Why: ${esc(w.detail)}${w.action?` · auto-recovery: ${esc(w.action)} → ${esc(w.result||"pending")}`:""}</span>`:"");
      h+=`<tr><td>${esc(r.name)}<br><span class="labels">${esc(r.labels.join(", "))} · ${esc(r.group)}</span></td><td class="${r.status}"><span class="dot"></span>${r.status}${r.offline_min?" "+age(r.offline_min):""}</td><td>${doing}${flag}</td></tr>`}
    h+=`</table>`}else h+=`<p class="muted">No runners registered.</p>`;
  return h+`</div>`}
function render(s){
  document.getElementById("meta").textContent=`${s.org||""} · updated ${s.updated?new Date(s.updated).toLocaleTimeString():"never"} · refreshes every 15s`;
  const a=s.alerts||[];document.getElementById("alerts").innerHTML=a.length?a.map(x=>`<div class="alert ${x.level}">${x.url?`<a href="${esc(x.url)}">${esc(x.text)}</a>`:esc(x.text)}</div>`).join(""):`<p class="allgood">All runners healthy, nothing stuck.</p>`;
  document.getElementById("machines").innerHTML=(s.machines||[]).map(machine).join("");
  const c=s.counts||{queued:0,running:0};document.getElementById("jobs-title").textContent=s.loading?"Jobs: loading from GitHub…":`Jobs: ${c.queued} queued, ${c.running} running`;
  const j=s.jobs||[];document.getElementById("jobs").innerHTML=s.loading?`<p class="muted">Checking every repo for queued and running jobs. Runners and machine stats above are already live.</p>`:j.length?`<table><tr><th>State</th><th>Age</th><th>Repo</th><th>Job</th><th>Wants</th><th>Runner</th></tr>`+
   j.map(x=>`<tr><td class="${x.status==="queued"?"queued":"running"}">${x.status==="in_progress"?"running":esc(x.status)}</td><td>${age(x.age_min)}</td><td>${esc(x.repo)}</td><td><a href="${esc(x.url)}">${esc(x.workflow)} / ${esc(x.name)}</a><br><span class="labels">${(x.prs||[]).length?x.prs.map(p=>`<a href="${esc(p.url)}">PR #${esc(p.number)}</a>`).join(", "):esc(x.branch)}</span></td><td class="labels">${esc(x.labels.join(", "))}${x.hosted?" (GitHub-hosted)":""}</td><td>${esc(x.runner||"–")}</td></tr>`).join("")+`</table>`:`<p class="muted">No queued or running jobs.</p>`;
  const e=s.errors||[];document.getElementById("foot").textContent=(s.token?`Using ${s.token}. `:"")+(s.rate&&s.rate.remaining!=null?`GitHub API: ${s.rate.remaining} of ${s.rate.limit} calls left this hour${s.rate.reset?`, resets ${new Date(s.rate.reset*1000).toLocaleTimeString()}`:""}; this page used ${s.rate.used_by_page_last_hour} in the last hour (${s.rate.free_304s} more answered free from cache). `:"")+(e.length?"Problems: "+e.join(" | "):"");
}
async function tick(){try{const r=await fetch("api/state",{cache:"no-store"});render(await r.json())}catch(e){document.getElementById("meta").textContent="Status server unreachable, retrying"}}
tick();setInterval(tick,15000);
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
                              "stats": collect_stats(cfg["disk_paths"], cfg.get("runner_roots"))}).encode()
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
                cache["body"] = json.dumps(collect_stats(cfg["disk_paths"], cfg.get("runner_roots")))
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
        "swap": {"total": 3 * gib, "used": 1.2 * gib}, "pressure": 1, "sleep_ac": 0,
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
