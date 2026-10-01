# Track B: V1 custom carrier engineering reference

**Status:** supporting reference. Last reviewed 2026-09-30, moved from Google Drive 2026-10-01.

The registers win over this file. Selections (B-nn) are owned by [v1-selections.md](v1-selections.md), pack geometry (M-nn) by [v1-battery-pack.md](v1-battery-pack.md), and decisions (D-nnn, R-nn) by [../decisions.md](../decisions.md). If this file disagrees with one of them, fix this file in the same PR. Open questions are Linear issues, not text here.

This file was reconciled on 2026-09-30: sections 10, 11, 30 and 31 were rewritten, and stale connector, pack and size references elsewhere were corrected. The other sections have not been audited line by line against the registers.

Status date: September 30, 2026. Project stage: architecture defined; first real hardware-design pass ready to continue. Target: rugged, compact, fanless, headless OpenMANET node in the physical class of an MPU5-style field node. Working PCB target: 117 x 67 mm. Primary compute: Raspberry Pi Compute Module 5.

This is the detailed supporting reference for the Track B (custom PCB) V1 hardware. It is written so another engineer or agent can resume the project without the earlier conversation. It covers requirements, architecture, selected and rejected hardware, electrical interfaces, mechanical floorplan, routing priorities, thermal strategy, unresolved decisions, validation requirements, and the recommended resume point. The cross-track summary is in [v1-selections.md](v1-selections.md) and decisions are in [../decisions.md](../decisions.md). Where this file differs, fix it and record any decision there first.

## 1. Product definition

The node is a real product architecture, not a disposable development-board prototype. It provides:

- Raspberry Pi CM5 compute (8 GB RAM, 32 GB eMMC), with no dependency on CM5 onboard wireless
- 900 MHz-class Wi-Fi HaLow mesh (North American 902 to 928 MHz), external antenna, USB interface, hardware power isolation
- 2.4/5/6 GHz Wi-Fi, 2T2R, external antennas, PCIe WLAN plus USB Bluetooth
- GNSS positioning and timing: multi-constellation, external active antenna, UART, PPS, reset, software-accessible timing
- Gigabit Ethernet through an Amphenol LTW RCP-5SPFFH-SCU7001 sealed panel feed-through (B-06, D-022), no PoE, no Ethernet LEDs
- Removable external battery pack designed by this project (3S2P 18650, about 76 Wh, decided September 30, 2026; 9 to 12.6 V in use, swapped without tools, charged in the radio while installed, through a sealed USB-C DATA / CHARGE port), reverse-polarity and transient protection, eFuse current limiting, regulated 5 V and 3.3 V, independently switchable radios, hardware supervision and watchdog
- Battery voltage, current, and power telemetry; board, radio, and CPU thermal telemetry; hardware-aware mesh telemetry exposed to software
- Fanless operation, aluminum enclosure baseline, external RF, external battery, external Ethernet
- No normal-use physical controls, no user-facing status LEDs, no required external debug connector; normal operation is controlled from an end-user device (EUD)

## 2. Design philosophy

Priority order:

1. Electrically sane
2. RF sane
3. Thermally sane
4. Mechanically sane
5. Debuggable
6. EUD-controlled
7. Manufacturable
8. Size and cost optimization

The 117 x 67 mm PCB target is important but not sacred. Do not compromise RF, thermal, mechanical, electrical, or serviceability requirements only to preserve it. Current analysis indicates the target is plausible, so the rule is: do not enlarge the PCB until an actual CAD assembly proves the target cannot be met without compromising the design. Section 31 records how this target relates to the Track A size analysis.

## 3. System architecture

- PCIe: CM5 PCIe Gen2 x1 to the AIW-170BQ Wi-Fi 6E module (two MHF4 antenna connectors)
- USB: CM5 USB2 to the TUSB4020BI hub; hub port 1 to the GW16170 HaLow module (MMCX antenna), port 2 to the AIW-170BQ Bluetooth
- Ethernet: CM5 integrated Gigabit PHY to discrete magnetics and the sealed Amphenol LTW Ethernet connector
- GNSS: CM5 UART, I2C, and PPS to the MAX-M10S, with an external active antenna
- Power path: battery spring contacts, SMBJ33CA bidirectional TVS, CSD19533Q5A blocking FET, TPS26633 eFuse, then the 10 mOhm Kelvin shunt (INA228 monitoring) and VBAT_PROTECTED
- Regulation: VBAT_PROTECTED feeds an LM76005 5 V buck (+5V_SYS to the CM5 and USB) and an LM76005 3.3 V buck (+3V3_RADIO). +3V3_RADIO feeds WIFI_3V3 and HALOW_3V3 through two TPS22975 switches, and a filtered +3V3_GNSS.

## 4. Compute

Selected: Raspberry Pi CM5008032 (8 GB RAM, 32 GB eMMC, 55 x 40 mm, four M2.5 mounting holes, integrated Gigabit Ethernet PHY, PCIe Gen2 x1, USB2, Linux ecosystem). The CM5 supplies compute, eMMC, PCIe, USB, and Ethernet in a compact module, so the carrier implements only the product-specific power, RF, battery, telemetry, and rugged I/O. SKU and availability still need verification before the BOM is frozen.

Carrier connector: Amphenol 10164227-1004A1RLF, 4.0 mm connector, about 7.44 mm connected stack height, about 2.5 mm clearance beneath the CM5. Reserve the underside for low-profile passives and routing. Do not place inductors, switching regulators, tall capacitors, or connectors under the CM5.

CM5 electrical decisions:

- GPIO_VREF is tied to CM5 3.3 V and must not float
- All CM5 5 V pins are tied to +5V_CM5
- The integrated BCM54210PE PHY is used, PCIe Gen2 x1 is used for Wi-Fi, and USB2 feeds the internal hub
- PWR_Button goes to internal test pad TP_PWR_BUTTON and nRPI_BOOT goes to TP_NBOOT; there are no physical buttons
- PMIC_Enable is used for hardware recovery; nEXTRST is not used as the external reset mechanism
- No user LEDs; Ethernet LED outputs and CM5 power/activity LEDs are unused
- No external debug USB connector; debug uses internal test pads and an internal debug UART/test points

## 5. Wi-Fi 6E: Advantech AIW-170BQ-001

Characteristics: M.2 2230 E-key, about 30 x 22 x 2.2 mm, Qualcomm WCN6856/QCA2066 family, Wi-Fi 6E (2.4/5/6 GHz), 2T2R, PCIe WLAN, USB Bluetooth, two MHF4 connectors, about -40 to +85 C. It fits the size, temperature, external-antenna, PCIe, and USB-Bluetooth requirements.

Documentation correction: older or alternate information suggested Bluetooth over UART. The current official Advantech documentation used for V1 says WLAN is PCIe and Bluetooth is USB, so V1 routes Bluetooth through the USB hub.

Power: +3V3_RADIO through a TPS22975 to WIFI_3V3, controlled by WIFI_PWR_EN. Antennas: two MHF4 external connectors, no PCB antenna.

