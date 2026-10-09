# Unified UI developer guide

**Owner:** [GHO-81](https://linear.app/ghostnet-labs/issue/GHO-81) (publish unified-UI guidance)  
**Status:** Written 2026-10-09 from the code and open PRs it links. The design it explains is [unified-ui-design.md](unified-ui-design.md) (D-037), which owns the routing table, cookie behavior and configuration-ownership rule. This guide does not restate them; it tells you where code goes and how a change reaches an image.

## 1. Routing, sessions and configuration ownership

**Routing.** The openmanetd frontend server is the one web origin (`:8081` HTTPS, `:8080` HTTP). With `frontend.luciProxy.enable` set, it forwards LuCI's `/cgi-bin/`, `/luci-static/` and `/ubus/` paths to uhttpd on loopback before any other handler. Everything else goes to the SPA, `/api/*`, `/ws`, or the API on `:8087`. The full table is [design §3](unified-ui-design.md#3-routing-option-1); the code is `openmanetd:internal/frontend/luci_proxy.go` and its user doc is [docs/luci-proxy.md](https://github.com/ghostnet-labs/openmanetd/blob/claude/project-thread-0s9sbx-gho70/docs/luci-proxy.md), both pending in [openmanetd#22](https://github.com/ghostnet-labs/openmanetd/pull/22).

Rules for new code:

- Never add an SPA route or `/api` path under `/cgi-bin`, `/luci-static` or `/ubus`. The proxy owns those prefixes.
- The SPA learns whether the proxy is on from `luci_proxy_enabled` on `/api/system/info` ([openmanetd#22](https://github.com/ghostnet-labs/openmanetd/pull/22)). Do not probe LuCI from the browser.
- uhttpd on `:80` is the recovery route. No change may make it depend on openmanetd, move it, or redirect its `/` without a new decision ([design §5](unified-ui-design.md#5-recovery-route)).

**Sessions.** Two separate logins, by design ([design §4](unified-ui-design.md#4-sign-in-sessions-and-csrf)):

| | OpenMANET | LuCI |
|---|---|---|
| Code | `openmanetd:internal/auth` (PAM, in-memory sessions) | rpcd `sysauth`, `luci:modules/luci-base/ucode/dispatcher.uc` |
| Cookie | `session`, `Path=/` | `sysauth_http`, `path=/cgi-bin/luci/` |

The proxy strips the OpenMANET `session` cookie before forwarding to LuCI and never edits LuCI's `Set-Cookie`. Do not bridge the two sessions; that needs a new decision. Sign-in gaps (two logins, empty root password under PAM) belong to [GHO-72](https://linear.app/ghostnet-labs/issue/GHO-72).

**Configuration.** One persistent owner per setting ([design §6](unified-ui-design.md#6-configuration-ownership)):

- **UCI (`/etc/config/*`) owns network, wireless, firewall, DHCP and system.** openmanetd pages read and write UCI through the daemon (`openmanetd:internal/network/uci_*.go`) and keep no copy. Reread UCI when a page opens; LuCI may have written it.
- **`/etc/openmanetd/config.yml` owns daemon features** (comms, BLOS, GNSS, auth, setup, `frontend.*`; `sysupgrade.releasesRepo` is pending for [GHO-77](https://linear.app/ghostnet-labs/issue/GHO-77)). It is read by viper in `openmanetd:internal/config`. Do not mirror it into UCI. LuCI does not edit it.
- When openmanetd rewrites UCI on its own (address reservation, `batmesh1` tuning), LuCI must show a warning. The pattern is the menu.d wrapper in `packages:openmanetd/files/luci/` ([GHO-74](https://linear.app/ghostnet-labs/issue/GHO-74), [packages#15](https://github.com/ghostnet-labs/packages/pull/15)). Add any new daemon-owned UCI option to `managed.js` there.

The current list of competing writers is the [audit, §2](unified-ui-audit.md#2-parity-matrix).

## 2. Local lab and physical-node modes

| Mode | What runs | Use it for | It cannot show |
|---|---|---|---|
| Local lab ([openmanetd tools/ui-lab](https://github.com/ghostnet-labs/openmanetd/blob/main/tools/ui-lab/README.md)) | Vite dashboard on `127.0.0.1:5173` with the simulated sample backend (`tools/sample-api.py`); a generic OpenWrt 24.10.5 VM with your `luci` and `packages` checkouts synced in, LuCI on `127.0.0.1:8083` | Layout, forms, LuCI theme and view changes, quick iteration with no hardware | The proxy and Advanced handoff (the two UIs have separate backends), radios, audio/PTT, flashing, setup apply, real Morse apps |
| Vite against a node | `cd frontend && VITE_API_TARGET=http://<node>:8081 pnpm run dev` (see `openmanetd:CLAUDE.md`) | SPA changes against real data and, with the proxy on at the node, the Advanced path through Vite's `/cgi-bin`, `/luci-static`, `/ubus` proxy entries ([openmanetd#22](https://github.com/ghostnet-labs/openmanetd/pull/22)) | Changes to the daemon itself |
| Physical node | A firmware image (or `openmanetd` binary copied to `/usr/bin` for a quick check) on the CM5 POC node | Release evidence: first boot, upgrade, radios, mesh, GPS, battery, PTT, recovery. The checklist is [unified-ui-acceptance-plan.md](unified-ui-acceptance-plan.md) ([GHO-79](https://linear.app/ghostnet-labs/issue/GHO-79)) | Nothing; this is the only mode that counts as evidence |

The lab's LuCI files come from the `mm-23.05` fork on OpenWrt 24.10. Check anything LuCI-specific on a node before relying on it. Browser and board acceptance in the lab is [GHO-78](https://linear.app/ghostnet-labs/issue/GHO-78).

## 3. Repository boundaries

| Repo | Owns | Put here |
|---|---|---|
| [ghostnet-labs/openmanetd](https://github.com/ghostnet-labs/openmanetd) | Daemon, API, OpenMANET UI (`frontend/`), LuCI proxy, setup wizard, sysupgrade client | Any OpenMANET UI or daemon change. Follow its `CLAUDE.md` and `.claude/rules/` (Lattice, generated code, tests). `static/` is rebuilt by its Build Frontend Assets workflow |
| [ghostnet-labs/packages](https://github.com/ghostnet-labs/packages) (branch `24.10`) | OpenWrt package recipes: the openmanetd pin (`openmanetd/Makefile`), the shipped `sample_config.yml`, init script, board `uci-defaults`, LuCI theme `luci-theme-openmanetargon`, the daemon-managed LuCI warnings, Morse LuCI apps | Package pins, default config, first-boot `uci-defaults`, LuCI theme and LuCI hooks that ship with openmanetd |
| [ghostnet-labs/luci](https://github.com/ghostnet-labs/luci) (branch `mm-23.05`) | Core LuCI modules | Only changes that cannot be a theme or a hook in packages. The firmware feed currently pins upstream `OpenMANET/luci` ([audit §0](unified-ui-audit.md#0-sources-and-notation)), so a change here also needs the feed repointed |
| [ghostnet-labs/firmware](https://github.com/ghostnet-labs/firmware) (branch `24.10`) | Feed pins (`feeds.conf.default`), board diffconfigs, image CI and the release workflow (`build-release.yml`) | Feed bumps, which packages go in an image, release assets |
| [ghostnet-labs/docs](https://github.com/ghostnet-labs/docs) | Decisions, design, audit and these guides under `project/` | Records only. Results and status go on Linear ([project/README.md](../README.md)) |

## 4. Release procedure

A UI change reaches a node in four hops. Each hop is its own PR and must merge before the next one points at it.

1. **openmanetd.** Merge the change. The shipped package builds the `ekh-1.3.10` line today; moving the package to newer openmanetd is [GHO-80](https://linear.app/ghostnet-labs/issue/GHO-80). Until that lands, a fix for current images must also be backported to `ekh-1.3.10` (example: [openmanetd#21](https://github.com/ghostnet-labs/openmanetd/pull/21)).
2. **packages (`24.10`).** In `openmanetd/Makefile`, set `PKG_SOURCE_VERSION` to the merged openmanetd commit and bump `PKG_RELEASE` (or raise `PKG_VERSION` and reset `PKG_RELEASE` for a new openmanetd version). Change `files/sample_config.yml` here if a new default is needed (for example `sysupgrade.releasesRepo`, D-039). Example: [packages#13](https://github.com/ghostnet-labs/packages/pull/13).
3. **firmware (`24.10`).** Pin the `openmanet` feed in `feeds.conf.default` to the merged packages commit. Let every target's PR image build pass. Example: [firmware#42](https://github.com/ghostnet-labs/firmware/pull/42).
4. **Image and release.** PR builds produce images as Actions artifacts (kept 5 days). A release comes from `build-release.yml` (tag push or manual run). Nodes verify online updates against a release asset named `sha256sums` (`openmanetd:internal/sysupgrade/manager.go`); publishing it is pending in [firmware#46](https://github.com/ghostnet-labs/firmware/pull/46). ghostnet-labs/firmware had no releases on 2026-10-09.

Then:

5. **Bench.** Run [unified-ui-acceptance-plan.md](unified-ui-acceptance-plan.md) on the CM5 POC node with that image. D-038 requires this run before the first-boot switch is released. Turning the LuCI proxy on by default waits for the bench checks in [design §4](unified-ui-design.md#4-sign-in-sessions-and-csrf) and Justin's sign-off (D-036).
6. **Docs.** Update the [operator guide](unified-ui-operator-guide.md) "Before you rely on this guide" table and anything else this PR series made false.

Merging any of these does not qualify hardware or close a bench gate ([AGENTS.md](../../AGENTS.md)).
