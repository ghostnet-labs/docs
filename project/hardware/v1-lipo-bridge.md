# V1 pack-swap bridge: internal 2S LiPo (GHO-38)

**Owner:** [GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38), the bridge that carries the radio across a pack change.
**Status:** Selected by D-053 in [../decisions.md](../decisions.md), 2026-11-06 (Justin's choice). B-24 in [v1-selections.md](v1-selections.md) owns the selection and wins over this file (README rule 6). This file holds the design, the numbers behind it and the bench gates that can still change it. The requirement study and the options that were compared are in [v1-hot-swap-bridge.md](v1-hot-swap-bridge.md).

Requirements used: D-008 (swap without reboot), D-027 (full node and mesh links for at least 10 s, no deliberate load reduction) and D-028 (−17.8 to +43.3 °C ambient, no throttling). The sizing load is the bridge study's 25 W held through the gap, with a 5 W × 10 s shutdown reserve on top (334 J at 90 % efficiency).

## Conventions

- **Verified:** read from the source in [Sources](#sources) on 2026-11-06.
- **Calculated:** derived here. The arithmetic is shown. Nobody has measured it.
- **Unverified:** an assumption or a value not checked against a primary source. Each one is listed in [What remains unverified](#what-remains-unverified).

## Summary

| Item | Selection | Basis |
|---|---|---|
| Architecture | A 2-series Li-ion cell on the held-up bus (+VBUS_HOLD) behind an ideal-diode switch. No boost converter. | The pack bus is 8.4 to 12.6 V (B-11). A 2S cell held at 7.60 V stays below it, so it idles while a pack is in and takes over the moment the bus falls below it. |
| Cell | 2S1P, 300 mAh nominal, high-rate (≥ 15C continuous) Li-ion pouch pack with NTC and balance lead, rated to discharge at 80 °C or more | MPN open (Unverified). The interior runs hot at the D-028 endpoint (§4). A standard hobby LiPo (discharge to about 60 °C) is acceptable only for the bench prototype. |
| Float voltage | **7.60 V** (3.80 V per cell, about half charge), 7.40 V (3.70 V per cell) while the cell reads 60 °C or more | Low state of charge slows calendar ageing in a warm body. |
| Charger | **Analog Devices LTC4121** (synchronous buck, 4.4 to 40 V in, 50 to 400 mA, float programmable 3.5 to 18 V, NTC-qualified charging, 3 × 3 mm QFN-16, −40 to 125 °C), set to 200 mA | Verified (ADI product summary). Fed from the pack side ahead of the eFuse, so it never charges the cell from itself during a swap. |
| Path switch | **TI LM7480x-Q1** ideal-diode controller with two back-to-back 40 V N-FETs (**TI CSD18512Q5B**, the part already in the BOM) | 3 to 65 V, 0.5 µs reverse turn-off, EN/UVLO for disconnect (Verified, TI product page). Blocks the pack from back-feeding the cell; disconnects the cell for shipping, over-temperature and under-voltage. LM74800-Q1 versus LM74801-Q1 is chosen at schematic. |
| Cell protection | Independent 2-cell protector with its own FETs, a 2-cell balancer and a 7.5 A fuse at the cell | Second cut-off for over-charge, over-discharge and short circuit. Parts Unverified. |
| Monitoring | I²C current/voltage monitor on the LiPo leg, cell NTC to the charger, a second temperature sensor read by firmware | Proposed. The INA228 (B-14) keeps its place on the pack side; what it measures in the charger-first path is open ([v1-schematic-netplan.md](v1-schematic-netplan.md) K-5). |
| Ride-through at 25 W | **≈ 140 s** fresh at 25 °C, ≈ 100 s at end of life, ≈ 50 s cold-soaked at −20 °C | Calculated (§2), against D-027's 10 s |
| Placement | Bottom bay next to the pack interface, bonded through a thermal pad to a side wall, 2 mm foam toward the carrier, 10 % swell gap | §4. Enclosure model v6 places it above the pogo daughterboard. |
| Mass and cost | About 30 g with its board; about $35 in parts | Estimate (Unverified) |

## 1. Power path

Pack contacts (VBAT_PACK) → BQ25798 BAT to SYS → TVS, Q1 and TPS26633 eFuse → INA228 shunt → **+VBUS_HOLD** → both LM76005 bucks.

LiPo (+ fuse and protector) → back-to-back FETs under LM7480x control → **+VBUS_HOLD**.

LTC4121 input from the charger's SYS output (ahead of the eFuse) → LiPo.

| Item | Behaviour |
|---|---|
| Pack in | +VBUS_HOLD sits at the pack voltage less the eFuse and shunt drops, 8.3 V or more above cutoff. The LM7480x sees the cell below its output and holds the FETs off. The cell carries nothing. |
| Pack out | The eFuse and Q1 block reverse current, so the cell never feeds the pogo contacts or the charger. +VBUS_HOLD falls until the LM7480x forward-biases, then rides at the cell voltage less the path drop: about 7.3 V at 25 W (§2). Both bucks and the supervisor stay up. |
| Pack back in | The eFuse ramps on its existing C_dVdT. When its output rises above the cell, the LM7480x turns off and load moves back to the pack. The charger restores the swap energy in about 4 minutes. |
| Near-empty pack | If the pack bus sags under the cell voltage before a swap, the cell shares load until the pack is replaced. The charger refills it afterwards. |
| Bucks' EN and SVS4 | Unchanged from D-044: EN from a divider on +VBUS_HOLD, SVS4 at 6.0 V on +VBUS_HOLD. Both sit below the 6.4 V cell cut-off, so a swap never resets the CM5. |

### Detection signal for software

| Signal | Source | Use |
|---|---|---|
| BRIDGE_ACTIVE_N | Comparator on VBAT_PROTECTED (pack side of the bridge junction), tripping at about 7.75 V falling | Primary. Start the swap timer and flush logs. GPIO allocation stays with GHO-13 ([v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md)). |
| PACK_PRESENT | Pack contact (M-11) | Tells a pulled pack from a pack at cutoff. |
| INA228_ALERT_N | Bus under-voltage limit | Backup. |
| LiPo voltage, current, temperature | LiPo-leg monitor and sensor over I²C | Remaining ride-through, health, clean shutdown when the cell reaches the reserve. |

Software policy (proposal): with BRIDGE_ACTIVE_N low and PACK_PRESENT gone, enter swap mode; if the cell falls to the reserve level (6.6 V under load, Proposed) before a pack returns, run a clean shutdown. The LM7480x UVLO at 6.4 V is the hardware floor.

## 2. Sizing (Calculated)

- **Current:** 25 W / 0.97 path efficiency / 7.3 V = **3.5 A**, about 12C on 300 mAh. A 15C or higher continuous rating leaves margin for cold and age.
- **Bus during a swap:** 7.60 V − 3.5 A × (pack ESR 60 mΩ + two FETs 4.6 mΩ + fuse and wiring 15 mΩ) ≈ **7.32 V**. Pack ESR is an assumption for a 300 mAh high-rate cell (Unverified).
- **Energy held:** 2 × 3.7 V × 0.30 Ah = 2.2 Wh. From 3.80 V to 3.40 V per cell under load a typical Li-ion curve gives about 45 % of capacity (Unverified curve), so about **1.0 Wh = 3,600 J** usable.
- **Ride-through:** 3,600 J × 0.97 / 25 W ≈ **140 s** fresh. At 70 % end-of-life capacity about **100 s**. Cold-soaked at −20 °C, allowing half the capacity and three times the resistance (bus ≈ 6.9 V), about **50 s**. Each is at least 5 × D-027's 10 s plus the 56 J shutdown reserve.
- **Charge:** one 10 s swap at 25 W takes about 290 J. At 200 mA into 7.6 V (1.5 W) that returns in about 3 to 4 minutes. A full charge from 3.40 to 3.80 V per cell takes about 40 minutes.
- **Swaps per charge:** 3,600 J / 290 J ≈ 12, so about 10 back-to-back swaps with margin. Charging can wait for a cool period (§4).
- **Why not a capacitor:** at 25 W the capacitor options are limited by the power lost in their internal resistance at low voltage, not by stored energy. See [v1-hot-swap-bridge.md](v1-hot-swap-bridge.md) §3.

## 3. Charger settings

- **Float:** LTC4121 feedback divider for 7.60 V. A small FET across one divider resistor drops it to 7.40 V when firmware reads 60 °C or more on the cell (Proposed).
- **Current:** 200 mA (RPROG), inside the 400 mA maximum.
- **Temperature window:** NTC set to allow charging only between 0 and 45 °C cell temperature (typical Li-ion charge window; confirm against the chosen cell's datasheet).
- **Input:** from the charger's SYS output, so USB-C power can also keep it topped up with no pack fitted.

## 4. Heat and cold

The thermal model that predated D-053 ([v1-thermal-update-tray.md](v1-thermal-update-tray.md)) puts internal air at 77 to 87 °C at the 43.3 °C D-028 endpoint and about 50 °C case temperature at the 21.1 °C nominal ambient. Its geometry is no longer current (GHO-12 reruns it for D-053 and D-054), but it shows the scale of the problem: a normal Li-ion cell would sit above its discharge limit on a hot day and above its charge limit most of the time.

The design answers this five ways:

1. **Hot-rated cell.** Specify a cell rated to discharge at 80 °C or more (high-temperature Li-ion, the class used for vehicle telematics backup). This is the main sourcing risk (Unverified).
2. **Coolest spot.** The bottom bay next to the pack interface, away from the CM5, Wi-Fi card and bucks, with the cell bonded to a side wall through a thermal pad and 2 mm of foam toward the carrier.
3. **Fins if needed.** External fins on that wall. Justin accepted adding heat sinks to the enclosure (thread, 2026-11-06).
4. **Low charge level.** 3.80 V per cell, dropping to 3.70 V at 60 °C or more.
5. **Charge only when cool.** The NTC blocks charging above 45 °C. With about 10 swaps stored, the cell can wait for a cooler period, a lighter load or the node being off.

Cold: discharge works to −20 °C with reduced capacity (§2). Charging is blocked below 0 °C; the running node warms its interior well above that. The cold-soaked ride-through is still about 50 s.

Swelling: leave a 10 % thickness gap over the pouch and no rigid clamp across its faces.

## 5. Health and service

- **Monthly self-test (Proposed):** firmware turns the eFuse off for 2 s so the cell carries the real load, logs the sag and the energy drawn, and aborts at 6.6 V.
- **Replace when:** capacity falls below 70 % of new, or the self-test sag at a given load grows by more than an agreed limit.
- **Service:** depot-replaced on a small keyed connector. Not a field operation.
- **Shipping:** the radio body ships as equipment containing a lithium-ion battery of about 2.2 Wh; the main pack is declared as before. Confirm the shipping class with the chosen cell's test summary (Unverified).

## 6. Removed by D-053

LTC3350 controller, six KYOCERA AVX SCCV60B107SRB cells, the bank board and fuse, the Bourns SRP1265A-4R7M inductor, RSNSC and RSNSI, two CSD18514Q5A switch FETs, the ballast resistors, the WR-MPC4 harness and the bridge tray (D-047, D-048; R-29). That frees about 170 g and the 408 mm² top-side stage area at board X 119.5 to 136.5, Y 36 to 60.

## Bench gates

| Gate | Measure | Pass | If it fails |
|---|---|---|---|
| L1 | **GHO-30:** full-node plus accessory power at +VBUS_HOLD, highest 10 s mean, at the D-028 endpoints | Cell current within its continuous rating at that load | Larger or higher-rate cell |
| L2 | **GHO-30:** clean-shutdown energy and time | Fits the reserve above the 6.4 V floor | Raise the reserve level |
| L3 | Gloved swap time, 95th percentile | Under the cold, end-of-life ride-through (about 50 s) | Larger cell |
| L4 | Pack pull at full load, fresh and aged cell, at 25 °C, −18 °C cold-soaked and the hot endpoint | No reset, no mesh-link interruption; +VBUS_HOLD stays above 6.4 V; log sag and temperature | Lower-resistance cell |
| L5 | Cell temperature in place, sealed, at the hot endpoint and full load (GHO-23 T3/T4) | Within the chosen cell's discharge rating | Fins, more insulation, or move the cell |
| L6 | Charge behaviour at nominal and hot ambient | Charges only inside the NTC window; float steps to 7.40 V at 60 °C | Adjust the NTC network |
| L7 | Pack reinsertion during a swap | Clean handover, no eFuse trip | Adjust eFuse ramp |
| L8 | Ten swaps in a row, 30 s apart, at full load | All ride through | Larger cell |
| L9 | Leave the pack out | Clean shutdown at the reserve; file system checks clean | Raise the reserve level |
| L10 | Shipping mode and over-temperature disconnect | The LM7480x opens the path; standby drain within budget | Fix EN logic |

## What remains unverified

- The cell itself: MPN, discharge temperature rating, resistance, rate and cycle life. No catalogued hot-rated 2S 300 mAh part has been checked.
- The 2-cell protector, balancer, LiPo-leg monitor and connector parts.
- The Li-ion discharge curve used for usable energy (45 % between 3.80 and 3.40 V per cell) and the cold factors.
- LTC4121 suitability for a 2-series stack at 7.60 V float (the summary gives a 3.5 to 18 V programmable float; the multi-cell application circuit was not read).
- Interior temperatures for the D-054 body (GHO-12).
- Mass and cost estimates.

## Sources

- Analog Devices LTC4121 product summary (40 V, 400 mA synchronous buck battery charger): https://www.radiolocman.com/news/new.html?di=153457 and https://analog.com/en/ltc4121
- TI LM7480-Q1 product page (LM74800-Q1 / LM74801-Q1): https://www.ti.com/product/LM7480-Q1
- TI CSD18512Q5B: already selected in the BOM (see [v1-bom-baseline.md](v1-bom-baseline.md))
- 2026-11-06 option comparison page: https://claude.ai/artifact/DwjF5BbcKvso6AtsjvtgMR
