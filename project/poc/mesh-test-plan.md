# Two-node mesh test plan (GHO-31)

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
- The wizard only offers the Wi-Fi backhaul on an MT7915/MT7916 radio. With the AW7916-AED fitted it is the real software path. With an ath10k card (GW17032) it isn't offered, and the secondary link has to be written by hand (Appendix A), which tests the radios but not the shipped software.

## Setup (both nodes)

1. Attenuators on both HaLow antenna ports (about 50 dB total between the nodes), or nodes at least 1 m apart with whips vertical. Never transmit into an open port.
2. Both nodes on the bench switch over Ethernet for SSH. Note each node's Ethernet IP.
3. Run the setup wizard on each node:
   - Node 1: role **Mesh gate**. Node 2: role **Mesh point**.
   - Same HaLow mesh ID, passphrase, channel and bandwidth on both. Use the US default channel and 2 MHz unless a test says otherwise.
   - Wi-Fi (access points step): set the 2.4 GHz radio to **Mesh backhaul**, with the same mesh ID and passphrase on both. Keep channel 8 and 40 MHz.
4. After the wizard reboots each node, copy [`mesh-snap.sh`](mesh-snap.sh) to both and run `sh mesh-snap.sh > snap-node1-setup.txt`. Attach both files.

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

## Appendix A: secondary link by hand (ath10k only)

Use this only if the Wi-Fi card is not MT7915/MT7916. It writes the same
option set the wizard uses, after the wizard has finished with no Wi-Fi
backhaul. `radio1` is the ath10k radio; check with `uci show wireless`.
ath10k has no HE modes, so use HT40.

```sh
R=radio1                 # ath10k wifi-device
ID=openmanet-wifi        # same on both nodes
KEY=changeme-wifi        # same on both nodes
uci batch <<EOF
set wireless.$R.channel='8'
set wireless.$R.htmode='HT40'
set wireless.$R.disabled='0'
set wireless.batmesh1_$R=wifi-iface
set wireless.batmesh1_$R.device='$R'
set wireless.batmesh1_$R.network='batmesh1'
set wireless.batmesh1_$R.mode='mesh'
set wireless.batmesh1_$R.mesh_id='$ID'
set wireless.batmesh1_$R.key='$KEY'
set wireless.batmesh1_$R.encryption='sae'
set wireless.batmesh1_$R.mesh_fwding='0'
set wireless.batmesh1_$R.mesh_nolearn='1'
set wireless.batmesh1_$R.mesh_rssi_threshold='-80'
set wireless.batmesh1_$R.mcast_rate='24000'
set wireless.batmesh1_$R.mesh_retry_timeout='255'
set wireless.batmesh1_$R.mesh_confirm_timeout='255'
set wireless.batmesh1_$R.mesh_holding_timeout='255'
EOF
uci commit && reload_config
```

The wizard always creates the `network.batmesh1` hardif on `bat0`, so only the
wireless side is needed. Check with `uci show network.batmesh1`.
