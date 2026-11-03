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
    "jit_missing_alert_minutes": 3, # a one-job slot with no online runner this long
    "flap_changes_per_hour": 4,     # online/offline flips in an hour that count as flapping
    "swap_alert_gb": 4,             # swap in use above this many GiB
    "vm_disk_alert_pct": 85,        # Lima disk image filled past this share of its size
    "no_sleep_machines": ["Mac Studio", "MacBook Pro"],  # must not sleep on power
    "runner_roots": ["~"],          # where to look for runner dirs (version check)
    "machines": [
        {"name": "Mac Studio", "agent": "local",
         "runner_pattern": r"(?i)studio|gh-ubuntu|gh-build",
         # Lima VM name -> pattern for the runners that live inside it.
         # One-job (JIT) runners are named <slot>-<epoch> and deregister after a job.
         "vms": {"gh-ubuntu": r"(?i)^(gh-ubuntu|studio-ubuntu)",
                 "gh-build": r"(?i)^studio-build-1(-\d+)?$",
                 "gh-build-2": r"(?i)^studio-build-2(-\d+)?$"},
         # VM role for the drift check in tools/ci-hosts/verify-vm.sh.
         "vm_roles": {"gh-ubuntu": "ubuntu", "gh-build": "build", "gh-build-2": "build"},
         "jit_slots": ["studio-ubuntu-1", "studio-ubuntu-2", "studio-ubuntu-3",
                       "studio-ubuntu-4", "studio-ubuntu-5", "studio-build-1",
                       "studio-build-2"]},
        {"name": "MacBook Pro", "agent": "push",
         "runner_pattern": r"(?i)macbook|mac-dev|\bdev\b",
         "vm_roles": {"gh-build": "build"},
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
PR_STATE_MAX = 20  # active PR details per sweep; busy self-hosted jobs take priority
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
        drift = wd.get("drift") if isinstance(wd.get("drift"), dict) else {}
        out["watchdog"] = {
            "drift": {str(k)[:32]: [_text(x, 200) for x in v[:8]]
                      for k, v in list(drift.items())[:8] if isinstance(v, list)},
            "checked_at": _text(wd.get("checked_at")), "error": _text(wd.get("error"), 300),
            "runners": {str(k)[:64]: {**{f: _text(v.get(f), 300) for f in
                                         ("cause", "detail", "action", "result", "at")},
                                      "tries": _num(v.get("tries")),
                                      "gave_up": bool(v.get("gave_up"))}
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
        self.series = History()
        if demo:
            demo_history(self.series, cfg)
        # Poller thread only: runner name -> {"status", "since", "flips": deque}.
        self.history: dict[str, dict] = {}
        self.jit_seen: dict[str, float] = {}  # slot -> last time a runner of it was online

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
        self.series.record(state, time.time())
        state["history"] = self.series.export()
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
                raw["jit_missing"] = self.track_jit_slots(raw["runners"], time.time())
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

    def track_jit_slots(self, runners: list[dict], now: float) -> dict:
        """Minutes each configured one-job slot has had no online runner. Those
        runners deregister after every job, so a dead slot never shows as
        "offline"; it just stops appearing."""
        slots = [(m["name"], s) for m in self.cfg["machines"] for s in m.get("jit_slots") or []]
        online = [r.get("name") or "" for r in runners if r.get("status") == "online"]
        missing = {}
        for machine, slot in slots:
            if any(re.fullmatch(re.escape(slot) + r"(-\d+)?", n) for n in online):
                self.jit_seen[slot] = now
                continue
            first = self.jit_seen.setdefault(slot, now)  # grace from first sight
            if now - first > 0:
                missing[slot] = {"machine": machine, "minutes": (now - first) / 60}
        return missing

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
                    j["head_sha"] = run.get("head_sha")
                    j["head_repo"] = (run.get("head_repository") or {}).get("full_name")
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
            return {"state": "merged" if pr.get("merged_at") else pr.get("state"),
                    "draft": pr.get("draft") is True, "title": pr.get("title"),
                    "base": (pr.get("base") or {}).get("ref"),
                    "head": (pr.get("head") or {}).get("ref"),
                    "head_repo": ((pr.get("head") or {}).get("repo") or {}).get("full_name"),
                    "base_repo": ((pr.get("base") or {}).get("repo") or {}).get("full_name")}

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
                with gh.mu:
                    open_details[(repo, pr["number"])] = {
                        "state": "open", "draft": pr.get("draft") is True,
                        "title": pr.get("title"), "head": head.get("ref"),
                        "base": (pr.get("base") or {}).get("ref"),
                        "head_repo": (head.get("repo") or {}).get("full_name"),
                        "base_repo": ((pr.get("base") or {}).get("repo") or {}).get("full_name")}
            return found

        open_details: dict = {}
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
            priority = {(j["repo"], n) for j in jobs if j.get("status") == "in_progress"
                        and j.get("runner_name") for n in j["prs"]}
            check = sorted({(j["repo"], n) for j in jobs for n in j["prs"]
                            if (j["repo"], n) not in known_open},
                           key=lambda rn: (rn not in priority, rn))[:PR_STATE_MAX]
            states = dict(zip(check, pool.map(lambda rn: pr_state(*rn), check)))
            states.update(open_details)
            for j in jobs:
                j["pr_details"] = {str(n): states[(j["repo"], n)] for n in j["prs"]
                                   if states.get((j["repo"], n))}
                j["closed_prs"] = [n for n in j["prs"] if (states.get((j["repo"], n)) or {}).get("state")
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
                stats[m["name"]]["_updated"] = time.time()
                continue
            if agent == "push":
                with self.mu:
                    got = self.pushed.get(m["name"])
                if got is None:
                    stats[m["name"]] = {"error": "no stats pushed yet (runner_status.py push "
                                                 "not running on that Mac?)",
                                        "_updated": None}
                elif time.time() - got[1] > PUSH_STALE_SECONDS:
                    stats[m["name"]] = {
                        "error": f"no stats pushed for {int(time.time() - got[1])}s",
                        "_updated": got[1],
                    }
                else:
                    stats[m["name"]] = {**got[0], "_updated": got[1]}
                continue
            try:
                with urllib.request.urlopen(agent.rstrip("/") + "/stats", timeout=5) as resp:
                    stats[m["name"]] = json.loads(resp.read().decode())
                    stats[m["name"]]["_updated"] = time.time()
            except (urllib.error.URLError, OSError, ValueError) as exc:
                stats[m["name"]] = {"error": str(exc), "_updated": None}
        return stats


def offline_reason(runner: str, machine: str, st: dict, vms: dict) -> dict:
    """Why a runner is offline: the watchdog's diagnosis when it has one,
    else what the page itself can see (machine silent, VM stopped)."""
    wd = (st.get("watchdog") or {}).get("runners") or {}
    if runner in wd:
        return {k: wd[runner].get(k) for k in
                ("cause", "detail", "action", "result", "at", "tries", "gave_up")}
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
            if why.get("gave_up"):
                parts.append("NEEDS A HUMAN: auto-recovery gave up")
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


def jit_alerts(missing: dict, machines: list[dict], cfg: dict) -> list[dict]:
    """A one-job slot without an online runner: say why when the watchdog knows."""
    reports = {m["name"]: ((m.get("stats") or {}).get("watchdog") or {}).get("runners") or {}
               for m in machines}
    alerts = []
    for slot, info in sorted(missing.items()):
        if info["minutes"] < cfg["jit_missing_alert_minutes"]:
            continue
        why = reports.get(info["machine"], {}).get(slot) or {}
        if why.get("cause") == "maintenance":
            alerts.append({"level": "info", "text": f"Slot {slot} is draining: {why['detail']}"})
            continue
        text = f"One-job slot {slot} has had no online runner for {fmt_minutes(info['minutes'])}"
        if why.get("detail"):
            text += f": {why['detail']}"
        if why.get("action"):
            text += f"; auto-recovery: {why['action']} -> {why.get('result') or 'pending'}"
        alerts.append({"level": "crit" if info["minutes"] >= cfg["offline_crit_minutes"]
                       else "warn", "text": text})
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
    for vm, problems in sorted(((st.get("watchdog") or {}).get("drift") or {}).items()):
        if problems:
            warn(f"VM {vm} drifted from the committed setup (tools/ci-hosts): "
                 + "; ".join(p.removeprefix("FAIL: ") for p in problems[:4]))
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
        for pr in prs:
            detail = (j.get("pr_details") or {}).get(str(pr["number"]))
            if isinstance(detail, dict):
                pr.update({k: detail[k] for k in ("state", "draft", "title", "base", "head", "head_repo", "base_repo")
                           if k in detail})
        jobs.append({"repo": j.get("repo"), "workflow": j.get("workflow"), "name": j.get("name"),
                     "status": j.get("status"), "labels": labels, "hosted": hosted,
                     "runner": j.get("runner_name"), "branch": j.get("branch"), "prs": prs,
                     "head_sha": j.get("head_sha"), "head_repo": j.get("head_repo"), "repo_full_name": f"{org}/{j.get('repo')}",
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
    alerts += jit_alerts(raw.get("jit_missing") or {}, shown, cfg)
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

_PAGE_SOURCE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Runner Status</title>
<script>(function(){var m="auto";try{m=localStorage.getItem("rs-theme")||"auto"}catch(e){}var q=matchMedia("(prefers-color-scheme:dark)");function a(){document.documentElement.setAttribute("data-theme",m==="auto"?(q.matches?"dark":"light"):m)}window.rsTheme=function(x){m=x;a()};a();q.addEventListener&&q.addEventListener("change",a)})()</script>
<style>
:root{--bg:#f4f5f7;--card:#fff;--card2:#f7f8fa;--text:#14171c;--muted:#566070;--faint:#5c6471;--line:#e1e4ea;--track:#e6e9ee;
--ok:#16704a;--okbg:#e4f3ea;--warn:#8f5400;--warnbg:#fff3d9;--crit:#c42b2b;--critbg:#fdeaea;--acc:#3351c9;--accbg:#eaeefc;
--okfill:#278a5c;--warnfill:#bb7500;--critfill:#d13434;--onfill:#fff;--accfill:#4c6ef5;--shadow:none;
--radius:12px;--control-radius:8px;--page:1320px;--ui:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--pattern:none;--border-w:1px;--space:1;--text-scale:1;color-scheme:light}
:root[data-theme=dark]{--bg:#0c0e12;--card:#15181e;--card2:#1b1f26;--text:#eceef2;--muted:#9ba3af;--faint:#8b93a0;--line:#262b33;--track:#272c35;
--ok:#4ccf8a;--okbg:#10261b;--warn:#f2b24a;--warnbg:#2a1f0b;--crit:#ff7b7b;--critbg:#2c1214;--acc:#8ea2ff;--accbg:#181e36;
--okfill:#2fb56f;--warnfill:#e9a23b;--critfill:#ef5350;--onfill:#1a0a0a;--accfill:#6d84ff;--shadow:none;color-scheme:dark}
/* Shared Synthesis II palette. */
:root{--bg:#f0f4fb;--card:#ffffff;--text:#161a22;--muted:#586273;--acc:#4263eb;--radius:20px;--control-radius:12px;--page:1380px;--shadow:none}
:root[data-theme=dark]{--bg:#080d18;--card:#141c2c;--text:#edf1f7;--muted:#9ba7b8;--acc:#91a7ff}
:root{--card2:color-mix(in srgb,var(--card) 88%,var(--bg));--faint:color-mix(in srgb,var(--muted) 86%,var(--text));--line:color-mix(in srgb,var(--muted) 28%,var(--bg));--track:color-mix(in srgb,var(--muted) 18%,var(--bg));--accfill:var(--acc);--accbg:color-mix(in srgb,var(--acc) 15%,var(--card))}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-padding-top:64px;scroll-behavior:smooth}
body{margin:0;background-color:var(--bg);background-image:var(--pattern);color:var(--text);font:calc(14px * var(--text-scale))/1.45 var(--ui);font-variant-numeric:tabular-nums}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:3px solid var(--acc);outline-offset:2px;border-radius:6px}
h1,h2,h3{margin:0}
.wrap{max-width:var(--page);margin:0 auto;padding:0 16px}
main.wrap{padding-bottom:40px}
svg.i{width:1em;height:1em;vertical-align:-.14em;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
code,.mono{font:13px/1.3 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
/* top bar (sticky, includes connection banners) */
.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 90%,transparent);backdrop-filter:none;-webkit-backdrop-filter:none;border-bottom:1px solid var(--line)}
.bar1{display:flex;align-items:center;gap:8px;min-height:52px}
.brand{font-weight:700;font-size:16px;white-space:nowrap;margin-right:4px}.brand .narrow{display:none}
.jump{display:flex;gap:2px}
.jump a{color:var(--text);min-height:40px;display:inline-flex;align-items:center;padding:0 10px;border-radius:8px;font-weight:550}
.jump a:hover,.jump a.active{background:var(--card);text-decoration:none}.jump a.active{box-shadow:none}
.nav-short{display:none}
.fresh{margin-left:auto;min-width:0;overflow:hidden;display:flex;align-items:center;gap:7px;font-size:13px;color:var(--muted);white-space:nowrap;min-height:40px}
.pulse{width:8px;height:8px;border-radius:50%;background:var(--okfill);animation:p 2.4s infinite}
.fresh.stale{color:var(--warn)}.fresh.stale .pulse{background:var(--warnfill);animation:none}
.fresh.lost{color:var(--crit);font-weight:650}.fresh.lost .pulse{background:var(--critfill);animation:none}
@keyframes p{0%{box-shadow:none}70%{box-shadow:none}100%{box-shadow:none}}
.btn{font:inherit;font-size:13px;color:var(--text);background:var(--card);border:var(--border-w) solid var(--line);border-radius:var(--control-radius);min-height:40px;min-width:40px;padding:0 10px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px}
.btn:hover{background:var(--card2)}
.btn.pause.on{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 50%,var(--line));background:var(--warnbg)}
.lostbar{background:var(--critbg);color:var(--crit);border-top:1px solid color-mix(in srgb,var(--crit) 35%,transparent);font-size:14px}
.lostbar .wrap{padding:8px 16px;display:flex;gap:8px;align-items:center}
.lostbar[hidden]{display:none}.lostbar.stalebar{background:var(--warnbg);color:var(--warn)}
/* hero */
.hero{margin-top:calc(16px * var(--space));border-radius:var(--radius);background:var(--card);border:var(--border-w) solid var(--line);box-shadow:none;position:relative;overflow:hidden;display:grid;grid-template-columns:minmax(0,1fr);gap:calc(16px * var(--space));padding:calc(20px * var(--space)) 20px calc(16px * var(--space)) 24px}
.hero::before{content:"";position:absolute;inset:0 auto 0 0;width:6px;background:var(--tone)}
.hero.ok{--tone:var(--okfill);--tbg:var(--okbg);--tt:var(--ok)}.hero.warn{--tone:var(--warnfill);--tbg:var(--warnbg);--tt:var(--warn)}.hero.crit{--tone:var(--critfill);--tbg:var(--critbg);--tt:var(--crit)}.hero.wait{--tone:var(--faint);--tbg:var(--card2);--tt:var(--muted)}
.vrow{display:flex;gap:16px;align-items:center}
.vicon{width:52px;height:52px;border-radius:12px;background:var(--tbg);color:var(--tt);display:grid;place-items:center;flex:none}
.vicon svg{width:30px;height:30px;stroke-width:2.4}
.verdict{font-size:clamp(28px,5vw,44px);line-height:1.05;font-weight:750;letter-spacing:-.02em;color:var(--tt)}
.vsub{margin:4px 0 0;color:var(--muted)}
.top1{margin:14px 0 0;font-size:16px;line-height:1.4;font-weight:550;overflow-wrap:anywhere}
.top1 a{color:inherit;text-decoration:underline;text-decoration-color:color-mix(in srgb,var(--tt) 60%,transparent);text-underline-offset:3px;text-decoration-thickness:2px}
.since{display:block;margin-top:5px;color:var(--muted);font-size:12px;font-weight:500}.since .new{color:var(--tt);font-weight:750;text-transform:uppercase;letter-spacing:.04em;margin-right:7px}
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
.hero-all{min-width:0}.hero-all>summary{display:none;list-style:none;color:var(--acc);cursor:pointer;min-height:42px;align-items:center;gap:7px;font-weight:650}.hero-all>summary::-webkit-details-marker{display:none}.hero-all>.ags{margin:0}
.inc>summary{list-style:none;cursor:pointer}.inc>summary::-webkit-details-marker{display:none}.inc .signals{font-size:11px;color:var(--muted);white-space:nowrap}.inc ul{padding-left:18px!important}.inc .al{padding-left:10px;font-size:13px}
.changes{display:block;width:100%;text-align:left;font:inherit;margin-top:10px;border:1px solid var(--line);border-radius:10px;background:var(--card);padding:8px 12px;color:var(--muted);font-size:13px;cursor:pointer}.changes:hover{border-color:var(--acc)}.changes b{color:var(--text)}.changes .recovered{color:var(--ok)}.changes .new{color:var(--warn)}
/* tiles */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:calc(12px * var(--space));margin-top:calc(12px * var(--space))}
.tile{background:var(--card);border:var(--border-w) solid var(--line);border-radius:var(--radius);padding:calc(10px * var(--space)) 12px;min-height:calc(96px * var(--space));display:flex;flex-direction:column;gap:2px;color:var(--text);box-shadow:none;min-width:0}
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
.tiles[data-fade=r]{mask-image:none;mask-image:none}
.tiles[data-fade=l]{mask-image:none;mask-image:none}
.tiles[data-fade=lr]{mask-image:none;mask-image:none}
.okl{list-style:none;margin:0;padding:0;display:grid;gap:8px;align-self:center;font-size:16px}
.okl li{display:flex;gap:10px;align-items:center}.okl svg{color:var(--ok);width:18px;height:18px;stroke-width:2.6}
.igg+.igg{margin-top:6px}
/* layout */
.cols{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:calc(20px * var(--space));margin-top:calc(20px * var(--space));align-items:start}
.colA,.colB,.stk{display:flex;flex-direction:column;gap:12px;min-width:0}
.h2{display:flex;align-items:center;gap:10px;min-height:40px;flex-wrap:wrap}
.h2 h2{font-size:18px;font-weight:700}
.h2 .c{color:var(--muted);font-size:13px}
.activity-h{align-items:flex-start}.activity-tools{margin-left:auto;display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;min-width:0}
.qfs{display:flex;gap:4px;overflow-x:auto;max-width:100%;scrollbar-width:none}.qfs::-webkit-scrollbar{display:none}
.qf,.smallctl{font:inherit;font-size:12px;color:var(--muted);background:var(--card);border:var(--border-w) solid var(--line);border-radius:999px;min-height:34px;padding:0 10px;cursor:pointer;white-space:nowrap}.qf.on{color:var(--text);background:var(--accbg);border-color:var(--acc)}
.smallctl{border-radius:var(--control-radius);min-height:38px}.matchc{font-size:12px;color:var(--muted);min-width:50px;text-align:right}
.flt{display:flex;align-items:center;gap:7px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:0 7px 0 10px;min-height:40px;min-width:0;flex:0 1 230px;color:var(--muted)}
.flt input{font:inherit;color:var(--text);background:none;border:0;outline:0;min-width:0;width:100%;min-height:38px}
.flt:focus-within{border-color:var(--acc);outline:2px solid var(--acc)}
.flt kbd,kbd{font:11px ui-monospace,Menlo,monospace;border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;padding:0 5px;color:var(--muted);background:var(--card2)}
.flt-clear{border:0;background:none;color:var(--muted);font:18px/1 system-ui;min-width:28px;min-height:32px;border-radius:6px;cursor:pointer}.flt-clear[hidden]{display:none}.flt-clear:hover{color:var(--text);background:var(--card2)}
.card{background:var(--card);border:var(--border-w) solid var(--line);border-radius:var(--radius);box-shadow:none;min-width:0;overflow:hidden}
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
.runner-tag{font:12px ui-monospace,Menlo,monospace;color:var(--muted)}
.group-label{padding:6px 16px;border-top:1px solid var(--line);background:var(--card2);color:var(--muted);font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.06em}
.tmw{flex:none;text-align:right;min-width:68px}
.tm{display:block;font-size:16px;font-weight:700;line-height:1.25}
.tmw small{font-size:12px;color:var(--muted)}
.tmw.long .tm{color:var(--warn)}.tmw.vlong .tm{color:var(--crit)}
.shimmer{display:inline-block;height:10px;width:160px;max-width:70%;border-radius:5px;background:var(--track);background-size:200% 100%;animation:sh 1.4s infinite linear;vertical-align:middle}
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
.machine>summary.mh{list-style:none;cursor:pointer;min-height:52px;padding-bottom:10px}.machine>summary.mh::-webkit-details-marker{display:none}.machine>summary .chev{margin-left:2px}.machine:not([open])>summary .chev{transform:none}.machine[open]>summary .chev{transform:rotate(90deg)}
.machine-health{font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.04em}.machine-health.ok{color:var(--ok)}.machine-health.issue{color:var(--warn)}
.mh h3{font-size:16px;font-weight:700}
.mh .r{margin-left:auto;font-size:13px;color:var(--muted);display:flex;gap:10px;flex-wrap:wrap}
.mh .r span{display:inline-flex;align-items:center;gap:5px}
.fresh-machine{font-size:12px;color:var(--muted);font-weight:500}.fresh-machine.stale{color:var(--warn)}
.machine-actions{margin-left:auto;display:flex;gap:6px;align-items:center}.machine-actions .smallctl{min-height:34px}
.meters{padding:8px 16px 4px;display:grid;gap:12px}
.memory-facts{display:flex;gap:8px;flex-wrap:wrap;padding:2px 16px 0;color:var(--muted);font-size:12px}.memory-facts span{background:var(--card2);border:1px solid var(--line);border-radius:6px;padding:3px 7px}.memory-facts .warn{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 45%,var(--line))}.memory-facts .crit{color:var(--crit);border-color:color-mix(in srgb,var(--crit) 55%,var(--line))}
.mt .l{display:flex;justify-content:space-between;gap:8px;align-items:baseline;flex-wrap:wrap}
.mt .l b{font-weight:650}.mt .l .v{color:var(--muted);text-align:right}
.mt em{font-style:normal;font-weight:750;margin-left:6px;font-size:11px;letter-spacing:.04em;text-transform:uppercase}
.mt em.warn{color:var(--warn)}.mt em.crit{color:var(--crit)}
.bar{height:12px;background:var(--track);border-radius:6px;margin-top:5px;position:relative;--fc:var(--accfill)}
.bar::after{content:attr(data-tip);display:none;position:absolute;z-index:4;left:4px;top:17px;background:var(--text);color:var(--bg);font-size:11px;white-space:nowrap;padding:4px 7px;border-radius:5px}.bar:hover::after,.bar:focus-visible::after{display:block}.bar{outline-offset:3px}.bar>*{overflow:hidden}
.bar.ok{--fc:var(--okfill)}.bar.warn{--fc:var(--warnfill)}.bar.crit{--fc:var(--critfill)}
.bar i{position:absolute;top:0;bottom:0;left:0;background:var(--fc)}
.bar i.hat{background:var(--track)}
.bar s{position:absolute;top:0;bottom:0;width:2px;margin-left:-1px;background:var(--text);opacity:.45}
.bar s.c{opacity:.75}
.chr{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px 16px 4px}
.chh{display:flex;justify-content:space-between;gap:6px;font-size:12px;color:var(--muted);margin-bottom:3px;min-height:18px}
.chh b{font-weight:650;color:var(--text)}
.chh .ro{white-space:nowrap;border-radius:5px;padding:0 3px}.chh .ro:not(:empty){background:var(--accbg);color:var(--acc)}
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
.chart-help{padding:2px 16px 0;color:var(--muted);font-size:11px}.chart-help kbd{margin:0 2px}
.vms{margin:12px 16px 16px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.vm{display:flex;gap:4px 10px;align-items:center;padding:8px 12px;border-top:1px solid var(--line);flex-wrap:wrap;min-height:40px}
.vm:first-child{border-top:0}.vm .s{font-size:13px;color:var(--muted)}.vm .w{margin-left:auto;font-size:13px;color:var(--muted);text-align:right}
.vm.stop{background:var(--warnbg)}.vm.stop .w{color:var(--warn);font-weight:650}
.vm[href]{color:var(--text)}.vm[href]:hover{background:var(--card2);text-decoration:none}.chip[data-filter]{cursor:pointer;color:var(--text)}.chip[data-filter]:hover{border-color:var(--acc)}
.gk{padding:4px 16px 14px;display:grid;gap:6px;font-size:13px;color:var(--muted)}
.gk b{color:var(--text);font-weight:600}
.diag{margin:0 16px 14px;border-top:1px solid var(--line);padding-top:6px}.diag>summary{cursor:pointer;color:var(--acc);min-height:36px;display:flex;align-items:center;gap:6px}.diag .gk{padding:4px 0 0}.gh-brief{padding:2px 16px 10px;color:var(--muted);font-size:13px}
.foot{color:var(--faint);font-size:13px;margin-top:20px;line-height:1.6}
.foot p{margin:0 0 4px}
dialog{border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--text);padding:0;width:min(400px,calc(100vw - 32px))}
dialog::backdrop{background:rgba(0,0,0,.4)}
dialog h2{font-size:16px;padding:14px 18px;border-bottom:1px solid var(--line)}
dialog dl{margin:0;padding:10px 18px 14px;display:grid;grid-template-columns:1fr auto;gap:8px 16px;align-items:center}
dialog dd{margin:0;text-align:right}dialog form{padding:0 18px 14px}
/* evolution lab and productivity layer */
.icon-tx{display:none}.spin{animation:spin .7s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.utility{display:flex;gap:6px}.utility .btn{position:relative}.refresh-count{font-size:10px;color:var(--muted);min-width:18px;text-align:center}
.wide-dialog{width:min(980px,calc(100vw - 28px));max-height:min(86vh,900px);overflow:auto}.wide-dialog>header{position:sticky;top:0;z-index:2;background:var(--card);display:flex;gap:10px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--line)}.wide-dialog>header h2{padding:0;border:0;flex:1}.dialog-x{border:0;background:transparent;color:var(--muted);font-size:24px;line-height:1;cursor:pointer;min-width:40px;min-height:40px;border-radius:var(--control-radius)}.dialog-x:hover{background:var(--card2);color:var(--text)}
.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:14px 18px}.setting{display:grid;gap:5px}.setting>span,.setting legend{font-size:12px;font-weight:700;color:var(--muted)}.setting select,.setting input[type=text],.setting input[type=number],#cmd-in,#note-text{font:inherit;color:var(--text);background:var(--card2);border:1px solid var(--line);border-radius:var(--control-radius);min-height:42px;padding:7px 10px;width:100%}.checks{display:flex;gap:8px;flex-wrap:wrap}.checks label{display:flex;gap:6px;align-items:center;background:var(--card2);border:1px solid var(--line);border-radius:999px;padding:6px 10px}.settings-actions{padding:2px 18px 18px;display:flex;flex-wrap:wrap;gap:8px}.saved{padding:0 18px 16px}.saved:empty{display:none}.saved h3{font-size:13px;margin-bottom:7px}.saved-row{display:flex;gap:7px;align-items:center;padding:6px 0;border-top:1px solid var(--line)}.saved-row b{flex:1}.saved-row button{min-height:34px}
.cmd-dialog{width:min(620px,calc(100vw - 24px));padding:0;overflow:hidden}.cmd-dialog form{padding:0}.cmd-head{display:flex;gap:8px;align-items:center;padding:10px;border-bottom:1px solid var(--line)}#cmd-in{border:0;background:transparent;outline:0;font-size:16px}.cmd-list{list-style:none;margin:0;padding:6px;max-height:min(60vh,520px);overflow:auto}.cmd-item{display:flex;align-items:center;gap:10px;width:100%;min-height:44px;padding:7px 10px;border:0;border-radius:var(--control-radius);background:transparent;color:var(--text);font:inherit;text-align:left;cursor:pointer}.cmd-item:hover,.cmd-item.sel{background:var(--accbg);color:var(--acc)}.cmd-item small{margin-left:auto;color:var(--muted)}
.toast{position:fixed;left:50%;bottom:24px;z-index:40;transform:translate(-50%,12px);background:var(--text);color:var(--bg);padding:9px 13px;border-radius:999px;box-shadow:none;opacity:0;pointer-events:none;transition:.18s;max-width:calc(100vw - 24px);text-align:center}.toast.show{opacity:1;transform:translate(-50%,0)}
.bottom-nav{display:none}.row.kb-focus,.tile.kb-focus,.machine.kb-focus{outline:3px solid var(--acc);outline-offset:2px}.pin,.note-b,.compare-b{border:0;background:transparent;color:var(--faint);font-size:17px;min-width:34px;min-height:34px;border-radius:var(--control-radius);cursor:pointer}.pin:hover,.note-b:hover,.compare-b:hover{background:var(--card2);color:var(--text)}.pin.on{color:var(--warnfill)}.note-dot{width:7px;height:7px;border-radius:50%;background:var(--accfill);display:inline-block}
.incident-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px}.incident-actions button{min-height:32px}.acked{color:var(--ok);font-size:12px;font-weight:700}.sla{font-size:11px;font-weight:700;border-radius:999px;padding:2px 7px}.sla.ok{background:var(--okbg);color:var(--ok)}.sla.warn{background:var(--warnbg);color:var(--warn)}.sla.crit{background:var(--critbg);color:var(--crit)}
.compare-tray{position:fixed;z-index:24;left:50%;bottom:18px;transform:translateX(-50%);display:flex;align-items:center;gap:10px;background:var(--text);color:var(--bg);border-radius:999px;padding:7px 8px 7px 14px;box-shadow:none}.compare-tray[hidden]{display:none}.compare-tray .btn{min-height:34px;background:var(--bg);color:var(--text);border:0}.compare-grid{display:grid;grid-template-columns:140px repeat(2,minmax(140px,1fr));padding:12px 18px 18px;overflow:auto}.compare-grid>*{padding:8px;border-bottom:1px solid var(--line)}.compare-grid b{font-weight:700}.compare-grid .lab{color:var(--muted)}
.activity-compact .row{padding-top:6px;padding-bottom:6px}.activity-compact .row>.ic{width:23px;height:23px}.activity-compact .meta{font-size:12px}.activity-compact .why,.activity-compact .last{display:none}
.workspace-activity .cols{grid-template-columns:minmax(0,1fr)}.workspace-activity .colB{display:none}.workspace-machines .cols{grid-template-columns:minmax(0,1fr)}.workspace-machines .colA{display:none}.workspace-machines #hostl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,430px),1fr));align-items:start}
body.hide-summary #tiles,body.hide-summary #changes{display:none!important}body.hide-activity .colA{display:none!important}body.hide-machines #hosts,body.hide-machines #hostl{display:none!important}body.hide-github #extra{display:none!important}body.hide-history #hist{display:none!important}
body.focus-mode .top .brand,body.focus-mode .top .jump,body.focus-mode .top .utility .btn:not(#settingsb),body.focus-mode #tiles,body.focus-mode #changes,body.focus-mode .colB,body.focus-mode main.wrap>.foot{display:none!important}body.focus-mode .cols{grid-template-columns:1fr;max-width:920px;margin-left:auto;margin-right:auto}body.focus-mode .fresh{margin-left:0}.focus-pill{display:none}body.focus-mode .focus-pill{display:inline-flex}
body.high-contrast{--border-w:2px;--shadow:none}body.high-contrast a{text-decoration:underline}body.reduce-motion *,body.reduce-motion *::before,body.reduce-motion *::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}
:root[data-color=deuteranopia]{--ok:#176d92;--okfill:#168aad;--okbg:#e3f3f8;--crit:#b14500;--critfill:#d05a00;--critbg:#fff0e5}:root[data-theme=dark][data-color=deuteranopia]{--ok:#69c5e2;--okbg:#092733;--crit:#ff9b5e;--critbg:#351b0c}
:root[data-color=tritanopia]{--acc:#9a3f86;--accfill:#bd4ca5;--accbg:#f7e9f4;--warn:#8a5f00;--warnfill:#b78000}:root[data-theme=dark][data-color=tritanopia]{--acc:#f08bd7;--accbg:#321229;--warn:#ffd16e}
.timeline{list-style:none;margin:0;padding:4px 18px 18px}.timeline li{position:relative;padding:8px 0 8px 22px;border-left:2px solid var(--line);margin-left:5px}.timeline li::before{content:"";position:absolute;left:-6px;top:13px;width:10px;height:10px;border-radius:50%;background:var(--accfill)}.timeline li.crit::before{background:var(--critfill)}.timeline li.warn::before{background:var(--warnfill)}.timeline li.ok::before{background:var(--okfill)}.timeline time{display:block;color:var(--muted);font-size:11px}.change-count{display:none;background:var(--critfill);color:#fff;border-radius:999px;font-size:10px;font-weight:800;min-width:17px;height:17px;place-items:center}.change-count.on{display:grid}
.recommend{margin:0 16px 14px;border:1px solid var(--line);border-radius:var(--control-radius);background:var(--card2);padding:10px 12px;color:var(--muted)}.recommend b{color:var(--text)}.projection{color:var(--acc);font-size:12px;font-weight:650}
.tour-body{padding:18px}.tour-step{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px}.tour-body h3{font-size:22px;margin:12px 0 6px}.tour-body p{color:var(--muted);min-height:62px}.tour-actions{display:flex;gap:8px;padding:0 18px 18px}.tour-actions .btn:last-child{margin-left:auto}.tour-target{outline:4px solid var(--acc)!important;outline-offset:4px;position:relative;z-index:12}
.bottom-safe{height:0}
/* Synthesis II surfaces. */
.card,.tile,.hero{backdrop-filter:none;-webkit-backdrop-filter:none}.top{border-bottom-color:transparent}
:root[data-density=compact]{--space:.72}.density-compact .row{padding-top:6px;padding-bottom:6px}.density-compact .machine>summary.mh{min-height:44px}.density-compact .tiles .tile{min-height:72px}.density-compact .tile .n{font-size:23px}
@media (max-width:980px){.cols{grid-template-columns:minmax(0,1fr)}.hero{padding-right:16px}}
@media (min-width:981px){
 .cols.quiet{grid-template-columns:minmax(0,1fr)}
 .quiet #hostl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));align-items:start}
 .quiet #extra{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}.quiet #extra:has(#hist:empty){grid-template-columns:minmax(0,1fr)}
 .quiet #extra .h2{grid-column:1/-1}
 .quiet .ig{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:2px 28px}.quiet .igg+.igg{margin-top:0}
}
@media (min-width:641px) and (max-width:900px){.tiles[data-n="5"]{grid-template-columns:repeat(6,1fr)}.tiles[data-n="5"] .tile{grid-column:span 2}.tiles[data-n="5"] .tile:nth-child(n+4){grid-column:span 3}}
@media (min-width:700px) and (max-width:1100px){
 .wrap{padding-left:20px;padding-right:20px}
}
@media (min-width:900px) and (max-width:1100px){
 .cols{gap:16px}.hero.two{grid-template-columns:minmax(0,1fr) minmax(280px,.8fr)}
 body.workspace-balanced .cols{grid-template-columns:minmax(0,1.08fr) minmax(340px,.92fr)}
}
@media (min-width:981px){.hero.two{grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:28px}.ch{height:64px}}
@media (min-width:1200px){.ch{height:72px}}
@media (max-width:640px){
 .wrap{padding:0 12px}main.wrap{padding-bottom:92px}
 .hero{margin-top:12px;padding:14px 12px 12px 18px;gap:12px}.vicon{width:42px;height:42px}.vicon svg{width:24px;height:24px}.vrow{gap:12px}
 .hero-all>summary{display:flex}.hero-all>.ags{margin-top:6px}.hero-all:not([open])>.ags{display:none}.hero.two{grid-template-columns:minmax(0,1fr)}
 .brand{display:block;font-size:13px;margin-right:0}.brand .wide{display:none}.brand .narrow{display:inline}.btn.hp,.top .jump{display:none}.bar1{gap:4px}.fresh{font-size:12px}.fresh span{max-width:72px;overflow:hidden;text-overflow:ellipsis}.btn{min-width:36px;padding:0 7px}.utility{margin-left:auto}.fresh{margin-left:0}.refresh-count{display:none}
 .tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:visible;margin:12px 0 0;padding:0;gap:8px;-webkit-mask-image:none!important;mask-image:none!important}
 .tile{min-height:88px;padding:8px 10px}.tile .n{font-size:24px}.tile .d{font-size:12px}
 .activity-tools{width:100%;justify-content:flex-start}.qfs{width:100%;order:2}.flt{flex:1 1 190px}.matchc{min-width:0}.smallctl.sort{flex:0 0 auto}
 .row{padding:10px 12px;gap:10px}.row>.ic{display:none}.gh{padding:12px 12px 6px}.empty,.calm{padding-left:12px;padding-right:12px}.ig{padding:0 12px 10px}
 .mh{padding:12px 12px 4px}.meters{padding-left:12px;padding-right:12px}.chr{padding:10px 12px 4px;gap:8px}.vms{margin:10px 12px 12px}.note{margin-left:12px;margin-right:12px}.gk{padding-left:12px;padding-right:12px}
 .memory-facts{padding-left:12px;padding-right:12px}.ch{height:58px}.flt kbd{display:none}.flt input{min-height:40px}.chart-help{padding-left:12px;padding-right:12px}
 .jt a,.top1 a{padding:12px 0}
 .pr{min-height:40px;padding:0 12px;margin:-5px 0}.meta{gap:6px 10px}
 details.sec>summary{padding:12px}.tmw{min-width:60px}
 .ag .nm{max-width:42%;overflow:hidden;text-overflow:ellipsis}
 .bottom-nav{position:fixed;z-index:20;left:8px;right:8px;bottom:max(8px,env(safe-area-inset-bottom));display:grid;grid-template-columns:repeat(5,1fr);background:color-mix(in srgb,var(--card) 92%,transparent);border:1px solid var(--line);border-radius:18px;box-shadow:none;backdrop-filter:none;-webkit-backdrop-filter:none;padding:4px}
 .bottom-nav a,.bottom-nav button{border:0;background:transparent;color:var(--muted);font:11px/1.1 var(--ui);min-height:52px;border-radius:14px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;text-decoration:none}.bottom-nav .i{font-size:18px}.bottom-nav a.active,.bottom-nav button:active{color:var(--acc);background:var(--accbg)}
 .toast{bottom:82px}.compare-tray{bottom:78px;width:calc(100vw - 24px);justify-content:center}.wide-dialog{width:100vw;max-width:none;max-height:100dvh;height:100dvh;border-radius:0}.settings-grid{grid-template-columns:1fr}.compare-grid{grid-template-columns:110px repeat(2,150px)}
 body.focus-mode main.wrap{padding-bottom:28px}body.focus-mode .bottom-nav{display:none}
}
@media (max-width:430px){.nav-full{display:none}.nav-short{display:inline}.fresh span{max-width:68px}.brand{display:block}.tile .n{font-size:22px}.top #theme{display:none}.bar1{min-height:48px}.vsub{font-size:12px}}
/* Calm default: one controls panel, with secondary actions revealed on demand. */
.top .utility{gap:8px}.top .btn{background:transparent;border-color:transparent}.top .btn:hover{background:var(--card2)}.dashboard-menu{font-size:24px;font-weight:700}.refresh-count{display:none}
.activity-h{align-items:center;gap:8px}.activity-tools{flex-wrap:nowrap;gap:6px}.activity-tools .flt{flex:0 1 180px;min-width:100px;border-color:transparent;background:color-mix(in srgb,var(--card) 65%,transparent)}.filters-open{min-height:40px;background:transparent;border-color:transparent}.filters-open:hover{background:var(--card)}.filters-open.has-filters{color:var(--acc);background:var(--accbg)}#filterCount{background:var(--acc);color:var(--card);border-radius:999px;min-width:17px;padding:0 4px;margin-left:5px;font-size:10px}
.filter-summary{display:flex;align-items:center;gap:8px;flex-basis:100%;color:var(--muted);font-size:12px;padding:2px 0 4px}.filter-summary[hidden]{display:none}.filter-summary .matchc{margin-left:auto}.text-btn{font:inherit;font-size:12px;color:var(--acc);border:0;background:transparent;padding:8px;min-height:36px;cursor:pointer;border-radius:6px}.text-btn:hover{background:var(--accbg)}
#tiles{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}#tiles .tile{min-height:96px;box-shadow:none;background:color-mix(in srgb,var(--card) 70%,transparent)}#tiles .tile .k{letter-spacing:.04em}.card,.hero{box-shadow:none}.machine>summary.mh{padding-top:16px;padding-bottom:14px;gap:6px 10px}.machine .machine-health{font-size:10px;font-weight:650;letter-spacing:.02em;text-transform:none}.machine .fresh-machine{font-size:11px}.machine .mh .r{font-size:12px}.machine-more{border:0;background:transparent;color:var(--muted);border-radius:8px;min-width:36px;min-height:36px;cursor:pointer;font:22px/1 system-ui}.machine-more:hover{background:var(--accbg);color:var(--acc)}
.control-panel{width:min(640px,calc(100vw - 28px))}.control-section{padding:18px 22px;border-bottom:1px solid var(--line)}.control-section h3{font-size:13px;margin:0 0 12px;color:var(--muted);font-weight:650}.control-section>summary{font-size:14px;font-weight:600;cursor:pointer;min-height:24px;list-style:none;display:flex;align-items:center;justify-content:space-between}.control-section>summary::-webkit-details-marker{display:none}.control-section>summary::after{content:"+";font-size:18px;color:var(--muted)}.control-section[open]>summary::after{content:"−"}.control-section[open]>summary{margin-bottom:14px}.control-row{display:flex;gap:8px;flex-wrap:wrap;align-items:end}.control-row .setting{flex:1;min-width:150px}.control-panel .qfs{flex-wrap:wrap;overflow:visible;margin-bottom:14px;width:auto;gap:6px}.control-panel .qf{min-height:40px}.control-panel .settings-grid{padding:14px 0 0;gap:16px}.control-panel .saved{padding:0 0 12px}.control-panel .btn{min-height:40px;font-size:12px}.panel-footer{position:sticky;bottom:0;background:var(--card);padding:12px 22px;display:flex;justify-content:flex-end;border-top:1px solid var(--line)}.panel-done{background:var(--acc)!important;color:var(--bg)!important;border-color:transparent!important;min-width:92px}.secondary-stats{grid-template-columns:repeat(auto-fit,minmax(130px,1fr));margin-top:16px}.secondary-stats .tile{min-height:80px}.secondary-stats .n{font-size:23px}
.menu-head{display:flex;align-items:center;padding-right:10px;border-bottom:1px solid var(--line)}.menu-head h2{flex:1;border:0}.machine-menu-items{padding:8px;display:grid;gap:2px}.machine-menu-items button{font:inherit;text-align:left;border:0;background:transparent;color:var(--text);min-height:46px;padding:10px 14px;border-radius:8px;cursor:pointer}.machine-menu-items button:hover{background:var(--accbg);color:var(--acc)}
.incident-menu{margin-top:8px;display:block;max-width:100%}.incident-menu>summary{list-style:none;cursor:pointer;display:inline-flex;color:var(--muted);font-weight:500;font-size:12px;min-height:32px;align-items:center;gap:5px}.incident-menu>summary::-webkit-details-marker{display:none}.incident-menu>summary::after{content:"⌄"}.incident-menu[open]>summary::after{content:"⌃"}.incident-menu .incident-actions{margin-top:0}.incident-menu .incident-actions button{min-height:40px}.since{font-size:11px}.chart-help{display:none}
.bottom-nav{grid-template-columns:repeat(4,1fr)}
.machine{position:relative}.machine>summary.mh{padding-right:54px}.machine-more{position:absolute;top:12px;right:10px}.machine .mh .r{margin-left:auto}.control-panel .tile{box-shadow:none}body.focus-mode .top #settingsb{display:inline-flex!important}
.control-panel[open]{display:flex;flex-direction:column}.control-panel>header,.control-panel>.control-section,.control-panel>.panel-footer{flex-shrink:0}.control-panel>.panel-footer{margin-top:auto}
.control-panel,.control-panel>header,.control-panel>.panel-footer{background:var(--bg)}
@media(max-width:640px){.top .brand .narrow{display:none}.top .brand .wide{display:inline}.top .brand{font-size:14px}.top .fresh{margin-left:auto}.top .fresh span{max-width:110px}.top .utility{margin-left:4px}.activity-tools{width:100%;margin:4px 0 0}.activity-tools .flt{flex:1}.activity-tools .filters-open{flex:none}#tiles{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}#tiles .tile:last-child{grid-column:1/-1;min-height:80px}.control-panel{width:100vw;max-width:none}.control-section{padding:16px 18px}.control-row .setting{min-width:100%}.control-panel .qf{flex:1 0 27%}.control-panel .settings-grid{grid-template-columns:1fr}.top #settingsb{display:none}.machine .mh .r{width:calc(100% - 42px);margin-left:0}.machine-more{margin-left:auto}.bottom-nav{grid-template-columns:repeat(4,1fr)}}
/* Structural styles share the same palette. */
:root[data-style=minimal]{--radius:8px;--control-radius:6px;--page:1280px}
[data-style=minimal] .card,[data-style=minimal] .hero,[data-style=minimal] #tiles .tile{box-shadow:none;border-width:0}
[data-style=minimal] .hero::before{width:3px}[data-style=minimal] .verdict{font-weight:600;letter-spacing:-.04em}[data-style=minimal] .ag{border-width:0}[data-style=minimal] .vicon{border-radius:50%}[data-style=minimal] .row{padding-top:14px;padding-bottom:14px}
:root[data-style=outline]{--radius:0px;--control-radius:4px;--border-w:2px;--page:1380px}
[data-style=outline] .card,[data-style=outline] .hero,[data-style=outline] #tiles .tile{box-shadow:none;border-width:2px}[data-style=outline] .ag,[data-style=outline] .vms{border-width:2px;border-radius:0}[data-style=outline] .bar,[data-style=outline] .ch,[data-style=outline] .ic{border-radius:0}[data-style=outline] .h2 h2{font-weight:800}
:root[data-style=editorial]{--radius:3px;--control-radius:5px;--page:1180px}
[data-style=editorial] .verdict,[data-style=editorial] .h2 h2,[data-style=editorial] .mh h3{font-family:Georgia,"Times New Roman",serif;font-weight:500}
[data-style=editorial] .verdict{font-size:clamp(32px,5vw,48px);letter-spacing:-.04em}[data-style=editorial] .h2 h2{font-size:23px}[data-style=editorial] .row{padding-top:18px;padding-bottom:18px}[data-style=editorial] .jt{font-size:16px;line-height:1.5}[data-style=editorial] .hero{padding-top:28px;padding-bottom:26px}[data-style=editorial] .card,[data-style=editorial] .hero{box-shadow:none}
:root[data-style=terminal]{--radius:4px;--control-radius:4px;--page:1500px;--ui:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
[data-style=terminal] .verdict{font-size:clamp(26px,4vw,36px);letter-spacing:-.05em}[data-style=terminal] .h2 h2,[data-style=terminal] .tile .k{text-transform:uppercase;letter-spacing:.08em;font-size:12px}[data-style=terminal] .row{padding-top:8px;padding-bottom:8px}[data-style=terminal] .jt{font-size:13px}[data-style=terminal] .bar{height:7px;border-radius:0}[data-style=terminal] .card,[data-style=terminal] .hero{box-shadow:none}[data-style=terminal] .vicon{border-radius:4px}
:root[data-style=blueprint]{--radius:6px;--control-radius:3px;--page:1420px}
[data-style=blueprint] .card,[data-style=blueprint] .hero,[data-style=blueprint] #tiles .tile{border-style:dashed;box-shadow:none}[data-style=blueprint] .h2{border-bottom:1px dashed var(--line);padding-bottom:8px}[data-style=blueprint] .h2 h2{text-transform:uppercase;letter-spacing:.12em;font-size:14px}[data-style=blueprint] .tile .n{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}[data-style=blueprint] .ch,[data-style=blueprint] .bar{border-radius:0}[data-style=blueprint] .meters{gap:16px}
:root[data-style=soft]{--radius:28px;--control-radius:999px;--page:1280px}
[data-style=soft] .hero{padding-top:28px;padding-bottom:24px}[data-style=soft] .hero::before{inset:0 24px auto;width:calc(100% - 48px);height:4px}[data-style=soft] .vicon{border-radius:50%}[data-style=soft] .row{padding-top:16px;padding-bottom:16px}[data-style=soft] .ic{border-radius:50%}[data-style=soft] .ag{border-radius:16px}[data-style=soft] .ch{height:86px;border-radius:12px}[data-style=soft] .vms{border-radius:16px}
:root[data-style=studio]{--radius:16px;--control-radius:10px;--page:1080px}
[data-style=studio] body.workspace-balanced #cols{grid-template-columns:minmax(0,1fr)}[data-style=studio] body.workspace-balanced #hostl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));align-items:start}[data-style=studio] .hero.two{grid-template-columns:minmax(0,1fr)}[data-style=studio] .hero-all>.ags{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr))}[data-style=studio] .tile .n{font-size:34px}[data-style=studio] .h2{min-height:52px}
:root[data-style=ledger]{--radius:0px;--control-radius:3px;--page:1440px}
[data-style=ledger] .card,[data-style=ledger] .hero{box-shadow:none}[data-style=ledger] .row{display:grid;grid-template-columns:28px minmax(0,1fr) 70px;gap:12px;padding-top:12px;padding-bottom:12px}[data-style=ledger] .jt{font-size:13px;font-weight:550}[data-style=ledger] .meta{font-size:12px}[data-style=ledger] .gh{padding-top:14px;padding-bottom:10px;border-bottom:1px solid var(--line)}[data-style=ledger] .group-label{letter-spacing:.1em}[data-style=ledger] .vm{border-radius:0}[data-style=ledger] .verdict{font-size:32px}
:root[data-style=command]{--radius:10px;--control-radius:6px;--page:1560px}
[data-style=command] .verdict{font-weight:850;letter-spacing:-.045em}[data-style=command] .h2 h2{text-transform:uppercase;font-size:15px;letter-spacing:.06em}[data-style=command] #tiles .tile{min-height:82px}[data-style=command] .tile .n{font-size:32px}[data-style=command] .row{padding-top:8px;padding-bottom:8px}[data-style=command] .ch{height:76px}[data-style=command] .machine>summary.mh{padding-top:12px;padding-bottom:12px}
@media(min-width:1101px){[data-style=command] body.workspace-balanced #cols:not(.quiet){grid-template-columns:minmax(0,1.45fr) minmax(0,1fr)}}
.style-setting{grid-column:1/-1}.style-note{font-size:12px;line-height:1.5;margin:0;font-weight:400;color:var(--muted)}
@media(max-width:640px){[data-style] .hero{padding-top:18px;padding-bottom:16px}[data-style] .hero.two{grid-template-columns:minmax(0,1fr)}[data-style] #tiles .tile .n{font-size:24px}[data-style=ledger] .row{display:flex;gap:10px}[data-style=studio] body.workspace-balanced #hostl{grid-template-columns:minmax(0,1fr)}[data-style=studio] .hero-all>.ags{display:flex}[data-style=editorial] .row{padding-top:14px;padding-bottom:14px}[data-style=terminal] .jt{font-size:13px}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}html{scroll-behavior:auto}}
/* GitHub-inspired structure, using our existing palette and status colors. */
:root[data-style=github]{--radius:6px;--control-radius:6px;--page:1440px;--shadow:none;scroll-padding-top:112px}
[data-style=github] body{background-image:none}
[data-style=github] .top{background:var(--bg);backdrop-filter:none;-webkit-backdrop-filter:none}
[data-style=github] .bar1{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:0 16px;padding-top:8px}
[data-style=github] .brand{display:flex;gap:10px;align-items:center;min-height:44px;font-size:15px;font-weight:600;letter-spacing:0}
[data-style=github] .brand::before{content:"</>";display:grid;place-items:center;width:30px;height:30px;border:1px solid var(--line);border-radius:6px;color:var(--muted);font:600 12px ui-monospace,monospace}
[data-style=github] .jump{grid-row:2;grid-column:1/-1;gap:8px;padding-top:4px}
[data-style=github] .jump a{border-radius:0;min-height:44px;padding:0 14px;border-bottom:2px solid transparent;font-size:14px;font-weight:500}
[data-style=github] .jump a.active{background:none;box-shadow:none;border-bottom-color:var(--acc);font-weight:650}
[data-style=github] .jump a:hover{background:var(--card2)}
[data-style=github] .top .btn{border:1px solid var(--line);background:var(--card2);min-height:34px;min-width:34px}
[data-style=github] .fresh{font-size:12px;margin:0 4px 0 0}
[data-style=github] .pulse{animation:none;box-shadow:none}
[data-style=github] .card,[data-style=github] .hero,[data-style=github] #tiles .tile{box-shadow:none;backdrop-filter:none;-webkit-backdrop-filter:none;background:var(--card);border:1px solid var(--line)}
[data-style=github] .hero{padding:16px 20px;margin-top:20px;gap:16px}
[data-style=github] .hero::before{display:none}
[data-style=github] .vrow{gap:12px}
[data-style=github] .vicon{width:32px;height:32px;border-radius:50%;background:none;color:var(--tt)}
[data-style=github] .vicon svg{width:24px;height:24px;stroke-width:2}
[data-style=github] .verdict{font-size:24px;letter-spacing:-.025em;font-weight:650;color:var(--text)}
[data-style=github] .vsub{font-size:12px}
[data-style=github] .top1{font-size:14px;font-weight:500;margin-top:12px}
[data-style=github] .top1 a{text-decoration:none;color:var(--acc)}
[data-style=github] .top1 a:hover{text-decoration:underline}
[data-style=github] .ag{background:var(--card2);border-radius:6px}
[data-style=github] .ags{gap:6px}
[data-style=github] #tiles{gap:0;border:1px solid var(--line);border-radius:6px;overflow:hidden;background:var(--card)}
[data-style=github] #tiles .tile{border:0;border-right:1px solid var(--line);border-radius:0;background:none;min-height:92px;padding:12px 16px}
[data-style=github] #tiles .tile:last-child{border-right:0}
[data-style=github] #tiles .tile:hover{background:var(--card2)}
[data-style=github] #tiles .tile .k{font-size:12px;text-transform:none;letter-spacing:0;font-weight:500}
[data-style=github] #tiles .tile .n{font-size:26px;font-weight:650}
[data-style=github] #tiles .tile .d{font-size:12px}
[data-style=github] .h2 h2{font-size:16px;font-weight:650;letter-spacing:0}
[data-style=github] .h2 .c{font-size:12px}
[data-style=github] .gh{background:var(--card2);padding:10px 16px;border-bottom:1px solid var(--line);scroll-margin-top:112px}
[data-style=github] .gh h3{font-weight:600;font-size:13px}
[data-style=github] .gh .c{font-weight:500;background:var(--track);padding:0 7px}
[data-style=github] .ul{padding-bottom:0}
[data-style=github] .row{padding:12px 16px;gap:10px}
[data-style=github] .row:hover{background:var(--card2)}
[data-style=github] .ic{width:20px;height:22px;background:none;border-radius:0;font-size:16px;margin-top:0}
[data-style=github] .jt{font-size:14px;font-weight:600;line-height:1.5}
[data-style=github] .jt a{color:var(--text)}
[data-style=github] .jt a:hover{color:var(--acc);text-decoration:underline}
[data-style=github] .meta{font-size:12px;gap:4px 10px;margin-top:5px}
[data-style=github] .repo{color:var(--muted);font-weight:500}
[data-style=github] .pr{background:none;padding:0;min-height:24px;border-radius:0;font-size:12px;font-weight:500}
[data-style=github] .tag,[data-style=github] .st{border-radius:999px;border:1px solid var(--line);font-size:11px;text-transform:none;letter-spacing:0;font-weight:500}
[data-style=github] .tm{font-size:13px;font-weight:600;line-height:1.5}
[data-style=github] .tmw small{font-size:11px}
[data-style=github] .inspect-open{font-size:11px;min-height:28px}
[data-style=github] .activity-tools .flt{border:1px solid var(--line);background:var(--bg);border-radius:6px;flex-basis:220px;min-height:34px}
[data-style=github] .activity-tools .flt input{min-height:32px;font-size:13px}
[data-style=github] .filters-open{background:var(--card2);border:1px solid var(--line);min-height:34px}
[data-style=github] .machine>summary.mh{background:var(--card2);padding-top:12px;padding-bottom:12px;border-bottom:1px solid var(--line)}
[data-style=github] .machine:not([open])>summary.mh{border-bottom:0}
[data-style=github] .mh h3{font-size:14px;font-weight:600}
[data-style=github] .machine-more{top:7px;right:8px}
[data-style=github] .bar,[data-style=github] .seg{border-radius:3px}
[data-style=github] .vms,[data-style=github] .ch{border-radius:6px}
[data-style=github] .tools-sheet,[data-style=github] .control-panel,[data-style=github] .cmd-dialog{border-radius:8px;box-shadow:none}
[data-style=github] .insight-stat,[data-style=github] .insight-list li{border-radius:6px}
[data-style=github] .sheet-tabs button{background:transparent;border-color:transparent;border-radius:6px}
[data-style=github] .sheet-tabs button[aria-pressed=true]{background:var(--card2);border-color:var(--line);color:var(--text);font-weight:600}
@media(min-width:1101px){[data-style=github] body.workspace-balanced #cols:not(.quiet){grid-template-columns:minmax(0,1.65fr) minmax(340px,1fr)}}
@media(max-width:640px){
 :root[data-style=github]{scroll-padding-top:68px}
 [data-style=github] .bar1{padding-top:0;gap:8px;min-height:56px}
 [data-style=github] .brand{font-size:14px;gap:7px}
 [data-style=github] .brand::before{width:26px;height:26px;font-size:10px}
 [data-style=github] .hero{margin-top:12px;padding:14px;gap:10px}
 [data-style=github] .verdict{font-size:22px}
 [data-style=github] #tiles{grid-template-columns:repeat(3,minmax(0,1fr))}
 [data-style=github] #tiles .tile{padding:10px;min-height:94px}
 [data-style=github] #tiles .tile:last-child{grid-column:auto;min-height:94px}
 [data-style=github] #tiles .tile .n{font-size:21px}
 [data-style=github] #tiles .tile .n small{font-size:11px}
 [data-style=github] #tiles .tile .d{font-size:11px}
 [data-style=github] .row{padding:12px;gap:10px}
 [data-style=github] .pr{min-height:32px;padding:2px 0;margin:0}
 [data-style=github] .inspect-open{min-height:44px}
 [data-style=github] .gh{scroll-margin-top:68px}
 [data-style=github] .activity-tools .flt{flex:1;min-height:44px}
 [data-style=github] .filters-open{min-height:44px}
 [data-style=github] .bottom-nav{left:0;right:0;bottom:0;border:0;border-top:1px solid var(--line);border-radius:0;background:var(--bg);box-shadow:none;backdrop-filter:none;-webkit-backdrop-filter:none;padding:0 8px env(safe-area-inset-bottom)}
 [data-style=github] .bottom-nav a,[data-style=github] .bottom-nav button{border-radius:0;min-height:56px;border-top:2px solid transparent}
 [data-style=github] .bottom-nav a.active{background:none;border-top-color:var(--acc)}
 [data-style=github] .tools-sheet,[data-style=github] .control-panel{border-radius:0}
}
/* Octicons are filled paths, not stroked approximations. */
svg.i.octicon,[data-style=github] svg.i.octicon{fill:currentColor;stroke:none;stroke-width:0;width:16px;height:16px;vertical-align:text-bottom;overflow:visible}
[data-icon]{display:inline-flex;align-items:center;justify-content:center;flex:none}
.brand-icon,.nav-icon{display:none}
:root[data-style=github]{--ui:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif,"Apple Color Emoji","Segoe UI Emoji"}
[data-style=github] body{line-height:1.5}
[data-style=github] .brand-icon,[data-style=github] .nav-icon{display:inline-flex}
[data-style=github] .brand-icon svg.i.octicon{width:24px;height:24px}
[data-style=github] .brand::before{display:none}
[data-style=github] .jump a{gap:8px}
[data-style=github] .brand,[data-style=github] .verdict,[data-style=github] .h2 h2,[data-style=github] .mh h3,[data-style=github] #tiles .tile .n,[data-style=github] .jump a.active{font-weight:600}
[data-style=github] .verdict,[data-style=github] .h2 h2,[data-style=github] .inspect-title{letter-spacing:normal;line-height:1.25}
[data-style=github] .meta,[data-style=github] .sheet-intro{line-height:1.5}
[data-style=github] code,[data-style=github] .mono,[data-style=github] .runner-tag,[data-style=github] kbd{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace}
[data-style=github] .dashboard-menu,[data-style=github] .machine-more{font-size:14px}
[data-style=github] .filters-open{display:inline-flex;align-items:center;gap:6px}
.inspect-open .i{width:12px!important;height:12px!important;margin-left:2px}
[data-style=github] .bottom-nav svg.i.octicon{width:20px;height:20px}
@media(max-width:640px){[data-style=github] .brand-icon svg.i.octicon{width:20px;height:20px}}
/* Quiet depth: advanced tools live in opaque, readable sheets. */
.tools-sheet{background:var(--bg);width:min(760px,calc(100vw - 28px))}.tools-sheet>header{background:var(--bg)}
.sheet-body{padding:20px;overflow-wrap:anywhere}.sheet-intro{color:var(--muted);font-size:13px;line-height:1.6;margin:0 0 20px}.sheet-tabs{display:flex;gap:6px;padding:12px 18px;border-bottom:1px solid var(--line);flex-wrap:wrap}.sheet-tabs button[aria-pressed="true"]{background:var(--accbg);color:var(--acc);border-color:var(--acc)}
.insight-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:22px}.insight-stat{padding:16px;border:1px solid var(--line);border-radius:14px;background:var(--card)}.insight-stat b{display:block;font-size:26px;letter-spacing:-1px}.insight-stat span{font-size:12px;color:var(--muted)}
.insight-list{list-style:none;padding:0;margin:0;display:grid;gap:8px}.insight-list li{padding:14px;border:1px solid var(--line);border-radius:12px;min-width:0}.insight-list small{display:block;color:var(--muted);line-height:1.6;margin-top:4px}.insight-list button{max-width:100%;white-space:normal;text-align:left}.sheet-actions{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 0}.sheet-heading{font-size:14px;margin:24px 0 12px}.inspect-facts{display:grid;grid-template-columns:110px minmax(0,1fr);gap:10px 16px;margin:18px 0}.inspect-facts dt{font-size:12px;color:var(--muted)}.inspect-facts dd{margin:0;font-size:13px;min-width:0}.inspect-title{font-size:20px;letter-spacing:-.4px;line-height:1.4;margin:0 0 6px}.inspect-open{display:block;margin-left:auto;border:0;background:transparent;color:var(--muted);font:inherit;font-size:11px;min-height:32px;padding:4px 0 0 12px;cursor:pointer}.inspect-open:hover{color:var(--acc)}.page-more{display:flex;justify-content:center;align-items:center;gap:12px;padding:14px;color:var(--muted);font-size:12px;border-top:1px solid var(--line)}.search-tip{font-size:12px;color:var(--muted);line-height:1.7;margin:12px 0 0}.cmd-item .cmd-label{flex:1;min-width:0;overflow-wrap:anywhere}.cmd-item .cmd-label small{display:block;font-size:11px;margin:2px 0 0}.cmd-count{padding:8px 12px;font-size:11px;color:var(--muted)}
@media(max-width:640px){.tools-sheet{width:100vw;max-width:none;height:100dvh;max-height:100dvh;border-radius:0}.sheet-body{padding:16px}.insight-grid{gap:6px}.insight-stat{padding:12px 9px}.insight-stat b{font-size:22px}.inspect-facts{grid-template-columns:90px minmax(0,1fr)}.inspect-open{min-height:44px}.sheet-tabs button{flex:1}.page-more{flex-wrap:wrap}}
/* Semantic comparison table stays readable without a horizontal page scroll. */
.comparison-table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:var(--type-sm)}.comparison-table th,.comparison-table td{padding:12px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;overflow-wrap:anywhere}.comparison-table th{font-weight:600}.comparison-table th:first-child{width:28%}.comparison-table th[scope=row]{color:var(--muted);font-weight:500}.comparison-table thead{background:var(--card2)}
#compareGrid,[data-style=github] #compareGrid{display:block;padding:16px 20px 20px}#compareGrid>.comparison-table,[data-style=github] #compareGrid>.comparison-table{padding:0;border:0}
@media(max-width:640px){#compareGrid,[data-style=github] #compareGrid{padding:12px}.comparison-table th:first-child{width:27%}.comparison-table th,.comparison-table td{padding:10px 6px}}
/* Git reference colors and components: GitHub Primer primitives 11.10.0. */
:root{--git-link:#0969da;--git-muted:#59636e;--git-branch-bg:#ddf4ff;--git-open:#1a7f37;--git-closed:#d1242f;--git-merged:#8250df;--git-draft:#59636e;--git-open-bg:#1f883d;--git-closed-bg:#cf222e;--git-merged-bg:#8250df;--git-draft-bg:#59636e;}
:root[data-theme=dark]{--git-link:#4493f8;--git-muted:#9198a1;--git-branch-bg:#388bfd1a;--git-open:#3fb950;--git-closed:#f85149;--git-merged:#ab7df8;--git-draft:#9198a1;--git-open-bg:#238636;--git-closed-bg:#da3633;--git-merged-bg:#8957e5;--git-draft-bg:#656c76;}

.git-repo,.git-ref,.git-pr{display:inline-flex;align-items:center;gap:4px;min-width:0;max-width:100%;font-size:var(--type-xs);line-height:1.5;vertical-align:middle;text-decoration:none;overflow-wrap:anywhere}
a.git-repo,[data-style=github] a.repo.git-repo{color:var(--git-link);font-weight:400}.git-repo .git-repo-name{font-weight:600}.git-repo .i,.git-ref>.i{color:var(--git-muted);flex:none}.git-repo-path{min-width:0;overflow-wrap:anywhere}.git-owner{font-weight:400}.git-separator{color:var(--git-muted);padding:0 2px}
.git-ref{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;font-weight:400}
a.git-branch,[data-style=github] a.git-branch{display:inline-block;padding:2px 6px;font:inherit;color:var(--git-link);background:var(--git-branch-bg);border-radius:6px;text-decoration:none;overflow-wrap:anywhere;max-width:100%}
a.git-branch:hover{background:color-mix(in srgb,var(--git-link) 20%,var(--git-branch-bg));text-decoration:none}
a.git-commit,[data-style=github] a.git-commit{font:inherit;color:var(--git-link);text-decoration:none;white-space:nowrap}
a.git-commit:hover,.git-repo:hover .git-repo-path{text-decoration:underline}
a.pr.git-pr,[data-style=github] a.pr.git-pr{padding:0;background:none;border:0;border-radius:0;min-height:24px;gap:4px;font-size:var(--type-xs);font-weight:400;color:var(--git-muted);margin:0;text-decoration:none;filter:none}
a.pr.git-pr:hover,[data-style=github] a.pr.git-pr:hover{color:var(--git-link);text-decoration:underline}.git-pr[data-pr-state=open]>.i{color:var(--git-open)}.git-pr[data-pr-state=closed]>.i{color:var(--git-closed)}.git-pr[data-pr-state=merged]>.i{color:var(--git-merged)}.git-pr[data-pr-state=draft]>.i,.git-pr[data-pr-state=unknown]>.i{color:var(--git-draft)}
.git-state-label{display:inline-flex;align-items:center;gap:4px;padding:4px 8px;font-size:var(--type-xs);line-height:16px;font-weight:600;border-radius:999px;color:#fff;background:var(--git-draft-bg);white-space:nowrap}.git-state-label[data-pr-state=open]{background:var(--git-open-bg)}.git-state-label[data-pr-state=closed]{background:var(--git-closed-bg)}.git-state-label[data-pr-state=merged]{background:var(--git-merged-bg)}
.git-pr-card{padding:16px 0;border-top:1px solid var(--line);margin-top:16px}.git-pr-title{font-size:var(--type-heading);font-weight:600;color:var(--text);line-height:1.4;overflow-wrap:anywhere}.git-pr-title .git-pr-number{font-weight:400;color:var(--git-muted)}.git-pr-card-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px}.git-pr-card-meta .git-ref{font-size:var(--type-xs)}.git-context{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.git-repo-summary{display:flex;gap:8px;justify-content:space-between;align-items:center;flex-wrap:wrap}.git-repo-summary .git-repo{font-size:var(--type-base)}
:root[data-color=deuteranopia]{--git-open:var(--ok);--git-closed:var(--crit);--git-merged:var(--text)}
@media(max-width:640px){a.pr.git-pr,[data-style=github] a.pr.git-pr{min-height:32px}.git-ref{min-height:32px;align-items:center}.git-pr-card{padding:16px 0}}
/* Component contract: one scale and one interaction language throughout. */
:root{--ui-gap:8px;--ui-padding:20px;--ui-control:36px;--ui-ring:2px solid var(--acc);--type-xs:calc(12px * var(--text-scale));--type-sm:calc(13px * var(--text-scale));--type-base:calc(14px * var(--text-scale));--type-heading:calc(16px * var(--text-scale));--type-title:calc(20px * var(--text-scale));--type-verdict:calc(24px * var(--text-scale))}
dialog{background:var(--bg);max-height:calc(100dvh - 32px);overflow:auto;box-shadow:none}
dialog>header,dialog.wide-dialog>header,.menu-head{display:flex;align-items:center;gap:12px;padding:12px var(--ui-padding);border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:2}
dialog>header h2,.menu-head h2{padding:0;border:0;flex:1;font-size:var(--type-heading);font-weight:600;line-height:1.5}
dialog .dialog-x{display:inline-flex;align-items:center;justify-content:center;min-width:36px;min-height:36px;padding:8px;flex:none}
dialog>form.dialog-form{padding:0}.dialog-form-body{padding:var(--ui-padding);display:grid;gap:16px}.dialog-form-body p{margin:0;color:var(--muted);font-size:var(--type-sm);line-height:1.5}
.dialog-footer{display:flex;justify-content:flex-end;gap:8px;padding:12px var(--ui-padding);border-top:1px solid var(--line);background:var(--bg)}
.btn-primary{background:var(--acc)!important;color:var(--bg)!important;border-color:transparent!important;font-weight:600!important}.btn-primary:hover{filter:brightness(.94)}.btn-danger{color:var(--crit)!important;border-color:color-mix(in srgb,var(--crit) 45%,var(--line))!important}.btn-danger:hover{background:var(--critbg)!important}
.form-help{font-size:var(--type-xs);color:var(--muted);line-height:1.5}.field-label{font-size:var(--type-sm);font-weight:600}.field-input{width:100%;font:inherit;background:var(--card2);border:1px solid var(--line);border-radius:var(--control-radius);color:var(--text);padding:8px 12px;min-height:var(--ui-control)}
button:disabled{opacity:.45;cursor:not-allowed}button[aria-pressed=true]{border-color:var(--acc)}input[type=checkbox]{accent-color:var(--acc);width:16px;height:16px;margin:0;flex:none}
.saved-row{gap:8px;flex-wrap:wrap}.saved-row b{min-width:0;overflow-wrap:anywhere}.saved-row small{font-size:var(--type-xs);color:var(--muted)}.saved-row .saved-delete{min-width:36px;padding:8px}
.inspect-facts{padding:0;align-items:start}.inspect-facts dd{text-align:left;overflow-wrap:anywhere;line-height:1.5}.inspect-facts dt{line-height:1.5}.inspect-facts dd .status-badge{display:inline-flex}
.status-badge{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);border-radius:999px;padding:1px 8px;font-size:var(--type-xs);font-weight:500;white-space:nowrap}.status-badge.running{color:var(--acc);background:var(--accbg)}.status-badge.queued{color:var(--warn);background:var(--warnbg)}
.sr-only-label{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
[data-style=github] dialog{border-radius:8px}
[data-style=github] .btn,[data-style=github] .qf,[data-style=github] .smallctl,[data-style=github] .control-panel .btn,[data-style=github] .control-panel .qf{min-height:var(--ui-control);font-size:var(--type-sm);border-radius:6px;font-weight:500;padding:0 12px}
[data-style=github] .btn:not(.btn-primary):not(.panel-done){background:var(--card2)}
[data-style=github] .qf{background:transparent;color:var(--muted);border-color:transparent}
[data-style=github] .qf.on{background:var(--card2);border-color:var(--line);color:var(--text);font-weight:600}
[data-style=github] .qfs{gap:4px;padding:4px;background:var(--bg);border:1px solid var(--line);border-radius:6px}
[data-style=github] .text-btn{font-size:var(--type-sm);min-height:var(--ui-control);padding:6px 8px;border-radius:6px}
[data-style=github] .btn:focus-visible,[data-style=github] input:focus-visible,[data-style=github] select:focus-visible,[data-style=github] textarea:focus-visible,[data-style=github] summary:focus-visible,[data-style=github] .text-btn:focus-visible{outline:var(--ui-ring);outline-offset:2px}
[data-style=github] .setting>span,[data-style=github] .setting legend{font-size:var(--type-xs);font-weight:600;color:var(--text)}
[data-style=github] .setting select,[data-style=github] .setting input,[data-style=github] #note-text,[data-style=github] .field-input{font-size:var(--type-base);min-height:var(--ui-control);background:var(--bg);border-radius:6px;padding:7px 10px}
[data-style=github] .checks{gap:8px}.checks label{cursor:pointer;min-height:36px}
[data-style=github] .checks label{background:none;border:0;border-radius:0;padding:4px 0;font-size:var(--type-sm);margin-right:8px}
[data-style=github] .control-section{padding:20px;border-bottom:1px solid var(--line)}
[data-style=github] .control-section h3{font-size:var(--type-sm);color:var(--text);font-weight:600;margin-bottom:12px}
[data-style=github] .control-section>summary{font-size:var(--type-base);min-height:28px;font-weight:600}
[data-style=github] .control-row{gap:8px 12px}.control-row .setting{min-width:0}
[data-style=github] .settings-grid{gap:16px 20px}
[data-style=github] .panel-footer,[data-style=github] .dialog-footer{padding:12px 20px}
[data-style=github] .sheet-body{padding:20px}
[data-style=github] .sheet-intro,[data-style=github] .search-tip,[data-style=github] .style-note{font-size:var(--type-sm);line-height:1.5}
[data-style=github] .sheet-intro{margin-bottom:16px}
[data-style=github] .sheet-heading{font-size:var(--type-base);font-weight:600;margin:24px 0 12px}
[data-style=github] .inspect-title{font-size:var(--type-title);font-weight:600;line-height:1.4;letter-spacing:normal}
[data-style=github] .inspect-facts{gap:12px 16px;margin:20px 0;grid-template-columns:112px minmax(0,1fr)}
[data-style=github] .inspect-facts dt{font-size:var(--type-xs)}[data-style=github] .inspect-facts dd{font-size:var(--type-base)}
[data-style=github] .sheet-tabs{gap:4px;padding:8px 12px;background:var(--bg)}
[data-style=github] .sheet-tabs button{border:0;border-bottom:2px solid transparent!important;background:none!important;border-radius:0;min-height:40px;padding:8px 12px;color:var(--muted)}
[data-style=github] .sheet-tabs button[aria-pressed=true]{border-bottom-color:var(--acc)!important;color:var(--text);font-weight:600}
[data-style=github] .insight-grid{gap:12px;margin-bottom:20px}
[data-style=github] .insight-stat{padding:16px}.insight-stat b{line-height:1.25}
[data-style=github] .insight-stat b{font-size:var(--type-verdict);font-weight:600;letter-spacing:normal}
[data-style=github] .insight-stat span,[data-style=github] .insight-list small{font-size:var(--type-xs);line-height:1.5}
[data-style=github] .insight-list li{padding:16px;background:var(--card);border-radius:6px}
[data-style=github] .insight-list b{font-size:var(--type-base);font-weight:600}
[data-style=github] .sheet-actions{padding-top:16px;margin-top:16px;border-top:1px solid var(--line);gap:8px}
[data-style=github] .insight-list .sheet-actions{padding:0;border:0;margin-top:8px}
[data-style=github] .h2 h2,[data-style=github] .mh h3{font-size:var(--type-heading);font-weight:600;line-height:1.5}
[data-style=github] .verdict{font-size:var(--type-verdict)}
[data-style=github] .jt,[data-style=github] .gh h3,[data-style=github] .vm b{font-size:var(--type-base);font-weight:600}
[data-style=github] .meta,[data-style=github] .h2 .c,[data-style=github] .vsub,[data-style=github] .fresh-machine,[data-style=github] .tmw small,[data-style=github] .runner-tag,[data-style=github] .pr,[data-style=github] .tile .d,[data-style=github] .tile .k{font-size:var(--type-xs);line-height:1.5}
[data-style=github] .tm,[data-style=github] .inspect-open{font-size:var(--type-xs)}
[data-style=github] .machine-health{border:1px solid var(--line);border-radius:999px;padding:1px 7px;font-size:var(--type-xs);font-weight:500}
[data-style=github] .machine-health.issue{color:var(--warn);background:var(--warnbg)}[data-style=github] .machine-health.ok{color:var(--ok);background:var(--okbg)}
[data-style=github] .sla,[data-style=github] .st{font-size:var(--type-xs);font-weight:500;padding:1px 7px;border:1px solid var(--line);line-height:1.5}
[data-style=github] .machine>summary.mh{gap:6px 8px;padding:12px 52px 12px 16px}
[data-style=github] .machine-more{top:10px;right:8px;min-width:36px;min-height:36px;display:grid;place-items:center}
[data-style=github] .meters{gap:12px;padding-top:16px;padding-bottom:4px}
[data-style=github] .mt .l,[data-style=github] .memory-facts{font-size:var(--type-xs)}
[data-style=github] .mt em{display:inline-flex;gap:4px;align-items:center;font-style:normal;font-size:var(--type-xs)}
[data-style=github] .vm{padding:10px 12px;gap:8px}[data-style=github] .vm .s,[data-style=github] .vm .w{font-size:var(--type-xs);line-height:1.5}
[data-style=github] .compare-grid{grid-template-columns:minmax(90px,.8fr) repeat(2,minmax(0,1fr));padding:16px 20px 20px;font-size:var(--type-sm)}
[data-style=github] .compare-grid>*{padding:12px 8px;overflow-wrap:anywhere;min-width:0}[data-style=github] .compare-grid b{font-weight:600}
[data-style=github] .toast,[data-style=github] .compare-tray{border:1px solid var(--line);border-radius:6px;background:var(--card2);color:var(--text);box-shadow:none;font-size:var(--type-sm)}
[data-style=github] .toast{padding:10px 16px}[data-style=github] .compare-tray{flex-wrap:wrap;justify-content:center;max-width:calc(100vw - 24px)}
[data-style=github] .cmd-head{padding:12px;gap:8px;background:var(--bg)}[data-style=github] #cmd-in{font-size:var(--type-base);min-height:36px}
[data-style=github] .cmd-item{font-size:var(--type-base);border-radius:6px;padding:10px 12px}[data-style=github] .cmd-label small{font-size:var(--type-xs)}
[data-style=github] .machine-menu-items{padding:8px}[data-style=github] .machine-menu-items button{font-size:var(--type-base);padding:10px 12px;min-height:40px;border-radius:6px}
[data-style=github] .timeline{padding:16px 20px 20px;font-size:var(--type-sm)}[data-style=github] .timeline li{padding:12px 0 12px 20px}[data-style=github] .timeline time{font-size:var(--type-xs);margin-top:4px}
[data-style=github] #help dl{padding:20px;font-size:var(--type-sm);gap:12px 16px}[data-style=github] #help dd{text-align:right}
[data-style=github] .tour-body{padding:20px}.tour-body h3{margin:0}.tour-body p{line-height:1.5}[data-style=github] .tour-step{font-size:var(--type-xs);margin-bottom:12px}
[data-style=github] .tour-actions{padding:12px 20px;border-top:1px solid var(--line)}
[data-style=github] body.density-compact .row,[data-style=github] body.activity-compact .row{padding-top:8px;padding-bottom:8px}
[data-style=github] body.high-contrast .card,[data-style=github] body.high-contrast .hero,[data-style=github] body.high-contrast #tiles,[data-style=github] body.high-contrast dialog{border-width:2px;border-color:var(--text);background:var(--bg)}
@media(max-width:640px){
 :root{--ui-padding:16px;--ui-control:44px}
 dialog{max-height:calc(100dvh - 24px)}dialog.wide-dialog{height:100dvh;max-height:100dvh}[data-style=github] dialog.wide-dialog{border-radius:0}
 [data-style=github] .btn,[data-style=github] .qf,[data-style=github] .smallctl,[data-style=github] .text-btn,[data-style=github] .control-panel .btn,[data-style=github] .control-panel .qf{min-height:44px}
 [data-style=github] .top .btn{min-width:44px;min-height:44px;padding:8px}
 [data-style=github] .sheet-body,[data-style=github] .control-section{padding:16px}
 [data-style=github] .dialog-footer,[data-style=github] .panel-footer,[data-style=github] .tour-actions{padding:12px 16px}
 [data-style=github] .control-row .setting{min-width:100%}
 [data-style=github] .sheet-tabs{padding:8px}.sheet-tabs button{white-space:normal}
 [data-style=github] .insight-grid{gap:8px}[data-style=github] .insight-stat{padding:12px 8px}
 [data-style=github] .insight-stat b{font-size:var(--type-title)}
 [data-style=github] .inspect-facts{grid-template-columns:88px minmax(0,1fr);gap:12px}
 [data-style=github] .machine-more{min-width:44px;min-height:44px;top:6px;right:4px}
 [data-style=github] .checks label{min-height:44px}
 [data-style=github] .compare-grid{grid-template-columns:80px repeat(2,minmax(0,1fr));padding:12px}
 [data-style=github] .saved-row b{flex-basis:100%}
 [data-style=github] .timeline{padding:16px}[data-style=github] #help dl{padding:16px;grid-template-columns:minmax(0,1fr) auto}
}
/* Flat surface policy: no glass, gradients, blur, glow, or soft shadows. */
:root{--shadow:none}
html body{background-image:none!important}
.card,.hero,.tile,dialog,.top,.top .bar1,.bottom-nav,.toast,.compare-tray{backdrop-filter:none!important;-webkit-backdrop-filter:none!important;box-shadow:none!important;background-image:none!important}
.top,.bottom-nav{background:var(--bg)!important;border-color:var(--line)}
.card,.hero,#tiles .tile{background:var(--card)}
.activity-tools .flt{background:var(--bg)}
.ch .mx,.ch .mn{background:var(--card2)}
.ch .ar,.mini .ar{display:none}
.shimmer{background:var(--track);animation:none}
.pulse{animation:none;box-shadow:none}
.bar i.hat{background:color-mix(in srgb,var(--fc) 45%,var(--card));border-left:1px solid var(--text)}
.row.k-gave{background:var(--critbg)}
.hero::after{background:none}
</style></head><body>
<header class="top" id="top"><div class="wrap bar1">
 <div class="brand" aria-label="Runner Status"><span class="brand-icon" aria-hidden="true" data-icon="repo"></span><span class="wide">Runners</span><span class="narrow">RS</span></div>
 <nav class="jump" aria-label="Jump to"><a href="#activity" aria-label="Activity"><span class="nav-icon" aria-hidden="true" data-icon="play"></span><span class="nav-full">Activity</span><span class="nav-short" aria-hidden="true">Act</span></a><a href="#hosts" aria-label="Machines"><span class="nav-icon" aria-hidden="true" data-icon="server"></span><span class="nav-full">Machines</span><span class="nav-short" aria-hidden="true">Mac</span></a><a href="#github" aria-label="GitHub"><span class="nav-icon" aria-hidden="true" data-icon="github"></span><span class="nav-full">GitHub</span><span class="nav-short" aria-hidden="true">GH</span></a></nav>
 <div class="fresh" id="fresh" role="status" aria-live="off"><i class="pulse"></i><span id="freshTx">Connecting…</span></div>
 <div class="utility">
  <button class="btn" id="refresh" type="button" aria-label="Refresh now" title="Refresh now"><span id="refreshIcon" aria-hidden="true" data-icon="refresh"></span><span class="refresh-count" id="refreshCount">15</span></button>
  <button class="btn dashboard-menu" id="settingsb" type="button" aria-label="Open dashboard controls" title="Dashboard controls"><span aria-hidden="true" data-icon="gear"></span><span class="sr">Dashboard controls</span></button>
 </div>
</div><div class="lostbar" id="lost" role="alert" hidden><div class="wrap"></div></div></header>
<main class="wrap">
 <section class="hero wait" id="hero" aria-label="Overall status"><div class="vrow"><div class="vicon"></div><div><h1 class="verdict">Checking…</h1><p class="vsub">Fetching the first status snapshot.</p></div></div></section>
 <nav class="tiles" id="tiles" aria-label="Summary"></nav>
 <div id="changes" aria-live="polite"></div>
 <div class="cols" id="cols">
  <div class="colA">
   <div class="h2 activity-h" id="activity"><h2>Activity</h2><span class="c" id="actc"></span><div class="activity-tools"><label class="flt"><span aria-hidden="true" data-icon="search"></span><span class="sr">Search runner, repository, workflow, branch or pull request</span><input id="flt" type="search" placeholder="Search" autocomplete="off"><button class="flt-clear" id="flt-clear" type="button" aria-label="Clear search" hidden>×</button><kbd>/</kbd></label><button class="smallctl filters-open" id="filtersb" type="button" aria-haspopup="dialog"><span aria-hidden="true" data-icon="filter"></span>Filters<span id="filterCount" hidden></span></button></div><div class="filter-summary" id="filterSummary" hidden><span id="filterSummaryTx"></span><span class="matchc" id="matchc" aria-live="polite"></span><button class="text-btn" id="filters-reset" type="button">Clear</button></div></div>
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
<nav class="bottom-nav" aria-label="Mobile navigation"><a href="#activity" data-mobile-nav="activity"><span aria-hidden="true" data-icon="play"></span><span>Activity</span></a><a href="#hosts" data-mobile-nav="hosts"><span aria-hidden="true" data-icon="server"></span><span>Machines</span></a><a href="#github" data-mobile-nav="github"><span aria-hidden="true" data-icon="github"></span><span>GitHub</span></a><button type="button" id="mobile-more"><span aria-hidden="true" data-icon="more"></span><span>More</span></button></nav>
<div class="compare-tray" id="compareTray" hidden><span id="compareTx">Select two machines</span><button class="btn" id="compareOpen" type="button" disabled>Compare</button><button class="btn" id="compareClear" type="button" aria-label="Clear comparison">×</button></div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<dialog id="help" aria-labelledby="help-h"><header><h2 id="help-h">Keyboard shortcuts</h2><button class="dialog-x" type="button" data-close="help" aria-label="Close">×</button></header><dl>
<dt>Find anything</dt><dd><kbd>⌘</kbd> <kbd>K</kbd></dd><dt>Search activity</dt><dd><kbd>/</kbd></dd><dt>Next or previous item</dt><dd><kbd>J</kbd> / <kbd>K</kbd></dd><dt>Open or close alerts</dt><dd><kbd>A</kbd></dd><dt>Show or hide idle runners</dt><dd><kbd>I</kbd></dd><dt>Pause live updates</dt><dd><kbd>P</kbd></dd><dt>Change theme</dt><dd><kbd>T</kbd></dd><dt>Move a chart cursor</dt><dd><kbd>←</kbd> <kbd>→</kbd></dd><dt>This help</dt><dd><kbd>?</kbd></dd><dt>Clear filter or chart lock</dt><dd><kbd>Esc</kbd></dd></dl>
<form method="dialog" class="dialog-form"><footer class="dialog-footer"><button class="btn">Close</button></footer></form></dialog>
<dialog id="settings" class="wide-dialog control-panel" aria-labelledby="settings-h"><header><h2 id="settings-h">Dashboard controls</h2><button class="dialog-x" type="button" data-close="settings" aria-label="Close">×</button></header>
 <section class="control-section"><h3>Explore</h3><div class="control-row"><button class="btn" type="button" data-explore="overview">Queue insights</button><button class="btn" type="button" data-explore="repos">Repositories</button><button class="btn" type="button" data-explore="watch">Watchlist</button><button class="btn" type="button" id="find-anything">Find anything <kbd>⌘K</kbd></button></div></section>
 <section class="control-section" id="filterControls"><h3>Activity</h3><div class="qfs" role="group" aria-label="Quick filters"><button class="qf on" data-qf="all">All</button><button class="qf" data-qf="attention">Needs attention</button><button class="qf" data-qf="running">In progress</button><button class="qf" data-qf="queued">Queued</button><button class="qf" data-qf="offline">Offline</button><button class="qf" data-qf="idle">Idle</button></div><div class="control-row"><label class="setting"><span>Sort and group</span><select class="smallctl sort" id="order" aria-label="Order or group activity"><option value="age">Order: age</option><option value="severity">Order: severity</option><option value="repo">Group: repository</option><option value="machine">Group: machine</option></select></label><button class="btn" id="activity-view" type="button">Compact rows</button><button class="text-btn" id="panel-filters-reset" type="button">Reset filters</button><button class="btn" id="export-csv" type="button">Export matching jobs · CSV</button></div><p class="search-tip">Search precisely: <code>repo:firmware status:queued</code>, <code>label:linux</code>, <code>machine:"Mac Studio"</code>, or exclude with <code>-branch:main</code>. Combine terms to narrow results.</p></section>
 <details class="control-section"><summary>Appearance and layout</summary><div class="control-row"><button class="btn" id="theme" type="button"><span id="themeTx">Theme: auto</span></button></div><div class="settings-grid" id="settingsGrid"></div></details>
 <details class="control-section"><summary>Live data and history</summary><div class="control-row"><button class="btn pause" id="pause" type="button" aria-label="Pause live updates"><span id="pauseIcon" aria-hidden="true" data-icon="pause"></span><span id="pauseTx">Pause live updates</span></button><button class="btn" id="timelineb" type="button">Timeline<span class="change-count" id="changeCount">0</span></button><button class="btn" id="copy-brief" type="button">Copy status brief</button><button class="btn" id="export-json" type="button">Export JSON</button></div><div class="tiles secondary-stats" id="secondaryStats"></div></details>
 <details class="control-section"><summary>Machines</summary><div class="control-row"><button class="btn" id="collapse-healthy" type="button">Collapse healthy</button><button class="btn" id="all-machines" type="button">Collapse all</button></div></details>
 <details class="control-section" id="savedControls"><summary>Saved views and sharing</summary><div class="saved" id="savedViews"></div><div class="control-row"><button class="btn" id="save-view" type="button">Save current view</button><button class="btn" id="share-view" type="button">Copy view link</button></div></details>
 <details class="control-section" id="helpControls"><summary>Help and reset</summary><div class="control-row"><button class="btn" id="helpb" type="button">Keyboard shortcuts</button><button class="btn" id="tour-start" type="button">Feature tour</button><button class="text-btn" id="reset-ui" type="button">Reset personalization</button></div></details>
 <footer class="panel-footer"><button class="btn panel-done" type="button" data-close="settings">Done</button></footer>
</dialog>
<dialog id="explore" class="wide-dialog tools-sheet" aria-labelledby="explore-h"><header><h2 id="explore-h">Explore</h2><button class="dialog-x" type="button" data-close="explore" aria-label="Close">×</button></header><div class="sheet-tabs" role="group" aria-label="Explore views"><button class="btn" data-explore="overview" type="button">Queue insights</button><button class="btn" data-explore="repos" type="button">Repositories</button><button class="btn" data-explore="watch" type="button">Watchlist</button></div><div class="sheet-body" id="exploreBody"></div></dialog>
<dialog id="inspect" class="wide-dialog tools-sheet" aria-labelledby="inspect-h"><header><h2 id="inspect-h">Job inspector</h2><button class="dialog-x" type="button" data-close="inspect" aria-label="Close">×</button></header><div class="sheet-body" id="inspectBody"></div></dialog>
<dialog id="machine-menu" aria-labelledby="machine-menu-h"><div class="menu-head"><h2 id="machine-menu-h">Machine actions</h2><button class="dialog-x" type="button" data-close="machine-menu" aria-label="Close">×</button></div><div class="machine-menu-items" id="machineMenuItems"></div></dialog>
<dialog id="cmd" class="cmd-dialog" aria-label="Find anything"><form method="dialog"><div class="cmd-head"><span aria-hidden="true">⌘</span><input id="cmd-in" type="search" placeholder="Find a job, machine, saved view, or command…" aria-label="Find anything" autocomplete="off"><kbd>Esc</kbd><button class="dialog-x" type="button" data-close="cmd" aria-label="Close">×</button></div><ul class="cmd-list" id="cmd-list"></ul></form></dialog>
<dialog id="timeline" class="wide-dialog" aria-labelledby="timeline-h"><header><h2 id="timeline-h">Alert and change timeline</h2><button class="dialog-x" type="button" data-close="timeline" aria-label="Close">×</button></header><ul class="timeline" id="timelineList"></ul></dialog>
<dialog id="compare" class="wide-dialog" aria-labelledby="compare-h"><header><h2 id="compare-h">Machine comparison</h2><button class="dialog-x" type="button" data-close="compare" aria-label="Close">×</button></header><div class="compare-grid" id="compareGrid"></div></dialog>
<dialog id="note" aria-labelledby="note-h"><header><h2 id="note-h">Machine note</h2><button class="dialog-x" type="button" data-close="note" aria-label="Close">×</button></header><form id="noteForm" class="dialog-form" method="dialog"><div class="dialog-form-body"><label class="setting"><span id="noteMachine">Machine</span><textarea id="note-text" rows="5" placeholder="Add a note for this machine" aria-describedby="noteHelp" maxlength="2000"></textarea></label><small class="form-help" id="noteHelp">Stored only on this device. Leave empty to remove the note.</small></div><footer class="dialog-footer"><button class="btn" value="cancel">Cancel</button><button class="btn btn-primary" value="save">Save note</button></footer></form></dialog>
<dialog id="view-name" aria-labelledby="view-name-h"><header><h2 id="view-name-h">Save view</h2><button class="dialog-x" type="button" data-close="view-name" aria-label="Close">×</button></header><form id="viewNameForm" class="dialog-form" method="dialog"><div class="dialog-form-body"><label class="setting"><span>View name</span><input class="field-input" id="viewNameInput" type="text" required maxlength="60" autocomplete="off" aria-describedby="viewNameHelp"></label><small class="form-help" id="viewNameHelp">Saves your current filters and appearance on this device. Up to 12 views.</small></div><footer class="dialog-footer"><button class="btn" type="button" data-close="view-name">Cancel</button><button class="btn btn-primary" type="submit">Save view</button></footer></form></dialog>
<dialog id="reset-confirm" aria-labelledby="reset-confirm-h" aria-describedby="resetHelp"><header><h2 id="reset-confirm-h">Reset personalization?</h2><button class="dialog-x" type="button" data-close="reset-confirm" aria-label="Close">×</button></header><form class="dialog-form" method="dialog"><div class="dialog-form-body"><p id="resetHelp">This resets appearance, filters, saved views, watchlist, machine pins and notes, and incident acknowledgements and snoozes on this device. This cannot be undone.</p><p>Live runner data, machines, and GitHub are not changed.</p></div><footer class="dialog-footer"><button class="btn" value="cancel">Cancel</button><button class="btn btn-danger" value="reset">Reset personalization</button></footer></form></dialog>
<dialog id="tour" aria-labelledby="tour-h"><header><h2 id="tour-h">Feature tour</h2><button class="dialog-x" type="button" data-close="tour" aria-label="Close">×</button></header><div class="tour-body"><div class="tour-step" id="tourStep"></div><p id="tourText"></p></div><footer class="tour-actions"><button class="btn" id="tourBack" type="button">Back</button><button class="btn" id="tourDone" type="button">Close</button><button class="btn btn-primary" id="tourNext" type="button">Next</button></footer></dialog>
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
 {id:"hosts",name:"Machines",re:/disk|VM |stats missing|memory|pressure|swap|load/i,href:"#hosts"},
 {id:"limits",name:"Limits and workflows",re:/quota|minutes|workflow/i,href:"#tiles"}];
const OTHER={id:"other",name:"Other",href:""};
const GAVE_FALLBACK=/gave up/i;      /* used only when why.gave_up is undefined */
const RESULT_BAD=/^(failed|gave up)/i; /* "ok", "retrying:", "dry run" and "already done" are not failures */
const CAUSE={maintenance:["Planned maintenance",""],"vm-stopped":["VM stopped","Start the VM by hand"],"service-dead":["Runner service died","Restart the runner service by hand"],network:["Network","Check the machine's network"],registration:["Registration lost","Re-register the runner with a new token"],"disk-full":["Disk full","Free up disk space"],"no-service":["No runner service","Install the runner service"],"host-silent":["Machine not reporting","Wake or reconnect the machine"],unknown:["Unknown cause","Check it by hand"]};
/* ===== */
/* GitHub Octicons. Source: https://github.com/primer/octicons/tree/ab05d0e8bbf64ecd6b08375044b016ecdac9ef6d
MIT License

Copyright (c) 2026 GitHub Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
const P={"check":"<path d=\"M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z\"/>","alert":"<path d=\"M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0 1 14.082 15H1.918a1.75 1.75 0 0 1-1.543-2.575Zm1.763.707a.25.25 0 0 0-.44 0L1.698 13.132a.25.25 0 0 0 .22.368h12.164a.25.25 0 0 0 .22-.368Zm.53 3.996v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z\"/>","x":"<path d=\"M2.344 2.343h-.001a8 8 0 0 1 11.314 11.314A8.002 8.002 0 0 1 .234 10.089a8 8 0 0 1 2.11-7.746Zm1.06 10.253a6.5 6.5 0 1 0 9.108-9.275 6.5 6.5 0 0 0-9.108 9.275ZM6.03 4.97 8 6.94l1.97-1.97a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734L9.06 8l1.97 1.97a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L8 9.06l-1.97 1.97a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734L6.94 8 4.97 6.03a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018Z\"/>","clock":"<path d=\"M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Zm7-3.25v2.992l2.028.812a.75.75 0 0 1-.557 1.392l-2.5-1A.751.751 0 0 1 7 8.25v-3.5a.75.75 0 0 1 1.5 0Z\"/>","play":"<path d=\"M0 1.75C0 .784.784 0 1.75 0h3.5C6.216 0 7 .784 7 1.75v3.5A1.75 1.75 0 0 1 5.25 7H4v4a1 1 0 0 0 1 1h4v-1.25C9 9.784 9.784 9 10.75 9h3.5c.966 0 1.75.784 1.75 1.75v3.5A1.75 1.75 0 0 1 14.25 16h-3.5A1.75 1.75 0 0 1 9 14.25v-.75H5A2.5 2.5 0 0 1 2.5 11V7h-.75A1.75 1.75 0 0 1 0 5.25Zm1.75-.25a.25.25 0 0 0-.25.25v3.5c0 .138.112.25.25.25h3.5a.25.25 0 0 0 .25-.25v-3.5a.25.25 0 0 0-.25-.25Zm9 9a.25.25 0 0 0-.25.25v3.5c0 .138.112.25.25.25h3.5a.25.25 0 0 0 .25-.25v-3.5a.25.25 0 0 0-.25-.25Z\"/>","pr":"<path d=\"M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z\"/>","chev":"<path d=\"M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z\"/>","off":"<path d=\"M7.25 2c-.69 0-1.351.13-1.957.371a.75.75 0 1 0 .554 1.394c.43-.17.903-.265 1.403-.265a3.72 3.72 0 0 1 3.541 2.496.75.75 0 0 0 .709.504c1.676 0 3 1.324 3 3a3 3 0 0 1-.681 1.92.75.75 0 0 0 1.156.955A4.496 4.496 0 0 0 16 9.5a4.472 4.472 0 0 0-3.983-4.471A5.222 5.222 0 0 0 7.25 2ZM.72 1.72a.75.75 0 0 1 1.06 0l2.311 2.31c.03.025.056.052.08.08l8.531 8.532.035.034 2.043 2.044a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215l-1.8-1.799a4.54 4.54 0 0 1-.42.019h-8A3.474 3.474 0 0 1 0 10.5c0-1.41.809-2.614 2.001-3.17a5.218 5.218 0 0 1 .646-2.622L.72 2.78a.75.75 0 0 1 0-1.06ZM3.5 7.25c.004.161.018.322.041.481a.75.75 0 0 1-.557.833c-.86.22-1.484.986-1.484 1.936 0 1.124.876 2 2 2h6.94L3.771 5.832A3.788 3.788 0 0 0 3.5 7.25Z\"/>","pause":"<path d=\"M5 2h1a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Zm5 0h1a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-1a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z\"/>","cloud":"<path d=\"M2 7.25A5.225 5.225 0 0 1 7.25 2a5.222 5.222 0 0 1 4.767 3.029A4.472 4.472 0 0 1 16 9.5c0 2.505-1.995 4.5-4.5 4.5h-8A3.474 3.474 0 0 1 0 10.5c0-1.41.809-2.614 2.001-3.17Zm1.54.482a.75.75 0 0 1-.556.832c-.86.22-1.484.987-1.484 1.936 0 1.124.876 2 2 2h8c1.676 0 3-1.324 3-3s-1.324-3-3-3a.75.75 0 0 1-.709-.504A3.72 3.72 0 0 0 7.25 3.5C5.16 3.5 3.5 5.16 3.5 7.25c.002.146.014.292.035.436l.004.036.001.008Z\"/>","plug":"<path d=\"M4 8H2.5a1 1 0 0 0-1 1v5.25a.75.75 0 0 1-1.5 0V9a2.5 2.5 0 0 1 2.5-2.5H4V5.133a1.75 1.75 0 0 1 1.533-1.737l2.831-.353.76-.913c.332-.4.825-.63 1.344-.63h.782c.966 0 1.75.784 1.75 1.75V4h2.25a.75.75 0 0 1 0 1.5H13v4h2.25a.75.75 0 0 1 0 1.5H13v.75a1.75 1.75 0 0 1-1.75 1.75h-.782c-.519 0-1.012-.23-1.344-.63l-.761-.912-2.83-.354A1.75 1.75 0 0 1 4 9.867Zm6.276-4.91-.95 1.14a.753.753 0 0 1-.483.265l-3.124.39a.25.25 0 0 0-.219.248v4.734c0 .126.094.233.219.249l3.124.39a.752.752 0 0 1 .483.264l.95 1.14a.25.25 0 0 0 .192.09h.782a.25.25 0 0 0 .25-.25v-8.5a.25.25 0 0 0-.25-.25h-.782a.25.25 0 0 0-.192.09Z\"/>","refresh":"<path d=\"M1.705 8.005a.75.75 0 0 1 .834.656 5.5 5.5 0 0 0 9.592 2.97l-1.204-1.204a.25.25 0 0 1 .177-.427h3.646a.25.25 0 0 1 .25.25v3.646a.25.25 0 0 1-.427.177l-1.38-1.38A7.002 7.002 0 0 1 1.05 8.84a.75.75 0 0 1 .656-.834ZM8 2.5a5.487 5.487 0 0 0-4.131 1.869l1.204 1.204A.25.25 0 0 1 4.896 6H1.25A.25.25 0 0 1 1 5.75V2.104a.25.25 0 0 1 .427-.177l1.38 1.38A7.002 7.002 0 0 1 14.95 7.16a.75.75 0 0 1-1.49.178A5.5 5.5 0 0 0 8 2.5Z\"/>","search":"<path d=\"M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215ZM11.5 7a4.499 4.499 0 1 0-8.997 0A4.499 4.499 0 0 0 11.5 7Z\"/>","server":"<path d=\"M1.75 1h12.5c.966 0 1.75.784 1.75 1.75v4c0 .372-.116.717-.314 1 .198.283.314.628.314 1v4a1.75 1.75 0 0 1-1.75 1.75H1.75A1.75 1.75 0 0 1 0 12.75v-4c0-.358.109-.707.314-1a1.739 1.739 0 0 1-.314-1v-4C0 1.784.784 1 1.75 1ZM1.5 2.75v4c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25v-4a.25.25 0 0 0-.25-.25H1.75a.25.25 0 0 0-.25.25Zm.25 5.75a.25.25 0 0 0-.25.25v4c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25v-4a.25.25 0 0 0-.25-.25ZM7 4.75A.75.75 0 0 1 7.75 4h4.5a.75.75 0 0 1 0 1.5h-4.5A.75.75 0 0 1 7 4.75ZM7.75 10h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 1 0-1.5ZM3 4.75A.75.75 0 0 1 3.75 4h.5a.75.75 0 0 1 0 1.5h-.5A.75.75 0 0 1 3 4.75ZM3.75 10h.5a.75.75 0 0 1 0 1.5h-.5a.75.75 0 0 1 0-1.5Z\"/>","repo":"<path d=\"M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z\"/>","github":"<path d=\"M6.766 11.328c-2.063-.25-3.516-1.734-3.516-3.656 0-.781.281-1.625.75-2.188-.203-.515-.172-1.609.063-2.062.625-.078 1.468.25 1.968.703.594-.187 1.219-.281 1.985-.281.765 0 1.39.094 1.953.265.484-.437 1.344-.765 1.969-.687.218.422.25 1.515.046 2.047.5.593.766 1.39.766 2.203 0 1.922-1.453 3.375-3.547 3.64.531.344.89 1.094.89 1.954v1.625c0 .468.391.734.86.547C13.781 14.359 16 11.53 16 8.03 16 3.61 12.406 0 7.984 0 3.563 0 0 3.61 0 8.031a7.88 7.88 0 0 0 5.172 7.422c.422.156.828-.125.828-.547v-1.25c-.219.094-.5.156-.75.156-1.031 0-1.64-.562-2.078-1.609-.172-.422-.36-.672-.719-.719-.187-.015-.25-.093-.25-.187 0-.188.313-.328.625-.328.453 0 .844.281 1.25.86.313.452.64.655 1.031.655s.641-.14 1-.5c.266-.265.47-.5.657-.656\"/>","more":"<path d=\"M8 9a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM1.5 9a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Zm13 0a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z\"/>","gear":"<path d=\"M8 0a8.2 8.2 0 0 1 .701.031C9.444.095 9.99.645 10.16 1.29l.288 1.107c.018.066.079.158.212.224.231.114.454.243.668.386.123.082.233.09.299.071l1.103-.303c.644-.176 1.392.021 1.82.63.27.385.506.792.704 1.218.315.675.111 1.422-.364 1.891l-.814.806c-.049.048-.098.147-.088.294.016.257.016.515 0 .772-.01.147.038.246.088.294l.814.806c.475.469.679 1.216.364 1.891a7.977 7.977 0 0 1-.704 1.217c-.428.61-1.176.807-1.82.63l-1.102-.302c-.067-.019-.177-.011-.3.071a5.909 5.909 0 0 1-.668.386c-.133.066-.194.158-.211.224l-.29 1.106c-.168.646-.715 1.196-1.458 1.26a8.006 8.006 0 0 1-1.402 0c-.743-.064-1.289-.614-1.458-1.26l-.289-1.106c-.018-.066-.079-.158-.212-.224a5.738 5.738 0 0 1-.668-.386c-.123-.082-.233-.09-.299-.071l-1.103.303c-.644.176-1.392-.021-1.82-.63a8.12 8.12 0 0 1-.704-1.218c-.315-.675-.111-1.422.363-1.891l.815-.806c.05-.048.098-.147.088-.294a6.214 6.214 0 0 1 0-.772c.01-.147-.038-.246-.088-.294l-.815-.806C.635 6.045.431 5.298.746 4.623a7.92 7.92 0 0 1 .704-1.217c.428-.61 1.176-.807 1.82-.63l1.102.302c.067.019.177.011.3-.071.214-.143.437-.272.668-.386.133-.066.194-.158.211-.224l.29-1.106C6.009.645 6.556.095 7.299.03 7.53.01 7.764 0 8 0Zm-.571 1.525c-.036.003-.108.036-.137.146l-.289 1.105c-.147.561-.549.967-.998 1.189-.173.086-.34.183-.5.29-.417.278-.97.423-1.529.27l-1.103-.303c-.109-.03-.175.016-.195.045-.22.312-.412.644-.573.99-.014.031-.021.11.059.19l.815.806c.411.406.562.957.53 1.456a4.709 4.709 0 0 0 0 .582c.032.499-.119 1.05-.53 1.456l-.815.806c-.081.08-.073.159-.059.19.162.346.353.677.573.989.02.03.085.076.195.046l1.102-.303c.56-.153 1.113-.008 1.53.27.161.107.328.204.501.29.447.222.85.629.997 1.189l.289 1.105c.029.109.101.143.137.146a6.6 6.6 0 0 0 1.142 0c.036-.003.108-.036.137-.146l.289-1.105c.147-.561.549-.967.998-1.189.173-.086.34-.183.5-.29.417-.278.97-.423 1.529-.27l1.103.303c.109.029.175-.016.195-.045.22-.313.411-.644.573-.99.014-.031.021-.11-.059-.19l-.815-.806c-.411-.406-.562-.957-.53-1.456a4.709 4.709 0 0 0 0-.582c-.032-.499.119-1.05.53-1.456l.815-.806c.081-.08.073-.159.059-.19a6.464 6.464 0 0 0-.573-.989c-.02-.03-.085-.076-.195-.046l-1.102.303c-.56.153-1.113.008-1.53-.27a4.44 4.44 0 0 0-.501-.29c-.447-.222-.85-.629-.997-1.189l-.289-1.105c-.029-.11-.101-.143-.137-.146a6.6 6.6 0 0 0-1.142 0ZM11 8a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM9.5 8a1.5 1.5 0 1 0-3.001.001A1.5 1.5 0 0 0 9.5 8Z\"/>","external":"<path d=\"M3.75 2h3.5a.75.75 0 0 1 0 1.5h-3.5a.25.25 0 0 0-.25.25v8.5c0 .138.112.25.25.25h8.5a.25.25 0 0 0 .25-.25v-3.5a.75.75 0 0 1 1.5 0v3.5A1.75 1.75 0 0 1 12.25 14h-8.5A1.75 1.75 0 0 1 2 12.25v-8.5C2 2.784 2.784 2 3.75 2Zm6.854-1h4.146a.25.25 0 0 1 .25.25v4.146a.25.25 0 0 1-.427.177L13.03 4.03 9.28 7.78a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042l3.75-3.75-1.543-1.543A.25.25 0 0 1 10.604 1Z\"/>","close":"<path d=\"M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734L9.06 8l3.22 3.22a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L8 9.06l-3.22 3.22a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06Z\"/>","filter":"<path d=\"M.75 3h14.5a.75.75 0 0 1 0 1.5H.75a.75.75 0 0 1 0-1.5ZM3 7.75A.75.75 0 0 1 3.75 7h8.5a.75.75 0 0 1 0 1.5h-8.5A.75.75 0 0 1 3 7.75Zm3 4a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z\"/>","pin":"<path d=\"m11.294.984 3.722 3.722a1.75 1.75 0 0 1-.504 2.826l-1.327.613a3.089 3.089 0 0 0-1.707 2.084l-.584 2.454c-.317 1.332-1.972 1.8-2.94.832L5.75 11.311 1.78 15.28a.749.749 0 1 1-1.06-1.06l3.969-3.97-2.204-2.204c-.968-.968-.5-2.623.832-2.94l2.454-.584a3.08 3.08 0 0 0 2.084-1.707l.613-1.327a1.75 1.75 0 0 1 2.826-.504ZM6.283 9.723l2.732 2.731a.25.25 0 0 0 .42-.119l.584-2.454a4.586 4.586 0 0 1 2.537-3.098l1.328-.613a.25.25 0 0 0 .072-.404l-3.722-3.722a.25.25 0 0 0-.404.072l-.613 1.328a4.584 4.584 0 0 1-3.098 2.537l-2.454.584a.25.25 0 0 0-.119.42l2.731 2.732Z\"/>","run":"<path d=\"m6.427 4.427 3.396 3.396a.25.25 0 0 1 0 .354l-3.396 3.396A.25.25 0 0 1 6 11.396V4.604a.25.25 0 0 1 .427-.177Z\"/>","branch":"<path d=\"M9.5 3.25a2.25 2.25 0 1 1 3 2.122V6A2.5 2.5 0 0 1 10 8.5H6a1 1 0 0 0-1 1v1.128a2.251 2.251 0 1 1-1.5 0V5.372a2.25 2.25 0 1 1 1.5 0v1.836A2.493 2.493 0 0 1 6 7h4a1 1 0 0 0 1-1v-.628A2.25 2.25 0 0 1 9.5 3.25Zm-6 0a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Zm8.25-.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5ZM4.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z\"/>","prClosed":"<path d=\"M3.25 1A2.25 2.25 0 0 1 4 5.372v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.251 2.251 0 0 1 3.25 1Zm9.5 5.5a.75.75 0 0 1 .75.75v3.378a2.251 2.251 0 1 1-1.5 0V7.25a.75.75 0 0 1 .75-.75Zm-2.03-5.273a.75.75 0 0 1 1.06 0l.97.97.97-.97a.748.748 0 0 1 1.265.332.75.75 0 0 1-.205.729l-.97.97.97.97a.751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018l-.97-.97-.97.97a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734l.97-.97-.97-.97a.75.75 0 0 1 0-1.06ZM2.5 3.25a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0ZM3.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm9.5 0a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z\"/>","prDraft":"<path d=\"M3.25 1A2.25 2.25 0 0 1 4 5.372v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.251 2.251 0 0 1 3.25 1Zm9.5 14a2.25 2.25 0 1 1 0-4.5 2.25 2.25 0 0 1 0 4.5ZM2.5 3.25a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0ZM3.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm9.5 0a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5ZM14 7.5a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Zm0-4.25a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Z\"/>","merge":"<path d=\"M5.45 5.154A4.25 4.25 0 0 0 9.25 7.5h1.378a2.251 2.251 0 1 1 0 1.5H9.25A5.734 5.734 0 0 1 5 7.123v3.505a2.25 2.25 0 1 1-1.5 0V5.372a2.25 2.25 0 1 1 1.95-.218ZM4.25 13.5a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm8.5-4.5a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5ZM5 3.25a.75.75 0 1 0 0 .005V3.25Z\"/>","commit":"<path d=\"M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z\"/>"};
const ic=(n,c)=>`<svg class="i octicon${c?" "+c:""}" viewBox="0 0 16 16" aria-hidden="true"><use href="#i-${n}"/></svg>`;
document.body.insertAdjacentHTML("afterbegin",`<svg width="0" height="0" style="position:absolute" aria-hidden="true">${Object.keys(P).map(k=>`<symbol id="i-${k}" viewBox="0 0 16 16">${P[k]}</symbol>`).join("")}</svg>`);
/* Static navigation and utility icons share the same local SVG sprite. */
for(const el of document.querySelectorAll('[data-icon]'))el.innerHTML=ic(el.dataset.icon);
for(const el of document.querySelectorAll('.dialog-x[data-close],.flt-clear,#compareClear'))el.innerHTML=ic("close");
const bytes=n=>{if(n==null)return"?";const dec=typeof PREF!=="undefined"&&PREF.units==="decimal",base=dec?1000:1024,u=dec?["B","kB","MB","GB","TB"]:["B","KiB","MiB","GiB","TiB"];let i=0;while(n>=base&&i<4){n/=base;i++}return(n>=100||i<3?Math.round(n):n.toFixed(1))+" "+u[i]};
/* links from data: only http(s) or "#" */
const url=u=>/^(https?:\/\/|#)/i.test(String(u||""))?String(u):"#";
const pad=n=>String(n).padStart(2,"0");
function elapsed(sec){sec=Math.max(0,sec);const d=Math.floor(sec/86400),h=Math.floor(sec%86400/3600),m=Math.floor(sec%3600/60),s=Math.floor(sec%60);return d?d+"d "+h+"h":h?h+"h "+pad(m)+"m":m+"m "+pad(s)+"s"}
const dur=m=>m==null?"-":m<1?"<1m":elapsed(m*60).replace(/ \d\ds$/,"").replace(/^0/,"");
const ago=s=>s<10?"just now":s<60?Math.floor(s)+"s ago":s<3600?Math.floor(s/60)+" min ago":Math.floor(s/3600)+"h "+Math.floor(s%3600/60)+"m ago";
const clock=d=>d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",hour12:typeof PREF!=="undefined"?!PREF.hour24:undefined});
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
const STYLES=[
 {id:"github",name:"GitHub",note:"Repository-style tabs, crisp bordered panels, compact activity rows, and understated status badges."},
 {id:"synthesis",name:"Synthesis II",note:"Solid cards, rounded corners, and balanced spacing."},
 {id:"minimal",name:"Minimal",note:"Quiet surfaces, lighter typography, and fewer visible borders."},
 {id:"outline",name:"Outline",note:"Square cards, strong edges, and crisp geometric controls."},
 {id:"editorial",name:"Editorial",note:"Serif headings, generous line spacing, and a narrower reading width."},
 {id:"terminal",name:"Terminal",note:"Monospaced typography, compact rows, and precise instrument-style meters."},
 {id:"blueprint",name:"Blueprint",note:"Dashed frames, technical labels, and measured spacing."},
 {id:"soft",name:"Soft",note:"Pill-shaped controls, round icons, larger curves, and airy cards."},
 {id:"studio",name:"Studio",note:"A centered, stacked workspace with a responsive machine-card gallery."},
 {id:"ledger",name:"Ledger",note:"Straight ruled panels, aligned job rows, and restrained table-like typography."},
 {id:"command",name:"Command",note:"A wider operational dashboard with bold headings and dense activity."},
];
const DEF={style:"github",density:"comfortable",scale:"100",activity:"cards",chart:60,workspace:"balanced",units:"binary",hour24:false,color:"standard",contrast:false,motion:"system",sla:20,focus:false,sections:{summary:true,activity:true,machines:true,github:true,history:true}};
let PREF={...DEF,sections:{...DEF.sections}};try{const p=JSON.parse(localStorage.getItem("rs-prefs")||"{}");PREF={...PREF,...p,sections:{...DEF.sections,...(p.sections||{})}}}catch(e){}
let PINS=new Set(),COMPARE=new Set(),NOTES={},ACK=new Set(),SNOOZE={},SAVED=[],LAST_SNAPSHOT=null;
try{PINS=new Set(JSON.parse(localStorage.getItem("rs-pins")||"[]"));NOTES=JSON.parse(localStorage.getItem("rs-notes")||"{}");ACK=new Set(JSON.parse(localStorage.getItem("rs-ack")||"[]"));SNOOZE=JSON.parse(localStorage.getItem("rs-snooze")||"{}");SAVED=JSON.parse(localStorage.getItem("rs-views")||"[]");LAST_SNAPSHOT=JSON.parse(localStorage.getItem("rs-snapshot")||"null")}catch(e){}
const save=(k,v)=>{try{localStorage.setItem(k,typeof v==="string"?v:JSON.stringify(v))}catch(e){}};
function persistPrefs(rerender=true){save("rs-prefs",PREF);applyPrefs();if(rerender&&S)render(S)}
function applyPrefs(){delete PREF.skin;if(!STYLES.some(x=>x.id===PREF.style))PREF.style=DEF.style;const b=document.body,r=document.documentElement;r.dataset.style=PREF.style;r.dataset.density=PREF.density;r.dataset.color=PREF.color;r.style.setProperty("--text-scale",String(Number(PREF.scale)/100));b.classList.toggle("density-compact",PREF.density==="compact");b.classList.toggle("activity-compact",PREF.activity==="compact");b.classList.toggle("high-contrast",!!PREF.contrast);b.classList.toggle("reduce-motion",PREF.motion==="reduce");b.classList.toggle("focus-mode",!!PREF.focus);for(const w of["balanced","activity","machines"])b.classList.toggle("workspace-"+w,PREF.workspace===w);for(const k of Object.keys(PREF.sections))b.classList.toggle("hide-"+k,!PREF.sections[k]);syncSettings()}
/* theme */
const modes=["auto","light","dark"];let mode="auto";try{mode=localStorage.getItem("rs-theme")||"auto"}catch(e){}
function applyTheme(){window.rsTheme(mode);$("themeTx").textContent="Theme: "+mode;$("theme").title="Theme: "+mode+" (t)";$("theme").setAttribute("aria-label","Theme: "+mode+". Activate to change.")}
function cycleTheme(){mode=modes[(modes.indexOf(mode)+1)%3];save("rs-theme",mode);applyTheme();toast("Theme: "+mode)}
$("theme").onclick=cycleTheme;applyTheme();applyPrefs();
/* state */
let quiet=false,S=null,TK={},CH={},HV=null,HLOCK=false,FLT="",MATCH_TX="",skew=0,failing=0,lastErr="",updMs=0,PAUSED=false,REFRESHING=false,NAV_I=-1,NOTE_MACHINE="",TOUR_I=0;
let QF="all",ORDER="age";try{QF=localStorage.getItem("rs-qf")||"all";ORDER=localStorage.getItem("rs-order")||"age"}catch(e){}
const URLP=new URLSearchParams(location.search);if(STYLES.some(x=>x.id===URLP.get("style"))){PREF.style=URLP.get("style");applyPrefs()}if(URLP.get("qf"))QF=URLP.get("qf");if(URLP.get("order"))ORDER=URLP.get("order");if(URLP.get("filter"))FLT=URLP.get("filter").toLowerCase();if(URLP.get("workspace")&&["balanced","activity","machines"].includes(URLP.get("workspace"))){PREF.workspace=URLP.get("workspace");applyPrefs()}
let FIRST={};try{FIRST=JSON.parse(localStorage.getItem("rs-first")||"{}")||{}}catch(e){}
let PREV_INC=null,CHANGES=[],NEW_KEYS=new Set(),HERO_MOBILE_OPEN=false,TIMELINE=[],UNSEEN=0;try{TIMELINE=JSON.parse(localStorage.getItem("rs-timeline")||"[]")}catch(e){}
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
 if(gave)return"gave";if(w.action)return w.result&&RESULT_BAD.test(w.result)?"fail":"rec";return"down"}
const KIND={gave:["Gave up · needs you","alert",0,"off"],fail:["Fix failed · retrying","x",1,"off"],down:["No auto-fix","off",2,"q"],unk:["Offline","off",2.5,"off"],rec:["Recovering","refresh",3,"rec"],plan:["Planned","pause",4,""]};
const blind=s=>(s.errors||[]).length&&!(s.machines||[]).some(m=>(m.runners||[]).length);
const match=(txt)=>!FLT||txt.toLowerCase().includes(FLT);
/* ---- alerts ---- */
function groupOf(a){if(a.runner)return AG[2];for(const g of AG)if(g.re.test(a.text))return g;return OTHER}
function alertText(a,offN){if(S&&a.text.startsWith("GitHub: ")&&(S.errors||[]).includes(a.text.slice(8)))return a.text.slice(8).split(/\.\s/)[0]+". Details under GitHub.";if(offN&&groupOf(a).id==="runners"&&!a.runner)return pl(offN,"runner")+" offline. Why and recovery status are under Activity.";return a.text.replace(/^GitHub:\s*/,"")}
function alertHref(a,s){if(a.url)return url(a.url);if(a.runner)return"#r-"+slug(a.runner);const g=groupOf(a);if(g.id==="hosts")for(const m of s.machines||[])if(a.text.indexOf(m.name)===0)return"#m-"+slug(m.name);return g.href}
/* Alerts are bundled into incidents so two symptoms of one machine problem do not inflate the verdict. */
function incidentKey(a,s){if(a.runner)return"r:"+a.runner;if(/^GitHub:/.test(a.text))return"gh";const g=groupOf(a);
 if(g.id==="runners")return"off";if(g.id==="hosts"){const m=(s.machines||[]).find(m=>a.text.indexOf(m.name)===0),n=m?m.name:"machine",t=a.text.toLowerCase();let k=/swap|memory|pressure/.test(t)?"memory":/disk/.test(t)?"disk":/\bvm\b/.test(t)?"vm":/stats missing|not reporting/.test(t)?"reporting":/sleep/.test(t)?"sleep":/service/.test(t)?"service":"other";return"host:"+n+":"+k}
 if(g.id==="queue")return/hosted/i.test(a.text)?"queue:hosted":"queue:waiting";return"t:"+a.text}
function makeIncidents(s,offN){const m=new Map(),now=Date.now();for(const k of Object.keys(SNOOZE))if(SNOOZE[k]<=now)delete SNOOZE[k];for(const a of s.alerts){const key=incidentKey(a,s),g=groupOf(a);if(SNOOZE[key]>now)continue;if(!m.has(key))m.set(key,{key,group:g,items:[],level:a.level,href:alertHref(a,s),acked:ACK.has(key)});const e=m.get(key);e.items.push(a);if(a.level==="crit")e.level="crit";if(!e.href)e.href=alertHref(a,s)}
 const out=[...m.values()];for(const e of out){const a=e.items[0],host=/^host:([^:]+):/.exec(e.key);e.text=e.items.length===1?alertText(a,offN):host&&e.key.endsWith(":memory")?host[1]+" memory pressure · "+pl(e.items.length,"signal"):alertText(a,offN)+" · "+(e.items.length-1)+" related"}
 return out.sort((a,b)=>(a.level==="crit"?0:1)-(b.level==="crit"?0:1))}
function trackIncidents(incs){const now=Date.now(),cur=new Map(incs.map(x=>[x.key,x]));NEW_KEYS=new Set();for(const x of incs)if(!FIRST[x.key])FIRST[x.key]=now;
 if(PREV_INC){for(const [k,x] of cur)if(!PREV_INC.has(k)){NEW_KEYS.add(k);const z={kind:"new",level:x.level,text:x.text,at:now};CHANGES.unshift(z);TIMELINE.unshift(z);UNSEEN++}for(const [k,x] of PREV_INC)if(!cur.has(k)&&!(SNOOZE[k]>now)){const z={kind:"recovered",level:"ok",text:x.text,at:now};CHANGES.unshift(z);TIMELINE.unshift(z);UNSEEN++}}
 for(const k of Object.keys(FIRST))if(!cur.has(k))delete FIRST[k];save("rs-first",FIRST);TIMELINE=TIMELINE.slice(0,80);save("rs-timeline",TIMELINE);PREV_INC=cur;CHANGES=CHANGES.slice(0,5);updateChangeCount()}
function changesHTML(){if(!CHANGES.length)return"";return`<button class="changes" id="changeSummary" type="button">${pl(CHANGES.length,"recent update")}<span style="float:right;color:var(--acc)">View timeline →</span></button>`}
function heroData(s){const fl=flat(s),offN=fl.filter(x=>x.r.status==="offline").length;
 const incidents=makeIncidents(s,offN);trackIncidents(incidents);
 const needs=fl.filter(x=>x.r.status==="offline"&&kindOf(x.r.why)==="gave");
 const P=new Set(),W=new Set();for(const x of incidents)(x.level==="crit"?P:W).add(x.key);
 for(const x of needs)P.add("r:"+x.r.name);for(const k of P)W.delete(k);if(offN>0)W.delete("off");
 const np=P.size,nw=W.size,nn=needs.length,oth=offN-nn,only=nn>0&&np===nn;
 const offTx=pl(oth,(nn?"other ":"")+"runner")+" offline",needTx=pl(nn,"runner")+" need"+(nn===1?"s":"")+" you";
 const down=blind(s);let tone,head,sub;
 if(down){tone="crit";head="GitHub unreachable";sub="Runner and job status unknown. Machine stats below are still live."}
 else if(np){tone="crit";head=only?needTx:pl(np,"problem");sub=[nn&&!only?needTx:"",oth>0?offTx:"",nw?pl(nw,"warning"):""].filter(Boolean).join(" · ")||(only?"Auto-recovery gave up":"Nothing else wrong")}
 else if(nw||oth>0){tone="warn";head=nw?pl(nw,"warning"):offTx;sub=nw?(oth>0?offTx+" too":"Nothing broken, a few things to watch"):"Nothing needs you right now"}
 else{tone="ok";head="All clear";sub="Every runner reachable, nothing stuck in the queue"}
 return{incidents,needs,offN,tone,head,sub,down,np,ok:tone==="crit"?"":okList(s,offN)}}
function okList(s,offN){const n=flat(s).length,q=s.jobs.filter(j=>j.status!=="in_progress"),old=q.length?Math.max(...q.map(j=>j.age_min||0)):0,ms=s.machines.filter(m=>isO(m.stats)&&!m.stats.error).length,r=s.rate,L=[];
 if(n&&!offN)L.push(`All ${pl(n,"runner")} reachable`);
 if(s.loading)L.push("Checking the queue");else if(!q.length)L.push("Nothing waiting for a runner");else if(old<20)L.push(pl(q.length,"job")+" waiting, oldest "+dur(old));
 if(s.machines.length&&ms===s.machines.length)L.push(`All ${pl(s.machines.length,"machine")} reporting`);
 if(!s.errors.length)L.push("GitHub is reachable"+(r&&num(r.limit)&&num(r.remaining)!=null?`, ${pct(r.remaining/r.limit)} of API calls left`:""));
 return L.length<2?"":`<ul class="okl" data-k="o" aria-label="What is fine">${L.map(t=>`<li>${ic("check")}${esc(t)}</li>`).join("")}</ul>`}
function alertGroups(h,s){const rest=h.incidents.slice(1),gs=new Map();
 for(const x of rest){const g=x.group;if(!gs.has(g.id))gs.set(g.id,{g,items:[],crit:false});const e=gs.get(g.id);e.items.push(x);if(x.level==="crit")e.crit=true}
 const list=[...gs.values()].sort((a,b)=>b.crit-a.crit);
 const row=a=>{const href=alertHref(a,s),inner=`<span class="lv ${a.level}">${ic(a.level==="crit"?"x":"alert")}</span><span class="sr">${a.level==="crit"?"Critical":"Warning"}: </span><span class="tx">${esc(alertText(a,h.offN))}</span>${href?`<span class="go">${ic("chev")}</span>`:""}`;return`<li>${href?`<a class="al" href="${esc(href)}">${inner}</a>`:`<div class="al">${inner}</div>`}</li>`};
 const inc=x=>x.items.length===1?row(x.items[0]):`<li><details class="inc"><summary class="al"><span class="lv ${x.level}">${ic(x.level==="crit"?"x":"alert")}</span><span class="tx">${esc(x.text)}</span><span class="signals">${pl(x.items.length,"signal")}</span>${ic("chev","chev")}</summary><ul>${x.items.map(row).join("")}</ul></details></li>`;
 const det=e=>{const id="ag-"+e.g.id,lv=e.crit?"crit":"warn";return`<details class="ag ${lv}" id="${id}" data-k="${id}"${op(id,0)}><summary>${ic("chev","chev")}<span class="lv">${ic(e.crit?"x":"alert")}</span><span class="nm">${esc(e.g.name)}</span><span class="pv">${esc(e.items[0].text)}</span><span class="n">${e.items.length}</span></summary><ul>${e.items.map(inc).join("")}</ul></details>`};
 const vis=list.slice(0,3),more=list.slice(3);
 const body=vis.map(det).join("")+(more.length?`<details class="more" id="ag-more" data-k="ag-more"${op("ag-more",0)}><summary>${ic("chev","chev")}${pl(more.length,"more area")}</summary><div class="ags">${more.map(det).join("")}</div></details>`:"");
 return body?`<details class="hero-all" data-k="hero-all"><summary>${ic("chev","chev")}Review ${pl(rest.length,"other incident")}</summary><div class="ags" role="region" aria-label="Warnings">${body}</div></details>`:""}
function heroHTML(s,h){const icon=h.tone==="ok"?"check":h.tone==="crit"?"x":"alert";
 const first=h.incidents[0];let left=`<div class="vrow" data-k="v"><div class="vicon">${ic(icon)}</div><div><h1 class="verdict">${esc(h.head)}</h1><p class="vsub">${esc(s.org||"")} · ${esc(h.sub)}</p></div></div>`;
 if(first){const href=first.href,t=esc(first.text),seen=FIRST[first.key]||Date.now(),nw=NEW_KEYS.has(first.key)?'<span class="new">New</span>':"";left+=`<div class="top1" data-k="t">${href?`<a href="${esc(href)}">${t}</a>`:t}<span class="since">${nw}First seen ${ago((Date.now()-seen)/1000)}${href?" · View details →":""}</span><details class="incident-menu" data-k="incident-actions"><summary>${first.acked?"✓ Acknowledged · Actions":"Actions"}</summary><div class="incident-actions">${first.acked?'':`<button class="smallctl" type="button" data-ack="${esc(first.key)}">Acknowledge</button>`}<button class="smallctl" type="button" data-snooze="${esc(first.key)}">Snooze 30 min</button><button class="smallctl" type="button" data-copy-incident="${esc(first.text)}">Copy incident</button></div></details></div>`}
 if(h.needs.length)left+=`<div class="must" role="note" data-k="m"><span class="k">${ic("alert")}Auto-recovery gave up · only you can fix ${h.needs.length>1?"these":"this"}</span><ul>${h.needs.map(x=>`<li><a href="#r-${slug(x.r.name)}">${esc(x.r.name)}<span>${locOf(x)} · ${esc((CAUSE[x.r.why.cause]||[x.r.why.cause])[0])}</span></a></li>`).join("")}</ul></div>`;
 const ags=alertGroups(h,s);return`<div data-k="l">${left}</div>`+(ags||h.ok)}
/* ---- tiles ---- */
function mini(arr,max,cls){if(!arr||arr.length<2)return"";return`<svg class="mini" viewBox="0 0 200 22" preserveAspectRatio="none" aria-hidden="true">${plot([{v:arr,cls:cls||""}],0,max,22,true)}</svg>`}
function tilesHTML(s,h,secondary=false){const c=s.counts||{},ld=s.loading,fl=flat(s);let idle=0,busy=0,off=0;for(const x of fl){const st=x.r.status;st==="busy"?busy++:st==="idle"?idle++:off++}
 const jobs=s.jobs||[],q=jobs.filter(j=>j.status!=="in_progress"),oldest=q.length?Math.max(...q.map(j=>j.age_min||0)):0,total=idle+busy+off,none=blind(s);
 const T=(href,key,cls,lab,n,d,viz)=>["health","a","b"].includes(key)!==secondary?"":`<a class="tile ${cls}" href="${href}" data-nav data-k="${key}"><span class="k">${lab}</span><span class="n">${n}</span><span class="d">${d}</span>${viz?`<span class="viz">${viz}</span>`:""}</a>`;
 const hj=s.history.jobs;let out="";
 out+=T("#sec-work","r","t-acc","In progress",ld?"…":none?"?":c.running??0,ld?"Fetching jobs":none?"Unknown":"jobs in progress",hj?mini(hj.running,Math.max(1,...hj.running,...hj.queued.map((q,i)=>q+hj.running[i])),""):"");
 out+=T("#sec-wait","q",q.length&&oldest>=PREF.sla?"t-warn":"","Queued",ld?"…":none?"?":c.queued??0,ld?"Fetching jobs":none?"Unknown":q.length?"oldest waiting "+dur(oldest):"nothing waiting",hj?mini(hj.queued,Math.max(1,...hj.queued),"w"):"");
 const seg=total?`<div class="seg" role="img" aria-label="${busy} busy, ${idle} idle, ${off} offline"><i style="flex:${busy};background:var(--accfill)"></i><i style="flex:${idle};background:var(--okfill)"></i><i style="flex:${off};background:var(--critfill)"></i></div>`:"";
 out+=T("#sec-off","u",off?"t-crit":"","Runners",none?"?":`${total-off}<small> of ${total} up</small>`,none?"Unknown":`${busy} busy · ${idle} idle · ${off} offline`,seg);
 const crit=h.incidents.filter(x=>x.level==="crit").length,warn=h.incidents.length-crit,score=Math.max(0,Math.round(100-crit*18-warn*7-(total?off/total*20:0)));out+=T("#hero","health",score<70?"t-crit":score<90?"t-warn":"","Health score",score+"<small> / 100</small>",crit?pl(crit,"critical incident"):warn?pl(warn,"warning"):"No active incidents",`<div class="bar ${score<70?"crit":score<90?"warn":"ok"}" role="img" aria-label="Health score ${score} of 100"><i style="width:${score}%"></i></div>`);
 const r=s.rate;if(r&&num(r.limit)&&num(r.remaining)!=null){const left=r.remaining/r.limit,lv=left<.1?"crit":left<.2?"warn":"ok";
  out+=T("#github","a",lv==="ok"?"":"t-"+lv,"API calls left",r.remaining.toLocaleString()+"<small> / "+r.limit.toLocaleString()+"</small>",(lv==="ok"?"":(lv==="crit"?ic("x")+" Very low · ":ic("alert")+" Low · "))+(num(r.reset)?"resets "+clock(new Date(r.reset*1000)):""),`<div class="bar ${lv}" role="img" aria-label="${pct(left)} left"><i style="width:${(left*100).toFixed(1)}%"></i></div>`)}
 const b=s.billing;if(b&&num(b.included_minutes)&&num(b.total_minutes_used)!=null){const p=b.total_minutes_used/b.included_minutes,lv=lvlOf(p,.8,.95);
  out+=T("#github","b",lv?"t-"+lv:"","Build minutes used",b.total_minutes_used.toLocaleString()+"<small> / "+b.included_minutes.toLocaleString()+"</small>",(lv==="crit"?ic("x")+" ":lv==="warn"?ic("alert")+" ":"")+pct(p)+" used this month",`<div class="bar ${lv||"ok"}" role="img" aria-label="${pct(p)} used"><i style="width:${Math.min(100,p*100).toFixed(1)}%"></i></div>`)}
 return out}
/* ---- charts ---- */
function plot(series,lo,hi,H,step){const n=series[0].v.length,X=i=>(i*200/(n-1)).toFixed(1),Y=v=>(H-1-Math.max(0,Math.min(1,(v-lo)/(hi-lo)))*(H-2)).toFixed(1);let out="";
 for(const s of series){let d="";s.v.forEach((v,i)=>{d+=i?(step?`H${X(i)}V${Y(v)}`:`L${X(i)} ${Y(v)}`):`M0 ${Y(v)}`});if(step)d+="H200";
  out+=`<path class="ar ${s.cls||""}" d="${d}L200 ${H}L0 ${H}Z"/><path class="ln ${s.cls||""}" d="${d}"/>`}
 return out}
function chart(key,grp,title,series,lo,hi,mxl,mnl,def,fmt,t,big,aria,step){const H=40;CH[key]={t,n:series[0].v.length,fmt,def,aria};
 const ref=hi<=1.0001&&title==="CPU"?`<line class="refl" x1="0" x2="200" y1="1" y2="1"/>`:"";
 return`<div class="chw"><div class="chh"><b>${esc(title)}</b><span class="ro" data-js data-c="${key}" aria-live="polite"></span></div><div class="ch${big?" big":""}" tabindex="0" role="img" aria-label="${esc(aria)}. Tap to lock a point; use left and right arrow keys." data-c="${key}" data-g="${grp}"><svg viewBox="0 0 200 ${H}" preserveAspectRatio="none" aria-hidden="true">${plot(series,lo,hi,H,step)}${ref}<line class="xh" data-js x1="-9" x2="-9" y1="0" y2="${H}"/></svg><span class="mx">${mxl}</span><span class="mn">${mnl}</span></div><div class="ax"><span>-${PREF.chart}m</span><span>now</span></div></div>`}
function hostCharts(m,h){if(!isO(h)||!Array.isArray(h.t)||h.t.length<2)return"";const all=h.t.length,start=Math.max(0,all-(PREF.chart+1)),t=h.t.slice(start),g="h-"+slug(m.name),n=t.length,cpu=arr(h.cpu).length===all?h.cpu.slice(start):[],mem=arr(h.mem).length===all?h.mem.slice(start):[];let out="";
 const tm=i=>clock(new Date(t[i]*1000));
 if(cpu.length>1){const pk=Math.max(1,...cpu),now=cpu[cpu.length-1];out+=chart(g+"-cpu",g,"CPU",[{v:cpu}],0,pk,pct(pk),"0%",`${pct(now)} now · peak ${pct(Math.max(...cpu))}`,i=>`${pct(cpu[i])} · ${tm(i)}`,t,0,`CPU load last ${PREF.chart} minutes, now ${pct(now)}, peak ${pct(Math.max(...cpu))} of cores`)}
 if(mem.length>1){let lo=Math.min(...mem)-.05,hi=Math.max(...mem)+.05;if(hi-lo<.2){const mid=(hi+lo)/2;lo=mid-.1;hi=mid+.1}lo=Math.max(0,lo);hi=Math.min(1,Math.max(hi,lo+.2));const now=mem[mem.length-1];
  out+=chart(g+"-mem",g,"RAM",[{v:mem}],lo,hi,pct(hi),pct(lo),`${pct(now)} now`,i=>`${pct(mem[i])} · ${tm(i)}`,t,0,`RAM used last ${PREF.chart} minutes, now ${pct(now)}, range ${pct(Math.min(...mem))} to ${pct(Math.max(...mem))}`)}
 return out?`<div class="chr">${out}</div>`:""}
function histHTML(s){const h=s.history.jobs;if(!h)return"";const start=Math.max(0,h.t.length-(PREF.chart+1)),t=h.t.slice(start),r=h.running.slice(start),q=h.queued.slice(start),tot=r.map((v,i)=>v+(q[i]||0)),pk=Math.max(1,...tot),n=r.length;
 const tm=i=>clock(new Date(t[i]*1000)),f=i=>`${r[i]} in progress · ${q[i]||0} queued · ${tm(i)}`;
 const c=chart("q","q","",[{v:tot,cls:"w"},{v:r}],0,pk,pk,"0",`now ${r[n-1]} in progress · ${q[n-1]||0} queued · peak ${Math.max(...tot)}`,f,t,1,`Jobs last ${PREF.chart} minutes: now ${r[n-1]} in progress and ${q[n-1]||0} queued, peak ${Math.max(...tot)} total`,true);
 return`<section class="card" data-k="hist"><div class="mh"><h3>Jobs, last ${PREF.chart} minutes</h3><span class="r"><span><i class="dot busy"></i>in progress</span><span><i class="dot warn"></i>queued</span></span></div><div style="padding:6px 16px 14px">${c}</div></section>`}
function readout(c,i){const e=document.querySelector(`.ro[data-c="${c}"]`),v=CH[c].fmt(i);if(e)e.textContent=v;const ch=document.querySelector(`.ch[data-c="${c}"]`);if(ch)ch.setAttribute("aria-label",CH[c].aria+", selected "+v)}
function setXH(g,f){for(const el of document.querySelectorAll(`.ch[data-g="${g}"]`)){const c=CH[el.dataset.c];if(!c)continue;const i=Math.round(f*(c.n-1)),x=(i*200/(c.n-1)).toFixed(1),l=el.querySelector(".xh");l.setAttribute("x1",x);l.setAttribute("x2",x);readout(el.dataset.c,i)}}
function clearXH(g){for(const el of document.querySelectorAll(g?`.ch[data-g="${g}"]`:".ch")){const l=el.querySelector(".xh");l.setAttribute("x1",-9);l.setAttribute("x2",-9)}refreshRo()}
function refreshRo(){for(const k in CH){const e=document.querySelector(`.ro[data-c="${k}"]`);if(e)e.textContent=CH[k].def}}
function applyHV(){refreshRo();if(HV&&document.querySelector(`.ch[data-g="${HV.g}"]`))setXH(HV.g,HV.f);else HV=null}
function hoverAt(e){const c=e.target.closest&&e.target.closest(".ch");if(!c){if(HV&&e.type==="pointerdown"){const g=HV.g;HV=null;HLOCK=false;clearXH(g)}return}if(e.type==="pointermove"&&HLOCK&&e.pointerType!=="mouse")return;
 const r=c.getBoundingClientRect(),f=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));if(HV&&HV.g!==c.dataset.g)clearXH(HV.g);HV={g:c.dataset.g,f};setXH(HV.g,f)}
document.addEventListener("pointermove",hoverAt);document.addEventListener("pointerdown",e=>{const c=e.target.closest&&e.target.closest(".ch");if(c)HLOCK=true;hoverAt(e)});
document.addEventListener("keydown",e=>{const c=e.target.closest&&e.target.closest(".ch");if(!c||(e.key!=="ArrowLeft"&&e.key!=="ArrowRight"))return;e.preventDefault();const n=CH[c.dataset.c].n;let f=HV&&HV.g===c.dataset.g?HV.f:1;f=Math.max(0,Math.min(1,f+(e.key==="ArrowRight"?1:-1)/(n-1)));HV={g:c.dataset.g,f};setXH(HV.g,f)});
/* ---- bars ---- */
function meter(label,val,frac,warnAt,critAt,lv,extra,tip){frac=Math.max(0,Math.min(1,frac));const cue=lv==="crit"?"Critical":lv==="warn"?"High":"",nm=label.replace(/<[^>]+>/g,""),help=tip||`Warn at ${pct(warnAt)} · critical at ${pct(critAt)}`;
 return`<div class="mt"><div class="l"><b>${label}</b><span class="v">${val}${cue?`<em class="${lv}">${ic(lv==="crit"?"x":"alert")} ${cue}</em>`:""}</span></div><div class="bar ${lv||"ok"}" tabindex="0" role="img" data-tip="${esc(help)}" aria-label="${esc(nm)} ${Math.round(frac*100)} percent full${cue?", "+cue.toLowerCase():""}. ${esc(help)}"><i style="width:${(frac*100).toFixed(1)}%"></i>${extra||""}<s style="left:${warnAt*100}%"></s><s class="c" style="left:${critAt*100}%"></s></div></div>`}
function hostHTML(m,s){const st=m.stats,h=s.history.machines[m.name],c=m.counts,id="m-"+slug(m.name);let body="";
 const issue=!!(c.offline||(st&&st.error)||(s.alerts||[]).some(a=>a.text.indexOf(m.name)===0)),at=st&&num(st._updated)?st._updated*1000:updMs,age=Math.max(0,(Date.now()-skew-at)/1000),fresh=at?ago(age):"no report yet";
 const head=`<summary class="mh"><span class="chev">${ic("chev")}</span><h3>${PINS.has(m.name)?'<span aria-label="Pinned" style="color:var(--warnfill)">'+ic('pin')+' </span>':""}${esc(m.name)}</h3><span class="machine-health ${issue?"issue":"ok"}">${issue?"Needs attention":"Healthy"}</span><span class="fresh-machine${age>180?" stale":""}">updated ${fresh}</span><span class="r">${c.busy?`<span><i class="dot busy"></i>${c.busy} busy</span>`:""}${c.idle?`<span><i class="dot ok"></i>${c.idle} idle</span>`:""}${c.offline?`<span style="color:var(--crit)"><i class="dot crit"></i>${c.offline} offline</span>`:""}</span><button class="machine-more" type="button" data-machine-menu="${esc(m.name)}" aria-label="Actions for ${esc(m.name)}" aria-haspopup="dialog">${ic("more")}</button></summary>`;
 if(!st)body=`<div class="note mut">${ic("plug")}<span>${m.configured_agent?"Waiting for the first report from this machine.":"This machine does not report stats."}</span></div>`;
 else if(st.error)body=`<div class="note warn">${ic("alert")}<span><b>No stats from this machine.</b> ${esc(st.error)}. Bars and charts come back when it reports again.</span></div>`;
 else{let ms="",facts="";const mem=st.memory,sw=st.swap||{},pressure=st.pressure===4?["Critical pressure","crit"]:st.pressure===2?["High pressure","warn"]:["Pressure normal",""];
  if(mem&&mem.total){const u=mem.used/mem.total,cp=(mem.compressed||0)/mem.total;
   ms+=meter("Memory",`${bytes(mem.used)} of ${bytes(mem.total)}${cp>.005?` · ${bytes(mem.compressed)} compressed`:""}`,u,.8,.92,lvlOf(u,.8,.92),cp>.005?`<i class="hat" style="left:${((u-cp)*100).toFixed(1)}%;width:${(cp*100).toFixed(1)}%"></i>`:"","Warn at 80% · critical at 92%. The lighter segment is compressed memory included in used memory.").replace(/<i style="width:([\d.]+)%"><\/i>/,(_,w)=>`<i style="width:${cp>.005?((u-cp)*100).toFixed(1):w}%"></i>`)}
  if(num(sw.used)!=null)facts+=`<span class="${(sw.used||0)>=4*1024**3?"warn":""}">Swap ${bytes(sw.used)}${num(sw.total)?" of "+bytes(sw.total):""}</span>`;if(st.pressure!=null)facts+=`<span class="${pressure[1]}">${pressure[0]}</span>`;
  if(st.load&&num(st.load[0])!=null&&num(st.cores)){const r=st.load[0]/st.cores;ms+=meter("Load average",`1 min: ${st.load[0].toFixed(1)} · ${st.cores} cores`,r/1.25,.85/1.25,1/1.25,lvlOf(r,.85,1),"","Load average divided by cores · warn at 0.85 per core · critical at 1.0 per core")}
  for(const d of st.disks){if(!num(d.total)||num(d.used)==null)continue;const u=d.used/d.total,f=(num(d.free)??d.total-d.used)/d.total;ms+=meter(`Disk <span class="mono" style="font-weight:500;color:var(--muted)">${esc(d.path)}</span>`,`${bytes(num(d.free)??d.total-d.used)} free of ${bytes(d.total)}`,u,.9,.95,f<.05?"crit":f<.1?"warn":"","","Warn below 10% free · critical below 5% free")}
  const charts=hostCharts(m,h);body=(NOTES[m.name]?`<div class="note mut"><span><b>Local note:</b> ${esc(NOTES[m.name])}</span></div>`:"")+(facts?`<div class="memory-facts">${facts}</div>`:"")+`<div class="meters">${ms}</div>`+(charts?`<div class="chart-help">Charts show the last ${PREF.chart} minutes. Tap to lock a value; use <kbd>←</kbd><kbd>→</kbd> when focused.</div>${charts}`:"");
  const st2={};for(const r of m.runners||[])st2[r.name]=r.status;const inVm=new Set(),cnt=ns=>{let b=0,i=0,o=0;for(const n of ns){const x=st2[n];x==="busy"?b++:x==="idle"?i++:x==="offline"&&o++}return[b?b+" busy":"",i?i+" idle":"",o?`<span style="color:var(--crit)">✕ ${o} offline</span>`:""].filter(Boolean).join(" · ")};
  let vm="";for(const v of st.vms||[]){(v.runners||[]).forEach(n=>inVm.add(n));const run=v.status==="Running";
   vm+=`<a class="vm${run?"":" stop"}" href="#activity" data-filter="${esc(v.name)}"><i class="dot ${run?(( v.jobs||[]).length?"busy":"ok"):"warn"}"></i><b>${esc(v.name)}</b><span class="s">${esc(v.cpus)} CPU · ${bytes(v.memory)}</span><span class="w">${run?(cnt(v.runners||[])||"no runners"):ic("alert")+" "+esc(v.status)+((v.runners||[]).length?" · "+pl(v.runners.length,"runner")+" down":"")}</span></a>`}
  const hostOnly=(m.runners||[]).filter(r=>!inVm.has(r.name)).map(r=>r.name);if(hostOnly.length)vm+=`<a class="vm" href="#activity" data-filter="${esc(m.name)}"><i class="dot ok"></i><b>Not in a VM</b><span class="w">${cnt(hostOnly)}</span></a>`;
  body+=vm?`<div class="vms">${vm}</div>`:`<div style="height:12px"></div>`}
 return`<details class="card machine" id="${id}" data-nav tabindex="-1" data-k="${id}" data-health="${issue?"issue":"ok"}"${op(id,1)}>${head}<div class="machine-body">${body}</div></details>`}
function githubHTML(s){const r=s.rate,errs=(s.errors||[]).map(e=>`<div class="note crit" style="margin:0">${ic("x")}<span>${esc(e)}</span></div>`).join("");const k=[];
 if(r&&r.used_by_page_last_hour!=null)k.push(`<span><b>${esc(r.used_by_page_last_hour)}</b> calls to GitHub by this page in the last hour${r.free_304s!=null?`, plus ${esc(r.free_304s)} answered from cache at no cost`:""}.</span>`);
 if(r&&num(r.reset))k.push(`<span>API calls reset at <b>${clock(new Date(r.reset*1000))}</b>.</span>`);
 if(s.token)k.push(`<span>Reading GitHub with ${esc(s.token)}.</span>`);
 const brief=r&&num(r.reset)?`API quota resets ${clock(new Date(r.reset*1000))}.`:"API usage is not available yet.";
 return`<section class="card" data-k="gh"><div style="padding:12px 16px 4px;display:grid;gap:8px">${errs||`<div class="note ok" style="margin:0">${ic("check")}<span>GitHub is reachable.</span></div>`}</div><div class="gh-brief">${esc(brief)}</div><details class="diag"><summary>${ic("chev","chev")}Diagnostics</summary><div class="gk">${k.join("")||'<span>No usage data yet.</span>'}</div></details></section>`}
/* ---- activity ---- */
const prs=j=>gitRefsHTML(j);
const timeCls=(m,w,c)=>m==null?"":m>=c?" vlong":m>=w?" long":"";
const jobName=j=>{const w=String(j.workflow||"").trim(),n=String(j.name||"").trim();return w.toLowerCase()===n.toLowerCase()?esc(w||n):esc(w)+(n?` <span class="sub">/ ${esc(n)}</span>`:"")};
function qok(kind,x){if(QF==="all")return true;if(QF==="running")return kind==="work";if(QF==="queued")return kind==="wait";if(QF==="offline")return kind==="off";if(QF==="idle")return kind==="idle";if(QF==="attention")return(kind==="off"&&kindOf(x.r.why)!=="plan")||(kind==="wait"&&(x.age_min||0)>=PREF.sla)||(kind==="work"&&(((x.r.job||{}).age_min||0)>=240||arr((x.r.job||{}).closed_prs).length));return true}
function itemKey(x,kind){if(ORDER==="repo")return kind==="wait"?x.repo:(x.r.job||{}).repo||"No active repository";if(ORDER==="machine")return kind==="wait"?(x.hosted?"GitHub-hosted":"Self-hosted"):x.m.name;return""}
function ordered(items,kind){return [...items].sort((a,b)=>{if(ORDER==="repo"||ORDER==="machine")return itemKey(a,kind).localeCompare(itemKey(b,kind));if(ORDER==="severity"&&kind==="off")return KIND[kindOf(a.r.why)][2]-KIND[kindOf(b.r.why)][2];const aa=kind==="wait"?a.age_min:(a.r.job||{}).age_min,bb=kind==="wait"?b.age_min:(b.r.job||{}).age_min;return(bb||0)-(aa||0)})}
function rows(items,kind,fn){const all=ordered(items,kind),a=kind==="wait"?all.slice(0,ACT_LIMIT):all,more=kind==="wait"&&all.length>12?`<li class="page-more"><span>Showing ${a.length} of ${all.length}</span>${a.length<all.length?'<button class="btn" type="button" id="queue-more">Show 12 more</button>':'<button class="text-btn" type="button" id="queue-less">Show fewer</button>'}</li>`:"";if(ORDER!=="repo"&&ORDER!=="machine")return a.map(fn).join("")+more;let last="",out="";a.forEach((x,i)=>{const k=itemKey(x,kind)||"Other";if(k!==last){out+=`<li class="group-label">${esc(k)}</li>`;last=k}out+=fn(x,i)});return out+more}
function offRow(x){const r=x.r,w=r.why,k=kindOf(w),[lab,icn,,icc]=KIND[k],cz=w&&CAUSE[w.cause]||["",""];
 let b=`<div class="ln1"><span class="st ${k}">${ic(icn)}${lab}</span><b class="mono" style="font-size:13px">${esc(r.name)}</b></div><div class="meta" style="margin-top:2px">${locOf(x)}${cz[0]?" · "+esc(cz[0]):""}</div>`;
 if(!w){const vmo=x.vm&&arr(x.m.stats&&x.m.stats.vms).find(v=>v.name===x.vm),hint=vmo&&vmo.status!=="Running"?` Its VM ${esc(x.vm)} is ${esc(String(vmo.status).toLowerCase())}.`:x.m.stats&&x.m.stats.error?" This machine is not reporting stats either.":"";b+=`<div class="why">Offline, no cause reported yet.${hint}</div>`}
 else{b+=`<div class="why">${esc(w.detail)}</div>`;
  if(w.action)b+=`<div class="last">${w.at?esc(w.at)+" · ":""}auto-recovery ran <code>${esc(w.action)}</code> → <span class="${k==="rec"?"good":"bad"}">${esc(w.result||"no result yet")}</span>${w.tries?` · ${pl(w.tries,"try","tries")} this hour`:""}</div>`;
  else if(k==="down")b+=`<div class="last">No automatic fix. ${esc(cz[1])}.</div>`;
  if(k==="gave")b+=`<div class="todo">${ic("alert")}<span><b>Needs you.</b> The watchdog stopped retrying. ${esc(cz[1])}; it stays offline until then.</span></div>`}
 return`<li class="row k-${k}" id="r-${slug(r.name)}" data-nav tabindex="-1" data-k="o-${esc(r.name)}"><span class="ic ${icc}">${ic(icn==="refresh"?"clock":icn)}</span><div class="m">${b}</div></li>`}
function workRow(x,ld){const r=x.r,j=r.job;TK["w-"+r.name]=j&&j.age_min!=null?j.age_min*60:null;
 const head=j?`<div class="jt"><a href="${esc(url(j.url))}">${jobName(j)}</a></div><div class="meta">${repoHTML(j)}${prs(j)}<span class="runner-tag">${esc(r.name)}</span><span>${locOf(x)}</span></div>`
  :`<div class="jt">${ld?'<span class="shimmer"></span>':"<span class=\"sub\">Job not in the latest sweep</span>"}</div><div class="meta"><span class="runner-tag">${esc(r.name)}</span><span>${locOf(x)}</span></div>`;
 return`<li class="row" data-nav tabindex="-1" data-k="w-${esc(r.name)}"><span class="ic busy">${ic("play")}</span><div class="m">${head}</div><div class="tmw${j?timeCls(j.age_min,60,180):""}"><b class="tm" data-js data-tk="w-${esc(r.name)}">${j?"":"…"}</b><small>In progress</small>${j?inspectButton(j):""}</div></li>`}
function waitRow(j,i){const key="q-"+i+"-"+j.repo+"-"+j.name;TK[key]=j.age_min!=null?j.age_min*60:null;const age=j.age_min||0,sl=age>=PREF.sla*3?"crit":age>=PREF.sla?"warn":"ok",sla=sl==="crit"?"SLA breached":sl==="warn"?"SLA at risk":"Within SLA";
 return`<li class="row" data-nav tabindex="-1" data-k="${esc(key)}"><span class="ic ${age>=PREF.sla?"q":""}">${ic(j.hosted?"cloud":"clock")}</span><div class="m"><div class="jt"><a href="${esc(url(j.url))}">${jobName(j)}</a></div><div class="meta">${repoHTML(j)}${prs(j)}${j.hosted?'<span class="tag">GitHub-hosted</span>':""}${j.status!=="queued"?`<span class="tag">${esc(jobStatusLabel(j.status))}</span>`:""}${age>=PREF.sla?`<span class="sla ${sl}">Past ${PREF.sla}m target</span>`:""}</div></div><div class="tmw${timeCls(age,PREF.sla,PREF.sla*3)}"><b class="tm" data-js data-tk="${esc(key)}"></b><small>Queued</small>${inspectButton(j)}</div></li>`}
const GH=(id,icn,t,n,hint)=>`<div class="gh" id="${id}" data-k="${id}"><h3>${ic(icn)}${t}</h3><span class="c">${n}</span>${hint?`<span class="hint">${hint}</span>`:""}</div>`;
function actHTML(s){const fl=flat(s),ld=s.loading;TK={};let h="";
 const hit=x=>smartMatch(searchFields(x.r.job||{},x,x.r.status==="busy"?"running":x.r.status));
 if(blind(s))return`<div class="card"><div class="note crit" style="margin-top:14px">${ic("x")}<span><b>Unknown until GitHub can be read.</b> Fix the GitHub problem below; this fills in on the next refresh. Machine stats keep updating.</span></div></div>`;
 const off=fl.filter(x=>x.r.status==="offline"&&hit(x)&&qok("off",x));
 const work=fl.filter(x=>x.r.status==="busy"&&hit(x)&&qok("work",x));
 const wait=(s.jobs||[]).filter(j=>j.status!=="in_progress"&&smartMatch(searchFields(j,null,"queued"))&&qok("wait",j));
 const idle=fl.filter(x=>x.r.status==="idle"&&hit(x)&&qok("idle",x));
 const nothing=!FLT&&QF==="all"&&!ld&&!(s.jobs||[]).length&&!fl.some(x=>x.r.status==="busy"),filtered=!!FLT||QF!=="all";MATCH_TX=filtered?pl(off.length+work.length+wait.length+idle.length,"result"):"";
 if(off.length)h+=GH("sec-off","off","Offline",off.length,ORDER==="severity"?"most urgent first":ORDER.startsWith("age")?"most urgent first":"grouped")+`<ul class="ul">${rows(off,"off",offRow)}</ul>`;
 if(nothing)h+=GH("sec-work","pause","In progress",0,"")+`<p class="calm" id="sec-wait">${ic("check")}No jobs in progress or queued. ${pl(fl.filter(x=>x.r.status==="idle").length,"runner")} ready for the next push.</p>`;
 else{if(QF==="all"||QF==="running"||QF==="attention")h+=GH("sec-work","play","In progress",work.length,ORDER==="age"?"longest first":ORDER.startsWith("severity")?"longest first":"grouped")+(work.length?`<ul class="ul">${rows(work,"work",x=>workRow(x,ld))}</ul>`:`<p class="empty">${filtered?"No jobs in progress match.":"No jobs in progress."}</p>`);
  if(QF==="all"||QF==="queued"||QF==="attention")h+=GH("sec-wait","clock","Queued",ld?"…":wait.length,ORDER==="age"?"oldest first":"grouped")+(ld?`<p class="empty"><span class="shimmer"></span><br>Checking every repo for queued jobs. Runners and machines are already live.</p>`:wait.length?`<ul class="ul">${rows(wait,"wait",waitRow)}</ul>`:`<p class="empty">${filtered?"No queued jobs match.":"No queued jobs."}</p>`)}
 if(idle.length){const g=new Map();for(const x of idle){const k=locOf(x);if(!g.has(k))g.set(k,[]);g.get(k).push(x.r.name)}
  h+=`<details class="sec" id="sec-idle" data-k="sec-idle"${QF==="idle"?' open':op("sec-idle",0)}><summary><h3>${ic("pause")}Idle</h3><span class="c" style="color:var(--muted)">${idle.length}</span><span class="r"><span class="sw"></span>${ic("chev","chev")}</span></summary><div class="ig">${[...g].map(([k,ns])=>`<div class="igg"><span class="igl">${k}</span><div class="chips">${ns.map(n=>`<button class="chip" type="button" data-filter="${esc(n)}"><i class="dot ok"></i>${esc(n)}</button>`).join("")}</div></div>`).join("")}</div></details>`}
 if(wait.length&&!filtered)h+=`<div class="recommend"><button class="text-btn" type="button" data-explore="overview">Understand this queue →</button></div>`;
 if(filtered&&!off.length&&!work.length&&!wait.length&&!idle.length)h=`<p class="empty" style="padding-top:14px">Nothing matches the current filters${FLT?` and “${esc(FLT)}”`:""}.</p>`;
 return`<div class="card">${h}</div>`}
/* ---- render ---- */
/* a malformed section is dropped, never the whole page */
function safe(f){try{return f()}catch(e){console.warn("section skipped:",e&&e.message);return""}}
function render(s){S=s=norm(s);CH={};const h=heroData(s);
 updMs=s.updated?new Date(s.updated).getTime():NaN;if(isNaN(updMs))updMs=Date.now()-skew;
 const hero=$("hero"),two=h.incidents.length>1||!!h.ok;hero.className="hero "+h.tone+(two?" two":"");
 mount(hero,safe(()=>heroHTML(s,h)));mount($("tiles"),safe(()=>tilesHTML(s,h)));mount($("secondaryStats"),safe(()=>tilesHTML(s,h,true)));$("tiles").dataset.n=$("tiles").children.length;fade();
 mount($("changes"),changesHTML());renderActivity();syncHeroAll();
 const machines=[...s.machines].sort((a,b)=>(PINS.has(b.name)?1:0)-(PINS.has(a.name)?1:0));mount($("hostl"),machines.map(m=>safe(()=>hostHTML(m,s))).join(""));
 mount($("ghc"),safe(()=>githubHTML(s)));mount($("hist"),safe(()=>histHTML(s)));
 const fl=flat(s),bl=blind(s),bz=fl.filter(x=>x.r.status==="busy").length;
 $("actc").textContent=bl?"status unknown":bz+" in progress · "+(s.loading?"queue loading":s.jobs.filter(j=>j.status!=="in_progress").length+" queued");
 $("hostc").textContent=pl(s.machines.length,"machine")+(bl?"":" · "+pl(fl.length,"runner"));
 document.title=(h.tone==="ok"?"":"("+h.head+") ")+"Runner Status";
 $("foot").innerHTML="<p>"+esc(s.org||"")+". Refreshes every 15 s.</p>";
 const fl2=flat(s);quiet=!s.loading&&!blind(s)&&!fl2.some(x=>x.r.status==="busy")&&!s.jobs.some(j=>j.status!=="in_progress");
 renderTimeline();updateCompareTray();if($("inspect").open)renderInspector();if($("explore").open)renderExplore();syncMachineControls();balance();tickAll();activeNav()}
function renderActivity(){if(!S)return;mount($("act"),safe(()=>actHTML(S)));$("matchc").textContent=MATCH_TX;$("flt-clear").hidden=!FLT;for(const b of document.querySelectorAll("[data-qf]")){const on=b.dataset.qf===QF;b.classList.toggle("on",on);b.setAttribute("aria-pressed",on)}$("order").value=ORDER;$("activity-view").textContent="Compact rows";$("activity-view").setAttribute("aria-pressed",String(PREF.activity==="compact"));const n=Number(QF!=="all")+Number(!!FLT)+Number(ORDER!=="age"),names={attention:"Needs attention",running:"In progress",queued:"Queued",offline:"Offline",idle:"Idle"};$("filterCount").textContent=n;$("filterCount").hidden=!n;$("filtersb").classList.toggle("has-filters",!!n);$("filterSummary").hidden=!n;$("filterSummaryTx").textContent=[names[QF],FLT?"“"+FLT+"”":"",ORDER!=="age"?$("order").selectedOptions[0]?.textContent:""].filter(Boolean).join(" · ");tickTimers()}
function syncHeroAll(){const d=document.querySelector(".hero-all");if(d)d.open=matchMedia("(min-width:641px)").matches||HERO_MOBILE_OPEN}
/* desktop: park GitHub + chart in whichever column is shorter (hysteresis avoids flip-flop) */
/* tiles: edge fade tells you the strip scrolls */
function fade(){const t=$("tiles"),m=t.scrollWidth-t.clientWidth;t.dataset.fade=(t.scrollLeft>4?"l":"")+(t.scrollLeft<m-4?"r":"")}
$("tiles").addEventListener("scroll",fade,{passive:true});
function balance(){const ex=$("extra"),A=document.querySelector(".colA"),B=document.querySelector(".colB"),two=matchMedia("(min-width:981px)").matches;
 $("cols").classList.toggle("quiet",quiet&&two);
 if(!two||quiet){if(ex.parentNode!==B)B.appendChild(ex);return}
 const cur=ex.parentNode,hA=A.offsetHeight-(cur===A?ex.offsetHeight+12:0),hB=B.offsetHeight-(cur===B?ex.offsetHeight+12:0);
 const want=hA+160<hB?A:hB+160<hA?B:cur===A?A:B;if(want!==cur)want.appendChild(ex)}
function activeNav(){const y=$("top").offsetHeight+24,links=[...document.querySelectorAll(".jump a,.bottom-nav a")];let active="activity";for(const id of["activity","hosts","github"]){const e=$(id);if(e&&e.getBoundingClientRect().top<=y)active=id}for(const a of links){const on=a.getAttribute("href")==="#"+active;a.classList.toggle("active",on);if(on)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current")}}
addEventListener("scroll",activeNav,{passive:true});addEventListener("resize",()=>{if(S)balance();fade();syncHeroAll();activeNav()});
function tickTimers(){if(PAUSED)return;const now=Date.now()-skew,base=Math.max(0,(now-updMs)/1000);for(const e of document.querySelectorAll("[data-tk]")){const a=TK[e.dataset.tk];if(a==null)continue;const t=elapsed(a+base);if(e.textContent!==t)e.textContent=t}}
function tickAll(){tickTimers();applyHV();tickFresh()}
function tickFresh(){const fr=$("fresh"),tx=$("freshTx");if(!S)return;
 const age=Math.max(0,(Date.now()-skew-updMs)/1000);let cls="",t;
 if(PAUSED){cls="stale";t="Paused · "+ago(age)}else if(failing){cls="lost";t="Connection lost"}else if(age>360){cls="stale";t="Stale · "+ago(age).replace(" ago"," old")}else t="Live · "+ago(age);
 fr.className="fresh "+cls;if(tx.textContent!==t)tx.textContent=t;$("refreshCount").textContent=PAUSED?"—":String(Math.max(0,15-Math.floor(age%15)));
 const lb=$("lost"),w=lb.firstElementChild;let m="";
 if(failing){lb.className="lostbar";m=`${ic("plug")}<span><b>Connection lost.</b> Retrying every 15 s. Showing the last data from ${updMs?clock(new Date(updMs)):"never"}${lastErr?" ("+esc(lastErr)+")":""}.</span>`}
 else if(age>600&&!PAUSED){lb.className="lostbar stalebar";m=`${ic("clock")}<span><b>This snapshot is ${ago(age).replace(" ago"," old")}.</b> The server answers but has not refreshed since ${clock(new Date(updMs))}. Treat everything as possibly out of date.</span>`}
 if(m){lb.hidden=false;if(w._h!==m){w._h=m;w.innerHTML=m}}else lb.hidden=true;
 document.documentElement.style.scrollPaddingTop=($("top").offsetHeight+8)+"px"}
async function tick(force=false){if(PAUSED&&!force)return;REFRESHING=true;$("refreshIcon").classList.add("spin");try{const r=await fetch("api/state",{cache:"no-store"});if(!r.ok)throw new Error("HTTP "+r.status);
  const d=r.headers.get("Date"),s=await r.json();if(d){const sv=new Date(d).getTime();if(!isNaN(sv))skew=Date.now()-sv}
  failing=0;lastErr="";LAST_SNAPSHOT=s;save("rs-snapshot",s);try{render(s)}catch(x){console.warn("render failed:",x&&x.message)}}
 catch(e){failing++;lastErr=e.message||"network error";
  if(!S&&LAST_SNAPSHOT){render(JSON.parse(JSON.stringify(LAST_SNAPSHOT)));toast("Offline snapshot restored")}
  else if(!S){const hero=$("hero");hero.className="hero crit";hero.innerHTML=`<div class="vrow"><div class="vicon">${ic("plug")}</div><div><h1 class="verdict">Can't reach the status server</h1><p class="vsub">Retrying every 15 s.</p></div></div>`;S=null;$("freshTx").textContent="Connection lost";$("fresh").className="fresh lost";const lb=$("lost");lb.hidden=true}
  else tickFresh()}finally{REFRESHING=false;$("refreshIcon").classList.remove("spin")}}
/* ---- preferences, commands, and local workflow tools ---- */
function settingsMarkup(){return`<label class="setting style-setting"><span>Style</span><select data-pref="style" aria-label="Style" aria-describedby="styleNote">${STYLES.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join("")}</select><small class="style-note" id="styleNote"></small></label><label class="setting"><span>Density</span><select data-pref="density"><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label><label class="setting"><span>Text size</span><select data-pref="scale"><option value="90">Small</option><option value="100">Standard</option><option value="115">Large</option></select></label><label class="setting"><span>Row layout</span><select data-pref="activity"><option value="cards">Comfortable</option><option value="compact">Compact</option></select></label><label class="setting"><span>Chart window</span><select data-pref="chart"><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">60 minutes</option></select></label><label class="setting"><span>Workspace</span><select data-pref="workspace"><option value="balanced">Balanced</option><option value="activity">Activity focus</option><option value="machines">Machines focus</option></select></label><label class="setting"><span>Storage units</span><select data-pref="units"><option value="binary">Binary · GiB</option><option value="decimal">Decimal · GB</option></select></label><label class="setting"><span>Time format</span><select data-pref="hour24"><option value="false">12 hour</option><option value="true">24 hour</option></select></label><label class="setting"><span>Color vision</span><select data-pref="color"><option value="standard">Standard</option><option value="deuteranopia">Blue/orange</option><option value="tritanopia">Magenta/amber</option></select></label><label class="setting"><span>Motion</span><select data-pref="motion"><option value="system">Follow system</option><option value="reduce">Reduce motion</option></select></label><label class="setting"><span>Queue SLA</span><select data-pref="sla"><option value="15">15 minutes</option><option value="20">20 minutes</option><option value="30">30 minutes</option><option value="60">60 minutes</option></select></label><div class="setting"><span>Accessibility and focus</span><div class="checks"><label><input type="checkbox" data-pref="contrast"> High contrast</label><label><input type="checkbox" data-pref="focus"> Focus mode</label></div></div><fieldset class="setting" style="border:0;padding:0;margin:0"><legend>Visible sections</legend><div class="checks">${Object.keys(DEF.sections).map(k=>`<label><input type="checkbox" data-section="${k}"> ${k[0].toUpperCase()+k.slice(1)}</label>`).join("")}</div></fieldset>`}
function syncSettings(){const g=$("settingsGrid");if(!g)return;if(!g.children.length)g.innerHTML=settingsMarkup();for(const e of g.querySelectorAll("[data-pref]")){const k=e.dataset.pref;if(e.type==="checkbox")e.checked=!!PREF[k];else e.value=String(PREF[k])}for(const e of g.querySelectorAll("[data-section]"))e.checked=!!PREF.sections[e.dataset.section];$("styleNote").textContent=STYLES.find(x=>x.id===PREF.style).note+" Same colors in every style.";renderSavedViews()}
function snapshotView(name){return{name,pref:JSON.parse(JSON.stringify(PREF)),qf:QF,order:ORDER,filter:FLT,at:Date.now()}}
function renderSavedViews(){const b=$("savedViews");if(!b)return;b.innerHTML=SAVED.length?SAVED.map((v,i)=>`<div class="saved-row"><b>${esc(v.name)}</b><small>Saved ${new Date(v.at||0).toLocaleDateString()}</small><button class="btn" type="button" data-load-view="${i}" aria-label="Load ${esc(v.name)}">Load</button><button class="btn saved-delete" type="button" data-delete-view="${i}" aria-label="Delete ${esc(v.name)}">${ic("close")}</button></div>`).join(""):'<p class="search-tip">No saved views yet. Save your current filters and appearance to return to them later.</p>'}
let MODAL_SOURCE=null;
function openControls(section=""){syncSettings();openSecondary("settings");$("settings").scrollTop=0;if(typeof section==="string"&&$(section)){$(section).open=true;$("settings").scrollTop=Math.max(0,$(section).offsetTop-76)}}
function openSecondary(id){if(!document.querySelector("dialog[open]"))MODAL_SOURCE=document.activeElement;for(const d of document.querySelectorAll("dialog[open]"))if(d.id!==id)d.close();if(!$(id).open)$(id).showModal()}
for(const d of document.querySelectorAll("dialog"))d.addEventListener("close",()=>{setTimeout(()=>{if(!document.querySelector("dialog[open]")){const source=MODAL_SOURCE;MODAL_SOURCE=null;if(source&&source.isConnected)source.focus({preventScroll:true});else if(source)$(matchMedia("(max-width:640px)").matches?"mobile-more":"settingsb").focus({preventScroll:true})}},0)});
function openMachineMenu(name){$("machine-menu-h").textContent=name;$("machineMenuItems").innerHTML=`<button type="button" data-pin-machine="${esc(name)}">${PINS.has(name)?"Unpin machine":"Pin machine"}</button><button type="button" data-compare-machine="${esc(name)}">${COMPARE.has(name)?"Remove from comparison":"Compare machine"}</button><button type="button" data-note-machine="${esc(name)}">${NOTES[name]?"Edit machine note":"Add machine note"}</button><button type="button" data-filter="${esc(name)}">Show this machine’s activity</button>`;openSecondary("machine-menu")}
function loadView(v){if(!v)return;PREF={...PREF,...v.pref,sections:{...DEF.sections,...(v.pref.sections||{})}};QF=v.qf||"all";ORDER=v.order||"age";FLT=v.filter||"";$("flt").value=FLT;persistPrefs();toast("View loaded: "+v.name)}
let toastTimer;function toast(msg){const t=$("toast");if(!t)return;t.textContent=msg;t.classList.add("show");clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove("show"),2400)}
async function copyText(text,msg="Copied"){try{await navigator.clipboard.writeText(text)}catch(e){const a=document.createElement("textarea");a.value=text;a.style.position="fixed";a.style.opacity="0";document.body.appendChild(a);a.select();document.execCommand("copy");a.remove()}toast(msg)}
function viewURL(){const u=new URL(location.href);u.search="";if(QF!=="all")u.searchParams.set("qf",QF);if(ORDER!=="age")u.searchParams.set("order",ORDER);if(FLT)u.searchParams.set("filter",FLT);if(PREF.workspace!=="balanced")u.searchParams.set("workspace",PREF.workspace);if(PREF.style!==DEF.style)u.searchParams.set("style",PREF.style);return u.toString()}
function statusBrief(){if(!S)return"Runner Status: no snapshot available.";const f=flat(S),busy=f.filter(x=>x.r.status==="busy").length,idle=f.filter(x=>x.r.status==="idle").length,off=f.filter(x=>x.r.status==="offline").length,q=S.jobs.filter(j=>j.status!=="in_progress"),alerts=S.alerts||[];return[`Runner Status · ${S.org||""}`,`${busy} in progress, ${q.length} queued, ${idle} idle, ${off} offline.`,alerts.length?`${alerts.length} alert${alerts.length===1?"":"s"}: ${alerts.slice(0,3).map(a=>a.text).join("; ")}`:"No active alerts.",`Updated ${S.updated?new Date(S.updated).toLocaleString():"unknown"}.`].join("\n")}
function exportJSON(){if(!S)return toast("No snapshot to export");const blob=new Blob([JSON.stringify({exported:new Date().toISOString(),state:S,view:{preferences:PREF,qf:QF,order:ORDER,filter:FLT}},null,2)],{type:"application/json"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="runner-status-"+new Date().toISOString().slice(0,19).replace(/[:T]/g,"-")+".json";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500);toast("Snapshot exported")}
function updateChangeCount(){const e=$("changeCount");if(!e)return;e.textContent=String(UNSEEN);e.classList.toggle("on",UNSEEN>0)}
function renderTimeline(){const b=$("timelineList");if(!b)return;const active=PREV_INC?[...PREV_INC.values()].map(x=>({kind:"active",level:x.level,text:x.text,at:FIRST[x.key]||Date.now()})):[],all=[...active,...TIMELINE];b.innerHTML=all.length?all.map(x=>`<li class="${x.level||"warn"}"><b>${x.kind==="recovered"?"Recovered":x.kind==="new"?"New":"Active"}</b> · ${esc(x.text)}<time>${x.kind==="active"?"First seen ":""}${new Date(x.at).toLocaleString()}</time></li>`).join(""):'<li class="ok"><b>No timeline events yet.</b><time>Changes will appear here as live data updates.</time></li>'}
function updateCompareTray(){const tray=$("compareTray"),names=[...COMPARE];tray.hidden=!names.length;$("compareTx").textContent=names.length===1?names[0]+" selected":names.length===2?names.join(" vs "):"Select two machines";$("compareOpen").disabled=names.length!==2}
function metric(m,k){const st=m&&m.stats||{},c=m&&m.counts||{};if(k==="Status")return st.error?"Not reporting":c.offline?`${c.offline} offline`:"Healthy";if(k==="Runners")return`${c.busy||0} busy · ${c.idle||0} idle · ${c.offline||0} offline`;if(k==="Memory")return st.memory&&st.memory.total?`${bytes(st.memory.used)} / ${bytes(st.memory.total)}`:"—";if(k==="Swap")return st.swap&&num(st.swap.used)!=null?bytes(st.swap.used):"—";if(k==="Load")return st.load&&num(st.load[0])!=null?`${st.load[0].toFixed(1)} / ${st.cores||"?"} cores`:"—";if(k==="Disk free")return(st.disks||[]).map(d=>`${d.path} ${bytes(d.free)}`).join(" · ")||"—";return"—"}
function openCompare(){if(!S||COMPARE.size!==2)return;const ns=[...COMPARE],ms=ns.map(n=>S.machines.find(m=>m.name===n)),ks=["Status","Runners","Memory","Swap","Load","Disk free"];$("compareGrid").innerHTML=`<table class="comparison-table"><caption class="sr">Machine metrics side by side</caption><thead><tr><th scope="col">Metric</th>${ns.map(n=>`<th scope="col">${esc(n)}</th>`).join("")}</tr></thead><tbody>${ks.map(k=>`<tr><th scope="row">${k}</th>${ms.map(m=>`<td>${esc(metric(m,k))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;openSecondary("compare")}
/* ---- on-demand investigation: no extra GitHub requests or write access ---- */
/* GitHub-native reference presentation; unknown PR state stays neutral. */
function gitRepo(j){const full=String(j.repo_full_name||((S&&S.org&&j.repo&&!String(j.repo).includes("/"))?S.org+"/"+j.repo:j.repo)||"");return /^[^/\s]+\/[^/\s]+$/.test(full)?full:null}
function repoURL(j){const full=gitRepo(j);return full?"https://github.com/"+full.split("/").map(encodeURIComponent).join("/"):null}
function repoHTML(j){const full=gitRepo(j),href=repoURL(j);if(!full)return`<span class="repo">${esc(j.repo||"Not reported")}</span>`;const [owner,name]=full.split("/");return`<a class="repo git-repo" href="${esc(href)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(full)}">${ic("repo")}<span class="git-repo-path"><span class="git-owner">${esc(owner)}</span><span class="git-separator">/</span><span class="git-repo-name">${esc(name)}</span></span></a>`}
function branchHTML(j,branch){const base=repoURL(j.head_repo?{...j,repo_full_name:j.head_repo}:j);if(!branch)return"";const label=esc(branch);return`<span class="git-ref">${ic("branch")}${base?`<a class="git-branch" href="${esc(base+"/tree/"+encodeURIComponent(branch))}" target="_blank" rel="noopener noreferrer" title="Branch: ${label}">${label}</a>`:`<code>${label}</code>`}</span>`}
function commitHTML(j){const sha=String(j.head_sha||""),base=repoURL(j.head_repo?{...j,repo_full_name:j.head_repo}:j);if(!/^[a-f0-9]{7,40}$/i.test(sha))return"";return`<span class="git-ref">${ic("commit")}${base?`<a class="git-commit" href="${esc(base+"/commit/"+sha)}" target="_blank" rel="noopener noreferrer" title="Commit: ${esc(sha)}">${esc(sha.slice(0,7))}</a>`:`<code>${esc(sha.slice(0,7))}</code>`}</span>`}
function prPresentation(pr){const state=pr.state==="merged"?"merged":pr.state==="closed"?"closed":pr.state==="open"?(pr.draft?"draft":"open"):"unknown";return{state,label:({open:"Open",closed:"Closed",merged:"Merged",draft:"Draft",unknown:"Unavailable"})[state],icon:({open:"pr",closed:"prClosed",merged:"merge",draft:"prDraft",unknown:"pr"})[state]}}
function prHTML(pr){const p=prPresentation(pr),number=esc(pr.number),title=`${p.label} pull request #${pr.number}${pr.title?": "+pr.title:""}`;return`<a class="pr git-pr" data-pr-state="${p.state}" href="${esc(url(pr.url))}" target="_blank" rel="noopener noreferrer" aria-label="${esc(title)}" title="${esc(title)}">${ic(p.icon)}<span class="git-pr-number">#${number}</span></a>`}
function gitRefsHTML(j){return arr(j.prs).map(prHTML).join("")+branchHTML(j,j.branch)+commitHTML(j)}
function gitPRCards(j){return arr(j.prs).filter(pr=>pr.title||pr.state).map(pr=>{const p=prPresentation(pr);return`<section class="git-pr-card" aria-label="Pull request #${esc(pr.number)}"><a class="git-pr-title" href="${esc(url(pr.url))}" target="_blank" rel="noopener noreferrer">${esc(pr.title||"Pull request")} <span class="git-pr-number">#${esc(pr.number)}</span></a><div class="git-pr-card-meta"><span class="git-state-label" data-pr-state="${p.state}">${ic(p.icon)}${p.label}</span>${pr.base&&pr.head?`${branchHTML({...j,head_repo:null,repo_full_name:pr.base_repo||gitRepo(j)},pr.base)}<span aria-label="receives changes from">←</span>${branchHTML({...j,head_repo:null,repo_full_name:pr.head_repo===null?"":pr.head_repo||gitRepo(j),repo:pr.head_repo===null?"":j.repo},pr.head)}`:""}</div></section>`}).join("")}
function jobStatusLabel(status){return({running:"In progress",in_progress:"In progress",queued:"Queued",waiting:"Waiting",pending:"Pending"})[status]||String(status||"Unknown")}
let EXPLORE_TAB="overview",INSPECT_KEY="",WATCH=[],ACT_LIMIT=12,CMD_RESULTS=[];
try{WATCH=JSON.parse(localStorage.getItem("rs-watch")||"[]");if(!Array.isArray(WATCH))WATCH=[];WATCH=WATCH.filter(x=>x&&typeof x.key==="string").slice(0,50)}catch(e){}
const jobKey=j=>j.url&&j.url!=="#"?"job:"+j.url:"job:"+JSON.stringify([j.repo,j.workflow,j.name,j.branch,j.runner,arr(j.prs).map(p=>p.number)]);
function jobRecords(s=S){if(!s)return[];const f=flat(s),map=new Map();for(const j of s.jobs){const x=f.find(x=>x.r.name===j.runner);map.set(jobKey(j),{key:jobKey(j),j,x,status:j.status==="in_progress"?"running":"queued"})}for(const x of f)if(x.r.job){const j=x.r.job;map.set(jobKey(j),{key:jobKey(j),j,x,status:"running"})}return[...map.values()]}
function searchFields(j={},x=null,status=""){return{repo:j.repo||"",workflow:j.workflow||"",branch:j.branch||"",runner:x?x.r.name:j.runner||"",machine:x?x.m.name:"",vm:x?x.vm||"":"",label:[...arr(j.labels),...arr(x&&x.r.labels)].join(" "),pr:arr(j.prs).map(p=>"#"+p.number+" pr"+p.number).join(" "),status,text:[j.name,j.repo,j.workflow,j.branch,j.runner,x&&x.r.name,x&&x.m.name,x&&x.vm,...arr(j.labels),...arr(x&&x.r.labels),...arr(j.prs).map(p=>"#"+p.number+" pr"+p.number)].join(" ")}}
function smartMatch(fields,query=FLT){const tokens=String(query).match(/(?:[^\s"]+|"[^"]*")+/g)||[];return tokens.every(raw=>{const neg=raw.startsWith("-"),t=neg?raw.slice(1):raw,k=t.indexOf(":"),field=k>0?t.slice(0,k).toLowerCase():"",value=(k>0&&Object.hasOwn(fields,field)?t.slice(k+1):t).replace(/"/g,"").toLowerCase();const hay=field&&Object.hasOwn(fields,field)?fields[field]:fields.text;const found=String(hay||"").toLowerCase().includes(value);return neg?!found:found})}
function compatibleRunners(j,s=S){if(!s||j.hosted||!arr(j.labels).length)return[];const labels=j.labels.map(l=>String(l).toLowerCase());return flat(s).filter(x=>{const have=arr(x.r.labels).map(l=>String(l).toLowerCase());return labels.every(l=>have.includes(l))})}
function queueDiagnosis(j,s=S){if(j.status==="waiting"||j.status==="pending")return"GitHub reports a pending/waiting job; workflow dependencies, approvals, or concurrency may also apply.";if(j.hosted)return"GitHub-hosted job. Local runners cannot take it; hosted capacity, account limits, or workflow rules may be involved.";if(!arr(j.labels).length)return"Runner requirements were not reported. Compatibility cannot be determined.";const a=compatibleRunners(j,s),idle=a.filter(x=>x.r.status==="idle").length,busy=a.filter(x=>x.r.status==="busy").length;if(!a.length)return"No local runner has every requested label in this snapshot.";if(idle)return`${pl(idle,"idle runner")} match the labels. Repository access, runner groups, and workflow rules still determine scheduling.`;if(busy)return`${pl(busy,"busy runner")} match the labels; none of the matching runners are idle.`;return"Every label-matching runner is offline in this snapshot."}
function inspectButton(j){return`<button class="inspect-open" type="button" data-inspect="${esc(jobKey(j))}" aria-label="Inspect ${esc(j.name||j.workflow||"job")}">Details ${ic("external")}</button>`}
function openInspector(key){INSPECT_KEY=key;renderInspector();openSecondary("inspect")}
function renderInspector(){const b=$("inspectBody"),r=jobRecords().find(r=>r.key===INSPECT_KEY);if(!r){mount(b,'<p class="sheet-intro">This job is no longer in the current snapshot. Its final result is not known here; check GitHub for the outcome.</p>');return}const {j,x,status}=r,watch=WATCH.some(w=>w.key===r.key),facts=[["Status",jobStatusLabel(status)],[status==="running"?"Runtime":"Wait time",dur(j.age_min)],["Repository",j.repo||"Not reported"],["Workflow",j.workflow||"Not reported"],["Branch",j.branch||"Not reported"],...(j.head_sha?[["Commit",j.head_sha]]:[]),["Runner",j.runner||x&&x.r.name||"Not assigned"],["Machine",x?x.m.name+(x.vm?" › "+x.vm:""):j.hosted?"GitHub-hosted":"Not assigned"],["Labels",arr(j.labels).join(", ")||"Not reported"],["Snapshot",S.updated?new Date(S.updated).toLocaleString():"Unknown"]];mount(b,`<h3 class="inspect-title">${esc(j.name||j.workflow)}</h3><div class="meta git-context">${prs(j)}</div><dl class="inspect-facts">${facts.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${k==="Status"?`<span class="status-badge ${status}">${ic(status==="running"?"play":"clock")}${esc(v)}</span>`:k==="Repository"?repoHTML(j):k==="Branch"&&j.branch?branchHTML(j,j.branch):k==="Commit"?commitHTML(j):esc(v)}</dd>`).join("")}</dl>${gitPRCards(j)}${status==="queued"?`<h3 class="sheet-heading">Why might it be waiting?</h3><p class="sheet-intro">${esc(queueDiagnosis(j))}</p>${!j.hosted?`<ul class="insight-list">${compatibleRunners(j).map(x=>`<li><b>${esc(x.r.name)}</b><small>${esc(x.m.name)}${x.vm?" › "+esc(x.vm):""} · ${esc(x.r.status)} · labels match</small></li>`).join("")}</ul>`:""}`:""}<div class="sheet-actions">${j.url&&j.url!=="#"?`<a class="btn" href="${esc(url(j.url))}" target="_blank" rel="noopener noreferrer">Open on GitHub ${ic("external")}</a>`:""}<button class="btn" type="button" data-watch="${esc(r.key)}" aria-pressed="${watch}">${watch?"Unwatch job":"Watch job"}</button><button class="btn" type="button" data-copy-job="${esc(r.key)}">Copy job brief</button><button class="btn" type="button" data-explore="${EXPLORE_TAB}">Explore</button></div><p class="search-tip">Read-only. Watching stays on this device. Missing jobs are not assumed to be completed.</p>`)}
function queueStats(s=S){const q=jobRecords(s).filter(r=>r.status==="queued"),ages=q.map(r=>r.j.age_min).filter(v=>v!=null).sort((a,b)=>a-b),n=ages.length;return{q,oldest:n?ages[n-1]:null,median:n?(ages[Math.floor((n-1)/2)]+ages[Math.floor(n/2)])/2:null,breached:q.filter(r=>r.j.age_min!=null&&r.j.age_min>=PREF.sla).length}}
function renderExplore(){const b=$("exploreBody");for(const e of document.querySelectorAll('#explore [data-explore]'))e.setAttribute("aria-pressed",e.dataset.explore===EXPLORE_TAB);if(!S){mount(b,'<p class="sheet-intro">Waiting for the first snapshot.</p>');return}const records=jobRecords(),stats=queueStats(),intro=`<p class="sheet-intro">Current snapshot${S.loading?" · GitHub sweep still loading":""} · ${S.updated?esc(new Date(S.updated).toLocaleString()):"timestamp unknown"}${PAUSED?" · paused":""}. These views use the same read-only data as the dashboard.</p>`;
 if(EXPLORE_TAB==="overview"){const groups=new Map();for(const r of stats.q){const labels=arr(r.j.labels).slice().sort().join(", ")||"Requirements not reported",key=(r.j.hosted?"GitHub-hosted":"Self-hosted")+" · "+labels;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r)}mount(b,intro+`<div class="insight-grid">${[[dur(stats.oldest),"Oldest wait"],[dur(stats.median),"Median wait"],[stats.breached,"Past "+PREF.sla+"m target"]].map(([n,l])=>`<div class="insight-stat"><b>${esc(n)}</b><span>${esc(l)}</span></div>`).join("")}</div><h3 class="sheet-heading">Queue by runner requirements</h3><ul class="insight-list">${[...groups].sort((a,b)=>b[1].length-a[1].length).map(([k,rs])=>`<li><b>${esc(k)}</b><small>${pl(rs.length,"job")} · oldest ${dur(Math.max(...rs.map(r=>r.j.age_min||0)))}</small><small>${esc(queueDiagnosis(rs[0].j))}</small><button class="text-btn" type="button" data-inspect="${esc(rs[0].key)}">Inspect a job →</button></li>`).join("")||'<li>No queued jobs in this snapshot.</li>'}</ul><p class="search-tip">Label matches are not a start-time prediction. Repository permissions, runner groups, and concurrency are not available here.</p>`) }
 else if(EXPLORE_TAB==="repos"){const repos=new Map();for(const r of records){const n=r.j.repo||"Unknown repository";if(!repos.has(n))repos.set(n,[]);repos.get(n).push(r)}mount(b,intro+`<ul class="insight-list">${[...repos].sort((a,b)=>b[1].filter(r=>r.status==="queued").length-a[1].filter(r=>r.status==="queued").length||a[0].localeCompare(b[0])).map(([name,rs])=>{const q=rs.filter(r=>r.status==="queued"),ages=q.map(r=>r.j.age_min).filter(v=>v!=null);return`<li><div class="git-repo-summary">${repoHTML(rs[0].j)}<button class="text-btn" data-repo-filter="${esc(name)}" type="button">View activity →</button></div><small>${rs.length-q.length} in progress · ${q.length} queued${ages.length?" · oldest wait "+dur(Math.max(...ages)):""}</small></li>`}).join("")||'<li>No active repositories in this snapshot.</li>'}</ul>`) }
 else{mount(b,intro+`<p class="sheet-intro">Follow up to 50 jobs on this device. When a job disappears from the active feed, check GitHub for its final result.</p><ul class="insight-list">${WATCH.map(w=>{const r=records.find(r=>r.key===w.key);return`<li><b>${esc(w.name)}</b><small>${repoHTML(r?r.j:{repo:w.repo,repo_full_name:w.repo_full_name})} · ${r?(jobStatusLabel(r.status))+" · "+dur(r.j.age_min):"No longer in current snapshot · outcome unknown"}</small><div class="sheet-actions">${r?`<button class="text-btn" data-inspect="${esc(w.key)}" type="button">Inspect →</button>`:w.url&&w.url!=="#"?`<a href="${esc(url(w.url))}" target="_blank" rel="noopener noreferrer">Check GitHub ${ic("external")}</a>`:""}<button class="text-btn" data-watch="${esc(w.key)}" type="button">Unwatch</button></div></li>`}).join("")||'<li>Your watchlist is empty.<small>Open Details on a job and choose Watch job.</small></li>'}</ul>`) }}
function openExplore(tab="overview"){EXPLORE_TAB=tab;renderExplore();openSecondary("explore")}
function toggleWatch(key){const i=WATCH.findIndex(w=>w.key===key);if(i>=0)WATCH.splice(i,1);else{const r=jobRecords().find(r=>r.key===key);if(!r)return;if(WATCH.length>=50)return toast("Watchlist full; unwatch a job first");WATCH.unshift({key,name:r.j.name||r.j.workflow,repo:r.j.repo,repo_full_name:gitRepo(r.j),url:r.j.url})}save("rs-watch",WATCH);if($("inspect").open)renderInspector();if($("explore").open)renderExplore();toast(i>=0?"Job unwatched":"Watching job on this device")}
function jobBrief(r){return[`${r.j.repo} · ${r.j.workflow} / ${r.j.name}`,`${jobStatusLabel(r.status)} · ${dur(r.j.age_min)}`,r.x?`Runner: ${r.x.r.name} · ${r.x.m.name}${r.x.vm?" / "+r.x.vm:""}`:"Runner: "+(r.j.runner||"not assigned"),"Labels: "+arr(r.j.labels).join(", "),r.status==="queued"?queueDiagnosis(r.j):"",r.j.url||""].filter(Boolean).join("\n")}
function filteredRecords(){return jobRecords().filter(r=>smartMatch(searchFields(r.j,r.x,r.status))&&(QF==="all"||QF===r.status||QF==="attention"&&(r.status==="queued"?r.j.age_min>=PREF.sla:r.j.age_min>=240||arr(r.j.closed_prs).length)))}
const csvCell=v=>'"'+String(v??"").replace(/^[\s]*[=+@-]/,"'$&").replace(/"/g,'""')+'"';
function activityCSV(){const rs=filteredRecords();return[["Repository","Workflow","Job","Status","Age minutes","Runner","Machine","VM","Labels","URL"],...rs.map(({j,x,status})=>[j.repo,j.workflow,j.name,status,j.age_min,j.runner||x&&x.r.name,x&&x.m.name,x&&x.vm,arr(j.labels).join("; "),j.url])].map(row=>row.map(csvCell).join(",")).join("\r\n")}
function exportCSV(){if(!S)return toast("No snapshot to export");const blob=new Blob(["\ufeff"+activityCSV()],{type:"text/csv;charset=utf-8"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="runner-activity-"+new Date().toISOString().slice(0,10)+".csv";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500);toast("Matching jobs exported")}
const COMMANDS=[
 ["Queue insights",()=>openExplore("overview"),""],["Repository overview",()=>openExplore("repos"),""],["Open watchlist",()=>openExplore("watch"),""],["Export matching jobs CSV",exportCSV,""],
 ["Refresh now",()=>tick(true),"R"],["Search activity",()=>{$("cmd").close();$("flt").focus()},"/"],["Open dashboard controls",openControls,""],["Open timeline",()=>openSecondary("timeline"),""],
 ["Pause or resume live updates",()=>setPaused(!PAUSED),"P"],["Change light/dark theme",cycleTheme,"T"],["Toggle compact density",()=>{PREF.density=PREF.density==="compact"?"comfortable":"compact";persistPrefs();toast("Density: "+PREF.density)},""],["Toggle focus mode",()=>{PREF.focus=!PREF.focus;persistPrefs(false);toast(PREF.focus?"Focus mode on":"Focus mode off")},""],
 ["Copy shareable view link",()=>copyText(viewURL(),"View link copied"),""],["Copy status brief",()=>copyText(statusBrief(),"Status brief copied"),""],["Export snapshot JSON",exportJSON,""],["Expand all machines",()=>setAllMachines(true),""],["Collapse all machines",()=>setAllMachines(false),""]
];let CMD_SEL=0;
function renderCommands(){const q=$("cmd-in").value.trim().toLowerCase(),base=COMMANDS.map(x=>({label:x[0],note:"Command",run:x[1],key:x[2]})),jobs=q?jobRecords().filter(r=>smartMatch(searchFields(r.j,r.x,r.status),q)).map(r=>({label:r.j.name||r.j.workflow,note:r.j.repo+" · "+(jobStatusLabel(r.status)),run:()=>openInspector(r.key)})):[],machines=S?S.machines.filter(m=>q&&m.name.toLowerCase().includes(q)).map(m=>({label:m.name,note:"Machine · show activity",run:()=>applySearch(`machine:"${m.name}"`)})):[],views=SAVED.filter(v=>q&&v.name.toLowerCase().includes(q)).map(v=>({label:v.name,note:"Saved view",run:()=>loadView(v)}));CMD_RESULTS=[...base.filter(x=>x.label.toLowerCase().includes(q)),...views,...machines,...jobs];const total=CMD_RESULTS.length;CMD_RESULTS=CMD_RESULTS.slice(0,40);CMD_SEL=Math.min(CMD_SEL,Math.max(0,CMD_RESULTS.length-1));$("cmd-list").innerHTML=CMD_RESULTS.map((x,i)=>`<li><button class="cmd-item${i===CMD_SEL?" sel":""}" type="button" data-command="${i}"><span class="cmd-label">${esc(x.label)}<small>${esc(x.note)}</small></span>${x.key?`<small>${esc(x.key)}</small>`:""}</button></li>`).join("")+(total>40?`<li class="cmd-count">Showing 40 of ${total}. Keep typing to narrow results.</li>`:"")||'<li class="empty">No matches. Try a repository, runner, or job name.</li>'}
function openCommands(){CMD_SEL=0;$("cmd-in").value="";renderCommands();openSecondary("cmd");setTimeout(()=>$("cmd-in").focus())}
function syncMachineControls(){const all=[...document.querySelectorAll(".machine")],healthy=all.filter(d=>d.dataset.health==="ok");$("all-machines").disabled=!all.length;$("all-machines").textContent=all.length&&all.every(d=>d.open)?"Collapse all machines":"Expand all machines";$("collapse-healthy").disabled=!healthy.length;$("collapse-healthy").textContent=healthy.length&&healthy.every(d=>d.open)?"Collapse healthy machines":"Expand healthy machines"}
function setAllMachines(open){for(const d of document.querySelectorAll(".machine"))d.open=open;syncMachineControls();toast((open?"Expanded ":"Collapsed ")+"all machines")}
const TOUR=[
 ["Command anything","Press ⌘K or Ctrl+K to search every major action without leaving the keyboard.","#settingsb"],["Read the verdict first","The hero bundles related symptoms into incidents and tells you what needs action.","#hero"],["One place for controls","Open Filters or the More menu for sorting, appearance, saved views, and live-data tools.","#activity"],["Compare machines","Open the machine actions menu on any two machine cards and choose Compare machine.","#hosts"],["Light, dark, or automatic","Open More, then Appearance and layout to choose Light, Dark, or Auto. Auto follows your device.","#settingsb"]
];
function tourRender(){document.querySelectorAll(".tour-target").forEach(e=>e.classList.remove("tour-target"));const x=TOUR[TOUR_I];$("tourStep").textContent=`Step ${TOUR_I+1} of ${TOUR.length}`;$("tour-h").textContent=x[0];$("tourText").textContent=x[1];$("tourBack").disabled=TOUR_I===0;$("tourNext").textContent=TOUR_I===TOUR.length-1?"Finish":"Next";const t=document.querySelector(x[2]);if(t)t.classList.add("tour-target")}
function startTour(){TOUR_I=0;tourRender();openSecondary("tour")}
tick();setInterval(tick,15000);setInterval(tickAll,1000);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)tick()});
/* controls and keyboard */
const flt=$("flt");flt.value=FLT;function clearSearch(){flt.value="";FLT="";ACT_LIMIT=12;renderActivity()}
function resetFilters(){ACT_LIMIT=12;QF="all";ORDER="age";FLT="";flt.value="";save("rs-qf",QF);save("rs-order",ORDER);renderActivity()}
flt.addEventListener("input",()=>{FLT=flt.value.trim().toLowerCase();ACT_LIMIT=12;renderActivity()});flt.addEventListener("keydown",e=>{if(e.key==="Escape"){clearSearch();flt.blur()}});$("flt-clear").onclick=()=>{clearSearch();flt.focus()};
for(const b of document.querySelectorAll("[data-qf]"))b.onclick=()=>{ACT_LIMIT=12;QF=b.dataset.qf;save("rs-qf",QF);renderActivity()};
$("order").onchange=e=>{ACT_LIMIT=12;ORDER=e.target.value;save("rs-order",ORDER);renderActivity()};
$("settingsGrid").addEventListener("change",e=>{const p=e.target.dataset.pref,sec=e.target.dataset.section;if(sec){PREF.sections[sec]=e.target.checked}else if(p){let v=e.target.type==="checkbox"?e.target.checked:e.target.value;if(["chart","scale","sla"].includes(p))v=Number(v);if(p==="hour24")v=v==="true";PREF[p]=v}persistPrefs();toast("Dashboard updated")});
document.addEventListener("click",e=>{
 const inspect=e.target.closest&&e.target.closest("[data-inspect]");if(inspect){openInspector(inspect.dataset.inspect);return}
 const explore=e.target.closest&&e.target.closest("[data-explore]");if(explore){openExplore(explore.dataset.explore);return}
 const watch=e.target.closest&&e.target.closest("[data-watch]");if(watch){toggleWatch(watch.dataset.watch);return}
 const brief=e.target.closest&&e.target.closest("[data-copy-job]");if(brief){const r=jobRecords().find(r=>r.key===brief.dataset.copyJob);if(r)copyText(jobBrief(r),"Job brief copied");return}
 const repo=e.target.closest&&e.target.closest("[data-repo-filter]");if(repo){applySearch(`repo:"${repo.dataset.repoFilter}"`);return}
 if(e.target.closest&&e.target.closest("#queue-more")){ACT_LIMIT+=12;renderActivity();const b=$("queue-more")||$("queue-less");if(b)b.focus({preventScroll:true});return}
 if(e.target.closest&&e.target.closest("#queue-less")){ACT_LIMIT=12;renderActivity();$("queue-more")?.focus();return}
 if(e.target.closest&&e.target.closest("#secondaryStats a"))$("settings").close();
 const close=e.target.closest&&e.target.closest("[data-close]");if(close){$(close.dataset.close).close();return}
 const menu=e.target.closest&&e.target.closest("[data-machine-menu]");if(menu){e.preventDefault();e.stopPropagation();openMachineMenu(menu.dataset.machineMenu);return}
 const cmd=e.target.closest&&e.target.closest("[data-command]");if(cmd){const fn=CMD_RESULTS[Number(cmd.dataset.command)]?.run;if(!fn)return;$("cmd").close();setTimeout(fn);return}
 const load=e.target.closest&&e.target.closest("[data-load-view]");if(load){loadView(SAVED[Number(load.dataset.loadView)]);return}
 const del=e.target.closest&&e.target.closest("[data-delete-view]");if(del){SAVED.splice(Number(del.dataset.deleteView),1);save("rs-views",SAVED);renderSavedViews();toast("Saved view deleted");return}
 const ack=e.target.closest&&e.target.closest("[data-ack]");if(ack){ACK.add(ack.dataset.ack);save("rs-ack",[...ACK]);render(S);toast("Incident acknowledged locally");return}
 const snooze=e.target.closest&&e.target.closest("[data-snooze]");if(snooze){SNOOZE[snooze.dataset.snooze]=Date.now()+30*60*1000;save("rs-snooze",SNOOZE);TIMELINE.unshift({kind:"snoozed",level:"warn",text:"Incident snoozed for 30 minutes",at:Date.now()});save("rs-timeline",TIMELINE);render(S);toast("Incident snoozed for 30 minutes");return}
 const ci=e.target.closest&&e.target.closest("[data-copy-incident]");if(ci){copyText(ci.dataset.copyIncident,"Incident copied");return}
 const pin=e.target.closest&&e.target.closest("[data-pin-machine]");if(pin){e.preventDefault();e.stopPropagation();$("machine-menu").close();const n=pin.dataset.pinMachine;PINS.has(n)?PINS.delete(n):PINS.add(n);save("rs-pins",[...PINS]);render(S);toast(PINS.has(n)?n+" pinned":n+" unpinned");return}
 const comp=e.target.closest&&e.target.closest("[data-compare-machine]");if(comp){e.preventDefault();e.stopPropagation();$("machine-menu").close();const n=comp.dataset.compareMachine;if(COMPARE.has(n))COMPARE.delete(n);else if(COMPARE.size<2)COMPARE.add(n);else toast("Clear one machine before selecting another");updateCompareTray();return}
 const note=e.target.closest&&e.target.closest("[data-note-machine]");if(note){e.preventDefault();e.stopPropagation();NOTE_MACHINE=note.dataset.noteMachine;$("noteMachine").textContent=NOTE_MACHINE;$("note-text").value=NOTES[NOTE_MACHINE]||"";$("note").returnValue="";openSecondary("note");return}
 const f=e.target.closest&&e.target.closest("[data-filter]");if(f){e.preventDefault();if($("machine-menu").open)$("machine-menu").close();QF="all";FLT=f.dataset.filter.toLowerCase();flt.value=f.dataset.filter;save("rs-qf",QF);renderActivity();location.hash="activity";return}
 if(e.target.closest&&e.target.closest("#changeSummary")){UNSEEN=0;updateChangeCount();renderTimeline();openSecondary("timeline")}
});
$("collapse-healthy").onclick=()=>{const a=[...document.querySelectorAll('.machine[data-health="ok"]')],open=!a.every(d=>d.open);for(const d of a)d.open=open;syncMachineControls()};
function applySearch(query){QF="all";FLT=query.toLowerCase();flt.value=query;ACT_LIMIT=12;save("rs-qf",QF);for(const d of document.querySelectorAll("dialog[open]"))d.close();renderActivity();location.hash="activity";flt.focus()}
$("find-anything").onclick=openCommands;$("export-csv").onclick=exportCSV;
function setPaused(v){PAUSED=v;$("pause").classList.toggle("on",v);$("pauseIcon").innerHTML=ic(v?"run":"pause");$("pauseTx").textContent=v?"Resume live updates":"Pause live updates";$("pause").setAttribute("aria-label",$("pauseTx").textContent);tickFresh();if(!v)tick()}
$("pause").onclick=()=>setPaused(!PAUSED);
$("refresh").onclick=()=>{tick(true);toast("Refreshing now")};
$("activity-view").onclick=()=>{PREF.activity=PREF.activity==="compact"?"cards":"compact";persistPrefs(false);renderActivity();toast(PREF.activity==="compact"?"Compact activity rows":"Comfortable activity rows")};
$("all-machines").onclick=()=>setAllMachines(![...document.querySelectorAll(".machine")].every(d=>d.open));
$("settingsb").onclick=$("mobile-more").onclick=()=>openControls();$("filtersb").onclick=()=>openControls("filterControls");
$("filters-reset").onclick=$("panel-filters-reset").onclick=resetFilters;
$("timelineb").onclick=()=>{UNSEEN=0;updateChangeCount();renderTimeline();openSecondary("timeline")};
$("compareOpen").onclick=openCompare;$("compareClear").onclick=()=>{COMPARE.clear();updateCompareTray()};
$("save-view").onclick=()=>{$("viewNameInput").value=`View ${SAVED.length+1}`;$("viewNameInput").setCustomValidity("");$("view-name").returnValue="";openSecondary("view-name");$("viewNameInput").focus();$("viewNameInput").select()};
$("viewNameInput").oninput=()=>$("viewNameInput").setCustomValidity("");
$("viewNameForm").onsubmit=e=>{e.preventDefault();const n=$("viewNameInput").value.trim();if(!n){$("viewNameInput").setCustomValidity("Enter a view name.");$("viewNameInput").reportValidity();return}SAVED.unshift(snapshotView(n));SAVED=SAVED.slice(0,12);save("rs-views",SAVED);$("view-name").close("save");toast("View saved")};
$("view-name").addEventListener("close",()=>{if(!document.querySelector("dialog[open]"))openControls("savedControls")});
$("share-view").onclick=()=>copyText(viewURL(),"View link copied");$("copy-brief").onclick=()=>copyText(statusBrief(),"Status brief copied");$("export-json").onclick=exportJSON;
$("reset-ui").onclick=()=>{$("reset-confirm").returnValue="";openSecondary("reset-confirm")};
$("reset-confirm").addEventListener("close",()=>{if($("reset-confirm").returnValue!=="reset"){if(!document.querySelector("dialog[open]"))openControls("helpControls");return}for(const k of["rs-prefs","rs-pins","rs-notes","rs-ack","rs-snooze","rs-views","rs-open","rs-qf","rs-order","rs-watch"])try{localStorage.removeItem(k)}catch(e){};OP={};ACT_LIMIT=12;PREF={...DEF,sections:{...DEF.sections}};PINS.clear();COMPARE.clear();NOTES={};ACK.clear();SNOOZE={};SAVED=[];WATCH=[];QF="all";ORDER="age";FLT="";flt.value="";applyPrefs();render(S);toast("Personalization reset")});
$("note").addEventListener("close",()=>{if($("note").returnValue!=="save")return;const v=$("note-text").value.trim();if(v)NOTES[NOTE_MACHINE]=v;else delete NOTES[NOTE_MACHINE];save("rs-notes",NOTES);render(S);toast(v?"Machine note saved":"Machine note removed")});
$("cmd-in").addEventListener("input",()=>{CMD_SEL=0;renderCommands()});$("cmd-in").addEventListener("keydown",e=>{if(e.key==="Escape"){e.preventDefault();$("cmd").close();return}const n=$("cmd-list").querySelectorAll("[data-command]").length;if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();CMD_SEL=Math.max(0,Math.min(n-1,CMD_SEL+(e.key==="ArrowDown"?1:-1)));renderCommands()}else if(e.key==="Enter"){e.preventDefault();const b=$("cmd-list").querySelectorAll("[data-command]")[CMD_SEL];if(b)b.click()}});
$("tour-start").onclick=startTour;$("tourDone").onclick=()=>$("tour").close();$("tourBack").onclick=()=>{TOUR_I=Math.max(0,TOUR_I-1);tourRender()};$("tourNext").onclick=()=>{if(TOUR_I===TOUR.length-1){$("tour").close();toast("Tour complete")}else{TOUR_I++;tourRender()}};$("tour").addEventListener("close",()=>document.querySelectorAll(".tour-target").forEach(e=>e.classList.remove("tour-target")));
$("helpb").onclick=()=>openSecondary("help");
document.addEventListener("toggle",e=>{if(e.target.classList&&e.target.classList.contains("machine"))syncMachineControls();if(e.target.classList&&e.target.classList.contains("hero-all")&&!matchMedia("(min-width:641px)").matches)HERO_MOBILE_OPEN=e.target.open},true);
document.addEventListener("keydown",e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){e.preventDefault();openCommands();return}if(e.metaKey||e.ctrlKey||e.altKey||document.querySelector("dialog[open]"))return;const t=e.target.tagName;if(t==="INPUT"||t==="TEXTAREA"||t==="SELECT")return;const key=e.key.toLowerCase();
 if(e.key==="/"){e.preventDefault();flt.focus();flt.select()}
 else if(key==="t")cycleTheme();
 else if(key==="p")setPaused(!PAUSED);
 else if(key==="j"||key==="k"){const a=[...document.querySelectorAll("[data-nav]")].filter(x=>x.offsetParent!==null);if(a.length){NAV_I=NAV_I<0?(key==="j"?0:a.length-1):(NAV_I+(key==="j"?1:-1)+a.length)%a.length;a.forEach(x=>x.classList.remove("kb-focus"));a[NAV_I].classList.add("kb-focus");a[NAV_I].focus({preventScroll:true});a[NAV_I].scrollIntoView({block:"center",behavior:PREF.motion==="reduce"?"auto":"smooth"})}}
 else if(e.key==="Escape"&&!HV&&(FLT||QF!=="all"||ORDER!=="age")){resetFilters()}
 else if(e.key==="Escape"&&HV){const g=HV.g;HV=null;HLOCK=false;clearXH(g)}
 else if(e.key==="?"){const d=$("help");d.open?d.close():openSecondary("help")}
 else if(key==="i"){const d=$("sec-idle");if(d){d.open=!d.open;if(d.open)d.scrollIntoView({block:"nearest"})}}
 else if(key==="a"){const more=$("ag-more");if(more&&!more.open)more.open=true;const all=[...document.querySelectorAll(".ags details.ag")],open=all.some(d=>!d.open);all.forEach(d=>d.open=open);$("hero").scrollIntoView({block:"start"})}});
</script></body></html>
"""

# Keep the deployable program a single stdlib-only file while serving the large
# UI assets separately. That makes the first HTML response small and lets the
# browser parse CSS and JavaScript in parallel; no third-party asset is loaded.
_page_css_match = re.search(r"<style>(.*?)</style>", _PAGE_SOURCE, re.S)
_page_scripts = re.findall(r"<script>(.*?)</script>", _PAGE_SOURCE, re.S)
assert _page_css_match and len(_page_scripts) == 2
PAGE_CSS = _page_css_match.group(1)
PAGE_JS = _page_scripts[-1]
PAGE = re.sub(r"<style>.*?</style>", '<link rel="stylesheet" href="/app.css">',
              _PAGE_SOURCE, count=1, flags=re.S)
PAGE = PAGE.replace("<script>" + PAGE_JS + "</script>",
                    '<script src="/app.js"></script>')


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
        if path == "/app.css":
            return PAGE_CSS, "text/css; charset=utf-8"
        if path == "/app.js":
            return PAGE_JS, "text/javascript; charset=utf-8"
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
