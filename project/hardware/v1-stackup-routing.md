# V1 stackup and routing rules

**Owner:** [GHO-14](https://linear.app/ghostnet-labs/issue/GHO-14), obtain a fabricator stackup and calculate routing constraints.  
**Status:** proposal, 2026-10-07. Desk calculation only; no fabricator quote, field solver run or impedance coupon yet. Fabricator confirmation before routing is [GHO-15](https://linear.app/ghostnet-labs/issue/GHO-15).

This file proposes a manufacturing stackup for the 138 x 67 mm carrier and the trace geometry, matching, via, keep-out and power-copper rules that follow from it. It replaces the conceptual layer list in [v1-reference.md](v1-reference.md) section 20 only once GHO-15 confirms it with the fabricator. It records no decisions. Interface facts come from [v1-reference.md](v1-reference.md) sections 6, 8, 10 and 19, [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md), [v1-3v3-rail.md](v1-3v3-rail.md) and [v1-hot-swap-bridge.md](v1-hot-swap-bridge.md); if they change, those files win.

## Summary

| Item | Proposal |
|---|---|
| Fabricator basis | JLCPCB controlled-impedance FR-4, Nan Ya NP-155F core, published prepreg and core Dk table |
| Layer count | 8 layers, 1.6 mm nominal, 1 oz outer, 0.5 oz inner |
| Impedance layer | L3 (stripline between L2 GND and L4 GND) for PCIe, USB and Ethernet MDI; L1 only for breakouts and the GNSS feed |
| PCIe and USB 2.0, 90 ohm | L3: 0.150 mm trace, 0.125 mm gap. L1: 0.180 / 0.125 mm |
| PCIe at 85 ohm (ticket target) | L3: 0.175 / 0.125 mm. L1: 0.200 / 0.125 mm |
| Ethernet MDI, 100 ohm | L3: 0.130 / 0.150 mm. L1: 0.155 / 0.150 mm |
| 50 ohm single-ended | L1: 0.190 mm. L3: 0.175 mm |
| Power copper (10 C rise) | VBAT and +VBUS_HOLD 6 A: 3.6 mm of 1 oz. +3V3_RADIO 5 A: 2.8 mm of 1 oz, but its 10 mOhm drop budget needs about 2.9 mm of 1 oz over 50 mm. Supercapacitor path 10 A: 7.2 mm of 1 oz |

## 1. Fabricator data used

Fetched 2026-10-07:

- [JLCPCB controlled impedance stackups](https://jlcpcb.com/impedance): prepreg Dk 7628 = 4.4, 3313 = 4.1, 1080 = 3.91, 2116 = 4.16; solder mask 1.2 mil over substrate, 0.6 mil over trace, Dk 3.8; full 4- and 6-layer stackups (for example JLC06161H-3313: 0.0994 mm 3313 outer prepreg, 0.55 mm cores, 1.538 mm copper plus dielectric for a "1.6 mm" board).
- [User guide to the JLCPCB impedance calculator](https://jlcpcb.com/help/article/User-Guide-to-the-JLCPCB-Impedance-Calculator): 4 to 8 layers are calculated on Nan Ya NP-155F; outer 1 oz = 1.6 mil, inner 0.5 oz = 0.6 mil (15.2 um); trace top width = base width minus 0.7 mil; per-thickness NP-155F core Dk table (0.10 to 0.20 mm = 4.36, 0.40 mm = 4.36, 0.55 mm = 4.41).
- [JLCPCB PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities): impedance control on 4 to 32 layers, impedance tolerance ±10 %, track width tolerance ±20 %, preferred minimum via drill 0.2 mm with pad 0.1 to 0.15 mm larger; 0.2 or 0.25 mm drills with pads under 0.45 mm cost extra.
- [Raspberry Pi CM5 datasheet](https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf) (history entry 8 June 2026), sections 2.2.1, 2.3, 2.4.2 and B.3: PCIe 90 ohm, intra-pair within 0.1 mm, no pair-to-pair matching, 220 nF RX coupling capacitors close to the peripheral TX; USB 2.0 90 ohm within 0.15 mm; Ethernet 100 ohm within 0.15 mm, pair-to-pair under 50 mm; 5 V up to 2.5 A.

**Not available:** JLCPCB's 8-layer stackups are produced by the calculator page script and are not in the published page, so the 8-layer build below is **constructed** from the published NP-155F core and prepreg table in the same pattern as the published 6-layer builds. It is not a JLCPCB stackup name. JLCPCB does not state the frequency at which its Dk values apply. The NP-155F loss tangent was not fetched; a typical FR-4 value (about 0.02) is assumed and does not change any width.

## 2. Layer count and assignment

Eight layers, as v1-reference.md section 20 assumed. The reasons, now that the interfaces are known:

- PCIe Gen2 (5 GT/s, 2.5 GHz Nyquist), USB 2.0 and the four MDI pairs want a stripline layer with ground on both sides, so the CM5 breakout field and the radio cards on L1 do not couple into them.
- The board carries 5 to 10 A power paths and a supercapacitor bridge; a dedicated power layer keeps that copper off the ground planes.
- Three solid ground planes (L2, L4, L7) give every signal layer an adjacent ground and short via returns.
- Six layers (for example JLC06161H-3313) can give either a stripline layer with two grounds or a power plane, not both: its L3 sits 0.11 mm from L4 and 0.55 mm from L2, and L6 would reference a power plane on the side that carries the bucks. It remains the cost fallback if GHO-15 finds 8 layers unavailable, with high-speed pairs on L3 over a solid L4 ground and no power plane.

| Layer | Material | Thickness (mm) | Dk | Use |
|---|---|---:|---:|---|
| L1 top | Copper 1 oz | 0.035 (0.041 in calc) | | CM5, M.2 sockets, GNSS, connectors; short breakouts; GNSS RF feed |
| | Prepreg 3313 x1 | 0.0994 | 4.10 | |
| L2 | Copper 0.5 oz | 0.0152 | | Solid GND, no splits |
| | Core | 0.20 | 4.36 | |
| L3 | Copper 0.5 oz | 0.0152 | | Impedance layer: PCIe, REFCLK, USB 2.0, MDI |
| | Prepreg 2116 + 1080 | 0.1164 + 0.0764 | 4.16 / 3.91 | |
| L4 | Copper 0.5 oz | 0.0152 | | Solid GND |
| | Core | 0.40 | 4.36 | |
| L5 | Copper 0.5 oz | 0.0152 | | Power pours: +VBUS_HOLD, +5V_SYS, +3V3_RADIO, WIFI_3V3; GND fill elsewhere |
| | Prepreg 1080 + 2116 | 0.0764 + 0.1164 | 3.91 / 4.16 | |
| L6 | Copper 0.5 oz | 0.0152 | | Low-speed signals; USB 2.0 only if L3 is full (see section 4) |
| | Core | 0.20 | 4.36 | |
| L7 | Copper 0.5 oz | 0.0152 | | Solid GND |
| | Prepreg 3313 x1 | 0.0994 | 4.10 | |
| L8 bottom | Copper 1 oz | 0.035 | | Bucks, eFuse, charger, LTC3350, supervisor; power pours; low-speed |

Copper plus dielectric is 1.546 mm, the same convention as JLCPCB's 1.538 mm "1.6 mm" six-layer build. The build is symmetric about the L4 to L5 core, which keeps warp down. L3 sits midway between L2 and L4 (b = 0.408 mm, thickness-weighted Dk 4.21). L6 is the mirror image, so it sees L5 power and L7 ground equally.

The Wi-Fi and HaLow RF lines stay on the cards (IPEX and MMCX on the modules, v1-reference.md section 19), so the only carrier-routed RF trace is the GNSS feed from its antenna connector to the MAX-M10S RF input.

## 3. Impedance calculation

Formulas (implemented in Python 3, no packages; widths solved by bisection):

| Structure | Formula |
|---|---|
| Microstrip, single | Hammerstad and Jensen (1980) with the Wheeler thickness correction, as given by Wadell, *Transmission Line Design Handbook* (1991) |
| Microstrip, edge-coupled | IPC-2141: Zdiff = 2 Z0 (1 − 0.48 e^(−0.96 s/h)) |
| Stripline, single | Wheeler thick-strip stripline formula (Wadell); checked against the Cohn exact zero-thickness result Z0 = (30π/√Dk) K(k)/K(k'), k = sech(πw/2b): 100.4 vs 100.5 ohm at w/b = 0.5 in air |
| Stripline, edge-coupled | Cohn exact odd mode, Zodd = (30π/√Dk) K(ko')/K(ko), ko = tanh(πw/2b) / tanh(π(w+s)/2b); Zdiff = 2 Zodd, scaled by the Wheeler thick/thin ratio for 15.2 um copper |
| Grounded coplanar (GNSS option) | Conformal mapping CPWG (Wadell), zero thickness |

Inputs: L1 h = 0.0994 mm, Dk 4.10, t = 0.0406 mm; L3 b = 0.408 mm, Dk 4.21, t = 0.0152 mm. Each trace is modelled at its mean width (drawn width minus 0.0089 mm, half the JLCPCB 0.7 mil etch taper). Outer-layer values **exclude solder mask**; mask over a microstrip typically lowers it by 1 to 3 ohm, which is why outer layers are limited to short breakouts. Sanity checks: 3.0 mm microstrip on 1.6 mm, Dk 4.5 gives 49.9 ohm; a wide-gap coupled stripline returns 2 x Z0.

| Interface | Target | L1 / L8 microstrip w / gap (mm) | Z | L3 / L6 stripline w / gap (mm) | Z | ±0.02 mm width on L3 |
|---|---:|---|---:|---|---:|---|
| PCIe Gen2 data and REFCLK (CM5 datasheet) | 90 Ω diff | 0.180 / 0.125 | 89.4 | 0.150 / 0.125 | 90.6 | 95.9 to 85.9 |
| PCIe Gen2 (ticket, M.2 convention) | 85 Ω diff | 0.200 / 0.125 | 84.0 | 0.175 / 0.125 | 84.9 | 89.4 to 80.9 |
| USB 2.0 (CM5 to hub, hub to ports) | 90 Ω diff | 0.180 / 0.125 | 89.4 | 0.150 / 0.125 | 90.6 | 95.9 to 85.9 |
| 1000BASE-T MDI | 100 Ω diff | 0.155 / 0.150 | 100.6 | 0.130 / 0.150 | 99.4 | 106.0 to 93.7 |
| GNSS RF, other 50 Ω | 50 Ω | 0.190 | 50.6 | 0.175 | 49.8 | 52.9 to 47.2 |
| GNSS RF, grounded coplanar option | 50 Ω | 0.200, 0.150 gap to L1 ground | 50 | | | |

Recommendation: route PCIe at 90 ohm as the CM5 datasheet asks. The M.2 card side is specified at 85 ohm, but 85 and 90 sit inside each other's ±10 % band and the carrier run is short; the 85 ohm row is kept for GHO-15 if the owner prefers it. The ±0.02 mm column shows that the ±20 % width tolerance alone would break ±10 %, so the board must be ordered with impedance control, which makes JLCPCB adjust widths against its own process.

Propagation delay: about 5.7 ps/mm on L1 (effective Dk 2.92) and 6.85 ps/mm on L3.

## 4. Matching, vias, coupling capacitors and reference planes

### Length matching and skew

| Interface | Intra-pair (P to N) | Pair to pair | Source |
|---|---|---|---|
| PCIe TX, RX, REFCLK | 0.10 mm (about 0.7 ps on L3) | Not required | CM5 datasheet 2.3.1 |
| USB 2.0 | 0.15 mm | Not required; no P/N swap | CM5 datasheet 2.4.2 |
| MDI, CM5 to magnetics to header | 0.15 mm | Under 50 mm | CM5 datasheet 2.2.1 |

Match at the end that has the mismatch, with small serpentine bumps (amplitude no more than twice the gap, segment length at least 3 x trace width), not at the far end. PCIe P and N may be swapped within a pair; USB 2.0 may not. Estimated PCIe run is 30 to 60 mm from the CM5 connector to the M.2 socket under the Wi-Fi card (floorplan estimate, not routed). Keep pairs at least 3 x trace width from other pairs and 5 x from clocks and switching nets.

### Vias

| Rule | Value |
|---|---|
| Standard signal via | 0.3 mm drill, 0.5 mm pad (no cost adder) |
| Dense CM5 breakout, if needed | 0.25 mm drill, 0.45 mm pad (cost adder at JLCPCB) |
| Layer changes per high-speed pair | At most two (L1 breakout to L3 and back), same on P and N |
| Return vias | Two GND vias within 1 mm of each differential via pair, placed symmetrically |
| Antipads | One shared oval antipad per pair on L2 and L4; size by field solver or fab in GHO-15 |
| Via stub | Through vias leave about 1.2 mm of stub below L3; quarter-wave resonance is about 30 GHz (c / (4 L √4.3)), far above 2.5 GHz, so no back-drilling |
| Power vias | About 1.4 A each at 10 C rise for 0.3 mm drill with 18 um barrel (IPC-2221 external curve, plating assumed); design to 1 A per via: 6 vias for 5 A, 8 for 6 A, 12 for 10 A at each layer change |

### PCIe AC-coupling capacitors

The 220 nF capacitor footprints (fitted with 0 Ω links by default, D-046) go on the card TX to CM5 RX pair only (M.2 pins 41/43 to CM5 pins 116/118); the CM5 already couples its TX. Place them close to the M.2 socket, since the CM5 datasheet asks for them near the driving source. Use 0201 (0402 if 0201 is not wanted): both capacitors side by side, pads symmetric, no stubs, pads inline with the trace. On L1 the capacitor pads are wider than the 0.18 mm trace, so void L2 under the pads (pad outline plus 0.1 mm), keep L3 clear under that void so L4 becomes the reference, and stitch L2 to L4 next to it. Confirm the void size in GHO-15.

### Reference-plane continuity

- L2, L4 and L7 are unbroken ground. No routing in them; no split runs under any pair.
- Route L3 pairs through the CM5 connector via field only where the plane webs between antipads survive on L2 and L4.
- L6 references L5 power. Use it for USB 2.0 only if L3 is full; the L5 pour under the whole run must be one net, with a 100 nF stitching capacitor to GND within 3 mm of each end. Never route PCIe on L6.
- At every layer change the return path changes plane; the return vias above are what close it.
- MDI: L2 and L4 ground run under the pairs from the CM5 to the magnetics. Between the magnetics and the Pico-Lock header (line side, 1500 Vrms isolation barrier) remove logic ground on every layer; keep the line-side run short and pair-coupled. The isolation spacing comes from the magnetics part, still unselected.
- Keep high-speed pairs at least 1 mm inside the board edge and away from mounting-hole keep-outs.

### Keep-outs under RF modules and the GNSS

| Region | Rule |
|---|---|
| GNSS receiver (X 120.5 to 136.5, Y 7 to 21) and its RF feed | L2 solid under module and feed; L3 to L8 under it carry no signals and are GND fill stitched to L2; no power pours, no switching nets; PCIe pairs stay at least 5 mm away (the Wi-Fi socket is 6.5 mm from the GNSS edge) |
| GNSS RF feed | 50 ohm on L1, no vias, shortest path; ground pour pulled back at least 0.5 mm, or grounded coplanar with a 0.15 mm gap; stitching vias along both sides at 1.5 mm pitch or less (under λ/16 at 7.125 GHz on L1, for isolation from the 6E card next to it); antenna bias (VCC_RF) through its feed inductor, not across the RF line. Check against the MAX-M10S integration manual (not fetched here) |
| Under the Wi-Fi and HaLow M.2 cards | No switching nodes, inductors or buck input loops on any layer; L5 may carry DC pours; keep L1 under the card as GND with stitching |
| Under the CM5 | Low-profile passives and routing only (2.5 mm clearance, section 4 of v1-reference.md) |
| Buck switch nodes (L8, X 30 to 66) | Smallest copper that carries the current; no L6 signals directly above; L7 ground solid above them |

## 5. Power copper

Temperature rise 10 C above the local board, chosen because the sealed enclosure already runs about 60 C inside (D-028, [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md)); 20 C figures are shown for comparison. IPC-2152 gives its results as charts, not a formula. As a closed-form proxy this uses the IPC-2221 external-layer curve, I = 0.048 ΔT^0.44 A^0.725 (A in mil²), for **all** layers; IPC-2152 found that internal conductors are close to (not half of) external ones, so the IPC-2221 internal factor is not applied. Treat the widths as estimates to check against the IPC-2152 charts or a thermal model with real pours. Resistance is at 60 C.

| Net | Requirement | Design current | 1 oz outer, 10 C | 0.5 oz inner, 10 C | 1 oz, 20 C | mOhm per 10 mm |
|---|---|---:|---:|---:|---:|---:|
| VBAT path: contacts, TVS, FET, eFuse, shunt, VBAT_PROTECTED | eFuse 5.56 A (5.94 A at tolerance); 11.1 A for 25 ms | 6 A | 3.6 mm | 8.2 mm | 2.3 mm | 1.6 |
| +VBUS_HOLD (LTC3350 output to both bucks) | Same input current; backup at about 7 V, 35 W stress is 5 A | 6 A | 3.6 mm | 8.2 mm | 2.3 mm | 1.6 |
| LTC3350 stack, inductor and FET path | 9.4 A average screening ceiling at 5 mOhm RSNSC, 13.1 A peak | 10 A | 7.2 mm | 16.6 mm | 4.7 mm | 0.8 |
| +3V3_RADIO | 4.5 A allocation, 5 A ceiling | 5 A | 2.8 mm | 6.4 mm | 1.8 mm | 2.1 |
| WIFI_3V3 (switch to M.2 socket) | 3.03 A peak | 3.5 A | 1.7 mm | 3.9 mm | 1.1 mm | 3.4 |
| +5V_SYS | 2.5 A allocation (CM5 datasheet maximum) | 3 A | 1.4 mm | 3.2 mm | 0.9 mm | 4.2 |

The 25 ms 11.1 A eFuse pulse is short enough to be adiabatic and does not set width.

Voltage drop sets the +3V3 copper, not heat. [v1-3v3-rail.md](v1-3v3-rail.md) budgets 10 mOhm of board copper between the buck and the Wi-Fi socket. The buck (bottom, X 30 to 66) to the socket under the Wi-Fi card is about 40 to 60 mm. Over 50 mm at 60 C, 10 mOhm needs about 2.9 mm of 1 oz or 6.6 mm of 0.5 oz. Proposal: a 3 mm or wider L8 pour from the buck through the TPS22975 toward the socket, paralleled by an L5 pour, joined with at least 6 vias at each end; then sum via and pour resistance once routed.

Placement rules: the high-current pours live on L8 (with the power parts) and L5, never on L2, L4 or L7. Keep the supercapacitor path as one short wide L8 pour plus an L5 pour; the 10 A row is why the LTC3350, its inductor and the stack connection should sit together. Kelvin sense from the shunt and the LTC3350 sense resistors run as a pair on L6 or L1 away from these pours. If GHO-15 shows 1 oz inner copper is cheap, it halves every inner width above but moves the stripline widths (recalculate).

## 6. Confirm with the fabricator before routing (GHO-15)

1. That JLCPCB offers this 8-layer build (or the nearest calculator stackup) with impedance control, its stackup name, and the real pressed prepreg thickness for the copper density on L3 and L6.
2. Dk at the frequency they use, and whether NP-155F Dk 4.36 holds for the 0.20 and 0.40 mm cores; NP-155F loss tangent.
3. Their calculator or field-solver widths for every row in section 3, including solder mask on L1; accept their widths over these.
4. Impedance tolerance (±10 % standard) and whether test coupons are supplied; ask for coupons for 90 Ω and 100 Ω on L3 and 50 Ω on L1.
5. Finished outer copper thickness after plating, inner copper weight options (1 oz inner and its impedance effect), and via barrel plating thickness (18 um assumed above).
6. Via sizes for the CM5 connector breakout, via-in-pad availability and cost, and minimum antipad and plane-web rules.
7. Total thickness and tolerance (1.6 mm nominal) against the M.2 sockets, the CM5 connector and the enclosure (GHO-7).
8. Material Tg and its fit with the 60 C internal enclosure and reflow of the 5 x 7 mm LTC3350 QFN and bottom-side power parts.
9. Whether the 85 or 90 ohm PCIe target stands (CM5 datasheet says 90 ohm).

## What this does not verify

- The 8-layer build is constructed from published materials, not read from a JLCPCB 8-layer stackup; the calculator was not run.
- Closed-form results are typically within about 5 % of a field solver for stripline and less accurate for the IPC-2141 coupled microstrip; no field solver was used.
- The IPC-2152 figures use a closed-form proxy, not the IPC-2152 charts or modifiers.
- Route lengths and drop are floorplan estimates; nothing is routed.
- The MAX-M10S integration manual, the M.2 card PCIe impedance and the magnetics isolation spacing were not fetched.