Pin documentation: the official [Advantech AIW-170BQ V1.4 User Manual](https://advdownload.advantech.com/productfile/Downloadfile4/1-2F5N99M/AIW-170BQ_%20V1.4%20User%20Manual.pdf) provides the module pin assignment. The canonical project table and CM5/Gateworks cross-check are in [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md). Use that manufacturer table; do not substitute generic M.2 assumptions or release layout until GHO-9 review is complete.

Supply is 3.0 to 3.3 V, and the datasheet gives 632 mA average in TX mode with no peak figure. Verify before freeze: the exact M.2 pin assignment against the Advantech manual, PCIe reset and CLKREQ behavior, power sequencing, the Linux ath11k path, Bluetooth over USB on the CM5, and 802.11s mesh-point support, which OpenMANET requires (see section 31).

## 6. Wi-Fi PCIe

The CM5 PCIe Gen2 x1 link carries the 100 MHz REFCLK, TX/RX pairs, PERST#, and CLKREQ# to the AIW-170BQ. The CM5 PCIe TX already has the relevant AC coupling, so do not add capacitors on the CM5 TX path; add 220 nF capacitors on the AIW TX to CM5 RX path as required. PEWAKE#/nWAKE is not used.

M.2 socket reference: TE Connectivity 2199119-6, about 21.9 x 8.7 x 3.2 mm. Check the exact footprint and pin implementation against the manufacturer documentation before freeze.

## 7. HaLow: Gateworks GW16170 / Morse Micro MM8108-M20

Characteristics: M.2 2230 E-key, 30 x 22 x 3.5 mm, 3.3 V, USB2, external MMCX, 902 to 928 MHz North American target, up to about +28.5 dBm TX, up to about 43.3 Mbps, -40 to +85 C. It gives 900 MHz HaLow in a compact M.2 module with an external antenna and Linux networking.

Software caveat: Gateworks documents the module as tested and supported on Gateworks platforms. CM5 support is not yet proven by this project. Linux driver validation, firmware validation, USB enumeration, power sequencing, and mesh software integration are explicit V1 tasks.

Power: +3V3_RADIO through a TPS22975 to HALOW_3V3, controlled by HALOW_PWR_EN. Antenna: MMCX, external. The module's FCC and IC modular certifications apply with the certified antenna (Pulse W1063, 1.0 dBi, 902 to 928 MHz) or one with the same specification; other antennas need a check with a test lab.

M.2 pinout, from the Gateworks GW16167 and GW16170 wiki page (checked September 30, 2026): pins 2, 4, 72, and 74 carry 3.3 V; pin 3 is USB D+ and pin 5 is USB D-; pin 56 (W_DISABLE1#) is wired to the module RESET_N with a 200 kOhm pull-up to the card's own 3.3 V rail; pin 54 (W_DISABLE2#) is wired to the module WAKE with a 10 kOhm pull-up to the same rail. The card does not enumerate on USB while either pin is held low. The wiki lists no PCIe, PERST#, CLKREQ#, or PEWAKE# signals for this card, so V1 leaves those M.2 pins unconnected unless Gateworks documents otherwise.

Control pin drive: the pull-ups return to the card's switched rail, so the CM5 GPIOs wired to pins 54 and 56 (GPIO 18 and 19 in section 16) must be driven open-drain: output low to assert, input to release, never driven high. That keeps the GPIO from back-feeding the card while HALOW_3V3 is off. Do not infer HaLow pin behavior from generic Morse Micro documentation or another Gateworks module. The Morse Micro Linux driver does not support two HaLow radios on one host, so the node carries one HaLow radio.

## 8. USB

Selected: two-port USB 2.0 hub, TI TUSB4020BI (480 Mbps, two downstream ports, about -40 to +85 C, about 9 x 9 mm HTQFP, 24 MHz crystal, strap configuration, no special host driver). The CM5 needs exactly two internal USB devices, and a two-port hub gives a simple, deterministic topology.

Topology: CM5 USB2 to the TUSB4020BI; port 1 to the GW16170 (HaLow); port 2 to the AIW-170BQ Bluetooth.

Configuration: strap configuration, no EEPROM, 24 MHz crystal, USB_HUB_RESET_N.

Power: USB VBUS switching is separate from radio 3.3 V switching, and the TPS22975 devices stay dedicated to radio 3.3 V. Dedicated USB VBUS switches are not yet selected. Fault signals: HALOW_USB_FAULT_N and BT_USB_FAULT_N.

Open: exact USB VBUS load switches, internal USB ESD, and exact hub strap configuration.

## 9. GNSS: u-blox MAX-M10S-00B

About 9.7 x 10.1 x 2.5 mm, multi-constellation, UART, I2C, PPS/time pulse, reset, integrated LNA and SAW filter, -40 to +85 C. Primary interfaces are UART, PPS, and reset; I2C is secondary.

Power: +3V3_RADIO, filtered, to +3V3_GNSS. No dedicated GNSS power switch is planned for V1, because independent GNSS power cycling is not currently required.

Antenna: external active antenna; VCC_RF provides the antenna bias.

Placement: a quiet RF corner, away from buck converters, Ethernet magnetics, CM5 high-speed routing, Wi-Fi, and HaLow.

Backup: V_BCKP is reserved; backup storage is not selected. Test pads: SAFEBOOT_N and EXTINT.

RF protection: do not automatically populate a generic TVS on the GNSS RF line. Select protection for the 1.575 GHz path with its capacitance and insertion-loss limits.

## 10. Ethernet: sealed Gigabit connector

Decision (B-06, D-022): the Ethernet port is the Amphenol LTW RCP-5SPFFH-SCU7001 sealed panel feed-through (IP67 with the port open or mated, shielded Cat5e, 13/16"-28 UNS thread, panel cut-out 20.8 mm with a 19.4 mm flat). A CAP-WACMSPC1 screw cap on a rubber strap covers the port when unused. The M12 X-coded option and the Glenair Series 80 Mighty Mouse candidate are retired (R-04), as are the Cat6A RCP-6APFFH-SCM7001 (R-15) and the Bel 1840888-4 as the wall connector (R-16). The feed-through ends in an RJ45 socket inside the wall, so the carrier needs a board-side RJ45 and a short internal patch cable. Not yet chosen: the board-side jack, the magnetics, the ESD and surge device, and the internal cable. The maker's drawings and 3D model are in the project files under v1-cad/step/.

Consequences: the feed-through has no magnetics. The board carries them, either as a discrete four-channel 1000BASE-T module or inside the board-side jack, plus a low-capacitance ESD and surge device. The CM5 already includes the BCM54210PE Gigabit PHY, so the design routes four 100 ohm differential MDI pairs from the CM5 through the magnetics to the connector, and no external PHY is used. The connector is sealed to the enclosure wall, and the shield follows the chassis rule below. Whether the connector offers any protection against shorting when submerged has not been reviewed. Magnetics part and board-side jack: not yet selected.

Not selected: an external PHY (duplicates CM5 function and adds power, area, cost, and complexity), PoE (not required, adds power-path and thermal complexity), and Ethernet LEDs (status belongs in software and the EUD).

ESD: a low-capacitance Gigabit Ethernet ESD device is required near the Ethernet connector. The part is open.

Chassis: CHASSIS_GND is reserved. Do not connect the Ethernet connector shield directly to digital ground without a deliberate strategy.

Timing: the CM5 PHY supports IEEE 1588-2008 and exposes a 3.3 V SYNC_OUT. ETH_SYNC_OUT is reserved to a CM5 GPIO or test point and is not hard-wired to GNSS PPS.

## 11. Battery pack and charging

Decision (B-11 to B-13, D-007, D-013, [v1-battery-pack.md](v1-battery-pack.md)): the project designs its own removable, sealed 3S2P 18650 pack (six Molicel INR-18650-M35A cells, 10.8 V nominal, 9 to 12.6 V in use, about 76 Wh). The pack mounts on the bottom of the radio with the radio's enclosure footprint (about 124 x 74 mm, D-016) and about 46 mm height, and capacity growth adds height only. It stays under 100 Wh, the air-transport threshold. The battery-to-radio interface is eight Mill-Max 7911 spring-loaded contacts on a replaceable radio-side daughterboard, landing on hard-gold pads on the pack, with a Southco C3 latch. The mechanical values are in master parameters M-01 to M-21, and this document does not repeat them.

Pack requirements retained from earlier analysis: use energy-type cells rated for at least 8 A continuous, since each cell sees only about 2 A at the 35 W peak. The pack carries a protection board (overcharge, over-discharge, overcurrent, short circuit) with a low-voltage cutoff of about 2.8 to 3.0 V per cell, which keeps the pack cutoff above the 7.43 V eFuse falling threshold. Its overcurrent trip must sit above 6 A and tolerate the 11 A, 25 ms eFuse pulse. The eFuse limit governs the current budget (D-019). Charging is in the radio, so the pack holds only the cells, the protection and balancing board, a temperature sensor, and a pack ID. Keep the cells away from the radio's warm aluminum shell with an insulating gap, since Li-ion charging should stay within about 0 to 45 C. A 3S1P pack and 21700 cells were considered and not chosen. CR123 cells were rejected: poor high-current behavior and not rechargeable.

Charging and power path (direction, to be verified; see D-009, D-010, B-08, B-09): one sealed USB-C DATA / CHARGE port (GCT USB4720-03-A) charges the installed pack while the radio runs and also carries USB 2.0 console and service data. The radio uses a TI TPS25751A PD controller and a TI BQ25798 1 to 4 cell buck-boost charger with a narrow-VDC power path. The TI USB-PD-CHG-EVM-01 is the reference starting point. The earlier charge figures came from the BQ25792 (about 5 A charge current, input up to 24 V, 3.3 A input current limit), so confirm the BQ25798 figures on its datasheet. A 45 W supply (15 V, 3 A) charges at about 2.5 A, roughly 3 to 3.5 hours from empty, while the radio runs; a 30 W supply charges more slowly. In this arrangement the charger output feeds the power tree, so the TVS, blocking FET, and Q2 described in section 12 move to the USB-C input or are dropped, and the eFuse sits between the charger system output and the bucks. This changes the power path and needs a review before schematic work ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)): the charger's battery FET current against the 4 A peak, the system voltage window, and integration with the hot-swap bridge ([GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38)).

Still to verify: the hot-swap bridge ([GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38)), the pack protection FETs, current sense, and thermistors ([GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8)), and the exact pack mechanical values (CAD review gates in [v1-battery-pack.md](v1-battery-pack.md)). Retired: the Mil-Con MC327-5 connector, the flat single-row 120 x 72 x 22 mm pack, the M12 A-coded charge port, and the L3Harris 8 to 28 V battery assumption (R-01 to R-03, D-006, D-009, D-013).

## 12. Power protection and telemetry

### Current shunt: Vishay WFK0612R0100FE66

10 mOhm, 1 percent, 1 W, four-terminal Kelvin. At 5 A the drop is 50 mV and dissipation 0.25 W; at 6 A the drop is 60 mV and dissipation 0.36 W. Kelvin sense traces are short, symmetric, direct to the INA228, and isolated from high-current switching paths. Final thermal derating still needs verification. Placement: the INA228 inputs are rated for a common-mode range of -0.3 V to 85 V, so a reversed battery would damage the INA228 if the shunt sat ahead of the blocking FET. Put the shunt after the eFuse output, so it sees only the protected bus. At the 5.56 A current limit the drop is 55.6 mV and the dissipation 0.31 W.

### Battery monitor: TI INA228AIDGSR

High-voltage bus measurement, 20-bit measurement, current, voltage, power, energy, charge, I2C, alert, and die temperature. It gives much richer telemetry than a simple ADC and current-sense implementation. Place it close to the shunt. Software telemetry: battery voltage, current, power, charge and energy, monitor temperature, and alert/fault state. Configuration: use the +/-163.84 mV shunt range, which covers 16.4 A with the 10 mOhm shunt; the +/-40.96 mV range would clip at 4.1 A. Resolution is about 31 µA per LSB of shunt voltage. Starting calibration: CURRENT_LSB of 25 µA and SHUNT_CAL of about 3277 (13107.2 x 10^6 x CURRENT_LSB x R_SHUNT), to be checked against the INA228 datasheet. Power the INA228 from the CM5 3.3 V rail so its I2C levels match the CM5, and route ALERT to GPIO 20.

### Input eFuse: TI TPS26633RGER

4.5 to 60 V, 6 A class, 31 mOhm internal FET, reverse-current blocking and reverse-polarity support through an external N-channel FET, UVLO, soft start, PGOOD, FLT, IMON, and thermal protection. It creates one controlled battery-input protection point. The TPS26633 is the variant with a fixed overvoltage clamp, adjustable output power limiting, and 2 x pulse overcurrent support (orderable as TPS26633RGER, 4 x 4 mm VQFN). The values below come from the TPS2663 datasheet (SLVSE94G, June 2024).

With charging moved into the radio (section 11), where the battery-side protection in this section sits is under review; the calculated values below stay valid for whichever input the eFuse ends up on.

Corrections to the earlier targets: the TPS26633 has no adjustable overvoltage cutoff. It clamps its output at a fixed 32.8 V typical (32 to 35 V) and turns off after 162 ms in the clamp, so the earlier OVLO target of about 30 to 31 V cannot be set. With a battery of 12.6 V maximum and an input target of 28 V, the clamp is not reached in normal use. The power limit target of about 40 W is also below the adjustable range: the PLIM resistor sets 1 W per kOhm and the recommended range starts at 60.4 kOhm.

Current limit: I_OL = 18 / R_ILIM (kOhm). R_ILIM = 3.24 kOhm gives 5.56 A (5.17 to 5.94 A over the 7 percent tolerance), a 2 x I_OL pulse of 11.1 A for 25.5 ms, and a fast-trip threshold of 16.7 A. The 3S 18650 pack peaks at about 4 A at 35 W and 9 V, so the 5.56 A limit stays. If a lower limit is wanted, R_ILIM = 4.53 kOhm gives 3.97 A and 4.02 kOhm gives 4.48 A. R_ILIM must not go below 3 kOhm (6 A).

Power limit: R_PLIM = 60.4 kOhm (60.4 W, the lowest recommended value). With the current limit at 5.56 A this takes effect only above about 10.9 V input, where it lowers the current limit (4.8 A at 12.6 V). It does not limit power at the 8 V low end (44.5 W at 5.56 A).

Undervoltage lockout: a divider from IN_SYS to UVLO to GND with R_top = 464 kOhm and R_bottom = 82.5 kOhm gives 7.95 V rising and 7.43 V falling (UVLO thresholds of 1.2 V and 1.122 V), or about 7.7 to 8.3 V rising across tolerances. R_top must be at least 300 kOhm because the blocking FET is used. Leave SHDN open.

Output ramp: C_dVdT = 22 nF gives t = 20.8 x 10^3 x V_IN x C_dVdT = 5.8 ms at 12.6 V (2,185 V/s), so charging about 25 µF of regulator input capacitance draws about 55 mA. The turn-on delay after UVLO is 742 µs + 49.5 µs per nF x 22 nF, about 1.8 ms.

PGOOD and PGTH: a divider from OUT to PGTH, 243 kOhm over 49.9 kOhm, sets PGOOD rising at 7.04 V and falling at 6.59 V. PGOOD is open drain; pull it up to the eFuse output through 100 kOhm and use it to drive the EN pins of both LM76005 regulators, so they start only after the eFuse ramp completes.

Fault response: tie MODE to ground for auto-retry (retry delay about 670 ms), which suits a headless node. MODE open would latch off until SHDN, UVLO, or the input is cycled. Leave IMON unconnected, because the INA228 measures current (if used: 27.9 µA per A, and R_IMON must stay under 12.9 kOhm to keep 2 x I_OL below 4 V).

Losses: at 4.4 A the eFuse dissipates about 0.9 W (45 mOhm at 85 C) and at the 5.56 A limit about 1.4 W, in addition to the blocking FET and shunt.

### Reverse polarity: TI CSD19533Q5A (candidate)

100 V N-MOSFET, about 5 x 6 mm class, used as the external blocking FET (Q1) of the TPS26633. Topology from the datasheet: Q1 source to IN_SYS (battery side), drain to IN, gate to B_GATE, so Q1 and the internal FET form a back-to-back pair. B_GATE drives 10.2 V typical (8.3 to 14 V); check that against the CSD19533Q5A gate rating. The differential across Q1 can reach the reverse surge clamp plus the output voltage, about 66 V here, so a 100 V part satisfies the datasheet's 80 V guidance.

A small signal FET (Q2) is also required from B_GATE to IN_SYS, driven by DRV, as the fast pulldown. It needs at least 15 V VDS, 20 V VGS maximum, Ciss of 50 pF or less, and a minimum VGS threshold of 3 V or lower. The datasheet example uses a BSS138, which is the Q2 candidate. Still to verify: the CSD19533Q5A RDS(on) at 10 V gate drive, reverse-current behavior, and availability.

### TVS: Diodes Inc. SMBJ33CA (initial candidate)

33 V standoff, about 36.7 to 42.2 V breakdown, about 53.3 V maximum clamp, 600 W, bidirectional. It replaces the earlier SMBJ30A candidate. The unidirectional version of this part cannot sit on the battery side of the blocking FET: a reversed battery would forward-bias it and short the battery through the diode. The bidirectional CA type stays off in both polarities, and the TPS26633 example circuit uses a bidirectional TVS for the same reason. Its 36.7 V minimum breakdown is above the eFuse's 35 V maximum clamp, so it does not conduct while the eFuse clamps. Place it at the connector, ahead of Q1. A 53.3 V clamp is below the TPS26633 60 V operating limit, and a negative surge stresses Q1 with about 66 V (53.3 V plus 12.6 V). Validate it against the actual battery, the cable and transient environment, the reverse-protection topology, and pulse duration.

## 13. Regulators, radio switches, and supervisor

### 5 V buck: TI LM76005

5.0 V, about 2 A initial allocation (about 10 W), synchronous buck, 3.5 to 60 V input, 5 A class capability retained for margin and transients. Calculated starting values, from the LM76005 datasheet (SNVSBK5A) and an 8 to 33 V input range:

Output setting: V_FB is 1.006 V typical (0.987 to 1.017 V). R_FBT = 100 kOhm and R_FBB = 24.9 kOhm give 5.05 V (4.95 to 5.10 V across the reference tolerance). Use 1 percent resistors of 100 ppm/C or better.

Switching frequency: 400 kHz, with the RT pin left open (the default; 99.6 kOhm gives the same nominal value). Start with forced PWM (SYNC/MODE high) so the frequency stays fixed over load, which keeps the switching spectrum predictable next to the GNSS receiver. Check efficiency at the 10 W typical load before keeping it.

Inductor: 6.8 µH. Ripple is 1.1 A peak to peak at 12.6 V and 1.6 A at 33 V, which is 22 to 31 percent of 5 A. The saturation current must exceed the high-side current limit of 6.0 to 7.8 A, so select 8 A or higher (the earlier 6 A figure is too low), with low DCR and a shielded body.

Input capacitors: 2 x 4.7 µF 100 V X7R plus 47 nF at PVIN, as in the datasheet example. Input ripple is about 0.15 V at 2 A and 12 V with 8 µF effective. Add 47 to 100 µF of bulk capacitance on the eFuse output.

Output capacitors: start with 3 x 47 µF 10 V X7R, as in the datasheet example, and confirm loop stability and the CM5 load step on the bench (the datasheet table lists 180 µF at 400 kHz). Add a 47 pF C0G feedforward capacitor across R_FBT.

Other pins: BIAS to +5V_SYS, 470 nF boot capacitor, 2.2 µF VCC capacitor, SS/TRK open for the 6.3 ms internal soft start, and EN driven from the eFuse PGOOD.

### 3.3 V buck: TI LM76005

3.3 V, about 4 A initial allocation (about 13.2 W), 400 kHz. Output setting: R_FBT = 100 kOhm and R_FBB = 44.2 kOhm give 3.28 V (3.22 to 3.32 V across the reference tolerance). The datasheet table value of 43.5 kOhm is not a standard 1 percent value, and 43.2 kOhm would give 3.34 V (up to 3.37 V), which is above the 3.0 to 3.3 V supply range Advantech lists for the AIW-170BQ. Confirm the AIW-170BQ and GW16170 supply limits, and use 0.1 percent resistors if the margin is tight.

Inductor: 4.7 µH, with ripple of 1.3 A peak to peak at 12.6 V and 1.6 A at 33 V, and a saturation current of 8 A or higher. Output capacitors: start with 3 x 47 µF (the datasheet table lists 220 µF at 400 kHz), with input capacitors, feedforward capacitor, boot, VCC, and soft-start as for the 5 V buck. BIAS goes to the 3.3 V output and EN to the eFuse PGOOD. If the two regulators ever beat against each other, the SYNC pin can lock them to one clock.

Critical layout rule: do not place the switching regulator or its inductor directly under or adjacent to RF modules.

### Radio load switches: TI TPS22975DSGT x 2

U302 is Wi-Fi and U303 is HaLow. 0.6 to 5.7 V, up to 6 A, about 16 mOhm typical, adjustable rise time, quick output discharge, thermal shutdown, about -40 to +105 C. Independent radio power control supports software recovery and hardware-aware mesh behavior.

### Supervisor and watchdog: TI TPS386000RGPR

Multi-rail supervision plus watchdog. Rails: SVS1 = CM5_3V3, SVS2 = +5V_SYS, SVS3 = +3V3_RADIO, SVS4 = VBAT_PROTECTED. SUPERVISOR_WDI comes from the CM5 and SUPERVISOR_WDO returns to it. Initial timeout is about 1 to 2 seconds, with a faster software heartbeat. The supervisor fault and watchdog output participates in a path that can pull SYS_PMIC_EN (the CM5 PMIC_Enable) low. Startup, release, watchdog timeout, and recovery behavior must be bench-tested before being treated as field-reliable.

## 14. Power budget

Initial design allocation:

- \+5V_SYS: 2 A, about 10 W
- \+3V3_RADIO: 4 A, about 13.2 W
- Combined: about 23.2 W output, about 25.8 W input at 90 percent efficiency
- System capability target: about 35 W, which is about 4.4 A at 8 V
- The input path should support at least about 5 A continuous at low battery voltage; the initial eFuse current limit is about 5.5 A

The 35 W value is a design capability target, not expected consumption. Actual power consumption must be measured on hardware. Track A estimates about 10 W typical and under 15 to 18 W peak, so converter sizing and the thermal path should be revisited after Track A measurements.

An earlier per-load estimate for the 3.3 V rail (HaLow 1.0 A, Wi-Fi 3.0 A, GNSS 0.1 A, misc 0.25 A, total 4.35 A) is above the 4 A allocation. The LM76005 is a 5 A part, so reconcile the allocation once the AIW-170BQ peak power draw is measured. The AIW-170BQ datasheet lists 632 mA average in TX mode and no peak figure. With 632 mA in place of the 3.0 A Wi-Fi figure the total is about 2 A, so the 4 A allocation looks conservative, but keep it until peak draw is measured.

## 15. Fanless thermal strategy

- Aluminum enclosure as heat spreader, with a thermal interface from the CM5 to the enclosure
- Copper thermal areas and thermal vias, with power converters coupled through copper pours and vias to the chassis
- A concentrated power island, kept away from GNSS and RF
- No fan and no switching regulators beneath RF modules

The enclosure is part of the thermal design. At the 35 W capability target, converter heat is about 2.8 W at 92 percent efficiency and about 4.2 W at 88 percent. Other heat sources: CM5, HaLow radio, Wi-Fi radio, Ethernet, and input protection.

## 16. GPIO and control assignment

This is a logical assignment, not a frozen physical CM5 pin assignment. The verified physical pins, alternate-function facts, and known GNSS UART allocation conflict are recorded in [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md). Before schematic freeze, verify every GPIO against the current CM5 datasheet and IO documentation, muxing, boot behavior, and Linux device-tree requirements.

Current logical map:

| GPIO | Signal | Function |
|---|---|---|
| 0 | GNSS_UART_TX | GNSS UART |
| 1 | GNSS_UART_RX | GNSS UART |
| 2 | SYS_I2C_SDA | System I2C |
| 3 | SYS_I2C_SCL | System I2C |
| 4 | HALOW_PWR_EN | HaLow power enable |
| 5 | WIFI_PWR_EN | Wi-Fi power enable |
| 6 | HALOW_FAULT_N | HaLow fault |
| 7 | WIFI_FAULT_N | Wi-Fi fault |
| 8 | GNSS_RESET_N | GNSS reset |
| 9 | GNSS_PPS | GNSS timing |
| 10 | SUPERVISOR_WDI | Watchdog heartbeat |
| 11 | SUPERVISOR_WDO | Watchdog status |
| 12 | POWER_GOOD | Power-good |
| 13 | EFUSE_FAULT | eFuse fault |
| 14 | USB_HUB_RESET_N | USB hub reset |
| 15 | HALOW_USB_FAULT_N | HaLow USB fault |
| 16 | BT_USB_FAULT_N | Bluetooth USB fault |
| 17 | ETH_SYNC_OUT | Ethernet timing |
| 18 | HALOW_RESET_N | HaLow reset (M.2 pin 56), open-drain |
| 19 | HALOW_WAKE_N | HaLow wake (M.2 pin 54), open-drain, optional |
| 20 | INA228_ALERT_N | Battery monitor alert |
| 21 | WIFI_WDIS1_N | Wi-Fi RF disable (provisional) |
| 22 | WIFI_WDIS2_N | Bluetooth disable (provisional) |
| 23 to 27 | Reserved | Future expansion |

Dedicated signals: SYS_PMIC_EN (CM5 PMIC enable), TP_PWR_BUTTON (internal test pad), and TP_NBOOT (internal test pad). GPIO 18 and 19 must be driven open-drain (output low to assert, input to release) because the GW16170 pull-ups return to its switched 3.3 V rail. All CM5 GPIO run at 3.3 V with GPIO_VREF tied to 3.3 V. GPIO 21 and 22 are provisional until the AIW-170BQ pin table is available.

## 17. Schematic sheets

- 01_CM5: CM5, two Amphenol connectors, +5V_CM5, GPIO_VREF, PCIe, USB2, Ethernet, UART, I2C, PPS, PMIC_Enable, internal test pads
- 02_PCIE_WIFI: AIW-170BQ, M.2 E-key socket, PCIe Gen2 x1, 100 MHz REFCLK, PERST#, CLKREQ#, 220 nF AIW TX capacitors, Wi-Fi TPS22975, two MHF4
- 03_USB_HALOW: TUSB4020BI, 24 MHz crystal, CM5 USB2 upstream, GW16170, AIW Bluetooth, hub reset, USB fault signals, USB VBUS switches, USB ESD
- 04_ETHERNET: CM5 PHY interface, discrete 1000BASE-T magnetics, sealed Ethernet connector, four MDI differential pairs, Ethernet ESD, chassis and shield, ETH_SYNC_OUT
- 05_GNSS: MAX-M10S-00B, UART, I2C, PPS, reset, VCC_RF, active antenna, optional RF protection and filter footprints, backup provision, test pads
- 06_POWER: battery contacts, 10 mOhm shunt, INA228, SMBJ33CA, CSD19533Q5A, Q2 pulldown FET, TPS26633, LM76005 5 V, LM76005 3.3 V, TPS22975 x 2, GNSS filtering, protection, fault, and telemetry
- 07_SYSTEM: GPIO assignment, supervisor, watchdog, PMIC_Enable recovery, radio power and fault, GNSS reset and PPS, USB hub reset and fault, Ethernet timing, reserved GPIO

## 18. Mechanical architecture

PCB: 117 x 67 mm working target. Enclosure concept: rectangular aluminum, about 2.0 mm wall and about 1.5 mm internal component-to-wall clearance (both assumptions), fanless, four M3 mounting points, external RF connectors, external Ethernet connector, and an external battery connector. The enclosure is not frozen.

### Placement rules

- CM5: central and upper anchor. Working envelope X about 31 to 86 mm, Y about 24 to 64 mm. Approximate hole references for that placement: (34.5, 27.5), (82.5, 27.5), (34.5, 60.5), (82.5, 60.5). These are not frozen.
- HaLow: upper left RF region, MMCX toward the RF enclosure wall
- Wi-Fi: upper right RF region, MHF4 connectors toward the RF enclosure wall
- GNSS: quiet lower left region
- Power: lower and middle, about a 45 x 25 mm working region
- USB hub: lower central area or bottom side
- Ethernet: left board edge for the magnetics, with the connector receptacle in the enclosure wall
- Battery: lower left board edge; the exact position is blocked by the pack and connector design. The pack mounts on the bottom of the radio ([v1-battery-pack.md](v1-battery-pack.md)), so the contacts sit on the back face
- No power inductors under RF modules

First-pass 2D floorplan (September 30, 2026, nominal part sizes, board origin at lower left, X right, Y up, all in mm): CM5 X 31 to 86, Y 24 to 64. HaLow M.2 X 4 to 26, Y 34 to 64 and Wi-Fi M.2 X 91 to 113, Y 34 to 64, both rotated so the socket end faces the CM5 side and the antenna end faces the top wall. Ethernet connector receptacle keepout X 1 to 21, Y 4 to 24 on the left edge, with the magnetics module at X 23 to 37, Y 12 to 21. Power-input termination X 26 to 38, Y 0.5 to 8.5 on the bottom edge (placeholder, behind the power receptacle in the bottom wall). USB hub X 39 to 53, Y 10 to 24. GNSS X 96 to 112, Y 5 to 19, in the corner farthest from the HaLow module. Bottom side: 5 V and 3.3 V bucks X 30 to 66, Y 3 to 17; charger with PD controller X 38 to 60, Y 26 to 42 and eFuse block X 62 to 80, Y 26 to 36, both under the CM5; shunt with INA228 X 70 to 82, Y 3 to 11; supervisor X 70 to 79, Y 13 to 22; one radio load switch beside each radio.

Result: no overlaps on either side, with 55 percent of the top side and 16 percent of the bottom side occupied, so the 117 x 67 mm target holds at this level of detail. Rules checked in the script: no switching part sits over or under an RF module on either side, and every power part is at least 15 mm from the GNSS receiver. Centre distances to the GNSS receiver: HaLow about 96 mm, Wi-Fi about 37 mm, 3.3 V buck about 47 mm, Ethernet connector about 92 mm. The Wi-Fi distance is the one to review against the coexistence results.

Limits of this check: sizes are nominal, not manufacturer drawings. The Ethernet connector keepout (20 x 20 mm) and the magnetics module (14 x 9 mm) are placeholders. They are too small for the D-022 feed-through, which with its plug and cable bend needs about 42 mm of depth and 25 mm of height (GHO-7). With the standard jack gone, top-side occupancy is 58 percent and the checks above still pass. The antenna connector position on each M.2 card is assumed to be the end opposite the socket, which is unverified for the GW16170. Estimated stack height: the earlier figure of about 27 mm for the radio body (the pack now adds about 46 mm, master M-02) assumed a 13.4 mm standard jack and is now an upper bound. The tallest top-side part is likely the CM5 on its connectors (about 7.4 mm connector stack plus the module, unverified), and the 3D assembly must recompute it. This does not replace the STEP-based 3D collision check.

The floorplan is conceptual only: HaLow module upper left, CM5 center, Wi-Fi module right of center, GNSS lower left, power and DC section lower middle, USB hub lower center, Ethernet connector lower left, battery contacts on the lower left edge. Actual placement must use manufacturer STEP models.

### Mechanical CAD blockers

Before freezing mechanical coordinates, obtain and use: the CM5 STEP, the Amphenol 10164227-1004A1RLF model, the GW16170 STEP, the AIW-170BQ STEP, the TE 2199119-6 model, the pack contact and latch models, the Ethernet connector model, the actual MHF4 and MMCX connectors, the GNSS RF connector, the enclosure, and the enclosure boss geometry. Then run a collision check, connector access check, battery insertion and removal check, antenna cable bend-radius check, enclosure-wall clearance check, thermal interface check, and mounting check. Do not freeze the battery contact position from guessed geometry.

### Area check

The CM5 (55 x 40 mm, 2,200 mm2), HaLow M.2 (30 x 22 mm, 660 mm2), and Wi-Fi M.2 (30 x 22 mm, 660 mm2) total about 3,520 mm2, roughly 45 percent of 117 x 67 mm (7,839 mm2). The modules are not the main area problem. The real constraints are RF connector placement, antenna separation, RF keepouts, ground and via fencing, M.2 connector clearances, the Ethernet and battery connectors, power inductors, thermal copper, mounting holes, enclosure walls, high-speed routing, and test access.

## 19. RF architecture

- HaLow: GW16170 to MMCX to external antenna
- Wi-Fi: AIW-170BQ to two MHF4 connectors to external antennas
- GNSS: MAX-M10S to active antenna connector to external antenna
- Rules: short 50 ohm paths, continuous reference plane, appropriate RF ground fencing, no unnecessary vias, no long wandering traces, no buck inductors near RF, GNSS separated from Ethernet magnetics and power switching, RF connectors near the enclosure wall

External RF is used for V1 because it better supports rugged enclosure integration, field antenna selection, and RF performance than PCB antennas.

## 20. Routing priority, stackup, and power layout

Routing priority:

1. PCIe
2. Gigabit Ethernet
3. RF
4. GNSS RF
5. USB 2.0
6. CM5 clocks and high-speed control
7. GNSS UART and PPS
8. I2C
9. GPIO
10. Power enables and supervisor
11. Telemetry
12. Everything else

Stackup: eight layers is the starting assumption. Conceptually: L1 components, critical signals, and RF; L2 solid GND; L3 high-speed signals; L4 GND; L5 power; L6 high-speed and general signals; L7 GND; L8 general, power, and low-speed. This is not a manufacturing stackup. The fabricator stackup must be used to calculate PCIe, Ethernet, USB, and 50 ohm RF geometry, return paths, and thermal copper.

Top and bottom: the top side carries the CM5, M.2 modules, GNSS, Ethernet, and RF connectors. The bottom side can carry converters, the INA228, protection support, load switches, supervisors, small support ICs, and test pads. Do not automatically place switching power underneath RF modules; RF isolation and thermal paths drive the final decision.

Power layout rules: the battery path runs battery contacts, TVS, blocking FET, and eFuse, then the shunt, then VBAT_PROTECTED (the shunt sits after the eFuse so the INA228 never sees reverse polarity). Keep high-current paths short, wide, low resistance, and thermally capable. Keep Kelvin sense traces isolated from switching current. Follow TI reference layouts for buck loops and keep switching nodes small.

## 21. Headless operation and hardware-aware mesh

The node is deliberately headless. There are no power, reset, or mode buttons, and no power, activity, Ethernet, or radio LEDs. Normal operation is EUD and software controlled; hidden test pads and service access are acceptable. The EUD should eventually support radio, mesh, Wi-Fi AP/client, and HaLow configuration; node status; neighbor and client information; GNSS status; battery status; temperature; reboot; shutdown; firmware and software updates; and diagnostics.

Hardware telemetry the carrier must expose: battery voltage, current, and power; energy and charge; power temperature; CM5 and system temperature; radio temperature where available; radio power and fault state; GNSS lock and PPS; Ethernet state and timing; USB fault state; power-good; and eFuse fault.

The hardware-aware mesh metric model is primarily a software task. Per radio: RSSI, SNR, MCS, bitrate, packet loss, retries, airtime, channel, channel width, TX power, radio temperature, interface state, and neighbor information. Per node: GNSS position, time, and PPS, battery voltage, current, and power, CPU and radio temperatures, uptime, and overall health. Link types to distinguish: HaLow, 2.4/5/6 GHz Wi-Fi, and Ethernet. The routing algorithm is intentionally not locked down; the hardware should provide the telemetry needed for multiple routing strategies.

## 22. Hardware recovery

Desired recovery hierarchy:

1. Reset an individual USB device
2. Reset the USB hub
3. Power-cycle an individual radio
4. Hardware supervisor and watchdog
5. CM5 PMIC_Enable recovery

The goal is to recover from common failures without physical user interaction. Independent radio power switching lets software tell apart a radio that is deliberately off, one that failed to start, a radio power fault, a main power fault, low battery, and an input protection trip.

## 23. Software direction

Software concepts: OpenMANET (OpenWrt), BATMAN-V, 802.11s, 2.4/5/6 GHz AP and client operation, HaLow, and multi-interface routing. The CM5 is not assumed to be fully supported by every desired OpenMANET combination. Before hardware is frozen, validate:

1. Linux and OpenMANET on the CM5
2. CM5 PCIe Wi-Fi with the AIW-170BQ ath11k path, including 802.11s mesh point
3. Bluetooth over USB on the CM5
4. GW16170 driver and firmware on the CM5, and USB enumeration
5. Simultaneous radio operation, and PCIe and USB resource availability
6. 802.11s and BATMAN-V behavior, and the EUD management architecture

Still to define: radio power-management software, the hardware telemetry API, hardware-aware mesh metrics, the watchdog service, GNSS PPS handling, Ethernet timing handling, and the fault and recovery state machine.

## 24. Components deliberately not selected

- External Ethernet PHY: the CM5 already contains the Gigabit PHY
- PoE: no requirement, and it would add power, area, and thermal complexity
- Physical buttons: the product is EUD controlled and headless
- User LEDs: software and the EUD are the status interface
- External debug connector: the product stays sealed and headless; internal test pads are sufficient
- PCB antennas: external antennas better support rugged integration, field antenna choice, and RF performance
- Separate GNSS power switch: independent GNSS power cycling is not required; a filtered 3.3 V rail is sufficient for V1
- GNSS PPS hard-wired to Ethernet timing: the two timing interfaces stay independent
- Generic GNSS RF TVS: protection must be selected for the GNSS path
- USB hub EEPROM: strap configuration is sufficient for V1
- Hub with more than two downstream ports: the architecture needs exactly two internal USB devices
- Extra HaLow SDIO or SPI routing: USB is the primary interface and those buses are not required
- Wi-Fi modules based on MT7915 or MT7916: retired for V1 in favor of the AIW-170BQ

## 25. Bill of materials and status

Current V1 parts and their status:

| Function | Part | Status |
|---|---|---|
| Compute | Raspberry Pi CM5008032 | Selected |
| CM5 connector | Amphenol 10164227-1004A1RLF | Selected |
| Wi-Fi 6E | Advantech AIW-170BQ-001 | Selected |
| HaLow | Gateworks GW16170 / MM8108-M20 | Selected |
| GNSS | u-blox MAX-M10S-00B | Selected |
| Ethernet | Amphenol LTW RCP-5SPFFH-SCU7001 sealed feed-through, CAP-WACMSPC1 cap (board-side jack and magnetics TBD) | Selected |
| M.2 socket | TE Connectivity 2199119-6 | Selected (reference) |
| Battery connector | Eight Mill-Max 7911 spring contacts (B-12) | Selected for V0; geometry CAD-verify |
| Shunt | Vishay WFK0612R0100FE66 | Selected |
| Battery monitor | TI INA228AIDGSR | Selected |
| Input eFuse | TI TPS26633RGER | Selected |
| Reverse FET | TI CSD19533Q5A | Candidate |
| Reverse FET pulldown (Q2) | BSS138 or equivalent | Candidate |
| TVS | Diodes Inc. SMBJ33CA | Initial candidate |
| 5 V buck | TI LM76005 | Selected |
| 3.3 V buck | TI LM76005 | Selected |
| Radio switches | TI TPS22975DSGT x 2 | Selected |
| Supervisor / watchdog | TI TPS386000RGPR | Selected |
| USB hub | TI TUSB4020BI | Selected |
| USB VBUS switch | TBD | Open |
| USB ESD | TBD | Open |
| Ethernet ESD | TBD | Open |
| GNSS backup | TBD | Open |
| GNSS RF protection | TBD | Open |
| Enclosure | TBD | Open |

Project status by area:

- Defined: product architecture and schematic architecture. Incomplete: exact schematic values.
- Concept defined: mechanical floorplan. Working target: PCB size 117 x 67 mm.
- Open: exact mechanical coordinates, enclosure, PCB stackup, exact battery SKU, and the TBD parts in the table above
- Not started: CAD collision check, PCB routing, thermal validation, RF validation, CM5 software validation, HaLow CM5/Linux validation, Wi-Fi and Bluetooth validation, production validation

## 26. Critical open items

- Mechanical: import the pack contact and latch models, exact CM5, AIW-170BQ, GW16170, TE M.2 socket, and Ethernet connector CAD; select the actual RF connectors; define enclosure wall thickness and bosses; freeze mounting holes; run 3D collision analysis; verify antenna cable bend radii, Ethernet connector enclosure intrusion, and battery latch and insertion and removal.
- Electrical: verify every CM5 GPIO mux and pin; verify the exact AIW-170BQ M.2 pin assignment and control pins (the GW16170 pins are verified in section 7); check the calculated TPS26633 and LM76005 component values in sections 12 and 13; verify the reverse-FET topology; validate the TVS against the actual battery and transients; finalize the LM76005 components; select USB VBUS switches, USB ESD, and Ethernet ESD; finalize GNSS backup, GNSS RF protection, and the chassis and shield strategy; finalize the supervisor recovery topology; verify PMIC_Enable behavior; verify startup and radio power sequencing; select the USB-C PD controller and charger, and review the power path with charging in the radio (section 11).
- Software: validate CM5 PCIe Wi-Fi and the ath11k path, Bluetooth over USB, the GW16170 on the CM5, and HaLow firmware; define radio power management, the hardware telemetry API, hardware-aware mesh metrics, the watchdog service, GNSS PPS handling, Ethernet timing handling, and the fault and recovery state machine.

## 27. Validation plan

- Power: minimum and maximum input, cold and hot startup, maximum radio load, Ethernet load, USB load, transient load, radio power cycling, short circuit and current limit, reverse battery, overvoltage, undervoltage, thermal shutdown, and recovery behavior
- RF: Wi-Fi at 2.4, 5, and 6 GHz, HaLow at 902 to 928 MHz, GNSS acquisition and sensitivity, coexistence, antenna isolation, enclosure and thermal effects, conducted TX, and receiver sensitivity
- Ethernet: 10/100/1000, negotiation, throughput, sustained traffic, ESD, shield and chassis behavior, and PHY timing
- USB: HaLow and Bluetooth enumeration, hub reset, device reset, fault and recovery, VBUS fault, and simultaneous operation
- GNSS: cold and warm start, multi-constellation, PPS, UART, I2C, active antenna bias, loss and recovery, and backup behavior
- Battery telemetry: compare INA228 voltage, current, power, accumulated charge and energy, and temperature against calibrated equipment

## 28. Design freeze criteria

Do not call the design frozen until all of the following are true:

- Mechanical: all major STEP models are loaded, there are no collisions, and connector access, battery insertion, antenna clearance, and mounting are verified
- Electrical: every external pin is verified, power and protection calculations are complete, regulator components are selected, and watchdog recovery is bench-tested
- RF: the actual stackup is calculated, connectors are placed, and keepouts and RF rules are defined
- Thermal: major dissipation is estimated, the enclosure thermal path is modeled, CM5 cooling is verified, and buck thermal performance is estimated
- Software: Wi-Fi, HaLow, Bluetooth, GNSS, and telemetry are demonstrated

## 29. Next steps and resume point

Resume here: import actual manufacturer STEP models for the CM5, GW16170, AIW-170BQ, TE 2199119-6, pack contact and latch, Ethernet connector, RF connectors, and the intended enclosure and boss geometry. Build the 117 x 67 mm assembly, resolve collisions and enclosure clearances, and produce a final mechanical coordinate table. The next meaningful step is not another architecture brainstorm. A first-pass 2D floorplan with nominal part sizes is recorded in section 18; the STEP-based 3D assembly is still the next step.

1. Mechanical CAD assembly: build a 117 x 67 mm board assembly with the CM5 and its connectors, GW16170, AIW-170BQ, M.2 sockets, battery contacts, Ethernet connector, RF connectors, major power components, TUSB4020BI, enclosure walls, and four M3 bosses, then run collision and clearance analysis. Success means everything fits with enclosure clearance, connector and antenna access, battery insertion and removal, thermal paths, and mounting access, without enlarging the board.
2. Freeze mechanical reference coordinates: PCB outline, mounting holes, CM5, M.2 sockets, Ethernet connector, battery contacts, RF connectors, and the enclosure interface.
3. Finish electrical values: check the calculated TPS26633 and LM76005 values, load-switch settings, watchdog timing, USB VBUS switches, USB ESD, Ethernet ESD, GNSS backup, RF protection, and the chassis strategy.
4. Verify authoritative pinouts: CM5 GPIO, PCIe, and USB; AIW-170BQ M.2 (Advantech pin table still needed); TE socket; the pack contact array. The GW16170 M.2 pinout is verified in section 7. No inferred pinout should reach PCB layout.
5. Select the actual PCB stackup from the fabricator and calculate PCIe, Ethernet, USB, and 50 ohm RF geometry, return paths, and thermal copper.
6. Route using the priority order in section 20, then run DRC and 3D clearance checks, build a prototype, and start bench validation.

## 30. Rules for future agents

1. Do not restart the architecture from scratch.
2. Do not substitute parts casually.
3. Do not guess connector pinouts.
4. Do not guess pack contact, latch, or gasket geometry; use [v1-battery-pack.md](v1-battery-pack.md) and the manufacturer drawings.
5. Do not assume generic M.2 pin behavior applies to the GW16170.
6. The AIW-170BQ design uses Bluetooth over USB, not UART.
7. Do not add an external Ethernet PHY.
8. Do not add PoE unless requirements change.
9. Do not add physical buttons.
10. Do not add user LEDs.
11. Do not enlarge the PCB until CAD proves it necessary.
12. Do not route switching inductors beneath RF modules.
13. Do not blindly populate a GNSS RF TVS.
14. Do not use CM5 nEXTRST as the external reset strategy; use PMIC_Enable for the hardware recovery path.
15. Keep USB VBUS switching separate from radio 3.3 V switching.
16. Use manufacturer STEP models wherever possible.
17. Treat the enclosure as part of the thermal and RF design.
18. Prefer authoritative manufacturer documentation.
19. Verify critical assumptions against the actual selected part revision before freeze.
20. Follow the record-keeping rules in [../README.md](../README.md): one fact, one place.

## 31. Reconciliation with Track A and the project records

This reference supersedes the September 29 Track B reference. The points below were raised by the former master doc and the Track A analysis and are not settled by the V1 handoff. They stay open until a decision is recorded in [../decisions.md](../decisions.md).

- PCB size and enclosure: resolved by D-016. The 117 x 67 mm board is the working target, and the enclosure and pack are about 124 x 74 mm. The goal is to get the whole unit as close to MPU5 size as CAD allows, and the CAD assembly decides how far the board and enclosure can shrink.
- Power budget: 35 W is a capability target, not expected consumption. Track A estimates about 10 W typical and under 15 to 18 W peak. Resize the converters, eFuse limit, and thermal path after Track A measurements.
- Battery range and current: resolved by the pack design. The battery is now a project-designed 3S 18650 pack (section 11), which sets the range at 9 to 12.6 V and the current at the pack's own rating. The earlier reference figures (6 A continuous, and the 4.0 A limit of the 12041-2400-0X pack from Track A) no longer apply. Keep the wide input tolerance only if a vehicle or external supply is wanted.
- GNSS isolation: the handoff places GNSS away from switching power, Ethernet magnetics, CM5 high-speed routing, Wi-Fi, and HaLow. Track A identifies the 28.5 dBm HaLow transmitter as the larger risk, so GNSS placement and RF keepouts should also follow the Track A coexistence results.
- Wi-Fi mesh support: OpenMANET needs an 802.11s mesh point. Mesh-point support on the AIW-170BQ (Qualcomm WCN6856, ath11k) is not yet confirmed. Track A rejected MT7921-class adapters for lacking mesh-point support.
- Changes since September 29: the 2.4/5 GHz Wi-Fi module moved from an MT7915/MT7916-class candidate to the AIW-170BQ (adds 6 GHz); the TVS moved from SMBJ30A to SMBJ33CA; the battery connector moved from TBD to the MC327-5 and later to the eight-contact spring interface (D-013); the supervisor moved from TBD to the TPS386000; and the USB hub (TUSB4020BI) was added.
- Power protection corrections: the TPS26633 has a fixed 32.8 V overvoltage clamp and no adjustable cutoff, its power limit cannot be set below 60 W, the TVS must be bidirectional and sit ahead of the blocking FET, the shunt moves after the eFuse, and the buck inductor saturation rating rises to 8 A. Section 12 has the calculated values.
- Pack size and charging: settled as a 3S2P 18650 pack charged in the radio over USB-C ([v1-selections.md](v1-selections.md), [v1-battery-pack.md](v1-battery-pack.md), D-007, D-009, D-010). Integration of the power path with charging in the radio is still open ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)).

