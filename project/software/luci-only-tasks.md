# LuCI-only tasks and retirement criteria

**Owner:** [GHO-81](https://linear.app/ghostnet-labs/issue/GHO-81) (evaluate later LuCI retirement)  
**Status:** Evaluation, 2026-10-09. It decides nothing.

**LuCI is not removed in this project.** D-036 keeps LuCI behind Advanced and makes full removal a separate later decision. Removing LuCI, hiding one of its pages, or retiring the uhttpd recovery route each needs its own D-row in [../decisions.md](../decisions.md), backed by the evidence below and Justin's sign-off.

The task rows come from the [audit parity matrix](unified-ui-audit.md#2-parity-matrix). "OM" is the OpenMANET UI.

## 1. Tasks only LuCI can do

| Task | LuCI page | Migrate to OM when | Retire from LuCI when |
|---|---|---|---|
| Firewall zones, rules, port forwards | `luci-app-firewall` | Operators need a field change more than once per deployment, and an OM page can show the zones the wizard and BLOS write (`openmanetd:internal/firewall/firewall.go`) without hiding them | Not in this project. An OM page edits every rule type the image uses, and a bench run shows no zone OM cannot read back |
| LAN interfaces and DHCP editing | `luci-mod-network` interfaces, DHCP | An OM editor exists that refuses or warns on the daemon-managed `ahwlan` address and pool (today's LuCI warning, [GHO-74](https://linear.app/ghostnet-labs/issue/GHO-74)) and rereads UCI on open | OM edits every interface and pool on the CM5 image, including address changes, with readback after reboot passing in [the acceptance plan](unified-ui-acceptance-plan.md) |
| Static routes, diagnostics (ping, traceroute, nslookup) | `luci-mod-network` routes, diagnostics | Field reports ask for in-UI diagnostics; the OM terminal already covers it for root users | OM offers the same diagnostics without a root shell |
| Services and startup | `luci-mod-system` startup | A daemon other than openmanetd needs routine operator control | OM can start, stop, enable and disable every init script in the image |
| Software packages | `luci-app-opkg` | A ghostnet package feed and signing key exist (opkg feeds point upstream today, D-039 follow-up, [GHO-77](https://linear.app/ghostnet-labs/issue/GHO-77)) | OM installs, removes and updates packages from that feed. Until a feed exists, keep it Advanced only |
| Backup and restore | `luci-mod-system` flash (`cgi-backup`, `cgi-upload`) | Before LuCI retirement is proposed; operators need a backup before every upgrade ([operator guide §6](unified-ui-operator-guide.md#6-firmware-updates)) | OM downloads and restores a sysupgrade backup, and a restore on the CM5 node returns the node to its prior state |
| Time servers (NTP) | `luci-mod-system` system | GNSS-disciplined time on the CM5 ([`43_cm5-ntpd-gps`](unified-ui-audit.md#2-parity-matrix)) needs an operator override | OM shows and edits NTP servers without breaking the GNSS/PPS config |
| Timezone after setup | `luci-mod-system` system | Low effort; the wizard already writes it (`openmanetd:internal/network/uci_system.go`) | OM Settings has a timezone field with readback |
| HaLow country, board config (BCF), raw radio options | `luci-app-morseconfig`, `luci-mod-network` wireless | A deployment needs another regulatory domain or BCF; changing them without safeguards risks illegal TX | Not in this project. Needs regulatory review as well as parity |
| Non-mesh wireless modes and deeper Wi-Fi options | `luci-mod-network` wireless | Never for Morse radios: OM rejects non-mesh mode there on purpose ([audit §2](unified-ui-audit.md#2-parity-matrix)) | Not in this project |
| Morse statistics and logs | Morse LuCI apps under `admin/statistics/morse` | Radio debugging moves to the field rather than the bench | OM shows the same counters, or the image drops the Morse apps by a separate decision |
| Live graphs, process list | `luci-mod-status` | Field debugging needs them more than the OM dashboard and logs give | OM covers them, or operators confirm they do not use them |
| SSH keys and dropbear settings | `luci-mod-system` admin | Fleet setup needs key-only SSH | OM manages `authorized_keys` and dropbear |
| Recovery when openmanetd is down | Whole LuCI on uhttpd `:80` | Never migrates: it exists because OM is down | Only after another recovery route that does not depend on openmanetd (for example SSH plus a documented CLI, or a minimal static page) passes the failure section of [the acceptance plan](unified-ui-acceptance-plan.md) |

## 2. Shared tasks LuCI can stop owning

These already have an OM page. LuCI's copy can be hidden (by a separate decision) once the criterion holds.

| Task | Criterion |
|---|---|
| First-boot wizard | D-038 has switched first boot to OM and the CM5 bench run passed. LuCI's Morse wizard stays installed for configured nodes until then ([GHO-75](https://linear.app/ghostnet-labs/issue/GHO-75)) |
| Hostname, password, reboot, factory reset, firmware upload, logs | The OM page passes its readback or recovery step on the CM5 node, and the reboot button ([openmanetd#24](https://github.com/ghostnet-labs/openmanetd/pull/24)) has shipped |
| HaLow channel, bandwidth, power; Wi-Fi mesh backhaul | OM writes UCI and LuCI shows the same values after reboot ([acceptance plan §C](unified-ui-acceptance-plan.md#c-radio-and-network-changes-readback-after-reboot)) |

## 3. Evidence a LuCI retirement decision needs

A proposal to remove LuCI from the image must show all of these:

1. Every row in section 1 is migrated, or explicitly accepted as dropped, with a reason.
2. A recovery route that does not depend on openmanetd, tested by stopping and breaking openmanetd on the CM5 node.
3. Firmware upgrade, backup and restore, and factory reset all work without LuCI.
4. No shipped package needs LuCI (Morse apps, `luci-app-ekhwizards`, optional extras such as rangetest).
5. The [acceptance plan](unified-ui-acceptance-plan.md) passes with LuCI absent, on every required board in the [audit §8](unified-ui-audit.md#8-browser-and-board-support-proposal).
6. Justin's sign-off, recorded as a new D-row.
