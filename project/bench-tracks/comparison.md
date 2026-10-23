# Bench compute tracks compared

**This is a dated snapshot from 2026-10-23, not a purchasing record.** Nothing has been bought, so no board has booted our image and nothing here is measured. Every power, runtime and RF figure is calculated from datasheets and schematics in the track folders. Purchases go through [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36) and the Linear "OpenMANET POC — Purchase BOM". The visual version, with photos and the full 187-board screen, is the [Manet Bench Compute Screen](https://claude.ai/artifact/Sm3hWVZPsHHcJnTMRVeCXe). A daily refresh keeps this file and that page in step.

Per-track detail stays in each track folder; this file only lines the tracks up.

| Track | Folder | Ticket |
|---|---|---|
| CM5 baseline on Waveshare CM5-DUAL-ETH-BASE | [cm5/](cm5/README.md) | [GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28) |
| Gateworks Venice GW7201 (GW11048-2 kit) | [venice/](venice/README.md) | [GHO-85](https://linear.app/ghostnet-labs/issue/GHO-85) |
| FriendlyElec NanoPC-T6 LTS | [nanopc-t6/](nanopc-t6/README.md) | [GHO-87](https://linear.app/ghostnet-labs/issue/GHO-87) |
| Protectli VP2430e | [protectli/](protectli/README.md) | [GHO-86](https://linear.app/ghostnet-labs/issue/GHO-86) |

## Evidence

| | CM5 | Venice | NanoPC-T6 LTS | Protectli |
|---|---|---|---|---|
| Image builds in CI | Yes, [firmware #53](https://github.com/ghostnet-labs/firmware/pull/53) | Yes, [firmware #52](https://github.com/ghostnet-labs/firmware/pull/52) | Yes, [firmware #55](https://github.com/ghostnet-labs/firmware/pull/55) | Yes, [firmware #54](https://github.com/ghostnet-labs/firmware/pull/54) |
| Hardware bought | No | No | No | No |
| Boots our image | Not tried | Not tried | Not tried | Not tried |
| Bench-measured | Nothing | Nothing | Nothing | Nothing |

## Side by side (calculated)

Costs come from each track's `build-list.md`; draw and runtime from each `power-budget.md`, on the 78 Wh 3S2P pack those budgets use.

| | CM5 | Venice | NanoPC-T6 LTS | Protectli |
|---|---|---|---|---|
| One node, full build | about $484 | about $1,182 | about $463 | about $1,130 |
| Draw from pack, typical | about 10.5 W | 9 to 13 W | 8 to 15 W | about 15 W |
| Draw, peak | about 27 W | 15.8 W worst case | about 24 W worst case | about 38 W |
| Runtime, typical | about 7.4 h | 5.8 to 8.4 h | 5.0 to 9.5 h | about 5.2 h |
| Pack input | 7 to 36 V carrier input, LM74700 in front; the carrier buck computes to about 5.40 V, above the CM5's 5.25 V limit | 8 to 60 V with reverse protection | 5.5 to 20 V, no reverse-polarity protection | 12 V only, through a Victron Orion-Tr 12/12-9 |
| Wi-Fi mesh card (D-026) | AW7916-AED on a Sintech M-to-A+E adapter | AW7916-NPD mini-PCIe (same MT7916 chip, not the V1 form factor) | AW7916-AED in the E-key bay | AW7916-AED in the E-key bay |
| 3.3 V for the card | Dedicated 3 A MP1658 rail; adapter about 2 A (Unverified) | About 1.5 A per socket (Unverified); 15 W shared | Official 3 A MP2143 rail | Unpublished; slot rated 8 W |
| Card fit | Overhangs; nylon spacer on the adapter, Kapton on HDMI (the carrier nuts are under the adapter) | Fits | Not cleanly, see [nanopc-t6/e-key-fit.md](nanopc-t6/e-key-fit.md) | Fits |
| GNSS and PPS | MAX-M10S on UART0, PPS on GPIO18 | On-board u-blox, PPS on GPIO1_15 | MAX-M10S on UART0, PPS on GPIO3_B7 | MAX-M10S through a MAX3232 into COM2, PPS on DCD |
| INA228 power monitor | Kernel driver | Userspace script (no imx kernel backport) | Kernel driver | Kernel driver on a USB-I2C bridge |

All three kernel-driver tracks, and the V1 image, use the one `kmod-hwmon-ina238` package defined in the firmware's generic `package/kernel/linux/modules/hwmon.mk`.

## CM5 carriers

Both Waveshare carriers are in use, for different jobs, and run the same `bcm2712_mm8108-usb` image:

- **CM5-IO-WIRELESS-BASE** is the Track A POC node (D-003, A-02) and is the carrier in the GHO-36 cart.
- **CM5-DUAL-ETH-BASE** is the bench baseline. The 2026-10-12 screen picked it for its dedicated 3 A M.2 rail, 7 to 36 V input and 40-pin header. No decision row records this choice yet.

## Changes since the 2026-10-12 screen

- All four track images build in CI; the four firmware PRs above are merged.
- A 3052 card does not fit the NanoPC-T6 LTS E-key bay cleanly ([nanopc-t6/e-key-fit.md](nanopc-t6/e-key-fit.md)).
- Rockchip kernels prepare again: the duplicate patches that rejected at patch time are gone, and `016-v6.13` is the single remaining copy of the combphy patch.
- The INA228 backport is one shared kernel package for every track except Venice.
- The full Protectli node costs about $1,130, not $720: the $419 box is barebone, and the node also needs RAM, storage, a Wi-Fi kit, a 12 V converter and a MAX3232.
- The Venice worst case, about 15.8 W, exceeds Gateworks' "up to 15 W" figure.
- The CM5-DUAL-ETH-BASE buck computes to about 5.40 V; measure it before seating a CM5.
- Seller pages on 2026-10-23: SparkFun's CM5104064 and MAX-M10S breakout show backorder, and Seeed shows the CM5104016 out of stock. The NanoPC-T6 LTS and the GW11048-2 kit show in stock. Protectli's VP2430e page offers it for sale but states no stock level.
