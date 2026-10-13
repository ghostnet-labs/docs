#!/usr/bin/env python3
"""Daily disk cleanup for self-hosted GitHub Actions runner hosts.

One file, Python 3.9+ standard library only. Meant for the Macs that run
native runners plus Lima VMs with Linux runners inside.

DRY RUN BY DEFAULT: it prints what it finds and what it would remove, with
sizes. Nothing is deleted unless --apply is given. Run it by hand in dry-run
mode first and read the report before installing the LaunchAgent.

What it cleans (idle runners only; a runner with a job running is skipped):
  <runner>/_work/_temp/*            any age
  <runner>/_work/<checkout>         untouched for --work-days (default 3)
  <runner>/_work/_actions/*         untouched for 14 days
  <runner>/_diag/*.log              older than --log-days (default 7)
  ~/Library/Logs/runner-status-*.log and runner-cleanup.log over 50 MB
                                    (truncated to their last 5 MB)
  Go build cache over 20 GB         (`go clean -cache`; ~/go/pkg/mod is never touched)
  Homebrew cache over 2 GB          (`brew cleanup --prune=14`)
  Inside each running Lima VM: the same runner rules, journald older than 7
  days, docker objects older than 72h (never volumes, never -a), then fstrim
  so the host's sparse disk image can shrink.

It never touches .runner, .credentials*, .env, .path, bin*, externals*,
svc.sh, config.sh, run.sh or _work/_tool. Every delete goes through
safe_delete(), which refuses anything outside the runner's _work/ or _diag/.

Examples:
  python3 runner_cleanup.py                    # dry run, human report
  python3 runner_cleanup.py --json             # dry run, JSON summary
  python3 runner_cleanup.py --apply            # actually delete
  python3 runner_cleanup.py --apply --no-vms   # host only
  python3 runner_cleanup.py --print-launchd > ~/Library/LaunchAgents/com.ghostnet.runner-cleanup.plist
"""

from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from typing import Callable, Iterable

MB = 1024 ** 2
GB = 1024 ** 3
DAY = 86400

ACTIONS_DAYS = 14
LOG_LIMIT = 50 * MB  # status logs above this are truncated...
LOG_KEEP = 5 * MB  # ...down to their last 5 MB
GO_CACHE_THRESHOLD = 20 * GB
BREW_THRESHOLD = 2 * GB
WORKER_LOG_GRACE = 600  # a runner whose Worker log changed this recently counts as busy
VM_TIMEOUT = 1800
LABEL = "com.ghostnet.runner-cleanup"
LOCK_FILE = os.path.expanduser("~/.cache/runner-cleanup.lock")
LOGS_DIR = os.path.expanduser("~/Library/Logs")
LOG_GLOBS = ("runner-status-*.log", "runner-cleanup.log")

# Top-level entries of _work that are never removed as a whole.
WORK_KEEP = ("_tool", "_actions", "_temp", "_PipelineMapping")
# Runner-dir entries that are never removed. A trailing * is a prefix match.
PROTECTED = (".runner", ".credentials*", ".env", ".path", "bin*", "externals*",
             "svc.sh", "config.sh", "run.sh")
# Directories never descended into while looking for runners.
SKIP_NAMES = (".Trash", ".git", "node_modules", "_work", "_diag")

