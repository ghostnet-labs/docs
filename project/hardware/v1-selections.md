# Track B: V1 custom carrier selections

## Expanded capability scope

The current capability contract is [Maer requirements](../requirements/maer-capabilities.md) (D-029 through D-032). This document describes the selected baseline and does not by itself demonstrate the expanded contract. GHO-50 owns POC hardware reconciliation; GHO-55 owns V1 impact and freeze disposition. 


## Goal

A product-oriented V1 carrier for the CM5 with two M.2 radio modules, GNSS, sealed Gigabit Ethernet, battery telemetry, node-side voice/PTT through an external OpenVLM USB audio module, and a fanless rugged enclosure. It is headless, with no buttons or user-facing LEDs. V1 has one sealed USB-C DATA / CHARGE service port that carries USB-C PD charging and CM5 console and service data, plus a separate sealed USB-C host port for the OpenVLM module. Hidden test pads are acceptable. This file owns the Track B selections. [v1-reference.md](v1-reference.md) is supporting engineering detail and refers to these rows by ID.

## Power and battery requirements

The battery is a custom removable, sealed 3S2P 18650 pack (about 76 Wh target) that is waterproof as an assembly and swapped without tools. The radio must support charging while operating. USB-C PD feeds an in-radio charger and power-path stage, and USB 2.0 data on the same port provides CM5 console and service access. The pack-swap operating requirement is D-027; V1 needs an internal bridge-energy source or an equivalent hold-up subsystem ([GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38)). The pack voltage range is 9 to 12.6 V, with current limited by the pack protection (at least 6 A continuous). The battery-to-radio contact system and the pack sealing are designed together ([v1-battery-pack.md](v1-battery-pack.md)).

## Selections register

Status words are defined in [../README.md](../README.md). Open parts are tracked in [GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11).

