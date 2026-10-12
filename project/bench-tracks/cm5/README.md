# Bench track: CM5 on the Waveshare CM5-DUAL-ETH-BASE (baseline)

Stage 2, track 1 of 4 from the Stage 1 bench compute screen (2026-10-12). This track is the reference that the Venice, NanoPC-T6 and Protectli tracks are compared against. It uses the same Raspberry Pi CM5 as the POC ([track-a.md](../../poc/track-a.md)). The difference is the carrier: the [Waveshare CM5-DUAL-ETH-BASE](https://www.waveshare.com/cm5-dual-eth-base.htm) replaces the CM5-IO-WIRELESS-BASE. It takes 7 to 36 V directly, has a dedicated 3 A regulator on its M.2 slot, and has a 40-pin header.

**Status (2026-10-12): software only. Nothing has been bought, and no CM5 has booted our image ([GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28)).**

![CM5-DUAL-ETH-BASE, what's on board (Waveshare)](https://www.waveshare.com/img/devkit/CM5-DUAL-ETH-BASE/CM5-DUAL-ETH-BASE-details-intro.jpg)

| File | What it holds |
|---|---|
| [carrier.md](carrier.md) | What the carrier schematic says about power, M.2, USB and the header, with schematic references |
| [power-budget.md](power-budget.md) | Load-by-load power budget at 5 V and at the 3S pack |
| [build-list.md](build-list.md) | Parts for one bench node (a screening snapshot, not a purchasing record) and the wiring |
| [bring-up.md](bring-up.md) | First-power checks, flashing, configuration and the verification commands, in order |

## Scorecard

All four tracks use the same columns. Evidence levels, weakest to strongest: **paper** (datasheet, schematic or source reading), **build-verified** (in a CI-built image, or the build of an open PR), **boot-verified** (seen running on the hardware), **bench-measured** (a number taken on the bench).

| Column | CM5 + DUAL-ETH-BASE | Evidence |
|---|---|---|
| Wi-Fi card (AW7916-AED, MT7916) | M.2 M-key slot (PCIe Gen2 x1) with its own MP1658 3.3 V rail, 3 A class, through a Sintech M-key to A+E adapter. `kmod-mt7915e` and the MT7916 firmware are in the ekh-bcm2712 image. Risks: the adapter's E-key side has four 3.3 V pins against the card's 3 A request, and the external PCIe 32-bit DMA limit ([raspberrypi/linux#7026](https://github.com/raspberrypi/linux/issues/7026), fallback overlay in [bring-up.md](bring-up.md)) | Driver and firmware: **build-verified**. Slot power and fit: **paper** |
| HaLow USB (GW16167 on a Pier42 USB carrier) | Goes on the USB-C port, which is the BCM2712's own dwc2 controller and is not shared with the 2.5 GbE NIC or the hub. That port needs `dtoverlay=dwc2,dr_mode=host`, added in [firmware#53](https://github.com/ghostnet-labs/firmware/pull/53). `kmod-mm8108` is in the image | mm8108 driver: **build-verified**. dwc2 host: **paper** until firmware#53 builds |
| GNSS + PPS (MAX-M10S + ANN-MB1) | NMEA on header UART0 (pins 8/10, `/dev/ttyAMA0`), PPS on GPIO18 (pin 12, `/dev/pps0`). gpsd gets both after [packages#22](https://github.com/ghostnet-labs/packages/pull/22) and the gpsd init fix in [firmware#53](https://github.com/ghostnet-labs/firmware/pull/53). Without that fix, gpsd received the two-device value as one path and read nothing | **paper** (fixes pending CI) |
| 3S power | 7 to 36 V barrel input, SMAJ40CA TVS, then an MP9447 buck to 5 V. A 3S pack (9.0 to 12.6 V) plugs straight in behind an LM74700 ideal diode. Peak budget is about 27 W from the pack ([power-budget.md](power-budget.md)). Open item: the buck's feedback divider computes to about 5.40 V, above the CM5's 5.25 V input limit, so measure it before seating the CM5 | **paper** |
| OpenWrt | `ekh-bcm2712` (device `bcm2712_mm8108-usb`), CI-built from ghostnet-labs/firmware 24.10 since 2026-10-01 ([D-021](../../decisions.md)). One image covers both CM5 carriers | **build-verified**. Boot: not yet ([GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28)) |
| Other | INA228 battery telemetry: our 6.6 kernel had no INA228 driver at all, so firmware#53 backports it with an `ina228` overlay; this also fixes Ghostnet V1. 2.5 GbE port: a USB 3 NIC whose chip the schematic does not name; `r8152` is in the image. Gigabit port: the CM5's own PHY (`eth0`). RTC battery header, fan header | INA228: **paper** until firmware#53 builds. NICs: **paper** |

## Software work done for this track

| Change | Where |
|---|---|
| dwc2 USB host on CM5, header pin map for both carriers in `distroconfig.txt` | [firmware#53](https://github.com/ghostnet-labs/firmware/pull/53) |
| INA228 driver backport (v6.17 `ina238.c`), `kmod-hwmon-ina238`, `ina228` DT overlay | [firmware#53](https://github.com/ghostnet-labs/firmware/pull/53) |
| gpsd init passes each configured device separately (same fix as the Venice track's [firmware#52](https://github.com/ghostnet-labs/firmware/pull/52)) | [firmware#53](https://github.com/ghostnet-labs/firmware/pull/53) |
| gpsd device list covers UART0 and the USB-UART; the UPS script leaves a DT-declared monitor alone | [packages#22](https://github.com/ghostnet-labs/packages/pull/22) |
| Corrected isolation figures (track-a, D-020), the CM5116064 price and the i.MX8MP OpenWrt support statement | [docs#83](https://github.com/ghostnet-labs/docs/pull/83), merged |

## Bench measurements still needed

Each of these needs hardware and is not counted as done. The work is tracked on [GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28) (run the CM5 image on development hardware), and the steps are in [bring-up.md](bring-up.md).
- The carrier's 5 V output voltage, and its current headroom at a 3S pack's low end.
- The AW7916-AED on the Sintech adapter at a full TX burst: the 3.3 V droop at the card, and whether the card probes without the 32-bit DMA overlay.
- HaLow on the dwc2 port under traffic.
- GNSS C/N0 against stepped HaLow and Wi-Fi power, using the screen's ground-bar layout and sweep order.
- The 2.5 GbE chip identity and idle power (an open question for Waveshare).
