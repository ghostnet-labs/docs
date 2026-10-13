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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API = "https://api.github.com"
DEFAULT_ORG = "ghostnet-labs"
TOKEN_FILE = os.path.expanduser("~/.config/runner-status/token")
CONFIG_FILE = os.path.expanduser("~/.config/runner-status/config.json")

# Machines shown on the page. A runner belongs to the first machine whose
# pattern matches its name; anything unmatched is listed under "Other runners"
# so nothing is hidden. "agent" is "local" (stats read in-process) or a URL of
# an agent started with `runner_status.py agent`.
DEFAULT_CONFIG = {
    "org": DEFAULT_ORG,
    "poll_seconds": 60,
    "queued_alert_minutes": 20,
    "hosted_stall_minutes": 15,
    "disk_paths": ["/", "/Volumes/NAS"],
    "machines": [
        {"name": "Mac Studio", "agent": "local",
         "runner_pattern": r"(?i)studio|gh-ubuntu|gh-build"},
        {"name": "Mac (dev)", "agent": "",
         "runner_pattern": r"(?i)macbook|mac-dev|\bdev\b"},
        {"name": "R620", "agent": "", "runner_pattern": r"(?i)r620"},
    ],
}

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


def read_token() -> str | None:
    token = os.environ.get("RUNNER_STATUS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            return fh.read().strip() or None
    return None


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
    def __init__(self, token: str):
        self.token = token
        self.rate_remaining: int | None = None

    def get(self, path: str, params: dict | None = None):
        url = path if path.startswith("http") else API + path
        if params:
            url += ("&" if "?" in url else "?") + "&".join(f"{k}={v}" for k, v in params.items())
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ghostnet-runner-status",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                self.rate_remaining = int(remaining)
            return json.loads(resp.read().decode())


class Poller:
    """Polls GitHub and agents on one background thread; the page reads a copy."""

    def __init__(self, cfg: dict, gh: GitHub | None, demo: bool = False):
        self.cfg = cfg
        self.gh = gh
        self.demo = demo
        self.stop = threading.Event()
        self.mu = threading.Lock()  # protects the fields below
        self.state: dict = {"updated": None, "errors": ["Starting up, first poll pending."]}
        self.slow: dict = {}
        self.slow_at = 0.0

    def snapshot(self) -> dict:
        with self.mu:
            return self.state

    def poll_once(self) -> None:
        if self.demo:
            raw = demo_raw()
        else:
            raw = self.fetch()
        state = build_state(raw, self.cfg, utcnow())
        with self.mu:
            self.state = state

    def fetch(self) -> dict:
        org = self.cfg["org"]
        errors: list[str] = []
        raw: dict = {"errors": errors}
        gh = self.gh
        if gh is None:
            errors.append("No GitHub token found. See README.md (token setup).")
        else:
            try:
                raw["runners"] = gh.get(f"/orgs/{org}/actions/runners",
                                        {"per_page": 100}).get("runners", [])
            except (urllib.error.URLError, OSError, ValueError) as exc:
                errors.append(f"Runners: {exc}")
            # Slow-changing data (repos, groups, workflows, billing) every 10 min.
            if time.time() - self.slow_at > 600 or not self.slow:
                self.slow = self.fetch_slow(gh, org, errors)
                self.slow_at = time.time()
            raw.update(self.slow)
            raw["jobs"] = self.fetch_jobs(gh, org, raw.get("repos", []), errors)
            raw["rate_remaining"] = gh.rate_remaining
        raw["machine_stats"] = self.fetch_agents(errors)
        return raw

    @staticmethod
    def fetch_slow(gh: GitHub, org: str, errors: list[str]) -> dict:
        out: dict = {"repos": [], "groups": {}, "disabled_workflows": [], "billing": None}
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
        for repo in out["repos"]:
            try:
                wfs = gh.get(f"/repos/{org}/{repo}/actions/workflows",
                             {"per_page": 100}).get("workflows", [])
            except (urllib.error.URLError, OSError, ValueError):
                continue
            for wf in wfs:
                if wf.get("state", "active") != "active":
                    out["disabled_workflows"].append(
                        {"repo": repo, "name": wf.get("name"), "state": wf.get("state"),
                         "url": wf.get("html_url")})
        try:
            out["billing"] = gh.get(f"/orgs/{org}/settings/billing/actions")
        except (urllib.error.URLError, OSError, ValueError):
            out["billing"] = None  # needs billing access; the stall heuristic covers it
        return out

    @staticmethod
    def fetch_jobs(gh: GitHub, org: str, repos: list[str], errors: list[str]) -> list[dict]:
        jobs: list[dict] = []
        for repo in repos:
            for status in ("queued", "in_progress"):
                try:
                    runs = gh.get(f"/repos/{org}/{repo}/actions/runs",
                                  {"status": status, "per_page": 50}).get("workflow_runs", [])
                except (urllib.error.URLError, OSError, ValueError) as exc:
                    errors.append(f"{repo} runs: {exc}")
                    break
                for run in runs:
                    try:
                        rjobs = gh.get(run["jobs_url"], {"per_page": 100}).get("jobs", [])
                    except (urllib.error.URLError, OSError, ValueError):
                        continue
                    for j in rjobs:
                        if j.get("status") in ("queued", "in_progress", "waiting", "pending"):
                            j["repo"] = repo
                            j["workflow"] = run.get("name")
                            j["branch"] = run.get("head_branch")
                            jobs.append(j)
        return jobs

    def fetch_agents(self, errors: list[str]) -> dict:
        stats = {}
        for m in self.cfg["machines"]:
            agent = m.get("agent")
            if not agent:
                continue
            if agent == "local":
                stats[m["name"]] = collect_stats(self.cfg["disk_paths"])
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
    for r in sorted(raw.get("runners", []), key=lambda r: r.get("name", "")):
        status = "offline" if r.get("status") != "online" else ("busy" if r.get("busy") else "idle")
        runner = {"name": r.get("name"), "status": status, "os": r.get("os"),
                  "labels": [lbl["name"] for lbl in r.get("labels", [])],
                  "group": groups.get(r.get("id"), "unknown")}
        target = next((m for m in machines if m["pattern"].search(runner["name"] or "")), other)
        target["runners"].append(runner)
    shown = [m for m in machines if m["runners"] or m["stats"] or m["name"] == "Mac Studio"]
    if other["runners"]:
        shown.append(other)
    for m in shown:
        m.pop("pattern", None)
        counts = {"idle": 0, "busy": 0, "offline": 0}
        for r in m["runners"]:
            counts[r["status"]] += 1
        m["counts"] = counts

    jobs = []
    for j in raw.get("jobs", []):
        labels = j.get("labels", [])
        hosted = any(HOSTED_LABELS.match(lbl) for lbl in labels) and "self-hosted" not in labels
        since = j.get("started_at") if j.get("status") == "in_progress" else j.get("created_at")
        jobs.append({"repo": j.get("repo"), "workflow": j.get("workflow"), "name": j.get("name"),
                     "status": j.get("status"), "labels": labels, "hosted": hosted,
                     "runner": j.get("runner_name"), "branch": j.get("branch"),
                     "url": j.get("html_url"), "age_min": age_minutes(since, now)})
    jobs.sort(key=lambda j: (j["status"] != "queued", -(j["age_min"] or 0)))

    alerts = []
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
            alerts.append({"level": "warn", "text": f"{m['name']} agent unreachable: {st['error']}"})
        for d in st.get("disks", []) or []:
            if d["total"] and d["free"] / d["total"] < 0.10:
                alerts.append({"level": "warn", "text":
                               f"{m['name']} disk {d['path']} low: {fmt_bytes(d['free'])} free"})
        for vm in st.get("vms") or []:
            if vm.get("status") != "Running":
                alerts.append({"level": "warn", "text":
                               f"{m['name']} VM {vm['name']} is {vm.get('status')}"})

    return {"updated": now.isoformat(), "org": cfg["org"], "machines": shown, "jobs": jobs,
            "alerts": alerts, "billing": billing, "rate_remaining": raw.get("rate_remaining"),
            "errors": raw.get("errors", []),
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
function machine(m){
  const c=m.counts,st=m.stats||{};let h=`<div class="card"><h2>${esc(m.name)}</h2><div class="pills">
  <span class="pill idle">${c.idle} idle</span><span class="pill busy">${c.busy} busy</span>
  <span class="pill offline">${c.offline} offline</span></div>`;
  if(st.error)h+=`<p class="offline">Agent unreachable</p>`;
  if(st.memory&&st.memory.total)h+=`<div class="stat"><span>RAM</span>${bar(st.memory.used,st.memory.total)}<span>${bytes(st.memory.used)} / ${bytes(st.memory.total)}</span></div>`;
  if(st.load&&st.cores)h+=`<div class="stat"><span>CPU load</span>${bar(st.load[0],st.cores)}<span>${st.load[0].toFixed(1)} / ${st.cores} cores</span></div>`;
  for(const d of st.disks||[])h+=`<div class="stat"><span>Disk ${esc(d.path)}</span>${bar(d.used,d.total)}<span>${bytes(d.free)} free</span></div>`;
  if(st.vms&&st.vms.length){h+=`<table><tr><th>VM</th><th>State</th><th>CPU</th><th>RAM</th><th>Disk</th></tr>`;
    for(const v of st.vms)h+=`<tr><td>${esc(v.name)}</td><td class="${v.status==="Running"?"idle":"offline"}">${esc(v.status)}</td><td>${esc(v.cpus)}</td><td>${bytes(v.memory)}</td><td>${bytes(v.disk)}</td></tr>`;
    h+=`</table>`}
  if(!m.stats&&!m.configured_agent&&m.name!=="Other runners")h+=`<p class="muted">No stats agent configured.</p>`;
  if(m.runners.length){h+=`<table style="margin-top:8px"><tr><th>Runner</th><th>State</th><th>Labels</th></tr>`;
    for(const r of m.runners)h+=`<tr><td>${esc(r.name)}</td><td class="${r.status}"><span class="dot"></span>${r.status}</td><td class="labels">${esc(r.labels.join(", "))}<br>group: ${esc(r.group)}</td></tr>`;
    h+=`</table>`}else h+=`<p class="muted">No runners registered.</p>`;
  return h+`</div>`}
function render(s){
  document.getElementById("meta").textContent=`${s.org||""} · updated ${s.updated?new Date(s.updated).toLocaleTimeString():"never"} · refreshes every 15s`;
  const a=s.alerts||[];document.getElementById("alerts").innerHTML=a.length?a.map(x=>`<div class="alert ${x.level}">${x.url?`<a href="${esc(x.url)}">${esc(x.text)}</a>`:esc(x.text)}</div>`).join(""):`<p class="allgood">All runners healthy, nothing stuck.</p>`;
  document.getElementById("machines").innerHTML=(s.machines||[]).map(machine).join("");
  const c=s.counts||{queued:0,running:0};document.getElementById("jobs-title").textContent=`Jobs: ${c.queued} queued, ${c.running} running`;
  const j=s.jobs||[];document.getElementById("jobs").innerHTML=j.length?`<table><tr><th>State</th><th>Age</th><th>Repo</th><th>Job</th><th>Wants</th><th>Runner</th></tr>`+
   j.map(x=>`<tr><td class="${x.status==="queued"?"queued":"running"}">${x.status==="in_progress"?"running":esc(x.status)}</td><td>${age(x.age_min)}</td><td>${esc(x.repo)}</td><td><a href="${esc(x.url)}">${esc(x.workflow)} / ${esc(x.name)}</a><br><span class="labels">${esc(x.branch)}</span></td><td class="labels">${esc(x.labels.join(", "))}${x.hosted?" (GitHub-hosted)":""}</td><td>${esc(x.runner||"–")}</td></tr>`).join("")+`</table>`:`<p class="muted">No queued or running jobs.</p>`;
  const e=s.errors||[];document.getElementById("foot").textContent=(s.rate_remaining!=null?`API calls left this hour: ${s.rate_remaining}. `:"")+(e.length?"Problems: "+e.join(" | "):"");
}
async function tick(){try{const r=await fetch("api/state",{cache:"no-store"});render(await r.json())}catch(e){document.getElementById("meta").textContent="Status server unreachable, retrying"}}
tick();setInterval(tick,15000);
</script></body></html>
"""


def make_handler(get_body):
    class Handler(BaseHTTPRequestHandler):
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


def serve(args) -> None:
    cfg = load_config(args.config)
    token = None if args.demo else read_token()
    poller = Poller(cfg, GitHub(token) if token else None, demo=args.demo)
    notifier = Notifier(args.notify)

    def loop():
        while not poller.stop.is_set():
            poller.poll_once()
            notifier.update(poller.snapshot().get("alerts", []))
            poller.stop.wait(cfg["poll_seconds"])

    threading.Thread(target=loop, daemon=True, name="poller").start()

    def body(path):
        if path in ("/", "/index.html"):
            return PAGE, "text/html; charset=utf-8"
        if path == "/api/state":
            return json.dumps(poller.snapshot()), "application/json"
        return None, ""

    srv = ThreadingHTTPServer((args.bind, args.port), make_handler(body))
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
                runner(21, "studio-build-2", "offline", False, bld)]
    jobs = [
        {"repo": "firmware", "workflow": "Build firmware (Mac pilot)", "name": "build (bcm27xx)",
         "status": "in_progress", "labels": bld, "runner_name": "studio-build-1",
         "head_branch": "main", "started_at": ago(74), "html_url": "#"},
        {"repo": "firmware", "workflow": "Build PR", "name": "build (mediatek/filogic)",
         "status": "queued", "labels": ["ubuntu-latest"], "created_at": ago(41), "html_url": "#"},
        {"repo": "luci", "workflow": "Manet merge gate", "name": "gate", "status": "in_progress",
         "labels": mac, "runner_name": "studio-mac-1", "started_at": ago(3), "html_url": "#"},
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
        "runner_processes": 12}}
    return {"runners": runners, "jobs": jobs, "machine_stats": stats, "errors": [],
            "groups": {r["id"]: "Default" for r in runners}, "disabled_workflows": [],
            "billing": None, "rate_remaining": 4710}


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
    lp = sub.add_parser("launchd", help="print a LaunchAgent plist")
    lp.add_argument("mode", choices=["serve", "agent"])
    args, extra = p.parse_known_args(argv)
    if extra and args.cmd != "launchd":
        p.error(f"unrecognized arguments: {' '.join(extra)}")
    args.extra = extra  # launchd passes these through, e.g. --notify
    {"serve": serve, "agent": agent, "launchd": launchd}[args.cmd](args)


if __name__ == "__main__":
    main(sys.argv[1:])
