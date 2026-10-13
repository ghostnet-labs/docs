# Venice bench node: bring-up

This takes the node from an unopened GW11048-2 kit to a measured scorecard. Each step lists its pass criteria. Results go on [GHO-85](https://linear.app/ghostnet-labs/issue/GHO-85), not in this file. The parts are in [build-list.md](build-list.md); the power numbers to compare against are in [power-budget.md](power-budget.md).

Safety rules carried over from the [POC bench](../../poc/bench-bom-and-topology.md) §7:
- Never transmit without an antenna or attenuator on every RF port.
- Keep the two nodes at least 1 m apart, or cable them through attenuators.

## 0. Image

Use the CI image from the Venice build of [firmware #52](https://github.com/ghostnet-labs/firmware/pull/52) (or from `24.10` once it has merged). The file in the build artifact is the one named `…-Venice-MM8108-USB-squashfs-sysupgrade.img.gz`. It is a whole-disk image: boot script, kernel, every Venice DTB, then squashfs root.

To build locally, from the firmware repository root:

```console
./scripts/openmanet_setup.sh -i -b venice && make -j"$(nproc)" download && make -j"$(nproc)"
```

## 1. Arrival checks

1. Board label reads GW7201-01, the i.MX8M Mini SoM.
2. The kit contains the power supply and the GW16099 JTAG/serial adapter.
3. Note the board revision letter. Revision H or later means the GNSS is a MIA-M10Q at 38400 baud; earlier boards have a ZOE-M8Q at 9600 baud ([Gateworks GPS wiki](https://trac.gateworks.com/wiki/gps)). gpsd handles either, but record which.
4. Note the DC input jack type, for the pack lead (GHO-85, question 5).

## 2. Console

1. Plug the GW16099 into the board's JTAG header and the host. On Linux it shows up as two ports:
   - `/dev/ttyUSB0` is JTAG.
   - `/dev/ttyUSB1` is the console, 115200 8N1 ([Gateworks JTAG instructions](https://trac.gateworks.com/wiki/jtag_instructions)).
2. Follow Gateworks' power-up order for the JTAG adapter to avoid a ground loop ([getting started](https://trac.gateworks.com/wiki/gettingstarted#Power)).
3. Power on with the kit supply.

**Pass:** the U-Boot banner shows `Model: Gateworks Venice GW72xx-0x` and the 4 GiB DRAM line, and stops when a key is pressed.

## 3. Flash and first boot

1. Copy the image to a USB flash drive.
2. At the U-Boot prompt, write it to eMMC:

   ```console
   usb start && load usb 0:1 $loadaddr <image>.img.gz && gzwrite mmc $dev $loadaddr $filesize
   ```

   Over TFTP instead: `setenv image <image>.img.gz; run update_all`.

3. Power-cycle.

**Pass:**
- `ubus call system board` shows `"board_name": "gw,imx8mm-gw72xx-0x"`.
- `eth0` (FEC) is WAN and `eth1` (LAN7430, `lan743x`) is LAN.
- The OpenMANET UI answers on the LAN.
- Write down the boot time to the UI.

## 4. Board sensors

Run `for h in /sys/class/hwmon/hwmon*; do echo "$h $(cat "$h"/name)"; done`. Then read the GSC channels; `vdd_vin` is the input voltage.

**Pass:** `vdd_vin` is within 2 % of the supply's voltage, measured at the jack.

## 5. Socket plan

Power off before fitting any card.

- **J10** takes the GW16151 adapter carrying the GW16167. J10 is the socket with the PCIe/USB 3.0 mux on `pci_usb_sel`.
- **The other mini-PCIe socket** takes the AW7916-NPD, with its heatsink.
- Which physical socket is J10 comes from the board silkscreen or the manual (GHO-85, question 3).
- Check that the heatsink clears its neighbours (GHO-85, question 6).
- Leave `pci_usb_sel` at its default, 0 (PCIe).

## 6. Wi-Fi card (AW7916-NPD)

Run each check in turn:

1. `lspci -nn` lists a MediaTek `14c3:7906` behind the PCIe switch.
2. `dmesg | grep -i mt79` shows `mt7915e` loading the MT7916 firmware with no errors.
3. `iw phy` lists the card's phys, with 2.4 GHz on one and 5/6 GHz on the other.
4. Before any traffic, set TX power to the lowest level: `uci set wireless.radioN.txpower=…`, then `wifi reload`.
5. In the OpenMANET setup wizard, enable the Wi-Fi mesh backhaul (`batmesh1`) on the same channel as the CM5 node.

**Pass:** the mesh peer appears in `iw dev <mesh-if> station dump`, and `batctl o` shows the CM5 node.

## 7. HaLow (GW16167 on GW16151)

1. `lsusb` shows the Morse Micro device.
2. `dmesg | grep -i morse` shows `morse_usb` binding with no errors.
3. The HaLow interface comes up in the wizard's HaLow mesh.

**Pass:** the CM5 node shows up as a HaLow mesh peer, and `iperf` across the HaLow link completes.

## 8. GNSS and PPS

Connect the ANN-MB1 to the board's MMCX GNSS port through the SMA-to-MMCX cable. Place it as in the screen's "Antennas within one foot" layout: on a 100 mm or larger ground plate at the far end of the 300 mm bar from the HaLow whip, with a view of the sky.

1. Run `ppstest /dev/pps0`. One assert per second appears once the receiver has a fix.
2. Run `uci get gpsd.core.device`. It must print `/dev/pps0 /dev/ttymxc0`.
3. Run `ps w | grep gpsd`. Both devices must appear as separate arguments.
4. Run `gpspipe -w -n 20`. The output shows `TPV` with `"mode":3`, and `PPS` records.
5. Run `ntpq -p`. After about 10 minutes, the `127.127.28.0` (PPS) line is marked `o` or `*`, and `127.127.28.1` (GPS NMEA) is listed but not selected.
6. Log the C/N0 sweep. Step HaLow TX power and Wi-Fi TX power separately, and record the power at which average C/N0 drops by 3 dB. The procedure is the screen's sweep order.

**Pass:** steps 1 to 5 as stated, plus a recorded C/N0-versus-power table.

## 9. Pack power and logging

Wiring, in order: pack +, then the LM74700 ideal diode, then the INA228 (high side), then the board's DC jack. Pack - goes to the board ground.

Connect the INA228's I2C pins to the board's off-board I2C header (`i2c3` in the device tree). Find its bus number with `i2cdetect -l`, then check that the chip answers with `i2cdetect -y <bus>` (expect 0x40).

Copy [venice-power-log.sh](venice-power-log.sh) to the node and run it. It is read-only and checks that the chip really is an INA228 before it logs:

```console
sh venice-power-log.sh -b <bus> -r 0.015 -n 300 -l idle_from_pack > power-idle.csv
```

`-r 0.015` is the Adafruit INA228's shunt. It also logs the GSC's own `vdd_vin` as a cross-check.

**Pass:**
- Idle input power with both radios up and no traffic is logged.
- `bus_mv` agrees with `gsc_vin_mv` within 2 %.
- The node boots and runs from the pack alone.

## 10. Full load and the socket current gate

Run traffic on both radios at once, for example `iperf` across the Wi-Fi mesh and across HaLow. Raise the AW7916 TX power one step at a time up to the regulatory maximum on both bands. Run the logger throughout, with a label per step.

**Pass:**
- 30 minutes at full TX with no reboot.
- No PCIe link-down in `dmesg`.
- No `mt7915e` firmware crash or reset.
- Peak input power recorded, compared with the 15.8 W worst case in [power-budget.md](power-budget.md).

If it fails, record the highest step that passed and take the fallback path in [power-budget.md](power-budget.md) §4.

## 11. Scorecard

Move each column of the scorecard in [README.md](README.md) to "boot" or "measured", citing the GHO-85 comment that holds the evidence.
