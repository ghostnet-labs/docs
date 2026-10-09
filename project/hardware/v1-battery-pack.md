# Track B battery pack and interface (V0 mechanical baseline)

The parameter table tags each value as Locked, Target, or CAD-verify. Do not treat Target or CAD-verify values as fabrication dimensions. The geometry conflicts found on 2026-09-30 (C-01 to C-05) were resolved by D-016 and D-017.

**Coordinates.** View the radio from the battery side, with X along the 145 mm length and Y along the 74 mm width. The contact and electronics end is at X = 145 mm and the fixed-hook end is at X = 0 mm. Datum A is the pack-to-radio mating plane, Datum B is the X = 0 hook-end plane, and Datum C is the Y = 0 left sidewall plane when viewing the pack from above.

## Design rules

- **Sourcing.** Prefer active, catalog-orderable parts that can be bought in small quantities from major authorized distributors such as DigiKey, Mouser, Newark, or Arrow. Avoid RFQ-only parts, custom connector builds, manufacturer-specific tooling, and large minimum order quantities unless no reasonable catalog alternative meets the requirement.
- **Priority order.** Preserve the 145 x 74 mm footprint first, keep safe cell clearances and sealing second, keep pack replacement easy third, and let pack height grow if needed. Do not reduce cell insulation or gasket and hard-stop robustness only to hold the 46 mm height target.
- **Modularity.** Standard and future higher-capacity packs share the same 145 x 74 mm footprint and radio-side mating interface, and extra capacity mainly adds height. The pack enclosure is sealed and not meant for routine field disassembly.
- **Sealing.** The radio and the pack are each independently sealed, so removing the pack does not open either enclosure to water. A replaceable silicone face seal around the mating and contact cavity adds secondary protection against water, mud, and debris. The contacts sit inside that cavity and do not need an IP rating.
- **Attachment and install sequence.** Bottom-mount hook and latch. The fixed hooks engage first, then the latch end pivots or presses upward and a positive recessed latch locks the pack. Asymmetric keying (an offset boss) prevents installing the pack reversed by 180 degrees. The release is glove-operable, recessed against accidental activation, and needs no tools.
- **Load path.** Hooks, locating bosses, hard stops, and the latch carry shock, shear, and gasket preload. The pogo contacts carry no structural load and are never used as hard stops. The pack-side target PCB and the radio-side pogo daughterboard carry electrical load only.
- **Contact budget.** Design around 5.2 A per contact as listed by DigiKey, even though the latest Mill-Max datasheet publishes higher derated figures. Two contacts per power rail give at least 10.4 A aggregate, above the V1 pack and system target. Spring force is about 100 gf per probe at mid-stroke, roughly 7.8 N for eight contacts, which is small compared with the gasket and latch preload.
- **Pogo hardware.** Eight identical Mill-Max probes on a replaceable radio-side daughterboard keep sourcing and field repair simple. The pack side uses flat hard-gold-over-nickel landing pads rather than a second proprietary connector, and ordinary bare copper must not be relied on. The radio-side daughterboard mounts from inside the radio so it can be replaced independently of the main carrier, with enough compliant assembly tolerance to align the probe array to the enclosure opening without letting the PCB float under service loads. The pack-side target PCB mounts rigidly to the electronics-bay structure, referenced to the hard-stop datums and not to the BMS PCB or the cells. BAT+ and BAT- drop directly from the target PCB into the protection area with minimal loop area and length.
- **Latch.** The latch must seat the pack against all hard stops and compress the gasket uniformly, and it must not set the pogo stroke. If CAD shows that a single centered latch compresses the seal unevenly, use two smaller catalog catches placed symmetrically rather than a custom spring or cam. If the C3 exceeds the available package, keep the latch-zone datum and substitute a smaller stocked commercial latch. Do not cut production tooling around the estimated latch envelope.
- **Hard stops.** Enclosure hard stops, not latch elasticity or the gasket, set the probe working height. They must prevent pogo over-compression even if the gasket is omitted during service or prototyping.
- **Keepouts.** No cell metal, tall BMS parts, fuse, latch hardware, screws, or conductive structural parts may intrude into the dry contact cavity, gasket gland, pogo travel cylinder, locating-boss engagement volume, or hard-stop contact surfaces. Keep wiring clear of latch travel and hook engagement paths. Cell cans, interconnects, and weld tabs must not touch the enclosure walls. Use nonconductive end supports at both cell ends, and reserve expansion and assembly tolerance around cell ends and interconnects.

