# V1 Ethernet and GNSS protection proposal

**Owner:** [GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11), open Track B parts (Ethernet ESD and magnetics, GNSS protection, backup and connector).  
**Status:** candidate proposal, desk review, 2026-10-09. No part is frozen and no decision is recorded. Nothing here has been built or measured.

This file proposes how to protect the 1000BASE-T MDI that runs from the CM5 to the Molex Pico-Lock header and pigtail (B-06, D-022, D-025). It also covers the MAX-M10S backup supply and active-antenna bias and RF protection (B-05, B-21), and summarises a chassis and shield bonding strategy. Selections stay owned by [v1-selections.md](v1-selections.md). Decisions stay owned by [../decisions.md](../decisions.md). Interface facts come from [v1-reference.md](v1-reference.md) §9, §10 and §18, [v1-stackup-routing.md](v1-stackup-routing.md), [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md) and [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md). If those files change, they win. A choice made from this file follows the four-step decision rule in [../README.md](../README.md).

## Summary

| Item | Proposal (candidate) | Main evidence |
|---|---|---|
| Magnetics location | On the carrier, between the CM5 connector and the Pico-Lock header. The CM5 and the feed-through have none, and a crimped Cat5e pigtail cannot hold them. | CM5 datasheet Release 3, Table 4: the MDI pins "connect to transformer or MagJack"; v1-reference.md §10 |
| Magnetics part | Open. It must be a low-profile discrete 1000BASE-T module, 3.5 mm tall or less (D-025). Common SMD modules are about 6 to 9 mm tall. Pulse HX5120NL (about 2.1 mm) is the lead to check. | Würth 7490220122: 8.8 mm (fetched). HX5120NL height from a distributor listing: **Unverified** |
| MDI ESD device | Two **TI TPD4EUSB30** (DQA) on the PHY side, next to the magnetics. Alternates: TPD4E05U06 (lower capacitance) and TPD4E1U06. No TVS from the line side to logic ground. | Raspberry Pi uses the TPD4EUSB30 on the PHY side in the CM5 datasheet Figure 2 |
| Centre taps | PHY side: tie the four centre taps together and decouple them with 100 nF to GND, as in the CM5 reference. Line side: Bob Smith network, 4 x 75 Ω to one 1000 pF high-voltage capacitor to CHASSIS_GND. | CM5 datasheet Figure 2. The Bob Smith values are common practice; the IEEE 802.3 text was not fetched |
| GNSS backup (V_BCKP) | Supercapacitor of about 0.33 to 0.47 F, charged from +3V3_GNSS through a resistor and a Schottky diode. Host-side time and orbit aiding covers longer outages. No coin cell. | MAX-M10S integration manual R05 §4.1.3; data sheet R08 Table 17 |
| Antenna bias | Feed the antenna from a current-limited switch (**TI TPS2553**, ILIM tied to IN: 50 to 100 mA), not straight from VCC_RF. Enable it from LNA_EN and wire its FAULT output to the module's ANT_SHORT_N input. This makes the u-blox two-pin antenna supervisor. | Data sheet R08 Tables 12 and 13; integration manual §3.3.1 and §B.2; TPS2553 SLVS841F §7.5 |
| GNSS RF ESD | Populate no TVS by default. Keep a DNP footprint. Populate it only with a part whose datasheet gives capacitance and S21 at 1575 MHz and that meets the limits in §2.4. | v1-reference.md §9 and §30 rule 13 |
| Chassis | The enclosure is the reference for every cable shield. The RF bulkheads and the thermal path already tie logic ground to the chassis, so treat CHASSIS_GND as bonded to GND at chosen points. Keep the Ethernet line side isolated. | §3 below. Needs an owner decision |

## 1. Ethernet: 1000BASE-T MDI to the Pico-Lock header

### 1.1 Where the magnetics sit

| Location | Status | Why |
|---|---|---|
| CM5 module | No magnetics | CM5 datasheet Release 3 (build 08/06/2026), Table 4, pins 3 to 12: each Ethernet pair is to "connect to transformer or MagJack". §2.2.1 assumes a "standard 1:1 RJ45 MagJack". |
| Feed-through (RCP-5SPFFH-SCU7001) | No magnetics | v1-reference.md §10: "the feed-through has no magnetics". |
| Pigtail | Not practical | The pigtail is Cat5e or Cat6 cable crimped to 504052 terminals at one end and a T568B plug at the other (B-06). It has no place for windings. |
| Carrier | **Required** (B-06: "Discrete magnetics on the carrier") | Signal order: CM5 MDI → PHY-side ESD → magnetics → line side → Pico-Lock header. |

