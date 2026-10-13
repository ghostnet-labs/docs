# V1 pack-swap bridge: working-default selection (GHO-38)

**Owner:** [GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38), sizing the bridge energy for pack changes.
**Status:** Candidate, 2026-10-09. This file proposes one concrete bridge design: cells, sense resistors, inductor, current limits, placement and interconnect. Only bench measurement should be able to change it. It edits no record, selects no part and assigns no D or B number. The owning records still win (README rule 6): B-24 in [v1-selections.md](v1-selections.md) and the sizing study [v1-hot-swap-bridge.md](v1-hot-swap-bridge.md). Each section ends with text the records owner can apply if the project owner accepts it.

Requirements used: D-008 (swap without reboot), D-027 (full node and mesh links for at least 10 s, no deliberate load reduction) and D-028 (0 to 110 °F, −17.8 to +43.3 °C ambient, no throttling), from [decisions.md](../decisions.md). The energy target is the bridge study's "25 W peak held throughout gap" row: 25 W × 10 s / 0.9 = 278 J, plus the 56 J shutdown reserve, gives **334 J**.

## Conventions

- **Verified:** read from the source document in [Sources](#sources), with its revision, on 2026-10-09.
- **Calculated:** derived here from Verified values. The arithmetic is shown. Nobody has measured it.
- **Unverified:** an assumption, a typical curve or a value not checked against a primary source. Each one is listed in [What remains unverified](#what-remains-unverified).

Coordinates: "pack frame" is the frame of [v1-battery-pack.md](v1-battery-pack.md) (X 0 to 145 from the hook end, Y 0 to 74). "Board frame" is the frame of firmware `docs/hardware/v1-mechanical/parts.yaml` (138 × 67 mm carrier, Z up from the PCB top). That file maps pack frame to board frame as board X = 141.5 − pack X and board Y = pack Y − 3.5.

## Summary

| Item | Working default | Basis |
|---|---|---|
| Controller | Analog Devices **LTC3350IUHF#PBF** (I grade, not E grade) | The E grade is only guaranteed for 0 to 125 °C junction; the I grade is guaranteed from −40 °C (Verified, Rev. D note 2). D-028 reaches −17.8 °C. |
| Cells | **6 × KYOCERA AVX SCCV60B107SRB** (100 F, 2.7 V, Ø18 × 60 mm radial) as **3S2P** | Fewer cells than 4S2P and more margin to the pack. Verified data, see §1. |
| Stack charge | **6.525 V** (2.175 V per cell), VCAP DAC code 12. Code 13 (6.75 V) is held back for end of life. | Worst-case cell voltage stays under the 2.3 V rating that allows 85 °C (§1.3). |
| RSNSC | **6 mΩ ±1 %** (Vishay WSL25126L000FEA, 1 W) | 5.33 A charge, 8.42 to 10.94 A peak limit, 7.94 A average backup ceiling (§2). |
| RSNSI | **7.5 mΩ ±1 %** (WSL25127L500FEA, 1 W) | 4.10 to 4.44 A total input limit, under the eFuse's 5.17 A minimum (§5.3). |
| Inductor | **Bourns SRP1265A-4R7M**: 4.7 µH ±20 %, 8.4 mΩ max DCR, Isat 28 A, Irms 13.5 A, 13.5 × 12.5 × 6.2 mm | The datasheet inductor equation gives 4.72 µH. Isat is 2.6 times the worst-case peak (§2). |
| Switch FETs | 2 × **TI CSD18514Q5A** (40 V, 7.9 mΩ max at 4.5 V, Qg 18 nC max) | 40 V because the eFuse output can reach its 32.8 V clamp (B-15). Low Qg keeps the IC's gate-drive current at 18 mA. |
| Ideal-diode FETs | 2 × **TI CSD18512Q5B** (40 V, 2.3 mΩ max at 4.5 V) | Below the 5.4 mΩ needed to hold 30 mV forward drop at 5.56 A. |
| Switching frequency | 500 kHz, RT = 107 kΩ (490 to 510 kHz over temperature) | Verified, Rev. D p4. Same value the RF review analysed. |
| Backup output | +VBUS_HOLD regulated at 7.0 V (OUTFB divider 487 kΩ over 100 kΩ, giving 7.04 V) | Unchanged from the bridge study. It sits above SVS4's 6.0 V (D-044) and above the 6.66 V maximum stack. |
| Energy | **445.0 J usable vs 334 J needed: +111 J.** The conservative calculator margin is **+47.0 J**. The duration lower bound is 13.1 s. | `bridge_budget.py` at −20 °C, end of life, minimum charge and +15 mΩ path ESR (§4). |
| Placement | Bank in a **bridge tray under the carrier** (the battery-side bay of the radio body). Power stage on the carrier top side at board X 55 to 85, Y 1.5 to 23. | The bank fits nowhere in the present body. The tray adds **23.0 mm** of under-board depth (§3). |
| Interconnect | Würth WR-MPC4 8-pin dual row (4.2 mm pitch). Two 16 AWG wires per pole, a fuse at the bank. | 14 A per pole against a 7.94 A average and a 10.94 A peak (§3.4). |

This design meets the 25 W case. It does **not** cover the 35 W stress case at −20 °C and end of life (−337.9 J). The break-even sustained load is **26.3 W**. See owner decision 4.

## 1. Cells

### 1.1 Why 3S2P

The LTC3350 charges the stack with a step-down converter. It starts charging only when VOUTSN is 145 to 225 mV above VCAP (Verified, VDUVLO, Rev. D p4). The output ideal diode turns on when VOUT drops 65 mV below VCAP (Verified, p16). So the stack must stay below the lowest bus voltage the pack gives. Pack cutoff is 8.4 V (B-11). That rules out a stack above about 8 V, so a higher-voltage stack is blocked.

| Population | Cells | Charge | Per cell | Margin (calculator, §4 conditions) | Fit (§3) | Verdict |
|---|---:|---:|---:|---:|---|---|
| 4S1P SCCV60B107SRB or SCCW45B107SSB | 4 | 8.0 V | 2.0 V | Negative (bridge study, before cold derating) | Fits | Rejected: fails 25 W |
| 4S2P SCCV60B107SRB | 8 | 8.0 V (7.84 V min) | 2.0 V | +193.3 J | 8 cells need two layers (+42 mm) | Rejected: volume. The stack also sits within 0.4 V of the pack-cutoff bus, so charging stops on a weak pack. |
| **3S2P SCCV60B107SRB** | **6** | **6.525 V (6.39 V min)** | **2.175 V** | **+47.0 J** | One layer (+23 mm) | **Default** |
| 3S2P at code 13 | 6 | 6.75 V (6.62 V min) | 2.25 V | +103.6 J | Same | End-of-life step, owner decision 3 |
| 3S1P SCCY62B307SSB (300 F, Ø35 × 62) | 3 | 6.525 V | 2.175 V | More than 3S2P (same ESR, 1.5 × C) | Ø36 mm layer, +40 mm | Rejected: height |

3S2P uses each cell harder (2.175 V against 2.0 V, so 1.18 × the energy per cell), and the stack stays 1.7 V or more below pack cutoff. Charging then completes from any pack above cutoff.

### 1.2 Selected cell: KYOCERA AVX SCCV60B107SRB

Source: [SCC Series datasheet TDS-SC-0001 Rev 11](https://datasheets.kyocera-avx.com/AVX-SCC.pdf), pp1 to 4.

| Property | Value | Tag |
|---|---|---|
| Capacitance | 100 F, +30 % / −10 % | Verified, p2 |
| ESR at 25 °C, maximum | 12 mΩ at 1 kHz; 14 mΩ DC 10 ms; 18 mΩ DC 5 s | Verified, p2 |
| ESR at −20 °C | About 155 % of the 25 °C value, so 27.9 mΩ (DC 5 s maximum × 1.55) | Unverified: read from the typical curve, p3. Not a guaranteed maximum. |
| Capacitance at −20 °C | About 94 % of the 25 °C value | Unverified: typical curve, p3 |
| End-of-life limits | Capacitance ≥ 70 % and ESR ≤ 200 % of specification after 1,000 h at 65 °C and rated voltage, and after 500,000 cycles | Verified, p2 (qualification limits, not a service-life guarantee) |
| Rated temperature | −40 to +65 °C at 2.7 V; −40 to +85 °C at 2.3 V | Verified, p1 and p2 |
| Leakage | 260 µA max at 25 °C (72 h); about 6.5 × at 85 °C | Verified (25 °C); the 85 °C figure is a typical curve |
| Peak current | 56.25 A | Verified, p2 |
| Dimensions | Ø18 +1.0/−0 mm × 60 ±2.0 mm, radial leads 0.8 mm on 8.0 mm pitch. Envelope Ø19 × 62 mm max. | Verified, p4 |
| Mass | About 20.7 g (0.1013 Wh at 4.90 Wh/kg); 124 g for six | Calculated, p2 |

**Against D-028.** At 2.175 V per cell the cell is rated −40 to +85 °C. That covers the −17.8 °C ambient endpoint. The open question is the hot endpoint, because cell temperature is set by the enclosure, not by ambient. The thermal plan estimates internal air at 5 to 15 K above a case that runs 42 to 59 K over ambient with a flat lid ([v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §2). The finned lid (D-035) lowers that by an amount not yet modelled. The tray (§3) places the cells as far from the lid as the body allows. Cell temperature at the hot endpoint is bench item B7.

**Screening factors used in §4.**
- Capacitance factor: 0.9 (initial −10 %) × 0.7 (end of life) × 0.94 (−20 °C) = **0.5922**. Calculated.
- Cell ESR: 18 mΩ × 2 (end of life) × 1.55 (−20 °C) = 55.8 mΩ. A 2P group is 27.9 mΩ and the 3S stack is 83.7 mΩ. Adding 15 mΩ of path (§3.4) gives **98.7 mΩ**. Calculated.

These stack the worst cases on purpose. The cold factors come from typical curves, so B4 must measure them.

### 1.3 Charge level and balancing

- **VCAP divider:** RFBC1 = 499 kΩ, RFBC2 = 100 kΩ, so VCAP = 5.99 × CAPFBREF. The DAC steps from 0.6375 V to 1.2 V in 37.5 mV steps (Verified, p17). Code 12 = 1.0875 V gives 6.51 V, and code 13 = 1.125 V gives 6.74 V. (The ideal 6.0 ratio gives 6.525 and 6.75 V, the values used below.) Calculated.
- **Worst-case cell voltage at code 12:** CAPFB reference ±2 % over temperature (1.176 to 1.224 V, Verified, p4) gives 6.66 V, or 2.22 V per cell. The balancer adds up to 10 mV (Verified, p17). That stays under the 2.3 V that permits 85 °C. Calculated.
- **Code 13:** 6.885 V worst case, 2.295 V per cell. That just meets 2.3 V before imbalance. Keep it for end of life only (owner decision 3).
- **Minimum initial charge used in §4:** 6.525 × 1.176 / 1.2 = **6.394 V**. Calculated.
- **CAP_SLCT:** three cells. Tie CAP4 to CAP3 and strap CAP_SLCT1 = 1, CAP_SLCT0 = 0 (num_caps = 2) (Verified, p21).
- **Balancer:** the internal balancer discharges the highest cell at about 10 mA until all cells are within about 10 mV. It is disabled in backup (Verified, pp17 and 18). Within a 2P group the cells share voltage, so only the three groups need balancing.
- **Shunt (overvoltage) regulators:** set vshunt to 2.30 V (programmable to 3.6 V, Verified, p18). Ballast resistors of 2.4 Ω ±1 %, 1 W give about 2.30 / (2 × 2.4) = 0.48 A of shunt current. The resistor dissipation is 3 × 2.30² / (16 × 2.4) = 0.41 W (equation Verified, p21; values Calculated). Four ballasts are needed, on CAPRTN, CAP1, CAP2 and CAP3.
- **Matching:** with ±30/−10 % groups, a 180 F group charged in series with two 260 F groups would reach 2.74 V at a 6.525 V stack. Calculated: V ∝ 1/C. Match the three groups to ±5 % of each other by measured capacitance. Then the smallest group reaches 2.32 V during a fast charge, and the 2.30 V shunt clamps it. Calculated. Matching is a production step (B10).

### 1.4 Alternatives considered and not chosen

| Option | Why not the default |
|---|---|
| A different controller (LTC3351, LTC3643, MAX38888 and others) | No datasheet was obtained in this pass. The bridge study already rejects TPS61094 and LTC4041 for current. Nothing here shows a controller that removes the step-down charging limit at 25 W. Not evaluated. |
| Protected Li-ion or LiFePO4 bridge cell (bridge study S4) | It adds a second charger and protector. Charging is limited to about 0 to 45 °C, which conflicts with D-028's cold endpoint and the warm interior. It also adds a second lithium cell to transport. Unchanged: not recommended. |
| Hybrid lithium-ion capacitor cells (3.8 V class) | Much higher energy per volume, so the bank might fit the present body without the tray. No datasheet was obtained, so cold ESR, the minimum-voltage limit and the shipping class are unknown. The LTC3350 has no backup cut-off voltage, so it would need added overdischarge protection. Owner decision 1 asks whether to fund a study. |

## 2. Power stage: RSNSC, inductor and current limits

All equations are from the LTC3350 Rev. D Applications Information section, pp21 to 30. Values are Calculated unless marked.

### 2.1 Sense resistors and limits

| Quantity | Equation (Rev. D) | 6 mΩ RSNSC, 7.5 mΩ RSNSI |
|---|---|---|
| Charge current ICHG(MAX) | 32 mV / RSNSC (p21; VSNSC 31.04 to 32.96 mV over temperature, p4) | 5.33 A nominal (5.12 to 5.55 A) |
| Peak inductor limit IPEAK | 58 mV / RSNSC (p22; VPEAK 51 / 58 / 65 mV, p4) | 9.67 A nominal; 8.42 A minimum (51 / 6.06); 10.94 A maximum (65 / 5.94) |
| Backup average ceiling | IPEAK(min) − ΔIL/2 | 8.42 − 0.475 = **7.94 A** |
| Input limit IIN(MAX) | 32 mV / RSNSI (p21; VSNSI 31.04 to 32.96 mV, p4) | 4.27 A nominal (4.10 to 4.44 A) |

The 6 mΩ choice settles the RSNSC question from the bridge study. 10 mΩ gave only a 4.37 A ceiling and fails. 5 mΩ gives a 9.42 A ceiling but a 13.1 A peak and 6.4 A of charge current. At 6 mΩ the current floor is 27.8 W / 7.94 A = **3.50 V** at the stack terminals. That equals the bridge study's assumed 3.5 V converter minimum, so the current limit now justifies that number. The 5 mΩ option would lower the floor to 2.9 V and add about 70 J. It costs 20 % more peak current, a smaller inductor and higher losses at 2.9 V. Keep it as a fallback if B5 shows a deficit.

### 2.2 Inductor

- **Value.** For VIN(MAX) ≤ 2 × VCAP the datasheet gives L = VCAP(1 − VCAP/VIN(MAX)) / (0.25 × ICHG(MAX) × fSW) (p26). With VCAP = 6.525 V, VIN(MAX) = 12.6 V (3S pack, full) and ICHG = 5.33 A, that is 6.525 × 0.482 / (0.25 × 5.33 × 500 kHz) = **4.72 µH**, so use 4.7 µH.
- **Charge ripple.** ΔIL = VCAP(1 − VCAP/VIN)/(L × f) = 3.146 / (4.7 µH × 500 kHz) = 1.34 A nominal. At −20 % L and 490 kHz it is 1.71 A. The peak while charging is at most 5.55 + 0.85 = 6.4 A, below the 8.42 A minimum peak limit.
- **Backup ripple.** In step-up mode ΔIL = VCAP(1 − VCAP/VOUT)/(L × f). Below 7.0 V this peaks at VCAP = 3.5 V: 1.75 / (3.76 µH × 490 kHz) = **0.95 A**.
- **Saturation.** The datasheet asks for Isat at least 80 % above ICHG(MAX), which is 9.6 A (p27). The stricter bound is the 10.94 A maximum peak limit.

**Selected: Bourns SRP1265A-4R7M** ([datasheet REV. 06/24](https://www.bourns.com/docs/Product-Datasheets/SRP1265A.pdf)). It is rated 4.7 µH ±20 %, 7.0 mΩ typical and 8.4 mΩ maximum DCR, Irms 13.5 A (40 °C rise), and Isat 28 A (20 % inductance drop). It measures 13.5 ±0.5 × 12.5 ±0.3 × 6.2 ±0.3 mm, operates from −55 to +150 °C including self-heating, and is AEC-Q200 (all Verified). Isat is 2.6 times the 10.94 A worst-case peak. Irms covers the 7.94 A backup average.

A lower-profile alternative is SRP1245A-4R7M ([REV. 06/24](https://www.bourns.com/docs/Product-Datasheets/SRP1245A.pdf)): 15.0 mΩ max DCR, Isat 27 A, Irms 12 A, 5.0 mm max height (Verified). Use it only if the stage must go on the bottom side. It adds about 0.4 W of copper loss at 7.94 A.

### 2.3 Duty cycle and frequency checks

| Constraint (Rev. D) | Limit | This design | Result |
|---|---|---|---|
| fSW = 53.5 / RT (p17) | RT 107 kΩ gives 500 kHz; 490 to 510 kHz over temperature (p4) | 500 kHz | Pass. Same value as [v1-rf-coexistence.md](v1-rf-coexistence.md) §3. |
| Step-up maximum duty (p5) | 87 % min, 93 % typical, at 25 °C only (no temperature dot) | D = 1 − 3.5/7.0 = 50 %, about 55 % with losses | Pass with 32 points of margin. The cold value is not guaranteed (B5). |
| Step-down maximum duty (p5) | 97 % min | 6.66 / 8.1 = 82 % (pack at cutoff, 0.3 V path drop assumed) | Pass |
| Charge enable VDUVLO (p4) | VOUTSN ≥ VCAP + 225 mV max | 6.66 + 0.225 = 6.89 V, below 8.1 V | Pass. The 4S 8.0 V stack would leave only about 0.1 V. |
| Minimum on-time (p30) | tON(min) 85 ns < VCAP / (VOUT × fSW) | Holds for VCAP ≥ 85 ns × 12.6 V × 510 kHz = 0.55 V | Pulse skipping only below 0.55 V on a first charge from empty. The datasheet allows this. |
| Maximum-power-transfer floor (p24) | VCAP(min) ≥ sqrt(4 × n × RSC × P / η) | sqrt(27.8 W × 98.7 mΩ) = 1.66 V terminal | Not limiting. The current limit sets 3.50 V. |
| IC dissipation (p29) | TJ = TA + VOUT(IQ + IG) × 34 °C/W | IG = 2 × 18 nC × 500 kHz = 18 mA; 12.6 V × 22 mA × 34 = **+9.4 K** | Pass |

### 2.4 Rest of the stage

| Part | Value | Basis |
|---|---|---|
| Top and bottom switches | 2 × CSD18514Q5A ([SLPS625A](https://www.ti.com/lit/ds/symlink/csd18514q5a.pdf)): 40 V, 7.9 mΩ max at 4.5 V, Qg 14 typ / 18 max nC at 4.5 V, Crss 138 pF max | Verified. Logic-level, as the datasheet requires for 5 V DRVCC (p28). Conduction loss at 7.94 A with a 1.3 × hot factor is about 0.33 W each. Calculated. |
| Input and output ideal diodes | 2 × CSD18512Q5B ([SLPS624A](https://www.ti.com/lit/ds/symlink/csd18512q5b.pdf)): 40 V, 2.3 mΩ max at 4.5 V | Verified. Datasheet rule: RDS(on) ≤ 30 mV / I (p30), so 5.4 mΩ at 5.56 A. The output FET sees the highest VIN (p30), so 40 V covers the 32.8 V eFuse clamp. |
| RSNSC, RSNSI | WSL25126L000FEA (6 mΩ) and WSL25127L500FEA (7.5 mΩ), ±1 %, 1 W at 70 °C ([Vishay 30100, 23-Nov-2023](https://www.vishay.com/docs/30100/wsl.pdf)) | The part-number pattern and the 0.5 mΩ to 0.5 Ω, ±1 % range are Verified. Those two exact values are not checked against Vishay's decade-value list (Unverified). RSNSC dissipates 7.94² × 6 mΩ = 0.38 W in backup. |
| CCAP | ≥ 100 µF effective at 6.5 V, ESR ≤ 2 mΩ (for example ceramics plus one polymer) | Datasheet rule: 1/(8 × CCAP × fSW) + RESR ≤ n × RSC / 5 = 3 × 9 mΩ / 5 = 5.4 mΩ (p28). 2.5 + 2 = 4.5 mΩ. Calculated. |
| COUT on +VBUS_HOLD | ≥ 250 µF bulk, 35 V rated. The bucks' existing input bulk may count. | Datasheet rule: 100 µF per 2 A of backup (p27). 5 A at the 35 W stress case gives 250 µF. 35 V covers the 32.8 V clamp. |
| VC compensation | 10 nF | "Backing up to low voltages (<8 V) use 8.2 nF to 10 nF" (p24) |
| OUTFB phase lead | CFBO1 = 1/(2π × 2 kHz × 487 kΩ) = 163 pF, so use 150 to 180 pF. RFO × CFO = 1/(2π × 500 kHz) = 318 ns. | Equations Verified (p24), values Calculated |
| PFI divider | 562 kΩ over 100 kΩ (unchanged): 7.75 V falling and 7.94 V rising | Bridge study. 1.17 V threshold and 30 mV hysteresis Verified (p5). |
| DB bootstrap diode | Fast PN diode, not Schottky | The stage never runs non-synchronously here because VCAP is always below VOUT. The datasheet still prefers PN when the output ideal diode is fitted (p29). |
| I2C | SMBus address 0b0001001 (0x09). Alert response address 0b0001100. | Verified, p18. Belongs on the SYS_I2C address map (net plan open item 24). |

**Backup efficiency.** At the floor (3.5 V in, 7.94 A) the conduction losses add up as follows: RSNSC 0.38 W, inductor 0.69 W (8.4 mΩ × 1.3), FETs 0.65 W, and gate drive 0.28 W. That is about 2.0 W of 27.8 W, or 93 %. Switching and core loss are not modelled. The 90 % used in §4 is plausible but **Unverified**, and the break-even is 85.7 % (B5).

## 3. Mechanical fit

### 3.1 Why the bank cannot go on the carrier

Sources: firmware branch 24.10 at [3ac1495](https://github.com/ghostnet-labs/firmware/commit/3ac1495dae62999ff95caa1b4a6ff1d1065efff4), `docs/hardware/v1-mechanical/parts.yaml` and `out/report.md`; [v1-battery-pack-gates.md](v1-battery-pack-gates.md).

- The six cells are 105.5 cm³ of cylinders. A flat layout covers 7,068 mm² (6 × 19 × 62) at a height of 19 mm. Calculated.
- **Top side.** The Ethernet feed-through already sets about 27 mm of clear height above the PCB. Most of the area is spoken for. The CM5 (X 31 to 86, Y 24 to 64) and the Wi-Fi card (X 88 to 118, Y 10.9 to 62.9) need lid pads (D-035). The feed-through, plug and pigtail fill X 0 to 48, Y 0 to 27 up to Z 20. The RF pigtails run along the top wall. The largest clear strips are X 48 to 88 × Y 0 to 24 and X 118 to 136.5 × Y 21 to 60. Neither takes a 62 mm cell. Cells under the lid would also sit in the hottest air.
- **Bottom side.** The current model leaves 10.4 mm below the board (the pogo zone spans Z −12 to −1.6). A 19 mm cell does not fit.

### 3.2 Default: bridge tray in the battery-side bay (option A)

The radio body grows downward. A tray holds the bank between the carrier's bottom side and the pack interface plate. The pack footprint (M-01) and the pack itself are unchanged.

| Element | Pack frame | Board frame | Tag |
|---|---|---|---|
| Radio interior (2.0 mm wall, from parts.yaml) | X 2 to 143, Y 2 to 72 | X −1.5 to 139.5, Y −1.5 to 68.5 | Unverified (parts.yaml assumption) |
| Row A (Y 13), row B (Y 37), row C (Y 61); cells Ø19, gaps 5.0 mm between rows and 1.5 mm to the walls | Y 3.5–22.5, 27.5–46.5, 51.5–70.5 | Y 0–19, 24–43, 48–67 | Calculated |
| Left and right cell of each row, leads facing the centre | X 3.5–65.5 and 79.5–141.5 | X 76–138 and 0–62 | Calculated |
| Bank board (vertical, cells soldered through, series bus, fuse, harness exit) | X 65.5–79.5 (14 mm gap) | X 62–76 | Proposed |
| Bank envelope | 138 × 67 × 19 mm | the board outline | Calculated |
| Pogo daughterboard column (M-10, M-14; 10.4 mm, from parts.yaml) | X 105–129, Y 29–45, under row B right | X 12.5–36.5, Y 25.5–41.5 | Unverified (pack-to-board mapping assumed in parts.yaml) |

**Groups.** Each row is one 2P group: A-left with A-right, and so on. The bank board connects A to B to C in series. All bus links are short and lie on one board. Proposed.

**Height.** Row B's board-frame X 0 to 62 cell sits over the pogo column and under the bottom-side charger block (board X 38 to 60, Y 26 to 42, to Z −4.6). The stack below the board is: 3.0 mm bottom-side parts (parts.yaml assumption), 0.5 mm clearance, 19.0 mm cell, 0.5 mm clearance and the 10.4 mm pogo column. That is **33.4 mm under the board, against 10.4 mm today: +23.0 mm.** If the charger block moved off row B, it would be +20.0 mm. Calculated. The 1 mm insulating sheet under the bottom-side power parts (D-051) needs its own layer in this stack: +0.5 to +1.0 mm, so 33.9 to 34.4 mm under the board.

**Clearances that pass.** Locating-boss recesses (X 117, Y 12 and 60, M-18) and the latch keeper (X 134 to 141 near Y 37, M-20) are in the interface plate below the tray. Every cell is clear of the hook bay (X 0 to 6) by its own 1.5 mm end clearance. These checks use the envelope only, and the plate thickness is not recorded (Unverified).

**Thermal.** The tray puts the cells next to the pack and away from the finned lid. That is the coolest internal location this body offers. Fit a 1 mm insulating sheet between the carrier's bottom-side power parts and the cells. Bottom-side parts that need a chassis path ([v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §2) must reach it through the side walls. The tray also lengthens the radio's side walls by 23 mm, which adds shedding area. Modelled in [v1-thermal-update-tray.md](v1-thermal-update-tray.md): hottest cells 75 to 82 °C at the hot endpoint and 18.5 W; B7 measures it.

**Service.** The pogo daughterboard is replaced by lifting out the tray. That is acceptable for depot service. It is not a field operation.

### 3.3 Alternative: move the contact array into the bank's centre gap (option B)

The bank board splits to the two outer ends, so the centre gap becomes X 67.5 to 77.5 (10 mm). Turn the 4 × 2 probe array 90° so that its 4 mm span runs along X. The pogo board (about 8.5 mm by 24 mm) then fits in the gap, and no cell sits over it. The depth below the board becomes 3.0 + 0.5 + 19.0 + 0.5 = 23.0 mm, which is **+12.6 mm**. This changes M-10 (centre and orientation), M-11 make and break order, M-15 to M-18 and the gate-1 latch work. That is GHO-8 rework, so it is owner decision 2, not the default.

### 3.4 Interconnect

| Link | Choice | Rating against need | Tag |
|---|---|---|---|
| VCAP+ and CAPRTN (stack power) | 2 × 16 AWG per pole, about 150 mm, soldered at the bank board | 13.17 mΩ/m per wire, so about 1.0 mΩ per pole for two wires in parallel. The worst-case average is 7.94 A (4 A per wire) and the peak 10.94 A. | Calculated |
| Carrier connector | Würth WR-MPC4 dual row, 8 pins, 4.2 mm pitch: header 649008227222 (right angle), housing 649008113322, crimp 64900113722 (16 AWG) | Header 7 A max per contact at 8 pins, crimp 9 A, contact 10 mΩ max, −40 to +105 °C (Verified, Würth datasheets 002.001 2019-12-20 and 001.001 2025-02-18). Two contacts per pole give 14 A. | Verified ratings. The vertical header variant and the crimp for 20 to 24 AWG are not chosen (Unverified). |
| Pin map | 1–2 VCAP+, 3–4 CAPRTN, 5 CAP1, 6 CAP2, 7 CAP3 Kelvin, 8 CAPRTN Kelvin | The Kelvin taps feed the CAP pins through the 2.4 Ω ballasts and carry at most 0.48 A, so 22 to 24 AWG is enough. | Proposed |
| Bank NTC | 10 kΩ NTC on the row A right cell (board X 0 to 62, Y 0 to 19, the hottest cell, under the bucks) to the LTC3350 GPI (a thermistor input the datasheet supports, p14), 2-pin link | Lets firmware step the charge from code 12 to code 11 (6.30 V) while it reads 60 °C or more (D-051) | Proposed. Circuit values Unverified. |
| Bank fuse | One fuse at the bank board in series with VCAP+: about 15 A slow-blow, ≥ 32 V, cold resistance ≤ 5 mΩ | Stack short-circuit current is about 6.5 V / 27 mΩ = 240 A. Without a fuse a harness short dumps the full bank (about 1.4 kJ). | MPN open (Unverified). Owner decision 5. |
| Path ESR budget | Connector pairs 2 × 5 mΩ max, wires 2 mΩ, bank bus about 2 mΩ: **14 mΩ**. 15 mΩ is used in §4; with a fuse, about +5 mΩ. | Calculated, B6 |

The bus side needs no new harness: the input and output ideal diodes and +VBUS_HOLD stay on the carrier.

### 3.5 Power-stage placement

**Default: carrier top side, board X 55 to 85, Y 1.5 to 23 (645 mm²).** Nothing in parts.yaml at 3ac1495 occupies that area. It is clear of the CM5 underside keepout (Y ≥ 24) and outside the XY shadow of both radio cards (HaLow X 7 to 29; Wi-Fi from X 88). It is 35.5 mm edge to edge from the GNSS block, against the 15 mm rule. The 6.5 mm maximum inductor height is under the CM5's 7.51 mm. The stage needs room for the IC (5 × 7 mm), the inductor (14.0 × 12.8 mm max), four 5 × 6 mm FETs, two 2512 sense resistors, CCAP and part of COUT: about 450 mm². Calculated. The radio load switches and the hub 1.1 V buck are not modelled yet and may claim the same area (Unverified). The WR-MPC4 header goes on the bottom side at about board X 80.5 to 90, Y 2 to 19, beside the shunt block (CAD-verify).

This places the stage on the top side. [v1-rf-coexistence.md](v1-rf-coexistence.md) §3.2 and [v1-stackup-routing.md](v1-stackup-routing.md) (L8 list) place it on the bottom side. That is a record conflict (see [Record conflicts](#record-conflicts)). The RF rules themselves are met. The bottom-side alternative uses SRP1245A-4R7M at 5.0 mm. Cells under the power band would then have to clear Z −6.6 instead of −4.6, which adds up to 2 mm of tray depth. The stackup's 10 A supercapacitor-path row still covers this design (7.94 A average, 10.94 A peak).

## 4. Calculator run

The tool is the existing [bridge_budget.py](../scripts/bridge_budget.py) (added in docs #26, 83101b4). Its arguments are command-line flags, so no new case file is needed. The run below is at docs `main` 73368aa, and the output is unedited.

```sh
python3 project/scripts/bridge_budget.py \
  --cells 3 --cell-f 200 --capacitance-factor 0.5922 --stack-esr-ohm 0.0987 \
  --start-v 6.3945 --terminal-min-v 3.5 --average-current-a 7.94 \
  --efficiency 0.9 --load-w 25 --gap-s 10 --shutdown-w 5 --shutdown-s 10
```

```json
{
  "classification": "conditional desk budget; not hardware qualification",
  "inputs": {
    "cells": 3,
    "cell_f": 200.0,
    "capacitance_factor": 0.5922,
    "stack_esr_ohm": 0.0987,
    "start_v": 6.3945,
    "terminal_min_v": 3.5,
    "average_current_a": 7.94,
    "efficiency": 0.9,
    "load_w": 25.0,
    "gap_s": 10.0,
    "shutdown_w": 5.0,
    "shutdown_s": 10.0
  },
  "effective_stack_f": 39.48,
  "terminal_floor_v": 3.5,
  "open_circuit_stack_floor_v": 4.283333333333333,
  "usable_energy_j": 444.9926178016666,
  "gap_energy_bound_j": 339.9470899470899,
  "shutdown_reserve_bound_j": 58.04232804232804,
  "energy_margin_j": 47.003199812248624,
  "gap_duration_lower_bound_s": 13.090055216266924,
  "gap_plus_reserve_budget_satisfied": true,
  "required_nominal_cell_f": 178.87461592309023
}
```

Inputs: `--cells 3` is the series group count. `--cell-f 200` is one 2P group. The factor and ESR come from §1.2. The start voltage is the code-12 minimum from §1.3. The current is the 7.94 A ceiling from §2.1. The other inputs are the bridge study's.

**Result.** Usable energy is 445.0 J against the 334 J target: **+111.7 J (+33 %)**. The calculator's conservative margin, which adds the I²R loss bound to both the gap and the reserve, is **+47.0 J**. A 2P group needs 178.9 F nominal, and 200 F is fitted.

**Sensitivity** (same command, one input changed; Calculated):

| Case | Floor (V) | Usable (J) | Margin (J) | Gap lower bound (s) |
|---|---:|---:|---:|---:|
| Default above | 4.283 | 445.0 | +47.0 | 13.1 |
| Load 16 W (typical estimate) | 4.001 | 491.1 | +229.8 | 24.2 |
| Load 20 W | 4.127 | 471.0 | +150.9 | 18.0 |
| Load 30 W | 4.981 | 317.3 | −135.5 | 8.0 |
| Load 35 W (stress case) | 5.681 | 170.1 | −337.9 | 3.8 |
| Path ESR +10 mΩ (fuse and contacts) | 4.363 | 431.4 | +26.9 | 12.5 |
| Charge code 13 (6.75 V) | 4.283 | 501.6 | +103.6 | 14.8 |
| New cells at 25 °C (factor 0.9, ESR 27 + 15 mΩ) | 3.833 | 785.9 | +425.0 | 25.8 |
| End of life at 25 °C (factor 0.63, ESR 54 + 15 mΩ) | 4.048 | 514.6 | +136.1 | 16.0 |
| Efficiency 0.85 | 4.488 | 409.6 | −8.0 | 11.5 |
| Shutdown reserve 10 W × 10 s | 4.283 | 445.0 | −16.0 | 13.1 |
| Gap 12 s | 4.283 | 445.0 | −21.0 | 13.1 |
| 4S2P, 8 cells at 8.0 V, for comparison | 4.505 | 609.6 | +193.3 | 17.0 |

**Break-even values** (margin = 0, other inputs at default; Calculated): load **26.3 W** (27.9 W at code 13); gap **11.4 s** at 25 W; shutdown reserve 18.1 s at 5 W, about 90 J; efficiency **85.7 %**; total stack ESR **122 mΩ**; capacitance factor **0.530**.

**Shutdown trigger.** Firmware should start `poweroff` when meas_vcap reaches the level that still holds the reserve at end of life and −20 °C. That level is ½ × 39.48 × (V² − 4.283²) = 58 J, which gives V = 4.61 V. Allowing for ADC error (1.5 %, Verified, p6), set the trigger at **4.75 V**. Calculated.

Verification of the tool: `python3 -m unittest discover -s project/scripts -p 'test_bridge_budget.py'` passes at 73368aa.

## 5. Balancing, charge time and the eFuse

### 5.1 Balancing
See §1.3. The balancers run only while input power is present. A swap does not change group voltages much, because one series current flows through all three groups. Mismatch comes from capacitance differences, so matching (B10) matters more than balancer speed.

### 5.2 Charge time back to full (Calculated)
These figures assume 93 % charger efficiency (Unverified), nominal C = 66.7 F (stack, new) and a maximum of 86.7 F (+30 %).

| Situation | Charge needed | Charging limited by | Time |
|---|---|---|---|
| After a typical swap (16 W × 10 s; new bank drops from 6.53 to about 5.9 V) | about 45 C | 5.33 A charge current | **about 9 s** |
| After a full 25 W × 10 s swap at −20 °C, end of life (39.5 F, 6.39 V down to about 5.0 V) | about 309 J | Input limit with 25 W load on a pack at cutoff: (4.10 − 2.98 A) × 8.4 V × 0.93 = 8.7 W | **about 36 s** |
| Bank drained to the 4.28 V floor (pack left out, then refitted), +30 % C | 194 C or 1,050 J | 5.12 A min (38 s), or 8.7 W input-limited (120 s) | **38 to 120 s** |
| First charge from 0 V, nominal / +30 % C | 435 C / 565 C | 5.33 A / 5.12 A, longer under heavy load | **82 to 110 s**; up to about 210 s at 25 W on a weak pack |

A second swap inside these times gets a partly charged bridge (owner decision 6). Software reads CAPGD (asserted at 92 % of the regulated level, Verified, p5) or meas_vcap before it reports the bridge ready.

### 5.3 Input current limit and the eFuse
- **Total input current.** The LTC3350 limits load plus charger current to IIN(MAX), but only by reducing charge current. It never limits the load (Verified, p15). With 7.5 mΩ the worst case is 32.96 mV / 7.425 mΩ = 4.44 A. Quiescent and gate-drive currents (about 22 mA) are not included (p22). The total is 4.46 A, against the eFuse's 5.17 A minimum limit (bridge study §4). That leaves 0.71 A of margin. Calculated.
- **Correction.** The bridge study's 6.4 mΩ gives up to 32.96 / 6.336 = **5.20 A**, which is above the 5.17 A eFuse minimum. A heavy load plus charging could then trip the eFuse at tolerance extremes. This is listed as a record conflict.
- **Load priority.** At 35 W on a pack at cutoff (4.17 A), the charger gets almost nothing. That is the intended behaviour. D-019's 5.56 A eFuse limit still governs the load.
- **Reinsertion during backup.** When the pack returns, the eFuse ramps its own output bulk as before. Then the input ideal diode turns on and lifts +VBUS_HOLD from 7.0 V to the pack voltage. INFET rises in 560 µs with 3.3 nF of gate capacitance (Verified, p5). That works out to about 18 µA of drive (Calculated). 300 µF lifted by 5.6 V in 560 µs is 3.0 A, plus 3.6 A of load, which is above the 5.56 A limit. **Proposed:** add gate capacitance to INFET for about 2.5 ms total (about 15 nF), which lowers the inrush to about 0.7 A. Calculated, Unverified until B8.
- **Interaction with BQ25798.** When USB-C power is present, SYS stays up with no pack and the bridge is not used. Charging the pack is upstream of the eFuse and does not count against IIN(MAX).

## 6. Signals and supervisor (no change to D-044)
- +VBUS_HOLD holds 7.0 V in backup. That is 1.0 V above SVS4's 6.0 V threshold (D-044, K-6), so a swap causes no reset. When the bridge runs out, the bus falls through 6.0 V and RESET4 shuts the CM5 down in order.
- The stack (≤ 6.66 V) is always below the 7.0 V backup point. Backup therefore starts in step-up mode straight away, and the output-ideal-diode and body-diode phase described on p30 does not occur.
- BRIDGE_ACTIVE_N (PFO), PACK_PRESENT and the LTC3350 SMBALERT need GPIOs. Those allocations belong to GHO-9 and are not proposed here.

## Proposed record text

For the records owner to apply only if the project owner accepts the defaults. The numbers are left blank.

**[v1-selections.md](v1-selections.md), B-24 row:**
"Pack-swap bridge | Analog Devices LTC3350IUHF#PBF backup controller. 6 × KYOCERA AVX SCCV60B107SRB (100 F, 2.7 V) as 3S2P, charged to 6.525 V (VCAP DAC code 12). RSNSC 6 mΩ, RSNSI 7.5 mΩ, Bourns SRP1265A-4R7M, 500 kHz, +VBUS_HOLD 7.0 V in backup. Bank in a tray under the carrier. Design and calculations: [v1-bridge-selection.md](v1-bridge-selection.md). | Selected working default, not frozen. Bench gates in v1-bridge-selection.md (B1 to B10); GHO-30 load and shutdown energy can change the population."

**[decisions.md](../decisions.md), new row (number assigned by the records owner):**
"D-0xx | 2026-10-xx | B-24 working default: LTC3350 (I grade) with 6 × AVX SCCV60B107SRB in 3S2P at 6.525 V, RSNSC 6 mΩ, RSNSI 7.5 mΩ, SRP1265A-4R7M, bank in a tray under the carrier (+23 mm radio-body depth). | Closes GHO-38's desk gates. The conservative budget at −20 °C, end of life and 25 W has +47 J of margin (445 J usable against 334 J). Supersedes the 4S2P/8.0 V screen and the 4 × 50 F population. The 35 W stress case is not covered; break-even is 26.3 W. Reopen if GHO-30 measures more than 24 W sustained."

**[v1-hot-swap-bridge.md](v1-hot-swap-bridge.md):**
- Result table, "Evaluated population" row: "Working default 3S2P SCCV60B107SRB at 6.525 V; see v1-bridge-selection.md."
- §S2, charge voltage paragraph: replace "held at 8.0 V, 2.0 V per cell" with "held at 6.525 V, 2.175 V per cell, three cells (v1-bridge-selection.md §1)". Keep the reasoning about the step-down charger.
- §4, Stack recharge row: "RSNSC 6 mΩ (5.33 A charge, 7.94 A backup ceiling). RSNSI 7.5 mΩ limits total input to 4.44 A worst case, under the eFuse's 5.17 A minimum."
- BOM table: "LTC3350IUHF#PBF"; "N-MOSFET 40 V: 2 × CSD18514Q5A switches, 2 × CSD18512Q5B ideal diodes"; "Inductor Bourns SRP1265A-4R7M"; "RSNSC 6 mΩ, RSNSI 7.5 mΩ, WSL2512 ±1 %"; "Supercapacitors 6 × SCCV60B107SRB, matched ±5 % per group".

**[v1-rf-coexistence.md](v1-rf-coexistence.md) §3.2, LTC3350 row:** add "Top-side alternative: board X 55 to 85, Y 1.5 to 23 meets the same rules (v1-bridge-selection.md §3.5)". The owner chooses the side.

**[v1-stackup-routing.md](v1-stackup-routing.md), supercapacitor-path row:** "7.94 A average ceiling at 6 mΩ RSNSC, 10.94 A peak" in place of "9.4 A average screening ceiling at 5 mOhm RSNSC, 13.1 A peak".

**Firmware `docs/hardware/v1-mechanical/parts.yaml` (GHO-7):**

```yaml
  - id: bridge_stage
    name: LTC3350 power stage (IC, SRP1265A-4R7M, 4 FETs, sense resistors, CCAP)
    kind: power_region
    status: assumption
    switching: true
    source: "v1-bridge-selection.md §3.5: top side, inductor 14.0 x 12.8 x 6.5 mm max"
    x: 55.0
    y: 1.5
    w: 30.0
    d: 21.5
    z0: 0.0
    h: 6.5
  - id: bridge_bank
    name: 6 x AVX SCCV60B107SRB (3S2P) bridge tray under the carrier
    kind: keepout
    status: assumption
    source: "v1-bridge-selection.md §3.2 option A: cells Z -24.1 to -5.1"
    x: 0.0
    y: 0.0
    w: 138.0
    d: 67.0
    z0: -24.6
    h: 19.5
    bans: [power_region, ic, connector]
```

Also move `pack_contacts` to `z0: -35.0` (option A) and add a WR-MPC4 header envelope at about X 80.5, Y 2 once the vertical-header drawing is read.

## Decisions for the project owner

Each decision has a recommended default.

1. **Bank technology and population.** Choices: 3S2P EDLC (6 cells); 4S2P EDLC (8 cells, two layers); or fund a hybrid lithium-ion-capacitor study that might avoid the tray. **Default: 3S2P EDLC.** It is the only option with verified data that fits in one layer and passes 25 W at −20 °C and end of life.
2. **Where the bank goes.** Choices: A, a tray under the carrier with the pogo column under one cell (+23 mm radio-body depth, no pack change); or B, move and rotate the contact array into the bank's centre gap (+12.6 mm, GHO-8 rework of M-10, M-11 and M-15 to M-18). **Default: A.** It changes no pack record. Choose B only if the 10 mm saved is worth reopening the pack gates.
3. **Charge level.** Choices: code 12 (6.525 V, 2.175 V per cell) with firmware stepping to code 13 (6.75 V) when the measured capacitance falls; or code 13 from the start. **Default: code 12, then step to 13 at end of life.** Code 13 adds 57 J but runs at 2.295 V worst case, right at the 85 °C voltage limit.
4. **Sizing load.** Choices: size for 25 W (the bridge study's peak-held row), with 26.3 W break-even and the 35 W stress case not covered; or size for 35 W, which needs roughly two to three times the cells. **Default: 25 W.** D-019 calls 35 W a capability target, not a load. Reopen if GHO-30 measures more than 24 W sustained at the bus.
5. **Bank fuse.** Choices: fit a fuse at the bank board (costs about 20 J of margin through +10 mΩ), or leave it unfused. **Default: fit it.** An unfused 1.4 kJ bank on a harness inside a sealed radio is a fire risk.
6. **Back-to-back swaps.** Choices: accept a partly charged bridge for a second swap within about 40 s (worst case), or size for two swaps. **Default: accept.** Software shows bridge state before the operator pulls the pack.
7. **Power-stage side.** Choices: top side at board X 55 to 85, Y 1.5 to 23 (lower loss, no tray-depth cost); or bottom side per the RF and stackup records (SRP1245A, about +2 mm). **Default: top side.** It meets every RF rule. The side is the only difference from the records.

## Bench measurements that can still change the selection

The first two belong to [GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30). The rest run on the V1 board under [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23) and the bridge study's bench list.

| ID | Measurement | Selection holds if | If not |
|---|---|---|---|
| B1 | **GHO-30:** full-node plus accessory power at +VBUS_HOLD, the highest 10 s mean, at the D-028 endpoints | ≤ 26.3 W (code 12) or ≤ 27.9 W (code 13) | Add cells (4S2P or a second layer), or decision 1's study |
| B2 | **GHO-30:** clean-shutdown energy and time | ≤ about 90 J (break-even 18.1 s at 5 W) | Raise the poweroff trigger; at worst add cells |
| B3 | Gloved swap time, 95th percentile (bridge study test 1) | ≤ 11.4 s at 25 W (longer at the measured B1 load) | As B1 |
| B4 | Capacitance and DC-5 s ESR of the six cells at −20 °C and 25 °C, plus aged-cell emulation | Stack factor ≥ 0.530; total stack ESR ≤ 122 mΩ including path | Change the cell or add a group cell |
| B5 | Backup efficiency at 3.5 V and 7.94 A input, and the step-up duty limit at −18 °C | ≥ 85.7 % | Switch to 5 mΩ RSNSC (§2.1) or lower-loss parts |
| B6 | Path resistance: connector pairs, harness, fuse | Fits inside B4's 122 mΩ | Shorter harness or more contacts |
| B7 | Cell temperature in the tray at the D-028 hot endpoint, sealed, at full load (GHO-23 T3/T4) | ≤ 85 °C at ≤ 2.3 V per cell | Lower the charge code, add insulation, or move the bank |
| B8 | Pack reinsertion during backup: INFET inrush, eFuse current, handover | No eFuse trip at 25 W | Increase INFET gate capacitance |
| B9 | LTC3350 meas_cap and meas_esr against B4 | Within 10 % | Firmware health thresholds |
| B10 | Group voltages during a full-rate charge, groups matched to ±5 % | Shunts only clamp at 2.30 V; charge completes | Tighter matching |

## Record conflicts

These were found, not resolved. README rule 6 asks for a Linear issue for each one. This file opens none.

1. **Controller grade.** The bridge study BOM lists LTC3350**E**UHF#PBF. Rev. D guarantees the E grade only from 0 °C junction, and D-028 reaches −17.8 °C. The I grade is needed.
2. **FET voltage.** The bridge study BOM says "30 V class". The eFuse output can reach its 32.8 V clamp (B-15), and the output ideal diode sees the highest VIN (Rev. D p30). 40 V is needed.
3. **RSNSI.** The bridge study's 6.4 mΩ gives up to 5.20 A worst case, above the 5.17 A eFuse minimum it was meant to stay under.
4. **Stack voltage and cell count.** The bridge study holds a 4-cell stack at 8.0 V. This file proposes 3 cells at 6.525 V. D-027's rationale still names "four 50 F cells" as a candidate, and the bridge study already calls that superseded.
5. **Power-stage side.** [v1-rf-coexistence.md](v1-rf-coexistence.md) §3.2 and [v1-stackup-routing.md](v1-stackup-routing.md) (L8) place the LTC3350 stage on the bottom side. This file's default is the top side (decision 7).
6. **Radio-body height.** The thermal model ([v1-thermal-update-tray.md](v1-thermal-update-tray.md)) uses a 50 mm body: 27 mm plus option A's 23 mm. The floorplan already needs more than 26.66 mm above the PCB for the feed-through, so the real body may be taller; 66 mm is run as a sensitivity case. The body height is not recorded yet (GHO-7).
7. **Bottom-side height.** parts.yaml assumes 3 mm for every bottom-side part. The 5.0 to 6.5 mm bridge inductor (if on the bottom) and probably the LM76005 inductors exceed that. The tray depth above uses 3 mm.
8. **LTC3350 frequency.** [v1-rf-coexistence.md](v1-rf-coexistence.md) says the nominal frequency is not recorded. Rev. D gives 500 kHz nominal, 495 to 505 kHz at 25 °C and 490 to 510 kHz over temperature (p4). This is informational and needs no change to the analysis.

## What remains unverified

- Cell ESR and capacitance at −20 °C (typical curves only), cell temperature in the tray, and lifetime at 2.175 V and the real interior temperature (B4, B7).
- Converter efficiency at the 3.5 V floor (90 % assumed), the step-up duty limit below 25 °C, and charger efficiency (93 % assumed) (B5).
- The measured load and shutdown energy (GHO-30, B1 and B2). Every margin above depends on them.
- The radio-interior dimensions, plate thickness, 10.4 mm pogo column, 3 mm bottom-side heights and pack-to-board mapping. All are parts.yaml assumptions, not CAD.
- Exact WSL2512 6 mΩ and 7.5 mΩ value availability, the vertical WR-MPC4 header and the small-wire crimp MPNs, the bank fuse MPN, and the NTC circuit.
- The INFET gate-capacitance inrush fix (B8).
- The AVX cell vent position and the end clearance it needs (not shown on the p4 drawing).
- Stock, price and lead time for every part. None were checked.
- Hybrid lithium-ion capacitors and other controllers. No datasheets were obtained.

## Sources

| Source | Revision | Used for |
|---|---|---|
| Analog Devices [LTC3350 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc3350.pdf) | Rev. D. Read from the [LCSC copy](https://datasheet.lcsc.com/datasheet/pdf/a3481fb78737e186956209c922e5015c.pdf?productCode=C580711) because analog.com refused scripted access on 2026-10-09. | Limits, equations, grades, frequency, ideal diodes, balancer, shunts, address |
| KYOCERA AVX [SCC Series](https://datasheets.kyocera-avx.com/AVX-SCC.pdf) | TDS-SC-0001 Rev 11 | Cell ratings, ESR, life limits, temperature curves, dimensions |
| Bourns [SRP1265A](https://www.bourns.com/docs/Product-Datasheets/SRP1265A.pdf) and [SRP1245A](https://www.bourns.com/docs/Product-Datasheets/SRP1245A.pdf) | REV. 06/24 | Inductor |
| TI [CSD18514Q5A](https://www.ti.com/lit/ds/symlink/csd18514q5a.pdf) | SLPS625A, January 2017 | Switch FETs |
| TI [CSD18512Q5B](https://www.ti.com/lit/ds/symlink/csd18512q5b.pdf) | SLPS624A, March 2019 | Ideal-diode FETs |
| Vishay [WSL series](https://www.vishay.com/docs/30100/wsl.pdf) | Document 30100, 23-Nov-2023 | Sense resistors |
| Würth [649008227222](https://www.we-online.com/components/products/datasheet/649008227222.pdf), [649008113322](https://www.we-online.com/components/products/datasheet/649008113322.pdf), [64900113722](https://www.we-online.com/components/products/datasheet/64900113722.pdf) | 002.001 2019-12-20; 002.001 2019-12-20; 001.001 2025-02-18 | Bank connector |
| ghostnet-labs/firmware `docs/hardware/v1-mechanical/` | branch 24.10 at 3ac1495 | Floorplan, heights, pogo zone, frame mapping |
| This repository: [v1-hot-swap-bridge.md](v1-hot-swap-bridge.md), [v1-battery-pack.md](v1-battery-pack.md), [v1-battery-pack-gates.md](v1-battery-pack-gates.md), [v1-netplan-blocker-proposals.md](v1-netplan-blocker-proposals.md), [v1-rf-coexistence.md](v1-rf-coexistence.md), [v1-stackup-routing.md](v1-stackup-routing.md), [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md), [decisions.md](../decisions.md) | main at 73368aa | Requirements, power path, existing candidate values |