def fmt_bytes(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _run(cmd: list[str], timeout: float = 15, env: dict | None = None) -> str | None:
    exe = shutil.which(cmd[0]) or next(
        (p for p in (f"/opt/homebrew/bin/{cmd[0]}", f"/usr/local/bin/{cmd[0]}",
                     f"/usr/sbin/{cmd[0]}", f"/usr/bin/{cmd[0]}") if os.path.exists(p)),
        None)
    if exe is None:
        return None
    full_env = None if env is None else {**os.environ, **env}
    try:
        out = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True,
                             timeout=timeout, check=False, env=full_env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# Sizes and ages
# --------------------------------------------------------------------------

def _alloc(st: os.stat_result) -> int:
    blocks = getattr(st, "st_blocks", None)
    return blocks * 512 if blocks is not None else st.st_size


def tree_size(path: str) -> int:
    """Allocated bytes under path. Never follows symlinks."""
    try:
        st = os.lstat(path)
    except OSError:
        return 0
    total = _alloc(st)
    if not os.path.isdir(path) or os.path.islink(path):
        return total
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            try:
                total += _alloc(os.lstat(os.path.join(root, name)))
            except OSError:
                pass
    return total


def dir_size(path: str, runner: Callable = _run) -> int:
    """Size of a big cache dir: `du -sk` when available (fast), else a walk."""
    out = runner(["du", "-sk", path], timeout=600)
    if out:
        first = out.split()[0] if out.split() else ""
        if first.isdigit():
            return int(first) * 1024
    return tree_size(path)


def newest_mtime(path: str) -> float:
    """Newest mtime of path and its immediate children (cheap, no deep walk)."""
    try:
        newest = os.lstat(path).st_mtime
    except OSError:
        return time.time()  # unreadable: treat as fresh so it is left alone
    if os.path.isdir(path) and not os.path.islink(path):
        try:
            with os.scandir(path) as it:
                for e in it:
                    try:
                        newest = max(newest, e.stat(follow_symlinks=False).st_mtime)
                    except OSError:
                        pass
        except OSError:
            pass
    return newest


def _entries(path: str) -> list[os.DirEntry]:
    if not os.path.isdir(path) or os.path.islink(path):
        return []
    try:
        with os.scandir(path) as it:
            return sorted(it, key=lambda e: e.name)
    except OSError:
        return []


# --------------------------------------------------------------------------
# Runner discovery and busy check
# --------------------------------------------------------------------------

def discover_runners(roots: Iterable[str], max_depth: int = 4) -> list[str]:
    """Directories holding a `.runner` file, at most max_depth below a root.
    Never follows symlinks, never enters ~/Library, never descends into a
    runner dir once found."""
    home_lib = os.path.realpath(os.path.expanduser("~/Library"))
    found: list[str] = []
    seen: set[str] = set()

    def walk(path: str, depth: int) -> None:
        real = os.path.realpath(path)
        if real in seen or real == home_lib:
            return
        seen.add(real)
        if os.path.isfile(os.path.join(path, ".runner")) and not os.path.islink(os.path.join(path, ".runner")):
            found.append(path)
            return
        if depth >= max_depth:
            return
        for e in _entries(path):
            if e.name in SKIP_NAMES or e.is_symlink():
                continue
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                walk(e.path, depth + 1)

    for root in roots:
        root = os.path.abspath(os.path.expanduser(root))
        if os.path.isdir(root) and not os.path.islink(root):
            walk(root, 0)
    return found


def parse_ps(text: str, read_cwd: bool = False) -> list[dict]:
    """Parse `ps -o pid,ppid,etime,command` output (header line first)."""
    procs = []
    for line in text.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        p = {"pid": int(parts[0]), "ppid": parts[1], "etime": parts[2], "cmd": parts[3], "cwd": None}
        if read_cwd:
            try:
                p["cwd"] = os.readlink(f"/proc/{p['pid']}/cwd")
            except OSError:
                pass
        procs.append(p)
    return procs


def list_processes(system: str | None = None, runner: Callable = _run) -> list[dict] | None:
    """All processes, or None when ps fails (callers then treat everything as busy)."""
    system = system or platform.system()
    if system == "Darwin":
        cmd = ["ps", "-axww", "-o", "pid,ppid,etime,command"]
    else:
        cmd = ["ps", "-eww", "-o", "pid,ppid,etime,cmd"]
    out = runner(cmd, timeout=15)
    if out is None:
        return None
    me = os.getpid()
    return [p for p in parse_ps(out, read_cwd=system == "Linux") if p["pid"] != me]


def runner_busy(rdir: str, procs: list[dict] | None, now: float | None = None) -> str | None:
    """Why this runner must be left alone, or None if it is idle."""
    if procs is None:
        return "process list unavailable"
    now = time.time() if now is None else now
    for d in {rdir.rstrip("/"), os.path.realpath(rdir)}:
        work = d + "/_work/"
        for p in procs:
            cmd, cwd = p.get("cmd") or "", p.get("cwd") or ""
            if "Runner.Worker" in cmd and d + "/" in cmd:
                return f"Runner.Worker running (pid {p.get('pid')})"
            if work in cmd or (cwd + "/").startswith(work):
                return f"pid {p.get('pid')} is using _work"
    for log in glob.glob(os.path.join(rdir, "_diag", "Worker_*.log")):
        try:
            if now - os.lstat(log).st_mtime < WORKER_LOG_GRACE:
                return "a job finished in the last 10 minutes"
        except OSError:
            pass
    return None


# --------------------------------------------------------------------------
# Candidates and the single delete path
# --------------------------------------------------------------------------

def runner_candidates(rdir: str, now: float, work_days: float, log_days: float,
                      actions_days: float = ACTIONS_DAYS) -> list[dict]:
    work, diag = os.path.join(rdir, "_work"), os.path.join(rdir, "_diag")
    out: list[dict] = []

    def add(path: str, kind: str) -> None:
        out.append({"path": path, "kind": kind, "bytes": tree_size(path)})

    def old(path: str, days: float) -> bool:
        return now - newest_mtime(path) > days * DAY

    for e in _entries(os.path.join(work, "_temp")):
        add(e.path, "temp")
    for e in _entries(work):
        if e.name not in WORK_KEEP and e.is_dir(follow_symlinks=False) and old(e.path, work_days):
            add(e.path, "checkout")
    for e in _entries(os.path.join(work, "_actions")):
        if old(e.path, actions_days):
            add(e.path, "actions")
    for e in _entries(diag):
        if e.name.endswith(".log") and e.is_file(follow_symlinks=False) and old(e.path, log_days):
            add(e.path, "diag-log")
    return out


def runner_roots(rdir: str) -> list[str]:
    return [os.path.join(os.path.realpath(rdir), "_work"), os.path.join(os.path.realpath(rdir), "_diag")]


def _is_protected_name(name: str) -> bool:
    return any(name.startswith(p[:-1]) if p.endswith("*") else name == p for p in PROTECTED)


def check_path(path: str, roots: Iterable[str], allowed_files: Iterable[str] = ()) -> str | None:
    """Why path may not be deleted, or None if it may. For a symlink the link
    itself is judged (by its real parent dir), never its target."""
    if os.path.islink(path):
        real = os.path.join(os.path.realpath(os.path.dirname(os.path.abspath(path))), os.path.basename(path))
    else:
        real = os.path.realpath(path)
    if real in {os.path.realpath(f) for f in allowed_files}:
        return None
    roots = [os.path.realpath(r) for r in roots]
    if os.path.dirname(real) in {os.path.dirname(r) for r in roots} and _is_protected_name(os.path.basename(real)):
        return "protected runner file"
    for root in roots:
        if not real.startswith(root + os.sep):
            continue
        rel = os.path.relpath(real, root)
        if os.path.basename(root) == "_work":
            top = rel.split(os.sep)[0]
            if top == "_tool":
                return "inside _work/_tool"
            if rel in WORK_KEEP:
                return f"_work/{rel} itself is kept"
        return None
    return "outside the allowed roots"


def safe_delete(path: str, roots: Iterable[str], allowed_files: Iterable[str] = (),
                apply: bool = False, log: Callable[[str], None] = _log) -> tuple[bool, str]:
    """The only function that deletes anything. Returns (ok, what happened)."""
    roots = list(roots)
    reason = check_path(path, roots, allowed_files)
    if reason:
        log(f"refused {path}: {reason}")
        return False, f"refused: {reason}"
    if not apply:
        return True, "would remove"
    try:
        if os.path.islink(path) or not os.path.isdir(path):
            os.unlink(path)  # a symlink is unlinked, its target is never followed
        else:
            shutil.rmtree(path)  # rmtree removes inner symlinks without following them
    except FileNotFoundError:
        return True, "already gone"
    except OSError as exc:
        log(f"error removing {path}: {exc}")
        return False, f"error: {exc}"
    log(f"removed {path}")
    return True, "removed"


def truncate_log(path: str, allowed_files: Iterable[str], apply: bool,
                 limit: int = LOG_LIMIT, keep: int = LOG_KEEP,
                 log: Callable[[str], None] = _log) -> dict | None:
    """Keep the last `keep` bytes of a log larger than `limit`."""
    try:
        size = os.lstat(path).st_size
    except OSError:
        return None
    if size <= limit:
        return None
    item = {"path": path, "bytes": size, "reclaim": size - keep}
    if os.path.islink(path):
        reason = "symlink"
    elif os.path.realpath(path) not in {os.path.realpath(f) for f in allowed_files}:
        reason = "not an allowed log file"
    else:
        reason = None
    if reason:
        log(f"refused {path}: {reason}")
        item["action"] = f"refused: {reason}"
        item["reclaim"] = 0
        return item
    if not apply:
        item["action"] = "would truncate"
        return item
    try:
        with open(path, "r+b") as fh:
            fh.seek(size - keep)
            tail = fh.read()
            nl = tail.find(b"\n")
            if 0 <= nl < len(tail) - 1:
                tail = tail[nl + 1:]  # start on a whole line
            fh.seek(0)
            fh.write(tail)
            fh.truncate()
        item["reclaim"] = size - len(tail)
        item["action"] = "truncated"
        log(f"truncated {path} to {fmt_bytes(len(tail))}")
    except OSError as exc:
        item["action"] = f"error: {exc}"
        item["reclaim"] = 0
    return item


# --------------------------------------------------------------------------
# Host checks (report only)
# --------------------------------------------------------------------------

def parse_ac_sleep(text: str) -> int | None:
    """AC Power `sleep` minutes from `pmset -g custom` (0 means never)."""
    section = None
    for line in text.splitlines():
        if line.strip().endswith(":") and not line.startswith(" "):
            section = line.strip()[:-1]
            continue
        m = re.match(r"^\s*sleep\s+(\d+)", line)
        if m and section == "AC Power":
            return int(m.group(1))
    return None


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
        for vm in obj if isinstance(obj, list) else [obj]:
            if isinstance(vm, dict):
                vms.append(vm)
    return vms


def host_report(runner: Callable, system: str) -> dict:
    rep: dict = {"disks": [], "swap": None, "ac_sleep": None, "warnings": []}
    for path in ("/", "/Volumes/NAS"):
        if os.path.exists(path):
            du = shutil.disk_usage(path)
            rep["disks"].append({"path": path, "total": du.total, "free": du.free})
    if system == "Darwin":
        swap = runner(["sysctl", "-n", "vm.swapusage"])
        rep["swap"] = swap.strip() if swap else None
    elif os.path.exists("/proc/meminfo"):
        with open("/proc/meminfo", encoding="utf-8") as fh:
            vals = {k: v.split()[0] for k, _, v in (ln.partition(":") for ln in fh) if v.strip()}
        total, free = int(vals.get("SwapTotal", 0)) * 1024, int(vals.get("SwapFree", 0)) * 1024
        rep["swap"] = f"total = {fmt_bytes(total)} used = {fmt_bytes(total - free)}"
    pm = runner(["pmset", "-g", "custom"])
    if pm:
        rep["ac_sleep"] = parse_ac_sleep(pm)
        if rep["ac_sleep"]:
            rep["warnings"].append(f"WARNING: AC sleep is {rep['ac_sleep']} min; runners go offline "
                                   "when the Mac sleeps (sudo pmset -c sleep 0)")
    return rep


# --------------------------------------------------------------------------
# Caches
# --------------------------------------------------------------------------

BREW_ENV = {"HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ANALYTICS": "1",
            "HOMEBREW_NO_INSTALL_CLEANUP": "1"}


def _brew_dry_free(text: str) -> int:
    m = re.search(r"approximately ([\d.]+)\s*([KMGT]?B)", text)
    if not m:
        return 0
    mult = {"B": 1, "KB": 1024, "MB": MB, "GB": GB, "TB": GB * 1024}[m.group(2)]
    return int(float(m.group(1)) * mult)


def clean_caches(apply: bool, runner: Callable, log: Callable[[str], None]) -> list[dict]:
    caches = []
    gocache = (runner(["go", "env", "GOCACHE"]) or "").strip()
    if gocache and os.path.isdir(gocache) and "pkg/mod" not in gocache:
        size = dir_size(gocache, runner)
        item = {"name": "Go build cache", "path": gocache, "bytes": size,
                "threshold": GO_CACHE_THRESHOLD, "reclaim": 0, "action": "kept (under threshold)"}
        if size > GO_CACHE_THRESHOLD:
            if apply:
                ok = runner(["go", "clean", "-cache"], timeout=1800) is not None
                after = dir_size(gocache, runner)
                item.update(reclaim=max(0, size - after), action="cleaned" if ok else "error: go clean failed")
                log(f"go clean -cache: {item['action']}")
            else:
                item.update(reclaim=size, action="would run go clean -cache")
        caches.append(item)
    brew_cache = (runner(["brew", "--cache"], env=BREW_ENV) or "").strip()
    if brew_cache:
        size = dir_size(brew_cache, runner) if os.path.isdir(brew_cache) else 0
        item = {"name": "Homebrew", "path": brew_cache, "bytes": size, "threshold": BREW_THRESHOLD,
                "reclaim": 0, "action": "kept (under threshold)"}
        if size > BREW_THRESHOLD:
            if apply:
                ok = runner(["brew", "cleanup", "--prune=14"], timeout=1800, env=BREW_ENV) is not None
                after = dir_size(brew_cache, runner) if os.path.isdir(brew_cache) else 0
                item.update(reclaim=max(0, size - after), action="cleaned" if ok else "error: brew cleanup failed")
                log(f"brew cleanup --prune=14: {item['action']}")
            else:
                dry = runner(["brew", "cleanup", "--prune=14", "-n"], timeout=600, env=BREW_ENV) or ""
                item.update(reclaim=_brew_dry_free(dry), action="would run brew cleanup --prune=14")
        caches.append(item)
    return caches


# --------------------------------------------------------------------------
# Lima VMs
# --------------------------------------------------------------------------

def vm_script(apply: bool, work_days: int, log_days: int, actions_days: int = ACTIONS_DAYS) -> str:
    """One POSIX sh script run as root inside a VM. In dry-run it only lists
    candidates with their `du -sk` size; with apply it also removes them,
    vacuums journald, prunes old docker objects and runs fstrim.

    Output lines: SKIPVM <why> | SKIP <dir> busy | RUNNER <dir> |
    CAND <kb> <kind> <path> | REFUSE <path> | ERROR <path> | NOTE <text> | DONE.
    The literal process names are split so ps never matches this script."""
    wd, ld, ad = int(work_days), int(log_days), int(actions_days)
    remove_link = '    rm -f -- "$p" || echo "ERROR $p"\n' if apply else ""
    remove_tree = '  rm -rf --one-file-system -- "$p" || echo "ERROR $p"\n' if apply else ""
    lines = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "RW=Runner; RW=\"$RW.Worker\"",
        "PS=$(ps -eww -o pid,ppid,etime,cmd 2>/dev/null) || { echo 'SKIPVM ps failed'; exit 0; }",
        'case "$PS" in *"$RW"*) echo "SKIPVM $RW running"; exit 0;; esac',
        "for pid in $(ps -e -o pid=,comm= | awk '$2==\"make\"{print $1}'); do",
        '  cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null) || continue',
        '  case "$cwd" in */_work/*) echo "SKIPVM make running in $cwd"; exit 0;; esac',
        "done",
        'fresh() { [ -n "$(find "$1" -maxdepth 1 -mtime -"$2" -print 2>/dev/null | head -n 1)" ]; }',
        "act() {",
        '  kind=$1; p=$2',
        '  if [ -L "$p" ]; then',
        '    echo "CAND 0 $kind $p"',
        remove_link.rstrip("\n") if remove_link else "    :",
        "    return",
        "  fi",
        '  r=$(readlink -f -- "$p") || { echo "REFUSE $p"; return; }',
        '  case "$r" in',
        '    "$W"/_tool|"$W"/_tool/*|"$W"/_temp|"$W"/_actions|"$W"/_PipelineMapping) echo "REFUSE $p"; return;;',
        '    "$W"/?*|"$G"/?*) ;;',
        '    *) echo "REFUSE $p"; return;;',
        "  esac",
        '  kb=$(du -sxk -- "$p" 2>/dev/null | cut -f1)',
        '  echo "CAND ${kb:-0} $kind $p"',
        remove_tree.rstrip("\n") if remove_tree else "  :",
        "}",
        "find / -xdev -maxdepth 4 -name .runner -type f 2>/dev/null | while IFS= read -r f; do",
        '  d=$(dirname -- "$f")',
        '  case "$PS" in *"$d/_work/"*) echo "SKIP $d busy"; continue;; esac',
        '  echo "RUNNER $d"',
        '  W=$(readlink -f -- "$d/_work" 2>/dev/null || echo "$d/_work")',
        '  G=$(readlink -f -- "$d/_diag" 2>/dev/null || echo "$d/_diag")',
        '  if [ -d "$d/_work/_temp" ]; then',
        '    find "$d/_work/_temp" -mindepth 1 -maxdepth 1 -print | while IFS= read -r c; do act temp "$c"; done',
        "  fi",
        '  if [ -d "$d/_work" ]; then',
        f'    find "$d/_work" -mindepth 1 -maxdepth 1 -type d ! -name _tool ! -name _actions ! -name _temp '
        f'! -name _PipelineMapping -mtime +{wd} -print | while IFS= read -r c; do',
        f'      fresh "$c" {wd + 1} || act checkout "$c"',
        "    done",
        "  fi",
        '  if [ -d "$d/_work/_actions" ]; then',
        f'    find "$d/_work/_actions" -mindepth 1 -maxdepth 1 -mtime +{ad} -print | while IFS= read -r c; do',
        f'      fresh "$c" {ad + 1} || act actions "$c"',
        "    done",
        "  fi",
        '  if [ -d "$d/_diag" ]; then',
        f'    find "$d/_diag" -mindepth 1 -maxdepth 1 -type f -name \'*.log\' -mtime +{ld} -print '
        '| while IFS= read -r c; do act diag-log "$c"; done',
        "  fi",
        "done",
    ]
    if apply:
        lines += [
            "if command -v journalctl >/dev/null 2>&1; then",
            "  journalctl --vacuum-time=7d 2>&1 | tail -n 1 | sed 's/^/NOTE journal: /'",
            "fi",
            "if command -v docker >/dev/null 2>&1; then",
            "  docker system prune -f --filter until=72h 2>&1 | tail -n 1 | sed 's/^/NOTE docker: /'",
            "fi",
            "if command -v fstrim >/dev/null 2>&1; then",
            "  fstrim -av 2>&1 | sed 's/^/NOTE fstrim: /'",
            "fi",
        ]
    else:
        lines += [
            "if command -v journalctl >/dev/null 2>&1; then",
            "  echo \"NOTE journal: $(journalctl --disk-usage 2>/dev/null)\"",
            "fi",
            "if command -v docker >/dev/null 2>&1; then",
            "  docker system df 2>/dev/null | sed 's/^/NOTE docker: /'",
            "fi",
            "echo 'NOTE journal vacuum, old docker objects and disk trim are handled only with --apply'",
        ]
    lines += ["echo DONE", "exit 0"]
    return "\n".join(lines) + "\n"


