# V1 hot-swap bridge sizing

**Owner:** [GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38) (was Q-10): size the bridge energy that carries the radio across a pack change (D-008)  
**Status:** Engineering candidate study. The operating-mode/time requirement is settled by D-027; the thermal requirement is D-028. B-24 in [v1-selections.md](v1-selections.md) owns the candidate selection. GHO-38 remains open for measured full-node load, current-capability analysis, end-of-life/temperature derating and mechanical fit. No component population is frozen.

D-008 says the main pack must swap without rebooting the radio. This file sizes the energy for that, compares the ways to store it, and lists what changes in the power path ([v1-reference.md](v1-reference.md) sections 11 to 14 and 22).

Every number marked **(est.)** is an estimate. Track A figures are also estimates until GHO-30 measures them.

## Result

| Item | Recommendation |
|---|---|
| Architecture | Analog Devices LTC3350 supercapacitor backup controller between the eFuse output and the regulators, creating a held-up bus (+VBUS_HOLD) |
| Evaluated population (not frozen) | Working default 3S2P SCCV60B107SRB at 6.525 V (D-047); see [v1-bridge-selection.md](v1-bridge-selection.md). |
| What it must cover | D-027 at the measured full-node load, with no swap-mode performance reduction; a shutdown reserve is additional (estimate below) |
| Smaller population | Not a compliant fallback if it requires radios off; alternatives must still satisfy D-027 |
| Detection | LTC3350 PFO plus the pack's PACK_PRESENT contact to CM5 GPIOs; INA228 bus undervoltage alert as a backup |
| Required changes | Bucks' EN and supervisor SVS4 move from the eFuse output to +VBUS_HOLD (otherwise the node resets mid-swap) |

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

Use the source-grounded candidate comparison below for current inputs and exact commands. Save JSON with the source/evidence for every input; replace estimates as GHO-30 produces measurements. Equality at the ESR maximum-power boundary offers no design margin.

Run verification with `python3 -m unittest discover -s project/scripts -p 'test_bridge_budget.py' -v`. Tests cover hand-calculated energy, series capacitance, current floor, ESR penalties, shutdown demand, low charge and invalid inputs; an independent numerical constant-power discharge checks the conservative duration bound.

## 3. Storage options

### S1. Supercapacitor bank directly on the input bus

Usable energy is ½C(V1² − V2²) down to the eFuse UVLO falling threshold, V2 = 7.43 V. A bank on the bus floats at pack voltage, so V1 is whatever the pack is at when it is removed, and operators swap packs when they are nearly empty. Pack cutoff is 2.8 to 3.0 V per cell, 8.4 to 9.0 V.

| V1 (pack at removal) | Usable energy per farad | C for 189 J |
|---:|---:|---:|
| 12.6 V (full, rare) | 51.8 J/F | 3.6 F |
| 9.0 V | 12.9 J/F | 14.7 F |
| 8.4 V (at cutoff) | 7.7 J/F | 24.6 F |

The stack must be rated above 12.6 V, so 5 cells of 2.7 V (13.5 V) with balancing; 24.6 F means 5 x 125 F cells, roughly 5 x 18 x 60 mm (est.), the largest option here. It also breaks the eFuse: after a swap the eFuse would recharge many farads in current limit (5.56 A, about 5 V across a 4 x 4 mm QFN, about 15 W average for several seconds), which trips thermal shutdown. **Rejected.**

### S2. Supercapacitor stack behind a backup controller on the input bus (recommended)

The LTC3350 (VIN 4.5 to 35 V, 1 to 4 series cells, step-down CC/CV charging, step-up backup, input and output ideal-diode controllers, PFI/PFO power-fail comparator, internal balancers, 14-bit ADC with capacitance and ESR measurement over I2C, 38-lead 5 x 7 mm QFN; [datasheet Rev. D](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc3350.pdf)) charges the stack from the eFuse output and boosts it back onto +VBUS_HOLD when the input fails.

Charge voltage: the charger is step-down only, and its output ideal diode turns on whenever +VBUS_HOLD falls 65 mV below the stack. If the stack sat above the lowest pack voltage (8.4 V), it would discharge into the load whenever the pack ran low. So the stack is held at **6.525 V, 2.175 V per cell, three cells** with the VCAP DAC ([v1-bridge-selection.md](v1-bridge-selection.md) §1). That is well under the 2.7 V cell rating, which helps life in a warm sealed enclosure, and the datasheet suggests raising the DAC as cells age to keep stored energy constant (code 13, 6.75 V, at end of life; D-047).

