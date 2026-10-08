# CM5 node bring-up runbook (GHO-28, GHO-29, GHO-30)

The steps to take one bench node from a bare CM5 to a checked node. Wiring,
parts and the carrier pinout are in
[bench-bom-and-topology.md](bench-bom-and-topology.md) (§4.1 for what the
Waveshare carrier exposes). Results go on the Linear issues named in each
step, not in this file.

Two scripts run on the node; copy them over with `scp` once SSH works:

- [`bench-check.sh`](bench-check.sh) is a read-only pass/fail check of every bench device path. It ends with raw details to paste into Linear.
- [`bench-log.sh`](bench-log.sh) is a CSV logger for power, thermal and radio TX bytes (GHO-30, GHO-31).

## 0. Before power

1. Build or download the current `ekh-bcm2712` image from `24.10`. It must include firmware #17 (PPS), #22 (`i2c-gpio`) and #25 (Bluetooth), and packages #3 (gpsd on USB, INA219 on `i2c-gpio`). CI artifacts expire after 5 days, so download the one from the latest `24.10` build when the hardware ships. Record the commit, Actions run, artifact name and `sha256sum` on [GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28).
2. Set the Serial Basic VCC selector to **3.3 V** (all three adapters).
3. Do arrival checks 1–5 and 9 in [bench-bom-and-topology.md §8](bench-bom-and-topology.md) as parts are fitted. Never transmit with an open antenna port.

## 1. Flash the eMMC (GHO-28)

