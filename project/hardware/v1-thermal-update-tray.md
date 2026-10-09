# V1 thermal update for the bridge tray (GHO-12)

**Owner:** [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12), fanless enclosure thermal paths.
**Status:** Candidate, 2026-10-09. This file re-derives the thermal model in [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §2 for the bridge tray (D-048), the top-side LTC3350 stage (D-047) and a 10 W Wi-Fi card. It edits no record and assigns no D, B or R number. The owning records still win (README rule 6). Nothing here is measured. Nothing here qualifies the design.

## Conventions

- **Verified:** read from the source in [Sources](#sources), at the revision given, on 2026-10-09.
- **Calculated:** derived here from the stated inputs. The arithmetic is shown or reproducible. Nobody has measured it.
- **Unverified:** an assumption, an estimate carried over from the thermal plan, or a value not checked against a primary source. All are listed in [What remains unverified](#what-remains-unverified).

Coordinates are in the board frame of [v1-reference.md](v1-reference.md) §18 (138 × 67 mm carrier, origin lower left, Z up from the PCB top).

Ambient is the D-028 hot endpoint, **+43.3 °C** (110 °F). The brief rounds it to 43 °C; this file uses 43.3 °C.

## Summary

- **No script exists for the thermal model.** `project/scripts/` has only the bridge energy calculator. The model is re-derived by hand below, with the same method and h values as the thermal plan. No case file was added.
- **The tray helps the enclosure.** It adds 23 mm of side wall: shedding area grows from 0.0226 to 0.0326 m² (+44 %). With the D-035 fins, case rise falls by about 16 %. At 18.5 W and 43.3 °C the case drops from 77.5 to **72.0 °C** (planning h). Every padded part gains the same 5.5 K. (Calculated)
- **The tray hurts its own cells.** Two supercaps sit 0.5 mm under the bottom-side bucks and charger. They run at about **75 to 82 °C** at the hot endpoint (18.5 W, planning h), 3 to 10 K under the 85 °C rating at ≤ 2.3 V. At a sustained 25.4 W they reach 86 to 93 °C and **exceed it**. (Calculated)
- **EDLC life is the real cost.** On the datasheet's 1,000 h at 65 °C anchor, halving per 10 °C, the bank reaches its sizing end of life in about **1,400 to 2,300 powered hours at the 21.1 °C nominal ambient**, and 300 to 500 hours at the hot endpoint. The 2.175 V charge level helps by an unknown factor. (Calculated on an Unverified life model)
- **Bridge stage losses do not move the case.** Standby loss is 0.05 to 0.12 W. Charge mode is about 1.5 to 2.2 W for at most 36 to 210 s. Backup is about 2.0 to 2.8 W for at most 13 s. The body time constant is about 11 minutes. (Calculated)
- **The Wi-Fi card fails its 70 °C rating with or without the tray.** At 10 W through a 2.5 K/W pad the card sits 25 K above the case. Staying at 70 °C needs a case at 45 °C, 1.7 K above ambient. No passive design does that. If 70 °C is an ambient rating, internal air at 77 to 87 °C fails it too. (Calculated)
- **The CM5 is marginal.** 83.3 °C against the 85 °C throttle point at 18.5 W (range 81.0 to 85.5 °C over the pad estimate). It fails at 25.4 W sustained. (Calculated)
- **The LTC3350 stage passes.** IC junction 96 to 106 °C against 125 °C at 18.5 W. (Calculated)
- **The pack cannot charge at the hot endpoint,** and it may not charge even at nominal ambient if it couples to the case. The M35A charge window ends at 45 °C. The case runs at about 50 °C at 21.1 °C ambient. (Calculated)

## 1. What changed in the inputs

| Input | Thermal plan (main) | This update | Tag |
|---|---|---|---|
| Radio body height | 27 mm | **50 mm** (27 + 23.0 mm tray, D-048) | Calculated from Verified D-048 text. The floorplan already needs more than 26.66 mm above the PCB ([v1-bridge-selection.md](v1-bridge-selection.md) record conflict 6). A 66 mm body is run as a sensitivity case. |
| Shedding area (top plus four sides; the pack covers the bottom) | 0.0107 + 0.0118 = 0.0226 m² | 0.0107 + 0.0219 = **0.0326 m²** | Calculated |
| Wi-Fi card | 8 W typical, 10 W peak | **10 W sustained** worst case | Verified: AsiaRF S3 page, "10W maximum, 8W average" ([v1-gpio-and-m2-audit.md](v1-gpio-and-m2-audit.md) §2.1). Sustained 10 W is a bounding assumption. |
| LTC3350 stage | not in the model | Top side, board X 55 to 85, Y 1.5 to 23 (D-047). Losses in §2. | Verified placement; losses Calculated |
| Supercaps | not in the model | 6 × SCCV60B107SRB in the tray, cells Z −24.1 to −5.1 | Verified (v1-bridge-selection.md §3.2) |
| Finned lid (D-035) | "roughly doubles heat shedding", not modelled | Modelled as a fixed added conductance equal to the old flat-body value: +0.271 W/K (planning) or +0.384 W/K (good) | Unverified. It is the decision card's estimate, held constant. Fin geometry is still open under [GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7). |

## 2. Bridge stage losses

All from [v1-bridge-selection.md](v1-bridge-selection.md) (main 53b0528) part values. Calculated unless marked.

| Mode | When | Loss | How |
|---|---|---:|---|
| Standby, bank full | Normal operation, always | **0.05 to 0.12 W** | Load current through RSNSI (7.5 mΩ) and the input ideal-diode FET (2.3 mΩ max × 1.3 hot = 3.0 mΩ): 1.48 A at 16 W from 10.8 V gives 0.02 W; 2.98 A at 25 W from 8.4 V gives 0.09 W. IC quiescent about 0.03 W (Unverified; Rev. D quiescent not re-read). Balancer bleeds 10 mA only while groups differ. Shunt ballasts (0.41 W max) run only if a group passes 2.30 V. |
| Charge mode | After each swap: 9 s typical, 36 s worst, up to 120 s from the floor, up to about 210 s for a first charge | **1.5 to 2.2 W** | At 5.33 A into a 5.5 V stack the stage delivers 29.3 W. At the assumed 93 % charger efficiency (Unverified) the loss is 2.2 W. Conduction alone: inductor 5.33² × 8.4 mΩ × 1.3 = 0.31 W; RSNSC 5.33² × 6 mΩ = 0.17 W; switch FETs 5.33² × 10.3 mΩ = 0.29 W; gate drive 12.6 V × 22 mA = 0.28 W; total 1.05 W. The rest is switching and core loss. At 25 W load the input limit leaves the charger about 21 W in, so the loss is about 1.5 W. |
| Backup mode | During a swap, at most 13.1 s (calculator lower bound) | **2.0 to 2.8 W** | v1-bridge-selection.md §2.4: 2.0 W of conduction at the 3.5 V floor and 7.94 A. 2.8 W at the assumed 90 % efficiency (Unverified). |

**Effect on the case.** New body heat capacity is about 420 J/K: the thermal plan's 250 J/K, plus 49 J/K for 23 mm more of 2 mm aluminium wall, plus about 124 J/K for 124 g of cells at an assumed 1 J/g·K (Unverified). With the finned planning resistance (1.55 K/W), the time constant is about 11 minutes. A worst first charge, 2.2 W for 210 s, is 462 J. Even with no shedding that lifts the case by 1.1 K. Backup is about 36 J. Neither is a steady-state input. (Calculated)

**Effect on the stage itself.** In charge mode the inductor rises about 40 × (5.33/13.5)² = 6 K (from its 13.5 A, 40 K rise rating, Verified in v1-bridge-selection.md). In backup it would rise 14 K at 7.94 A if held, but backup lasts 13 s. The IC's own rise is +9.4 K (v1-bridge-selection.md §2.3). (Calculated)

Not counted, as before: BQ25798 charger losses while the pack charges in the radio. They sit under the CM5, on top of tray row B (§4).

## 3. Model and results

**Method (same as v1-thermal-rf-plan.md §2).** The aluminium body is one isothermal node. R(case to ambient) = 1 / (h × area). Planning h = 12 W/m²K and good h = 17 W/m²K (anodized, still air). Side-wall convection is scaled by (27/50)^0.25 = 0.857 for the taller wall, which lowers side h to 11.2 (planning) and 15.5 (good). Fins add the fixed conductance in §1. Parts padded to the lid sit at case + P × R_pad, with R_pad = 2.5 K/W (range 2 to 3, thermal plan estimate). Internal air is case + 5 to 15 K (thermal plan estimate). A 2 mm wall 50 mm tall has fin efficiency about 0.97, so the taller wall stays near case temperature. (Calculated; inputs Unverified)

Holding h fixed is conservative at 43.3 °C: radiation alone rises from 6.9 to about 7.8 W/m²K at a 72 °C case.

| Body | G (W/K), planning / good | R (K/W), planning / good |
|---|---:|---:|
| 27 mm, flat lid (thermal plan) | 0.271 / 0.384 | 3.69 / 2.61 |
| 27 mm, finned | 0.541 / 0.767 | 1.85 / 1.30 |
| 50 mm, flat lid | 0.374 / 0.521 | 2.68 / 1.92 |
| **50 mm, finned (primary case)** | **0.644 / 0.905** | **1.55 / 1.11** |
| 66 mm, finned (floorplan sensitivity, planning) | 0.715 | 1.40 |

**Load cases** (W inside the radio body). Calculated from the thermal plan §1 table, changed only where stated.

| Case | Total | What changed |
|---|---:|---|
| Typical, 10 W Wi-Fi | **18.5** | Thermal plan typical (16.1 W) with Wi-Fi 8 → 10 W; 3.3 V buck loss +0.27 W (2 W more out at 88 %); TPS22975 loss 0.15 → 0.23 W (current ratio squared); input path +0.02 W; bridge standby +0.06 W |
| All peaks sustained | **25.4** | Thermal plan peak column (25.2 W, which already holds 10 W Wi-Fi) plus 0.12 W bridge standby. CM5 7 W, HaLow 3.3 W. |

The plan calls 25 W a transient. D-028 asks for the measured full continuous load, which nobody has yet (T0, T1). The two cases bracket it.

### 3.1 Temperatures at 43.3 °C ambient

Primary column: 50 mm body, finned lid, planning h, 18.5 W. All values Calculated.

| Part | Limit used | 18.5 W, finned, planning | Margin | 18.5 W, finned, good | 25.4 W, finned, planning | Margin at 25.4 W |
|---|---|---:|---:|---:|---:|---:|
| Case (lid, walls) | none (touch comfort open) | **72.0** | — | 63.7 | 82.7 | — |
| Internal air | — | 77.0 to 87.0 | — | 68.7 to 78.7 | 87.7 to 97.7 | — |
| CM5 SoC (4.5 W, 7 W at peak, pad 2 to 3 K/W) | 85 °C: firmware throttles to hold the SoC below 85 °C (CM5 datasheet §4.4). D-028 forbids relying on throttling. | **83.3** (81.0 to 85.5) | **+1.7 K** (−0.5 to +4.0) | 75.0 | 100.2 | **−15.2 K** |
| Wi-Fi AW7916-AED (10 W, pad 2 to 3 K/W) | 70 °C, AsiaRF operating range −10 to +70 °C. Not stated as ambient, surface or junction. | **97.0** (92.0 to 102.0) | **−27.0 K** | 88.7 | 107.7 | **−37.7 K** |
| HaLow GW16170 (1 W, 3.3 W at peak) | 70 °C as a planning limit (the brief's AW7916 rating; the GW16170's own rating is not in the records) | 77.0 with a 5 K/W pad; 87 to 97 with no pad (air at 10 K/W) | **−7 K** (pad) to −27 K | 68.7 (pad) | 99.2 (pad) | **−29 K** |
| GNSS MAX-M10S (sits in internal air) | +85 °C ambient (thermal plan, u-blox) | 77.0 to 87.0 | **+8 to −2 K** | 68.7 to 78.7 | 87.7 to 97.7 | **−3 to −13 K** |
| Supercaps, hottest cells (§4) | 85 °C at ≤ 2.3 V per cell (65 °C at 2.7 V). Charge is 2.175 V; 2.22 V worst case at code 12. | **75.0 to 82.0** | **+3 to +10 K** | 66.7 to 73.7 | 85.7 to 92.7 | **−1 to −8 K** |
| LTC3350 IC junction | 125 °C (I grade) | 96.4 to 106.4 | **+19 to +29 K** | 88.1 to 98.1 | 107.1 to 117.1 | **+8 to +18 K** |
| LTC3350 inductor (charge mode) | 150 °C including self-heating | about 93 to 103 | about +47 K | — | about 104 to 114 | about +36 K |
| LM76005 3.3 V buck die (not asked; see §4) | 125 °C | 120 to 131 (1.47 W × 29.6 °C/W JEDEC over 77 to 87 °C air) | **+5 to −6 K** | 112 to 122 | 147 to 157 (2.0 W) | **−22 to −32 K** |
| Battery pack top cell (upper bound = case) | Charge 0 to 45 °C; discharge to 60 °C (Unverified); BQ7721602 secondary OT 70 °C blows the pack fuse | ≤ 72.0 | **Charge: fails at any pack temperature above 45 °C.** Discharge and OT: open, set by the pack interface (§5) | ≤ 63.7 | ≤ 82.7 | — |

LTC3350 local board temperature is taken as case + 15 to 25 K, because the stage overlaps the bottom-side buck island at board X 55 to 66 (Unverified). Junction adds the +9.4 K of v1-bridge-selection.md §2.3, which assumes full switching, so it is conservative in standby.

**Old geometry for comparison** (27 mm, finned, planning h, 18.5 W): case 77.5, CM5 88.7, Wi-Fi 102.5 °C. The tray buys 5.5 K on every part tied to the case. With a flat lid the gain would be 18.8 K (111.6 → 92.8 °C case).

**Floorplan sensitivity** (66 mm body, finned, planning, 18.5 W): case 69.2 °C, CM5 80.4 °C, Wi-Fi 94.2 °C. More wall helps a little more, if the real body is that tall.

### 3.2 What it would take to pass

| Target | Case needed | Conductance needed at 18.5 W | Primary case has |
|---|---:|---:|---:|
| CM5 SoC ≤ 85 °C at 2.5 K/W | ≤ 73.75 °C | ≥ 0.61 W/K | 0.644 W/K (just passes) |
| Wi-Fi ≤ 70 °C at 2.5 K/W | ≤ 45.0 °C | ≥ 10.9 W/K | 0.644 W/K (17 × short) |
| Wi-Fi ≤ 70 °C at 1.0 K/W | ≤ 60.0 °C | ≥ 1.11 W/K | 0.644 W/K |

At 25.4 W the CM5 needs ≥ 1.05 W/K. (Calculated)

The Wi-Fi result does not depend on the tray. A 70 °C card limit and a 43.3 °C ambient leave 26.7 K for the whole path from the card to air. At 10 W that is 2.67 K/W in total, and the pad alone uses most of it.

## 4. Does the tray help or hurt?

**It helps the system.**
- Side-wall area grows 85 % and total shedding area 44 %. Case-to-ambient conductance rises 38 % with a flat lid and 19 % with fins. (Calculated)
- The case, CM5, Wi-Fi card and HaLow card all run 5.5 K cooler in the primary case. (Calculated)
- Heat capacity rises from about 250 to about 420 J/K. Short bursts and bridge recharge pulses are smoothed more. (Calculated, Unverified inputs)
- The tray puts 19 mm of cells and still air between the carrier and the pack plate. Bottom-side power parts no longer sit about 7 mm above the pack. (Calculated)

**It hurts the cells and the bottom-side power parts.**
- **Cells under hot parts.** Row A's right cell (board X 0 to 62, Y 0 to 19) sits under the 5 V and 3.3 V bucks (X 30 to 66, Y 3 to 17). Row B's right cell (X 0 to 62, Y 24 to 43) sits under the BQ25798 charger and PD block (X 38 to 60, Y 26 to 42). Row B's left cell is partly under the eFuse block. Clearance is 0.5 mm. (Verified positions, v1-reference.md §18 and v1-bridge-selection.md §3.2)
- **Cell temperature estimate.** Board under the bucks: case + 15 to 25 K (Unverified). Cell to board: 0.5 mm air over an effective 62 × 6 mm strip, about 60 to 70 K/W, since the gap widens around the can. Cell to wall and plate: about 40 K/W. The cell then sits 0.36 to 0.40 of the way from case to board, so case + 5 to 10 K. The range used is **case + 3 to 10 K**; the low end covers cells away from the bucks. (Calculated, Unverified inputs)
- **The bucks lose their chassis path.** The thermal plan §2 and v1-reference.md §15 couple the bucks to the chassis through copper and vias. With the tray filling the whole underside, that path must now go to the side walls. On the JEDEC θJA the 3.3 V buck die reaches 120 to 131 °C against 125 °C. A good pour does better, but this is now marginal. v1-3v3-rail.md assumed 60 °C internal air; this model gives 77 to 87 °C at the hot endpoint. (Calculated)
- **EDLC life** (life halves per 10 °C, anchored at 1,000 h, 65 °C, 2.7 V, end of life at 70 % capacitance and 200 % ESR, which is the sizing end of life):

| Ambient | Load | Case | Hottest cells | Hours to sizing end of life, 2.7 V basis |
|---|---:|---:|---:|---:|
| 21.1 °C nominal, finned planning | 18.5 W | 49.8 | 52.8 to 59.8 | 2,330 to 1,430 |
| 21.1 °C nominal, finned good | 18.5 W | 41.5 | 44.5 to 51.5 | 4,130 to 2,540 |
| 43.3 °C, finned planning | 18.5 W | 72.0 | 75.0 to 82.0 | 500 to 310 |
| 43.3 °C, finned planning | 25.4 W | 82.7 | 85.7 to 92.7 | 240 to 150 |

The cells run at 2.175 V, not 2.7 V. EDLC life also improves at lower voltage, but the SCC datasheet extract in the records gives no voltage factor. Do not apply one until KYOCERA AVX supplies it. (Calculated; life model Unverified)

**Net.** The tray is a thermal gain for the radio and a thermal cost for the bank. Before the tray, the bank had no place in the body at all (v1-bridge-selection.md §3.1). The tray is still the coolest spot available, but only if the cells are kept off the power parts.

**Mitigations (proposed, not modelled).**
1. Put a 1 mm insulating sheet between the bottom-side power parts and rows A and B. v1-bridge-selection.md §3.2 asks for one, but its stack leaves only 0.5 mm. That needs +0.5 to +1.0 mm of tray depth (see Record conflicts).
2. Move the bank NTC from the bank board (X 62 to 76) onto the row A right cell, under the bucks. That cell is the hottest, and firmware ties the charge code to it.
3. Step the charge code down with temperature. Hot cells have more capacitance and less ESR than cold ones, and the energy budget is set at −20 °C. With `bridge_budget.py` at 25 °C end of life (factor 0.63, ESR 54 + 15 mΩ, 25 W): code 12 (6.525 V) gives +136.1 J margin; **code 11 (6.30 V, 2.10 V per cell) gives +77.9 J**; code 10 (6.075 V, 2.025 V per cell) gives +21.9 J. (Calculated, run below)
4. Route the bucks' heat to the side walls with a copper pour and a wall contact.

```sh
python3 project/scripts/bridge_budget.py --cells 3 --cell-f 200 \
  --capacitance-factor 0.63 --stack-esr-ohm 0.069 --start-v 6.174 \
  --terminal-min-v 3.5 --average-current-a 7.94 --efficiency 0.9 \
  --load-w 25 --gap-s 10 --shutdown-w 5 --shutdown-s 10
# usable_energy_j 456.4, energy_margin_j 77.9, gap_duration_lower_bound_s 14.2
# --start-v 6.3945 (code 12): 514.6 J, +136.1 J, 16.0 s
# --start-v 5.954 (code 10): 400.4 J, +21.9 J, 12.5 s
```

Start voltages are the code minimums at −2 % reference (code × 1.176 / 1.2), as in v1-bridge-selection.md §1.3. Run at docs main 53b0528.

## 5. Battery pack

- The pack shell meets the radio's bottom plate. That plate is aluminium joined to the walls, so it sits near case temperature. If the pack couples well, its top cell approaches the case: 72 °C at the hot endpoint, about 50 °C at nominal. If the interface is a thermal break, the top cell stays near ambient plus its own I²R (about 0.3 to 0.5 W in the pack, Unverified). (Calculated)
- **Charging.** The M35A charge window ends at 45 °C (v1-battery-pack-gates.md). At a 43.3 °C ambient the pack has 1.7 K of margin before any heating. Charging in the radio at the hot endpoint is not achievable. The BQ76942 T1 thermistor will inhibit it. At nominal ambient, a well-coupled pack would also exceed 45 °C. So the pack interface must be a thermal break.
- **Discharge and the secondary OT.** The BQ7721602 secondary over-temperature is 70 °C, and with the current wiring it blows the pack fuse (v1-battery-pack-gates.md). A coupled pack at the hot endpoint could reach it. The M35A discharge limit (60 °C in the data sheet copies) is Unverified here.
- **What the tray changes.** The tray adds 19 mm of still air and cells between the hot carrier and the pack plate. It does not stop conduction down the aluminium walls. So it helps, but it is not a thermal break. The thermal plan's "pack sides also shed heat" row should stay rejected.

## 6. Bench tests that settle it

The brief names T8 to T11. In [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §4 those are RF tests (spectrum scan, desense, TTFF under load, antenna isolation). They do not measure temperature. The thermal tests in that plan are T0 to T6 and T12. Both sets are listed.

**Thermal (settle the numbers above):**

| Test | What it settles here | Change needed for the tray |
|---|---|---|
| T0 | Real sustained AW7916-AED power: is 10 W sustained, or 8 W? | None |
| T1 | Measured continuous load, replacing the 18.5 and 25.4 W cases. Add the LTC3350 charge-mode and standby input power. | Add bridge states: standby, charging after a swap, backup |
| T2 | Hot spots on the open board, including the stage over the buck island | Image both sides; add the LTC3350 IC and inductor |
| T3 | Case-to-ambient resistance of the 50 mm finned body; internal air; pad rises | Add thermocouples on the row A and row B right cells, the tray air, the bank NTC, the LTC3350 inductor, the pack top cell and the pack plate |
| T4 | Hot endpoint at 43.3 °C, full load, 2 h and stable. Settles the CM5 and supercap margins | Include a swap and full recharge at the hot endpoint. Log the bank NTC and meas_cap. This is bridge test B7. |
| T6 | Wi-Fi pad A/B. Settles whether 2.5 K/W is real | None |
| T12 | GNSS fix at the hot endpoint | None |
| Bridge B7 | Cell temperature in the tray at the hot endpoint ([v1-bridge-selection.md](v1-bridge-selection.md)) | Run inside T4 |

**RF (T8 to T11) and the stage:**

| Test | Relevance to this update |
|---|---|
| T8 spectrum scan | The LTC3350 is a new 490 to 510 kHz switcher. Harmonic 3151 of 500 kHz is 1575.5 MHz. The stage switches only while charging or in backup, so T8 must run it in charge mode (after a swap). |
| T9 desense | Repeat the all-on case during a bridge recharge. |
| T10 TTFF under load | No change. |
| T11 antenna isolation | No change; the tray does not move the antennas. |

## Proposed record text

For the records owner to apply only if the project owner accepts. No IDs are assigned.

**[v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §1, add a row:**
"LTC3350 bridge stage (B-24) | 0.05 to 0.12 | 2.2 (charge mode, ≤ 210 s); 2.8 (backup, ≤ 13 s) | v1-thermal-update-tray.md §2. Transient losses do not change the case temperature."

**§1, Wi-Fi row, Basis column:** add "Worst case sustained 10 W (D-026); modelled in v1-thermal-update-tray.md."

**§2, Enclosure assumptions:** replace the stale sentence and the body figures with:
"Radio body 145 x 74 x 50 mm: 27 mm plus the 23.0 mm bridge tray (D-048). The battery pack covers the bottom face, so only the top and four sides shed heat: about 0.0326 m². [Keep the h text.] With fins (D-035) held at the decision card's estimate, R case to ambient is 1.55 K/W (planning) or 1.11 K/W (good). Model and results: [v1-thermal-update-tray.md](v1-thermal-update-tray.md)."

**§2, R table:** replace the three rows with the 50 mm rows from §3 of this file, flat and finned.

**§2, predicted temperatures table:** replace with §3.1 of this file, at 43.3 °C (the D-028 endpoint) instead of 25 and 45 °C.

**§2, "What this means", add an item:**
"The bridge supercaps sit in the tray under the bottom-side bucks and charger. They reach 75 to 82 °C at the hot endpoint and 18.5 W, against 85 °C at ≤ 2.3 V. Fit an insulating sheet, put the bank NTC on the hottest cell and step the charge code down when hot."

**§4 T3:** add the thermocouple sites in §6 of this file.
**§4 T4:** add "Include a pack swap and a full bridge recharge. Log the bank NTC."
**§4 T8:** add "the LTC3350 stage in charge mode" to the source list.

**[v1-bridge-selection.md](v1-bridge-selection.md) §3.2 Thermal:** replace "Neither effect is modelled (B7)" with "Modelled in v1-thermal-update-tray.md: hottest cells 75 to 82 °C at the hot endpoint and 18.5 W; B7 measures it." Also give the insulating sheet its own row in the height stack.

**[v1-3v3-rail.md](v1-3v3-rail.md), Losses and heat:** replace "At a 60 C internal enclosure temperature" with the 77 to 87 °C internal air of this file, and say the die margin is now marginal on the JEDEC θJA.

**[v1-bom-baseline.md](v1-bom-baseline.md), SCC note:** replace "The enclosure interior is estimated at about 60 °C" with "Hottest bank cells are estimated at 75 to 82 °C at the D-028 hot endpoint (v1-thermal-update-tray.md)."

## Decisions for the project owner

Each has a recommended default.

1. **Wi-Fi card against the hot endpoint.** At 10 W the card cannot meet a 70 °C limit at 43.3 °C on any passive path. Choices: (a) ask AsiaRF what the 70 °C means and for any extended-temperature grade or shield limit, and hold the design; (b) screen an industrial-temperature MT7916 card now, alongside; (c) accept a lower Wi-Fi power at the hot endpoint (conflicts with D-028 and R-21). **Default: (a) and (b) together.** D-028 stays as is. The card choice is the blocker, not the tray.
2. **Load case for passive closure.** Choices: close at 18.5 W (typical with 10 W Wi-Fi) until T0 and T1 measure the continuous load; or close at 25.4 W (every peak sustained). **Default: 18.5 W, and check the CM5 and the supercaps at 25.4 W as a stress case.** At 25.4 W both fail.
3. **Supercap protection.** Choices: (a) fit a 1 mm insulating sheet under the power parts (+0.5 to +1.0 mm tray depth), move the bank NTC to the row A right cell, and step down to code 11 (6.30 V) when it reads ≥ 60 °C; (b) leave the design as in v1-bridge-selection.md. **Default: (a).** Code 11 keeps +77.9 J of margin hot, and the sheet costs at most 1 mm.
4. **Bank life.** On the only life data in the records the bank reaches its sizing end of life in 1,400 to 2,300 powered hours at nominal ambient. Choices: (a) ask KYOCERA AVX for life against voltage and temperature, treat the bank as a depot-replaced part, and set the firmware health threshold from meas_cap (B9); (b) resize the bank for a longer life now. **Default: (a).** The voltage factor may change the answer by several times.
5. **Pack interface.** Choices: a thermal break between the radio's bottom plate and the pack (insulating gasket or standoffs); or a conductive interface that lets the pack shed heat. **Default: thermal break.** A coupled pack goes above its 45 °C charge limit even at nominal ambient, and may reach the 70 °C secondary OT at the hot endpoint. Accept that the pack does not charge in the radio at the hot endpoint.
6. **Bottom-side buck heat path.** Choices: route the bucks' copper to the side walls with a wall contact; or move the bucks to the top side. **Default: side-wall path.** Moving the bucks reopens the RF placement rules.

## Record conflicts

Found, not resolved. README rule 6 asks for a Linear issue for each. This file opens none.

1. **Test IDs.** The brief names T8 to T11 as the tests that settle the thermal update. In v1-thermal-rf-plan.md §4 they are RF tests. The thermal tests are T0 to T6 and T12 (§6).
2. **Insulating sheet.** v1-bridge-selection.md §3.2 asks for a 1 mm sheet between the bottom-side power parts and the cells. Its height stack allows 0.5 mm, and D-048 records +23.0 mm from that stack.
3. **Bucks' chassis path.** v1-thermal-rf-plan.md §2 and v1-reference.md §15 send bottom-side converter heat to a chassis contact. Under D-048 the tray covers the whole underside. The path must change.
4. **Internal temperature.** v1-3v3-rail.md uses 60 °C internal air and v1-bom-baseline.md about 60 °C interior. This model gives 77 to 87 °C internal air at the D-028 hot endpoint.
5. **Bank NTC position.** v1-bridge-selection.md §3.4 puts the NTC on the bank board, centred between the rows. The hottest cells are the right cells of rows A and B.
6. **Body height.** v1-thermal-rf-plan.md uses 27 mm. The floorplan needs more than 26.66 mm above the PCB before the tray (v1-bridge-selection.md conflict 6). This file uses 50 mm and shows 66 mm as a sensitivity case.
7. **Wi-Fi power.** The thermal plan's typical row uses 8 W. D-026 and the AsiaRF page give 10 W maximum, and the same page also says 9 W maximum (v1-gpio-and-m2-audit.md conflict 8).

## What remains unverified

- Everything carried over from the thermal plan: h values, pad resistances (2 to 3 K/W), internal air at case + 5 to 15 K, the 250 J/K body heat capacity, and every typical and peak power except the AsiaRF figures.
- The finned-lid conductance, held at the decision card's "doubles shedding" estimate. Fin geometry is open (GHO-7).
- The body height (50 mm here) and wall thickness (2 mm assumed).
- Board temperature under the bucks (case + 15 to 25 K) and the cell-to-board and cell-to-wall resistances.
- EDLC life: the 1,000 h, 65 °C anchor is a qualification limit, not a service-life rating. The 10 °C halving rule is from the brief. There is no voltage factor.
- EDLC specific heat (1 J/g·K assumed). Cell capacitance and ESR at high temperature (taken as the 25 °C values in the energy runs).
- LTC3350 quiescent current, charger efficiency (93 %) and backup efficiency (90 %).
- The LM76005 θJA is the JEDEC value; a real pour will be lower.
- The GW16170 temperature rating; the M35A discharge limit; the meaning of the AW7916-AED 70 °C limit.
- The CM5 firmware may start throttling below 85 °C. The datasheet only says it holds the SoC below 85 °C.

## Sources

| Source | Revision | Used for |
|---|---|---|
| This repository: [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md), [v1-bridge-selection.md](v1-bridge-selection.md), [v1-gpio-and-m2-audit.md](v1-gpio-and-m2-audit.md), [v1-3v3-rail.md](v1-3v3-rail.md), [v1-reference.md](v1-reference.md) §15 and §18, [v1-battery-pack.md](v1-battery-pack.md), [v1-battery-pack-gates.md](v1-battery-pack-gates.md), [v1-bom-baseline.md](v1-bom-baseline.md), [decisions.md](../decisions.md) (D-026, D-028, D-035, D-047), [bridge_budget.py](../scripts/bridge_budget.py) | main at 53b0528 | Model, loads, part values, positions, limits, energy runs |
| [docs PR #78](https://github.com/ghostnet-labs/docs/pull/78), decisions.md D-048 | head 0498b2d (open, not merged on 2026-10-09) | Tray envelope and +23.0 mm depth |
| Raspberry Pi [CM5 datasheet](https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf) §4.4 | Release 3, build date 08/06/2026 | 85 °C SoC throttle point; −20 to +85 °C operating range |
| AsiaRF [AW7916-AED product page](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) (S3), via v1-gpio-and-m2-audit.md | Fetched 2026-10-09 | 10 W maximum; −10 to +70 °C |
| Analog Devices LTC3350, KYOCERA AVX SCC series, Bourns SRP1265A, TI CSD18514Q5A and CSD18512Q5B, via v1-bridge-selection.md | Rev. D; TDS-SC-0001 Rev 11; REV. 06/24; SLPS625A; SLPS624A | Stage losses, junction and cell ratings. Not re-read in this pass. |
| TI LM76005 θJA 29.6 °C/W, via v1-3v3-rail.md | As cited there | Buck die rise |