| ID | Function | Selection | Status |
|---|---|---|---|
| B-01 | Compute | Raspberry Pi CM5008032 (8 GB, 32 GB eMMC, no wireless) on Amphenol 10164227-1004A1RLF connectors | Selected. SKU and availability to verify. |
| B-02 | HaLow radio | Gateworks GW16170 / MM8108-M20, M.2 2230 E-key, USB 2.0, MMCX antenna | Selected. CM5 and Linux support unproven. M.2 pinout and control-pin behavior Verified 2026-09-30 (Gateworks wiki). |
| B-03 | Wi-Fi radio | [AsiaRF AW7916-AED](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) ([datasheet](https://asiarf.com/wp-content/uploads/2026/07/260709_Datasheet_AW7916-AED_V1-1P.pdf)): MediaTek MT7916, Linux mt7915e driver, Wi-Fi 6E (2.4 GHz plus 5 or 6 GHz), M.2 3052 A+E key, 30 x 52 mm, 3 x IPEX, PCIe WLAN, no Bluetooth. 10 W maximum and 8 W average at 3.3 V; needs a 3.3 V supply of at least 3 A. Replaces the AIW-170BQ, whose firmware has no 802.11s mesh point (D-026, R-19). | Selected. Two cards approved for the bench 2026-10-02. Bench gate: enumerates on the CM5 PCIe x1, `iw phy` lists mesh point, and an 802.11s link comes up between two nodes ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)). M.2 pin table not yet checked ([GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9)). |
| B-04 | USB hub | TI TUSB4041IPAPRG4, four-port USB 2.0 hub; port 1 serves HaLow, port 3 serves the external OpenVLM host connector, and ports 2 and 4 are spare (V1 has no Bluetooth, D-026) | Selected. Supersedes TUSB4020BI (D-023). |
| B-05 | GNSS | u-blox MAX-M10S-00B, UART plus PPS, external active antenna | Selected. Antenna connector open ([GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11)). |
| B-06 | Ethernet | CM5 native Gigabit PHY and an Amphenol LTW RCP-5SPFFH-SCU7001 sealed panel feed-through (IP67 unmated and mated, shielded Cat5e, 13/16"-28 UNS screw thread), with an Amphenol LTW CAP-WACMSPC1 screw cap on a rubber strap (IP67). The feed-through ends in an RJ45 socket inside the wall. A short pigtail runs from an RJ45 plug in that socket to a Molex Pico-Lock 1.50 mm 8-circuit right-angle header on the carrier (504050-0891, housing 504051-0801, terminals 504052-0098, GHO-45), which replaces a board-side RJ45 (D-025). The pigtail is custom: Cat5e or Cat6 cable crimped to 504052 terminals at the board end and a T568B plug at the other. Discrete magnetics on the carrier. No LEDs and no PoE (D-022). | Selected. Header signal-integrity limits are in v1-reference.md §10. Still to choose: the magnetics. Positions are in v1-reference.md §18. |
| B-07 | USB-C service port | GCT USB4720-03-A sealed USB-C DATA / CHARGE port (IP67 mated and unmated, USB 2.0, 5 A / 48 V capability, 20,000 mating cycles) | Selected baseline. Enclosure integration, caps, and mating cable to validate. |
| B-08 | USB-C PD controller | TI TPS25751A | Selected. Orderable variant open: the D device (38-pin REF package) and the S device (32-pin RSM package) differ in package ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)). |
| B-09 | Charger and power path | TI BQ25798 (BQ25798RQMR), 1 to 4S buck-boost charger and system power path. Reference starting point: TI USB-PD-CHG-EVM-01. | Selected. Integration open ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)). |
| B-10 | Pack monitor | TI BQ76942 (BQ76942PFBR) pack monitor, protector, and balancer | Selected. Candidates for protection FETs (CSD18512Q5B), secondary overvoltage protector and fuse (BQ7721602 + ITV4030L1212), current sense (WSK2512 2 mΩ) and thermistors (4 × Semitec 103AT-2) are in [v1-battery-pack-gates.md](v1-battery-pack-gates.md) ([GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8)). |
| B-11 | Pack cells | Molicel INR-18650-M35A, six cells in 3S2P, about 75.6 Wh nominal | Selected. Same cell as Track A. Maximum charge current is unresolved: data sheet copies give 1.7 A and 3.4 A per cell ([v1-battery-pack-gates.md](v1-battery-pack-gates.md), [GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8)). |
| B-12 | Battery-to-radio contacts | Eight Mill-Max 7911-0-15-20-86-14-11-0 spring-loaded contacts on a replaceable radio-side daughterboard, landing on hard-gold pads on the pack side ([v1-battery-pack.md](v1-battery-pack.md)) | Selected for V0. |
| B-13 | Pack latch | Southco C3-99-107-055 small-profile 5 lb-class Grabber Catch. On 2026-09-30 DigiKey Marketplace showed multi-thousand stock at about $5.40 each; on 2026-10-09 the only listing found was DigiKey Marketplace with no price and no stock ([v1-bom-baseline.md](v1-bom-baseline.md)). Supply source open. | Selected for V0. Keeper orientation, mounting hole pattern, and preload to verify against the trade drawing before enclosure release. |
| B-14 | Battery monitor | TI INA228AIDGSR with a Vishay WFK0612R0100FE66 10 mOhm Kelvin shunt | Selected. |
| B-15 | Input eFuse | TI TPS26633RGER (limit 5.56 A, UVLO 7.95 V rising and 7.43 V falling nominal, about 7.7 to 8.3 V rising across tolerances, fixed 32.8 V overvoltage clamp) | Selected. Values calculated, verify on the bench (see D-019). |
| B-16 | Reverse polarity | TI CSD19533Q5A blocking FET, with a BSS138-class Q2 fast pulldown | Candidate. Topology to verify. |
| B-17 | TVS | Diodes Inc. SMBJ33CA (SMBJ33CA-13-F) | Candidate. Depends on the pack and charging input. |
| B-18 | 5 V and 3.3 V bucks | TI LM76005 (LM76005RNPR) x 2 (2.5 A and 4.5 A allocations) | Selected. The 3.3 V allocation was raised to 4.5 A at 3.39 V for the AW7916-AED (D-026, [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10), [v1-3v3-rail.md](v1-3v3-rail.md)). The 5 V allocation is 2.5 A, the CM5 maximum from its datasheet §B.3; the USB accessory load on top is still pending. |
| B-19 | Radio load switches | TI TPS22975DSGT x 2 (WIFI_PWR_EN and HALOW_PWR_EN) | Selected. |
| B-20 | Supervisor | TI TPS386000RGPR (four rails, watchdog, PMIC_Enable recovery) | Selected. Bench-test recovery. |
| B-21 | RF connectors | MMCX (HaLow), 3 x IPEX on the Wi-Fi card (type to confirm on arrival), GNSS active antenna connector | GNSS connector open ([GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11)). The GNSS active antenna must have a filter ahead of its LNA and meet the criteria in [v1-rf-coexistence.md](v1-rf-coexistence.md) §2.5. |
| B-22 | Voice/PTT module | OpenMANET Voice Link Module VLMKW0100 (Kenwood accessory variant), external USB audio/PTT device using CM108B + 93C46 EEPROM + GPIO1 OpenVLM identity strap | Selected. Supplier ordering code, availability, and the exact Kenwood accessory cable SKU must be verified before procurement. |
| B-23 | OpenVLM host connector | GCT USB4720-03-A sealed USB-C receptacle, one additional connector beyond B-07; configured as a USB 2.0 downstream-facing host port with switched +5V VBUS | Selected baseline. USB-C host CC implementation, VBUS switch/current limit, USB ESD, and enclosure CAD fit remain to verify ([GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11), [GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7)). |
| B-24 | Pack-swap bridge | Analog Devices LTC3350IUHF#PBF backup controller. 6 × KYOCERA AVX SCCV60B107SRB (100 F, 2.7 V) as 3S2P, charged to 6.525 V (VCAP DAC code 12). RSNSC 6 mΩ, RSNSI 7.5 mΩ, Bourns SRP1265A-4R7M, 40 V FETs, 500 kHz, +VBUS_HOLD 7.0 V in backup, power stage on the top side. Bank fused. Design and calculations: [v1-bridge-selection.md](v1-bridge-selection.md) | Selected working default (D-047), not frozen. Bank placement open: tray under the carrier (+23 mm, recommended) or a reworked contact array (+12.6 mm, GHO-8), waiting on Justin. Bench gates B1 to B10 in v1-bridge-selection.md; GHO-30 load and shutdown energy can change the population |
| B-25 | M.2 sockets | TE Connectivity 2199119-6, about 21.9 x 8.7 x 3.2 mm, one each for the HaLow and Wi-Fi cards | Candidate, mechanical reference only. Key type and footprint not yet checked against the TE drawing; the Wi-Fi current qualification is open ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10), [GHO-26](https://linear.app/ghostnet-labs/issue/GHO-26), [v1-3v3-rail.md](v1-3v3-rail.md)). |
| B-26 | Hub core regulator | TI TLV62568DBVR buck, CM5_3V3 to HUB_1V1 at 1.10 V, sized for the TUSB4041I global-reset current (370 mA max, SLLSEK3F §5.7); 2.2 µH inductor | Candidate, V1 working default (D-044). Inductor MPN open ([GHO-26](https://linear.app/ghostnet-labs/issue/GHO-26)); efficiency at this load Unverified ([v1-netplan-blocker-proposals.md](v1-netplan-blocker-proposals.md) K-9). At the hub's 98 mA active load it runs in power-save mode, so its frequency varies with load. If C7 shows its harmonics in the GNSS band, the forced-PWM TI TPS62A01A (2.4 MHz, SLUSEG9E; not pin-compatible) is the alternative ([v1-rf-coexistence.md](v1-rf-coexistence.md) §3.2) |
| B-27 | GNSS PPS isolation buffer | TI SN74LVC1G34DCKR, Ioff-rated single buffer powered from CM5_3V3, between MAX-M10S TIMEPULSE and GNSS_PPS | Proposed (D-044). Keeps TIMEPULSE, which shares SAFEBOOT_N, from being pulled low at GNSS start-up ([v1-netplan-blocker-proposals.md](v1-netplan-blocker-proposals.md) K-8) |

## Power tree

The chain runs from the battery interface through input transient and reverse-polarity protection, the TPS26633 eFuse, and the 10 mOhm shunt (INA228 monitoring) to VBAT_PROTECTED. The shunt sits after the eFuse so the INA228 never sees reverse polarity. The TPS26633 clamps at a fixed 32.8 V and its power limit cannot go below 60 W, so the earlier adjustable overvoltage cutoff and 40 W limit are dropped. The exact protection topology is being revalidated around the removable 3S2P pack and in-radio charging ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)). Calculated component values are in [v1-reference.md](v1-reference.md), sections 12 and 13.

VBAT_PROTECTED feeds an LM76005 5 V buck (+5V_SYS for the CM5 and USB, including switched USB VBUS for the OpenVLM accessory) and an LM76005 3.3 V buck (+3V3_RADIO). +3V3_RADIO feeds two TPS22975 switches (WIFI_3V3 and HALOW_3V3) and a filtered +3V3_GNSS. Independent radio power switching lets software tell apart a radio that is deliberately off, one that failed to start, a radio power fault, a main power fault, low battery, and an input protection trip. A TPS386000 supervises four rails and, together with the CM5 watchdog, can pull PMIC_Enable low. Recovery order: reset the USB device, reset the hub, power-cycle the radio, then supervisor and PMIC recovery.

## PCB and thermal approach

- Eight-layer stackup. The final stackup and impedance rules come from the chosen fabricator. Controlled impedance is required for PCIe, USB, Ethernet, and RF lines.
- Thermal operating requirement and permitted cooling strategy are D-028; qualification remains under GHO-12. Fanless, with the enclosure acting as the heat spreader and external fins on the lid (D-035): the CM5 and the Wi-Fi card couple to the lid through thermal interface pads, and the power converters couple to the chassis through copper pours and thermal vias.
- Top side: CM5, both M.2 slots, GNSS, Ethernet, and RF connectors. Bottom side: converters, INA228, protection, load switches, supervisor, and test pads.
- Power sits in a concentrated island of about 45 x 25 mm in the lower middle. No inductors, regulators, or tall parts go between the CM5 and the carrier (top side, about 2.5 mm of clearance). Bottom-side power parts may sit in the CM5's shadow; the CM5 is not an RF module. Switching power should not sit under RF modules.
- The module footprints (CM5, the 30 x 22 mm HaLow card and the 30 x 52 mm Wi-Fi card) total about 4,420 mm2, roughly 48 percent of 138 x 67 mm. The real constraints are RF connector placement, antenna separation, keepouts, M.2 clearances, the Ethernet and battery connectors, inductors, thermal copper, mounting holes, and enclosure walls.
- The working PCB target is 138 x 67 mm. It grew from 117 x 67 mm to fit the 30 x 52 mm Wi-Fi card in its own column (D-026) and should not grow again until CAD proves it must ([GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7)).

## Gates unlocked by Track A

1. Measured power draw finalizes the power tree and converter sizing ([GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) then [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)).
2. GPS coexistence results set the floorplan and GNSS placement ([GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) then [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12)).
3. The pack design and the charging power path unlock the input protection design ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10), [GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8)).
4. A two-node 802.11s link on the AW7916-AED closes the Wi-Fi selection ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)).