1. Disconnect the UPS. Fit the CM5 to the carrier with no radios attached.
2. Hold the carrier BOOT button and connect the host to the carrier USB-C with the Adafruit 4474 cable.
3. On the host, run `sudo rpiboot` ([usbboot](https://github.com/raspberrypi/usbboot)). The eMMC appears as a mass-storage disk.
4. Write the image. The CI artifact holds one full-disk image, `openmanet-<version>-rpi5-cm5-mm8108-usb-squashfs-sysupgrade.img.gz`; check it against the artifact's `sha256sums`, then run `gunzip -c openmanet-*-sysupgrade.img.gz | sudo dd of=/dev/sdX bs=4M conv=fsync`.
5. Optional, for the serial console: mount the boot (FAT) partition and add `dtparam=uart0_console` under `[all]` in `config.txt`. Then wire connection 12: pull both RS485 CH1 jumpers first, and use the host's Serial Basic at 115200 8N1.

## 2. First boot (GHO-28)

1. Power from the bench supply or USB-C (not the UPS yet). Capture the console from power-on: `picocom -b 115200 /dev/ttyUSB0 | tee node1-boot.log` on the host, or watch HDMI.
2. Connect Ethernet, then SSH to `root@<ip>` (OpenWrt default LAN `192.168.1.1` unless the image changed it).
3. Record on GHO-28:
   - `cat /etc/openwrt_release`
   - `uname -a`
   - `cat /tmp/sysinfo/board_name`
   - `df -h`
   - the boot log
4. Reboot twice and confirm the eMMC stays bound each time. `bcm2712-morse-fix` stops morsechipreset from unbinding it.

## 3. Fit radios and GNSS, then run the check (GHO-29)

Power off between each addition, fit antennas first, then:

1. The AW7916-AED in the M.2 M-key slot on its Sintech adapter, with all three antennas (the B-key Mini-PCIe adapter has no PCIe; see bench-bom-and-topology.md §4.1). Check `lspci` lists it.
2. Pier42 + GW16167 on a carrier USB-A port, W1063M on the HaLow port.
3. SAM-M10Q on its Serial Basic in another USB-A port. PPS goes to terminal "18" and GND to the GND terminal (connections 8 and 8a). Put the GNSS where it sees the sky.

Then run:

```sh
sh bench-check.sh > /tmp/check-node1.txt 2>&1; cat /tmp/check-node1.txt
```

Paste the output on [GHO-29](https://linear.app/ghostnet-labs/issue/GHO-29). For each FAIL:

| FAIL | First look |
| -- | -- |
| no morse netdev | `lsusb` (Morse Micro device?), `dmesg \| grep -i morse` (firmware load), USB cable seated, Pier42 3.3 V. |
| no Wi-Fi netdev | `lspci` (MT7916, 14c3:7906?), `dmesg \| grep mt7915` (firmware load). Check the 3.3 V rail if the card isn't listed. |
| gpsd device missing | `dmesg \| grep ch341`; `uci get gpsd.core.device` should be `/dev/ttyUSB0`. |
| `/dev/pps0` missing | `dtoverlay=pps-gpio` in the boot partition's `config.txt`, `lsmod \| grep pps`. |
| no INA219 hwmon | `logread -e ina219-ups`. Find the i2c-gpio bus with `ls /sys/bus/i2c/devices/` and run `i2cdetect -y <n>`; expect 0x41. No device usually means missing pull-ups or swapped SDA/SCL (terminals 22/27). |
| eth0 no carrier | Cable, switch port, `ethtool eth0`. |

Then the per-radio checks GHO-29 asks for:

- **HaLow:** `morse_cli -i <iface> version` (firmware and chip), then join the mesh from the LuCI wizard on both nodes. `iw dev <iface> station dump` shows the peer.
- **Wi-Fi:** an 802.11s mesh point on both nodes (`iw dev`, `iw dev <iface> station dump`).
- **GNSS:** `gpspipe -w | grep TPV` shows `"mode":3`, and `ppstest /dev/pps0` shows one assert per second.
- **Bluetooth** ([GHO-47](https://linear.app/ghostnet-labs/issue/GHO-47), firmware #25): `hciconfig -a` shows `hci0` UP, then `bluetoothctl` → `power on`, `scan on` sees a nearby phone. If `hci0` is missing, check `dmesg | grep -i -E 'hci_uart|bluetooth|brcm'`; a missing `BCM4345C0*.hcd` warning is expected and harmless.
- **Ethernet throughput:** the image has `iperf` (v2). Run `iperf -s` on the node and `iperf -c <node> -t 30` on the host; use iperf 2 on the host too.

## 4. Power and thermal (GHO-30)

Sources available on the bench:

| Quantity | Source | Interface | Unit | Notes |
| -- | -- | -- | -- | -- |
| Battery bus voltage | UPS INA219 | `/sys/class/hwmon/hwmonN/in1_input` | mV | Pack side of the UPS, not the 5 V rail. |
| Battery current | UPS INA219 | `curr1_input` | mA | Uses the 10 mΩ shunt from `/etc/config/ups`; check the sign on charge and discharge. |
| Battery power | UPS INA219 | `power1_input` | µW | |
| SoC temperature | CM5 | `/sys/class/thermal/thermal_zone0/temp` | m°C | |
| Undervoltage / throttling | CM5 firmware | `vcgencmd get_throttled` | bit flags | From `bcm27xx-utils` (pinned in the ekh-bcm2712 image for GHO-30). Without `vcgencmd` the logger writes `na`. |
| 5 V input, core rail | CM5 PMIC | `vcgencmd pmic_read_adc` | V, A | Logged as `ext5v_v` (EXT5V_V), `core_v` (VDD_CORE_V) and `core_a` (VDD_CORE_A); `na` without `vcgencmd`. EXT5V_V is the CM5 5 V input from the carrier. |
| 5 V input current | USB-C power meter | Read by eye or photo | A, W | Between UPS and carrier. |
| Radio TX activity | netdev counters | `/sys/class/net/<if>/statistics/tx_bytes` | bytes | Lines up power steps with traffic. |

None of these is the V1 INA228 or the custom supervisor. They measure the bench UPS and the CM5 only, so record POC numbers as "bench" on GHO-30.

Log a run:

```sh
sh bench-log.sh 5 > /tmp/node1-idle.csv &
# idle 10 min, then HaLow iperf, then Wi-Fi iperf, then both
kill %1
```

Run it once closed-box without a CM5 cooler and once with one (arrival check 10). Attach the CSVs to GHO-30.

## 5. Two nodes (GHO-31)

Repeat steps 1–3 on node 2. Then run [mesh-test-plan.md](mesh-test-plan.md) for [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31), with the nodes at least 1 m apart or behind attenuators.
