# Runner status page

A small always-on page that shows, without anyone asking:

- every self-hosted runner in the `ghostnet-labs` org, grouped by machine
  (Mac Studio, "Mac (dev)" once its runner exists, R620 only if it appears),
  with idle / busy / offline, labels and runner group;
- every queued and running Actions job across the org's repos, oldest first,
  with its age, the runner labels it wants and the runner it got;
- alerts: offline runners, jobs queued 20+ minutes, GitHub-hosted jobs stuck
  (the usual sign of the Actions minutes or spending limit), disabled
  workflows, low disk, stopped Lima VMs, and the minutes counter when the
  token can read billing;
- each Mac's RAM, CPU load, disks (`/` and `/Volumes/NAS`) and Lima VMs
  (`gh-ubuntu`, `gh-build`, `gh-build-2` on the Studio).

The page refreshes itself every 15 seconds; GitHub is polled every 60
seconds (about 1,500 API calls an hour, well under the 5,000 limit).

![Desktop view, demo data](https://github.com/ghostnet-labs/docs/raw/main/tools/runner-status/screenshot.png)

It is one file, `runner_status.py`, Python 3 standard library only. Nothing to
install. It only reads: it calls GitHub `GET` endpoints with a read-only token
and runs a fixed list of read-only commands (`sysctl`, `vm_stat`, `ps`,
`limactl list`).

## Try it with fake data

```sh
python3 tools/runner-status/runner_status.py serve --demo
# open http://localhost:8090/
```

## 1. Make a read-only token (once)

1. Open <https://github.com/settings/personal-access-tokens/new>.
2. Name `runner-status`, expiration 1 year, **Resource owner: ghostnet-labs**.
3. Repository access: **All repositories**.
4. Repository permissions: **Actions: Read-only** (Metadata read-only is added
   automatically).
5. Organization permissions: **Self-hosted runners: Read-only**.
6. Generate, copy the token.
7. If the org asks for approval, approve it at
   <https://github.com/organizations/ghostnet-labs/settings/personal-access-token-requests>.

On the machine that hosts the page:

```sh
mkdir -p ~/.config/runner-status
pbpaste > ~/.config/runner-status/token
chmod 600 ~/.config/runner-status/token
```

`RUNNER_STATUS_TOKEN` in the environment also works. `GITHUB_TOKEN` is used
only when neither of those exists, because on a runner machine it is often
some other, short-lived token. The page footer names the token type and where
it came from (never the token itself).

## 2. Run it on the Mac Studio

```sh
git clone --depth 1 https://github.com/ghostnet-labs/docs ~/runner-status-src
cd ~/runner-status-src/tools/runner-status
python3 runner_status.py launchd serve --notify \
  > ~/Library/LaunchAgents/com.ghostnet.runner-status.serve.plist
launchctl load ~/Library/LaunchAgents/com.ghostnet.runner-status.serve.plist
```

Open `http://<studio-name>.local:8090/` from any device on the LAN (phone
included). The Studio's own stats are read in-process, so it needs no agent.
`--notify` shows a macOS banner on the Studio whenever a new alert appears.
Logs: `~/Library/Logs/runner-status-serve.log`. Update with `git pull` and
`launchctl kickstart -k gui/$(id -u)/com.ghostnet.runner-status.serve`.

The page shows runner names and job titles to anyone on the LAN. It has no
controls and holds no token in the page.

## 3. Add another Mac (when "Mac (dev)" gets a runner)

On that Mac:

```sh
python3 runner_status.py launchd agent \
  > ~/Library/LaunchAgents/com.ghostnet.runner-status.agent.plist
launchctl load ~/Library/LaunchAgents/com.ghostnet.runner-status.agent.plist
```

Then on the Studio create `~/.config/runner-status/config.json` with the
agent URL and restart the page:

```json
{
  "machines": [
    {"name": "Mac Studio", "agent": "local", "runner_pattern": "(?i)studio|gh-ubuntu|gh-build"},
    {"name": "Mac (dev)", "agent": "http://<macbook-name>.local:8091", "runner_pattern": "(?i)macbook|mac-dev|\\bdev\\b"},
    {"name": "R620", "agent": "", "runner_pattern": "(?i)r620"}
  ]
}
```

A runner belongs to the first machine whose `runner_pattern` matches its
name; unmatched runners show under "Other runners", so a wrong pattern never
hides one. Other keys: `poll_seconds`, `queued_alert_minutes`,
`hosted_stall_minutes`, `disk_paths`.

## Troubleshooting

Problems show as red alerts at the top of the page, in plain words:

| Alert says | Meaning | Fix |
|---|---|---|
| No GitHub token | No token file | Step 1 |
| token rejected (401) | Token wrong, expired or revoked, or not the one you meant (check the footer's "Using ... from ...") | Make a new token and overwrite the file; picked up on the next poll |
| missing permission | The token lacks the named permission | Edit the token on GitHub and add it; no restart needed |
| waiting for org-owner approval | Org requires approval for fine-grained tokens | Approve it in the org's token requests |
| org does not allow fine-grained tokens | Org policy blocks them | Allow them in org Settings > Personal access tokens |

If fine-grained tokens cannot be used at all, a classic token works too, but
listing org runners needs the `admin:org` scope, which also grants write
access to the org. Prefer the fine-grained token.

## Tests

```sh
python3 -m unittest discover -s tools/runner-status -v
```