## Parameters

Each row is the single owner of its value. Status is Locked, Target, or CAD-verify.

| ID | Parameter | Value | Status |
|---|---|---|---|
| M-01 | Plan-view envelope | About 145 x 74 mm, matching the radio enclosure footprint (138 x 67 mm board plus walls and clearance). The board grew from 117 mm for the M.2 3052 Wi-Fi card (D-026, [GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)); the pack grew 21 mm with it, all of it in the M-22 spare zone, so the interface zone keeps its distance from the contact end. Shrink toward MPU5 size if CAD allows (D-016). The coordinates in this table use the 145 x 74 mm frame. | Target. Shrinks if CAD allows (D-016). |
| M-02 | Height | About 46.0 mm standard, and it may increase if safe packaging, latch, or sealing requires. Cell-zone structural height about 42 to 44 mm (two 18.6 mm cells, about 1 mm layer gap, 1.5 to 2 mm insulation and support above and below, plus wall and clearance). | Target |
| M-03 | Perimeter structure | 4.0 mm nominal wall and edge margin around the plan-view perimeter, with a continuous structural load path along both 145 mm sidewalls from hook end to latch end. Corner radii and draft depend on the enclosure process. | Target. Radii and draft CAD-verify. |
| M-04 | Cells | Six Molicel INR-18650-M35A, modeled at 65.2 mm max length x 18.6 mm max diameter, along X. Three across Y and two layers, with the lower layer directly under the upper. | Locked |
| M-05 | Cell Y centerlines | 17.4, 37.0, and 56.6 mm (19.6 mm spacing, about 8.1 mm margin from the outer can to each 74 mm sidewall) | Target |
| M-06 | Cell spacing | At least 1.0 mm between adjacent cans and between layers, plus separate insulation bodies | Target |
| M-07 | Cell zone | X = 6.0 to 74.0 mm (68 mm). Reserve about 68 x 61 x 41 mm for the insulated cell zone. | Target |
| M-08 | Electronics bay | X = 100.0 to 141.0 mm and Y = 4.0 to 70.0 mm, with a 5.0 mm structural and insulation corridor (X = 95 to 100 mm) between it and the M-22 spare zone | Target |
| M-09 | BMS PCB | Envelope about 32 x 48 mm, long axis along Y, in the lower portion of the bay. Keep the pack fuse and protection close to the BAT+ and BAT- pads and thermally separate from the cell ends. | Target. Z placement CAD-verify. |
| M-10 | Contact array | Eight Mill-Max 7911-0-15-20-86-14-11-0 probes in a 4 x 2 grid on 4.0 mm pitch, centered at X = 117.0 mm and Y = 37.0 mm. Offsets from center: X = -6, -2, +2, +6 mm and Y = -2, +2 mm (a 12 x 4 mm center span). | Pitch Locked. Center Target. |
| M-11 | Contact allocation | Two BAT+ in parallel, two BAT- in parallel, SDA, SCL, PACK_PRESENT/ID, and one spare or wake contact | Selected |
| M-12 | Probe working height | About 6.79 mm recommended. Target 6.8 +/- 0.25 mm effective in the locked condition, with worst case between 6.25 and 7.14 mm, which includes the probe's ±0.15 mm length tolerance and a 0.2 mm minimum preload. | Target. Tolerance study CAD-verify. |
| M-13 | Pack-side target pads | Eight round or rounded hard-gold-over-nickel pads, at least 2.5 mm diameter, on the same 4.0 mm grid. Increase the size if the process allows without reducing creepage or short-circuit tolerance. | Target. Finish thickness, shape, and vendor capability CAD-verify. |
| M-14 | Target PCB and pogo daughterboard | Each about 24 x 16 mm (the daughterboard plus mounting ears), separately replaceable on the radio side. Both PCBs are located by their contact faces against datum shoulders, so board thickness stays out of the probe stack. | Target. Mounting ears and fasteners CAD-verify. |
| M-15 | Dry contact cavity | About 28 x 20 mm internal, centered on the contact array, with at least 5 mm of land between the outermost target pad and the gasket | Target |
| M-16 | Secondary gasket | Replaceable solid silicone rectangular gasket or cord, a closed rounded rectangle around the contact cavity only (not the whole pack face). Centerline envelope about 34 x 26 mm centered at X = 117 mm and Y = 37 mm (X = 100 to 134 mm, Y = 24 to 50 mm). 2.0 mm cross-section, precision molded loop (or cord to an equivalent tolerance), about 22 to 25 percent nominal axial compression, below about 30 percent worst case, with the gland-plus-face-gap stack held to ±0.10 mm worst case (D-050). | Target. Gland geometry CAD-verify. |
| M-17 | Hard-stop lands | Four broad lands outside the gasket perimeter, two on each side in the Y margins (X about 109 and 125 mm, Y about 10 and 64 mm), coplanar with Datum A | Target. Positions CAD-verify. |
| M-18 | Locating bosses | Two tapered bosses at X about 117 mm and Y about 12 and 60 mm, outside the gasket and asymmetric about the Y = 37 mm centerline so they key the pack, engaging before the probes reach working compression and before meaningful gasket compression | Target. Diameter, taper, clearance, and depth CAD-verify. |
| M-19 | Fixed hooks | Two hooks at X about 1 to 6 mm in the hook bay (which includes the 4 mm end wall), near Y = 14 and 60 mm, tied into sidewall and endwall ribs rather than the cell support structure. Keepers are open enough for first engagement and tapered to guide the pack without scraping the gasket. | Target. Width, undercut, and thickness CAD-verify. |
| M-20 | Latch zone | Two end-face pockets for Southco 97-30-160-12 draw latches (B-13), at about Y 14 and Y 60, X 136 to 145, Z 0 to about 16 mm on the pack (D-050). Keepers on the radio end face | Target. Pocket size, keeper position and lever access CAD-verify. |
| M-21 | Interface zone | Reserve the final 50 mm of length (X = 95 to 145 mm) for the corridor, contact cavity and gasket, latch pocket, locating features, and electronics bay, and the first 74 mm for the hook bay and cell block | Target |
| M-22 | Spare zone | X = 74 to 95 mm (21 mm) between the cell block and the corridor, added when the pack grew to 145 mm (D-026). Unassigned: it can take the BMS, wiring slack, or a longer cell support, or be cut if the radio shrinks again. | Target |

