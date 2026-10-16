# V1 bridge: header-to-stage copper budget

**Status:** Candidate, 2026-10-16. This file adds the board-copper run that [v1-bridge-selection.md](v1-bridge-selection.md) §3.4 did not budget, now that the LTC3350 stage sits at X 119.5 to 136.5, Y 36 to 60 (firmware #71, docs #119). It edits no record and assigns no D, B or R number. The owning records still win (README rule 6). Nothing here is routed or measured.

## 1. Result

- **V1 working default (not asked of Justin): the bank header goes at the east end of the tray, under the stage.** This closes the WR-MPC4 header-position item. The firmware floorplan README still lists it as open until its next edit.
- With the header there, the VCAP+ run is about 30 mm and adds **about 3.4 mΩ** of board resistance (1.4 mΩ pour plus about 2 mΩ of vias). Total stack ESR is **102.1 mΩ** (107.1 mΩ with the 5 mΩ bank fuse), against the 122 mΩ break-even.
- Calculator margin is **+40.2 J** (+30.1 J with the fuse), against +47.0 J in the record. Gap lower bound 12.9 s (12.6 s with the fuse), against the 10 s target. The hold-up target is met.
- Drop on the run is **27 mV at the 7.94 A backup average and 37 mV at the 10.94 A peak**, about 1 % of the 3.50 V floor.
- The bounding case, a header at the far west end of the tray (130 mm run), would add about 8 mΩ and cut the margin to +30.9 J. Moving the header east returns about 5 mΩ. Nothing in the selection changes.

## 2. Inputs and assumptions

| Item | Value | Tag |
|---|---|---|
| Run length | **30 mm** with the header at the east end of the tray under the stage (default). Bounding case 130 mm: header at the west end (X about 5, Y about 33) | Working default for the header position; the 130 mm case is kept for comparison |
| Copper default (picked, not asked of Justin) | **8 mm wide pour on L8 (1 oz) in parallel with 8 mm on L5 (0.5 oz)**, joined by vias at both ends | V1 working default. 8 mm is above the 7.2 mm that [v1-stackup-routing.md](v1-stackup-routing.md) §5 gives for 10 A at 10 K rise on 1 oz alone. |
| Sheet resistance at 60 °C | 1 oz: 0.570 mΩ/sq. 0.5 oz: 1.140 mΩ/sq. Parallel: **0.380 mΩ/sq** | Calculated from copper resistivity 1.724e-8 Ω·m with 0.00393 per K. |
| Pour resistance | 30 / 8 = 3.75 squares × 0.380 = **1.4 mΩ** (130 mm: 16.25 squares, 6.2 mΩ) | Calculated |
| Via transitions | The stage is on the top side, the pour on L8 and L5: two transitions of about 8 vias each, about **1 mΩ each**, so about 2 mΩ | Assumption (0.3 mm drill, 1.6 mm board); sum real via resistance once routed |
| CAPRTN return | Taken as the solid ground planes (L2, L4, L7), so its drop is under 1 mΩ and not counted | Assumption |
| Allowance already in the old 15 mΩ | None for board copper | The 14 mΩ list is connectors, wires and bank bus only |

## 3. Effect on hold-up

`bridge_budget.py` at the §4 command with only `--stack-esr-ohm` changed (Calculated):

| Case | Stack ESR | Usable (J) | Margin (J) | Gap bound (s) |
|---|---:|---:|---:|---:|
| Record (§4) | 98.7 mΩ | 445.0 | +47.0 | 13.1 |
| **Default: header east, 30 mm run (+3.4 mΩ)** | 102.1 mΩ | 440.4 | +40.2 | 12.9 |
| Default plus bank fuse (+8.4 mΩ) | 107.1 mΩ | 433.6 | +30.1 | 12.6 |
| Bounding case, 130 mm run (+8 mΩ) | 106.7 mΩ | 434.2 | +30.9 | 12.6 |
| 130 mm run plus fuse (+13 mΩ) | 111.7 mΩ | 427.3 | +20.8 | 12.3 |
| 130 mm run, fuse and 7 mΩ tolerance (+20 mΩ) | 118.7 mΩ | 417.7 | +6.6 | 11.8 |

The last row is still positive but only 3.3 mΩ under the 122 mΩ break-even, and it is already at the aged, cold-cell corner that §1.2 uses. The 7 mΩ tolerance is an assumed stress value, not a datasheet figure. The run is worth shortening.

## 4. If the header cannot go east

1. A 10 mm pour instead of 8 mm lowers a 130 mm run from 6.2 to 4.9 mΩ.
2. Keep the harness at 2 × 16 AWG per pole; do not add contacts.
3. The 130 mm rows in §3 show the cost: about 16 J of margin.

## 5. Proposed record text

For the records owner to apply only if the project owner accepts. No IDs are assigned.

- **§3.4 interconnect:** the bank header sits at the east end of the tray, under the stage (V1 working default).
- **§3.4 path ESR budget:** add a row "Board copper, header to stage: 3.4 mΩ at 30 mm, 8 mm pour on L8 plus L5 (v1-bridge-stage-path.md)"; path ESR becomes about 17.4 mΩ (22.4 mΩ with the fuse). In §4 the stack total becomes 102.1 mΩ and the margin +40.2 J.
- **B6:** include the board run in the 122 mΩ check.

## 6. §4 re-run at the record's path budget

The records thread applied §5 in docs #121 (path 17.4 mΩ, so total stack ESR 83.7 + 17.4 = **101.1 mΩ**, 1 mΩ under the 102.1 mΩ used in §1 to §3 above). §4 of v1-bridge-selection.md was not re-run. Result at 101.1 mΩ, from `project/scripts/bridge_budget.py` (Calculated; `--stack-esr-ohm 0.1011`, every other flag as in §4 of the record):

```sh
python3 project/scripts/bridge_budget.py \
  --cells 3 --cell-f 200 --capacitance-factor 0.5922 --stack-esr-ohm 0.1011 \
  --start-v 6.3945 --terminal-min-v 3.5 --average-current-a 7.94 \
  --efficiency 0.9 --load-w 25 --gap-s 10 --shutdown-w 5 --shutdown-s 10
```

Key output: `open_circuit_stack_floor_v` 4.302, `usable_energy_j` 441.764, `gap_energy_bound_j` 341.459, `shutdown_reserve_bound_j` 58.103, `energy_margin_j` **42.203**, `gap_duration_lower_bound_s` 12.938, `gap_plus_reserve_budget_satisfied` true, `required_nominal_cell_f` 180.89.

| Quantity | Record (15 mΩ path, 98.7 mΩ) | Re-run (17.4 mΩ path, 101.1 mΩ) |
|---|---:|---:|
| Usable energy | 445.0 J | 441.8 J |
| Calculator margin | +47.0 J | **+42.2 J** |
| Gap lower bound | 13.1 s | 12.9 s |
| Required nominal cell | 178.9 F | 180.9 F (200 F fitted) |
| Break-even load | 26.3 W | **26.2 W** |
| Break-even gap at 25 W | 11.4 s | **11.2 s** |
| Break-even efficiency | 85.7 % | **86.1 %** |
| Break-even shutdown reserve at 5 W | 18.1 s | **17.3 s** |
| Break-even capacitance factor | 0.530 | **0.536** |
| Break-even total stack ESR | 122 mΩ | 122 mΩ (unchanged, it is the answer, not an input) |

Sensitivity rows at 101.1 mΩ (floor V, usable J, margin J, gap bound s): load 16 W 4.014 / 489.2 / +227.2 / 24.0; 20 W 4.142 / 468.5 / +147.4 / 17.8; 30 W 5.001 / 313.5 / −140.9 / 7.9; 35 W 5.701 / 165.7 / −343.8 / 3.7; path +10 mΩ 4.382 / 428.2 / +22.0 / 12.3; efficiency 0.85 4.507 / 406.2 / −13.0 / 11.4; shutdown 10 W × 10 s 4.302 / 441.8 / −21.0 / 12.9; gap 12 s 4.302 / 441.8 / −26.1 / 12.9. The charge-code-13, new-cell and end-of-life rows are not re-run here (they need their own start voltage and cell inputs).

No selection changes: D-047's parts, B1's pass criterion and the code-12 default all hold. The margin falls by 4.8 J and every break-even moves by under 1 %. Only the quoted numbers (26.3 W, 11.4 s, 85.7 %, 18.1 s, 0.530, +47.0 J, 13.1 s) need updating in the summary, §1.1, §1.2, §2.3 and §4.