def parse_vm_output(text: str) -> dict:
    res: dict = {"skipped": None, "busy_runners": [], "runners": [], "items": [],
                 "notes": [], "refused": [], "errors": [], "done": False}
    for line in text.splitlines():
        tag, _, rest = line.partition(" ")
        if tag == "SKIPVM":
            res["skipped"] = rest
        elif tag == "SKIP":
            res["busy_runners"].append(rest.rsplit(" ", 1)[0])
        elif tag == "RUNNER":
            res["runners"].append(rest)
        elif tag == "CAND":
            parts = rest.split(" ", 2)
            if len(parts) == 3 and parts[0].isdigit():
                res["items"].append({"bytes": int(parts[0]) * 1024, "kind": parts[1], "path": parts[2]})
        elif tag == "REFUSE":
            res["refused"].append(rest)
        elif tag == "ERROR":
            res["errors"].append(rest)
        elif tag == "NOTE":
            res["notes"].append(rest)
        elif tag == "DONE":
            res["done"] = True
    return res


def lima_vms(apply: bool, run_inside: bool, work_days: int, log_days: int,
             runner: Callable, log: Callable[[str], None]) -> list[dict]:
    out = runner(["limactl", "list", "--json"], timeout=30)
    if out is None:
        return []
    lima_home = os.environ.get("LIMA_HOME") or os.path.expanduser("~/.lima")
    vms = []
    for vm in parse_lima(out):
        name = str(vm.get("name") or "")
        if not name:
            continue
        vdir = vm.get("dir") or os.path.join(lima_home, name)
        diff = os.path.join(vdir, "diffdisk")
        try:
            allocated = _alloc(os.lstat(diff))
        except OSError:
            allocated = None
        info = {"name": name, "status": vm.get("status"), "diffdisk_bytes": allocated,
                "disk_bytes": vm.get("disk"), "items": [], "reclaim": 0}
        vms.append(info)
        if not run_inside or vm.get("status") != "Running":
            continue
        script = vm_script(apply, work_days, log_days)
        text = runner(["limactl", "shell", "--workdir", "/", name, "--", "sudo", "-n", "sh", "-c", script],
                      timeout=VM_TIMEOUT)
        if text is None:
            info["error"] = "limactl shell failed (VM unreachable or sudo needs a password)"
            continue
        res = parse_vm_output(text)
        info.update(skipped=res["skipped"], busy_runners=res["busy_runners"], runners=res["runners"],
                    items=res["items"], notes=res["notes"], refused=res["refused"], errors=res["errors"])
        info["reclaim"] = sum(i["bytes"] for i in res["items"])
        if apply:
            for i in res["items"]:
                log(f"{name}: removed {i['path']}")
    return vms


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def acquire_lock(path: str):
    """Exclusive non-blocking flock, or None if another run holds it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fh = open(path, "a+", encoding="utf-8")  # held open for the whole run
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def clean_runner(rdir: str, opts, list_procs: Callable, now: float,
                 log: Callable[[str], None]) -> dict:
    entry: dict = {"dir": rdir, "status": "idle", "items": [], "reclaim": 0}
    busy = runner_busy(rdir, list_procs(), now)
    if busy:
        entry.update(status="busy", reason=busy)
        return entry
    cands = runner_candidates(rdir, now, opts.work_days, opts.log_days)
    if opts.apply and cands:
        busy = runner_busy(rdir, list_procs(), now)  # a job may have started meanwhile
        if busy:
            entry.update(status="busy", reason=busy)
            return entry
    roots = runner_roots(rdir)
    for c in cands:
        ok, what = safe_delete(c["path"], roots, apply=opts.apply, log=log)
        c["action"] = what
        if ok and what != "already gone":
            entry["reclaim"] += c["bytes"]
        entry["items"].append(c)
    return entry


def run_cleanup(opts, list_procs: Callable = list_processes, runner: Callable = _run,
                now: float | None = None, log: Callable[[str], None] = _log,
                system: str | None = None) -> dict:
    now = time.time() if now is None else now
    system = system or platform.system()
    result: dict = {"apply": opts.apply, "host": platform.node(),
                    "started": datetime.fromtimestamp(now).isoformat(timespec="seconds")}
    result.update(host_report(runner, system))
    result["runners"] = [clean_runner(d, opts, list_procs, now, log)
                         for d in discover_runners(opts.runner_root, opts.depth)]
    allowed_logs = sorted({f for g in LOG_GLOBS for f in glob.glob(os.path.join(opts.logs_dir, g))})
    result["logs"] = [i for i in (truncate_log(f, allowed_logs, opts.apply, log=log) for f in allowed_logs) if i]
    result["caches"] = clean_caches(opts.apply, runner, log) if opts.caches else []
    result["vms"] = lima_vms(opts.apply, opts.vms, opts.work_days, opts.log_days, runner, log)
    total = sum(r["reclaim"] for r in result["runners"])
    total += sum(i.get("reclaim", 0) for i in result["logs"])
    total += sum(c.get("reclaim", 0) for c in result["caches"])
    total += sum(v.get("reclaim", 0) for v in result["vms"])
    result["total_bytes"] = total
    errors = [i["path"] for r in result["runners"] for i in r["items"] if i["action"].startswith("error")]
    errors += [v["name"] for v in result["vms"] if v.get("error") or v.get("errors")]
    result["errors"] = errors
    return result


def render_text(res: dict) -> str:
    verb = "removed" if res["apply"] else "would remove"
    out = [f"runner-cleanup on {res['host']} at {res['started']} "
           f"({'APPLY' if res['apply'] else 'dry run; pass --apply to delete'})"]
    for d in res["disks"]:
        out.append(f"Disk {d['path']}: {fmt_bytes(d['free'])} free of {fmt_bytes(d['total'])}")
    if res["swap"]:
        out.append(f"Swap: {res['swap']}")
    if res["ac_sleep"] is not None:
        out.append(f"AC sleep: {res['ac_sleep']}")
    out += res["warnings"]
    out.append(f"Runners ({len(res['runners'])}):")
    for r in res["runners"]:
        if r["status"] == "busy":
            out.append(f"  {r['dir']}: skipped, busy ({r['reason']})")
            continue
        out.append(f"  {r['dir']}: idle, {len(r['items'])} item(s), {fmt_bytes(r['reclaim'])}")
        for i in r["items"]:
            rel = os.path.relpath(i["path"], r["dir"])
            out.append(f"    {i['action']:<14} {fmt_bytes(i['bytes']):>9}  {rel}")
    for i in res["logs"]:
        out.append(f"Log {i['path']}: {fmt_bytes(i['bytes'])}, {i['action']}")
    for c in res["caches"]:
        out.append(f"{c['name']} {c['path']}: {fmt_bytes(c['bytes'])} "
                   f"(threshold {fmt_bytes(c['threshold'])}), {c['action']}")
    for v in res["vms"]:
        disk = f"diffdisk {fmt_bytes(v['diffdisk_bytes'])} allocated of {fmt_bytes(v['disk_bytes'])}"
        out.append(f"VM {v['name']} ({v['status']}): {disk}")
        if v.get("error"):
            out.append(f"  error: {v['error']}")
        if v.get("skipped"):
            out.append(f"  skipped: {v['skipped']}")
        for d in v.get("busy_runners", []):
            out.append(f"  {d}: skipped, busy")
        for i in v["items"]:
            out.append(f"  {verb:<14} {fmt_bytes(i['bytes']):>9}  {i['path']}")
        for p in v.get("refused", []):
            out.append(f"  refused        {p}")
        for n in v.get("notes", []):
            out.append(f"  {n}")
    if res["errors"]:
        out.append(f"Errors: {len(res['errors'])} (see log lines above)")
    total = fmt_bytes(res["total_bytes"])
    out.append(f"Freed {total}" if res["apply"] else f"Would free {total}")
    return "\n".join(out)


def launchd_plist(python: str, script: str, extra: list[str], home: str) -> str:
    args = list(extra)
    if "--dry-run" not in args and "--apply" not in args:
        args.insert(0, "--apply")
    log = os.path.join(home, "Library", "Logs", "runner-cleanup.log")
    plist = {
        "Label": LABEL,
        "ProgramArguments": [python, script, *args],
        "StartCalendarInterval": {"Hour": 4, "Minute": 30},
        "RunAtLoad": False,
        "LowPriorityIO": True,
        "Nice": 10,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }
    return plistlib.dumps(plist).decode()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="actually delete (default is a dry run)")
    p.add_argument("--dry-run", action="store_true", help="explicit dry run (the default)")
    p.add_argument("--runner-root", action="append", metavar="DIR",
                   help="where to look for runner dirs (repeatable, default ~)")
    p.add_argument("--depth", type=int, default=4, help="search depth below each root (default 4)")
    p.add_argument("--work-days", type=int, default=3, help="checkout age in days (default 3)")
    p.add_argument("--log-days", type=int, default=7, help="_diag log age in days (default 7)")
    p.add_argument("--vms", dest="vms", action="store_true", default=True, help="clean inside Lima VMs (default)")
    p.add_argument("--no-vms", dest="vms", action="store_false", help="skip work inside Lima VMs")
    p.add_argument("--no-caches", dest="caches", action="store_false", default=True,
                   help="skip Go/Homebrew caches")
    p.add_argument("--json", action="store_true", help="print a JSON summary instead of the report")
    p.add_argument("--logs-dir", default=LOGS_DIR, help=argparse.SUPPRESS)
    p.add_argument("--lock-file", default=LOCK_FILE, help=argparse.SUPPRESS)
    p.add_argument("--print-launchd", action="store_true",
                   help="print a LaunchAgent plist (daily 04:30, --apply; run a dry run by hand first)")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["launchd"]:
        argv = ["--print-launchd", *argv[1:]]
    parser = build_parser()
    if "--print-launchd" in argv:
        extra = [a for a in argv if a != "--print-launchd"]
        parser.parse_args(extra)  # validate the pass-through flags
        print(launchd_plist(sys.executable, os.path.abspath(__file__), extra, os.path.expanduser("~")), end="")
        print("# Run a dry run first: python3 runner_cleanup.py", file=sys.stderr)
        return 0
    opts = parser.parse_args(argv)
    if opts.apply and opts.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")
    opts.runner_root = opts.runner_root or ["~"]
    lock = acquire_lock(opts.lock_file)
    if lock is None:
        print("runner-cleanup: another run holds the lock; skipping", file=sys.stderr)
        return 0
    try:
        res = run_cleanup(opts)
    finally:
        lock.close()
    print(json.dumps(res, indent=2, default=str) if opts.json else render_text(res))
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
