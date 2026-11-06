# Track B battery pack and interface (V0 mechanical baseline)

The parameter table tags each value as Locked, Target, or CAD-verify. Do not treat Target or CAD-verify values as fabrication dimensions. D-054 (2026-11-06) set the current layout: six cells one cell deep, stacked six high, docking on the bottom end of an upright radio body. Rows whose positions came from the earlier 145 x 74 mm under-board frame are Open under GHO-8.

**Coordinates.** View the pack from its mating face, the face that meets the radio's bottom end. X runs along the 76 mm width (the cell axis), Y along the 27.6 mm depth from the back (MOLLE) face to the front (lid) face, and Z down the 132 mm height from the mating face. Datum A is the pack-to-radio mating plane, Datum B is the X = 0 side face, and Datum C is the Y = 0 back face.

## Design rules

- **Sourcing.** Prefer active, catalog-orderable parts that can be bought in small quantities from major authorized distributors such as DigiKey, Mouser, Newark, or Arrow. Avoid RFQ-only parts, custom connector builds, manufacturer-specific tooling, and large minimum order quantities unless no reasonable catalog alternative meets the requirement.
- **Priority order.** Preserve the mating-face envelope (M-01) first, keep safe cell clearances and sealing second, keep pack replacement easy third, and let pack height grow if needed. Do not reduce cell insulation or gasket and hard-stop robustness only to hold the M-02 height target.
- **Modularity.** Standard and future higher-capacity packs share the same mating-face envelope (M-01) and radio-side mating interface, and extra capacity mainly adds height. The pack enclosure is sealed and not meant for routine field disassembly.
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
| M-01 | Mating-face envelope | About 76 x 27.6 mm, inside the bottom end face of the upright radio body (about 76 x 34 mm, D-054). Packing rules from the enclosure model: 1 mm between cells, 1.5 mm insulation, 3 mm wall, 2 mm cell end supports. | Target. CAD-verify. |
| M-02 | Height | About 132 mm: six 18.6 mm cell layers, 1 mm gaps, insulation, walls and a 6 mm BMS layer (D-054). It may increase if safe packaging, latch, or sealing requires. | Target |
| M-03 | Perimeter structure | 3.0 mm wall in the D-054 envelope, with a continuous structural load path along both long side faces. A 4.0 mm wall adds about 2 mm to each plan dimension. Corner radii and draft depend on the enclosure process. | Target. Wall thickness, radii and draft CAD-verify. |
| M-04 | Cells | Six Molicel INR-18650-M35A, modeled at 65.2 mm max length x 18.6 mm max diameter, along X, one cell deep, stacked six high along Z. Electrically 3S2P. | Cells Locked. Layout Target (D-054). |
| M-05 | Cell centerlines | Y about 13.8 mm (mid-depth). Z on 19.6 mm pitch (18.6 mm cells plus 1 mm gap); first-layer position follows the BMS layer (M-08). | Target. Z positions CAD-verify. |
| M-06 | Cell spacing | At least 1.0 mm between adjacent cans and between layers, plus separate insulation bodies | Target |
| M-07 | Cell zone | About 69 x 22 x 120 mm insulated cell zone (cells, end supports, gaps and insulation). | Target |
| M-08 | Electronics bay | A layer about 6 mm thick across the plan area for the BMS, fuse and target PCB. Which end (mating face or far end) and the corridor between it and the cells are Open (D-054). | Open |
| M-09 | BMS PCB | Must fit about 70 x 21 mm of plan area in the M-08 layer. Keep the pack fuse and protection close to the BAT+ and BAT- pads and thermally separate from the cell ends. | Open (D-054) |
| M-10 | Contact array | Eight Mill-Max 7911-0-15-20-86-14-11-0 probes in a 4 x 2 grid on 4.0 mm pitch, a 12 x 4 mm center span, long axis along X on the mating face. Center position Open (D-054). | Pitch Locked. Center Open. |
| M-11 | Contact allocation | Two BAT+ in parallel, two BAT- in parallel, SDA, SCL, PACK_PRESENT/ID, and one spare or wake contact | Selected |
| M-12 | Probe working height | About 6.79 mm recommended. Target 6.8 +/- 0.25 mm effective in the locked condition, with worst case between 6.25 and 7.14 mm, which includes the probe's ±0.15 mm length tolerance and a 0.2 mm minimum preload. | Target. Tolerance study CAD-verify. |
| M-13 | Pack-side target pads | Eight round or rounded hard-gold-over-nickel pads, at least 2.5 mm diameter, on the same 4.0 mm grid. Increase the size if the process allows without reducing creepage or short-circuit tolerance. | Target. Finish thickness, shape, and vendor capability CAD-verify. |
| M-14 | Target PCB and pogo daughterboard | Each about 24 x 16 mm (the daughterboard plus mounting ears), separately replaceable on the radio side. Both PCBs are located by their contact faces against datum shoulders, so board thickness stays out of the probe stack. | Target. Mounting ears and fasteners CAD-verify. |
| M-15 | Dry contact cavity | About 28 x 20 mm internal, centered on the contact array, with at least 5 mm of land between the outermost target pad and the gasket. Fit on the 27.6 mm deep mating face is Open (D-054). | Target. Fit Open. |
| M-16 | Secondary gasket | Replaceable solid silicone gasket or cord, a closed rounded rectangle around the contact cavity only (not the whole pack face). 2.0 mm cross-section, precision molded loop or cord to an equivalent tolerance (D-050). The earlier 34 x 26 mm centerline envelope does not fit inside the 27.6 mm deep face; size and position Open (D-054). | Open |
| M-17 | Hard-stop lands | Four broad lands outside the gasket perimeter, coplanar with Datum A. Positions Open (D-054). | Open |
| M-18 | Locating bosses | Two tapered bosses outside the gasket, asymmetric so they key the pack, engaging before the probes reach working compression and before meaningful gasket compression. Positions Open (D-054). | Open. Diameter, taper, clearance, and depth CAD-verify. |
| M-19 | Fixed hooks | Two hooks at one end of the mating face, tied into side and end wall ribs rather than the cell support structure. Keepers are open enough for first engagement and tapered to guide the pack without scraping the gasket. Positions Open (D-054). | Open |
| M-20 | Latch zone | Pockets for Southco 97-30-160-12 draw latches (B-13, D-050) with keepers on the radio body. Pocket positions Open (D-054). | Open. Pocket size, keeper position and lever access CAD-verify. |
| M-21 | Interface zone | The mating face holds the contact cavity and gasket, hard stops, locating features, hooks and latch keepers. Zone allocation Open (D-054). | Open |
| M-22 | Spare zone | None reserved in the D-054 layout. | Open |

## CAD assembly bodies

Create these bodies first: radio-bottom interface plate, pack outer shell, pack top and interface plate, six cell solids, cell carriers and insulators, electronics-bay volume, BMS PCB envelope, target PCB, pogo daughterboard, eight pogo-pin solids, secondary gasket, four hard stops, two locating bosses and recesses, two hook and keeper pairs, a latch placeholder envelope, a fuse and protection placeholder, and wiring and interconnect keepout volumes. Model the hooks as separate replaceable bodies until the enclosure material and drop-load assumptions are chosen.

## CAD review gates

1. Fit check. All bodies sit inside the M-01 and M-02 envelope.
2. Motion check. Hook-first installation, pivot path, locating engagement, pogo compression, gasket compression, and latch travel work without interference.
3. Tolerance study. Hard-stop stack, gasket squeeze, pogo stroke, and PCB positional tolerance.
4. Structural review. Identify the hook and latch load paths and the weak enclosure sections.
5. Electrical and mechanical review. Freeze the target-pad geometry and contact pin allocation before BMS PCB routing.

Open design work is tracked in [GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8). Gate results: [v1-battery-pack-gates.md](v1-battery-pack-gates.md).
