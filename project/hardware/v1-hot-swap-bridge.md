# V1 hot-swap bridge sizing

**Owner:** [GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38) (was Q-10): size the bridge energy that carries the radio across a pack change (D-008)  
**Status:** Requirement and option study. D-027 sets the operating mode and time; D-028 sets the temperatures. D-053 selected the internal 2S LiPo bridge; B-24 in [v1-selections.md](v1-selections.md) owns the selection and [v1-lipo-bridge.md](v1-lipo-bridge.md) owns its design. GHO-38 stays open for the measured full-node load and the bench gates there.

D-008 says the main pack must swap without rebooting the radio. This file sizes the energy for that and compares the ways to store it. The selected design and its power path are in [v1-lipo-bridge.md](v1-lipo-bridge.md).

Every number marked **(est.)** is an estimate. Track A figures are also estimates until GHO-30 measures them.

## Result

| Item | Result |
|---|---|
| What it must cover | D-027 at the measured full-node load, with no swap-mode performance reduction, plus a shutdown reserve. Sizing case: 25 W for 10 s plus 5 W for 10 s, 334 J at 90 % efficiency (§2) |
| Selected | Internal 2S Li-ion cell on +VBUS_HOLD behind an ideal-diode switch (D-053, [v1-lipo-bridge.md](v1-lipo-bridge.md)) |
| Why not capacitors | At 25 W every capacitor bank that fits is limited by power lost in its own resistance at low voltage, not by stored energy (§3) |
| Required changes, any bridge | Bucks' EN and supervisor SVS4 follow +VBUS_HOLD, not the eFuse output, or the node resets mid-swap (D-044) |

## 1. Load during the gap

Track A estimates about 10 W typical and under 15 to 18 W peak for the whole node ([v1-reference.md](v1-reference.md) section 14). These are input-side figures, so regulator losses are already inside them.

| Option | What runs during the swap | Load | Source |
|---|---|---:|---|
| (a) Full node | CM5, Wi-Fi, HaLow, GNSS; mesh links stay up | 10 W typical, 18 W peak; 12 W used for sizing (est.) | Track A estimate, section 14 |
| (b) Radios off | CM5 idle, radio load switches U302 and U303 off, GNSS on | 4 to 5 W, 5 W used (est.) | Not measured anywhere yet |
| (c) Shutdown only | CM5 runs a clean `poweroff` and stops | 5 W for about 10 s (est.) | OpenWrt shutdown time not measured |

Option (a) keeps the mesh links. Option (b) keeps the CM5 running (no reboot, so D-008 is met literally) but the radios drop and must reassociate after the swap, which takes seconds. Option (c) does not meet D-008; it only avoids file system damage.

The table above is a historical low-load sensitivity case, not the V1 sizing basis. The AW7916-AED thermal budget now estimates about 16 W typical and 25 W peak (v1-thermal-rf-plan.md §1). D-027 does not permit a swap-mode TX-power cap. Recalculate against actual node plus external accessory load, regulator losses and transient demand.

## 2. Swap time and energy

The pack is hook-first, latch-end-second, glove-operable and tool-free ([v1-battery-pack.md](v1-battery-pack.md)). A practiced swap is probably 3 to 6 s; a gloved swap in the field 10 s or more (est.). The minimum is owned by D-027. The 5 s column is sensitivity only, not an acceptable requirement; gloved swap trials may justify a larger design interval, never reduce the minimum.

Energy drawn from storage: E = P x t / efficiency, with 0.9 for a boost holdup controller (est.).

| Load | 5 s | 10 s | 20 s |
|---|---:|---:|---:|
| (a) 10 W typical | 56 J | 111 J | 222 J |
| (a) 12 W sizing | 67 J | 133 J | 267 J |
| (a) 18 W peak | 100 J | 200 J | 400 J |
| (b) 5 W | 28 J | 56 J | 111 J |
| (c) shutdown, 5 W for 10 s | 56 J | 56 J | 56 J |

Design energy, adding a shutdown reserve (56 J) so the node can still stop cleanly if the operator does not refit a pack in time, and allowing 20 % capacitance loss at end of life:

| Option at 10 s | Swap + reserve | New capacitor must hold |
|---|---:|---:|
| (a) | 133 + 56 = 189 J | 236 J |
| (b) | 56 + 56 = 112 J | 140 J |
| (c) | 56 J | 70 J |

### Revised full-load energy check

These are estimates, not measured acceptance. Using the same 90% conversion efficiency, 56 J shutdown-reserve estimate and 20% capacitance-loss allowance:

| Load scenario | Swap energy | Swap plus reserve | Required new usable energy |
|---|---:|---:|---:|
| 16 W typical estimate | 178 J | 234 J | 293 J |
| 25 W peak held throughout gap | 278 J | 334 J | 417 J |
| 35 W capability stress case, not expected consumption | 389 J | 445 J | 556 J |

The energy comparison is necessary but insufficient: controller/inductor/FET current, ESR voltage drop and discharge floor must also pass at the same load. The reserve must be replaced with measured shutdown energy; the existing 5 W assumption is unverified. Include temperature, initial charge and repeated-swap conditions in the calculation.

### Reproducible conditional budget

Run [bridge_budget.py](../scripts/bridge_budget.py) with explicit worst-case or measured inputs. It screens capacitance, initial charge, whole-stack ESR, conversion loss, the effective average stack-current ceiling, gap load/time and an additional shutdown reserve. It never selects a controller or declares hardware qualification. Inputs at the held-up bus must include downstream regulator and accessory demand.

The current ceiling is **average current the complete converter can sustain**, after ripple/inductor/sense/FET/thermal margins. Do not copy the LTC3350 peak inductor limit into this input: manufacturer Rev. D, *Minimum VCAP Voltage in Backup Mode* (printed pp24–25) also requires ESR/power-transfer, peak-current and duty-cycle analysis. Converter minimum terminal voltage must incorporate duty cycle, UVLO and regulation headroom; no 3.5 V floor is implied by the tool.

Model: identical series cells give effective stack capacitance `Ccell × derating / N`. With converter input power `P = Pload / efficiency`, terminal floor is the maximum of converter minimum, `P / Iaverage_max` and `sqrt(P × ESR)`. Open-circuit floor adds `P × ESR / Vterminal`. Usable energy is `0.5 × Cstack × (Vinitial² - Vfloor²)`. The draw bound includes maximum `I² × ESR` heating over that window. Efficiency excludes the separately modeled stack ESR (including it again is conservative). The larger of operating and shutdown load sets the common floor; that conservatively reserves shutdown energy without assuming deeper discharge is available.

The 2026-11-06 capacitor runs and their inputs are in §3. Save JSON with the source/evidence for every input; replace estimates as GHO-30 produces measurements. Equality at the ESR maximum-power boundary offers no design margin.

Run verification with `python3 -m unittest discover -s project/tests -p 'test_bridge_budget.py' -v`. Tests cover hand-calculated energy, series capacitance, current floor, ESR penalties, shutdown demand, low charge and invalid inputs; an independent numerical constant-power discharge checks the conservative duration bound.


## 3. Options compared (2026-11-06)

