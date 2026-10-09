# V1 radio and dual-radio mesh validation

**Owner:** [GHO-22](https://linear.app/ghostnet-labs/issue/GHO-22): validate the selected radios and dual-radio mesh on the CM5  
**Status:** Procedure, not yet run. Captures, loop logs and pass/fail results go on GHO-22, never in this file.

This file owns how the V1 radios are validated: what to capture, which tests to run in which order, and how to tell supported behavior apart from unproven behavior. The radios and their selections are B-03 (AsiaRF AW7916-AED, MT7916, `mt7915e`) and the GW16170 HaLow card in [v1-selections.md](v1-selections.md). Their limits and risks are in [v1-reference.md](v1-reference.md) §5 to §7. V1 has no Bluetooth (D-026), so nothing here tests it.

Tools:

- [`v1-radio-validate.sh`](v1-radio-validate.sh) runs on the node. `capture` is read-only. `loop` resets or power-cycles one radio N times and logs a PASS/FAIL line per iteration.
- [`../poc/mesh-test-plan.md`](../poc/mesh-test-plan.md) and [`../poc/mesh-snap.sh`](../poc/mesh-snap.sh) are the two-node mesh tests and snapshot. They are reused unchanged on V1 nodes.
- [`../poc/bench-check-v1.sh`](../poc/bench-check-v1.sh) is the device and GPIO check that every node must pass first.

## Supported, advertised and unproven

Keep these three apart in every result posted on GHO-22. A capability flag in `iw phy` is not a working mesh link.

| Class | What | Evidence that moves it up |
|---|---|---|
| Configured by the shipped software | HaLow 802.11s as the primary `batmesh0` link, and 2.4 GHz Wi-Fi 802.11s as the `batmesh1` backhaul on an MT7915/MT7916 radio. The setup wizard builds both (mesh-test-plan.md, "What the software does"). | Mesh tests M1 to M13 pass on two V1 nodes |
| Advertised by the driver, not configured | Mesh point on the MT7916's 5 GHz phy. Nothing in the setup wizard puts the backhaul there. | `capture` shows mesh point and channels that may initiate TX on that phy, and the per-band link test in section 3 passes |
| Unproven | Any 6 GHz mesh link. Nothing in the software configures one. The kernel regulatory domain often marks 6 GHz channels no-IR, which blocks the beaconing a mesh point needs. The outdoor 6 GHz rules for this node are still open (v1-reference §5). | All three: `capture` under the deployed country code shows 6 GHz channels that may initiate TX; the section 3 link test passes on 6 GHz; and the regulatory question is answered on its own issue. Until then, report any 6 GHz result as "unproven", whatever it shows |

The `capture` summary prints, for each phy, the enabled bands, the bands that may initiate TX (channels not disabled and not no-IR), and whether mesh point is listed. It adds a NOTE when a phy lists mesh point and has 6 GHz channels, to keep the flag from being read as proof.

## 1. Prerequisites

1. Two V1 nodes, each past first power ([v1-first-power.md](v1-first-power.md)) with no FAIL lines from `bench-check-v1.sh`.
2. Antennas or attenuators on every RF port, as in mesh-test-plan.md "Setup". Never transmit into an open port.
3. The same image on both nodes, with its commit, Actions run and `sha256sum` recorded on GHO-22.

## 2. Capture (each node)

```sh
sh v1-radio-validate.sh capture > radios-<node>.txt 2>&1
```

It records:

- PCI and USB IDs, with link capability and status when `lspci` is installed
- netdevs with driver, phy and `ethtool -i` firmware version
- mt76 firmware lines from `dmesg` and the installed `mediatek/mt7916*` files
- the `morse` driver and firmware version (`modinfo`, `dmesg`, `morse_cli version`)
- `iw reg get` and the wireless country, channel, band and `htmode` settings
- the per-phy summary above, plus the full `iw phy <phy> info`, `iw dev` and station dumps

Attach both files to GHO-22. Run `capture` again whenever the image, firmware or country code changes.

## 3. Mesh on each radio

Run [mesh-test-plan.md](../poc/mesh-test-plan.md) on the two V1 nodes, with `mesh-snap.sh` before and after, exactly as written. That covers association, batman-adv neighbours, ping, throughput per radio, HaLow-only fallback, multicast, simultaneous traffic on both radios (M8), radio resets with `wifi down/up` (M9, M10), node power cycle (M11) and GNSS during TX (M13).

Then test mesh point per Wi-Fi band. Repeat M1 (association) and M4 (throughput) with the `batmesh1` interface moved from the 2.4 GHz radio to the other MT7916 radio on both nodes. Check the radio names with `uci show wireless`:

```sh
R24=radio0   # the MT7916 2.4 GHz wifi-device the wizard used
R5=radio1    # the MT7916 5/6 GHz wifi-device
uci set wireless.batmesh1_$R24.device="$R5"   # the section keeps its name; only the radio changes
uci set wireless.$R5.band='5g'; uci set wireless.$R5.channel='36'; uci set wireless.$R5.htmode='HE80'
uci set wireless.$R5.disabled='0'
uci commit wireless && wifi
```

Channel 36 is used because it needs no DFS radar wait. For the 6 GHz attempt, set `band` to `6g` and pick a channel that `capture` lists as able to initiate TX. If none is listed, record "6 GHz: no channel may initiate TX under country XX" and stop: that is a result, not a failure of the test. Restore the wizard's 2.4 GHz setting afterwards.

Record per band on GHO-22: channel and width, `mesh plink` state, RSSI, TX/RX bitrate, and M4 throughput each way.

## 4. Simultaneous radios and RF coexistence

- Simultaneous traffic is M8 in mesh-test-plan.md, run on V1 nodes. Record any `dmesg` errors from `mt7915e` or `morse` during it.
- Radio-to-GNSS coexistence (desense, TTFF under load, antenna isolation) is owned by [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) tests T7 to T12. Run them there.
- Wi-Fi to HaLow isolation: with the T11 VNA setup, also measure S21 from the HaLow port to each Wi-Fi port, with the final antennas mounted. During M8, compare HaLow throughput with Wi-Fi idle and with Wi-Fi at full throughput, on the 2.4 GHz and the 5 GHz backhaul. Record both on GHO-22. No pass threshold is set yet. The first measurement sets the baseline for GHO-12.

## 5. Enumeration, reset and power-cycle loops

The loops exercise the recovery ladder in [v1-hw-telemetry-recovery.md](../software/v1-hw-telemetry-recovery.md) §5, with the timeouts proposed in its §4. The script's defaults are those timeouts. Each can be overridden through the environment, and the loop header prints the values used. Run each loop on one node while it has a mesh link to the other node. When a peer was present before an iteration, the iteration passes only if the peer returns within `PEER_TIMEOUT` (default 60 s).

| Test | Ladder step | What it does | Drives GPIO | Iterations |
|---|---|---|---|---|
| `wifi-pci-reset` | 1w | PCI function reset through sysfs | no | 50 |
| `wifi-pci-rescan` | 1w | PCI remove, wait, bus rescan | no | 50 |
| `halow-usb-reset` | 1 | USB device reset (`usbreset`, or a deauthorize/authorize fallback) | no | 50 |
| `hub-reset` | 2 | Hub reset pulse, then waits for the HaLow device; the OpenVLM must also return if it was present | yes | 20 |
| `wifi-power` | 3 | PCI remove, Wi-Fi rail off for the off time, rail on, rescan | yes | 20 |
| `halow-power` | 3 | HaLow reset asserted, rail off, rail on, reset released | yes | 20 |

```sh
sh v1-radio-validate.sh loop wifi-pci-rescan 50 > loop-wifi-pci-rescan-<node>.txt 2>&1
ALLOW_GPIO=1 sh v1-radio-validate.sh loop wifi-power 20 > loop-wifi-power-<node>.txt 2>&1
```

The GPIO tests refuse to run without `ALLOW_GPIO=1`. Set it only after the first-power sequence captures have verified, on this board, the polarity of each line the test drives, and confirmed that no control line back-feeds a switched rail (v1-first-power.md §4; recovery doc tests T1 and T2). The recovery doc forbids software GPIO drive until then. The script drives the open-drain lines only low or back to input, never high, and on exit restores the boot states from the V1 distroconfig.

Each loop prints a CSV line per iteration: result, device time, netdev time, peer time, peer counts before and after, and a failure reason. Failed iterations add the last `dmesg` lines. A radio that is missing before an iteration stops the loop.

Pass for each loop: every iteration passes, and the device and netdev times stay inside the §4 timeouts. Attach the full output to GHO-22. Report any failure with its reason and `dmesg`. Failures that point at hardware (rail, reset line, hub) also go to GHO-9 or GHO-10.

## 6. Done

GHO-22 is done when its record holds, for both nodes:

1. A `capture` from the final image.
2. Mesh tests M1 to M13 passing, with the per-band results from section 3.
3. The simultaneous-traffic and isolation results from section 4, with the T7 to T12 results linked.
4. All six loops passing at the iteration counts above.
5. A results summary that sorts every claim into the three classes in the table above. Any 6 GHz mesh claim must meet all three conditions in that table.