## Not yet locked

Final PCB outline, mounting holes, enclosure dimensions, connector locations, board thickness, thermal interface, PCB stackup, TVS and reverse-polarity implementation, eFuse resistor values and current limits, buck components, RF connector selection, and antenna separation.

## Track A versus Track B

Differences are acceptable for a POC unless a row says otherwise. Track A feeds Track B only through measured results.

| Item | Track A | Track B | Resolution |
|---|---|---|---|
| CM5 SKU | 4 GB / 16 GB eMMC, wireless (A-01) | 8 GB / 32 GB eMMC, no wireless (B-01) | Acceptable for a POC. The Track B SKU is chosen later. |
| Wi-Fi radio | AW7916-AED on an M-key adapter (A-09, D-034) | AW7916-AED M.2 3052 Wi-Fi 6E, MT7916, mt7915e (B-03) | Same card. The POC bench runs the V1 card's mesh gate ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)); V1 still has to prove its own socket, power and antennas. |
| HaLow radio | GW16167 through the Pier42 USB carrier (A-04, A-05) | GW16170 high-power MM8108-M20 in a native M.2 E-key slot (B-02) | Same MM8108 family and software path. Repeat high-power RF, GNSS, and thermal testing with the GW16170 before Track B is frozen. |
| Power source | Waveshare 3S UPS, 5 V output, three M35A cells, about 37 Wh (A-14, A-15) | Custom 3S2P pack, 9 to 12.6 V, about 75.6 Wh, charged over USB-C (B-11) | Same cell baseline. Measure Track A run time and regulator losses before resizing the Track B pack. |
| System power | About 10 W typical (estimate) | 35 W design capability target, not expected consumption | Measure in Track A, then resize ([GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) then [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)). |
| Board size | 145 x 90 mm carrier (A-02) | 138 x 67 mm working PCB target (D-026) | Track A does not target MPU5-class size. Track B aims to get as close to MPU5 size as CAD allows (D-016). |

## Verified, estimated, and unconfirmed

- **Verified from documents or live pages.** Part specifications, stock and prices (except where marked estimated), connector types and mating, the Gateworks board-file download, the Morse Micro engineer statements, the u-blox immunity figure, and the GW16170 M.2 pinout and control-pin behavior (Gateworks wiki, checked 2026-09-30).
- **Estimates.** Stack heights other than the cooler and adapter, enclosure sizes and volumes, run times, isolation figures, thermal expectations, and node power draw.
- **Not confirmed.** an 802.11s mesh link on the Track B AW7916-AED under mt7915e ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)), the GW16170 on the CM5, the config lines that enable the header UART and I2C on the Track A carrier, the Track B pinouts for the CM5 GPIO and the AW7916-AED M.2 slot ([GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9)), how the UPS feeds the Track A carrier ([GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36)), the final pack contact, latch, and seal geometry ([v1-battery-pack.md](v1-battery-pack.md)), hot-swap bridge sizing ([GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38)), and CM5 SKU availability.
