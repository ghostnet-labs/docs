# V1 battery pack CAD gate results and protection proposal

**Owner:** [GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8), which covers designing the V0 battery pack and passing its CAD review gates.
**Status:** First envelope evaluation, 2026-10-09. Nothing here changes a register. The geometry values (M-nn) live in [v1-battery-pack.md](v1-battery-pack.md) and the part selections (B-nn) in [v1-selections.md](v1-selections.md). This file records gate results against those values, plus candidate parts for the open B-10 items. Every part below is a **Candidate**, not Selected.

**Tooling.** The model is firmware [`docs/hardware/v1-mechanical/pack.py`](https://github.com/ghostnet-labs/firmware/blob/gho8-pack-gates/docs/hardware/v1-mechanical/pack.py), with inputs in [`pack.yaml`](https://github.com/ghostnet-labs/firmware/blob/gho8-pack-gates/docs/hardware/v1-mechanical/pack.yaml) and generated output in [`out/pack_report.md`](https://github.com/ghostnet-labs/firmware/blob/gho8-pack-gates/docs/hardware/v1-mechanical/out/pack_report.md). It is on branch `gho8-pack-gates`, commits [70761c1](https://github.com/ghostnet-labs/firmware/commit/70761c1a79e5538bbc8778caa18987111de2fd0a) and [38ac40d](https://github.com/ghostnet-labs/firmware/commit/38ac40dd6fbb8fab2f6052d314276bcadad4f915).

The script builds every body in the "CAD assembly bodies" list of v1-battery-pack.md as an envelope. Each body is either taken from its M-nn row or marked as an assumption in `pack.yaml`. The script then checks the parts of the gates that an envelope model can check. The carrier floorplan check (`floorplan.py`, GHO-7) is unchanged and still passes.

An envelope model can prove that something does not fit. It cannot freeze a dimension, so a PASS below means "no conflict found at the M-nn values with the stated assumptions".

## Summary

| Gate | Result | Why |
|---|---|---|
| 1. Fit check | **Fail** (3 items) | Every body stays inside the 145 x 74 mm footprint, and the D-017 budget sums to 145 mm on the cord centerline. Three items fail. (a) The gasket gland, which is wider than the cord, runs 1.45 mm into the M-20 latch zone. (b) No Southco C3-family catch fits the 7 mm latch zone. (c) Two items are tight: cell spacing is exactly at the M-06 minimum, and there is 1.4 mm of end room per cell. |
| 2. Motion check | **Can't evaluate** (first-order pivot check passes) | The hook-first pivot engages the bosses (1.5°) before the probes (0.37°) and the gasket (0.24°). Probe scrub is about 40 µm. The hook profiles, the keeper path and the latch travel are not modeled because M-19 and M-20 are still CAD-verify and the B-13 drawing was not obtained. |
| 3. Tolerance study | **Fail as specified** (pass with two changes) | The probe stack passes only if both PCBs are face-referenced. The gasket squeeze reaches 30.2 % worst case against the M-16 limit of under 30 %, and drops to 9 % at the other extreme. The plunger-on-pad position check passes. All tolerance contributors are assumptions until the processes are chosen. |
| 4. Structural review | **Can't evaluate** | No enclosure material, hook geometry or load case exists yet. Load paths and weak sections are listed below. The latch preload estimate suggests a 5 lbf-class catch cannot hold the seal closed. |
| 5. Electrical and mechanical review | **Can't close** (geometry checks pass) | The pad gap is 1.5 mm and the land to the gland is 8.3 mm (at least 5 mm is required). The pin-position allocation is not fixed by M-11, and a proposal is given below. The pad finish (M-13) is still CAD-verify. |

## Gate 1: fit check

The checks covered the footprint, the M-02 height, pairwise 3D collisions between all bodies, the design-rule keepouts (contact cavity, gasket gland, pogo travel cylinders, boss engagement volumes and hard-stop lands), cell spacing and the D-017 budget.

Results:

- **Footprint and height: pass.** All bodies lie within X 0 to 145 mm and Y 0 to 74 mm. The Z stack over the cells is 45.7 mm, within the 46 mm of M-02. That figure uses the M-02 midpoint of 1.75 mm insulation and assumes 2.0 mm top and bottom walls. With 2.0 mm insulation the stack is 46.2 mm, so the cell stack alone uses up the M-02 margin. M-02 already allows the height to grow.
- **D-017 length budget: closes on centerlines only.** The budget is 6 + 68 + 21 + 5 + 34 + 11 = 145 mm. However, the 34 mm gasket zone is a cord-centerline span. The gland must be wider than the 2.0 mm cord: about 2.9 mm, scaled from Parker's face-seal groove width for a 0.070 in cord ([Parker O-Ring Handbook ORD 5700, Design Chart 4-3](https://discover.parker.com/Parker-ORing-Handbook-ORD-5700)). That puts the gland's outer edge at X 135.45 mm, 1.45 mm into the M-20 latch zone (X 134 to 141). In the model, the gasket and the latch placeholder overlap by 32 mm³. **Fail.**
- **Latch envelope: fail if B-13 resembles the C3 family.** The [Southco C3 push-to-close latch drawing](https://www.marek.eu/katalog-obrazku/produkt-8479/19311-c3-en.pdf) (a distributor copy) shows a snap-in catch body of about 26.6 x 43 x 17 mm and a side-mount catch 28.2 mm wide. None of these dimensions fits the 7 mm X span of M-20. The C3-99-107-055 drawing itself could not be retrieved: southco.com and DigiKey refused scripted access. The design rule's fallback applies ("substitute a smaller stocked commercial latch").
- **Cells: warning.** All seven adjacent can pairs sit at 1.00 mm, exactly the M-06 minimum. The "separate insulation bodies" and any holder ribs must fit inside that 1.00 mm. The 68 mm cell zone leaves 1.40 mm per cell end for the nonconductive end support, the interconnect and the expansion allowance. No cell intrudes into a keepout or touches a wall. The cans are 4.1 mm from the sidewalls and 1.75 to 2.05 mm from the top and bottom walls, through the insulation.
- **Keepouts: pass.** No hardware intrudes into the contact cavity, the probe travel cylinders, the boss engagement volumes or the hard-stop lands. The BMS envelope, the protection placeholder and the harness keepout are all in the bay, the corridor slot and the M-22 zone.

Ways to clear the gland and latch overlap. These are proposals, not decisions:

1. **Shorten the gasket on the latch side (preferred).** Make the centerline X 100 to 131 (31 x 26 mm), shrink the dry cavity to X 103 to 128, and keep the radio-side probe opening at least 26 mm long (X 103 to 129.5) so that the 24 mm daughterboard still clears it. The model's what-if run with these values clears the overlap. It leaves 1.55 mm of wall between the gland and the latch zone and 5.3 mm of land from the pad edge to the gland, against the 5 mm M-15 minimum. The M-10 contact center does not move, so the carrier floorplan is unaffected.
2. **Shift the whole contact and gasket group toward the hook end.** A 1.5 mm shift only just clears the latch zone. Under the carrier mapping assumed in `parts.yaml`, it also moves the pogo zone onto the charger. A 3 mm shift fails the floorplan check: the `charger` part intrudes into `pack_contacts`. This option is not recommended without re-checking GHO-7.

The latch envelope itself needs a new or confirmed B-13 part. See gate 4 for the retention problem.

## Gate 2: motion check (pivot pre-check only)

The model assumes the pack pivots about the hook engagement point (X 3.5 mm, Z −2 mm, an assumption). It computes the angle, measured from closed, at which each feature meets its mate:

| Feature | Engagement | Angle | Order while closing |
|---|---|---|---|
| Locating bosses (X 117) | 3.0 mm (assumed) | 1.51° | 1st |
| Probes, X 111 column | 0.69 mm nominal stroke | 0.37° | 2nd |
| Probes, X 123 column | 0.69 mm | 0.33° | 3rd |
| Gasket, hook side (X 100) to latch side (X 134) | 0.40 mm squeeze | 0.24° to 0.18° | last |

The M-18 order, bosses before the probes and before meaningful gasket compression, holds. Over the probes' travel the tips slide about 40 µm along X, and the pad is tilted 0.37° at first touch. Both are negligible.

On removal, the X 123 column breaks first and the X 111 column last. The pin allocation proposal below uses this ordering.

Not evaluated:

- the hook and keeper profiles, and therefore the true pivot
- the latch keeper path and the over-travel
- whether the gasket scrapes the keepers or the boss tapers

## Gate 3: tolerance study

All contributors are assumptions (listed in `pack.yaml`) until the enclosure process and the PCB fabricator are chosen.

**Probe working height.** The [Mill-Max 7911-0-15-20-86-14-11-0 data sheet](https://www.mill-max.com/products/datasheet/7911-0-15-20-86-14-11-0) gives the probe dimensions, read 2026-10-09:

| Probe value | Data sheet |
|---|---|
| Initial height | 7.493 mm |
| Mid-stroke | 0.711 mm (rated travel) |
| Max stroke | 1.397 mm |
| Standard length tolerance | ±0.15 mm |
| Spring force | 25 gf initial, 100 gf mid-stroke |
| Current | 11 A at a 30 °C rise; 8.8 A derated |
| Contact resistance | 40 mΩ max |

M-12 quotes 6.10 to 7.49 mm as the worst-case working height. That is the probe's full stroke at its nominal length. Including the ±0.15 mm length tolerance, the working height must stay between 6.25 mm (no bottoming) and 7.14 mm (at least 0.2 mm of preload). The two reference cases give:

| PCB referencing | Stack ± (worst case / RSS) | Stroke range | Result |
|---|---|---|---|
| Both PCBs located by their contact faces against datum shoulders | 0.20 / 0.09 mm | 0.34 to 1.04 mm | **Pass** (inside M-12 ±0.25) |
| Both located by their back faces, so the 1.6 mm ±10 % board thickness enters the stack | 0.52 / 0.24 mm | 0.02 to 1.36 mm | **Fail**: no preload at one extreme, 0.03 mm from bottoming at the other |

**Gasket squeeze.** The values are a 2.0 mm cord with a 1.6 mm nominal compressed height (20 %, M-16). The gland and the face gap set by the hard stops are ±0.15 mm worst case (three ±0.05 contributors). For comparison, Parker's face-seal chart allows 19 to 32 % squeeze for a 0.070 in cord, which has a ±0.003 in cross-section tolerance.

| Cord tolerance | Squeeze, worst case | Squeeze, RSS | Against M-16 (under 30 %) |
|---|---|---|---|
| ±0.076 mm (molded O-ring class) | 9.0 to 30.2 % | 14.2 to 25.8 % | Marginal fail (worst case) |
| ±0.15 mm (extruded cord, assumed) | 5.4 to 32.6 % | 11.3 to 28.7 % | Fail |

The 20 % nominal sits low in Parker's band, so the minimum squeeze falls well below 19 %. Proposed fix: take the gasket as a precision molded loop or a cord to an equivalent tolerance, raise the nominal squeeze to about 22 to 25 %, and hold the gland-plus-face-gap stack to ±0.10 mm worst case. Confirm against the chosen gasket supplier's data.

**Plunger on pad.** The radial allowance for the 0.813 mm plunger on a 2.5 mm pad is 0.84 mm. The position stack is 0.49 mm worst case and 0.21 mm RSS. **Pass.**

## Gate 4: structural review (inputs only)

The gate cannot be evaluated without four inputs:

- the enclosure material and process (M-03)
- the hook and keeper geometry (M-19)
- a confirmed latch (B-13)
- the drop and shock load cases

Pack mass is at least 288 g of cells: six M35A cells at 48 g max each ([Molicel M35A data sheet, distributor copy](https://www.imrbatteries.com/content/molicel_m35a.pdf)).

The load paths to analyse are:

- **Hooks.** Shear and pull-out at the X 0 end. M-19 requires the hooks to tie into the sidewall and end-wall ribs, so the 4 mm end wall and the two sidewalls carry it.
- **Latch.** This load path carries most of the seal and probe preload.
- **Hard stops.** These carry the compression on seating.
- **Bosses.** These carry lateral shear.

The weak sections are:

- the interface plate around the 28 x 20 mm cavity cut-out plus the gland groove, which leaves the least material next to the latch pocket
- the X 141 to 145 end wall with the latch pocket in it
- the hook roots
- the unsupported top and bottom walls across the 21 mm M-22 spare zone if it stays empty

**Latch preload estimate.** The estimate is a moment balance about the hooks, with the gasket and probes centred at X 117 and the latch at X 137.5. The gasket load is 20 to 40 N, read approximately from Parker ORD 5700 Fig. 2-4 (about 1 to 2 lbf per inch at 20 % squeeze over a 115 mm centerline). The probes add 7.8 N. On those numbers the latch must hold about **24 to 41 N** before any shock load.

A 5 lbf (22 N) grabber-class catch, as described for B-13, does not cover this, and it releases by pull rather than by a positive lock. That is a second reason, besides the envelope, to revisit B-13 against the design rule, which calls for a positive recessed latch, or two symmetric catches if one seals unevenly. This is an estimate: replace the gasket load with the supplier's compression data.

## Gate 5: target pads and contact allocation

The geometry checks pass:

- **Pad gap.** On the 4.0 mm grid, M-13's 2.5 mm minimum pads leave a 1.5 mm edge gap. That is far above the creepage needed at 12.6 V, so the practical risk is debris bridging inside the dry cavity, not voltage.
- **Land to the gland.** The land from the outermost pad edge to the gland's inner edge is 8.3 mm (at least 5 mm is required).
- **Land to the cavity wall.** The land to the cavity wall is 6.75 mm. Under gate-1 option 1 it becomes 3.75 mm.

**Proposed pin positions.** M-11 lists the signals but not where they go. Columns run X 111, 115, 119 and 123 from the hook end; the two rows are Y 35 and Y 39.

| Column | Contacts | Reason |
|---|---|---|
| X 111 | BAT− ×2 | Nearest the hooks: makes first and breaks last (gate 2) |
| X 115 | BAT+ ×2 | Next to BAT− for a short, low-inductance loop into the pack protection (design rule) |
| X 119 | SDA, SCL | Away from both the first-break and last-break columns |
| X 123 | PACK_PRESENT/ID, FET enable | Breaks first on removal, which gives the hot-swap logic ([GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38)) an early warning |

**Optional use of the spare contact.** The spare or wake contact could become the BQ76942 BOTHOFF input (DFETOFF pin configured as BOTHOFF, [datasheet](https://www.ti.com/lit/ds/symlink/bq76942.pdf) §12.7). The arrangement would work like this:

- A pack-side pull asserts BOTHOFF when the pack is out of the radio.
- The radio ties that contact to BAT− to release it.

The benefits:

- The exposed pads on a removed pack are dead.
- The power pads make contact before the FETs turn on.
- The FETs turn off before the power pads break.

The pin polarity must be confirmed in the BQ76942 technical reference manual. This option is a proposal and depends on the hot-swap design under GHO-38.

## Electrical proposal: protection, current sense and thermistors

These requirements come from v1-reference.md §11 and D-019:

- trip above 6 A continuous
- tolerate the 11 A, 25 ms eFuse pulse
- 2.8 to 3.0 V per cell cutoff
- charge within 0 to 45 °C

The other inputs are the BQ76942 (B-10) and 3S2P M35A cells (B-11).

### Protector IC

**Primary: keep the TI BQ76942 (B-10).** According to its [data sheet SLUSE14B](https://www.ti.com/lit/ds/symlink/bq76942.pdf), it is a 3-series to 10-series monitor and protector with these features:

- Supply range of 4.7 to 55 V.
- High-side N-FET drivers with an integrated charge pump. Drive is 10 to 13 V above BAT for VBAT ≥ 8 V, and 8 to 13 V below 8 V.
- A coulomb counter input of ±0.2 V across SRP and SRN.
- Overcurrent thresholds: OCD1, OCD2 and OCC from 4 to 200 mV in 2 mV steps, with delays of 10 to 425 ms.
- Short-circuit (SCD) thresholds of 10 to 500 mV, with delays of 15 to 450 µs.
- Up to nine thermistor inputs with an 18 kΩ pull-up intended for the Semitec 103AT.
- A FUSE drive pin for permanent-fail fusing.

At 3S, the unused VC inputs are shorted per the data sheet's Figure 10-2.

**Secondary (independent overvoltage): TI BQ7721602PWR.** The [BQ77216 data sheet SLUSE36L](https://www.ti.com/lit/ds/symlink/bq77216.pdf), Table 4-1/4-2, gives:

| Parameter | Value |
|---|---|
| Overvoltage trip (OVP) | 4.325 V |
| OVP hysteresis | 0.1 V |
| OVP delay | 1 s |
| Undervoltage trip (UVP) | 2.25 V |
| Overtemperature (OT) | 70 °C |
| Open-wire detection | Enabled |
| COUT output | Active high, 6 V drive |
| Package | 24-pin TSSOP |
| Cell count | 3S to 16S |

COUT drives the heater FET of the fuse below. Caution: overtemperature and open-wire faults also assert COUT, so with this wiring a 70 °C secondary overtemperature blows the fuse. That outcome is a deliberate owner choice; otherwise, pick a variant or wiring that avoids it.

**Pack fuse: Littelfuse ITV4030L1212**, a three-terminal SMD battery protector for 3S ([ITV4030 12A series](https://www.littelfuse.com/products/fuses-overcurrent-protection/battery-protector/itv-three-terminal-fuses/itv4030-12a/itv4030l1212)). Its ratings:

| Parameter | Value |
|---|---|
| Rated current | 12 A at 40 °C |
| Derating | 10 A at 60 °C |
| Maximum voltage | 36 V DC |
| Interrupting current (Ibreak) | 50 A |
| Heater operating voltage | 7.4 to 13.8 V |

One heater is driven by the BQ76942 FUSE pin (permanent fail) and by the BQ7721602 COUT. The rating values come from the product page summary because the PDF could not be retrieved, so they are **Unverified**.

### Protection FETs

The FETs are two N-channel devices, back to back in the high side, driven by the BQ76942 CHG and DSG outputs.

| Candidate | V_DS | V_GS | R_DS(on) max at 10 V | Package | Data sheet |
|---|---|---|---|---|---|
| **TI CSD18512Q5B** (preferred) | 40 V | ±20 V | 1.6 mΩ (1.3 typ) | SON 5 x 6 | [SLPS624A](https://www.ti.com/lit/ds/symlink/csd18512q5b.pdf) |
| TI CSD18540Q5B (more voltage margin) | 60 V | ±20 V | 2.2 mΩ (1.8 typ) | SON 5 x 6 | [SLPS488B](https://www.ti.com/lit/ds/symlink/csd18540q5b.pdf) |
| TI CSD17573Q5B (not preferred) | 30 V | ±20 V | 1.0 mΩ (0.84 typ) | SON 5 x 6 | [SLPS492B](https://www.ti.com/lit/ds/symlink/csd17573q5b.pdf) |

The BQ76942 gate drive of up to 13 V is inside ±20 V. The 40 V part gives about 3.2 times margin over 12.6 V for turn-off spikes when a short is interrupted. At 6 A, the two CSD18512Q5B FETs dissipate about 0.12 W at 25 °C. At the 11 A pulse they dissipate about 0.39 W.

Add a PACK+ to PACK− TVS and the BQ76942 pre-discharge (PDSG) path to limit inrush into the radio's input. Choose the TVS with the schematic, together with the radio-side SMBJ33CA (B-17).

### Current sense

**Candidate shunt:** Vishay Dale WSK2512, 2 mΩ, ±1 %, four-terminal, 1 W at 70 °C. Under the [WSK2512 data sheet](https://www.vishay.com/docs/30108/wsk2512.pdf) numbering, the part number is WSK25122L000FEA. It sits low side, between the cell stack's negative terminal and PACK−, with Kelvin sense lines to SRP and SRN. At 6 A it drops 12 mV and dissipates 72 mW. The ±0.2 V coulomb counter range covers ±100 A.

Proposed thresholds, using the BQ76942 accuracy from its data sheet §7.26:

| Protection | Setting | Nominal | Worst-case band | Check |
|---|---|---|---|---|
| OCD1 | 16 mV, 100 ms | 8.0 A | 7.0 to 9.3 A | Above 6 A; rides through the 11 A, 25 ms pulse on the delay; below the 10.4 A two-contact budget |
| OCD2 | 40 mV, 10 ms | 20 A | 18 to 22 A | Above the 11 A pulse |
| SCD | 60 mV, about 200 µs | 30 A | 19.5 to 40.5 A | Above 11 A; below the ITV 50 A Ibreak |
| OCC | 10 mV, 100 ms | 5.0 A | 4.0 to 6.3 A | Above the charge current |

The charge current itself depends on the cell rating. The M35A charge limit is 1.7 A per cell in one data sheet copy ([simpower](https://www.simpower.co.nz/wp-content/uploads/2023/05/INR18650M35A-Datasheet.pdf)) and 3.4 A in another ([imrbatteries](https://www.imrbatteries.com/content/molicel_m35a.pdf)). On the 1.7 A figure, the BQ25798 charge current must stay at or below 3.4 A for the pack. That is consistent with the 2.5 A planned in §11.

An alternative is a 1 mΩ WSK2512, which halves the dissipation, at the cost of current resolution and threshold granularity: 2 A per OCD step.

### Thermistors

**Candidate: Semitec 103AT-2.** It is a 10 kΩ ±1 %, B25/85 3435 K ±1 % NTC ([ATC Semitec AT series data sheet](https://static.rapidonline.com/pdf/30167_v2.pdf)). It is the thermistor the BQ76942's 18 kΩ pull-up and default calibration are intended for. Use four:

| NTC | Input | Placement | Purpose |
|---|---|---|---|
| T1 | BQ76942 TS1 (cell) | Upper-layer middle cell (Y 37), mid-length (X about 40), on the can face toward the top wall, inside the M-02 top insulation layer | Hottest cell: an interior cell nearest the warm radio shell (thermal plan item 6). Sets the charge over-temperature limit and the discharge over-temperature limit. |
| T2 | BQ76942 TS3 (cell) | Lower-layer outer cell (Y 17.4), mid-length, on the can face toward the sidewall (4.1 mm gap) | Coldest cell in cold ambient. Sets the 0 °C charge inhibit (D-028 ambient down to −17.8 °C). |
| T3 | BQ76942 multifunction pin (DCHG, DDSG or HDQ) set as FET thermistor | On the drain copper of the CHG/DSG FET pair | FET over-temperature |
| T4 | BQ7721602 TS | Next to T1 on the same cell | Independent 70 °C over-temperature |

Keep TS2 free for its wake-from-shutdown function. The 1.0 mm can gaps (M-06) cannot take a bead, so T1 and T2 sit in the insulation layers or the side gap; confirm the 103AT-2 bead diameter against the 1.75 mm layer. Bond each thermistor to the can with thermally conductive adhesive, under the cell insulation, and route its leads with the balance harness.

A surface-mount option for T3 is the Murata NCP15XH103F03RC (0402, 10 kΩ ±1 %). Arrow lists it as NRND and Murata's page could not be read, so it is **Unverified**; the leaded 103AT-2 on the FET copper avoids that question.

## Verification status

Every item below needs checking before the related record changes:

- **Southco C3-99-107-055 drawing.** It was not retrieved, so the latch findings use the C3 family drawing.
- **Littelfuse ITV4030L1212 ratings.** They come from the product page summary only.
- **Molicel M35A maximum charge current.** The data sheet copies conflict.
- **Parker compression load.** It is a rough reading of a chart.
- **Extruded-cord tolerance.** The ±0.15 mm value is assumed.
- **Model assumptions.** Every dimension marked as an assumption in `pack.yaml` needs confirming. These cover the wall thicknesses, the interface plate thickness, the pad-plane depth, the boss, hook and latch sizes, the BMS Z position and the pivot point.
- **BQ76942 BOTHOFF pin polarity.** Confirm it in the technical reference manual.
- **Stock and pricing.** Not checked for any candidate. DigiKey refused scripted access.

GHO-8 tracks these items.
