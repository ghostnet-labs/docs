# VP2430e bench node: bring-up

Do these steps in order. Record each result on [GHO-86](https://linear.app/ghostnet-labs/issue/GHO-86), not in this file. The commands assume the OpenMANET `x86-64` image from [firmware #54](https://github.com/ghostnet-labs/firmware/pull/54) with `bsp-x86` from [packages #23](https://github.com/ghostnet-labs/packages/pull/23). Background for each step is in [hardware.md](hardware.md), and the wiring is in [build-list.md](build-list.md#wiring).

## 1. Before first power

1. Fit the parts, with the box unplugged:
   - RAM and the NVMe drive.
   - The AW7916-AED, with the standoff in the 3052 position and the Wi-Fi thermal pad.
   - The three IPEX cables to the antenna holes.
2. Power the box from Protectli's own 12 V brick for the first boot, not from the pack chain.
3. Plug the console cable into the front USB-C COM port and open a terminal at 115200 8N1.
4. Enter firmware setup.
   - **AMI:** go to *Advanced > Serial Port Console Redirection*. Leave COM0 (USB-C) redirection on. Enable the COM1 port (the internal header) but **leave console redirection off on COM1**, so the firmware does not write to the GNSS line.
   - **coreboot:** go to *Dasharo System Features > Serial Port Configuration* and enable COM1.
5. While in setup, note the board and product strings the firmware shows. `bsp-x86` matches on a DMI name that contains `protectli` and `vp2430`.

## 2. Flash and first boot

1. Write `openmanet-*-x86-64-generic-squashfs-combined-efi.img.gz` to a USB stick (`gunzip -c image.img.gz | dd of=/dev/sdX bs=4M`) and boot from it.
2. Check that the board is recognised:
   ```sh
   cat /tmp/sysinfo/board_name        # expect protectli-vp2430... (lowercased DMI vendor + product)
   /usr/libexec/bsp-x86/board          # prints protectli-vp2430 when bsp-x86 matches
   ```
   If the second command prints nothing, the DMI strings differ from `protectli*vp2430*`. Record the exact `board_name`; the match needs updating in packages.
3. Install to the NVMe drive: `gunzip -c image.img.gz | dd of=/dev/nvme0n1 bs=4M`, then remove the stick and reboot. Later updates use `sysupgrade` with the same image.

## 3. Serial and PPS

1. Find the ports:
   ```sh
   dmesg | grep -i ttyS
   cat /proc/interrupts | grep -i serial
   uci get gpsd.core.device           # bsp-x86 sets /dev/ttyS1
   ```
   Expected (Unverified): `ttyS0` at 0x3f8 IRQ 4 is the USB-C console, and `ttyS1` at 0x2f8 IRQ 3 is the COM2 header. If the header turns out to be another `ttyS`, set `gpsd.core.device` to it and record the mapping.
2. With the GNSS wired and the antenna outside, check NMEA: `gpspipe -r -n 20`. NMEA sentences prove pins 2 and 3 and the MAX3232 T1/R1 path.
3. Wait for a fix. The u-blox sends no PPS until GNSS time is valid. Then check the pulse:
   ```sh
   ppstest /dev/pps0                  # assert and clear both tick once a second
   ntpq -p                            # SHM(1) PPS selected (o) once SHM(0) is in range
   ```
   - The MAX3232 inverts the pulse, so the clear edge is the top of the second. gpsd takes the clear edge without any setting. To see that choice, stop the gpsd service and run `gpsd -N -D 5 /dev/ttyS1` by hand: its PPS lines name the clear edge as the "1Hz leading edge".
   - If `/dev/pps0` exists but never ticks, the header's DCD interrupt may not be arriving (the coreboot source marks its IRQ "low level"). Check `/proc/interrupts` for `ttyS1` while PPS runs. As a test, try `setserial /dev/ttyS1 irq 0` (polled mode), and record the result.
4. Run [`gnss-ttff.sh`](../../hardware/gnss-ttff.sh) with `-m none` right after power-on, plus `-p 600` for a ten-minute PPS count.
   - The image has no `ubxtool`, because gpsd is built without Python, so cold, warm and hot restarts are not available here.
   - `ppstest` counts assert events, which on this wiring are the trailing edge. The interval jitter is still meaningful.

## 4. Radios

1. Wi-Fi card:
   ```sh
   lspci -nn | grep -i 14c3           # MediaTek MT7916 (14c3:7906)
   dmesg | grep -i mt7915
   iw list | grep -A12 'Supported interface modes' | grep -i 'mesh point'
   ```
2. HaLow: `dmesg | grep -i morse` and `iw dev` should show the MM8108 interface after the GW16167 carrier is plugged into a USB-A port.
3. Ethernet order: `ethtool -p eth0 5` blinks a port; repeat for eth0 to eth3 and record which chassis port each is. `bsp-x86` makes eth0 WAN and eth1 to eth3 LAN on the assumption that eth0 is port 1. Fix the board.d mapping if not.
4. Mesh: run the two-node steps in [mesh-test-plan.md](../../poc/mesh-test-plan.md) with [`mesh-snap.sh`](../../poc/mesh-snap.sh) against another bench node.
5. Wi-Fi under load: run a TX burst over the mesh (`iperf -c <peer> -t 600`, from the image's utils extras) and check that the card stays up with no `mt7915e` errors in `dmesg`. Watch the card's temperature with `sensors` (the `mt7915_phy*` hwmon, if exposed) and the chassis by hand. This is the only check on the undocumented E-key 3.3 V limit.

## 5. Power

1. Move to the pack chain. Before connecting the VP2430, set a current-limited bench supply to 11.1 V and 6 A in place of the pack, then check the following:
   - The Orion-Tr output reads 12.0 to 12.2 V.
   - The converter's input and output negatives are tied ([build-list.md](build-list.md#power)).
2. Battery monitor:
   ```sh
   ls /sys/bus/i2c/devices/           # an i2c-N adapter from the MCP2221A, and N-0040
   cat /sys/module/ina238/parameters/shunt_uohm   # 15000
   for h in /sys/class/hwmon/hwmon*; do echo "$h $(cat $h/name)"; done   # one named ina228
   sensors
   ```
   - Compare `in1_input` with a meter on the pack, and `curr1_input` with the bench supply's current.
   - If the current reads about 1.5 times high, the shunt parameter was not applied before the bind. In that case:
     1. Check `logread -e bsp-x86`.
     2. Unbind the chip with `echo 0x40 > /sys/bus/i2c/devices/i2c-N/delete_device`.
     3. Replug the MCP2221A.
3. Log power with [`ina228-log.sh`](../../hardware/ina228-log.sh) for each state, using `-l` to label the rows:
   - idle with the radios up
   - mesh traffic
   - all four CPU cores loaded at once, with Wi-Fi TX
4. Low end:
   1. Sweep the bench supply down from 12.6 V to 7.0 V in 0.5 V steps under the working load.
   2. Record where the Orion-Tr cuts out (7 V by its datasheet).
   3. Raise the supply again and record where it restarts (7.5 V by its datasheet).
   4. Check that the box powers back on by itself, since JPWR1 defaults to auto power-on.
5. Watchdog: `ls /dev/watchdog*` and `ubus call system watchdog` should show the `it87_wdt` device.

## 6. Coexistence

Run the screen's GNSS C/N0 sweep with the antennas on the ground bar:
1. Log GNSS C/N0 with `gpspipe -w` while stepping HaLow TX power, then Wi-Fi TX power.
2. Use the same order and spacing as the CM5 track, so the numbers compare directly.
