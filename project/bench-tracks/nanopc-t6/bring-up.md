# NanoPC-T6 LTS bench node: bring-up

This takes the node from an unopened board to a measured scorecard. Each step lists its pass criteria. Results go on [GHO-87](https://linear.app/ghostnet-labs/issue/GHO-87), not in this file. The parts are in [build-list.md](build-list.md); the power numbers to compare against are in [power-budget.md](power-budget.md).

Safety rules carried over from the [POC bench](../../poc/bench-bom-and-topology.md) §7:
- Never transmit without an antenna or attenuator on every RF port.
- Keep the two nodes at least 1 m apart, or cable them through attenuators.

This board adds one more rule: **it has no reverse-polarity protection.** Never connect the pack without the LM74700 in line, and check the barrel plug's polarity (centre positive) with a meter before the first connection.

## 0. Image

Use the CI image from the NanoPC-T6 LTS build of [firmware #55](https://github.com/ghostnet-labs/firmware/pull/55), or from `24.10` once it has merged. The file in the build artifact is `…-rockchip-armv8-friendlyarm_nanopc-t6-lts-squashfs-sysupgrade.img.gz`. It is a whole-disk image: U-Boot (the NanoPC-T6 build), kernel, LTS DTB, then squashfs root.

To build locally, from the firmware repository root:

```console
./scripts/openmanet_setup.sh -i -b nanopc-t6 && make -j"$(nproc)" download && make -j"$(nproc)"
```

## 1. Arrival checks

1. The silkscreen on the underside reads "NanoPC-T6 LTS" and "2310". This image targets that revision; the older T6 (2301) is a different board.
2. Record the RAM and eMMC size from the label (4 GB / 64 GB expected).
3. Fit the heatsink and fan before running anything under load.

## 2. Console

1. Connect the USB-C port labelled DEBUG to the host. It enumerates as a CH340 serial port.
2. Open it at **1500000 baud**, 8N1 (wiki). Example: `picocom -b 1500000 /dev/ttyUSB0`.
3. Power on from a 12 V bench supply through the 5.5 x 2.1 mm jack.

**Pass:** the U-Boot banner and kernel log appear on the console.

## 3. Flash and first boot

Take one of two routes:
- **USB maskrom (default).** Hold the MASK button while powering on, then write the image to eMMC from the host with `rkdeveloptool`. Follow the wiki's "Install OS via USB" for the loader file and driver. This works whatever is already on the eMMC.
- **SD card.** Write the image to a microSD card (`gunzip -c <image>.img.gz | dd of=/dev/sdX bs=4M conv=fsync`), insert it, and power on.
  - The RK3588 boot ROM tries eMMC before SD. So this route works only on a blank eMMC, or where the factory eMMC loader hands over to SD, as FriendlyElec's "Install OS via TF card" relies on. **Unverified** for our image.
  - Once the image boots from SD, copy it to eMMC from the node: `gunzip -c <image>.img.gz | dd of=/dev/mmcblk<N> bs=4M`. Find the eMMC with `cat /sys/block/mmcblk*/device/type`; it reports `MMC`, not `SD`.

Power-cycle without the SD card.

**Pass:**
- `ubus call system board` shows `"board_name": "friendlyarm,nanopc-t6-lts"` and the model "FriendlyElec NanoPC-T6 LTS".
- Both 2.5 GbE ports come up as `eth0` (LAN) and `eth1` (WAN), with `r8169`. Note which physical port is which.
- The OpenMANET UI answers on the LAN.
- Write down the boot time to the UI.

## 4. Board checks

1. `ls /dev/ttyS0 /dev/pps0 /dev/i2c-8` all exist.
2. `cat /sys/class/thermal/thermal_zone0/type` and `temp` give the SoC temperature.
3. `ls /sys/class/hwmon/*/name` includes `pwmfan`, and the fan runs. Run `echo 100 > /sys/class/hwmon/hwmonN/pwm1` and check that the fan slows. If the fan stops at 255 and runs at 0, the PWM polarity is inverted; record it on GHO-87.

**Pass:** all three as stated.

## 5. E-key fit

Power off. Follow [e-key-fit.md](e-key-fit.md) §4:

1. Caliper the standoff height, L2303's height and the card's back-side components.
2. Remove any 2280 SSD.
3. Lay Kapton over the area under the card.
4. Seat the AW7916-AED, screw it at the 30 mm standoff, and support the free end with a nylon spacer.
5. Leave out any heatsink screw at the hole under the card.

**Pass:** the card sits flat, nothing on its back side touches the board, and the measurements are on GHO-87.

## 6. Wi-Fi card (AW7916-AED)

Run each check in turn:

1. `lspci -nn` lists a MediaTek `14c3:7906`.
2. `dmesg | grep -i mt79` shows `mt7915e` loading the MT7916 firmware with no errors.
3. `iw phy` lists the card's phys, with 2.4 GHz on one and 5/6 GHz on the other.
4. Before any traffic, set TX power to the lowest level: `uci set wireless.radioN.txpower=…`, then `wifi reload`.
5. In the OpenMANET setup wizard, enable the Wi-Fi mesh backhaul (`batmesh1`) on the same channel as the CM5 node.

**Pass:** the mesh peer appears in `iw dev <mesh-if> station dump`, and `batctl o` shows the CM5 node.

## 7. HaLow (GW16167 on the Pier42 carrier)

Plug the carrier into a USB 2.0 Type-A port. A USB 2.0 port is enough; keep the USB 3.0 port free so its noise stays away from the HaLow card.

1. `lsusb` shows the Morse Micro device.
2. `dmesg | grep -i morse` shows `morse_usb` binding with no errors.
3. The HaLow interface comes up in the wizard's HaLow mesh.

**Pass:** the CM5 node shows up as a HaLow mesh peer, and `iperf` across the HaLow link completes.

## 8. GNSS and PPS

1. **Check antenna bias first** (GHO-87, question 4). With the MAX-M10S powered and no antenna fitted, measure DC between the SMA centre pin and its shell.
   - 3.0 V or more means the ANN-MB1 can be fitted directly.
   - 0 V means feed the ANN-MB1 through a bias tee from 3.3 V.
2. Wire the MAX-M10S to the header as in [build-list.md](build-list.md) ("Header wiring").
3. Place the ANN-MB1 as in the screen's "Antennas within one foot" layout: on a 100 mm or larger ground plate at the far end of the 300 mm bar from the HaLow whip, with a view of the sky.

Then run each check in turn:

1. `ppstest /dev/pps0`. One assert per second appears once the receiver has a fix.
2. `uci get gpsd.core.device` prints `/dev/ttyS0`. The first-boot default in [firmware #55](https://github.com/ghostnet-labs/firmware/pull/55) sets it.
3. `gpspipe -w -n 20` shows `TPV` with `"mode":3`. gpsd auto-detects the MAX-M10S at its default 38400 baud.
4. Log the C/N0 sweep. Step HaLow TX power and Wi-Fi TX power separately, and record the power at which average C/N0 drops by 3 dB. The procedure is the screen's sweep order.

**Pass:** checks 1 to 3 as stated, plus a recorded C/N0-versus-power table. Whether ntpd selects PPS depends on the gpsd/ntpd PPS work on the Venice track ([packages #21](https://github.com/ghostnet-labs/packages/pull/21)); record what `ntpq -p` shows, but it is not a pass criterion here.

## 9. Pack power and logging

Wiring, in order: pack +, then the LM74700 ideal diode, then the INA228 (high side, VIN+ to VIN-), then the board's DC jack. Pack - goes to the board ground. The INA228's I2C goes to header pins 3/5, with 3.3 V on pin 1 and ground on pin 9.

1. Run `i2cdetect -y 8`. Address 0x40 shows as `UU`, meaning the driver has bound it.
2. Copy [nanopc-power-log.sh](nanopc-power-log.sh) to the node and run it:

   ```console
   sh nanopc-power-log.sh -n 300 -l idle_from_pack > power-idle.csv
   ```

**Pass:**
- Idle input power with both radios up and no traffic is logged.
- `bus_mv` agrees with a meter at the jack within 2 %.
- The node boots and runs from the pack alone.

## 10. Full load

Run traffic on both radios at once, for example `iperf` across the Wi-Fi mesh and across HaLow. Raise the AW7916 TX power one step at a time up to the regulatory maximum on both bands. Run the logger throughout, with a label per step.

Then add an all-core CPU load (for example `stress -c 8` or eight `yes > /dev/null` loops) for 10 minutes. This gives the board's own worst case.

**Pass:**
- 30 minutes at full TX with no reboot.
- No PCIe link-down in `dmesg`.
- No `mt7915e` firmware crash or reset.
- Peak input power recorded, compared with the 24 W worst case in [power-budget.md](power-budget.md).
- The SoC stays below its throttle point, which shows as `soc_c` levelling off with the fan at full speed.

If the Wi-Fi card fails here, record the highest step that passed and cap TX power there.

## 11. Scorecard

Move each column of the scorecard in [README.md](README.md) to "boot" or "measured", citing the GHO-87 comment that holds the evidence.