**Floorplan fit.** The §18 placeholder is 14 x 9 mm at X 23 to 37, Y 12 to 21, under the RJ45 plug, and the part must be 3.5 mm tall or less (D-025). The header sits at X 41 to 54.5, Y 2 to 9.5, so the line-side run from the magnetics to the header is short, about 5 to 15 mm, which suits the isolated line-side region in [v1-stackup-routing.md](v1-stackup-routing.md) §4.

**The height limit is the hard constraint.** Common 24-pin SMD gigabit modules are tall. The Würth WE-LAN 7490220122 (a 1000BASE-T SMT transformer with PoE+) is 8.8 mm tall with a 17.55 x 14.7 mm body ([datasheet](https://www.we-online.com/components/products/datasheet/7490220122.pdf), fetched 2026-10-09). Low-profile parts exist:

| Candidate | Height | Body | Status of the evidence |
|---|---|---|---|
| Pulse HX5120NL, 10/100/1000BASE-T, 1CT:1CT, 350 µH | 2.08 mm seated (0.082 in) | 16.51 x 9.14 mm | **Unverified.** From distributor listings found in a search on 2026-10-09. The Pulse datasheet could not be fetched (connection reset), so isolation rating, pinout and whether the 1000BASE-T return-loss and crosstalk figures are guaranteed are unchecked. |
| Abracon ALANL10001, 1000BASE-T | about 2.5 mm | 19.8 x 16.6 mm | **Unverified.** From a search snippet; the datasheet download failed. Too large for the placeholder. |

If HX5120NL checks out, its 16.5 mm length overruns the 14 mm placeholder by about 2.5 mm. GHO-7 has to place it. Selection criteria for the magnetics: 1000BASE-T, four channels with centre taps on both sides, at least 1500 Vrms isolation (§10 already assumes 1500 Vrms), seated height of 3.5 mm or less, −40 °C or lower to at least +85 °C, and published insertion loss, return loss, crosstalk and CMRR. The creepage and clearance between the PHY-side and line-side pins set the isolation gap in the stackup's line-side region ([v1-stackup-routing.md](v1-stackup-routing.md) §4 leaves that gap open).

### 1.2 ESD and surge device on the MDI pairs

**Placement: PHY side only.** The header is on the MDI side of the 1500 Vrms barrier, and v1-reference.md §10 allows no logic-ground pins there. A TVS from a line-side conductor to logic ground would bridge the barrier and break the isolation, so V1 puts no line-side TVS to GND. ESD arriving on the cable pins couples through the transformer. A low-capacitance array between the magnetics and the CM5, referenced to GND and placed right at the magnetics' PHY-side pins, clamps what gets through. This is the topology Raspberry Pi shows for the CM5: CM5 datasheet Figure 2 places two TPD4EUSB30 on the TRD pairs between the CM5 and the MagJack.

**Capacitance limit for 1000BASE-T.** IEEE 802.3 sets no TVS capacitance limit. The limit comes from the return-loss budget, which the magnetics and connector use up first. On a 100 Ω differential pair (50 Ω odd mode), a shunt capacitance C on each line gives |Γ| ≈ ωC·25 Ω. At 100 MHz, the top of the 1000BASE-T return-loss band, that works out to:

| C per line | Return loss from the TVS alone |
|---:|---:|
| 0.8 pF | 38 dB |
| 2 pF | 30 dB |
| 5 pF | 22 dB |

Proposed limit: **2 pF per line maximum**, matched within each pair (ΔC 0.1 pF or less), so the TVS stays at least 10 dB below any realistic link return-loss requirement. Balance matters more than the absolute value, because mismatch converts differential signal to common mode. The 802.3 return-loss mask itself was not fetched (**Unverified**); the calculation above is first-order and ignores package inductance.

| Part | Line C (typ) | VRWM | Clamp | IEC 61000-4-2 | IEC 61000-4-5 (8/20 µs) | Temp | Package | Notes |
|---|---|---|---|---|---|---|---|---|
| **TI TPD4EUSB30** (DQA) | 0.8 pF IO to GND, 0.05 pF IO to IO | 5.5 V | 8 V max at 1 A | ±8 kV contact, ±9 kV air | 5 A, 45 W | −40 to +85 °C | USON-10, 2.5 x 1.0 mm, flow-through | **Lead.** Used in Raspberry Pi's CM5 Ethernet reference (CM5 datasheet Figure 2). Two per port. [SLVSAC2G](https://www.ti.com/lit/ds/symlink/tpd4eusb30.pdf) §6.1, §6.2, §6.5 |
| TI TPD4E05U06 (DQA) | 0.5 pF, ΔC 0.05 typ / 0.07 max | 5.5 V (VBR 6.5 V min) | 10 V at 1 A and 14 V at 5 A (TLP) | ±12 kV contact, ±15 kV air | 2.5 A, 40 W | −40 to +125 °C | USON-10 | Lowest capacitance, but half the surge current of the lead. Whether its pinout drops into the TPD4EUSB30 land is **Unverified**. [SLVSBO7O](https://www.ti.com/lit/ds/symlink/tpd4e05u06.pdf) §5 |
| TI TPD4E1U06 | 0.8 pF (1 pF max), ΔC 0.025 typ / 0.07 max | 5.5 V | 11 V at 1 A and 15 V at 3 A, 8/20 µs | ±15 kV contact and air | 3 A, 45 W | −40 to +125 °C | SC70-6 or SOT-23-6 | Lists Ethernet as an application. Larger leaded package, easier to rework. [SLVSBQ9D](https://www.ti.com/lit/ds/symlink/tpd4e1u06.pdf) §7 |
| Semtech RClamp0524P | 0.3 pF IO to IO | 5 V | n/a | ±8 kV contact, ±15 kV air | 5 A | n/a | SLP2510P8 | **Unverified, not recommended.** The Semtech datasheet could not be fetched (bot block); figures are from search snippets. A distributor notice says the part is discontinued, with a 2022 last-time buy and RClamp0594P named as its replacement (also unverified). |
| Nexperia PESD2ETH1G-T / PESD2ETH1GXT-Q | 1.8 / 1.1 pF | 24 V | trigger Vt1 100 V min | 30 kV contact | 2.3 A | AEC-Q101 | SOT23 | **Wrong application.** Made for automotive 100/1000BASE-T1 single-pair links. A 100 V trigger is far above what a PHY-side 1000BASE-T pin survives. [PESD2ETH1G-T](https://assets.nexperia.com/documents/data-sheet/PESD2ETH1G-T.pdf), [PESD2ETH1GXT-Q](https://assets.nexperia.com/documents/data-sheet/PESD2ETH1GXT-Q.pdf) |

All three TI parts are unidirectional to GND. The lead part is the one Raspberry Pi validated against the CM5's BCM54210PE swing. The BCM54210PE datasheet is not public, so the PHY-side common-mode level and the PHY pins' own ESD rating are **Unverified**. If the TPD4EUSB30 is used beyond what Raspberry Pi shows, its 85 °C ambient limit is enough for D-028, but it needs a check against the sealed-enclosure temperatures in [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md).

**Surge.** The project records set no surge level for the Ethernet port. Line-to-ground surge is held off by the 1500 Vrms isolation. Line-to-line surge is passed through the magnetics, attenuated by them, and then clamped by the PHY-side array (5 A, 8/20 µs for the lead part). A port that may connect to long outdoor cable runs would need a requirement, then a test to IEC 61000-4-5 and possibly a line-side differential (line-to-line) protector. That requirement needs an owner decision under GHO-11; this file assumes short field patch cables.

### 1.3 Centre taps and Bob Smith termination

- **PHY side.** Follow CM5 datasheet Figure 2: tie the four PHY-side centre taps together and decouple them with 100 nF to GND at the magnetics. Do not bias them from a rail. The BCM54210PE is not documented as needing CT bias, and Raspberry Pi's reference applies none (**Unverified** against the Broadcom datasheet).
- **Line side, Bob Smith.** Connect each line-side centre tap through a 75 Ω resistor to a common node, then through one 1000 pF capacitor to CHASSIS_GND. This is the network inside the MagJack in Figure 2. Size the capacitor for the 802.3 isolation test, which is commonly stated as 1500 Vrms for 60 s or 2250 Vdc (**Unverified**; IEEE 802.3 §40.6.1.1 was not fetched). A 2 kV rating is common practice and 3 kV adds margin. Place the network inside the line-side isolated region, with no logic ground under it.
- If the selected magnetics integrate the Bob Smith network or common-mode chokes, do not duplicate them. Check the module schematic.

### 1.4 Header, pigtail and shield continuity

- All eight Pico-Lock circuits carry the MDI pairs (§10: pins 1/2, 3/4, 5/6, 7/8). The header has **no spare pin** for a cable shield or drain. If the pigtail uses shielded cable, terminate the shield only at the feed-through end, on the plug's shell. The board end stays unterminated.
- The RCP-5SPFFH-SCU7001 is specified for shielded Cat5e (B-06). How its shield bonds to the wall depends on the panel interface and whether the internal RJ45 socket shell is continuous with the external shell. Neither is in the records (**Unverified**; check the Amphenol drawing in v1-cad/step/ under GHO-7).
- Twisting and matching limits stay as §10 and the stackup file give them.

## 2. GNSS: MAX-M10S backup and active antenna

Sources: [MAX-M10S data sheet UBX-20035208 R08](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf) (30 Jan 2026) and [MAX-M10S integration manual UBX-20053088 R05](https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf) (28 Apr 2026), both fetched 2026-10-09.

### 2.1 When the backup domain matters

Under D-027 the pack-swap bridge keeps +3V3_RADIO, and with it +3V3_GNSS, alive through a swap. A CM5 PMIC_Enable recovery does not remove +3V3_GNSS either. So V_BCKP is exercised only when the whole node is off: deliberate shutdown, storage or transport, bridge exhaustion, or an eFuse trip. With VCC and V_IO at 3.3 V, both supplies may be switched off together (data sheet §4.2). If V_BCKP is supplied, the module then enters hardware backup mode and keeps the RTC and battery-backed RAM (BBR).

### 2.2 Options

| Option | What it keeps | Typical TTFF on next power-up | Cost and risk |
|---|---|---|---|
| **None** (V_BCKP open, as the manual allows) | Nothing: RTC, ephemeris and BBR configuration are lost. Configuration must live in host software and be re-sent. | Cold start 27 s typical in the default GPS+GAL+BDS B1I mode at −130 dBm (Table 2). Cold-start sensitivity is −148 dBm against −159 dBm for a hot start, so weak-signal starts take much longer. Host time aiding (UBX-MGA-INI-TIME_UTC) and orbit data stored on the host can shorten this (manual §B.2). | Zero parts. The CM5 has no recorded time source while offline: its RTC needs VBAT, and V1 records no RTC battery (see §2.5). |
| **Supercapacitor** (proposed) | RTC and orbit data for hours | Hot start 1 s while the ephemeris is valid (typically up to 4 h, manual §4.1.3). AssistNow Autonomous 3 to 4 s with orbit data up to a few days old. | Small, needs no maintenance, rechargeable for life. Leakage and high-temperature aging shorten hold time. |
| **Coin cell** (for example CR2032) | Months | Hot or warm start for the whole storage period | Primary lithium cell in a sealed, headless enclosure with no service access. Needs reverse-charge protection, adds a second battery to the node, and its life drops at the enclosure's internal temperature. **Not proposed.** It is the same reasoning that [v1-hot-swap-bridge.md](v1-hot-swap-bridge.md) applies to a second cell. |

### 2.3 Supercapacitor sizing (desk estimate)

The hardware backup current is 28 µA typical at V_BCKP = 3.3 V (data sheet Table 17); about 3 µA flows during normal operation. V_BCKP must stay between 1.65 and 3.6 V (Table 13 and Table 12). If the capacitor charges to about 3.0 V (3.3 V less a Schottky drop) and discharges to 1.65 V at a constant 28 µA, with no capacitor leakage counted:

| C | Hold time to 1.65 V |
|---:|---:|
| 0.10 F | 1.3 h |
| 0.22 F | 2.9 h |
| 0.33 F | 4.4 h |
| 0.47 F | 6.3 h |
| 1.0 F | 13.4 h |

Proposal: **0.33 to 0.47 F**, rated at least 3.3 V and at least 85 °C, to cover the 4-hour hot-start window with some leakage margin. Circuit: +3V3_GNSS → Schottky (blocks back-feed into the rail when it is off) → series resistor, about 330 Ω (initial charge about 9 mA, τ about 155 s at 0.47 F) → capacitor at the V_BCKP pin. u-blox warns against high resistance between the backup source and the pin (manual §4.1.3). Putting the capacitor directly at the pin and the resistor upstream satisfies that. No supercapacitor MPN is proposed. Leakage current, ESR and aging at temperature must come from the chosen part's datasheet, and the 28 µA is typical, not maximum.

Interface rules for hardware backup mode (data sheet §3 Table 11 note, manual §3.6.3.1): PIOs must not be driven while V_IO is 0 V. The CM5 drives GNSS_UART_TX and GNSS_RESET_N (allocations in [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md)). If a state where the CM5 is powered and +3V3_GNSS is off can exist, add series resistors or a buffer, and check this when GHO-9/GHO-10 close the sequencing. RESET_N clears BBR, so firmware must not pulse GNSS_RESET_N on every boot if the backup is to be useful.

### 2.4 Active antenna bias, current limit and short detection

**Why not feed the antenna straight from VCC_RF.** VCC_RF is VCC − 0.1 V, at most 50 mA in operation (Table 13), with an absolute maximum of 250 mA source current (Table 12). The u-blox supply network (manual §4.3.4, Figure 28; values in §C) uses L3 = 27 nH (over 500 Ω at L1, rated at least 300 mA), C14 = 10 nF and R8 = 10 Ω, 0.25 W. A dead short at the antenna through R8 alone draws about 3.2 V / 10 Ω ≈ 320 mA, which is above the VCC_RF absolute maximum. v1-reference.md §9 says "VCC_RF provides the antenna bias"; this proposal replaces that with a limited switch (see Conflicts).

**Proposed bias tee (two-pin antenna supervisor).**

| Element | Proposal | Evidence |
|---|---|---|
| Source | +3V3_GNSS, filtered (or +5V_SYS through a filter if the antenna chosen under B-21 needs 5 V) | Manual §3.3.1: the antenna "can be supplied by VCC_RF or an external supply" that must be clean |
| Current limit | **TI TPS2553** with ILIM tied to IN: 50 / 75 / 100 mA (min / typ / max), 2 µs response, reverse-voltage protection, VIN 2.5 to 6.5 V. Typical active antennas draw 10 to 14 mA (manual Table 51 examples), so the 50 mA minimum leaves margin and the 100 mA maximum stays within the 0.1 A GNSS rail allocation ([v1-3v3-rail.md](v1-3v3-rail.md)). A higher limit (RILIM 210 kΩ: 110 / 130 / 150 mA) is available if the antenna needs it. | [TPS2553 SLVS841F](https://www.ti.com/lit/ds/symlink/tps2553.pdf) §7.3, §7.5 |
| Enable | TPS2553 EN (active high) from MAX-M10S LNA_EN, which carries ANT_OFF_N. Add a pull-down so the antenna is off in hardware backup mode, when LNA_EN is not driven. | Manual §3.2.3.4, §3.3.1.3; LNA_EN goes low in software standby |
| Short detection | TPS2553 FAULT (open drain, 7.5 ms deglitch) to a MAX-M10S PIO configured as ANT_SHORT_N, with a pull-up to V_IO. The u-blox two-pin reference uses PIO5, the EXTINT pin (CFG-HW-ANT_SUP_SHORT_PIN = 5). V1 has EXTINT only as a test pad (v1-reference.md §9), so taking it costs nothing, but it gives up EXTINT time-mark and wake functions. | Manual §B.2, Table 49 |
| Configuration | CFG-HW-ANT_CFG_VOLTCTRL = 1, SHORTDET = 1, PWRDOWN = 1, RECOVER = 1 (retests after 60 s), saved to BBR. Status is in UBX-MON-RF and `$GNTXT ANTSTATUS=` over the UART, which software can export as telemetry (v1-reference.md §21). | Manual §3.3.1.4 to §3.3.1.7, Table 22 |
| Feed | L3 27 nH (LQG15H or LQW15A class), C14 10 nF X7R to GND. R8 is optional with the limiter; keep a 0 Ω or 10 Ω footprint. | Manual §C.2 to §C.4 |

**Open-circuit detection** needs the three-pin supervisor: a comparator (LT6000 class) and two spare PIOs. The u-blox reference takes SDA and SCL and disables I2C (manual §B.2, Table 50). v1-reference.md §3 and §9 keep I2C as a secondary interface, so the three-pin version means dropping GNSS I2C. Proposal: lay out the two-pin version populated, and the comparator as DNP. Dropping I2C is an owner decision.

**RF ESD.** The project rule is no generic TVS on the GNSS RF line (v1-reference.md §9 and §30 rule 13; [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §3). The MAX-M10S data sheet gives no ESD rating for RF_IN. Its limits are ±5.5 V DC and 0 dBm RF input (Table 12), and RF_IN has an internal DC block. The proposal:

1. **Primary path:** bond the antenna connector shell and coax shield to the enclosure at the wall (§3), so discharges to the shell stay in the chassis.
2. **DNP footprint** for a shunt RF ESD device at the connector, before the bias-tee injection point. Populate it only with a part whose manufacturer datasheet gives all of the following:
   - capacitance of 0.5 pF or less. At 1575.42 MHz on 50 Ω, a shunt 0.5 pF gives about 18 dB return loss and 0.07 dB mismatch loss; 1 pF gives about 12 dB and 0.26 dB; 0.3 pF gives about 23 dB and 0.02 dB (desk calculation);
   - measured S21 or insertion loss at or near 1.575 GHz;
   - a working voltage above the antenna bias (above 3.3 V, or above 5 V for a 5 V antenna), bidirectional preferred, and leakage small next to the antenna current;
   - linearity: no harmonic or intermodulation generation from the HaLow fundamental at the antenna port (+28.5 dBm transmitter, [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §3).
   No RF ESD MPN is proposed here. Infineon's ESD0P2RF family is a candidate class to evaluate; its datasheet could not be fetched, so it is **Unverified**.
3. **Out-of-band:** keep a 0 Ω footprint for an external SAW filter between the bias tee and RF_IN, behind a 47 pF DC block (manual §C.2 C18). The MAX-M10S immunity is −17 dBm at 915 MHz and −18 dBm at 2440 MHz (manual Table 43). Whether to populate the SAW is set by the T9 and T11 tests in v1-thermal-rf-plan.md.

### 2.5 Related item outside this scope

The CM5 VBAT pin keeps its RTC: 2.5 to 3.5 V, about 6 µA when the CM5 is unpowered (CM5 datasheet Table 3 and §4.3.3 Table 9). The records specify no V1 RTC backup. A single backup source could serve both the CM5 RTC and the GNSS backup domain, and it would give host time aiding after long outages. This needs a separate Linear issue; it is not proposed here.

## 3. Chassis and shield bonding summary

Constraints already in the records:
- CHASSIS_GND is reserved, and the Ethernet shield must not go straight to digital ground without a deliberate strategy (v1-reference.md §10).
- The enclosure is aluminium and part of both the thermal and the RF design (§15, §30 rule 17; D-035). Power converters couple to the chassis through copper pours and thermal vias (v1-selections.md, "PCB and thermal approach").
- External RF uses wall connectors (§19). [maer-capabilities.md](../requirements/maer-capabilities.md) asks for grounded shields and deliberate cable bonding.

Proposed strategy (candidate):

1. **The enclosure is the shield reference.** Every cable shield and connector shell bonds to the enclosure at the wall: the Ethernet feed-through, both USB4720-03-A shells, the HaLow, Wi-Fi and GNSS RF bulkheads, and the pack-interface frame if it is metal. These bonds are 360° where the connector allows it.
2. **Logic GND bonds to the chassis on purpose, at chosen points.** RF bulkhead coax shields are logic and RF ground, so mounting them in the wall already bonds GND to the chassis. Any thermal contact made without an insulating pad does the same. This proposal makes those bonds deliberate: low-inductance GND-to-chassis contacts at the RF connector wall and at the power island's thermal contact, plus the M3 fixings if they are plated. A fully isolated CHASSIS_GND is not achievable while the RF connectors sit in a metal wall.
3. **The Ethernet line side stays isolated.** Its only path to the chassis is the Bob Smith capacitor (§1.3). No logic ground is placed in the line-side region. The PHY-side ESD array returns to logic GND, which the bonds in point 2 tie to the enclosure. Raspberry Pi's reference ties the MagJack shield straight to GND (CM5 datasheet Figure 2); V1 instead bonds the feed-through shell to the wall.
4. **No cable shield lands on the board through the Pico-Lock header** (§1.4).
5. Validate with the existing plans: Ethernet ESD and shield behaviour (v1-reference.md §27), and a near-field scan for common mode on the Ethernet cable near the GNSS antenna (v1-thermal-rf-plan.md T8).

## Conflicts and gaps found (not changed here)

Per [../README.md](../README.md) rule 6, these need Linear issues or an owner decision. None is resolved in this file.

1. **Magnetics height and footprint against D-025 and v1-reference.md §18.** Common gigabit modules are 6 to 9 mm tall (the Würth part checked is 8.8 mm), against a limit of 3.5 mm or less. The only low-profile leads found (HX5120NL, 16.5 x 9.1 mm; ALANL10001, 19.8 x 16.6 mm) are **Unverified** and larger than the 14 x 9 mm placeholder. Owner: GHO-7 and GHO-11.
2. **Antenna bias source.** v1-reference.md §9 states "VCC_RF provides the antenna bias". This proposal recommends a current-limited switch, because a short through the u-blox example network exceeds the VCC_RF absolute maximum (250 mA).
3. **GNSS I2C against open-antenna detection.** The three-pin supervisor uses the SDA and SCL PIOs, which conflicts with I2C being a listed GNSS interface (§3, §9).
4. **CHASSIS_GND "reserved" against actual bonding.** RF bulkheads in the aluminium wall and the thermal path of converters to the chassis already bond GND to the chassis. The "deliberate strategy" in §10 has to say so.
5. **No Ethernet surge requirement.** Neither the records nor D-028 give an IEC 61000-4-5 level or a cable-length assumption for the Ethernet port.
6. **The Pico-Lock header has no spare pin** for shield or chassis. v1-reference.md §10 says "any extra pins are chassis or shield only", but all eight are MDI.
7. **Stale cross-reference.** [v1-stackup-routing.md](v1-stackup-routing.md) §4 says its 0.15 mm MDI intra-pair match is "tighter than the 1 mm in v1-reference.md section 10", but §10 now says 0.15 mm.
8. **No V1 RTC backup** for the CM5 (§2.5). It is not tracked in the records.

## What this does not verify

- The Pulse HX5120NL and Abracon ALANL10001 figures come from distributor or search listings. Their datasheets could not be fetched.
- Semtech RClamp0524P specifications and status come from search snippets. The Semtech site blocked the download.
- The IEEE 802.3 return-loss mask and isolation test text were not fetched. The capacitance limits are first-order calculations.
- The BCM54210PE datasheet is not public. PHY common-mode level, CT handling and pin ESD rating rest on Raspberry Pi's CM5 reference figure.
- No supercapacitor, RF ESD diode, SAW filter or GNSS antenna connector MPN is proposed. Their leakage, aging, S21 and fit are open.
- Supercapacitor hold times use the typical 28 µA backup current at 25 °C and ignore capacitor leakage.
- The Amphenol feed-through's shield path to the panel was not checked against its drawing.
- Nothing was simulated, built or measured.

## Primary references

- [Raspberry Pi CM5 datasheet](https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf), Release 3, build 08/06/2026: §2.2.1 and Figure 2, Table 3, Table 4.
- [u-blox MAX-M10S data sheet UBX-20035208 R08](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf): Tables 2, 12, 13, 17.
- [u-blox MAX-M10S integration manual UBX-20053088 R05](https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf): §3.3.1, §3.6.3, §4.1.3, §4.3, §B.2, §C.
- [TI TPD4EUSB30, SLVSAC2G](https://www.ti.com/lit/ds/symlink/tpd4eusb30.pdf); [TI TPD4E05U06, SLVSBO7O](https://www.ti.com/lit/ds/symlink/tpd4e05u06.pdf); [TI TPD4E1U06, SLVSBQ9D](https://www.ti.com/lit/ds/symlink/tpd4e1u06.pdf).
- [TI TPS2553, SLVS841F](https://www.ti.com/lit/ds/symlink/tps2553.pdf).
- [Nexperia PESD2ETH1G-T](https://assets.nexperia.com/documents/data-sheet/PESD2ETH1G-T.pdf); [Nexperia PESD2ETH1GXT-Q](https://assets.nexperia.com/documents/data-sheet/PESD2ETH1GXT-Q.pdf).
- [Würth Elektronik 7490220122](https://www.we-online.com/components/products/datasheet/7490220122.pdf).
