# NanoPC-T6 LTS bench node: power budget

All figures are from published sources or are calculated, and none has been measured. The bench steps that replace each estimate with a measurement are in [bring-up.md](bring-up.md). Open questions are on [GHO-87](https://linear.app/ghostnet-labs/issue/GHO-87).

## 1. Input

| Item | Value | Status |
|---|---|---|
| Board input range | 5.5 x 2.1 mm DC jack, "5V~20V, 12V is recommended" | Verified 2026-10-12, [wiki](https://wiki.friendlyelec.com/wiki/index.php/NanoPC-T6) "About Power" |
| Silkscreen and schematic | The jack is labelled 5.5 to 20 V. The input path is 2 x 4 A ferrites, an SMAJ22A TVS, then two MP8759GD bucks making 5V0 and 4V0_SYS. | Verified 2026-10-12, [LTS 2310 schematic](https://wiki.friendlyelec.com/wiki/images/4/44/NanoPC-T6_LTS_2310_SCH.pdf) |
| Reverse-polarity protection | **None** on the board. A reversed pack lead goes straight into the TVS and the bucks. | Verified from the schematic. This is why the LM74700 is required. |
| Pack | 3S Li-ion, 9.0 V (3.0 V/cell cut-off) to 12.6 V (full) | Same cells as B-11 in [v1-selections.md](../../hardware/v1-selections.md) |
| Margin at an empty pack | 9.0 V against the 5.5 V minimum is 3.5 V | Calculated |
| Margin at a full pack | 12.6 V against the 20 V maximum, and below the SMAJ22A's 22 V standoff | Calculated |
| Board power limit | "Total 35W" across all outputs | Verified, wiki power table |

The pack plugs straight in through the LM74700 and INA228. No buck-boost is needed, unlike the Protectli track, and no 5 V regulator, unlike a bare CM5.

## 2. Rails the node uses (wiki power table, Verified 2026-10-12)

| Port | Rated output | Used for |
|---|---|---|
| M.2 E-key | 3.3 V / 3 A (dedicated MP2143 buck, schematic p.30) | AW7916-AED |
| USB-A 2.0 | 5 V / 2 A | Pier42 carrier with the GW16167 |
| 10-pin USB 2.0 header | 5 V / 2 A | Alternative HaLow port, inside an enclosure |
| 40-pin header | 5 V / 0.5 A, 3.3 V / 0.5 A | MAX-M10S breakout (3.3 V), INA228 logic (3.3 V) |
| M.2 M-key | 3.3 V / 3 A | Unused. No 2280 SSD with a 3052 Wi-Fi card ([e-key-fit.md](e-key-fit.md)) |

## 3. Load, one node

| Load | Typical | Worst case | Source |
|---|---|---|---|
| NanoPC-T6 LTS (RK3588, 4 GB, eMMC, 2x 2.5 GbE, fan) | about 3 to 6 W | about 12 W with all CPU cores loaded | **Unverified.** FriendlyElec publishes no idle or load figure. This range is a planning estimate for an RK3588 board; bring-up step 9 measures it. |
| AsiaRF AW7916-AED | 4 to 8 W | 10 W (3.3 V / 3 A) | [AsiaRF](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) and the screen |
| GW16167 HaLow on the Pier42 carrier | 0.33 W (0.1 A at 3.3 V) | about 1.2 W | [Gateworks wiki](https://trac.gateworks.com/wiki/expansion/gw16167) |
| MAX-M10S breakout + ANN-MB1 | about 0.1 W | about 0.15 W | u-blox typical figures; the ANN-MB1 draws 15 mA at 5 V ([data sheet](https://cdn.sparkfun.com/assets/3/3/3/8/d/ANN-MB1_DataSheet_UBX-21005551.pdf)) |
| INA228, LM74700 | negligible | under 0.1 W including the 15 mΩ shunt at 2.7 A | Calculated |
| **Node total** | **about 8 to 15 W** | **about 24 W** | Sum, before buck losses |

The worst case is 24 W against the board's 35 W total, so the board's own limit is not the constraint. The E-key rail is the closest to its limit: 10 W worst case against 9.9 W (3.3 V x 3 A). This is the same squeeze as every track with this card, and the reason bring-up step 10 steps TX power up while logging.

Input current at an empty pack and worst-case load: 24 W / 9.0 V is about 2.7 A, before buck efficiency. That is within the 4 A input ferrites and the Pololu LM74700 board's 10 A or 12 A rating.

## 4. Run time on the pack

The pack is the B-11 cell set: 3S2P Molicel M35A, about 75.6 Wh nominal.

| Load | Run time |
|---|---|
| 8 W (light traffic) | about 9.5 h |
| 15 W (busy mesh) | about 5.0 h |
| 24 W (worst case, all CPU cores loaded) | about 3.2 h |

These assume the full nominal capacity is usable; the pack's own cut-off and ageing reduce them. OpenMANET does not load the CPU heavily, so the realistic range is the first two rows. The board's idle draw is the number that decides this track against the CM5 (about 2.3 W idle) and Venice (3.9 W typical), and it is unpublished.

## 5. Thermal note

- The board is rated **0 to 70 °C** ambient (wiki). That is the narrowest of the tracks: Venice is -40 to +85 °C, and the AW7916 card itself is -10 to +70 °C.
- The RK3588 needs a heatsink and fan. The board's 5 V fan header is driven by PWM1_M1 (schematic p.34). Upstream has no fan node, so [firmware #55](https://github.com/ghostnet-labs/firmware/pull/55) adds one; the fan starts at full speed and `/sys/class/hwmon/*/pwm1` lowers it.
- The E-key card is on the underside, away from a top heatsink. Its own heat goes into the board and the air under it, so leave airflow under the board. Bring-up step 10 logs SoC and card temperature.