### Source-grounded cell/controller comparison (2026-10-04)

B-24 remains a candidate architecture. This comparison advances GHO-38/GHO-10; it does not select parts or replace measured load and CAD review.

**Controller evidence:** [LTC3350 Rev. D](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc3350.pdf), Electrical Characteristics (printed pp4–5), *Setting Input and Charge Currents* (p21), *Low Current Charging and High Current Backup* (p22), *Minimum VCAP Voltage in Backup Mode* (pp24–25), and *Inductor Selection* (pp26–27): charge sense is nominal 32 mV; peak-inductor sense is 51/58/65 mV minimum/typical/maximum, not an average-current specification. At RT = 107 kΩ, frequency minimum is 490 kHz. Step-up maximum-duty capability has an 87% minimum and 93% typical value at TA = 25°C under the table conditions; that row has no temperature-range dot, so these values do not establish guaranteed duty capability across D-028's ambient endpoints. Saturation and copper losses require separate checks.

For a conditional 7 V boost, 3.3 µH nominal with −20% inductance, and ±1% sense resistance, ideal continuous-conduction ripple is ΔI = Vcap(1 − Vcap/7)/(L × f). Its maximum below 7 V is 7/(4 × 2.64 µH × 490 kHz) = 1.353 A. Subtracting half this ripple from the minimum peak threshold gives the following **screening ceilings**, before extra saturation, conduction, control/transient and thermal margins:

| RSNSC candidate | Minimum-threshold peak | Conditional average ceiling | Maximum-threshold peak for component stress |
|---|---:|---:|---:|
| 10 mΩ ±1% | 5.050 A | 4.373 A | 6.566 A |
| 5 mΩ ±1% | 10.099 A | 9.423 A | 13.131 A |

This calculation is an ideal-model inference, not a guaranteed converter rating. The earlier 5.8 A number was nominal peak current and must not be entered as sustainable average current. At that 25°C table condition, the ideal duty-only floor is 7 × (1 − 0.87) = 0.91 V, but losses, UVLO and buck regulation headroom raise the real floor; duty capability at temperature and operating corners still needs validation, and the 3.5 V value below remains unverified. A 5 mΩ choice requires a new inductor/FET/shunt/layout review; the earlier ≥8 A saturation estimate is insufficient against the possible peak. Charge setting would nominally become 6.4 A, so RSNSI/input-power management must restrict recharge while maintaining full-node demand. At 9 A, a 5 mΩ shunt alone dissipates about 0.405 W.

