# Two-node mesh test plan (GHO-31)

## Expanded capability scope

The current capability contract is [Maer requirements](../requirements/maer-capabilities.md) (D-029 through D-032). This document describes the selected baseline and does not by itself demonstrate the expanded contract. GHO-50 owns POC hardware reconciliation; GHO-55 owns V1 impact and freeze disposition. 


How to run [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) on the two
bench nodes once both pass the bring-up runbook
([bring-up-runbook.md](bring-up-runbook.md) steps 1–3). Results, logs and
pass/fail go on GHO-31, not in this file.

## What the software does

The node is configured by the openmanetd setup wizard (web UI, **Setup**). It
builds one batman-adv mesh (`bat0`) on top of two 802.11s links:

| Link | batman-adv hardif | Radio | Who configures it |
| -- | -- | -- | -- |
| Primary | `batmesh0` | HaLow (MM8108), wifi-iface `default_<radio>` | Wizard, always |
| Secondary (Wi-Fi backhaul) | `batmesh1` | 2.4 GHz Wi-Fi, wifi-iface `batmesh1_<radio>` | Wizard, only when the radio is MediaTek MT7915/MT7916 |

Facts from openmanetd (`internal/network/uci_wireless.go`,
`internal/openmanet/server/handlers/setup_phases.go`):

- 802.11s forwarding and path learning are off (`mesh_fwding 0`, `mesh_nolearn 1`); batman-adv routes.
- The secondary link defaults to channel 8, HE40, SAE, `mesh_rssi_threshold -80`, `mcast_rate 24000`. It is meant to be faster than HaLow at short range, not to add range.
- `bat0` sits in the `br-ahwlan` bridge with the Ethernet ports. A mesh-gate advertises `gw_mode server`, a mesh-point `client`.
- Multicast: `bat0 multicast_mode 0` by default (batman floods all multicast). ATAK SA is 239.2.3.1, ATAK chat 224.10.10.1, voice talk groups 239.192.41.1:38801–38864.
- The wizard only offers the Wi-Fi backhaul on an MT7915/MT7916 radio. The POC Wi-Fi card is the AsiaRF AW7916-AED (MT7916, `mt7915e`) on a Sintech M.2 M-key to A/E-key adapter in the carrier's M-key slot (A-09, [D-034](../decisions.md)), so these tests run the shipped wizard path on both radios. No hand-written secondary link is needed or supported; the GW17032 fallback is retired (R-22).

## Setup (both nodes)

1. Attenuators on both HaLow antenna ports (about 50 dB total between the nodes), or nodes at least 1 m apart with whips vertical. Never transmit into an open port.
2. On each node, confirm the Wi-Fi card is the AW7916-AED on its M-key adapter (A-09, D-034): `lspci` lists the MediaTek MT7916 and `mesh-snap.sh` shows an `mt7915e` netdev. A node without it cannot run the Wi-Fi backhaul tests; record that on GHO-31 instead of configuring the link by hand.
3. Both nodes on the bench switch over Ethernet for SSH. Note each node's Ethernet IP.
4. Run the setup wizard on each node:
   - Node 1: role **Mesh gate**. Node 2: role **Mesh point**.
   - Same HaLow mesh ID, passphrase, channel and bandwidth on both. Use the US default channel and 2 MHz unless a test says otherwise.
   - Wi-Fi (access points step): set the 2.4 GHz radio to **Mesh backhaul**, with the same mesh ID and passphrase on both. Keep channel 8 and 40 MHz.
5. After the wizard reboots each node, copy [`mesh-snap.sh`](mesh-snap.sh) to both and run `sh mesh-snap.sh > snap-node1-setup.txt`. Attach both files.

Unplug Ethernet from Node 2 for the radio tests. It is reachable over the mesh at its `ahwlan` address (from `mesh-snap.sh`).

## Tests

Run `sh bench-log.sh 5 > node<N>-<test>.csv &` on both nodes during every test. It logs power, temperature and per-radio TX bytes.

| # | Test | How | Pass | Record |
| -- | -- | -- | -- | -- |
| M1 | Association | `iw dev <halow> station dump` and `iw dev <wifi> station dump` on both | Each node lists the other on both radios, `mesh plink: ESTAB` | RSSI, TX/RX bitrate per link |
| M2 | batman-adv neighbours | `batctl n`, `batctl o`, `batctl if` | Node 2 shows Node 1 on both `batmesh0` and `batmesh1`; originator table has one best route | Throughput metric per hardif |
| M3 | Ping over the mesh | `ping -c 100 <node2 ahwlan IP>` from Node 1 | 0 % loss | min/avg/max/mdev |
| M4 | Throughput, Wi-Fi up | Node 2 `iperf -s`; Node 1 `iperf -c <node2> -t 30` and `-r` | Runs to completion | Mb/s each way; which hardif carried it (TX bytes in the CSV) |
| M5 | Throughput, HaLow only | `ifconfig <wifi> down` on both (or `wifi down <radio>`), repeat M4 | Traffic moves to `batmesh0`, no loss of SSH | Mb/s; recovery time from link down to traffic flowing |
| M6 | Latency under load | M4 running, `ping -i 0.2 -c 150` in parallel | No loss | RTT spread during load |
| M7 | Multicast (ATAK SA) | Node 2 `iperf -s -u -B 239.2.3.1 -p 6969`; Node 1 `iperf -c 239.2.3.1 -u -p 6969 -T 4 -b 100k -t 30` | Node 2 reports the stream | Loss %, jitter; repeat with Wi-Fi down |
| M8 | Simultaneous radios | M4 on Wi-Fi and a HaLow-only flow at the same time (bind with `iperf -c <ip> -B <local ahwlan IP>` while `batctl tp` runs on batmesh0) | Both run | Combined Mb/s, CPU temp, any driver errors in `dmesg` |
| M9 | HaLow radio reset | `wifi down <halow radio>; sleep 5; wifi up <halow radio>` on Node 2 with ping running | Mesh re-forms without reboot | Seconds to first reply; `dmesg` |
| M10 | Wi-Fi radio reset | Same for the Wi-Fi radio | Mesh re-forms | Seconds to first reply |
| M11 | Node power cycle | Pull Node 2 power during ping, restore | Node 2 rejoins | Seconds from power-on to first reply |
| M12 | Range trend (optional) | Step the attenuators or move a node; repeat M1 and M4 | — | RSSI vs Mb/s per radio; where batman switches hardif |
| M13 | GNSS during TX | `gpspipe -w` C/N0 while M8 runs ([D-020](../decisions.md)) | Fix holds | Average C/N0 idle vs TX |

After the tests, run `mesh-snap.sh` again on both nodes and attach the
output, `logread`, and `dmesg`.

## Known limitations to record

- Bench distance: two nodes on a bench saturate each other without attenuation. Throughput numbers are best-case.
- With only two nodes, there is no multi-hop routing. A third node is on [GHO-40](https://linear.app/ghostnet-labs/issue/GHO-40).
- POC radios aren't V1 radios: GW16167 vs GW16170 transmit power ([bench-bom-and-topology.md](bench-bom-and-topology.md) §1).
- The Wi-Fi card is the V1 card (B-03), but it is fed through the Sintech adapter and the carrier's M-key slot, not the V1 socket and +3V3_RADIO path. Wi-Fi current and temperature from these tests are POC evidence, not V1 socket qualification ([v1-3v3-rail.md](../hardware/v1-3v3-rail.md)).
