# CM5 bench node: bring-up

Do these steps in order. Each step names what it proves and its evidence level once done. Record every result, and any reading that disagrees with the docs, in [GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28).

The image is the CI-built `ekh-bcm2712` factory image (device `bcm2712_mm8108-usb`) from [ghostnet-labs/firmware](https://github.com/ghostnet-labs/firmware) 24.10. It needs [firmware#53](https://github.com/ghostnet-labs/firmware/pull/53) (dwc2 host, INA228 driver, gpsd fix) and the feeds pin bump that brings in [packages#22](https://github.com/ghostnet-labs/packages/pull/22).

## 1. Inspect (no power)

- Check the carrier's solder side and the M.2 slot for damage. Confirm the Multifunction strap resistors (`WIFI_EN`, `BT_EN`, `EEPROM_WP`, `ETH_OUT`, `PI_GLOBAL_EN`) are unpopulated, as the schematic shows.
- Fit the cooler to the CM5. Do not seat the CM5 yet.

## 2. Measure the carrier's 5 V rail (no CM5 fitted)

Proves: the buck output is inside the CM5's 4.75 to 5.25 V input range. The schematic computes about 5.40 V ([carrier.md](carrier.md#power-input)).

1. Bench supply at 11.1 V with a 0.5 A current limit, into the barrel jack. Nothing else plugged in.
2. Measure `CM4_5V` at header pin 2 or 4 against pin 6. Expect 5.0 to 5.25 V. **If it reads above 5.25 V, stop.** Do not seat the CM5. Change R54 or R60 ([power-budget.md](power-budget.md#open-item-the-540-v-output)) or ask Waveshare.
3. Measure header pin 1 (`PWR_3V3`). Expect about 3.3 V. `PCIE_3V3` stays off until the CM5 drives `PCIE_PWR_EN`.
4. Sweep the supply from 9.0 V to 12.6 V and confirm 5 V stays put. Record the no-load input current.

## 3. Flash the eMMC

1. Seat the CM5. Hold the carrier's BOOT button and connect the USB-C port to a PC. **Do not connect the barrel jack** while the USB-C port is on a PC: with DC present the carrier drives 5 V out of that port.
2. On the PC, run `rpiboot -d mass-storage-gadget64` from [raspberrypi/usbboot](https://github.com/raspberrypi/usbboot). The eMMC appears as a USB disk.
3. Write the factory image: `gunzip -c openwrt-*-bcm2712_mm8108-usb-*-factory.img.gz | sudo dd of=/dev/sdX bs=4M conv=fsync`.
4. Unplug USB-C. If the bootloader EEPROM is old, update it through the same `rpiboot` path first (`rpiboot -d recovery5`).

## 4. First boot and configuration

1. Connect a laptop to the gigabit port (`eth0`, the CM5's own PHY). Power from the bench supply at 11.1 V, 3.5 A limit. Log in over SSH or LuCI at the image's default LAN address.
2. Add the INA228 overlay to `/boot/config.txt`, after the `include distroconfig.txt` line. Adafruit 5832 has a 15 mΩ shunt:

   ```
   dtoverlay=ina228,shunt_resistor=15000
   ```

   Reboot. The `ina219-ups` service sees the bound monitor and stays out of the way.
3. Fit the radios and GNSS per [build-list.md](build-list.md#wiring), then reboot.

## 5. Verification commands

| Check | Command | Expect | Proves |
|---|---|---|---|
| Undervoltage and throttling | `vcgencmd get_throttled` | `throttled=0x0` | 5 V rail holds under load |
| USB tree | `lsusb -t` | The GW16167 on the dwc2 bus, the 2.5 GbE NIC on a 5000M xHCI port, the CH334 hub on the other xHCI bus | dwc2 host mode works |
| Drivers | `dmesg \| grep -iE 'dwc2\|mt7915e\|mm8108\|morse\|r8152\|ina2'` | Each probes with no errors | Every driver in the image binds |
| Network interfaces | `ip link` | `eth0`, `eth1` (2.5 GbE), the MT7916 phys and the HaLow interface | |
| 2.5 GbE chip | `ethtool -i eth1`, `lsusb` | Driver name and USB ID | Settles the unnamed chip |
| Wi-Fi card | `lspci -nn`, `iw list` | MT7916 at 14c3:7906, 2.4/5/6 GHz bands | PCIe link and card power |
| Battery monitor | `cat /sys/class/hwmon/hwmon*/name`, then `in1_input`, `curr1_input`, `power1_input` | `ina228` present; voltage within 1% of a meter reading | The backported driver and overlay |
| PPS | `ppstest /dev/pps0` | One assert per second once the receiver has a fix | PPS on GPIO18 |
| GNSS | `gpspipe -w -n 20`, `cgps -s` | TPV with mode 3, PPS events | gpsd reads both devices |
| Thermal | `cat /sys/class/thermal/thermal_zone0/temp` during a 10 min iperf3 load | Below 80 °C | Cooler is enough |

### If the MT7916 does not probe

The external PCIe link can hit the BCM2712's 32-bit DMA limit ([raspberrypi/linux#7026](https://github.com/raspberrypi/linux/issues/7026)). Add this to `/boot/config.txt` and reboot:

```
dtoverlay=pcie-32bit-dma-pi5
```

Record which way it works. If the overlay is needed, it goes into `distroconfig.txt` in a follow-up firmware PR.

## 6. Power measurements

With the 3S pack in place of the bench supply, log the INA228 every second (`power1_input`) for each case in [power-budget.md](power-budget.md): idle, meshing with light traffic, and a full TX burst on both radios plus a CPU load (`stress-ng --cpu 4`). At the same time, measure the 3.3 V droop at the AW7916-AED's adapter pins with a scope. These numbers replace the paper figures and move the "3S power" and "Wi-Fi card" scorecard columns to **bench-measured**.

## 7. GNSS coexistence sweep

Use the antenna layout in [build-list.md](build-list.md#antenna-layout). Order, from the screen:
1. Log idle C/N0 with both radios off.
2. Step HaLow TX power (per [D-020](../../decisions.md)) and log C/N0 at each step.
3. Do the same for Wi-Fi TX power, separately.
4. Record the power at which C/N0 drops by 3 dB.
5. Repeat with the SAM-M10Q in the same x = 300 mm position.

## Known issue: console on ttyUSB0 (IO-WIRELESS-BASE only)

The shared image's `cmdline.txt` sets `console=ttyUSB0,115200`, and `inittab` spawns a login on `ttyUSB0`. On the CM5-DUAL-ETH-BASE nothing sits on `ttyUSB0` unless a USB serial adapter is plugged in, so this is harmless here. On the CM5-IO-WIRELESS-BASE the GNSS's CH340 USB-UART enumerates as `ttyUSB0` and collides with the console and login. That is a separate fix and is not part of this track.
