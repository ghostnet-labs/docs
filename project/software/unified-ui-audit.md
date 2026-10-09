# Unified UI audit: workflows, parity and configuration ownership

**Owner:** [GHO-67](https://linear.app/ghostnet-labs/issue/GHO-67) (audit UI workflows, feature parity and configuration ownership)
**Status:** Audit, read from the code on 2026-10-09. It records what exists; it decides nothing. The direction is D-036 in [../decisions.md](../decisions.md). Open design choices (origin, sign-in, recovery route) belong to [GHO-69](https://linear.app/ghostnet-labs/issue/GHO-69).

## 0. Sources and notation

| Repo | Revision read | Notes |
|---|---|---|
| ghostnet-labs/openmanetd `ekh-1.3.10` | `f8751da` | Pinned by packages `openmanetd/Makefile` (`PKG_SOURCE_VERSION`, release 1.3.10-8). |
| ghostnet-labs/openmanetd `main` | `13b61a2` | 74 commits ahead of `ekh-1.3.10`. Not shipped. |
| ghostnet-labs/packages | `b4faf12` | |
| ghostnet-labs/luci `mm-23.05` | `cef427b` | firmware `feeds.conf.default` pins OpenMANET/luci `53e6515`, an ancestor of `cef427b` (8 commits behind). |
| ghostnet-labs/firmware `24.10` | `726c6a4` | |

Paths are written `repo:path`. Branch marks: **[both]** = on `ekh-1.3.10` and `main`; **[main]** = only on `main`. "Inferred" marks anything not read directly from code or config.

Feed pin note: firmware `24.10` `feeds.conf.default` pins packages `f03035e`, whose `openmanetd/Makefile` pins openmanetd `0cf4d7d` (on `ekh-1.3.10`, one MT7916 detection fix behind `f8751da`). The firmware branch `claude/project-thread-zwsae0-feed-pin` bumps packages to `b4faf12` (openmanetd `f8751da`). Both are 1.3.10; nothing in this audit differs between `0cf4d7d` and `f8751da` except MT7916 detection.

## 1. Entry points today

| Service | Listener | Source |
|---|---|---|
| LuCI (uhttpd) | HTTP :80, HTTPS :443, no redirect to HTTPS | `firmware:package/network/services/uhttpd/files/uhttpd.config`; `packages:boards/bsp-common/files/uci-defaults/01_openmanet_uhttpd_http` (`redirect_https=0`) |
| OpenMANET UI (openmanetd frontend) | HTTP :8080, HTTPS :8081 (self-signed unless a cert is configured) | `openmanetd:internal/config/config.go` (`DefaultOpenMANETFrontendHostPort`, `...TLSHostPort`); `openmanetd:internal/frontend/server.go` (`Run`) |
| openmanetd ConnectRPC API | :8087 on `0.0.0.0` | `openmanetd:internal/config/config.go` (`DefaultOpenMANETAPIAddress`); `openmanetd:internal/openmanet/server/server.go` |
| SSH (dropbear) | enabled by default | `packages:boards/bsp-common/files/uci-defaults/32_openmanet_dropbear_enable` |

The frontend proxies `/rpc/*` (prefix stripped), `/auth/*` and `/api/sysupgrade/*` to :8087, serves its own `/api/*` and `/ws`, and returns `index.html` for every other unknown path (`openmanetd:internal/frontend/server.go`, `handler`, `buildAPIProxies`). Neither UI links to the other: the OpenMANET nav has no LuCI entry (`openmanetd:frontend/src/Layout.jsx`, `frontend/src/pages/SettingsLayout.jsx`) [both].

## 2. Parity matrix

"OM" = OpenMANET UI. Page paths are under `openmanetd:frontend/src/`; LuCI core views are under `luci:modules/` and `luci:applications/`; Morse LuCI apps are under `packages:luci/`. LuCI core apps shipped come from `firmware:boards/common/openmanet_diffconfig` (`luci-mod-admin-full`, `luci-app-firewall`, `luci-app-opkg`) and `packages:morse-micro/openmanet-morse-stack/Makefile` (morseconfig, ekhwizards, mod-home, openmanetargon theme).

| Task | OM page + backend | LuCI page/app | Config owner | Competing writers / boot-time reconciliation | Proposed placement | First-release gap |
|---|---|---|---|---|---|---|
| First-boot setup / mesh join | `pages/SetupWizard.jsx`, `pages/setup/*`, gate `components/SetupGate.jsx`; `internal/openmanet/server/handlers/setup.go`, `setup_phases.go` [both, disabled by default]. Mesh-join QR (`components/MeshJoinQR.jsx`, `QrScanInput.jsx`, `handlers/mesh_join.go`, `docs/mesh-join-qr.md`) [main] | `luci-app-ekhwizards`: `admin/morse/landing` → `admin/selectwizard` → `admin/morse/meshwizard`; save logic `luci-app-morseconfig/htdocs/.../tools/morse/wizard.js` | UCI `wireless`, `network`, `dhcp`, `firewall`, `system`, `mesh11sd` [both]; plus `umdns`, `openmanetd`, `luci` [main] (`wizardConfigs` in `handlers/setup.go`); config.yml `setup.*`, `auth.enable` | Two wizards write the same UCI. Go wizard resets wireless/network first (`runResetWireless`, `runResetNetwork`). LuCI landing sets `luci.main.homepage` (`10_luci-app-ekhwizards`). Go wizard writes `luci.wizard.used=1` and clears the wizard homepage only on [main] (`writeLuciBookkeeping`) | Default | Shipped firmware runs only the LuCI wizard (see section 5). One wizard must be chosen (GHO-75) |
| Dashboard status | `pages/Dashboard.jsx`; `handlers/dashboard.go`, `/api/system/*` in `internal/frontend/handlers.go` [both] | `luci-mod-home` (`admin/home`, `view/home/index.js`); status overview in `luci-mod-status` | Read-only | None | Default | None |
| Topology | `pages/Topology.jsx`; `handlers/mesh_topology*.go` [both]; per-peer link rates [main] (`internal/wireless/rate.go`) | `luci-mod-home/.../view/home/mesh11s-topology.js` | Read-only (alfred/batman-adv) | None | Default | None |
| Comms / PTT | `pages/Comms.jsx`, `DeviceAudioPanel.jsx`; `handlers/comms.go`, `internal/comms` [both]; talk-group selector and voice announce [main] (`internal/comms/gpio/selector.go`, `internal/comms/announce`) | None | config.yml `comms.*` | `packages:boards/bsp-bcm271x/files/uci-defaults/42_ghostnet-v1-comms` rewrites `comms.enable` on `ghostnet,v1`; OM Settings raw-YAML editor writes the same file (`internal/frontend/handlers.go`, `handleSettingsConfig`) | Default | None |
| GPS | `pages/GpsStatus.jsx`; `handlers/gnss.go`, `internal/gpsd` [both] | None | config.yml `gnss.*`; gpsd device in UCI `gpsd` (board-owned) | `packages:boards/bsp-bcm271x/files/uci-defaults/40_cm5-gpsd-device` sets `gpsd.core.device` on CM5; OM does not write `gpsd` | Default | None |
| Battery | Dashboard card, `pages/dashboardBattery.js`; `internal/system/battery.go` [both]; freshness cache and V1 pack profile [main] (`internal/system/battery_cache.go`) | None | Daemon-managed (hwmon read-only) | None | Default | V1 pack profile is [main] only |
| BLOS | `pages/BLOS.jsx`; `handlers/blos.go`, `internal/blos` [both] | None (tailscale has no LuCI app in the image) | config.yml `blos.*`; tailscale state; UCI `firewall` (adds tunnel device to mesh zone, `internal/blos/interfaces.go`) | `packages:boards/bsp-common/files/uci-defaults/16_openmanet_roip` enables/disables tailscale on first boot from `mesh11sd.mesh_params.mesh_gate_announcements` | Default | None |
| Hostname / identity | `pages/Settings.jsx` → `POST /api/settings/hostname` (`internal/frontend/handlers.go`, shell `uci set system.@system[0].hostname`); wizard `runHostname` [both] | `luci-mod-system/.../view/system/system.js`; LuCI landing (`landing.js`, hostname field) | UCI `system.@system[0].hostname` | Three writers (OM settings, Go wizard, LuCI). No reconciliation | Default | None |
| HaLow channel / bandwidth / power | `pages/SettingsWireless.jsx`; `handlers/wifi_config.go` (`UpdateRadioSettings`), `internal/network/uci_wireless.go` [both] | `luci-mod-network/.../view/network/wireless.js`; `luci-app-morseconfig` `admin/config` (`view/morse/config.js`) | UCI `wireless` (morse `wifi-device` `channel`, `htmode`, `txpower`, `country`) | `99_morse_radio_defaults` (packages bsp-common) seeds channel 42, country US, BCF on first boot. OM rejects non-mesh mode on Morse radios (`rejectNonMeshModeOnMorse`) [main]; LuCI does not | Default (common), Advanced (country, BCF, raw options) | None |
| Wi-Fi mesh backhaul and AP | `pages/SettingsWireless.jsx`, wizard `StepAPs.jsx`; `handlers/wifi_config.go` [both]; HE40 default, peer admission floor, batmesh1 tuning [main] | `luci-mod-network` wireless; LuCI mesh wizard | UCI `wireless` (`default_<radio>`, `batmesh1_<radio>`), `network.batmesh1`; `/etc/config/openmanetd` `batmesh1configured` | openmanetd boot: `setupBatMesh1Interface` creates batmesh1 unless an AP is enabled; `reconcileBatMesh1Options` adds tuning options [main] (`internal/mgmt/device.go`, `mgmt.go` `Start`). `97_2g_radio_defaults` sets 2.4 GHz channel 6 | Default | LuCI edits to batmesh1 options can be re-added at next start [main] |
| LAN / DHCP | `pages/SettingsNetwork.jsx` (read-only: interfaces, DHCP config, leases); `handlers/network_interface.go` [both] | `luci-mod-network/.../view/network/interfaces.js`, `dhcp.js` | UCI `network`, `dhcp`; `/etc/config/openmanetd` `dhcpconfigured` | openmanetd `AddressReservationWorker` rewrites the mesh bridge address and DHCP pool, then reboots, when unconfigured or on conflict (`internal/mgmt/address_reservation.go`) [both]. LuCI edits to that interface can be overwritten | Advanced (edit); Default (view) | LuCI needs a "daemon-managed" warning on the mesh bridge (GHO-74) |
| Firewall | None in OM UI. Wizard and BLOS write zones (`internal/firewall/firewall.go`) | `luci-app-firewall` (`view/firewall/zones.js`) | UCI `firewall` | Go wizard topology phases; BLOS adds tunnel to zone | Advanced | None |
| Services / startup | `pages/Settings.jsx` "Restart openmanetd" (QuickAction). `/api/system/restart-service` exists but no UI [both] | `luci-mod-system/.../view/system/startup.js` | `/etc/init.d/*`, `/etc/rc.d` | None | Advanced | None |
| Software packages | None | `luci-app-opkg` (`view/opkg.js`) | opkg; feeds `/etc/opkg/customfeeds.conf` | `15_openmanet_custom_feeds` points feeds at `openmanet.github.io` (upstream), not ghostnet-labs | Advanced | Feed source is upstream (GHO-77) |
| Firmware upgrade | `pages/SettingsFirmware.jsx`; `handlers/sysupgrade.go`, `sysupgrade_upload.go`, `internal/sysupgrade` [both] | `luci-mod-system/.../view/system/flash.js` (`cgi-upload`, ubus sysupgrade) | Daemon-managed; logs in `/etc/openmanetd/sysupgrade` | Online releases come from GitHub `OpenMANET/firmware` (`internal/openmanet/openmanet.go`, `GitHubReleasesClient`) [both] | Default | Online updates would offer upstream images, not ghostnet builds (GHO-77) |
| Backup / restore | None | `flash.js` (`cgi-backup`, `cgi-upload`) | sysupgrade backup | None | Advanced | No OM backup; LuCI only |
| Factory reset | `SettingsFirmware.jsx` "Factory Reset"; `PerformFactoryReset` → `/sbin/firstboot -r -y` (`internal/sysupgrade/factoryreset.go`) [both] | `flash.js` "Perform reset" | Overlay wipe | None | Default | None |
| Logs | `pages/SettingsLogs.jsx`; `handlers/logs.go` → `logread`/`dmesg` (`internal/logs/provider.go`) [both] | `luci-mod-status/.../view/status/syslog.js`, `dmesg.js`; Morse logs `admin/statistics/morse/logs` | Read-only | None | Default | None |
| Terminal / shell | `pages/SettingsTerminal.jsx`; `/api/terminal/ws`, `internal/terminal` running `/bin/login` (`DefaultTerminalShell`) [both] | None (`luci-app-ttyd` exists in luci but is not selected in the firmware diffconfigs) | config.yml `terminal.*` | None | Advanced (inferred; it is a root shell) | None |
| Password change | `pages/Settings.jsx` "Passphrase" → `/auth/change-password` (`internal/auth/handlers.go`, `password.go` via `chpasswd`/`passwd`) [both] | `luci-mod-system/.../view/system/password.js`; LuCI landing sets root password | `/etc/shadow` (root) | Shared by both UIs, Go wizard (`runPassword`, root) and LuCI landing | Default | None |
| Time / NTP | Wizard timezone and clock sync only (`runSetTimezone`, `syncClock`; `internal/network/uci_system.go`) [both] | `system.js` (timezone, NTP servers) | UCI `system` (`zonename`, `timezone`, `ntp`); `/etc/ntpd.d/gps.conf` on CM5 | `43_cm5-ntpd-gps` (packages bsp-bcm271x) installs GNSS/PPS ntpd config on `bcm2712,mm8108-usb`; LuCI landing sets timezone from the browser | Advanced (NTP); Default (timezone, inferred) | No post-setup timezone page in OM |
| Reboot | Backend only: `/api/system/reboot` (`internal/frontend/handlers.go`), QuickAction `REBOOT_DEVICE` (`handlers/dashboard.go`). No button in any page [both] | `luci-mod-system/.../view/system/reboot.js` | n/a | Address reservation reboots by itself after renumbering | Default | Add a reboot button (backend exists) |

## 3. Auth and session boundaries

| Item | openmanetd | LuCI |
|---|---|---|
| Credential check | PAM, service `login` by default (`auth.pamService`; `internal/auth/pam_linux.go`, `DefaultAuthPAMService` in `internal/config/config.go`) | rpcd `session.login` against the system account (`luci:modules/luci-base/ucode/dispatcher.uc`, `session_retrieve`) |
| Account | Any PAM user; wizard and LuCI set `root` | `root` (`duser: 'root'` in `dispatcher.uc`) |
| Cookie | `session`, `Path=/`, `HttpOnly`, `SameSite=Lax`, no `Secure` (deliberate, dual HTTP/HTTPS) (`internal/auth/middleware.go` `SessionCookieName`, `handlers.go`) | `sysauth_http` or `sysauth_https`, `path=/cgi-bin/luci/` (from `build_url()` = `SCRIPT_NAME` + `/`), `SameSite=strict`, `HttpOnly`, `secure` on HTTPS (`dispatcher.uc` lines 951–954, `build_url`) |
| Other token forms | `Authorization: Bearer` header wins over cookie (`extractSessionToken`) | ubus session id in JSON-RPC body on `/ubus` |
| Lifetime | 24 h, max 16 sessions (`DefaultAuthSessionMaxAgeSecs`, `DefaultAuthSessionMaxSize`); in memory | rpcd session timeout (standard 300 s sliding, inferred; not read from this image) |
| Unauthenticated paths | API: `/auth/login`, `/auth/check`, `DashboardService/GetDashboardStatus`, `SetupService/GetSetupStatus`, `SetupService/ApplySetup` (`isAPISkipPath`). Frontend: everything except `/api/*` and `/ws` (`isFrontendProtectedPath`); `/rpc`, `/auth`, `/api/sysupgrade` are checked upstream | Login page, static `/luci-static` |
| Kill switch | `auth.enable` (default true); `setup-reset` sets it false | none |

Consequences: the two UIs share the root password (`/etc/shadow`) but not sessions; an operator signs in twice. Cookie names and paths do not collide on one origin. The API on :8087 is reachable directly on all interfaces and accepts bearer tokens, so a same-origin gateway does not remove that second surface. Whether PAM `login` accepts the empty root password of a fresh image is not verified (inferred risk; bench item for GHO-72).

## 4. LuCI paths a same-origin reverse proxy must forward

| Path | Why | Source |
|---|---|---|
| `/cgi-bin/luci` and everything below | ucode dispatcher; also the RPC fallback `/cgi-bin/luci/admin/ubus` | `firmware:.../uhttpd.config` (`lua_prefix`), `luci:modules/luci-base/Makefile` (`ucode_prefix`), `luci:modules/luci-base/htdocs/luci-static/resources/rpc.js` |
| `/luci-static/` | Theme, `resources/`, view JS; `mesh11s-topology.js` imports `/luci-static/resources/vivagraph.min.js` absolutely | `luci:modules/luci-base/root/etc/config/luci` (`mediaurlbase`, `resourcebase`), `packages:luci/luci-theme-openmanetargon/root/etc/uci-defaults/30_luci-theme-openmanet`, `packages:luci/luci-mod-home/.../mesh11s-topology.js` |
| `/ubus/` | JSON-RPC; LuCI probes it first and falls back to `/cgi-bin/luci/admin/ubus` | `firmware:package/network/services/uhttpd/files/ubus.default` (`ubus_prefix=/ubus`), `luci:modules/luci-base/ucode/template/header.ut` (`ubuspath`), `luci.js` |
| `/cgi-bin/cgi-upload` | File upload (firmware image, restore) | `luci:modules/luci-base/htdocs/luci-static/resources/ui.js` |
| `/cgi-bin/cgi-download` | File download | `luci:.../resources/fs.js`, `luci-mod-system/.../flash.js` |
| `/cgi-bin/cgi-backup` | Backup archive | `luci-mod-system/.../flash.js` |
| `/cgi-bin/cgi-exec` | Command output streaming | `luci:.../resources/fs.js` |
| `/` (`/www/index.html`) | Meta-refresh to `cgi-bin/luci/`; must not be forwarded if `/` becomes the OM UI | `luci:modules/luci-base/root/www/index.html` |

The four `cgi-*` helpers come from the `cgi-io` package (dependency in `luci:modules/luci-base/Makefile`; package source is openwrt/packages, not checked out here). Forward the `/cgi-bin/` prefix rather than each helper. Proxy cautions:

- The OM frontend serves `index.html` for unknown paths, so LuCI prefixes must be matched before the SPA fallback (`openmanetd:internal/frontend/server.go`, `spaHandler`).
- The OM frontend adds `Cross-Origin-Embedder-Policy: require-corp` and `Cross-Origin-Opener-Policy: same-origin` to every response (`coiMiddleware`). LuCI pages served through it would inherit these; cross-origin resources such as rangetest's OpenStreetMap tiles would then be blocked (inferred; rangetest is an optional extra, `firmware:boards/common_extras/rangetest_diffconfig`).
- uhttpd has `rfc1918_filter 1`; a proxy on localhost is unaffected (inferred).
- LuCI's wizard and IP-change helpers redirect to `protocol//<new IP>` root (`packages:luci/luci-app-morseconfig/.../tools/morse/wizard.js`, `luci-lib-morseui/.../morseui.js`), which lands on whatever owns `/`.

## 5. Shipped defaults and first-boot guards

| Guard | `ekh-1.3.10` (shipped) | `main` | Source |
|---|---|---|---|
| `setup.enabled` | false (default; `sample_config.yml` sets no `setup` key) | false | `openmanetd:internal/config/config.go` (`DefaultSetupEnabled`); `packages:openmanetd/files/sample_config.yml` |
| `setup.complete` | false | false | `DefaultSetupComplete` |
| `auth.enable` | true | true | `DefaultAuthEnable` |
| `luci.wizard` section | Created empty on first boot if missing | same | `packages:luci/luci-app-ekhwizards/root/etc/uci-defaults/10_luci-app-ekhwizards` |
| `luci.main.homepage` | Set to `admin/morse/landing` on first boot; landing then sets `admin/selectwizard`; LuCI wizard save deletes it | same LuCI behaviour; the Go wizard also deletes it if it is `admin/morse/landing` or `admin/selectwizard` | `10_luci-app-ekhwizards`; `landing.js`; `tools/morse/wizard.js`; [main] `handlers/setup_phases.go` `writeLuciBookkeeping` |
| `luci.wizard.used` | Unset at factory. LuCI wizard sets `1`. Go wizard reads it (treated as complete) but never writes it | Go wizard writes `1` at apply | `tools/morse/wizard.js`; `handlers/setup.go` `legacyLuciWizardUsed` |
| `setup-reset` CLI | Sets `setup.complete=false`, `auth.enable=false` | Also sets `luci.wizard.used=0` | `openmanetd:cmd/setup_reset.go`; [main] `internal/network/uci_luci.go` |

Result on shipped firmware: first boot is the LuCI landing page on :80. The OM UI on :8080/:8081 hides its wizard (SetupGate `wizard-hidden`) and shows the login page. If the Go wizard were enabled on `ekh-1.3.10`, LuCI would still redirect to its landing page after the Go wizard ran, because only `main` writes the LuCI bookkeeping. `setup-reset` on either branch does not set `setup.enabled`, so on a stock config it does not reopen the Go wizard.

## 6. Recovery routes

| Route | Works when | Source |
|---|---|---|
| LuCI on :80 | uhttpd and rpcd run; independent of openmanetd | Section 1 |
| SSH | dropbear enabled by default | `32_openmanet_dropbear_enable` |
| OM terminal page | openmanetd frontend runs; still asks for a login (`/bin/login`) | `openmanetd:internal/terminal`, `DefaultTerminalShell` |
| `openmanetd setup-reset` + `/etc/init.d/openmanetd restart` | Console, serial or SSH; also needs `setup.enabled: true` to show the wizard (section 5) | `openmanetd:cmd/setup_reset.go`, `openmanetd:docs/setup-wizard-recovery.md` |
| Find a renumbered node | `<hostname>.local` after the address-reservation reboot | `openmanetd:docs/setup-wizard-recovery.md`; umdns registration [main] (`internal/network/uci_umdns.go`) |
| Factory reset | OM firmware page, LuCI `flash.js`, or `firstboot` from a shell | `internal/sysupgrade/factoryreset.go`; `flash.js` |
| openmanetd crash loop | procd respawns (threshold 3600 s, 5 s delay, 5 retries), then stops; LuCI stays up | `packages:openmanetd/files/openmanetd.init` |
| OpenWrt failsafe | Standard OpenWrt boot failsafe (inferred; not verified on CM5) | none in these repos |

## 7. Smallest first-release gap list

Only items that block "OM is primary, LuCI behind Advanced". Each names the issue that owns it.

1. **Advanced entry.** No link from OM to LuCI or back (`Layout.jsx`, `SettingsLayout.jsx`). Owner [GHO-71](https://linear.app/ghostnet-labs/issue/GHO-71).
2. **One entry point.** Forward the section 4 paths ahead of the SPA fallback, or put a gateway in front of both; decide what serves `/` and whether COEP applies to LuCI. Owner [GHO-70](https://linear.app/ghostnet-labs/issue/GHO-70).
3. **One first-boot wizard.** Shipped config disables the Go wizard and LuCI owns first boot. Enabling the Go wizard needs the `main` LuCI bookkeeping and a `setup-reset` that also restores `setup.enabled`. Owner [GHO-75](https://linear.app/ghostnet-labs/issue/GHO-75).
4. **Ship a newer openmanetd.** `ekh-1.3.10` lacks the 360 px layout fix (`b2066e0`), self-hosted fonts (`675fc2c`; `ekh-1.3.10` loads Google Fonts from `frontend/index.html`, which fails offline), LuCI bookkeeping, mesh-join QR and the V1 battery profile. Owner [GHO-80](https://linear.app/ghostnet-labs/issue/GHO-80).
5. **Firmware and package sources.** Online sysupgrade checks `OpenMANET/firmware`; opkg feeds point at `openmanet.github.io`. Owner [GHO-77](https://linear.app/ghostnet-labs/issue/GHO-77).
6. **Sign-in.** Two sessions and two logins; empty-root-password PAM behaviour unverified. Owner [GHO-72](https://linear.app/ghostnet-labs/issue/GHO-72).
7. **Daemon-owned settings.** Mark in LuCI (or hide) what openmanetd rewrites: mesh bridge address and DHCP pool, batmesh1 options, tailscale enable. Owner [GHO-74](https://linear.app/ghostnet-labs/issue/GHO-74).
8. **Reboot button.** Backend exists, no UI. Owner [GHO-76](https://linear.app/ghostnet-labs/issue/GHO-76).

Left in Advanced for the first release (no OM work): firewall, services/startup, packages, backup/restore, NTP, LAN/DHCP editing.

## 8. Browser and board support proposal

Proposal only; acceptance runs belong to [GHO-78](https://linear.app/ghostnet-labs/issue/GHO-78) and [GHO-79](https://linear.app/ghostnet-labs/issue/GHO-79).

| Browser | Viewport | Must pass |
|---|---|---|
| Chrome desktop (current stable) | 1280 px | All rows marked Default; Advanced → LuCI → back |
| Safari iOS (current major) | 360 px | Same, plus accepting the self-signed cert on :8081 and on :443 |
| Chrome Android (current stable) | 360 px | Same as Safari iOS |

Web PTT needs a secure context for the microphone, and `SharedArrayBuffer` needs a secure context plus the COOP/COEP headers (inferred from `coiMiddleware` and browser rules), so Comms must be tested over HTTPS on both phones.

| Board | Firmware target | Status |
|---|---|---|
| CM5 POC | `bcm2712_mm8108-usb` (`firmware:boards/ekh-bcm2712/target_diffconfig`; board id `bcm2712,mm8108-usb` in `openmanetd:internal/util/board/board_type.go`) | Required |
| Raspberry Pi 4 / CM4 | `bcm2711_mm6108-spi`, `-sdio`, `bcm2711_mm8108-usb` (`firmware:boards/ekh-bcm2711/target_diffconfig`) | Required (one variant) |
| Raspberry Pi 3 | `bcm2710_mm6108-*` (`firmware:boards/ekh-bcm2710/target_diffconfig`) | Optional |
| Ghostnet V1 | `ghostnet,v1` | When hardware exists |
