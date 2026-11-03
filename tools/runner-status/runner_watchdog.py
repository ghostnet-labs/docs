#!/usr/bin/env python3
"""Runner watchdog: finds out why a self-hosted runner is offline and brings
it back when that is safe.

Runs on each runner host (Mac Studio, MacBook Pro) every 2 minutes from a
LaunchAgent. It reads the status page's /api/state to learn which runners
GitHub sees as offline (no GitHub token needed here), works out the cause on
this machine, and writes the cause and its last action to
~/.config/runner-status/watchdog.json. The status page shows that next to
each offline runner.

Causes it tells apart, and what it does about each:

  maintenance   listed in maintenance.json (e.g. the one-job runner
                conversion): nothing, shown as "draining"
  vm-stopped    the Lima VM holding the runner is not running: limactl start
  service-dead  the runner's launchd or systemd service is not running:
                restart it
  registration  the runner log says its registration was removed or its
                credentials were refused: nothing (needs re-registering)
  disk-full     less than 2 GB free on the Mac or in the VM: nothing (run the
                cleanup)
  network       github.com cannot be reached from the Mac or the VM: nothing
  no-service    no service for that runner exists here (one-job slot not
                refilled, or removed by hand): runs "jit_command" only if
                configured, else nothing
  unknown       the service runs but GitHub still sees it offline: restart

Restarts back off (2, 4, 8 minutes) and stop after 3 tries in an hour; the
page then says auto-recovery gave up and why.

  python3 runner_watchdog.py --machine "Mac Studio"            # one pass
  python3 runner_watchdog.py --machine "Mac Studio" --dry-run  # diagnose only
  python3 runner_watchdog.py launchd --machine "MacBook Pro" --page http://studio.local:8090
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runner_status as rs  # noqa: E402

STATE_DIR = os.path.expanduser("~/.config/runner-status")
REPORT_FILE = os.path.join(STATE_DIR, "watchdog.json")
ATTEMPTS_FILE = os.path.join(STATE_DIR, "watchdog-attempts.json")
MAINTENANCE_FILE = os.path.join(STATE_DIR, "maintenance.json")
LOCK_FILE = os.path.join(STATE_DIR, "watchdog.lock")
DRIFT_FILE = os.path.join(STATE_DIR, "watchdog-drift.json")
DRIFT_EVERY_SECONDS = 3600
JIT_PREFIX = "com.ghostnet.jit."
MAX_TRIES_PER_HOUR = 3
BACKOFF_MINUTES = (2, 4, 8)
MIN_FREE_BYTES = 2 * 1024 ** 3
REPORT_MAX_AGE_SECONDS = 600  # the page ignores an older report

REGISTRATION_RX = re.compile(
    r"(?i)registration .*(deleted|removed|not found)|runner .*(deleted|removed) from|"
    r"401|unauthori[sz]ed|invalid (token|credential)|access denied|"
    r"failed to (create|refresh) (a )?session")
DISK_RX = re.compile(r"(?i)no space left on device")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Host:
    """Everything the watchdog runs on the machine. Tests replace it."""

    def run(self, cmd: list[str], timeout: float = 30) -> tuple[int, str]:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                                 check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, str(exc)
        return out.returncode, out.stdout + out.stderr

    def vm(self, vm: str, script: str, timeout: float = 30) -> tuple[int, str]:
        return self.run(["limactl", "shell", vm, "--", "sh", "-c", script], timeout)

    def vm_stdin(self, vm: str, role: str, script: str) -> tuple[int, str]:
        try:
            out = subprocess.run(["limactl", "shell", vm, "--", "bash", "-s", role],
                                 input=script, capture_output=True, text=True, timeout=60,
                                 check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, str(exc)
        return out.returncode, out.stdout

    def free_bytes(self, path: str = "/") -> int | None:
        try:
            return os.statvfs(path).f_bavail * os.statvfs(path).f_frsize
        except OSError:
            return None

    def reachable(self, url: str = "https://github.com") -> bool:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10):
                return True
        except urllib.error.HTTPError:
            return True  # an HTTP answer still means the network works
        except (urllib.error.URLError, OSError):
            return False

    def page_state(self, page: str) -> dict:
        with urllib.request.urlopen(page.rstrip("/") + "/api/state", timeout=10) as resp:
            return json.loads(resp.read().decode())

    def uid(self) -> int:
        return os.getuid()


def load_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)  # the page never reads a half-written file


def maintenance_reason(name: str, entries: list, now: float) -> str | None:
    """Reason a runner is intentionally down, from maintenance.json entries
    {"runner": regex, "reason": text, "until": ISO time (optional)}."""
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict) or not e.get("runner"):
            continue
        until = rs.parse_ts(e.get("until"))
        if until is not None and until.timestamp() < now:
            continue
        try:
            if re.search(e["runner"], name):
                return str(e.get("reason") or "maintenance")
        except re.error:
            continue
    return None


def may_act(attempts: list[float], now: float) -> tuple[bool, str]:
    """Backoff: 2, 4, 8 minutes between tries, at most 3 tries an hour."""
    recent = [t for t in attempts if t > now - 3600]
    if len(recent) >= MAX_TRIES_PER_HOUR:
        return False, (f"gave up: {MAX_TRIES_PER_HOUR} tries this hour did not bring it back; "
                       "it tries again when the oldest try is an hour old")
    if recent:
        wait = BACKOFF_MINUTES[min(len(recent), len(BACKOFF_MINUTES)) - 1] * 60
        if now - recent[-1] < wait:
            return False, f"waiting {int((wait - (now - recent[-1])) // 60) + 1} min before the next try"
    return True, ""


def classify_log(text: str) -> str | None:
    if DISK_RX.search(text):
        return "disk-full"
    if REGISTRATION_RX.search(text):
        return "registration"
    return None


class Watchdog:
    def __init__(self, cfg: dict, machine: str, host: Host, dry_run: bool = False,
                 jit_command: list[str] | None = None):
        self.cfg = cfg
        self.machine = machine
        self.host = host
        self.dry_run = dry_run
        self.jit_command = jit_command
        mcfg = next((m for m in cfg["machines"] if m["name"] == machine), {})
        self.jit_slots = list(mcfg.get("jit_slots") or [])
        self.vm_roles = dict(mcfg.get("vm_roles") or {})
        self.drift_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "ci-hosts", "verify-vm.sh")
        self.done: set[tuple] = set()  # commands already run in this pass
        self.vm_patterns = {vm: re.compile(p) for vm, p in (mcfg.get("vms") or {}).items()}
        self.runner_rx = re.compile(mcfg.get("runner_pattern", "$^"))

    # ---- facts -------------------------------------------------------------

    def vms(self) -> dict[str, str]:
        code, out = self.host.run(["limactl", "list", "--json"], timeout=15)
        return {v["name"]: v.get("status") or "?" for v in rs.parse_lima(out)} if code == 0 else {}

    def launchd_services(self) -> dict[str, dict]:
        code, out = self.host.run(["launchctl", "list"], timeout=10)
        return {s["label"]: s for s in rs.parse_launchctl(out)} if code == 0 else {}

    def vm_units(self, vm: str) -> dict[str, str]:
        code, out = self.host.vm(vm, "systemctl list-units --all --plain --no-legend "
                                     "'actions.runner.*' 2>/dev/null")
        units = {}
        for line in out.splitlines() if code == 0 else []:
            parts = line.split()
            if len(parts) >= 4 and parts[0].startswith("actions.runner."):
                units[parts[0]] = parts[2]  # unit -> ACTIVE (active/inactive/failed)
        return units

    # ---- one runner --------------------------------------------------------

    def diagnose(self, name: str, ctx: dict) -> dict:
        """Return {"cause", "detail", "action": [cmd] or None, "where"}."""
        reason = maintenance_reason(name, ctx["maintenance"], ctx["now"])
        if reason:
            return {"cause": "maintenance", "detail": f"draining: {reason}", "action": None}
        if not ctx["network"]:
            return {"cause": "network", "detail": "this Mac cannot reach github.com",
                    "action": None}
        if (ctx["free"] or MIN_FREE_BYTES) < MIN_FREE_BYTES:
            return {"cause": "disk-full", "detail": f"only {rs.fmt_bytes(ctx['free'])} free on "
                    "this Mac; run runner_cleanup.py --apply", "action": None}
        vm = next((v for v, rx in self.vm_patterns.items() if rx.search(name)), None)
        if vm:
            return self.diagnose_vm(name, vm, ctx)
        return self.diagnose_launchd(name, ctx)

    def diagnose_vm(self, name: str, vm: str, ctx: dict) -> dict:
        status = ctx["vms"].get(vm)
        if status is None:
            return {"cause": "no-service", "detail": f"VM {vm} does not exist on this Mac",
                    "action": None}
        if status != "Running":
            return {"cause": "vm-stopped", "detail": f"VM {vm} is {status}",
                    "action": ["limactl", "start", vm]}
        units = ctx["units"].setdefault(vm, self.vm_units(vm))
        unit = next((u for u in units if name in u), None)
        if unit is None:
            return self.no_service(name, f"no actions.runner service for {name} in VM {vm}")
        code, log = self.host.vm(vm, f"journalctl -u '{unit}' -n 40 --no-pager 2>&1; "
                                     "df -Pk / | tail -1")
        kind = classify_log(log)
        free = re.search(r"\s(\d+)\s+\d+%\s+/\s*$", log)
        if free and int(free.group(1)) * 1024 < MIN_FREE_BYTES:
            kind = "disk-full"
        if kind == "registration":
            return {"cause": "registration", "detail": f"{unit} log says the registration was "
                    "removed or its credentials were refused; it needs re-registering",
                    "action": None}
        if kind == "disk-full":
            return {"cause": "disk-full", "detail": f"VM {vm} is out of disk; run "
                    "runner_cleanup.py --apply", "action": None}
        code, _ = self.host.vm(vm, "curl -sfI --max-time 10 https://github.com >/dev/null")
        if code != 0:
            return {"cause": "network", "detail": f"VM {vm} cannot reach github.com; "
                    f"restarting the VM", "action": ["limactl", "restart", vm]}
        state = units[unit]
        cause = "service-dead" if state != "active" else "unknown"
        detail = (f"{unit} is {state}" if state != "active" else
                  f"{unit} runs but GitHub sees it offline")
        return {"cause": cause, "detail": detail,
                "action": ["limactl", "shell", vm, "--", "sudo", "systemctl", "restart", unit]}

    def diagnose_launchd(self, name: str, ctx: dict) -> dict:
        label = next((lbl for lbl in ctx["services"] if lbl.endswith("." + name)
                      or name in lbl), None)
        if label is None:
            return self.no_service(name, f"no actions.runner launchd service for {name}")
        svc = ctx["services"][label]
        action = ["launchctl", "kickstart", "-k", f"gui/{self.host.uid()}/{label}"]
        log = self.runner_log(label)
        kind = classify_log(log)
        if kind == "registration":
            return {"cause": "registration", "detail": f"{name}'s log says the registration was "
                    "removed or its credentials were refused; it needs re-registering",
                    "action": None}
        if not svc.get("running"):
            return {"cause": "service-dead",
                    "detail": f"{label} is not running (last exit {svc.get('exit')})",
                    "action": action}
        return {"cause": "unknown", "detail": f"{label} runs but GitHub sees it offline",
                "action": action}

    def runner_log(self, label: str) -> str:
        """Tail of the runner's newest _diag log, found from its plist."""
        plist = os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist")
        try:
            with open(plist, encoding="utf-8") as fh:
                m = re.search(r"<string>([^<]*)/runsvc\.sh</string>", fh.read())
        except OSError:
            return ""
        if not m:
            return ""
        diag = os.path.join(m.group(1), "_diag")
        try:
            logs = sorted((os.path.join(diag, f) for f in os.listdir(diag)
                           if f.startswith("Runner_")), key=os.path.getmtime)
            with open(logs[-1], "rb") as fh:
                fh.seek(max(0, os.path.getsize(logs[-1]) - 16384))
                return fh.read().decode(errors="replace")
        except (OSError, IndexError):
            return ""

    def no_service(self, name: str, detail: str) -> dict:
        if self.jit_command:
            return {"cause": "no-service", "detail": detail + "; refilling the one-job slot",
                    "action": [*self.jit_command, name]}
        return {"cause": "no-service", "detail": detail, "action": None}

    # ---- pass --------------------------------------------------------------

    def offline_runners(self, state: dict) -> list[str]:
        names = []
        for m in state.get("machines") or []:
            for r in m.get("runners") or []:
                if r.get("status") == "offline" and (
                        m.get("name") == self.machine or self.runner_rx.search(r.get("name") or "")):
                    names.append(r["name"])
        return sorted(set(names))

    def check_jit_slots(self, ctx: dict, attempts: dict, now: float) -> dict:
        """One-job runners: each slot is a Mac LaunchAgent (com.ghostnet.jit.<slot>)
        that mints a config, runs one job in a VM and loops. If that agent is
        not running, kickstart it; if its VM is stopped, start the VM. The
        watchdog never mints tokens or registers runners itself."""
        out = {}
        code, text = self.host.run(["launchctl", "list"], timeout=10)
        jobs = {}
        for line in text.splitlines() if code == 0 else []:
            parts = line.split("\t") if "\t" in line else line.split()
            if len(parts) == 3 and parts[2].startswith(JIT_PREFIX):
                jobs[parts[2][len(JIT_PREFIX):]] = parts[0].strip().isdigit()
        started: set[str] = set()
        for slot in self.jit_slots:
            reason = maintenance_reason(slot, ctx["maintenance"], now)
            if reason:
                out[slot] = {"cause": "maintenance", "detail": f"draining: {reason}",
                             "action": None, "result": None, "at": utcnow_iso()}
                continue
            vm = next((v for v, rx in self.vm_patterns.items() if rx.search(slot)), None)
            status = ctx["vms"].get(vm) if vm else None
            if vm and status is not None and status != "Running":
                diag = {"cause": "vm-stopped", "detail": f"VM {vm} is {status}",
                        "action": None if vm in started else ["limactl", "start", vm]}
                started.add(vm)
                out[slot] = self.act(f"vm:{vm}", diag, attempts, now)
            elif slot not in jobs:
                out[slot] = {"cause": "no-service", "at": utcnow_iso(), "action": None,
                             "result": None, "detail": f"LaunchAgent {JIT_PREFIX}{slot} is not "
                             "loaded; the watchdog never registers runners, so load it by hand"}
            elif not jobs[slot]:
                diag = {"cause": "service-dead", "detail": f"{JIT_PREFIX}{slot} has no process",
                        "action": ["launchctl", "kickstart", "-k",
                                   f"gui/{self.host.uid()}/{JIT_PREFIX}{slot}"]}
                out[slot] = self.act(f"jit:{slot}", diag, attempts, now)
        return out

    def check_drift(self, vms: dict, now: float) -> dict | None:
        """Run tools/ci-hosts/verify-vm.sh inside each running VM (hourly) and
        return {vm: [problems]}. None when it is not due yet."""
        state = load_json(DRIFT_FILE, {})
        if not self.vm_roles or now - state.get("at", 0) < DRIFT_EVERY_SECONDS:
            return state.get("drift") if isinstance(state.get("drift"), dict) else None
        try:
            with open(self.drift_script, encoding="utf-8") as fh:
                script = fh.read()
        except OSError:
            return None
        drift = {}
        for vm, role in sorted(self.vm_roles.items()):
            if vms.get(vm) != "Running":
                continue
            code, out = self.host.vm_stdin(vm, role, script)
            drift[vm] = [ln for ln in out.splitlines() if ln.startswith("FAIL:")][:8] \
                if code == 0 else [f"FAIL: drift check could not run (exit {code})"]
        if not self.dry_run:
            write_json(DRIFT_FILE, {"at": now, "drift": drift})
        return drift

    def run_once(self) -> dict:
        now = time.time()
        report: dict = {"machine": self.machine, "checked_at": utcnow_iso(), "runners": {},
                        "dry_run": self.dry_run}
        attempts = load_json(ATTEMPTS_FILE, {})
        try:
            state = self.host.page_state(self.cfg.get("watchdog_page", "http://127.0.0.1:8090"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            report["error"] = f"status page unreachable ({exc}); only VMs were checked"
            state = None
        vms = self.vms()
        if state is None:
            # Without the page, still bring back a stopped runner VM.
            for vm, status in vms.items():
                if vm in self.vm_patterns and status != "Running":
                    report["runners"][f"VM {vm}"] = self.act(
                        f"vm:{vm}", {"cause": "vm-stopped", "detail": f"VM {vm} is {status}",
                                     "action": ["limactl", "start", vm]}, attempts, now)
        else:
            offline = self.offline_runners(state)
            maint = load_json(MAINTENANCE_FILE, {})
            ctx = {"now": now, "vms": vms, "units": {}, "services": self.launchd_services(),
                   "maintenance": maint.get("entries", []) if isinstance(maint, dict) else [],
                   "network": self.host.reachable() if offline else True,
                   "free": self.host.free_bytes("/")}
            started_vms: set[str] = set()
            for name in offline:
                diag = self.diagnose(name, ctx)
                action = diag.get("action") or []
                if action[:2] == ["limactl", "start"] and action[2] in started_vms:
                    diag["action"] = None  # one start per VM covers all its runners
                    diag["detail"] += " (starting)"
                elif action[:2] == ["limactl", "start"]:
                    started_vms.add(action[2])
                report["runners"][name] = self.act(name, diag, attempts, now)
        if self.jit_slots:
            maint = load_json(MAINTENANCE_FILE, {})
            jit_ctx = {"vms": vms, "maintenance": maint.get("entries", [])
                       if isinstance(maint, dict) else []}
            report["runners"].update(self.check_jit_slots(jit_ctx, attempts, now))
        drift = self.check_drift(vms, now)
        if drift is not None:
            report["drift"] = drift
        keep = {k: [t for t in v if t > now - 3600] for k, v in attempts.items()}
        if not self.dry_run:
            write_json(ATTEMPTS_FILE, {k: v for k, v in keep.items() if v})
        return report

    def act(self, key: str, diag: dict, attempts: dict, now: float) -> dict:
        entry = {"cause": diag["cause"], "detail": diag["detail"], "action": None,
                 "result": None, "at": utcnow_iso()}
        cmd = diag.get("action")
        if not cmd:
            return entry
        if tuple(cmd) in self.done:  # e.g. one VM start covers every runner in it
            entry["action"], entry["result"] = " ".join(cmd), "already done this pass"
            return entry
        self.done.add(tuple(cmd))
        ok, why = may_act(attempts.get(key, []), now)
        entry["action"] = " ".join(cmd)
        entry["tries"] = len([t for t in attempts.get(key, []) if t > now - 3600])
        entry["gave_up"] = not ok and why.startswith("gave up")
        if not ok:
            # "ok" / "failed ..." / "gave up ..." / "waiting ...": the page keys off these.
            entry["result"] = why if entry["gave_up"] else f"retrying: {why}"
            return entry
        if self.dry_run:
            entry["result"] = "dry run: not run"
            return entry
        attempts.setdefault(key, []).append(now)
        code, out = self.host.run(cmd, timeout=300)
        entry["result"] = "ok" if code == 0 else f"failed (exit {code}): {out.strip()[-200:]}"
        return entry


LAUNCHD = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.ghostnet.runner-watchdog</string>
  <key>ProgramArguments</key><array>
    <string>{python}</string><string>{script}</string>{extra}
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartInterval</key><integer>120</integer>
  <key>RunAtLoad</key><true/>
  <key>LowPriorityIO</key><true/>
  <key>StandardOutPath</key><string>{home}/Library/Logs/runner-watchdog.log</string>
  <key>StandardErrorPath</key><string>{home}/Library/Logs/runner-watchdog.log</string>
</dict></plist>
"""


def main(argv: list[str] | None = None) -> int:
    import html
    argv = list(sys.argv[1:] if argv is None else argv)
    print_plist = bool(argv) and argv[0] == "launchd"
    if print_plist:
        argv = argv[1:]
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--machine", required=True, help='machine name in the page config, e.g. "Mac Studio"')
    p.add_argument("--page", help="status page URL (default http://127.0.0.1:8090)")
    p.add_argument("--config")
    p.add_argument("--dry-run", action="store_true", help="diagnose and report, change nothing")
    p.add_argument("--jit-command", help="command that refills a one-job runner slot; the "
                   "runner name is appended (off unless given)")
    args = p.parse_args(argv)
    if print_plist:
        extra = "".join(f"<string>{html.escape(a)}</string>" for a in argv)
        print(LAUNCHD.format(python=sys.executable, script=os.path.abspath(__file__),
                             extra=extra, home=os.path.expanduser("~")))
        return 0
    cfg = rs.load_config(args.config)
    if args.page:
        cfg["watchdog_page"] = args.page
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LOCK_FILE, "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("another watchdog pass is running", flush=True)
            return 0
        dog = Watchdog(cfg, args.machine, Host(), dry_run=args.dry_run,
                       jit_command=args.jit_command.split() if args.jit_command else None)
        report = dog.run_once()
    if not args.dry_run:
        write_json(REPORT_FILE, report)
    for name, e in report["runners"].items():
        print(f"{report['checked_at']} {name}: {e['cause']}: {e['detail']}"
              + (f" -> {e['action']}: {e['result']}" if e["action"] else ""), flush=True)
    if report.get("error"):
        print(report["error"], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
