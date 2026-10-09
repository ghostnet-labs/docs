# V1 net-plan blocker proposals (K-3, K-6, K-8, K-9)

**Owner:** [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10), with [GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9) and [GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11) for the parts they own.  
**Status:** Candidate, 2026-10-09. This file proposes circuits for four blockers that the GHO-13 schematic net plan raised (`v1-schematic-netplan.md`, branch `gho13-schematic-netplan`, [PR #67](https://github.com/ghostnet-labs/docs/pull/67), conflicts K-3, K-6, K-8 and K-9). It edits no record, selects no part and assigns no D-number. Each proposal ends with record text the records owner can apply if the project owner accepts it. Until then the owning records win (README rule 6).

## Conventions

The status words follow the net plan.

- **Datasheet:** read from the document in [Sources](#sources), with its revision.
- **Calculated:** derived here from datasheet values. The arithmetic is shown. Nobody has measured it.
- **Proposed:** a value or connection this file suggests, so capture has a starting point.
- **Unverified:** not checked against a primary source or hardware. Every Unverified item is listed in [What is unverified](#what-is-unverified).
- **Owner decision:** only the project owner can settle it. These are collected in [Decisions for the project owner](#decisions-for-the-project-owner).

GPIO numbers are not restated here. Signals use the canonical ledger's names ([v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md)), and any new signal is named once and marked Proposed.

## Summary

| Blocker | Proposal in one line | New parts (all candidate) |
|---|---|---|
| K-3 B-07 service data | Move the TUSB4041I upstream to the USB 2.0 pair of one CM5 USB 3.0 port. B-07 D+/D- then go straight to the CM5's only device-capable USB 2.0 port (pins 103/105), as on the CM5 IO board. No switch is needed and there is no mode to select. rpiboot is entered from software, from a BOOT_ORDER fallback, or by grounding nRPIBOOT inside the enclosure. A 2:1 switch (TS3USB221A) is documented as the fallback. | None for option A. The fallback adds a TS3USB221A. A DRV5032FC Hall switch is optional and needs an owner decision. |
| K-6 Supervisor | Keep §13's rail assignment, but change what the outputs drive and where VDD comes from. VDD comes from +3V3_RADIO, because WDI and MR need 0.7 x VDD, which a 3.3 V GPIO cannot reach when VDD is 5 V. RESET2 (+5V_SYS) and RESET4 (input bus) gate SYS_PMIC_EN. RESET1 no longer touches PMIC_Enable; it becomes the watchdog arm, through MR from a CM5 arm signal. WDO forces RESET4, so every watchdog trip gives a PMIC_Enable low pulse of at least 225 ms. | No new IC. Only resistors, and one GPIO row that GHO-9 must allocate. |
| K-8 GNSS PPS and safeboot | Buffer TIMEPULSE through an Ioff-rated single gate powered from CM5_3V3 (SN74LVC1G34). The module pin then sees only its own pull-up at start-up, whatever state the CM5 is in. | SN74LVC1G34DCKR |
| K-9 Hub 1.1 V | HUB_1V1 comes from a TLV62568 1 A buck that runs from CM5_3V3 and is set to 1.10 V. It is sized for the hub's 370 mA global-reset current, not the 98 mA active figure. GRSTz is held low by a 2.2 kΩ pull-down until firmware releases it. | TLV62568DBVR, 2.2 µH inductor |

---

## K-3. B-07 service data path, rpiboot and debug console

### Problem (net plan K-3)

D-009 and B-07 say the sealed USB-C DATA / CHARGE port carries CM5 console and service data. The CM5 has one USB 2.0 port that can act as a device: pins 103/105, with USB_OTG_ID on pin 101. The records give that port to the TUSB4041I upstream link, and a hub upstream needs the CM5 to be the host. So B-07 has no data endpoint, rpiboot (which needs that port in device mode) cannot be reached, and the CM5 debug UART exists only on the module's own test points TP35/TP36 (CM5 datasheet Table 13).

### What the CM5 offers (Datasheet)

- The CM5 has a third USB 2.0 high-speed host path that the records do not use. Each of its two USB 3.0 ports carries its own USB 2.0 pair: USB3-0-DP/DM on pins 134/136 and USB3-1-DP/DM on pins 163/165 (CM5 datasheet, Release 3, Table 4 and Table 14, where they are marked "USB 2.0 signal"). The net plan currently marks these pins No connect.
- The dedicated USB 2.0 port (pins 103/105) is the port that the boot ROM's USB device boot uses. nRPI_BOOT means "hold low during boot to bypass eMMC and boot through USB 2.0 instead" (§2.12.2, Table 3). The pin must be low within 2 ms after the 5 V rail rises (§3.1). It has an internal 10 kΩ pull-up to CM5_3.3V (Table 4).
- USB_OTG_ID is internally pulled up, and grounding it makes the CM5 a host (Table 4). The datasheet calls OTG/device use "not officially documented" (§2.4.2 note).
- The Raspberry Pi CM5 IO board uses exactly this split. Its two USB 3.0 Type-A ports are for peripherals, and its USB 2.0 Type-C port is "primarily intended for data transfer and enabling board updates through rpiboot" (CM5IO datasheet §1.3 and §3.4). The eMMC flashing guide connects the host to that Type-C port with the nRPI_BOOT jumper fitted.

### Proposal: option A, re-home the hub (recommended)

| Item | Net plan today | Proposed |
|---|---|---|
| Hub upstream (USB_UP_DP / USB_UP_DM) | CM5 pins 105 / 103 | CM5 USB3-0-DP / USB3-0-DM, pins 134 / 136 (or USB3-1, pins 163 / 165, whichever the floorplan favours; GHO-7/GHO-14). The two USB 2.0 pairs may not be P/N swapped (§2.4) |
| USB 3.0 SuperSpeed pairs of that port (RX, TX) | No connect | Still no connect |
| VBUS_EN (pin 111) | No connect | Still no connect. The hub's VBUS detect comes from its own divider (open item 11 in the net plan, unchanged) |
| B-07 data (SVC_DP / SVC_DM) | No CM5 endpoint | B-07 A6/B6 and A7/B7 are tied at the receptacle, then go through the USB ESD array (GHO-11, O-3) and a 90 Ω differential pair, matched within 0.15 mm (§2.4.2), point to point to CM5 USB_P / USB_N, pins 105 / 103. Proposed: a DNP common-mode-choke footprint, only if EMC needs it; no other stubs or test pads on the pair |
| USB_OTG_ID (pin 101) | Open | No connect: the internal pull-up selects the device role. Add a DNP 0 Ω to GND as a host-role fallback |
| nRPIBOOT (pin 93) | TP_NBOOT | TP_NBOOT (Record), plus the optional sealed service input below |
| TPS25751A GPIO4/USB_P, GPIO5/USB_N (B-08) | Not given | Not connected to SVC_DP/DM. These pins are for BC1.2 detection (TPS25751 datasheet pin table). PD replaces BC1.2 here, and a second tap would add a stub and a drive source on the HS pair |
| BQ25798 D+/D- (B-09) | Not given | Same rule. Proposed: DNP 0 Ω links to SVC_DP/DM, disabled in firmware. **Unverified:** the BQ25798 datasheet was not fetched for this file |
| TPS25751A data role | Not given | B-07 is a sink. The PD controller should be configured to report the UFP data role and reject DR_Swap, so a PC is always the USB host. **Unverified** against the TPS25751A configuration tool (GHO-10) |

Firmware (GHO-19): the 103/105 port runs `dtoverlay=dwc2,dr_mode=peripheral` with a composite gadget (CDC-ACM console plus CDC-NCM or CDC-ECM network). The hub, HaLow and OpenVLM move to the RP1 xHCI controller, which the OpenWrt CM5 target must include. **Unverified:** neither the gadget on OpenWrt CM5 nor the hub on an RP1 port has been run by this project.

**Why A over a switch.** Option A puts no part in either 480 Mb/s path, needs no select logic and no default state, and cannot drop HaLow and the OpenVLM when a charger is plugged into B-07. That last point matters because the product charges while it runs (D-007, B-09). It keeps D-023's separation: the OpenVLM port still shares no net with B-07. A likely side benefit, not evaluated here: HaLow and the USB audio device run on xHCI instead of the dwc2 controller.

### Service-mode selection without buttons (option A)

Option A needs no data-path selection. B-07 is always the CM5 device port. The only selection left is whether the boot ROM or bootloader enters rpiboot instead of booting the eMMC. Three mechanisms are proposed, in order of preference:

| # | Mechanism | Covers | Evidence |
|---|---|---|---|
| 1 | Software request: from the running OS, `set_reboot_order` / `vcmailbox 0x0003808b` with BOOT_ORDER `0x3` (RPIBOOT), then `reboot`. The next boot waits in USB device boot on the 103/105 port. The setting is one-shot, so the boot after that is normal | Reflash or provision an eMMC that still boots. Can be offered from the EUD UI | Raspberry Pi bootloader docs (`set_reboot_order`, "Raspberry Pi 5 only"; RPIBOOT boot mode "from the USB OTG port", no timeout). **Unverified on CM5** (same BCM2712 as the Pi 5) |
| 2 | BOOT_ORDER fallback: put RPIBOOT last, for example `0x31` (eMMC, then RPIBOOT) | eMMC that no longer boots, when the bootloader EEPROM is intact | The docs say to use RPIBOOT only as the last entry, because it never times out. A node with a transient eMMC failure would then wait for a USB host with no retry. **Owner decision** against the default `0xf1`-style retry loop |
| 3 | Hardware nRPIBOOT low at power-up | Corrupt bootloader EEPROM, which is the only case 1 and 2 cannot reach | Datasheet §3.1 and Table 3 |

For #3, the records already have TP_NBOOT, an internal pad that a technician grounds with the enclosure open. The sealed alternative is a Hall-effect switch behind a marked spot on the wall: a TI DRV5032FC (omnipolar, open-drain output, 20 Hz sampling, SOT-23, VCC 1.65 to 5.5 V, [SLVSDC7H](https://www.ti.com/lit/ds/symlink/drv5032.pdf)). It is powered from +3V3_RADIO, and its open-drain output goes onto the nRPIBOOT net. Holding a magnet there while the CM5 powers up selects rpiboot. It has no opening, no moving part and no visible control. The open-drain output only ever pulls low, so it cannot back-feed the CM5 when the CM5 is off (net plan K-7). Whether a magnet-actuated service input breaks "no physical buttons" (§30 rule 9) is an **owner decision**. The default proposal is TP_NBOOT only, with a DNP DRV5032FC footprint.

A power cycle with nRPIBOOT held low is needed for #3. With the K-6 proposal, a long press then a short press on TP_PWR_BUTTON is the bench route: more than 5 s forces a shutdown (Table 3). Whether a PWR_BUTTON power-on re-samples nRPIBOOT is **Unverified**. Pulling the pack does not cycle power while the B-24 bridge holds the bus up.

### Debug console: test pads, not B-07 SBU

Recommendation: do not put a UART on the B-07 SBU pins.

- SBU is reserved for USB-C alternate-mode and accessory sideband use. A 3.3 V UART on SBU, with no Debug Accessory Mode handshake, can fight with any host or dock that drives SBU.
- It would put an RP1 GPIO on a field-facing connector. That is a direct ESD and overvoltage path to the SoC, and a back-feed path into an unpowered CM5 (K-7).
- B-07 is a USB 2.0 part. Whether the GCT USB4720-03-A even has SBU contacts was not checked (**Unverified**).
- It would need a custom cable. The CDC-ACM gadget gives the same console over standard D+/D-.

Console paths instead:

1. Normal console: the CDC-ACM gadget on B-07 (above), external and sealed.
2. Recovery console: Raspberry Pi's `mass-storage-gadget` rpiboot image, which "also provides a debug console as a serial port gadget" (Raspberry Pi CM flashing docs).
3. Bench only: internal test pads TP_CON_TX / TP_CON_RX (Proposed) on a spare RP1 UART, if GHO-9 allocates one. The ledger's Reserved rows include pins whose alternate functions offer a UART (CM5 datasheet Table 1). That choice is GHO-9's.

Firmware and bootloader messages (BOOT_UART) go to the primary UART, which on the CM5 is the module's debug UART on TP35/TP36. Those messages stay reachable only with the module on a bench carrier or CM5 IO board. The carrier cannot route TP35/TP36.

### Signal integrity (option A)

- B-07 to CM5: one connector, one ESD array and one 90 Ω pair. ESD capacitance is the only added load, so pick the array for low capacitance (GHO-11). The route length from the wall to pins 103/105 depends on the floorplan and needs a limit from GHO-14/GHO-15. Tie the receptacle's duplicated D+/D- pins at the pads, so the stubs are a few millimetres at most.
- Hub upstream: unchanged in kind (CM5 pair to hub, 90 Ω, matched within 0.15 mm), but the pins move to the high-speed connector region (pins 134/136 or 163/165), which changes the route. GHO-14 re-plans it.

### Default state and failure modes (option A)

| Condition | Behaviour |
|---|---|
| Normal boot, nothing on B-07 | nRPIBOOT high: eMMC boot. The hub and radios run from the RP1 port. The gadget is idle |
| PC on B-07, OS up | The PC sees a composite console and network device. Charging runs in parallel through the PD path |
| Charger (no data) on B-07 | No effect on data. The hub and radios are unaffected |
| CM5 off, PC on B-07 | The host sees no device. The host does not drive D+/D- before attach, so nothing is injected into the CM5 |
| OS hung or gadget not loaded | No console on B-07. Recovery uses rpiboot (#2 or #3) or the hardware watchdog (K-6) |
| ESD on B-07 data | It now reaches the BCM2712 USB PHY, where before it reached nothing. ESD selection (GHO-11, O-3) becomes mandatory, not optional. A damaged PHY also loses rpiboot |
| BOOT_ORDER fallback (#2) chosen and the eMMC fails | The node waits for a USB host and never retries the eMMC. This is the cost of #2 |
| Hall input (#3) fitted, and a stray magnet is present at power-up | The node boots into rpiboot and waits. Mitigate with the DRV5032 sensitivity choice and the label position (**Unverified**) |

### Fallback: option B, 2:1 high-speed switch

Use this only if the owner keeps the hub on pins 103/105.

| Item | Proposed |
|---|---|
| Part | TI TS3USB221A, 1:2 USB 2.0 HS mux, µQFN-10 ([SCDS277C](https://www.ti.com/lit/ds/symlink/ts3usb221a.pdf)): VCC 2.3 to 3.6 V, RON 6 Ω max, CON 7.5 pF max, COFF 5 pF max, 0.9 GHz bandwidth, I(OFF) ±2 µA at VCC = 0, -40 to 85 °C. The alternative is the TS3USB30E ([SCDS255G](https://www.ti.com/lit/ds/symlink/ts3usb30e.pdf)): RON 10 Ω max, 1.4 GHz |
| Wiring | Common D± to CM5 103/105. 1D± to hub upstream (S = L). 2D± to B-07 (S = H). VCC from CM5_3V3. OE tied low |
| Select | S has a pull-down (default: hub). A CM5 GPIO drives S high for service, and nRPIBOOT asserted also forces S high through a diode-OR, so rpiboot reaches B-07 |
| Signal integrity | The off branch hangs on the common node as a stub (up to 5 pF), and the on path adds up to 7.5 pF and 6 Ω. Place the switch at the CM5 pins, keep both branches short, and run a USB 2.0 HS eye test on both paths (GHO-14/GHO-15) |
| Failure modes | Service mode drops HaLow and the OpenVLM for its whole duration. A VBUS-based select is not acceptable, because charging would disconnect the radios. Selecting from PD "USB Communications Capable" works only with PD hosts. The design needs a GPIO the ledger does not have spare |

Option B costs a part, a GPIO and HS margin, and still needs software to select. Option A is recommended.

### Proposed record text (K-3)

- **v1-pinout-and-sequencing.md, "CM5 physical carrier pins":** replace the row "USB2 D-/D+ | 103 / 105" with two rows. "USB2 D-/D+ (B-07 service port, device role; rpiboot) | 103 / 105" and "USB3-0 USB 2.0 pair DP/DM (TUSB4041I upstream) | 134 / 136". Add the sentence: "USB_OTG_ID (101) is left unconnected (internal pull-up, device role) with a DNP 0 Ω to GND."
- **v1-reference.md §3 and §8:** "USB: CM5 USB3-0's USB 2.0 pair to the four-port TUSB4041I hub … The CM5's dedicated USB 2.0 port (pins 103/105) connects only to B-07 as a USB device (console and network gadget, rpiboot)."
- **v1-reference.md §4:** replace "debug uses internal test pads and an internal debug UART/test points" with "The service console is a USB gadget on B-07. The CM5 debug UART is reachable only on the module's own TP35/TP36, on a bench carrier."
- **decisions.md:** a new D row when accepted (number assigned by the records owner). Text: "B-07 data connects directly to the CM5 USB 2.0 OTG port; the hub moves to a USB 3.0 port's USB 2.0 pair; rpiboot entry by software request, BOOT_ORDER (owner choice) and TP_NBOOT." It settles net plan K-3 and open item 20.

---

## K-6. Supervisor topology against CM5 power-up

### Problem (net plan K-6)

§13 puts SVS1 on CM5_3V3 and lets the TPS386000 pull PMIC_Enable low. But CM5_3V3 rises only after PMIC_Enable rises (CM5 datasheet §3.1: 5 V, then PMIC_EN, then CM5_+3.3V, then CM5_+1.8V). So RESET1 on SYS_PMIC_EN would hold the CM5 off for ever. The watchdog runs only after RESET1 releases, and it latches until MR, a SENSE1 reset or VDD loss (SBVS105F §8.3.3). VDD is 1.8 to 6.5 V, so VBAT_PROTECTED cannot feed it, and no record gives a source.

### Constraints that fix the topology (Datasheet)

1. **WDI and MR thresholds track VDD.** VIH = 0.7 x VDD and VIL = 0.3 x VDD (SBVS105F §6.3 and §6.5). With VDD = +5V_SYS (5.05 V), VIH is 3.54 V, which a 3.3 V CM5 GPIO cannot reach. The net plan's proposed +5V_SYS for VDD therefore fails the WDI interface. VDD must be a 3.3 V class rail.
2. **VDD must be up before the CM5 and stay up across a PMIC_Enable cycle.** §8.3.4 says to feed VDD from the earliest available rail. CM5_3V3 fails this, because it is off until PMIC_EN. +3V3_RADIO meets it: the LM76005 starts on BUCK_EN, independent of the CM5.
3. **Open-drain outputs may be pulled above VDD**, up to 6.5 V (§8.3.4). The CM5's own 100 kΩ pull-up to 5 V on PMIC_Enable is therefore a valid pull-up for RESET2 and RESET4.
4. **The watchdog belongs to SVS1:** it starts at RESET1 release, and only RESET1 assertion clears the WDO latch (§8.3.3, Table 5). MR is SVS1's only manual input, and it has no internal pull-up (§8.3.2).
5. **A CM5 boot takes far longer than the 450 ms minimum timeout** (§6.7). Without an arming gate, the watchdog would trip during every boot. The CT delay tops out at about 10 s (§9.1.4), which is not a dependable boot bound for OpenWrt (**Unverified** boot time).

### Proposed topology

The rails stay as §13 assigns them. What changes is the VDD source and where each output goes.

| Pin | Proposed connection | Status |
|---|---|---|
| VDD (14) | +3V3_RADIO, 0.1 µF at the pin | Proposed. Alternative: a 3.3 V LDO from +5V_SYS used only for the supervisor (one more part; it keeps the supervisor alive if only the 3.3 V buck fails) |
| SENSE1 (10) | CM5_3V3 through 64.9 kΩ / 10.0 kΩ (0.1 %): 2.996 V falling (Calculated, about 2.96 to 3.03 V) | Rail Record (§13), value Proposed |
| MR (1) | SUP_MR_N, driven by a new CM5 output SUPERVISOR_ARM, with 10 kΩ to GND. Low = disarmed | Proposed. 10 kΩ keeps MR below 0.3 x VDD even against an RP1 pull-up as strong as 37 kΩ at reset: 3.3 x 10/47 = 0.70 V, under 1.02 V (Calculated). The RP1 reset pull is **Unverified** |
| RESET1 (15) | TP_SUP_ARMED only. **Not** connected to SYS_PMIC_EN | Proposed |
| CT1 (5) | Open, 20 ms | Proposed |
| SENSE2 (9) | +5V_SYS through 110 kΩ / 10.0 kΩ (0.1 %): 4.80 V falling (Calculated, about 4.74 to 4.86 V) | Rail Record, value Proposed |
| RESET2 (16) | SYS_PMIC_EN (wired-OR, open drain, CM5 internal pull-up) | Proposed: the CM5 needs 5 V above 4.75 V before PMIC_EN rises (§3.1) |
| CT2 (4) | Open, 20 ms | Proposed |
| SENSE3 (8) | +3V3_RADIO through 65.0 kΩ / 10.0 kΩ (0.1 %): 3.00 V falling, a rail-absent level (Calculated) | Rail Record, value Proposed. A threshold near the 3.32 V setpoint minimum would trip on Wi-Fi load steps (the comparator responds to pulses of about 4 µs, §6.6) |
| RESET3 (17) | TP_SUP_RADIO only. DNP option: 10 kΩ series to each TPS22975 ON node as a hardware radio interlock | Proposed. Gating ON live would let a rail dip switch a radio off |
| CT3 (3) | Open | Proposed |
| SENSE4L (7) | +VBUS_HOLD (VBAT_PROTECTED if B-24 is not fitted) through 140 kΩ / 10.0 kΩ (0.1 %): 6.00 V falling (Calculated, about 5.93 to 6.07 V). WDO also connects to this node | Rail per the bridge study §4. Threshold Proposed: below the 7.0 V bridge backup point (bridge study, est.) and above the 5 V buck's dropout, about 5.33 V plus I x R. That figure is Calculated from LM76005 DMAX = 1 - tOFF-MIN x fSW = 0.948 and is **Unverified** |
| SENSE4H (6) | GND (OV unused) | Datasheet |
| RESET4 (18) | SYS_PMIC_EN (wired-OR) | Proposed |
| CT4 (2) | 100 kΩ to VDD: 300 ms fixed (225 to 375 ms) | Datasheet Table 6 |
| WDI (20) | SUPERVISOR_WDI (ledger), weak pull-down | Ledger; pull-down from the net plan |
| WDO (19) | Directly to the SENSE4L divider tap. No pull-up: when released it is high-Z and leaves the tap alone | Proposed. See the WDO note below |
| VREF (13) | No connect | Datasheet |
| NC (11), GND (12), PAD | GND | Datasheet |

The SENSE dividers use 10 kΩ bottom resistors, so the ±25 nA SENSE input current adds under 0.3 mV at the tap (Calculated). The ranges above combine the ±1 % VITN (396 to 404 mV) with 0.1 % resistors.

**WDO note.** Wiring WDO into SENSE4L turns every watchdog trip into a RESET4 event. RESET4 then holds SYS_PMIC_EN low for CT4 after WDO releases. That gives a PMIC_Enable pulse of at least 225 ms with no extra part. The ledger's SUPERVISOR_WDO input then has no useful job: by the time the CM5 could read WDO, its power is being removed, and the latch is clear after the reboot. Two ways forward, a **GHO-9 decision**:
- (a) Repurpose the SUPERVISOR_WDO ledger row as SUPERVISOR_ARM (the direction changes from input to output). No new GPIO is needed.
- (b) Keep SUPERVISOR_WDO as an input. Take a Reserved row for SUPERVISOR_ARM, isolate the tap with a Schottky diode (cathode to WDO), pull WDO up to VDD, and read it through an Ioff-rated open-drain buffer powered from CM5_3V3 (SN74LVC1G07, [SCES296AG](https://www.ti.com/lit/ds/symlink/sn74lvc1g07.pdf)), so the K-7 back-feed rule holds.

### Sequences (Calculated from datasheet behaviour; bench-verify)

**Power-up.** BUCK_EN rises, and +5V_SYS and +3V3_RADIO soft-start together (6.3 ms). Supervisor VDD passes 0.9 V and every RESET asserts (power-up reset voltage, §6.5). RESET2 and RESET4 hold SYS_PMIC_EN low against the CM5's internal pull-up. +5V_SYS passes 4.80 V, so RESET2 releases after 20 ms. The bus is above 6.0 V and WDO is high-Z, so RESET4 releases after 300 ms. PMIC_EN rises, CM5_3V3 comes up and the CM5 boots. RESET1 stays asserted, because SUPERVISOR_ARM is low through its pull-down, so the watchdog is idle.

One unchecked window: until supervisor VDD reaches 0.9 V, the RESET outputs are undefined. By then +5V_SYS has risen only to the same fraction of its ramp (under about 1.5 V), well below the 4.75 V at which the CM5 starts its sequence (Calculated).

**Arming.** The watchdog daemon starts toggling SUPERVISOR_WDI, then drives SUPERVISOR_ARM high. MR goes high, RESET1 releases after 20 ms, and the 450 to 750 ms timer runs.

**Trip.** No WDI edge for 450 to 750 ms, so WDO latches low. The SENSE4L tap goes low, and RESET4 drives SYS_PMIC_EN low. The CM5 PMIC turns off. CM5_3V3 falls below 3.0 V and SUPERVISOR_ARM falls to its pull-down, so RESET1 asserts and the WDO latch clears (§8.3.3). The tap recovers, RESET4 releases 225 to 375 ms later, and the CM5 reboots disarmed. The latch clears through SENSE1 or MR, never through VDD, which matches §13's warning that a PMIC_Enable cycle does not remove supervisor VDD.

**Pack swap.** With B-24, +VBUS_HOLD stays above about 7.0 V (bridge study, est.), above the 6.0 V SVS4 threshold, so no reset. If the bridge is exhausted, the bus falls through 6.0 V. RESET4 then powers the CM5 down in an orderly way before the 5 V buck drops out, and holds it off until the bus is back for 300 ms.

### Failure modes

| Case | Result |
|---|---|
| Watchdog daemon never arms (crash during boot, bad image) | No external watchdog coverage. The BCM2712 internal watchdog (`kernel_watchdog_timeout`, Raspberry Pi config docs) covers kernel hangs. This is the price of having no boot loop |
| CM5 hang with the arm GPIO still high | Recovered as designed |
| Kernel crash that resets RP1 pins to their defaults | The arm signal drops and disarms the watchdog. The SoC watchdog has to recover it |
| `poweroff` from the EUD | The daemon must drop SUPERVISOR_ARM before halting. Otherwise the watchdog power-cycles a node that was meant to stay off (software requirement, GHO-19) |
| `config.txt` sets SUPERVISOR_ARM high in the bootloader | Boot loop. The arm signal must be driven only by the watchdog service |
| +3V3_RADIO buck fails, +5V_SYS good | The supervisor has no VDD. Its open-drain outputs float, so the CM5 runs unsupervised. The LDO-from-+5V_SYS alternative avoids this |
| +5V_SYS dips under 4.80 V | RESET2 powers the CM5 off and back on 20 ms after recovery. The margin to the 4.95 V setpoint minimum is about 90 mV (Calculated); bench-check it against CM5 load steps |

### Proposed record text (K-6)

- **v1-reference.md §13, supervisor paragraph:** "Rails: SVS1 = CM5_3V3, SVS2 = +5V_SYS, SVS3 = +3V3_RADIO, SVS4 = +VBUS_HOLD (VBAT_PROTECTED without B-24). VDD = +3V3_RADIO, because WDI and MR use 0.7 x VDD thresholds that a 3.3 V GPIO meets only with a 3.3 V VDD. RESET2 and RESET4 drive SYS_PMIC_EN (open drain, wired-OR); RESET1 does not. MR is the watchdog arm: the CM5 drives SUPERVISOR_ARM high once its watchdog service runs, and a 10 kΩ pull-down disarms it whenever the CM5 is off or in reset. WDO pulls the SENSE4L tap, so a timeout asserts RESET4 and holds PMIC_Enable low for the CT4 delay (300 ms nominal). The latch clears when CM5_3V3 falls (SENSE1) or the arm drops (MR)." Keep the existing verified watchdog timing sentence.
- **v1-pinout-and-sequencing.md:** GHO-9 adds SUPERVISOR_ARM, either by repurposing the SUPERVISOR_WDO row (option a) or in a Reserved row (option b). The "Electrical sources" row for SUPERVISOR_WDI / SUPERVISOR_WDO is updated to match.
- **v1-hot-swap-bridge.md §4, supervisor row:** "SVS4 senses +VBUS_HOLD with a threshold below the backup regulation point (proposal: 6.0 V)."
- **Net plan 07_SYSTEM:** this replaces the VDD = +5V_SYS proposal.

---

## K-8. GNSS TIMEPULSE, SAFEBOOT_N and the PPS input

### Problem (net plan K-8)

MAX-M10S SAFEBOOT_N connects inside the module to TIMEPULSE through 1 kΩ, and the receiver enters safeboot if the pin is low at start-up (data sheet R08, Table 10 note 15). The u-blox integration manual says: "Make sure this pin has no load that could pull it low at startup" (UBX-20053088 R05, §3.2.3.3, page 28). Its migration table says: "Do not drive the TIMEPULSE pin low at startup because it will put the receiver in safeboot mode" (Appendix, Table 47, page 89).

In V1 this is not a corner case. +3V3_GNSS comes from +3V3_RADIO and is up before PMIC_Enable rises; with the K-6 proposal the gap is at least 20 to 300 ms. So the GNSS starts with the CM5 unpowered on every cold start. An unpowered RP1 input's protection structures would hold GNSS_PPS near ground (**Unverified**: the RP1 pad structure is not documented in the CM5 datasheet). Against the module's own pull-up (6 to 72 kΩ on SAFEBOOT_N, 8 to 40 kΩ on the PIO at V_IO 3.3 V; Table 14), that reads as low (VIL 0.63 V max). A GNSS reset through GNSS_RESET_N re-samples the pin too. While the CM5 is powered, an RP1 reset-default pull-down (35 to 98 kΩ, CM5 datasheet §4.3) against a 72 kΩ pull-up gives about 1.07 V, between VIL and VIH (0.68 x V_IO, about 2.3 V). That is undefined.

### Proposal

| Item | Proposed |
|---|---|
| Isolation buffer | TI SN74LVC1G34DCKR single buffer, SC70-5 ([SCES519O](https://www.ti.com/lit/ds/symlink/sn74lvc1g34.pdf)). Ioff "supports live insertion, partial power down" (±10 µA with VI or VO up to 5.5 V and VCC = 0), tpd 3.5 ns max at 3.3 V |
| Supply | VCC = CM5_3V3, 0.1 µF. The buffer is off whenever the CM5 is off |
| Input | A = GNSS_TIMEPULSE (Proposed net name), MAX-M10S pin 4, with a very short trace. No other load on this net |
| Output | Y = GNSS_PPS (ledger signal) to the CM5 PPS input. Proposed: a 22 to 33 Ω series footprint at Y for edge damping, then TP_GNSS_PPS on the CM5 side |
| Pull-up | DNP 100 kΩ from GNSS_TIMEPULSE to +3V3_GNSS. Populate only if the bench shows a need. It returns to the GNSS's own rail, so hardware backup mode (VCC = V_IO = 0) still sees no driven PIO (data sheet Table 11 note) |
| TP_GNSS_SAFEBOOT | Unchanged (Record): pin 18, for deliberate safeboot entry |
| CM5-side default | GNSS_PPS is an input with no pull (`ip,pn`); `dtoverlay=pps-gpio` stays (ledger, firmware PR #23). It must never be configured as an output, because it is driven by Y. Whenever the CM5 is powered, the buffer defines the level, so the RP1 reset pull no longer matters |

Margin check (Calculated). With the CM5 off, the worst-case buffer input leakage is 10 µA, through the 40 kΩ worst-case PIO pull-up. That drops 0.4 V, so the pin sits at at least 2.9 V against VIH of about 2.3 V. No safeboot. The 3.5 ns fixed delay is small next to PPS-to-GPIO interrupt latency and can be calibrated out.

The buffer also removes the TIMEPULSE back-feed into an unpowered CM5 (TIMEPULSE has 4 mA drive, Table 14 note 22), which is one of the K-7 paths. GNSS TXD to GNSS_UART_RX is the same pattern. A dual SN74LVC2G34 would cover both. That is left to K-7 and GHO-9, and is not proposed here.

**Rejected alternatives.**
- A series resistor alone. With the CM5 unpowered the pin is near 0 V. A resistor of 470 kΩ or more would be needed to stay high against a 72 kΩ pull-up, and that slows the PPS edge into the GPIO capacitance and fails against an RP1 pull-down while the CM5 is on.
- An external pull-up alone. It cannot beat a pin clamped by an unpowered input.
- Moving PPS to EXTINT. That does not exist: TIMEPULSE is the only time-pulse output (integration manual §3.2.3.3).

### Proposed record text (K-8)

- **v1-reference.md §9:** "TIMEPULSE shares SAFEBOOT_N through 1 kΩ inside the module, and a low at start-up forces safeboot (u-blox data sheet R08 Table 10; integration manual R05 §3.2.3.3). GNSS_PPS reaches the CM5 through an Ioff-rated buffer powered from CM5_3V3, so the module pin sees no load at start-up whatever the CM5 state. The CM5 PPS input is configured as an input with no pull."
- **Net plan, 05_GNSS pin 4 and 07_SYSTEM GPIO defaults:** "GNSS_TIMEPULSE to the buffer input; GNSS_PPS from the buffer output." This closes K-8 and open item 30.

---

## K-9. TUSB4041I 1.1 V core rail

### Requirement (Datasheet, TUSB4041I SLLSEK3F, revised June 2026)

- VDD (1.1 V core, seven pins): 0.99 to 1.26 V. 1.05, 1.1 or 1.2 V supplies are acceptable (§5.3). VDD33: 3.0 to 3.6 V.
- Current (§5.7, typical / max):

| Mode | VDD33 | VDD (1.1 V) |
|---|---|---|
| Power on (after reset) | 2.3 / 2.6 mA | 28 / 32 mA |
| 2.0 host, 1 HS device | 45 / 51 mA | 63 / 72 mA |
| 2.0 host, 4 HS devices | 76 / 87 mA | 86 / 98 mA |
| Global reset mode | 77 / 88 mA | 332 / 370 mA |
| SMBus programming | 79 / 90 mA | 329 / 378 mA |

  The core draws more while GRSTz is held low than in any active mode. V1 holds the hub in reset by default and as a recovery step, so HUB_1V1 is sized for 370 mA continuous, not 98 mA.
- Sequencing (§5.6, §6.3.7): there is no required order between VDD and VDD33. If VDD33 is stable before VDD, an active reset is required. GRSTz must stay low for at least 3 ms after both supplies are in range. Ramps are 0.2 to 100 ms. The straps (FULLPWRMGMTz, GANGED, PWRCTL_POL, SMBUSz, BATEN[4:1], AUTOENz) are sampled when GRSTz rises.
- Layout (§7.3.1): an optional ferrite on VDD with DCR under 0.05 Ω. 0.1 µF per pin plus 10 µF bulk. Place the regulator away from the hub, the crystal and the pairs.

### Regulator choice

| Option | Dissipation at 370 mA | Verdict |
|---|---|---|
| LDO from CM5_3V3 to 1.1 V | 2.2 V x 0.37 A = 0.81 W. In a SOT-23-5 DYD (60.3 °C/W, [TLV757P SBVS322C](https://www.ti.com/lit/ds/symlink/tlv757p.pdf)) that is a 49 °C rise. It also takes 0.37 A of the CM5's 600 mA 3.3 V budget | Rejected for the sealed fanless enclosure |
| LDO from CM5_1V8 to 1.1 V | 0.26 W | Rejected. 0.7 V of headroom is below the characterized dropout (TLV755P: 825 mV max at 500 mA for 1.0 to 1.2 V out; TLV757P: 1.2 V max at 1 A; [SBVS320D](https://www.ti.com/lit/ds/symlink/tlv755p.pdf)). The core could sag out of range in global reset |
| **Buck from CM5_3V3 to 1.10 V (proposed)** | About 0.07 W loss at 370 mA. CM5_3V3 input about 0.16 A (Calculated at an assumed 85 % efficiency, **Unverified** at this operating point) | Proposed |

**Proposed part:** TI TLV62568DBVR, 1 A synchronous buck, SOT-23-5, VIN 2.5 to 5.5 V, 1.5 MHz, power-save mode at light load, VFB 0.6 V (0.588 to 0.612 V), 700 µs soft start for the DBV, UVLO 2.3 to 2.45 V falling ([SLVSD89B](https://www.ti.com/lit/ds/symlink/tlv62568.pdf)).

| Pin or part | Proposed |
|---|---|
| VIN | CM5_3V3, 10 µF local |
| EN | Tied to VIN. The buck runs exactly when the CM5 is powered |
| L | 2.2 µH shielded (the datasheet's typical value), rated at least 1.5 A (the high-side current limit). Exact MPN open (GHO-26) |
| FB divider | 150 kΩ over 180 kΩ (1 %): 0.6 x (1 + 150/180) = 1.10 V. With the VFB tolerance, about 1.07 to 1.13 V, inside 0.99 to 1.26 V (Calculated) |
| Output | HUB_1V1: 2 x 10 µF at the buck (Proposed; check against the datasheet output-capacitor table), then an optional ferrite with DCR under 0.05 Ω (18.5 mV at 370 mA), then 0.1 µF at each of the seven VDD pins and 10 µF bulk |
| Placement | Not under the CM5 (no inductors there, §4). At least the hub-to-crystal distance away from XI/XO and the USB pairs (TUSB4041I §7.4.1.1) |

The TLV62568**P** variant (SOT-563 or SOT-23-6) adds an open-drain power-good. It is not proposed for GRSTz: wiring it onto a pin that a push-pull GPIO also drives would cause contention, and the timing below already meets td2.

LDO fallback, if the owner rejects a switcher near the hub: TLV75712PDYDR (1.2 V fixed, inside the 1.26 V maximum) fed from +3V3_RADIO, not from CM5_3V3. That accepts the 0.81 W worst case only if firmware never leaves the hub in global reset (**Owner decision**, GHO-10).

### HUB_3V3 and sequencing against GRSTz

| Item | Proposed |
|---|---|
| HUB_3V3 (VDD33) | CM5_3V3 (the net plan's proposal, kept). The hub, its core and its upstream link are all in the CM5 power domain, so nothing in the hub back-feeds the CM5 when the CM5 is off (K-7) |
| Order | CM5_3V3 rises (after PMIC_EN). The buck passes UVLO and soft-starts in about 0.7 ms, so HUB_1V1 is in range about 1 ms after CM5_3V3 (**Unverified**). VDD33 is stable first, so the datasheet's active-reset rule applies |
| GRSTz bias | USB_HUB_RESET_N gets 2.2 kΩ to GND (Proposed). It must hold GRSTz under VIL = 0.8 V against the internal pull-up, whose current can reach IOZ(P) = 250 µA (TUSB4041I §5.5). That allows at most 0.8 V / 250 µA = 3.2 kΩ (Calculated). Driving 2.2 kΩ high costs the GPIO 1.5 mA |
| Release | Firmware drives USB_HUB_RESET_N high (`op,dh` in firmware PR #23). That runs in the bootloader, hundreds of ms after CM5_3V3, far beyond td2 = 3 ms after both supplies (**Unverified** on hardware). The hub cannot be released early, because the GPIO is itself in the CM5 domain |
| Recovery reset | A low pulse of at least 10 ms (Proposed; the datasheet gives only the 3 ms power-up figure). Release again afterwards, because the hub draws up to 370 mA on the core while held in reset. Software should not park the hub in reset to disable its ports; use port power (HUB_PWRCTL3) instead |
| Straps | The net plan's strap biases stand. All are static resistors, so they are valid at the GRSTz rising edge |

CM5_3V3 budget for the hub (Calculated): VDD33 at most 88 mA, plus the buck input at most about 0.16 A. That is under about 0.25 A in global reset and about 0.13 A active, out of the CM5's 600 mA (CM5 datasheet §3.4). GHO-10 should add the INA228, buffers and pull-ups to the same tally.

### Proposed record text (K-9)

- **v1-selections.md (records owner assigns the next B-ID when accepted):** "Hub core regulator: TI TLV62568DBVR buck, CM5_3V3 to HUB_1V1 1.10 V, sized for the TUSB4041I global-reset current (370 mA max, SLLSEK3F §5.7). Candidate."
- **v1-reference.md §17, 03_USB_HALOW_AUDIO:** add "HUB_1V1 buck (TLV62568) from CM5_3V3; HUB_3V3 = CM5_3V3; GRSTz held low by 2.2 kΩ until firmware release."
- **v1-pinout-and-sequencing.md, working sequence step 6:** "Deassert TUSB4041I reset only after CM5_3V3, HUB_1V1 and 24 MHz are stable (at least 3 ms after both supplies, SLLSEK3F §5.6); the 2.2 kΩ pull-down holds it until then."

---

## How the four proposals fit together

- K-3 option A, K-8 and K-9 all put the CM5-facing parts (the hub, its regulator and the PPS buffer) in the CM5_3V3 domain, so they switch off with the CM5. The always-on GNSS and supervisor reach the CM5 only through Ioff-rated or open-drain interfaces.
- K-6 sets the start-up gap that K-8 depends on: the GNSS always starts before the CM5.
- K-6 needs one ledger row (SUPERVISOR_ARM), and K-3 option B would need another. Option A needs none. Both are GHO-9 allocations.

## Decisions for the project owner

1. **K-3 architecture:** option A (re-home the hub to a USB 3.0 port's USB 2.0 pair; B-07 direct to the OTG port), recommended, or option B (TS3USB221A switch). This changes the ledger's USB pin rows and the stackup routing plan (GHO-9, GHO-14).
2. **Hardware rpiboot entry without opening the enclosure:** TP_NBOOT only (enclosure open; the default proposal), or a sealed DRV5032FC Hall input behind a marked spot on the wall. The question is whether a magnet-actuated service input is acceptable under "no physical buttons" (§30 rule 9).
3. **BOOT_ORDER RPIBOOT fallback:** whether a node whose eMMC fails should wait indefinitely in rpiboot (field-recoverable over B-07), or keep retrying the eMMC (it cannot be recovered without the enclosure open or a software request).
4. **Supervisor VDD:** +3V3_RADIO (no new part), or a dedicated LDO from +5V_SYS (survives a 3.3 V buck failure).
5. **SUPERVISOR_WDO:** repurpose its ledger row as SUPERVISOR_ARM, or keep it as an input with a Schottky diode, a buffer and a separate arm GPIO (GHO-9).
6. **External watchdog arming policy:** armed by software after boot (proposed: no boot loops, no coverage before the daemon starts), against an always-armed design that needs a boot time guaranteed under about 10 s.
7. **K-9 regulator type:** a buck near the hub (proposed), or the LDO fallback with a firmware rule never to hold the hub in reset.

## What is unverified

- CM5 USB device mode and the dwc2 gadget on the OpenWrt CM5 image. The CM5 datasheet calls device mode "not officially documented". rpiboot device boot is documented for the CM5 IO board.
- `set_reboot_order` on the CM5 (documented as "Raspberry Pi 5 only"; same SoC), and whether a PWR_BUTTON power-on re-samples nRPIBOOT.
- That the TUSB4041I enumerates and performs on an RP1 USB 3.0 port's USB 2.0 pair, and that the OpenWrt target includes the RP1 xHCI driver.
- TPS25751A UFP data-role configuration. BQ25798 D+/D- behaviour (its datasheet was not fetched).
- Whether the GCT USB4720-03-A has SBU contacts.
- RP1 pad behaviour when unpowered (assumed clamped near ground) and the RP1 reset-default pulls on the arm, PPS and hub-reset GPIOs.
- The LM76005 5 V dropout at 2.5 A (about 5.33 V plus I x R, Calculated), and so the 6.0 V SVS4 threshold margin. The 7.0 V bridge backup point is itself an estimate (bridge study).
- The +5V_SYS SVS2 threshold (4.74 to 4.86 V) against CM5 load-step undershoot.
- The supervisor's behaviour below VDD = 0.9 V during the first part of the rail ramp.
- OpenWrt boot time on the CM5 (relevant only if the always-armed policy is chosen).
- The TLV62568 efficiency and output-capacitor choice at 1.10 V and 370 mA, the HUB_1V1 rise time, and the GRSTz release timing on hardware.
- DRV5032FC actuation distance through the enclosure wall, and its immunity to stray fields.
- Every Calculated value above is arithmetic on datasheet figures. None is measured.

## Sources

| Document | Revision used | Sections cited |
|---|---|---|
| [Raspberry Pi CM5 datasheet](https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf) | Release 3, build 08/06/2026 | §2.4, §2.8, §2.12.2 Table 3, §3.1, §3.4, §4.3, Table 4, Table 13, Table 14 |
| [Raspberry Pi CM5 IO board datasheet](https://datasheets.raspberrypi.com/cm5/cm5io-datasheet.pdf) | history entry 11 September 2026 | §1.3, §3.4, §5.1 Table 1 |
| Raspberry Pi documentation ([raspberrypi/documentation](https://github.com/raspberrypi/documentation), commit `62ba0a0`, 2026-10-08) | `eeprom-bootloader.adoc` (BOOT_ORDER, BOOT_UART), `bootflow-eeprom.adoc`, `config_txt/boot.adoc` (`set_reboot_order`), `compute-module/cm-emmc-flashing.adoc`, `cm-bootloader.adoc` | |
| [TI TS3USB221A](https://www.ti.com/lit/ds/symlink/ts3usb221a.pdf) | SCDS277C, October 2024 | §5.3, §5.5, dynamic characteristics, Table 7-1 |
| [TI TS3USB30E](https://www.ti.com/lit/ds/symlink/ts3usb30e.pdf) | SCDS255G, October 2024 | Features |
| [TI TPS25751](https://www.ti.com/lit/ds/symlink/tps25751.pdf) | Rev. A | Pin functions (GPIO4/USB_P, GPIO5/USB_N) |
| [TI DRV5032](https://www.ti.com/lit/ds/symlink/drv5032.pdf) | SLVSDC7H, December 2024 | Device comparison, VCC range |
| [TI TPS386000](https://www.ti.com/lit/ds/symlink/tps386000.pdf) | SBVS105F, October 2018 | §6.3, §6.5 to §6.7, §8.3.2 to §8.3.4, Tables 1 to 6, §9.1.4 |
| [TI LM76005](https://www.ti.com/lit/ds/symlink/lm76005.pdf) | SNVSBK5A | tOFF-MIN, Equation 2 |
| [TI SN74LVC1G07](https://www.ti.com/lit/ds/symlink/sn74lvc1g07.pdf) | SCES296AG, October 2025 | Ioff |
| [u-blox MAX-M10S data sheet](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf) | UBX-20035208 R08, 30 January 2026 | Table 10 note 15, Table 11, Table 14 |
| [u-blox MAX-M10S integration manual](https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf) | UBX-20053088 R05, 28 April 2026 | §3.2.3.2, §3.2.3.3 (page 28), Appendix Table 47 (page 89) |
| [TI SN74LVC1G34](https://www.ti.com/lit/ds/symlink/sn74lvc1g34.pdf) | SCES519O, October 2025 | Features, Ioff, tpd |
| [TI TUSB4041I](https://www.ti.com/lit/ds/symlink/tusb4041i.pdf) | SLLSEK3F, June 2026 | §5.3, §5.5, §5.6, §5.7, §6.3.7, §7.3.1, §7.4.1.1 |
| [TI TLV62568](https://www.ti.com/lit/ds/symlink/tlv62568.pdf) | SLVSD89B, November 2017 | Electrical characteristics, typical application |
| [TI TLV757P](https://www.ti.com/lit/ds/symlink/tlv757p.pdf) | SBVS322C, March 2024 | Dropout, thermal |
| [TI TLV755P](https://www.ti.com/lit/ds/symlink/tlv755p.pdf) | SBVS320D, September 2024 | Dropout |