All rows use the §2 sizing case at end of life. Capacitor rows are `bridge_budget.py` runs (inputs below); the others are estimates. The visual comparison, drawn to scale in the enclosure, is the [hot-swap bridge options page](https://claude.ai/artifact/DwjF5BbcKvso6AtsjvtgMR).

| Option | Size inside the body | Bridge mass (est.) | Ride-through at 25 W | Cold | Heat | Outcome |
|---|---|---:|---|---|---|---|
| A. LTC3350 + 6 × KYOCERA AVX SCCV60B107SRB (100 F, Ø18 × 60) as 3S2P | 138 × 67 × 19 mm tray, +23 mm body depth | 170 g | Duration bound 12.9 s, +42.1 J margin at −20 °C | Rated −40 °C | 85 °C at ≤ 2.3 V per cell; tray model put cells at 75 to 82 °C | Retired (R-29) |
| B. Same with 6 × SCCV40B506SRB (50 F, Ø18 × 40) | Same 19 mm layer | 115 g | 6.2 s, −191.2 J; still −23.8 J at 16 W | Rated −40 °C | As A | Fails D-027 |
| C. Same controller with 6 × Taiyo Yuden LIC1840RH3R8107 lithium-ion capacitors (100 F, 3.8 V, Ø18 × 40) as 2S3P at 7.0 V | Same 19 mm layer, about 25 % shorter | 150 g | 21.1 s, +310.8 J warm; no usable energy cold-soaked | At −25 °C capacitance may fall to 60 % and resistance rise to 10 × (Taiyo Yuden limits) | +105 °C at 3.5 V (RH series) | Not chosen: little space saved, fails cold |
| D. Internal 2S 300 mAh Li-ion on +VBUS_HOLD, no boost | About 25 cm³ | 30 g | About 140 s (100 s aged, 50 s cold-soaked) | Discharges to −20 °C; charges above 0 °C | Needs a hot-rated cell and a cool mounting spot | **Selected (D-053)** |
| E. Two half packs, swap one at a time, no bridge | None | Net about −135 g | Unlimited | As the main pack | Nothing stored in the body | Rejected (R-28) |
| F. Plug in USB-C or vehicle power during the swap | None | 0 g | Unlimited while connected | Depends on the source | Nothing new | Not compliant alone: needs a source on hand |

Rejected before 2026-11-06 and unchanged: a supercapacitor bank floating directly on the input bus (5 × 125 F, and the eFuse would recharge it in current limit until thermal shutdown); rail-level holdup on +5V_SYS only (LTC4041 or TPS61094, which cannot carry the radios, R-20); and no bridge (about 13 mJ of bulk capacitance, about 1 ms at 10 W).

### Capacitor screening inputs

Common: `--efficiency 0.9 --gap-s 10 --shutdown-w 5 --shutdown-s 10 --average-current-a 7.94 --load-w 25` (7.94 A was the A design's average backup ceiling with a 6 mΩ charge sense resistor).

| Row | Arguments |
|---|---|
| A | `--cells 3 --cell-f 200 --capacitance-factor 0.5922 --stack-esr-ohm 0.1011 --start-v 6.394 --terminal-min-v 3.5`: initial −10 %, end of life 70 %, −20 °C 94 %; cell 18 mΩ × 2 × 1.55, plus 17.4 mΩ path |
| B | As A with `--cell-f 100 --stack-esr-ohm 0.1104` (20 mΩ cells) |
| C warm | `--cells 2 --cell-f 300 --capacitance-factor 0.56 --stack-esr-ohm 0.1507 --start-v 6.86 --terminal-min-v 4.6`: ±20 % tolerance, end of life 70 %, DC resistance under 100 mΩ doubled at end of life, 2.3 V per cell floor |
| C cold | As C warm with `--capacitance-factor 0.336 --stack-esr-ohm 1.351` (Taiyo Yuden −25 °C limits) |

The binding term in B and C is resistance: the bank must deliver about 28 W at 4 to 7 V, so tens of milliohms cost more energy than the extra capacitance adds. A Li-ion cell of the same volume has a few tens of milliohms at 7 V and stores about ten times the energy.

## 4. Power path

The selected path, detection signals and software policy are in [v1-lipo-bridge.md](v1-lipo-bridge.md) §1. The pack-side parts (BQ25798, TVS, Q1, TPS26633 eFuse, INA228 and its shunt) are unchanged. What the INA228 measures in the charger-first path is open ([v1-schematic-netplan.md](v1-schematic-netplan.md) K-5). With USB-C power present, the charger keeps SYS up with no pack, so a swap while charging does not draw on the bridge.

## Requirement compliance

| Option | What it means | Cost |
|---|---|---|
| A. Full-node ride-through (required) | Input-bus bridge sized for full load: the internal LiPo (D-053) | About 30 g |
| B. CM5-only ride-through | Rail-level holdup on +5V_SYS with radios off; links drop and reassociate | Not compliant (R-20) |
| C. Shutdown on removal | Smallest storage for a clean `poweroff` only | Revises D-008 |

D-027 settles the operating-mode and time choice: only A is compliant.
