# Unified UI operator guide

**Owner:** [GHO-81](https://linear.app/ghostnet-labs/issue/GHO-81) (publish unified-UI guidance)  
**Status:** Written 2026-10-09 from the code and open PRs listed below. No ghostnet-labs firmware release contains the unified UI yet, so check the "Before you rely on this guide" list against the image you run.  
**Design:** routing, sign-in and recovery are owned by [unified-ui-design.md](unified-ui-design.md) (D-037). This guide tells an operator how to use them.

## Before you rely on this guide

This guide describes the integrated image. On 2026-10-09 these parts were not yet in any firmware image:

| Part | State | Link |
|---|---|---|
| LuCI proxy and the Advanced entry | Pending, openmanetd PR | [openmanetd#22](https://github.com/ghostnet-labs/openmanetd/pull/22) ([GHO-70](https://linear.app/ghostnet-labs/issue/GHO-70), [GHO-71](https://linear.app/ghostnet-labs/issue/GHO-71)) |
| Reboot button on Settings | Pending, openmanetd PR | [openmanetd#24](https://github.com/ghostnet-labs/openmanetd/pull/24) ([GHO-76](https://linear.app/ghostnet-labs/issue/GHO-76)) |
| A newer openmanetd in the package (the shipped package builds the `ekh-1.3.10` line) | Pending | [GHO-80](https://linear.app/ghostnet-labs/issue/GHO-80) |
| "Back to OpenMANET" link in LuCI | Merged in packages `24.10` ([packages#14](https://github.com/ghostnet-labs/packages/pull/14)); not yet in a firmware feed pin | [GHO-73](https://linear.app/ghostnet-labs/issue/GHO-73) |
| LuCI warnings on daemon-managed settings | Merged in packages `24.10` as openmanetd 1.3.10-9 ([packages#15](https://github.com/ghostnet-labs/packages/pull/15)); not yet in a firmware feed pin | [GHO-74](https://linear.app/ghostnet-labs/issue/GHO-74) |
| OpenMANET wizard as the first-boot route | Decided (D-038), ships with the next openmanetd bump, gated on a CM5 bench run | [GHO-75](https://linear.app/ghostnet-labs/issue/GHO-75) |
| Online updates from ghostnet-labs/firmware | Decided (D-039); `sha256sums` asset pending in [firmware#46](https://github.com/ghostnet-labs/firmware/pull/46); `sysupgrade.releasesRepo` pending in an openmanetd PR | [GHO-77](https://linear.app/ghostnet-labs/issue/GHO-77) |

The firmware feed pin that brings package changes into an image is described in the [developer guide](unified-ui-developer-guide.md#4-release-procedure).

## 1. One address

Open **`https://<node>:8081/`**. `<node>` is the node's IP address or `<hostname>.local`.

- The node uses a self-signed certificate unless one is configured (`frontend.tlsCertFile`, `frontend.tlsKeyFile`). openmanetd makes a new certificate every time it starts (`openmanetd:internal/frontend/tls.go`), so expect the browser warning again after a reboot or a daemon restart.
- `http://<node>:8080/` serves the same UI over plain HTTP. Browser PTT does not work there, because the microphone needs HTTPS.
- Sign in with the node's root password. This is the same password LuCI uses.
- Your OpenMANET session lasts up to 24 hours. It is kept in memory, so a reboot or daemon restart signs you out.

## 2. Primary tasks

These live in the OpenMANET UI. The left sidebar (or the bottom bar on a phone) has them.

| Task | Where |
|---|---|
| First-boot setup | Setup wizard, shown at `https://<node>:8081/` on a fresh node once D-038 ships. Until then, first boot is LuCI's wizard at `http://<node>/`. |
| Node health | Dashboard (the node, mesh, GPS and battery chips also sit at the top of every page) |
| Mesh view | Topology |
| Voice / PTT | Comms |
| GPS fix | GPS / GNSS |
| Satellite / tunnel link | BLOS |
| Hostname, password, restart the daemon, reboot | Settings → General (the reboot button is pending [openmanetd#24](https://github.com/ghostnet-labs/openmanetd/pull/24)) |
| HaLow channel, bandwidth, power; Wi-Fi mesh backhaul and AP | Settings → Wireless |
| Interfaces, DHCP leases (view only) | Settings → Network |
| Firmware update and factory reset | Settings → Firmware |
| Root shell | Settings → Terminal |
| System and kernel logs | Settings → Logs |

Radio and network settings are stored in OpenWrt's UCI files. If you change one in LuCI, reopen the OpenMANET page to see the new value.

## 3. Advanced (LuCI)

Use Advanced for anything not in the table above: firewall, LAN and DHCP editing, services, packages, backup and restore, NTP, country and board-config radio options. The full list is in [luci-only-tasks.md](luci-only-tasks.md).

- The **Advanced** entry ("Full router settings (LuCI)") is in the sidebar, and in the **More** sheet on a phone. It appears only when the proxy is on: `frontend.luciProxy.enable: true` in `/etc/openmanetd/config.yml` (default off). Reload the page after changing the flag.
- It opens `https://<node>:8081/cgi-bin/luci/` as a full page.
- **LuCI has its own login.** Sign in as `root` with the root password. Signing in to OpenMANET does not sign you in to LuCI, and signing out of LuCI does not sign you out of OpenMANET.
- LuCI marks settings that openmanetd rewrites by itself: the mesh bridge `ahwlan` address and DHCP pool, and the `batmesh1` mesh tuning options ([GHO-74](https://linear.app/ghostnet-labs/issue/GHO-74)). An edit there can be undone by the daemon, so leave those values to openmanetd.
- **To return**, use **Back to OpenMANET** in the LuCI header ([GHO-73](https://linear.app/ghostnet-labs/issue/GHO-73)), the browser's Back button, or open `https://<node>:8081/`. You stay signed in to OpenMANET.

## 4. Reconnect after a reboot

1. Start the reboot from Settings → General (pending [openmanetd#24](https://github.com/ghostnet-labs/openmanetd/pull/24)) or LuCI → System → Reboot. The OpenMANET page reports when the node goes down and when it answers again; it usually takes about a minute.
2. Accept the new certificate warning.
3. Sign in again. Sign in to LuCI again too if you use Advanced.

If the node does not come back at the same address:

- openmanetd can renumber the mesh bridge and reboot by itself after setup or on an address conflict (`openmanetd:internal/mgmt/address_reservation.go`). Try `https://<hostname>.local:8081/`. The `.local` name needs an openmanetd newer than the shipped `ekh-1.3.10` line ([GHO-80](https://linear.app/ghostnet-labs/issue/GHO-80)).
- Or connect over Ethernet and use the address your DHCP server or the node's console shows.

## 5. Recovery

Try these in order.

| Problem | Do this |
|---|---|
| OpenMANET UI does not load, or Advanced shows a 502 error | Open plain LuCI at **`http://<node>/`** (uhttpd, port 80). It does not depend on openmanetd. |
| Advanced is missing or broken | Use `http://<node>/cgi-bin/luci/` directly. To turn the proxy off, set `frontend.luciProxy.enable: false` in `/etc/openmanetd/config.yml`. |
| openmanetd keeps crashing | procd restarts it up to 5 times, then gives up (`packages:openmanetd/files/openmanetd.init`). LuCI on port 80 and SSH stay up. Check Status → System Log in LuCI, or `logread -e openmanetd` over SSH. |
| Setup left the node unreachable | Over SSH or serial, run `openmanetd setup-reset`, then `/etc/init.d/openmanetd restart` ([openmanetd docs/setup-wizard-recovery.md](https://github.com/ghostnet-labs/openmanetd/blob/main/docs/setup-wizard-recovery.md)). It also turns off the OpenMANET login, so use it only on a node you are recovering. |
| Nothing on the web works | SSH as `root` (dropbear is on by default). |
| The configuration is beyond repair | Factory reset from Settings → Firmware, LuCI → System → Backup / Flash Firmware, or `firstboot` over SSH. This erases all settings. |

## 6. Firmware updates

- **Upload an image:** Settings → Firmware. Leave **Preserve configuration** checked to keep your settings. LuCI → System → Backup / Flash Firmware also works.
- **Online updates:** Settings → Firmware → **Check for Updates** lists GitHub releases. A release is offered only if it has a `sha256sums` asset, which openmanetd uses to verify the download (`openmanetd:internal/sysupgrade/manager.go`). Nodes will check ghostnet-labs/firmware releases (D-039). Until the `releasesRepo` setting ships ([GHO-77](https://linear.app/ghostnet-labs/issue/GHO-77)) and ghostnet-labs/firmware publishes a release with that asset ([firmware#46](https://github.com/ghostnet-labs/firmware/pull/46)), do not install online updates on a ghostnet node: the current code checks upstream OpenMANET/firmware, whose images would replace the ghostnet build.
- **Before any update**, download a backup from LuCI → System → Backup / Flash Firmware. To roll back, flash the previous image the same way, then restore the backup if needed.
