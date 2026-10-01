# Track B: V1 custom carrier selections

## Goal

A product-oriented V1 carrier for the CM5 with two M.2 radio modules, GNSS, sealed Gigabit Ethernet, battery telemetry, and a fanless rugged enclosure. It is headless, with no buttons or user-facing LEDs. V1 has one sealed USB-C DATA / CHARGE service port that carries USB-C PD charging and CM5 console and service data, so no separate external debug connector is required. Hidden test pads are acceptable. This file owns the Track B selections. [v1-reference.md](v1-reference.md) is supporting engineering detail and refers to these rows by ID.

## Power and battery requirements

The battery is a custom removable, sealed 3S2P 18650 pack (about 76 Wh target) that is waterproof as an assembly and swapped without tools. The radio must support charging while operating. USB-C PD feeds an in-radio charger and power-path stage, and USB 2.0 data on the same port provides CM5 console and service access. The main pack must be hot-swappable without rebooting the radio, so V1 needs an internal bridge-energy source or an equivalent hold-up subsystem ([GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38)). The pack voltage range is 9 to 12.6 V, with current limited by the pack protection (at least 6 A continuous). The battery-to-radio contact system and the pack sealing are designed together ([v1-battery-pack.md](v1-battery-pack.md)).

## Selections register

Status words are defined in [../README.md](../README.md). Open parts are tracked in [GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11).

| ID | Function | Selection | Status |
|---|---|---|---|
| B-01 | Compute | Raspberry Pi CM5008032 (8 GB, 32 GB eMMC, no wireless) on Amphenol 10164227-1004A1RLF connectors | Selected. SKU and availability to verify. |
| B-02 | HaLow radio | Gateworks GW16170 / MM8108-M20, M.2 2230 E-key, USB 2.0, MMCX antenna | Selected. CM5 and Linux support unproven. M.2 pinout and control-pin behavior Verified 2026-09-30 (Gateworks wiki). |
| B-03 | Wi-Fi radio | Advantech AIW-170BQ-001, M.2 2230 E-key, Wi-Fi 6E 2x2 (Qualcomm WCN6856), PCIe WLAN, USB Bluetooth, 2 x MHF4 | Selected. 802.11s mesh-point support unconfirmed ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)). Pin table not public ([GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9)). |
| B-04 | USB hub | TI TUSB4020BI, two downstream ports (HaLow and Bluetooth) | Selected. |
| B-05 | GNSS | u-blox MAX-M10S-00B, UART plus PPS, external active antenna | Selected. Antenna connector open ([GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11)). |
| B-06 | Ethernet | CM5 native Gigabit PHY and an Amphenol LTW RCP-5SPFFH-SCU7001 sealed panel feed-through (IP67 unmated and mated, shielded Cat5e, 13/16"-28 UNS screw thread), with an Amphenol LTW CAP-WACMSPC1 screw cap on a rubber strap (IP67). The feed-through ends in an RJ45 socket inside the wall, so the carrier needs its own board-side RJ45 and a short internal patch cable. No LEDs and no PoE (D-022). | Selected. Board-side jack, magnetics and internal cable to choose. Mechanical fit to redo in [GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7): the feed-through, plug and cable bend need about 42 mm of depth and 25 mm of height, against the 20 x 20 mm placeholder. |
| B-07 | USB-C service port | GCT USB4720-03-A sealed USB-C DATA / CHARGE port (IP67 mated and unmated, USB 2.0, 5 A / 48 V capability, 20,000 mating cycles) | Selected baseline. Enclosure integration, caps, and mating cable to validate. |
| B-08 | USB-C PD controller | TI TPS25751A | Selected. |
| B-09 | Charger and power path | TI BQ25798, 1 to 4S buck-boost charger and system power path. Reference starting point: TI USB-PD-CHG-EVM-01. | Selected. Integration open ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)). |
| B-10 | Pack monitor | TI BQ76942 pack monitor, protector, and balancer | Selected. Protection FETs, current sense, and thermistors open ([GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8)). |
| B-11 | Pack cells | Molicel INR-18650-M35A, six cells in 3S2P, about 75.6 Wh nominal | Selected. Same cell as Track A. |
| B-12 | Battery-to-radio contacts | Eight Mill-Max 7911-0-15-20-86-14-11-0 spring-loaded contacts on a replaceable radio-side daughterboard, landing on hard-gold pads on the pack side ([v1-battery-pack.md](v1-battery-pack.md)) | Selected for V0. |
| B-13 | Pack latch | Southco C3-99-107-055 small-profile 5 lb-class Grabber Catch. Active and stocked through DigiKey Marketplace in multi-thousand quantity at about $5.40 each as of 2026-09-30. | Selected for V0. Keeper orientation, mounting hole pattern, and preload to verify against the trade drawing before enclosure release. |
| B-14 | Battery monitor | TI INA228AIDGSR with a Vishay WFK0612R0100FE66 10 mOhm Kelvin shunt | Selected. |
| B-15 | Input eFuse | TI TPS26633RGER (limit 5.56 A, UVLO 7.4 to 8.0 V, fixed 32.8 V overvoltage clamp) | Selected. Values calculated, verify on the bench (see D-019). |
| B-16 | Reverse polarity | TI CSD19533Q5A | Candidate. Topology to verify. |
| B-17 | TVS | Diodes Inc. SMBJ33CA | Candidate. Depends on the pack and charging input. |
| B-18 | 5 V and 3.3 V bucks | TI LM76005 x 2 (about 2 A and 4 A allocations) | Selected. Sizing pending Track A power data. |
| B-19 | Radio load switches | TI TPS22975DSGT x 2 (WIFI_PWR_EN and HALOW_PWR_EN) | Selected. |
| B-20 | Supervisor | TI TPS386000RGPR (four rails, watchdog, PMIC_Enable recovery) | Selected. Bench-test recovery. |
| B-21 | RF connectors | MMCX (HaLow), 2 x MHF4 (Wi-Fi), GNSS active antenna connector | GNSS connector open ([GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11)). |