**Cell evidence:** [KYOCERA AVX SCC, TDS-SC-0001 Rev 11](https://datasheets.kyocera-avx.com/AVX-SCC.pdf), printed p2 rating/life tables and p4 drawings: the two 100 F parts below have +30/−10% initial tolerance. Qualification limits use ≥70% capacitance and ≤200% ESR. For conservative screening, combine initial minimum with that retention as 0.9 × 0.7 = 0.63 of nominal C; use twice maximum DC ESR at 5 s, rather than the smaller 1 kHz figure. Those test limits are not a service-life guarantee or cold-temperature bound.

| Candidate population | Series-group nominal C | Whole-bank screening ESR | Maximum single-body envelope D × L | Total body cylinder volume / flat bounding area |
|---|---:|---:|---:|---:|
| 4 × SCCV60B107SRB, radial | 100 F | 0.144 Ω | 19 × 62 mm | 70.3 cm³ / 4,712 mm² |
| 4 × SCCW45B107SSB, solder pin | 100 F | 0.096 Ω | 23 × 47 mm | 78.1 cm³ / 4,324 mm² |
| 8 × SCCV60B107SRB, four series groups of two parallel cells (4S2P) | 200 F | 0.072 Ω | 19 × 62 mm | 140.6 cm³ / 9,424 mm² |

The last column is calculated from drawing tolerances: sum of cylinders πD²L/4 and flat body rectangles D × L. It excludes leads, vent/mounting clearance, matching/interconnects and power electronics. The eight-cell rectangles already exceed the 138 × 67 mm carrier area (9,246 mm²). An off-board/bracket or stacked enclosure arrangement needs manufacturer CAD and a checked assembly; body volume alone proves no fit.

#### Reproduce the screen

Common assumptions: four series groups, 8 V initial charge, 3.5 V converter terminal minimum, 9.422602974583173 A average screening ceiling from the 5 mΩ case, 90% conversion efficiency excluding bank ESR, ≥10 s full-load gap, and an additional 5 W × 10 s shutdown reserve. All voltage/load/efficiency/reserve assumptions need qualified tolerances or measurements. Wiring/contact ESR is additional.

| Population | Load held for 10 s | Open-circuit bank floor | Available energy | Conservative energy margin including reserve |
|---|---:|---:|---:|---:|
| Four radial | 25 W | 4.643 V | 334.2 J | −93.4 J |
| Four radial | 35 W stress case | 5.484 V | 267.2 J | −307.7 J |
| Four solder pin | 25 W | 4.262 V | 361.0 J | −35.3 J |
| Four solder pin | 35 W stress case | 5.032 V | 304.6 J | −226.8 J |
| Eight radial, 4S2P | 25 W | 4.071 V | 746.9 J | +366.4 J |
| Eight radial, 4S2P | 35 W stress case | 4.806 V | 644.3 J | +134.6 J |

Negative conservative margin means this worksheet has **not demonstrated** the duration; it need not prove physical failure because the ESR-loss bound is conservative. Positive margin establishes only a conditional desk budget. Four radial cells with the 10 mΩ current assumption have just 120.1 J available at 25 W and no usable 8 V window at 35 W, exposing why the old current assumption must change.

For each row, run the existing worksheet with `--cell-f 100 --stack-esr-ohm 0.144` (four radial), `100 / 0.096` (four solder pin), or `200 / 0.072` (4S2P); other arguments are:

```sh
python3 project/scripts/bridge_budget.py \
  --cells 4 --cell-f 200 --capacitance-factor 0.63 --stack-esr-ohm 0.072 \
  --start-v 8 --terminal-min-v 3.5 --average-current-a 9.422602974583173 \
  --efficiency 0.9 --load-w 25 --gap-s 10 --shutdown-w 5 --shutdown-s 10
```

Repeat with `--load-w 35`; this is a capability stress case, not measured consumption. 4S2P uses four monitored series groups, not eight series cells; assembly must qualify current sharing, shorts and balancing behavior.

The SCC voltage/temperature rating is 2.7 V to 65°C or 2.3 V to 85°C. Proposed 2 V cell charge is below both, but external ambient does not establish cell temperature. Cold ESR and effective capacitance, self-heating, enclosure/passive cooling, leakage and lifetime still require characterization for D-028. The datasheet temperature curves are not guaranteed cold maximum ESR values. Preserve normal performance; none of these options closes thermal qualification by throttling.

Next evidence: measured full-node/accessory and shutdown demand (GHO-30), exact minimum initial charge and added path ESR, a derated high-current power stage and guaranteed terminal floor (GHO-10), and matched-cell mounting/clearance/passive thermal CAD (GHO-7/GHO-12). Choose a population only after those gates; no procurement is authorized here.

### S3. Supercapacitor holdup on +5V_SYS only

A rail-level manager backs up the 5 V rail; the input bus and +3V3_RADIO still collapse, so this is option (b) or (c) by construction.

| Part | Fit |
|---|---|
| Analog Devices [LTC4041](https://www.analog.com/en/products/ltc4041.html): 2.9 to 5.5 V rails, 1 or 2 series caps, 2.5 A boost backup, PFI and power-fail flags, 4 x 5 mm QFN | Workable for (b)/(c): 2.5 A at 5 V is about 12.5 W. Two caps at 2.5 V give ½C(5.0² − 2.0²) = 10.5 J/F, so about 13 F of stack (2 x 27 F) for 140 J (est.). Figures from product summaries; datasheet not fetched. |
| TI [TPS61094](https://www.ti.com/lit/ds/symlink/tps61094.pdf): 0.7 to 5.5 V in, 1.8 to 5.4 V out, 2 A switch limit, single cap, buck charging 2.5 to 600 mA, 60 nA Iq, 2 x 3 mm WSON | Too small. With a 2 A switch limit it cannot carry a 4 to 5 W CM5 from a discharged cap. Suits a dying-gasp or RTC holdup only. |

Smaller and cheaper than S2 but it cannot deliver option (a), and the +5V_SYS rail would need its own power-fail wiring to the CM5.

### S4. Small Li-ion or LiFePO4 bridge cell

A 1S 300 mAh Li-ion cell holds about 4,000 J (est.), far more than needed, behind a boost converter (5 A class from 3 V) and its own charger. It brings what supercaps avoid: a second charger and protection circuit, charging limited to about 0 to 45 C inside a warm aluminum shell, poor output below about -20 C, cycle and calendar aging, swelling risk in a sealed enclosure, and air-transport paperwork for a second cell. LiFePO4 is safer but heavier for the same energy. Worth it only if the requirement becomes minutes of bridge time. **Not recommended for V1.**

### S5. None

The existing bulk (about 300 µF on the bus) holds ½ x 300 µF x (12² − 7.43²) = 13 mJ, about 1 ms at 10 W. The CM5 loses power without warning on every swap, which risks eMMC file system damage and fails D-008. Only acceptable if D-008 is revised.

## 4. Interaction with the eFuse, INA228 and supervisor

Power path with S2: pack pogo contacts → BQ25798 (BAT to SYS) → TVS, Q1 and TPS26633 eFuse → INA228 shunt → LTC3350 input ideal diode → **+VBUS_HOLD** → both LM76005 bucks. The supercap stack hangs off the LTC3350 switching node and output ideal diode.

| Item | Effect and required change |
|---|---|
| eFuse reverse blocking | When the pack is pulled, the TPS26633 and Q1 block reverse current, and the LTC3350 input ideal diode (fast-off at 30 mV reverse) also blocks, so the stack never backfeeds the pogo contacts or the charger. Two blocking stages; keep both. |
| eFuse UVLO (7.95 V rising, 7.43 V falling) | The eFuse turns off when the pack goes; that is now harmless. On a near-empty pack (8.4 V) the rising threshold, up to 8.3 V across tolerance, leaves little margin, so a refitted near-empty pack may not start. Existing issue, worth a bench check. |
| Inrush on reinsertion through C_dVdT | The eFuse sees only its own output bulk (47 to 100 µF), not the regulators' input capacitance and never the stack, so the existing 22 nF C_dVdT ramp (5.8 ms, about 55 mA per 25 µF) is unchanged. Load moves back to the input when the eFuse output rises above +VBUS_HOLD. The stack then recharges at the programmed rate. |
| Stack recharge | RSNSC 6 mΩ (5.33 A charge, 7.94 A backup ceiling). RSNSI 7.5 mΩ limits total input to 4.44 A worst case, under the eFuse's 5.17 A minimum (D-047). A second swap within about 40 s gets a partly charged bridge. |
| **Buck EN (change)** | Today both bucks' EN come from the eFuse PGOOD. On pack removal PGOOD falls at 6.59 V and would switch the bucks off while the bridge is still full. EN must come from a divider on +VBUS_HOLD (or PGOOD OR'd with the LTC3350 CAPGD); eFuse PGOOD reaches GPIO12 POWER_GOOD only through the logic-level translation the [pinout ledger](v1-pinout-and-sequencing.md) requires; the battery-domain node never connects to the CM5 directly. |
| **Supervisor SVS4 (change)** | SVS4 senses +VBUS_HOLD with a threshold below the backup regulation point (proposal: 6.0 V), so a swap does not reset the CM5 (D-044). |
| Backup regulation point | Set LTC3350 OUTFB so +VBUS_HOLD holds about 7.0 V in backup (est.): above what the 5 V buck needs and the new EN threshold, below any normal pack voltage. |
| INA228 | Sits before the bridge, so it sees pack current only and its energy and charge counters stay pack-only. Its bus undervoltage alert on GPIO 20 is a backup removal signal. Stack charge current appears as extra pack load after a swap, and software should not read it as a fault. |
| BQ25798 | With USB-C power present the charger keeps SYS up with no pack, so a swap while charging needs no bridge. Confirm the BQ25798 battery-absent behavior on its datasheet. |

### Detection signal for software

| Signal | Source | Timing | Use |
|---|---|---|---|
| BRIDGE_ACTIVE_N | LTC3350 PFO; PFI divider 562 k over 100 k trips at 7.75 V falling (1.17 V threshold, 30 mV hysteresis, so about 0.2 V at the bus) | 85 ns comparator delay | Primary. Start the swap timer and flush logs; maintain D-027 operation without a swap-mode TX-power cap. |
| PACK_PRESENT | Pack contact (M-11), pulled up on the radio side | Breaks with the power contacts | Tells a pulled pack apart from a pack at cutoff. |
| INA228_ALERT_N | Bus undervoltage limit, GPIO 20 | About 1 ms at fast conversion (est.) | Backup if PFO wiring fails. |
| Stack voltage | LTC3350 ADC over I2C | Polled | Remaining bridge time; triggers `poweroff` when the stack reaches the shutdown reserve. |

Software policy (proposal): on PFO low with PACK_PRESENT gone, enter swap mode; if the stack falls to a reserve level calculated from the qualified bank, converter floor and measured shutdown demand before the pack returns, run a clean shutdown. PFO needs a GPIO; the allocation belongs to the pinout owner ([GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9), [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md)). A latch-release switch would give earlier warning but is not needed with this bridge.

## 5. Recommendation

**Candidate: S2 input-bus backup architecture (B-24), not a frozen LTC3350/cell design.** It can keep both regulated rails supplied across a swap and isolates the eFuse from direct supercapacitor charging. Use the source-grounded population/current comparison above to advance cell and power-stage sizing. If volume or current capability does not close, compare a larger bank, a higher-current controller or a separately protected bridge-cell architecture against the same requirement; do not fall back to radios-off operation. Final cell MPN, current capability, thermal/ESR margins and CAD placement remain GHO-38/GHO-10/GHO-7 work.

### BOM additions (all candidates)

| Part | Qty | Notes |
|---|---:|---|
| Analog Devices LTC3350IUHF#PBF | 1 | Backup controller, 5 x 7 mm QFN; I grade for the D-028 cold limit |
| Supercapacitors 6 × SCCV60B107SRB | 6 | 3S2P, matched ±5 % per group; bank fuse fitted |
| N-MOSFET 40 V: 2 × CSD18514Q5A switches, 2 × CSD18512Q5B ideal diodes | 4 | 40 V because the eFuse output can reach its 32.8 V clamp |
| Inductor Bourns SRP1265A-4R7M | 1 | 4.7 µH |
| RSNSC 6 mΩ, RSNSI 7.5 mΩ, WSL2512 ±1 % | 2 | Exact value availability unverified |
| Dividers for PFI, OUTFB, buck EN; INTVCC and DRVCC caps | about 10 | |

Power-electronics placement remains unverified. Use the cell envelopes above for GHO-7 assembly review; any off-board or upright placement needs checked retention, interconnects, clearance and thermal paths.

### Bench tests

1. Time 20 gloved pack swaps by two people; check the 95th percentile against D-027 and increase the design interval if needed.
2. Measure node power in options (a), (b) and the shutdown (GHO-30 on Track A, then the V1 board).
3. Pull the pack at full measured node/accessory load and at cutoff voltage: prove D-027 with no reset, mesh-link interruption or deliberate performance reduction; log +VBUS_HOLD minimum, stack current, temperatures and bridge duration. Repeat with end-of-life capacitance/ESR emulation.
4. Refit during backup: eFuse ramp, no inrush trip, clean handover, stack recharge time and peak input current against 5.56 A.
5. Leave the pack out: clean shutdown fires at the reserve level and the file system checks clean.
6. Contact bounce on insertion and removal with a scope on the BQ25798 BAT pin and the eFuse input.
7. Repeat 3 to 5 at -20 C and +60 C enclosure temperature; read C and ESR from the LTC3350.
8. Two swaps 10 s apart.

## Requirement compliance

| Option | What it means | Cost |
|---|---|---|
| A. Full-node ride-through (required) | Input-bus bridge sized for full load; cell/controller candidates still under evaluation | Volume/cost not finalized |
| B. CM5-only ride-through | LTC3350 + 4 x 25 F with radios off, or LTC4041 on +5V_SYS; links drop and reassociate | About half the volume |
| C. Shutdown on removal | Smallest bank for a clean `poweroff` only | Revises D-008 |

D-027 settles the operating-mode/time choice: only A is compliant. B and C are comparisons, not choices awaiting Justin. The cell population and controller implementation are still engineering candidates.