## CAD assembly bodies

Create these bodies first: radio-bottom interface plate, pack outer shell, pack top and interface plate, six cell solids, cell carriers and insulators, electronics-bay volume, BMS PCB envelope, target PCB, pogo daughterboard, eight pogo-pin solids, secondary gasket, four hard stops, two locating bosses and recesses, two hook and keeper pairs, a latch placeholder envelope, a fuse and protection placeholder, and wiring and interconnect keepout volumes. Model the hooks as separate replaceable bodies until the enclosure material and drop-load assumptions are chosen.

## CAD review gates

1. Fit check. All bodies sit inside the 145 x 74 mm footprint.
2. Motion check. Hook-first installation, pivot path, locating engagement, pogo compression, gasket compression, and latch travel work without interference.
3. Tolerance study. Hard-stop stack, gasket squeeze, pogo stroke, and PCB positional tolerance.
4. Structural review. Identify the hook and latch load paths and the weak enclosure sections.
5. Electrical and mechanical review. Freeze the target-pad geometry and contact pin allocation before BMS PCB routing.

Confirm the D-017 length budget in gate 1. The 145 mm frame adds 21 mm of spare length (M-22), which covers the earlier 128 mm fallback.

Open design work is tracked in [GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8). Gate results: [v1-battery-pack-gates.md](v1-battery-pack-gates.md).