## Power tree

The chain runs from the battery interface through input transient and reverse-polarity protection, the TPS26633 eFuse, and the 10 mOhm shunt (INA228 monitoring) to VBAT_PROTECTED. The shunt sits after the eFuse so the INA228 never sees reverse polarity. The TPS26633 clamps at a fixed 32.8 V and its power limit cannot go below 60 W, so the earlier adjustable overvoltage cutoff and 40 W limit are dropped. The exact protection topology is being revalidated around the removable 3S2P pack and in-radio charging ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)). Calculated component values are in [v1-reference.md](v1-reference.md), sections 12 and 13.

VBAT_PROTECTED feeds an LM76005 5 V buck (+5V_SYS for the CM5 and USB) and an LM76005 3.3 V buck (+3V3_RADIO). +3V3_RADIO feeds two TPS22975 switches (WIFI_3V3 and HALOW_3V3) and a filtered +3V3_GNSS. Independent radio power switching lets software tell apart a radio that is deliberately off, one that failed to start, a radio power fault, a main power fault, low battery, and an input protection trip. A TPS386000 supervises four rails and, together with the CM5 watchdog, can pull PMIC_Enable low. Recovery order: reset the USB device, reset the hub, power-cycle the radio, then supervisor and PMIC recovery.

## PCB and thermal approach

- Eight-layer stackup. The final stackup and impedance rules come from the chosen fabricator. Controlled impedance is required for PCIe, USB, Ethernet, and RF lines.
- Fanless, with the enclosure acting as the heat spreader: the CM5 couples to the shell through a thermal interface, and the power converters couple to the chassis through copper pours and thermal vias.
- Top side: CM5, both M.2 slots, GNSS, Ethernet, and RF connectors. Bottom side: converters, INA228, protection, load switches, supervisor, and test pads.
- Power sits in a concentrated island of about 45 x 25 mm in the lower middle. No inductors, regulators, or tall parts go under the CM5, which has about 2.5 mm of underside clearance. Switching power should not sit under RF modules.
- The module footprints (CM5 and two M.2 cards) total about 3,520 mm2, roughly 45 percent of 117 x 67 mm. The real constraints are RF connector placement, antenna separation, keepouts, M.2 clearances, the Ethernet and battery connectors, inductors, thermal copper, mounting holes, and enclosure walls.
- The working PCB target is 117 x 67 mm and should not be enlarged until CAD proves it must (see D-016 and [GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7)).