## 32. Reference sources

- [Raspberry Pi Compute Module documentation](https://www.raspberrypi.com/documentation/computers/compute-module.html)
- [Raspberry Pi CM5 datasheet](https://pip-assets.raspberrypi.com/categories/944-raspberry-pi-compute-module-5/documents/RP-008180-DS/cm5-datasheet)
- [Raspberry Pi CM5 IO datasheet](https://datasheets.raspberrypi.com/cm5/cm5io-datasheet.pdf)
- [OpenMANET hardware documentation](https://openmanet.github.io/docs/hardware)
- [OpenMANET networking documentation](https://openmanet.github.io/docs/networking)
- [OpenMANET documentation repository](https://github.com/OpenMANET/docs)
- [Gateworks GW16170 product page](https://www.gateworks.com/products/wireless-options/gw16170-mm8108-m20-802-11ah-halow-wifi-m2-card/)
- [Gateworks GW16167 and GW16170 wiki page (M.2 pinout)](https://trac.gateworks.com/wiki/expansion/gw16167)
- [Advantech AIW-170BQ datasheet](https://advdownload.advantech.com/productfile/PIS/AIW-170BQ/file/AIW-170BQ_DS\(022025\)20250224094249.pdf)
- [Persistent Systems MPU5 specifications](https://persistentsystems.com/mpu5-specs/)
- [TI TPS2663 (TPS26633RGER) product page](https://www.ti.com/product/TPS2663/part-details/TPS26633RGER)
- [TI CSD19533Q5A product page](https://www.ti.com/product/CSD19533Q5A)
- [TI INA228 product page](https://www.ti.com/product/INA228)
- [TI LM76005 product page](https://www.ti.com/product/LM76005)
- [TI LM76005 evaluation module](https://www.ti.com/tool/LM76005QEVM)
- [TI TPS22975 product page](https://www.ti.com/product/TPS22975)
- [u-blox MAX-M10S datasheet](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf)

Manufacturer documentation for the AIW-170BQ (user manual with pin table), TUSB4020BI, TPS386000, Mill-Max 7911 contacts, Ethernet connector, and SMBJ33CA should be added here as it is downloaded and checked.

## 33. Summary

OpenMANET V1 is a compact, rugged, fanless, headless node centered on a Raspberry Pi CM5, with an Advantech AIW-170BQ Wi-Fi 6E module, a Gateworks GW16170 HaLow module, a u-blox MAX-M10S GNSS, integrated CM5 Gigabit Ethernet, a removable custom 3S2P 18650 battery pack (eight spring contacts, D-013), INA228 battery telemetry, a protected input (9 to 12.6 V pack, wider tolerance retained), LM76005-based 5 V and 3.3 V rails, independently switched radios, a TUSB4020BI USB hub, and TPS386000 hardware supervision. The 117 x 67 mm PCB remains the working target. The architecture is defined; the next work is manufacturer-model CAD placement and collision checking, exact power and protection calculations, authoritative pinout verification, PCB stackup selection, then layout and prototype validation. Do not re-architect without a concrete requirement or verification result forcing the change.
