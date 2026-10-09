# Unified UI physical-node acceptance plan (GHO-79)

**Owner:** [GHO-79](https://linear.app/ghostnet-labs/issue/GHO-79) (physical-node acceptance and failure/recovery validation)  
**Status:** Ready to run, written 2026-10-09. Not run: the bench hardware has not arrived. This file is the checklist; results do not go here.  
**Target:** the CM5 POC node ([bring-up runbook](../poc/bring-up-runbook.md), [bench topology](../poc/bench-bom-and-topology.md)). A second POC node is needed for the mesh and PTT steps.

## How to use it

1. Copy this file, fill in the run record and every Result box, and attach the copy to [GHO-79](https://linear.app/ghostnet-labs/issue/GHO-79) with the evidence named in each step (screenshots, command output, logs).
2. Mark each step **Pass**, **Fail** or **N/A**. N/A needs a reason (hardware missing, feature not in this image). File every Fail as a Linear issue and link it next to the box.
3. Steps assume the node is already brought up per runbook sections 1 to 3. Never transmit with an open antenna port.
4. Owner acceptance (section J) is required before any default cutover (D-036, D-038).

## Run record

| Item | Value |
|---|---|
| Date, tester | |
| Firmware commit and Actions run (or release tag) | |
| Image file name and `sha256sum` | |
| `feeds.conf.default` openmanet pin (packages commit) | |
| openmanetd package (`opkg list-installed openmanetd`) and source commit | |
| Contains openmanetd [#22](https://github.com/ghostnet-labs/openmanetd/pull/22) (proxy, Advanced), [#24](https://github.com/ghostnet-labs/openmanetd/pull/24) (reboot), [GHO-75](https://linear.app/ghostnet-labs/issue/GHO-75) first-boot switch, [GHO-77](https://linear.app/ghostnet-labs/issue/GHO-77) `releasesRepo` | yes / no for each |
| Contains packages [#14](https://github.com/ghostnet-labs/packages/pull/14) (Back to OpenMANET) and [#15](https://github.com/ghostnet-labs/packages/pull/15) (managed-setting warnings) | yes / no for each |
| Previous image used for the upgrade and rollback steps | |
| Node 1 (CM5) and node 2: board name (`cat /tmp/sysinfo/board_name`), radios fitted | |
| Clients: laptop Chrome version; iPhone Safari version; Android Chrome version | |
| Management paths available: Ethernet, node Wi-Fi AP, over the mesh from node 2 | |

## A. First boot

Fresh flash of the image under test (runbook §1), no saved config.

| # | Step | Expected | Result |
|---|---|---|---|
| A1 | Power on with Ethernet connected. Find the node's address (console, DHCP lease or `192.168.1.1`). | Node boots; SSH as `root` works. | ☐ Pass ☐ Fail ☐ N/A |
| A2 | Open `https://<node>:8081/` in laptop Chrome. Accept the certificate. | With the D-038 change in the image: the OpenMANET setup wizard opens. Without it: the login page; record which. | ☐ Pass ☐ Fail ☐ N/A |
| A3 | Open `http://<node>/`. | With D-038: LuCI login, no Morse landing page or wizard redirect. Without D-038: LuCI's Morse landing (expected today). | ☐ Pass ☐ Fail ☐ N/A |
| A4 | Complete the OpenMANET wizard as mesh gate (node 1), with a root password. | Apply finishes; the node may reboot and renumber. Reconnect at the new address or `<hostname>.local`. | ☐ Pass ☐ Fail ☐ N/A |
| A5 | Over SSH: `uci get luci.wizard.used; uci -q get luci.main.homepage; grep -A3 '^setup:' /etc/openmanetd/config.yml`. | `luci.wizard.used=1`; homepage unset or not a wizard page; `setup.complete: true`. | ☐ Pass ☐ Fail ☐ N/A |
| A6 | Sign in at `https://<node>:8081/` with root and the new password. Then try an empty password on a second fresh flash if time allows. | Correct password signs in, wrong password is refused. Record empty-password behavior for [GHO-72](https://linear.app/ghostnet-labs/issue/GHO-72). | ☐ Pass ☐ Fail ☐ N/A |
| A7 | Reload `http://<node>/` after the wizard. | LuCI does not redirect to its own wizard. | ☐ Pass ☐ Fail ☐ N/A |

## B. Upgrade with an existing configuration

Start from the previous image (run record), configured with LuCI's wizard as a mesh point, with a custom hostname, HaLow channel and password.

| # | Step | Expected | Result |
|---|---|---|---|
| B1 | Save `uci export > /tmp/before.uci` and a copy of `/etc/openmanetd/config.yml` off the node. Download a backup from LuCI → System → Backup / Flash Firmware. | Backup archive downloads. | ☐ Pass ☐ Fail ☐ N/A |
| B2 | Settings → Firmware: upload the image under test with **Preserve configuration** checked. | Image passes the compatibility check, flashes and reboots. | ☐ Pass ☐ Fail ☐ N/A |
| B3 | After reboot, diff `uci export` against `before.uci`, and compare `config.yml`. | Hostname, wireless, network and password are kept. Differences are limited to ones a new package intends; record each. | ☐ Pass ☐ Fail ☐ N/A |
| B4 | Open `https://<node>:8081/`. | Login page, not the setup wizard (the LuCI-configured node counts as set up through `luci.wizard.used`). | ☐ Pass ☐ Fail ☐ N/A |
| B5 | Check the mesh rejoins (`batctl n` on both nodes). | Peer present within 2 minutes of boot. | ☐ Pass ☐ Fail ☐ N/A |
| B6 | Settings → Firmware → Check for Updates (node has internet over Ethernet). | Lists only ghostnet-labs/firmware releases that carry a `sha256sums` asset; with none published, offers no update. If the image lacks `releasesRepo` (GHO-77) and upstream releases appear, record it as Fail and do not install. | ☐ Pass ☐ Fail ☐ N/A |

## C. Radio and network changes, readback after reboot

| # | Step | Expected | Result |
|---|---|---|---|
| C1 | Settings → Wireless: change HaLow channel and TX power. Save. | Saved without error. `uci show wireless` shows the new values. `iw dev` reflects them after the apply. | ☐ Pass ☐ Fail ☐ N/A |
| C2 | Settings → General: change the hostname. | `uci get system.@system[0].hostname` shows it. | ☐ Pass ☐ Fail ☐ N/A |
| C3 | Settings → General → Reboot (or LuCI → System → Reboot if #24 is not in the image). | The page reports going down, then back online. | ☐ Pass ☐ Fail ☐ N/A |
| C4 | Reconnect: accept the new certificate, sign in again. | Works at the same address; the browser shows a certificate warning again (new self-signed cert per start). | ☐ Pass ☐ Fail ☐ N/A |
| C5 | Read back C1 and C2 in the OpenMANET UI, in LuCI (Network → Wireless, System), and with `uci`. | All three agree with the values set. | ☐ Pass ☐ Fail ☐ N/A |
| C6 | Change HaLow TX power in LuCI. Reopen Settings → Wireless. | The OpenMANET page shows LuCI's value. | ☐ Pass ☐ Fail ☐ N/A |
| C7 | LuCI → Network → Interfaces, edit `ahwlan`; Network → Wireless, edit the `batmesh1` mesh interface. | A warning names OpenMANET as owner on the page and in the edit dialog ([GHO-74](https://linear.app/ghostnet-labs/issue/GHO-74)). | ☐ Pass ☐ Fail ☐ N/A |
| C8 | Interrupted change: start a Settings → Wireless save and pull power within 2 s. Power up. | Node boots and is reachable; wireless config is either all old or all new values. Record which. | ☐ Pass ☐ Fail ☐ N/A |
| C9 | Interrupted change: close the browser tab during a save, reopen. | Same as C8, without a reboot. | ☐ Pass ☐ Fail ☐ N/A |
| C10 | Address change: in LuCI set `ahwlan` to a different address and save and apply. Wait 3 minutes. | Record whether the daemon keeps or rewrites it (address reservation). Node is reachable at the resulting address or `<hostname>.local`; LuCI's IP-change rollback does not strand the node. | ☐ Pass ☐ Fail ☐ N/A |
| C11 | Reach `https://<node>:8081/` over each management path in the run record (Ethernet, node AP, over the mesh from node 2). | UI loads and signs in on each available path. | ☐ Pass ☐ Fail ☐ N/A |

## D. Advanced access and return

Set `frontend.luciProxy.enable: true` in `/etc/openmanetd/config.yml` if the image does not already. No restart needed.

| # | Step | Expected | Result |
|---|---|---|---|
| D1 | Reload `https://<node>:8081/`. | **Advanced** ("Full router settings (LuCI)") appears in the sidebar; on a 360 px phone it is in the More sheet with a 44 px row. | ☐ Pass ☐ Fail ☐ N/A |
| D2 | Click Advanced. | Full page load of `https://<node>:8081/cgi-bin/luci/`, same origin, LuCI login. | ☐ Pass ☐ Fail ☐ N/A |
| D3 | Sign in to LuCI. In dev tools, check cookies. | LuCI loads. `sysauth_http` with path `/cgi-bin/luci/`; the OpenMANET `session` cookie is unchanged. | ☐ Pass ☐ Fail ☐ N/A |
| D4 | Open Status, Network, System pages and the Topology view in LuCI. | All load, no missing styles or scripts, no mixed-content errors. | ☐ Pass ☐ Fail ☐ N/A |
| D5 | Download a backup and upload a small file (Backup / Flash Firmware, restore dialog, cancel before applying) through the proxy. | Download completes; upload reaches the confirm step. | ☐ Pass ☐ Fail ☐ N/A |
| D6 | Click **Back to OpenMANET** in the LuCI header. | Returns to `https://<node>:8081/`, still signed in to OpenMANET. | ☐ Pass ☐ Fail ☐ N/A |
| D7 | Open `http://<node>/cgi-bin/luci/` directly, then Back to OpenMANET. | Goes to `https://<node>:8081/`. | ☐ Pass ☐ Fail ☐ N/A |
| D8 | Log out of LuCI. Return to OpenMANET. Then sign out of OpenMANET and open Advanced. | Each logout affects only its own UI. | ☐ Pass ☐ Fail ☐ N/A |
| D9 | Leave LuCI idle past its session timeout, then click a page. | LuCI asks for login again on the same origin. | ☐ Pass ☐ Fail ☐ N/A |
| D10 | Install `luci-ssl` or set `uhttpd.main.redirect_https=1`, restart uhttpd, open Advanced. Revert afterwards. | Record whether the browser leaves the `:8081` origin ([design §4](unified-ui-design.md#4-sign-in-sessions-and-csrf) bench check 2). | ☐ Pass ☐ Fail ☐ N/A |
| D11 | Repeat D1, D2 and D6 on iPhone Safari and Android Chrome. | Same results. | ☐ Pass ☐ Fail ☐ N/A |

## E. Mesh, topology, GPS and battery

| # | Step | Expected | Result |
|---|---|---|---|
| E1 | With node 2 configured as mesh point (see [mesh test plan](../poc/mesh-test-plan.md) setup), open Topology on node 1. | Node 2 appears with a link; matches `batctl n` and `batctl o`. | ☐ Pass ☐ Fail ☐ N/A |
| E2 | Dashboard peer count and link quality. | Agree with `iw dev <halow> station dump` within one refresh. | ☐ Pass ☐ Fail ☐ N/A |
| E3 | Power node 2 off, then on. | Topology drops, then shows node 2 again; record both times. | ☐ Pass ☐ Fail ☐ N/A |
| E4 | GPS / GNSS page with the antenna in sky view. | 3D fix; position and satellite count agree with `gpspipe -w` TPV and SKY. | ☐ Pass ☐ Fail ☐ N/A |
| E5 | Disconnect the GNSS antenna or receiver. | Page shows loss of fix; topbar GPS chip changes state. Reconnect restores it. | ☐ Pass ☐ Fail ☐ N/A |
| E6 | Dashboard battery card on UPS power. | Value agrees with the INA219 reading from `bench-check.sh`; unplug and replug external power and record the change. | ☐ Pass ☐ Fail ☐ N/A |

## F. Browser PTT over TLS

Set `comms.enable: true` and `comms.controlSource: web` in `config.yml` on both nodes.

| # | Step | Expected | Result |
|---|---|---|---|
| F1 | iPhone Safari at `https://<node1>:8081/`, Comms page. Allow the microphone. | Permission prompt appears; Comms page ready. | ☐ Pass ☐ Fail ☐ N/A |
| F2 | In the browser console, `crossOriginIsolated`. | `true`. | ☐ Pass ☐ Fail ☐ N/A |
| F3 | Hold PTT and speak; listen on node 2 (a second browser on its Comms page, or its audio device). | Audio heard on the same talk group; release ends TX. Record delay and quality. | ☐ Pass ☐ Fail ☐ N/A |
| F4 | Talk from node 2. | Audio plays in the phone browser. | ☐ Pass ☐ Fail ☐ N/A |
| F5 | Repeat F1 to F4 on Android Chrome. | Same. | ☐ Pass ☐ Fail ☐ N/A |
| F6 | Open `http://<node1>:8080/` Comms page. | Microphone is refused (not a secure context); record the message shown. | ☐ Pass ☐ Fail ☐ N/A |
| F7 | Lock the phone during RX, unlock. | Comms reconnects without a page reload, or shows a clear reconnect state. | ☐ Pass ☐ Fail ☐ N/A |

## G. Daemon, dashboard and LuCI failure

| # | Step | Expected | Result |
|---|---|---|---|
| G1 | `/etc/init.d/openmanetd stop`. | `:8081` and `:8080` refuse connections. `http://<node>/` (LuCI) still works. | ☐ Pass ☐ Fail ☐ N/A |
| G2 | `/etc/init.d/openmanetd start`. | UI back within 30 s; operator must sign in again. | ☐ Pass ☐ Fail ☐ N/A |
| G3 | `kill -9 $(pidof openmanetd)`. | procd restarts it within about 5 s. | ☐ Pass ☐ Fail ☐ N/A |
| G4 | Kill it 6 times in a row within an hour. | procd stops respawning after 5 retries; LuCI and SSH stay up; `/etc/init.d/openmanetd restart` brings it back. | ☐ Pass ☐ Fail ☐ N/A |
| G5 | Set `frontend.luciProxy.upstream: ftp://x` and reload the page. | Advanced entry disappears; error logged; OpenMANET UI otherwise fine. Revert. | ☐ Pass ☐ Fail ☐ N/A |
| G6 | Break `config.yml` syntax (save a copy first), restart openmanetd. | Record behavior. LuCI on `:80` and SSH remain usable to repair it. Restore the copy. | ☐ Pass ☐ Fail ☐ N/A |
| G7 | `/etc/init.d/uhttpd stop`, click Advanced. | 502 page that points to the direct route. OpenMANET UI unaffected. Start uhttpd again. | ☐ Pass ☐ Fail ☐ N/A |
| G8 | `/etc/init.d/rpcd stop`, try LuCI login. | LuCI login fails; OpenMANET UI and its login still work. Start rpcd again. | ☐ Pass ☐ Fail ☐ N/A |
| G9 | Over SSH run `openmanetd setup-reset`, then `/etc/init.d/openmanetd restart`. | Behaves as [setup-wizard-recovery.md](https://github.com/ghostnet-labs/openmanetd/blob/main/docs/setup-wizard-recovery.md) describes; record whether the wizard opens (it needs `setup.enabled: true`). Re-run the wizard or restore the config afterwards. | ☐ Pass ☐ Fail ☐ N/A |
| G10 | Reboot during a dashboard session left open in a tab. | The tab shows a disconnected state, then recovers or asks for login once the node is back. | ☐ Pass ☐ Fail ☐ N/A |

## H. Rollback

| # | Step | Expected | Result |
|---|---|---|---|
| H1 | Settings → Firmware: upload the previous image with Preserve configuration checked. | Node boots the previous version (`cat /etc/openwrt_release`, `opkg list-installed openmanetd`) and is reachable. Record which settings survive. | ☐ Pass ☐ Fail ☐ N/A |
| H2 | Restore the B1 backup from LuCI on `http://<node>/`. | Node returns to the B1 configuration after reboot; mesh rejoins. | ☐ Pass ☐ Fail ☐ N/A |
| H3 | Upgrade again to the image under test from LuCI's flash page (not the OpenMANET UI). | Same results as B2 to B5. | ☐ Pass ☐ Fail ☐ N/A |
| H4 | Last resort: re-flash the eMMC with `rpiboot` (runbook §1) and restore the backup. | Node recovers. Record the time it took. | ☐ Pass ☐ Fail ☐ N/A |

## I. Unsupported and not tested

List here, in the filled copy, every board, browser or feature that was not tested and why (for example no second node, no OpenVLM device, Raspberry Pi 4 variant not on the bench). The required set is in the [audit §8](unified-ui-audit.md#8-browser-and-board-support-proposal).

## J. Owner acceptance

| Item | Value |
|---|---|
| Open Fail issues (links) | |
| Owner decision: accept for default cutover / accept with listed gaps / reject | |
| Justin, date | |
