# V1 thermal model, 50 mm body run (GHO-12)

**Owner:** [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12), fanless enclosure thermal paths.
**Status:** Candidate, 2026-10-09; trimmed 2026-11-06. This is the last full run of the thermal model in [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §2. It modelled a 145 x 74 x 50 mm body with the pack under it and a 10 W Wi-Fi card. D-054 replaces that geometry with an upright body about 76 x 34 mm in section and about 228 mm long, with the pack docked on its bottom end, and D-053 replaces the supercap tray with an internal LiPo cell. GHO-12 reruns the model for that geometry. Until then the part margins below are the best estimate on record, and the findings that do not depend on the body shape (Wi-Fi card, CM5, pack charge window) stand. It edits no record (README rule 6). Nothing here is measured. Nothing here qualifies the design.

## Conventions

- **Verified:** read from the source in [Sources](#sources), at the revision given, on 2026-10-09.
- **Calculated:** derived here from the stated inputs. The arithmetic is shown or reproducible. Nobody has measured it.
- **Unverified:** an assumption, an estimate carried over from the thermal plan, or a value not checked against a primary source. All are listed in [What remains unverified](#what-remains-unverified).

Ambient is the D-028 hot endpoint, **+43.3 °C** (110 °F).

## Summary

- **No script exists for the thermal model.** The model is derived by hand below, with the same method and h values as the thermal plan.
- **Case.** At 18.5 W and 43.3 °C the 50 mm finned body ran at **72.0 °C** (planning h) and about 50 °C at the 21.1 °C nominal ambient. The D-054 body has more shedding area (about 0.05 m² of side and top faces against 0.0326 m² here, before fins), so the rerun should come out cooler. (Calculated; the D-054 area is a rough figure, not a model run)
- **The Wi-Fi card fails its 70 °C rating on any passive path.** At 10 W through a 2.5 K/W pad the card sits 25 K above the case. Staying at 70 °C needs a case at 45 °C, 1.7 K above ambient. If 70 °C is an ambient rating, internal air at 77 to 87 °C fails it too. This does not depend on the body shape. (Calculated)
- **The CM5 is marginal.** 83.3 °C against the 85 °C throttle point at 18.5 W (range 81.0 to 85.5 °C over the pad estimate). It fails at 25.4 W sustained. (Calculated)
- **The pack cannot charge at the hot endpoint,** and it may not charge even at nominal ambient if it couples to the case. The M35A charge window ends at 45 °C. (Calculated)
- **Internal air at 77 to 87 °C** at the hot endpoint is the input [v1-lipo-bridge.md](v1-lipo-bridge.md) §4 designs the bridge cell against. (Calculated)

## 1. Inputs

| Input | Thermal plan (main) | This run | Tag |
|---|---|---|---|
| Radio body height | 27 mm | **50 mm** | The geometry of the time. Retired by D-054. A 66 mm body is run as a sensitivity case. |
| Shedding area (top plus four sides; the pack covers the bottom) | 0.0107 + 0.0118 = 0.0226 m² | 0.0107 + 0.0219 = **0.0326 m²** | Calculated |
| Wi-Fi card | 8 W typical, 10 W peak | **10 W sustained** worst case | Verified: AsiaRF S3 page, "10W maximum, 8W average" ([v1-gpio-and-m2-audit.md](v1-gpio-and-m2-audit.md) §2.1). Sustained 10 W is a bounding assumption. |
| Finned lid (D-035) | "roughly doubles heat shedding", not modelled | Modelled as a fixed added conductance equal to the old flat-body value: +0.271 W/K (planning) or +0.384 W/K (good) | Unverified. It is the decision card's estimate, held constant. Fin geometry is still open under [GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7). |

## 2. Model and results

**Method (same as v1-thermal-rf-plan.md §2).** The aluminium body is one isothermal node. R(case to ambient) = 1 / (h × area). Planning h = 12 W/m²K and good h = 17 W/m²K (anodized, still air). Side-wall convection is scaled by (27/50)^0.25 = 0.857 for the 50 mm wall, which lowers side h to 11.2 (planning) and 15.5 (good). Fins add the fixed conductance in §1. Parts padded to the lid sit at case + P × R_pad, with R_pad = 2.5 K/W (range 2 to 3, thermal plan estimate). Internal air is case + 5 to 15 K (thermal plan estimate). A 2 mm wall 50 mm tall has fin efficiency about 0.97, so the taller wall stays near case temperature. (Calculated; inputs Unverified)

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

### 2.1 Temperatures at 43.3 °C ambient

Primary column: 50 mm body, finned lid, planning h, 18.5 W. All values Calculated.

| Part | Limit used | 18.5 W, finned, planning | Margin | 18.5 W, finned, good | 25.4 W, finned, planning | Margin at 25.4 W |
|---|---|---:|---:|---:|---:|---:|
| Case (lid, walls) | none (touch comfort open) | **72.0** | — | 63.7 | 82.7 | — |
| Internal air | — | 77.0 to 87.0 | — | 68.7 to 78.7 | 87.7 to 97.7 | — |
| CM5 SoC (4.5 W, 7 W at peak, pad 2 to 3 K/W) | 85 °C: firmware throttles to hold the SoC below 85 °C (CM5 datasheet §4.4). D-028 forbids relying on throttling. | **83.3** (81.0 to 85.5) | **+1.7 K** (−0.5 to +4.0) | 75.0 | 100.2 | **−15.2 K** |
| Wi-Fi AW7916-AED (10 W, pad 2 to 3 K/W) | 70 °C, AsiaRF operating range −10 to +70 °C. Not stated as ambient, surface or junction. | **97.0** (92.0 to 102.0) | **−27.0 K** | 88.7 | 107.7 | **−37.7 K** |
| HaLow GW16170 (1 W, 3.3 W at peak) | 70 °C as a planning limit (the brief's AW7916 rating; the GW16170's own rating is not in the records) | 77.0 with a 5 K/W pad; 87 to 97 with no pad (air at 10 K/W) | **−7 K** (pad) to −27 K | 68.7 (pad) | 99.2 (pad) | **−29 K** |
| GNSS MAX-M10S (sits in internal air) | +85 °C ambient (thermal plan, u-blox) | 77.0 to 87.0 | **+8 to −2 K** | 68.7 to 78.7 | 87.7 to 97.7 | **−3 to −13 K** |
| LM76005 3.3 V buck die (not asked) | 125 °C | 120 to 131 (1.47 W × 29.6 °C/W JEDEC over 77 to 87 °C air) | **+5 to −6 K** | 112 to 122 | 147 to 157 (2.0 W) | **−22 to −32 K** |
| Battery pack top cell (upper bound = case) | Charge 0 to 45 °C; discharge to 60 °C (Unverified); BQ7721602 secondary OT 70 °C blows the pack fuse | ≤ 72.0 | **Charge: fails at any pack temperature above 45 °C.** Discharge and OT: open, set by the pack interface (§3) | ≤ 63.7 | ≤ 82.7 | — |

**Old geometry for comparison** (27 mm, finned, planning h, 18.5 W): case 77.5, CM5 88.7, Wi-Fi 102.5 °C. The extra 23 mm of wall bought 5.5 K on every part tied to the case. With a flat lid the gain would be 18.8 K (111.6 → 92.8 °C case).

**Floorplan sensitivity** (66 mm body, finned, planning, 18.5 W): case 69.2 °C, CM5 80.4 °C, Wi-Fi 94.2 °C. More wall area helps; the D-054 body has more of it.

### 2.2 What it would take to pass

| Target | Case needed | Conductance needed at 18.5 W | Primary case has |
|---|---:|---:|---:|
| CM5 SoC ≤ 85 °C at 2.5 K/W | ≤ 73.75 °C | ≥ 0.61 W/K | 0.644 W/K (just passes) |
| Wi-Fi ≤ 70 °C at 2.5 K/W | ≤ 45.0 °C | ≥ 10.9 W/K | 0.644 W/K (17 × short) |
| Wi-Fi ≤ 70 °C at 1.0 K/W | ≤ 60.0 °C | ≥ 1.11 W/K | 0.644 W/K |

At 25.4 W the CM5 needs ≥ 1.05 W/K. (Calculated)

The Wi-Fi result does not depend on the body height. A 70 °C card limit and a 43.3 °C ambient leave 26.7 K for the whole path from the card to air. At 10 W that is 2.67 K/W in total, and the pad alone uses most of it.

## 3. Battery pack

- In this run the pack shell met the radio's bottom plate, an aluminium face joined to the walls that sits near case temperature. Under D-054 the pack docks on the bottom end face instead; the coupling question is the same. If the pack couples well, its top cell approaches the case: 72 °C at the hot endpoint, about 50 °C at nominal. If the interface is a thermal break, the top cell stays near ambient plus its own I²R (about 0.3 to 0.5 W in the pack, Unverified). (Calculated)
- **Charging.** The M35A charge window ends at 45 °C (v1-battery-pack-gates.md). At a 43.3 °C ambient the pack has 1.7 K of margin before any heating. Charging in the radio at the hot endpoint is not achievable. The BQ76942 T1 thermistor will inhibit it. At nominal ambient, a well-coupled pack would also exceed 45 °C. So the pack interface must be a thermal break.
- **Discharge and the secondary OT.** The BQ7721602 secondary over-temperature is 70 °C, and with the current wiring it blows the pack fuse (v1-battery-pack-gates.md). A coupled pack at the hot endpoint could reach it. The M35A discharge limit (60 °C in the data sheet copies) is Unverified here.

## 4. Bench tests that settle it

The thermal tests in [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §4 are T0 to T6 and T12. T8 to T11 there are RF tests.

| Test | What it settles here |
|---|---|
| T0 | Real sustained AW7916-AED power: is 10 W sustained, or 8 W? |
| T1 | Measured continuous load, replacing the 18.5 and 25.4 W cases |
| T2 | Hot spots on the open board |
| T3 | Case-to-ambient resistance of the real body; internal air; pad rises. Add thermocouples on the bridge cell (L-gates in [v1-lipo-bridge.md](v1-lipo-bridge.md)), the pack top cell and the pack interface. |
| T4 | Hot endpoint at 43.3 °C, full load, 2 h and stable. Settles the CM5 margin. Include a pack swap and a bridge recharge. |
| T6 | Wi-Fi pad A/B. Settles whether 2.5 K/W is real |
| T12 | GNSS fix at the hot endpoint |

## Decisions for the project owner

Each has a recommended default. The working defaults are recorded in D-051.

1. **Wi-Fi card against the hot endpoint.** At 10 W the card cannot meet a 70 °C limit at 43.3 °C on any passive path. Choices: (a) ask AsiaRF what the 70 °C means and for any extended-temperature grade or shield limit, and hold the design; (b) screen an industrial-temperature MT7916 card now, alongside; (c) accept a lower Wi-Fi power at the hot endpoint (conflicts with D-028 and R-21). **Default: (a) and (b) together.**
2. **Load case for passive closure.** Choices: close at 18.5 W (typical with 10 W Wi-Fi) until T0 and T1 measure the continuous load; or close at 25.4 W (every peak sustained). **Default: 18.5 W, and check the CM5 at 25.4 W as a stress case.**
3. **Pack interface.** Choices: a thermal break between the radio body and the pack; or a conductive interface that lets the pack shed heat. **Default: thermal break.** A coupled pack goes above its 45 °C charge limit even at nominal ambient, and may reach the 70 °C secondary OT at the hot endpoint. Accept that the pack does not charge in the radio at the hot endpoint.

## Record conflicts

Found, not resolved. README rule 6 asks for a Linear issue for each. This file opens none.

1. **Internal temperature.** [v1-3v3-rail.md](v1-3v3-rail.md) uses 60 °C internal air and [v1-bom-baseline.md](v1-bom-baseline.md) about 60 °C interior. This model gives 77 to 87 °C internal air at the D-028 hot endpoint.
2. **Wi-Fi power.** The thermal plan's typical row uses 8 W. D-026 and the AsiaRF page give 10 W maximum, and the same page also says 9 W maximum (v1-gpio-and-m2-audit.md conflict 8).

## What remains unverified

- Everything carried over from the thermal plan: h values, pad resistances (2 to 3 K/W), internal air at case + 5 to 15 K, the body heat capacity, and every typical and peak power except the AsiaRF figures.
- The finned-lid conductance, held at the decision card's "doubles shedding" estimate. Fin geometry is open (GHO-7).
- The body geometry: this run used 50 mm; D-054 sets a different body that has not been modelled.
- The LM76005 θJA is the JEDEC value; a real pour will be lower.
- The GW16170 temperature rating; the M35A discharge limit; the meaning of the AW7916-AED 70 °C limit.
- The CM5 firmware may start throttling below 85 °C. The datasheet only says it holds the SoC below 85 °C.

## Sources

| Source | Revision | Used for |
|---|---|---|
| This repository: [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md), [v1-gpio-and-m2-audit.md](v1-gpio-and-m2-audit.md), [v1-3v3-rail.md](v1-3v3-rail.md), [v1-battery-pack-gates.md](v1-battery-pack-gates.md), [decisions.md](../decisions.md) (D-026, D-028, D-035) | main at 53b0528 | Model, loads, limits |
| Raspberry Pi [CM5 datasheet](https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf) §4.4 | Release 3, build date 08/06/2026 | 85 °C SoC throttle point; −20 to +85 °C operating range |
| AsiaRF [AW7916-AED product page](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) (S3), via v1-gpio-and-m2-audit.md | Fetched 2026-10-09 | 10 W maximum; −10 to +70 °C |
| TI LM76005 θJA 29.6 °C/W, via v1-3v3-rail.md | As cited there | Buck die rise |
