# V1 bridge: header-to-stage copper budget

**Status:** Candidate, 2026-10-16. This file adds the board-copper run that [v1-bridge-selection.md](v1-bridge-selection.md) §3.4 did not budget, now that the LTC3350 stage sits at X 119.5 to 136.5, Y 36 to 60 (firmware #71, docs #119). It edits no record and assigns no D, B or R number. The owning records still win (README rule 6). Nothing here is routed or measured.

## 1. Result

- The stack-power (VCAP+) run from the bank header to the stage adds **about 8 mΩ** of board resistance with the default copper below. Total stack ESR rises from 98.7 mΩ to **106.7 mΩ** (111.7 mΩ with the 5 mΩ bank fuse), against the 122 mΩ break-even.
- Calculator margin falls from **+47.0 J to +30.9 J** (+20.8 J with the fuse). Gap lower bound 12.6 s (12.3 s with the fuse), against the 10 s target. The hold-up target is still met.
- Voltage drop on the run is **65 mV at the 7.94 A backup average and 90 mV at the 10.94 A peak**, about 2 % of the 3.50 V floor. Copper loss is 0.5 W for at most 13 s.
- Nothing in the selection changes. B6 (path resistance fits inside B4's 122 mΩ) now needs the board run counted in it.

## 2. Inputs and assumptions

| Item | Value | Tag |
|---|---|---|
| Run length | **130 mm**, bounding case: header at the west end of the tray (X about 5, Y about 33) to the stage at X 119.5 | Assumption. The bank header position is still open (WR-MPC4 item in the floorplan README). |
| Copper default (picked, not asked of Justin) | **8 mm wide pour on L8 (1 oz) in parallel with 8 mm on L5 (0.5 oz)**, joined by vias at both ends | V1 working default. 8 mm is above the 7.2 mm that [v1-stackup-routing.md](v1-stackup-routing.md) §5 gives for 10 A at 10 K rise on 1 oz alone. |
| Sheet resistance at 60 °C | 1 oz: 0.570 mΩ/sq. 0.5 oz: 1.140 mΩ/sq. Parallel: **0.380 mΩ/sq** | Calculated from copper resistivity 1.724e-8 Ω·m with 0.00393 per K. |
| Pour resistance | 130 / 8 = 16.25 squares × 0.380 = **6.2 mΩ** | Calculated |
| Via transitions | The stage is on the top side, the pour on L8 and L5: two transitions of about 8 vias each, about **1 mΩ each**, so about 2 mΩ | Assumption (0.3 mm drill, 1.6 mm board); sum real via resistance once routed |
| CAPRTN return | Taken as the solid ground planes (L2, L4, L7), so its drop is under 1 mΩ and not counted | Assumption |
| Allowance already in the old 15 mΩ | None for board copper | The 14 mΩ list is connectors, wires and bank bus only |

## 3. Effect on hold-up

`bridge_budget.py` at the §4 command with only `--stack-esr-ohm` changed (Calculated):

| Case | Stack ESR | Usable (J) | Margin (J) | Gap bound (s) |
|---|---:|---:|---:|---:|
| Record (§4) | 98.7 mΩ | 445.0 | +47.0 | 13.1 |
| With the 130 mm run (+8 mΩ) | 106.7 mΩ | 434.2 | +30.9 | 12.6 |
| Run plus bank fuse (+13 mΩ) | 111.7 mΩ | 427.3 | +20.8 | 12.3 |
| Run, fuse and 7 mΩ contact/wire tolerance (+20 mΩ) | 118.7 mΩ | 417.7 | +6.6 | 11.8 |

The last row is still positive but close to the 122 mΩ break-even. It does not hold if the cells are also at the aged, cold corner that §1.2 already uses, so the run is worth shortening.

## 4. Cheap ways to buy the margin back

1. **Put the bank header at the east end of the tray**, under the stage. The run drops to about 30 mm and the board resistance to about 2 mΩ, which returns about 5 mΩ. This is a placement choice for the WR-MPC4 open item and costs no parts.
2. A 10 mm pour instead of 8 mm lowers the 130 mm run from 6.2 to 4.9 mΩ.
3. Keep the harness at 2 × 16 AWG per pole; do not add contacts.

## 5. Proposed record text

For the records owner to apply only if the project owner accepts. No IDs are assigned.

- **§3.4 path ESR budget:** add a row "Board copper, header to stage: 8 mΩ at 130 mm, 8 mm pour on L8 plus L5 (v1-bridge-stage-path.md)"; path ESR becomes about 22 mΩ (27 mΩ with the fuse). Replace the 15 mΩ used in §4 and the 98.7 mΩ total with 106.7 mΩ for the same run, or keep 15 mΩ if the header is placed under the stage.
- **B6:** include the board run in the 122 mΩ check.