## Gates unlocked by Track A

1. Measured power draw finalizes the power tree and converter sizing ([GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) then [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)).
2. GPS coexistence results set the floorplan and GNSS placement ([GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) then [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12)).
3. The pack design and the charging power path unlock the input protection design ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10), [GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8)).
4. Confirmed 802.11s mesh-point support on the AIW-170BQ closes the Wi-Fi selection ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)).

## Not yet locked

Final PCB outline, mounting holes, enclosure dimensions, connector locations, board thickness, thermal interface, PCB stackup, TVS and reverse-polarity implementation, eFuse resistor values and current limits, buck components, RF connector selection, and antenna separation.

## Track A versus Track B

Differences are acceptable for a POC unless a row says otherwise. Track A feeds Track B only through measured results.

| Item | Track A | Track B | Resolution |
|---|---|---|---|
| CM5 SKU | 4 GB / 16 GB eMMC, wireless (A-01) | 8 GB / 32 GB eMMC, no wireless (B-01) | Acceptable for a POC. The Track B SKU is chosen later. |
| Wi-Fi radio | GW17032 / WLE900VX Mini-PCIe 3x3 Wi-Fi 5, QCA9880, ath10k (A-09) | AIW-170BQ M.2 Wi-Fi 6E, WCN6856, ath11k (B-03) | Track A uses a card that Gateworks has tested for 802.11s. Track B must still confirm mesh-point support ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)). |
| HaLow radio | GW16167 through the Pier42 USB carrier (A-04, A-05) | GW16170 high-power MM8108-M20 in a native M.2 E-key slot (B-02) | Same MM8108 family and software path. Repeat high-power RF, GNSS, and thermal testing with the GW16170 before Track B is frozen. |
| Power source | Waveshare 3S UPS, 5 V output, three M35A cells, about 37 Wh (A-14, A-15) | Custom 3S2P pack, 9 to 12.6 V, about 75.6 Wh, charged over USB-C (B-11) | Same cell baseline. Measure Track A run time and regulator losses before resizing the Track B pack. |
| System power | About 10 W typical (estimate) | 35 W design capability target, not expected consumption | Measure in Track A, then resize ([GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) then [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)). |
| Board size | 145 x 90 mm carrier (A-02) | 117 x 67 mm working PCB target | Track A does not target MPU5-class size. Track B aims to get as close to MPU5 size as CAD allows (D-016). |

## Verified, estimated, and unconfirmed

- **Verified from documents or live pages.** Part specifications, stock and prices (except where marked estimated), connector types and mating, the Gateworks board-file download, the Morse Micro engineer statements, the u-blox immunity figure, and the GW16170 M.2 pinout and control-pin behavior (Gateworks wiki, checked 2026-09-30).
- **Estimates.** Stack heights other than the cooler and adapter, enclosure sizes and volumes, run times, isolation figures, thermal expectations, and node power draw.
- **Not confirmed.** 802.11s mesh-point support on the Track B AIW-170BQ under ath11k ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)), the GW16170 on the CM5, the config lines that enable the header UART and I2C on the Track A carrier, the Track B pinouts for the CM5 GPIO and the AIW-170BQ M.2 slot ([GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9)), how the UPS feeds the Track A carrier ([GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36)), the final pack contact, latch, and seal geometry ([v1-battery-pack.md](v1-battery-pack.md)), hot-swap bridge sizing ([GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38)), and CM5 SKU availability.
