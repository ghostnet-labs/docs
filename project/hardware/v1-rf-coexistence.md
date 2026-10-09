# V1 RF coexistence review

**Owner:** [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12), RF-coexistence half (antenna isolation and keepouts, switcher placement, prototype measurements).  
**Status:** Candidate, desk review, 2026-10-09. Nothing here was built, simulated or measured. It edits no record, selects no part and assigns no D-number. Where it disagrees with a record, the record wins until the records owner applies the proposed text in [section 5](#5-proposed-text-for-the-records-owner) (README rule 6).

The thermal half of GHO-12 is [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md), under D-028 and D-035. That file's §3 lists the coexistence mechanisms and its §4 defines tests T7 to T12; this file sizes them. Radio facts come from [v1-reference.md](v1-reference.md) §5, §7, §9 and §18 and [v1-selections.md](v1-selections.md) (B-02, B-03, B-05, B-21). Layout facts come from [v1-stackup-routing.md](v1-stackup-routing.md) §4 and the firmware floorplan model on branch `gho7-usbc-magnetics` (commit `44aa670`, `docs/hardware/v1-mechanical/parts.yaml` and `out/report.md`). Three open docs PRs are read but not relied on as records: `v1-eth-gnss-protection.md` (branch `gho11-eth-gnss`, GHO-11), `v1-schematic-netplan.md` (branch `gho13-schematic-netplan`, GHO-13) and `v1-netplan-blocker-proposals.md` (branch `gho10-netplan-blockers`, GHO-10).

## Conventions

- **Datasheet:** read from the source in [Sources](#sources) with its revision.
- **Calculated:** arithmetic shown here from datasheet or record values. Not measured.
- **Assumed:** a working value chosen so the budget can be written. Every assumption is numbered (A1 to A9) and is a requirement on a part or a measurement, not a fact.
- **Unverified:** not checked against a primary source or hardware. Collected in [section 7](#7-what-is-unverified).

Levels are in dBm, densities in dBm/Hz. "Isolation" I is the measured port-to-port S21 loss between two antenna connectors with the final antennas mounted, so it already includes both antennas' gains and patterns.

## Summary

1. **The external GNSS SAW filter that GHO-11 leaves as a 0 Ω footprint is required.** With a filtered active antenna and the isolation a 145 mm enclosure can give, the coupled HaLow, 2.4 GHz and 5/6 GHz levels at the MAX-M10S RF input exceed u-blox's out-of-band immunity by 18.5, 28.5 and 10.5 dB without it, and clear it by 21.5, 6.5 and 29.5 dB with it (section 2.2, Calculated from assumptions A1 to A6). The 2.4 GHz margin with the SAW is the thinnest. Populate the SAW by default and set the MAX-M10S internal LNA to bypass mode; leave it DNP only if C2 to C4 measure enough margin without it.
2. **The SAW cannot fix the active antenna.** The first nonlinear part is the LNA inside the external GNSS antenna (B-21, not selected). That antenna must have a filter ahead of its LNA and published rejection and linearity figures; section 2.5 lists the numbers. With an unfiltered active antenna the HaLow budget fails by 58.5 dB without the SAW and still by 18.5 dB with it, and its LNA sees about −8.5 dBm; no placement on this enclosure recovers that.
3. **No integer HaLow harmonic lands in a GNSS band.** 2 × 902 to 928 MHz is 1804 to 1856 MHz, 228.6 MHz or more above L1. At 915 MHz the nearest products need a partner at 660.42, 254.58, 1169.58 or 2490.42 MHz, and no V1 transmitter is there. The HaLow risks near 1575 MHz are blocking, its broadband emission inside the GNSS band, and the second-order product with 2.4 GHz Wi-Fi.
4. **2.4 GHz Wi-Fi minus HaLow (1474 to 1570 MHz) can land on BeiDou B1I**, which the MAX-M10S tracks by default. The shipped software runs HaLow and 2.4 GHz Wi-Fi together ([v1-radio-validation.md](v1-radio-validation.md)), so this is the default configuration. It only happens when Wi-Fi's occupied band reaches above 2461 MHz (2.4 GHz channels 9 to 11 at 20 MHz) and HaLow's lower channel edge is below 913 MHz. The product cannot reach GPS L1 or Galileo E1. Switching the receiver to BDS B1C instead of B1I removes this product and two clock harmonics (65 × 24 MHz and 130 × 12 MHz, both 1560 MHz) from the tracked bands. That choice is the owner's (section 6).
5. **Shielding: lay out a two-piece shield can around the GNSS receiver and its RF front end; decide population from C7 and T8.** The GNSS block sits 2.5 mm from the 8 to 10 W Wi-Fi card. No shield is needed over the bucks: they are 54.5 mm away, on the opposite side, under three solid ground planes.
6. **Switcher placement passes.** On the current floorplan no switching part sits under or over either M.2 card, socket or the GNSS block, and every placed power part is at least 40.5 mm from the GNSS receiver. Two switchers are not in the floorplan yet (the LTC3350 bridge stage and the hub 1.1 V buck); section 3.2 gives their keepouts.
7. **Switcher frequency cannot be planned around GNSS.** Every converter here (400 kHz to 2.4 MHz) puts one to six harmonics inside the 2.046 MHz GPS C/A main lobe, and part tolerance moves them by hundreds of MHz at these harmonic orders. None of the parts has spread spectrum, and it would not help at harmonic order 1000 to 4500. Control amplitude instead: forced PWM, small switch nodes, solid planes, distance and, if C7 fails, slower edges.
8. **Transmitter emissions inside the GNSS band need about 52 to 57 dB more suppression than FCC rules require.** That is Calculated against the 15.209 restricted-band limit. Certification therefore proves nothing about co-located GNSS. C1 measures it, and inline filters on the HaLow and Wi-Fi antenna paths are the remedy if it fails.

## 1. Frequency plan

### 1.1 Transmitters and victim bands

| Radio | Band (US) | TX level used here | Source |
|---|---|---|---|
| HaLow, GW16170 (Morse MM8108-M20) | 902 to 928 MHz, 1/2/4/8 MHz channels | +28.5 dBm conducted maximum. Certified antenna Pulse W1063, 1.0 dBi | v1-reference.md §7 (record); MM8108-M20 "up to 28.5 dBm" ([CNX Software, 2026-06-03](https://www.cnx-software.com/2026/06/03/morse-micro-mm8108-m20-high-power-wi-fi-halow-module-delivers-up-to-28-5-dbm-tx-output-power/)). The GW16170 datasheet itself was not found: **Unverified** for this card |
| Wi-Fi, AsiaRF AW7916-AED (MT7916) | 2412 to 2462 MHz centres (ch 1 to 11), 5150 to 5875 MHz, 5925 to 7125 MHz. G-band 2T2R, A-band 2T3R, DBDC, 3 IPEX | Per chain: 2.4 GHz 23 ± 1.5 dBm (11b), 21 ± 1.5 (11g/n HE20); 5/6 GHz 20 ± 1.5 (HE20). Used: 24.5 dBm per chain at 2.4 GHz, 21.5 dBm at 5/6 GHz, +3 dB when both TX chains couple equally | AsiaRF product page, fetched 2026-10-09. AsiaRF gives no separate 6 GHz power table; 6 GHz uses the A-band figure (**Unverified**) |
| GNSS, u-blox MAX-M10S-00B | Receive only | – | Data sheet R08 Table 4 |

| Receiver | Protected band | Note |
|---|---|---|
| GPS L1 C/A, QZSS, SBAS | 1575.42 ± 1.023 MHz = 1574.397 to 1576.443 MHz (main lobe) | Default |
| Galileo E1, BeiDou B1C | 1575.42 ± 2.046 MHz = 1573.374 to 1577.466 MHz | E1 default; B1C optional |
| BeiDou B1I | 1561.098 ± 2.046 MHz = 1559.052 to 1563.144 MHz | Default (data sheet R08 Table 2, "GPS+GAL+BDS B1I (default)") |
| GLONASS L1OF | 1602 + k × 0.5625 MHz, k = −7 to 6, ± 0.511 MHz = 1597.552 to 1605.886 MHz | Off by default |
| HaLow RX | 902 to 928 MHz | Half duplex; receives whenever it is not transmitting |
| Wi-Fi RX | 2402 to 2472, 5150 to 5895, 5925 to 7125 MHz | Each band receives while the other transmits (DBDC) |

The 1559 to 1610 MHz window used for scans in [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) T8 covers every row above.

### 1.2 Harmonics of each transmitter

| Product | Frequency (MHz) | Lands in | Risk |
|---|---|---|---|
| HaLow 2f | 2 × 902 to 2 × 928 = 1804 to 1856 | Nothing protected. 228.6 MHz above L1 (1804 − 1575.42) | Low. A blocker for GNSS only; the MAX-M10S immunity at 1880 MHz is −25 dBm (manual R05 Table 43) |
| HaLow 3f | 2706 to 2784 | Nothing protected (FCC restricted band 2690 to 2900) | Low |
| HaLow 4f, 5f | 3608 to 3712, 4510 to 4640 | Nothing protected | Low |
| HaLow 6f | 5412 to 5568 | Wi-Fi 5 GHz, U-NII-2C channels covering 5470 to 5568 | Medium. Measure (C1, C10) |
| HaLow 7f | 6314 to 6496 | Wi-Fi 6 GHz, U-NII-5/6 | Medium. Measure (C1, C10) |
| Wi-Fi 2.4 GHz 2f | 4804 to 4944 (centres 2 × 2402 to 2 × 2472 occupied) | Nothing protected (below 5150) | Low |
| Wi-Fi 2.4 GHz 3f | 7206 to 7416 | Above 7125 | Low |
| Wi-Fi 5/6 GHz 2f and up | 10300 and up | Nothing protected | None |

**Rule for the channel controller (candidate):** when HaLow is on channel f_H, avoid 5 GHz channels whose occupied band contains 6 × f_H, and 6 GHz channels that contain 7 × f_H, until C10 shows the harmonic is harmless. Example: HaLow at 915 MHz puts 6f at 5490 MHz (channel 100 or 104 at 20 MHz) and 7f at 6405 MHz.

### 1.3 Intermodulation products

Products are listed if they reach a protected band, up to third order (and one fifth-order line for completeness). The frequency range of each uses the occupied edges of both signals. A product is generated in whatever nonlinear part sees both signals: the GNSS antenna's LNA, the MAX-M10S front end, a Wi-Fi antenna port shared by two bands (passive intermodulation), or a radio's own front end.

| Product | Range (MHz) | Hits | Order | Risk |
|---|---|---|---|---|
| f(2.4) − f(HaLow) | 2402 − 928 = 1474 to 2472 − 902 = 1570 | B1I (all of it), Galileo E1 band below 1570 MHz. Cannot reach L1 C/A or E1/B1C main lobes (1570 < 1573.374) | 2 | **High for B1I** in the default HaLow + 2.4 GHz configuration. See 1.4 |
| f(6) − 2 f(2.4) | 5925 − 4944 = 981 to 7125 − 4804 = 2321 | L1, E1, B1I, GLONASS for some pairs. L1 when f(6) = 1575.42 + 2 f(2.4): 6399.4 MHz with ch 1, 6499.4 MHz with ch 11 | 3 | Medium. Only with DBDC 2.4 + 6 GHz |
| f(5) − 2 f(2.4) | 5150 − 4944 = 206 to 5895 − 4804 = 1091 | HaLow 902 to 928 when f(5) = f_H + 2 f(2.4) = 5706 to 5872 (U-NII-3 ch 149 to 165) | 3 | Low to medium. Could come from passive intermodulation at a shared Wi-Fi antenna port |
| 2 f(2.4) + f(HaLow) | 4804 + 902 = 5706 to 4944 + 928 = 5872 | Wi-Fi 5 GHz U-NII-3 receive | 3 | Low (both signals must reach the 5 GHz front end) |
| f(5) − 4 f(HaLow) | 5150 − 3712 = 1438 to 5895 − 3608 = 2287 | All GNSS bands for some pairs | 5 | Low |
| f(5) − f(2.4), f(6) − f(2.4), f(2.4) + f(HaLow), 2 f(2.4) − f(HaLow), 3 f(HaLow) − f(2.4) | 2678 to 3493, 3453 to 4723, 3304 to 3400, 3876 to 4042, 234 to 382 | Nothing protected | 2–4 | None |
| f(6) − f(5) | 30 to 1975 | Would cover all GNSS bands | 2 | Not possible: the MT7916 runs 2.4 GHz plus one of 5 or 6 GHz (AsiaRF, DBDC) |

### 1.4 HaLow near 1575 MHz

Products that could put a HaLow-derived signal on L1, worked for the requested 915 MHz case:

| Form | Partner needed for 1575.42 MHz | Present in V1? |
|---|---|---|
| 2 × 915 | 1830 MHz, +254.58 MHz from L1 | No (not a GNSS band) |
| 915 + f_x | f_x = 660.42 MHz | No transmitter or recorded clock |
| f_x − 915 | f_x = 2490.42 MHz | No: above the US 2.4 GHz occupied edge (2472 MHz). Japan channel 14 (2484 MHz, ± 11 MHz for 11b) would reach it, and is not a US channel |
| 2 × 915 − f_x | f_x = 254.58 MHz | No transmitter. CM5 clocks below 300 MHz are not recorded (**Unverified**) |
| 3 × 915 − f_x | f_x = 1169.58 MHz | No |
| f(2.4) − f(HaLow), whole US bands | 1474 to 1570 MHz | Reaches B1I, not L1 (1.3) |
| LNA-generated 2nd harmonic of a blocker | Blocker at 787.71 MHz (L1/2) or 780.55 MHz (B1I/2) | HaLow is 902 MHz or higher, so its LNA second harmonic (1804 to 1856) misses. This is why the MAX-M10S immunity dips to −35 dBm at 785 MHz but is −17 dBm at 915 MHz (manual R05 §4.3.2, Table 43) |

Not covered by arithmetic: spurs of the MM8108 synthesizer (fractional-N or divided-VCO products of the form (p/q) × f). The architecture is not published (**Unverified**). C1 therefore sweeps the HaLow channel across all of 902 to 928 MHz and records anything in 1555 to 1610 MHz at the MMCX, whatever its cause.

**When f(2.4) − f(HaLow) touches B1I.** The product occupies [f_W,low − f_H,high, f_W,high − f_H,low]. It reaches the bottom of B1I (1559.052 MHz) only if f_W,high − f_H,low ≥ 1559.052, so f_W,high ≥ 1559.052 + 902 = 2461.05 MHz. At 20 MHz width that means 2.4 GHz channels 9 (upper edge 2462), 10 (2467) and 11 (2472), with HaLow's lower channel edge at or below 902.95, 907.95 and 912.95 MHz respectively. A 40 MHz 2.4 GHz channel widens this. Worked example: Wi-Fi channel 11 (2452 to 2472 MHz) with a 1 MHz HaLow channel at 903.5 MHz (903 to 904) gives 1548 to 1569 MHz, covering all of B1I.

**Level, worked example (Calculated from assumptions).** A second-order product at an amplifier input is P_IM2 = P_1 + P_2 − IIP2. With the section 2.2 blocker levels at the active antenna's LNA input (HaLow −31.5 dBm, Wi-Fi −22.5 dBm, after the assumed pre-filter) and an assumed IIP2 of +20 dBm: P_IM2 = −31.5 − 22.5 − 20 = −74 dBm, spread over about 21 MHz (10 log10 21e6 = 73.2 dB-Hz), so −147.2 dBm/Hz. Against the antenna-input noise density N0 = −172 dBm/Hz (A7) that is 24.8 dB above the noise, and B1I C/N0 drops by 10 log10(1 + 10^2.48) = 24.8 dB. With IIP2 = +40 dBm the excess is 4.8 dB and the drop 6.0 dB. GPS L1 and Galileo E1 are untouched in both cases. The active antenna's IIP2 is not known for any candidate; this is why section 6 asks for a B1I/B1C decision and C5 measures it.

### 1.5 Wi-Fi 2.4 GHz desense of GNSS

2.4 GHz is the closest Wi-Fi band to L1 (2412 − 1575.42 = 836.6 MHz), the strongest Wi-Fi transmitter (24.5 dBm per chain, two chains), the band the shipped backhaul uses, and on V1 its antennas are the nearest to the GNSS antenna. Four mechanisms, each with its own test:

| Mechanism | Arithmetic | Where it is handled |
|---|---|---|
| Blocking and compression | 27.5 dBm (two chains at 24.5) minus isolation must stay 6 dB under the MAX-M10S 2440 MHz immunity of −18 dBm (manual R05 Table 43), after the antenna and SAW filtering | Section 2.2; C3, C4 |
| Wi-Fi emission inside the GNSS band | At the Wi-Fi port it must be ≤ −178 + I(1575) dBm/Hz (section 2.3). With I(1575) = 20 dB (A6): −158 dBm/Hz, −98 dBm/MHz | Section 2.3; C1. Not filterable at the GNSS side |
| Second-order with HaLow | 1474 to 1570 MHz, B1I only (1.3, 1.4) | C5; owner decision on B1I |
| Third-order with 6 GHz | f(6) − 2 f(2.4), e.g. 6399.4 − 2 × 2412 = 1575.4 MHz. Level: P_IM3 = 2 P_2.4 + P_6 − 2 IIP3. With −22.5 dBm (2.4 GHz) and −40.5 dBm (6 GHz: 24.5 − 25 − 40, A2, A5) at the antenna LNA and IIP3 = 0 dBm (assumed), −85.5 dBm over about 60 MHz (77.8 dB-Hz) is −163.3 dBm/Hz: 8.7 dB over N0, a 9.2 dB C/N0 drop. At IIP3 = +10 dBm the drop is 0.3 dB | C5; antenna selection (section 2.5) |

The near-field path (Wi-Fi card 2.5 mm from the GNSS block) is in-band board noise, not a 2.4 GHz effect; it is covered in section 3.4 and C7.

### 1.6 Switcher and clock harmonics

Harmonic order n = 1575.42 / f_sw. A C/A main lobe is 2.046 MHz wide, so any switcher under 2.046 MHz has at least one harmonic in it.

| Source | f_sw (source) | Order at L1 | Nearest harmonics (MHz) | Harmonics in L1 C/A lobe | B1I |
|---|---|---|---|---|---|
| LM76005, 5 V and 3.3 V (B-18) | 400 kHz typical, 350 to 450 kHz with RT open; 200 to 500 kHz settable (SNVSBK5A §6.5 fOSC, §7.1) | 3938.55 | 3938 → 1575.2, 3939 → 1575.6 | 5 or 6. Over the tolerance the order runs 3501 to 4501, which moves a given harmonic by about ± 197 MHz | 3903 → 1561.2 |
| BQ25798 charger (B-09) | 1.5 MHz or 750 kHz typical, set by PROG strap or PWM_FREQ; no min/max given (SLUSDV2C §6.5, Table 7-1, REG0x18) | 1050.28 (1.5 MHz), 2100.56 (750 kHz) | 1575.0, 1576.5 (1.5 MHz); 1575.0, 1575.75 (750 kHz) | 1 (1.5 MHz), 2 (750 kHz) | 1041 → 1561.5; 2081 → 1560.75 |
| LTC3350 bridge (B-24, candidate) | 500 kHz nominal, 490 to 510 kHz over temperature (LTC3350 Rev. D p4, [v1-bridge-selection.md](v1-bridge-selection.md)) | 3215.1 at 490 kHz | 1575.35, 1575.84 | 4 | 3186 → 1561.14 |
| TLV62568 hub 1.1 V buck (GHO-10 proposal) | 1.5 MHz typical in PWM; power-save mode below DCM, with lower, load-dependent frequency (SLVSD89B §6.5, §7.3.1) | 1050.28 | 1575.0, 1576.5 | 1 in PWM; wanders in PSM | 1561.5 |
| TPS62A01A (forced-PWM alternative, section 3.3) | 2.4 MHz FPWM (SLUSEG9E §6.5) | 656.43 | 1574.4, 1576.8 | 1 (at the lobe edge) | 1560.0 |
| TPS26633 eFuse (B-15) | Not a switching regulator: a pass FET with gate drive, no inductor. SLVSE94G gives no internal charge-pump frequency | – | – | – | – |
| TPS25751A, TPS22975, TPS2553 | Not switching regulators (power switches) | – | – | – | – |
| TUSB4041I 24 MHz crystal (B-04) | 24 MHz | 65.6 | 66 × 24 = 1584 (+8.58 from L1) | 0 | **65 × 24 = 1560.0, inside B1I** |
| USB full speed, 12 MHz (OpenVLM CM108B, hub) | 12 MHz | 131.3 | 131 × 12 = 1572 (−3.42) | 0 | **130 × 12 = 1560.0, inside B1I** |
| PCIe 100 MHz REFCLK | 100 MHz | 15.75 | 16 × 100 = 1600 | 0 | GLONASS L1OF (off by default) |
| 25 MHz reference, if the CM5 Ethernet PHY uses one | 25 MHz (**Unverified**; BCM54210PE datasheet not public) | 63.02 | 63 × 25 = 1575.0 (−0.42) | 1 | 1550 (no) |
| CM5 SoC crystal, if 54 MHz | 54 MHz (**Unverified**) | 29.2 | 29 × 54 = 1566 | 0 | 1566 (no, 2.9 MHz above B1I) |

**Amplitude, order of magnitude (Calculated, illustrative).** A trapezoidal switch node of amplitude V, duty D and rise time t_r has a harmonic envelope 2VD × f1 × f2 / f² above f2, with f1 = f_sw / (πD) and f2 = 1/(π t_r). For the 3.3 V LM76005 at 12.6 V in (D = 3.39 / 12.6 = 0.269), 400 kHz and an assumed 2 ns edge: f1 = 473 kHz, f2 = 159 MHz, so at 1575 MHz the line is 206 µV peak (46 dBµV), −63.7 dBm into 50 Ω. To reach the −125 dBm C7 limit at the MAX-M10S input the coupling loss from that switch node must be about 61 dB or more. Opposite board sides, 54.5 mm apart, three solid ground planes and a metal enclosure make that plausible, not proven.

**Note for the GHO-11 bias tee:** the antenna-side gain changes what board noise means. Noise that reaches the GNSS feed after the external antenna's LNA is divided by that gain (about 27 dB net, A1 and A3) when referred to the antenna. Noise radiated out of the enclosure through the antenna cables, the Ethernet cable or the OpenVLM cable and picked up by the GNSS antenna itself is not.

### 1.7 Aircraft receivers (D-030), if they join V1

They are not on the V1 carrier. If they are added, two lines from the arithmetic above matter and belong to [GHO-54](https://linear.app/ghostnet-labs/issue/GHO-54): f(6) − 2 f(2.4) reaches 1090 MHz when f(6) = 1090 + 2 f(2.4) = 5894 to 6034 MHz (lowest 6 GHz channels), and HaLow's upper edge (928 MHz) is 50 MHz from 978 MHz UAT. 960 to 1240 MHz is an FCC restricted band, so the regulatory emission limit there (section 2.3) is as weak a guarantee as it is at L1.

## 2. Antenna isolation budget

### 2.1 Method and assumptions

For each transmitter (aggressor) and receiver (victim):

- **Blocking.** Required attenuation from the aggressor's port to the victim's first sensitive input: A_req = P_TX − (B − M), with B the victim's published blocking or immunity level at the aggressor frequency and M = 6 dB margin. Achieved attenuation for GNSS: A = I + R_pre − G_a + L_c + R_SAW.
- **In-band emission.** The aggressor's emission density inside the victim's band, at the aggressor's port, must be ≤ N0 − 6 dB + I(victim band). 6 dB below the noise gives 10 log10(1 + 10^−0.6) = 0.97 dB of desense.
- **Free-space isolation** for orientation only: L = 20 log10(4π d / λ). At 915 MHz (λ = 327.6 mm): 12.5 dB at 110 mm, 17.3 dB at 190 mm, 21.2 dB at 300 mm. At 2440 MHz (λ = 122.9 mm): 12.2 dB at 40 mm, 21.0 dB at 110 mm. Below about λ/2π (52 mm at 915 MHz) the formula does not apply. Pattern nulls (a vertical monopole's null toward a zenith-pointing patch) add to this; enclosure currents and cables subtract.

| ID | Assumption | Value used | Becomes |
|---|---|---|---|
| A1 | Active GNSS antenna gain at L1, G_a | 28 dB | Antenna selection (B-21). Must stay inside the MAX-M10S external-gain limit: 30 dB maximum in low-gain mode, 10 to 40 dB in bypass mode (data sheet R08 Table 13) |
| A2 | Antenna rejection ahead of its LNA, R_pre | 40 dB at 902 to 928 MHz, 35 dB at 2400 to 2500 MHz, 40 dB at 5150 to 7125 MHz | Antenna selection requirement (section 2.5); C3 |
| A3 | Cable and connector loss, antenna to board, L_c | 1 dB | GHO-7 cable choice |
| A4 | External SAW rejection, R_SAW | ≥ 40 dB at 902 to 928 MHz, ≥ 35 dB at 2400 to 2500 MHz, ≥ 40 dB at 5150 to 7125 MHz; ≤ 2 dB insertion loss at L1 | SAW selection requirement (no MPN proposed); C4 |
| A5 | Isolation at the aggressor frequency, I | HaLow → GNSS 20 dB; Wi-Fi 2.4 GHz port → GNSS 15 dB; Wi-Fi 5/6 GHz port → GNSS 25 dB | Placement in section 2.5; C2 |
| A6 | Isolation at L1 between each aggressor antenna and the GNSS antenna, I(1575) | HaLow 25 dB (HaLow antenna mismatched at 1575 MHz), Wi-Fi 20 dB | C2 |
| A7 | Noise density at the GNSS antenna input, N0 | −172 dBm/Hz (−174 + 2 dB antenna noise figure) | Antenna selection; T7 |
| A8 | Wi-Fi receiver noise figure | 5 dB, so −174 + 73.0 + 5 = −96 dBm in 20 MHz | MT7916 figure not published; C10 |
| A9 | HaLow receiver noise figure | 5 dB, so −174 + 60 + 5 = −109 dBm in 1 MHz | MM8108 figure not published; C9 |

### 2.2 Transmitters into GNSS: blocking

Immunity B at the MAX-M10S RF_IN (low-gain mode, 64QAM 10 MHz test signal; manual R05 Table 43): −17 dBm at 915 MHz, −18 dBm at 2440 MHz. u-blox publishes none above 3300 MHz; −18 dBm is assumed for 5 to 7 GHz (**Unverified**). Absolute maximum at RF_IN is 0 dBm CW (data sheet R08 Table 12).

| Aggressor | P_TX (dBm) | A_req = P_TX − B + 6 (dB) | A without SAW = I + R_pre − G_a + L_c | Margin without SAW | A with SAW | Margin with SAW | Isolation needed without SAW (A_req − R_pre + G_a − L_c) | Blocker at the antenna's LNA input, P_TX − I − R_pre |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| HaLow, 915 MHz | 28.5 | 28.5 + 17 + 6 = 51.5 | 20 + 40 − 28 + 1 = 33 | −18.5 | 73 | +21.5 | 38.5 dB (≈ 2.2 m in free space) | −31.5 dBm |
| Wi-Fi 2.4 GHz, two chains | 27.5 | 27.5 + 18 + 6 = 51.5 | 15 + 35 − 28 + 1 = 23 | −28.5 | 58 | +6.5 | 43.5 dB | −22.5 dBm |
| Wi-Fi 5/6 GHz, two chains | 24.5 | 24.5 + 18 + 6 = 48.5 | 25 + 40 − 28 + 1 = 38 | −10.5 | 78 | +29.5 | 35.5 dB | −40.5 dBm |
| HaLow, unfiltered active antenna (R_pre = 0) | 28.5 | 51.5 | 20 + 0 − 28 + 1 = −7 | −58.5 | 33 | −18.5 | 78.5 dB | −8.5 dBm |

Reading the table:

1. **Without the external SAW all three aggressors fail** on these assumptions. The isolation that would make the SAW unnecessary (35.5 to 43.5 dB) is not available between antennas on a 145 mm enclosure; at 915 MHz it means about 2.2 m of free space.
2. **With the SAW, HaLow and 5/6 GHz have 20 dB or more of margin; 2.4 GHz has 6.5 dB.** That margin depends on I ≥ 15 dB and the antenna's 35 dB at 2.4 GHz, so C2 and C3 must confirm both.
3. **An active antenna without a pre-LNA filter fails even with the SAW** (bottom row). Its LNA would see −8.5 dBm at 915 MHz, enough to compress most low-noise amplifiers, and no board-side filter can undo that.
4. **External gain with the SAW**: 28 − 1 − 2 = 25 dB at RF_IN. That is inside both limits in A1. u-blox recommends bypass mode for 10 to 15 dB of external gain or more, for immunity (manual R05 §4.3.1). Proposed: configure CFG-HW-RF_LNA_MODE to bypass (in BBR or OTP). Table 43 is for low-gain mode; C4 repeats the threshold in bypass mode.
5. **Cost in sensitivity:** after a 28 dB LNA, a 2 dB SAW plus 1 dB cable adds about 0.01 dB to the system noise figure (Friis cascade), so the SAW's sensitivity trade-off in manual R05 §4.3 does not apply to this active-antenna design.

### 2.3 Transmitters into GNSS: emission inside the GNSS band

No filter at the GNSS side can remove an aggressor's emission that is already inside 1559 to 1610 MHz. The limit at each aggressor port (A6, A7): density ≤ −172 − 6 + I(1575).

| Aggressor port | I(1575) (A6) | Limit at the port | Same, per MHz |
|---|---:|---:|---:|
| HaLow MMCX | 25 dB | −153 dBm/Hz | −93 dBm/MHz |
| Each Wi-Fi IPEX | 20 dB | −158 dBm/Hz | −98 dBm/MHz |

What regulation guarantees: 1435 to 1626.5 MHz is an FCC restricted band (47 CFR 15.205(a)), where emissions must meet 15.209: 500 µV/m at 3 m above 960 MHz, average detector. As EIRP: (500e−6 × 3)² / 30 W = 7.5e−8 W = −41.2 dBm, measured in 1 MHz. The limits above are 51.8 dB (HaLow, −93 versus −41.2) and 56.8 dB (Wi-Fi, −98 versus −41.2) tighter, before subtracting antenna gain. A certified module can be legal and still jam a GNSS receiver centimetres away. C1 measures the real figure. If a port fails, the remedies are an inline filter at that aggressor port (section 2.5) or more I(1575).

**Board-coupled noise at RF_IN (feeds C7).** With G_a − L_c = 27 dB, the satellite signal at RF_IN is about −130 + 27 = −103 dBm. For 1 dB of degradation, broadband noise coupled onto the board-side feed must be ≤ −172 + 27 − 6 = −151 dBm/Hz at RF_IN. Proposed limit for discrete spurs: ≤ −125 dBm at RF_IN within ± 2.046 MHz of 1561.098 and 1575.42 MHz, which is 22 dB under the satellite signal.

### 2.4 HaLow and Wi-Fi into each other

Neither radio publishes out-of-band blocking: AsiaRF gives only sensitivity (for example −99 dBm at 11b 11 Mbps), and the MM8108-M20 datasheet is not public (**Unverified**). IEEE 802.11 defines adjacent-channel rejection, not blocking at a GHz offset. So these pairs are written as formulas with the blocking level B to be measured (C9, C10). The example B = −10 dBm is a placeholder, not a figure for either part.

| Pair | Mechanism | Required isolation or limit | Example |
|---|---|---|---|
| HaLow TX → Wi-Fi RX (any band) | 915 MHz blocking at the Wi-Fi front end | I(915) ≥ 28.5 − B_W + 6 | B_W = −10 dBm → 44.5 dB |
| HaLow TX → Wi-Fi 5 GHz RX | 6f, 5412 to 5568 MHz | HaLow 6f at the MMCX ≤ −96 − 6 + I(5.5 GHz) dBm in 20 MHz | I = 40 dB → ≤ −62 dBm/20 MHz |
| HaLow TX → Wi-Fi 6 GHz RX | 7f, 6314 to 6496 MHz | Same form at 6.4 GHz | Same |
| Wi-Fi TX → HaLow RX | 2.4 GHz blocking at the HaLow front end | I(2.4) ≥ 27.5 − B_H + 6 | B_H = −10 dBm → 43.5 dB |
| Wi-Fi TX → HaLow RX | Wi-Fi emission in 902 to 928 MHz | ≤ −109 − 6 + I(915) dBm/MHz at the Wi-Fi port | I = 20 dB → ≤ −95 dBm/MHz |
| Wi-Fi 5 GHz + 2.4 GHz → HaLow RX | f(5) − 2 f(2.4) (1.3) | Product at the HaLow port ≤ −115 dBm/MHz | C9 |

902 to 928 MHz is not a restricted band, so FCC 15.247(d) only requires Wi-Fi emission there to be 20 dB below the in-band level per 100 kHz. Again the rule says nothing useful about a co-located receiver.

The likely shape of the answer, before measurement: if either radio's front end has little filtering at the other's band, the 43 to 45 dB examples are out of reach by antenna separation alone on this enclosure, and filtering at the antenna ports (2.5) is the practical fix. D-031 (scheduling after shielding, filtering, isolation and channel choice) is the fallback for any combination that still conflicts.

### 2.5 What achieves the budget

**GNSS antenna (B-21, open in GHO-11).** Selection requirements, from 2.2 and 1.5:

| Parameter | Requirement (proposed) |
|---|---|
| Gain at L1 | 25 to 30 dB including its cable, so that with a 2 dB SAW the MAX-M10S sees 10 to 30 dB (bypass or low-gain mode limits) |
| Filter ahead of the LNA | Published; ≥ 40 dB at 902 to 928 MHz, ≥ 35 dB at 2400 to 2500 MHz, ≥ 40 dB at 5150 to 7125 MHz relative to L1 |
| Linearity | Published input P1dB, IIP2 or IIP3, or a blocking level. The worked examples need IIP3 ≥ +10 dBm and IIP2 ≥ +40 dBm at the LNA input to keep IM products under 1 dB of degradation, or B1I disabled |
| Noise figure | ≤ 2 dB (A7) |
| Bands | L1 band covering 1559 to 1606 MHz (B1I to GLONASS) |
| Pattern | Zenith-pointing (patch or similar), low gain toward the horizon and below |
| Supply | Inside the TPS2553 50 mA minimum limit in the GHO-11 proposal |

**Placement (proposed for GHO-7).**

1. **GNSS antenna connector on the right-hand wall (X = 138 mm side), level with the GNSS block (Y 7 to 21 mm),** not on the top RF wall. A top-wall GNSS bulkhead at X ≈ 128 mm would sit 10 to 40 mm from the three Wi-Fi bulkheads (card at X 88 to 118 mm), and its feed would run 46 mm up the 2.5 mm gap beside the Wi-Fi card. A right-wall connector keeps the board feed under about 10 mm and puts the whole Wi-Fi card between the HaLow and GNSS antennas. The pack's hooks and latch are on the short ends (M-19, M-20), so GHO-7 must check the bulkhead against the latch release and pack insertion.
2. **GNSS antenna on the right end of the top face, pointing up,** or on a cable if the use case allows a remote antenna. Not on the finned lid area that D-035 assigns to cooling. The HaLow whip stays at the far left of the top wall (card X 7 to 29 mm): about 110 mm from the right end, 12.5 dB free-space at 915 MHz, plus whatever pattern discrimination the mount gives. A5 assumes 20 dB in total.
3. **Wi-Fi antennas:** whichever IPEX port carries only A-band (5/6 GHz) receive should get the bulkhead nearest the GNSS antenna, and the two ports that carry 2.4 GHz the farthest two. AsiaRF does not publish its port-to-chain map (**Unverified**; check on the bench cards).
4. Transmitting antennas mounted with their pattern nulls toward the GNSS antenna's boresight (vertical monopoles on a horizontal top face).
5. No GNSS RF feed, bias network or SAW under or beside the Wi-Fi card's RF end, the HaLow pigtail or the Wi-Fi pigtails.

**Filtering.**

| Where | Filter | Fixes | Status |
|---|---|---|---|
| GNSS feed, between bias tee and RF_IN (GHO-11 footprint behind 47 pF) | GNSS SAW, A4 | Blocking from all three transmitters | **Required; populate** |
| Inside the GNSS antenna | Pre-LNA filter, 2.5 table | Antenna LNA compression and intermodulation | Required by antenna selection |
| HaLow antenna path (MMCX pigtail or bulkhead) | Low-pass with cutoff about 1 GHz, or a 902 to 928 MHz band-pass | HaLow emission in the GNSS band, 6f and 7f into Wi-Fi | Only if C1 or C10 fails |
| Each Wi-Fi antenna path | High-pass with cutoff about 2 GHz | Wi-Fi emission in the GNSS band and in 902 to 928 MHz; 915 MHz blocking of the Wi-Fi front end | Only if C1, C9 or C10 fails |

Inline filters change the antenna system the modules were certified with. A passive filter only lowers EIRP, but the HaLow grant names the Pulse W1063 "or one with the same specification" (v1-reference.md §7) and the AsiaRF grant (FCC ID TKZAW7916-NPD) has its own antenna list. Whether an inline filter is a permissive change needs a test lab's answer (**Unverified**).

### 2.6 Verdict on the MAX-M10S external SAW

Populate it. GHO-11's proposal leaves the decision to T9 and T11; on the numbers above it is required, not optional. u-blox says an external SAW "may be required" for designs with other radios and describes the result as SAW, Band 13 notch, LNA, SAW "for the highest immunity" (manual R05 §4.3). The external-SAW footprint should stay a real SAW land, with a 0 Ω option only for the C4 A/B test. It still protects only the module: the antenna requirements in 2.5 are separate and also required.

## 3. Switcher placement review

### 3.1 Floorplan check

Edge-to-edge XY gaps (mm) from the firmware floorplan, branch `gho7-usbc-magnetics` commit `44aa670` (Calculated from `parts.yaml`; side ignored, so a bottom part counts as "under" a top part when the gap is 0).

| Part (side) | Switching? | HaLow card | HaLow socket | Wi-Fi card | Wi-Fi socket | GNSS block |
|---|---|---:|---:|---:|---:|---:|
| 5 V and 3.3 V LM76005 region, X 30–66, Y 3–17 (bottom) | Yes | 17.0 | 13.1 | 22.0 | 26.0 | 54.5 |
| BQ25798 + TPS25751A, X 38–60, Y 26–42 (bottom) | Yes (BQ25798) | 9.0 | 9.1 | 28.0 | 33.7 | 60.7 |
| TPS26633 eFuse block, X 62–80, Y 26–36 (bottom) | No inductor | 33.0 | 33.0 | 8.0 | 15.9 | 40.8 |
| Shunt + INA228, X 68–80, Y 3–11 (bottom) | No | 45.3 | 43.5 | 8.0 | 12.0 | 40.5 |
| Supervisor, X 70–79, Y 13–22 (bottom) | No | 42.7 | 41.8 | 9.0 | 13.0 | 41.5 |
| USB hub, X 39–53, Y 10–24 (top) | Crystal | 14.1 | 11.8 | 35.0 | 39.0 | 67.5 |
| OpenVLM DFP parts, X 72–80, Y 2–10 (top) | No (TPS2553 switch) | 49.2 | 47.5 | 8.1 | 12.0 | 40.5 |

Results:

- **No switching inductor or regulator sits under or over any RF module** (HaLow card and socket, Wi-Fi card and socket, GNSS block). The nearest switching region to an RF module is the charger, 9.0 mm from the HaLow card; the bucks are 17.0 mm from it. This matches the floorplan script's own rule check (`out/report.md`: no violations).
- **Every placed power part is at least 40.5 mm from the GNSS block**, against the 15 mm rule in v1-reference.md §18. The bucks are 54.5 mm edge to edge (80.6 mm centre to centre).
- The pack pogo zone sits below the HaLow socket (floorplan note). It carries pack current, not a switch node, so it does not break the rule; its return currents should not be routed under the HaLow card.
- The `usb_hub` entry in `parts.yaml` is still named "TI TUSB4020BI", which B-04 retired (D-023). Position is unaffected (section 5, item 7).

### 3.2 Switchers not yet in the floorplan: keepouts

| Part | Proposed keepout |
|---|---|
| LTC3350 switching stage: IC, inductor, FETs, sense resistors (B-24 candidate) | Top side at board X 55 to 85, Y 1.5 to 23 (D-047, [v1-bridge-selection.md](v1-bridge-selection.md) §3.5), which meets the same rules. Bottom-side alternative: inside the power band X 30 to 86, Y 0 to 26 (the free strip X 30 to 66, Y 17 to 26, between the bucks and the charger, fits the 5 x 7 mm QFN and its inductor). Not in the XY shadow of the HaLow card and socket (X 7 to 29, Y 30.1 to 64) or of the Wi-Fi card and socket (X 88 to 118, Y 7 to 62.9). At least 15 mm from the GNSS block. The supercapacitor stack is not a switch node and may go elsewhere, but the 10 A path ([v1-stackup-routing.md](v1-stackup-routing.md) §5) favours keeping it close |
| Hub 1.1 V buck (TLV62568 or alternative, GHO-10 proposal) | Beside the hub (X 39 to 53, Y 10 to 24), at least the hub-to-crystal distance from XI/XO and the USB pairs (TUSB4041I §7.4.1.1), not under the CM5 (top side), at least 9 mm from the HaLow socket (keep Y < 28 or X > 31) |
| TPS22975 load switches (blocked in the floorplan) | Not switchers. Keep the WIFI_3V3 burst loop (switch to socket bulk capacitors) on the socket side away from the GNSS column |
| Any future switcher | Same rules: not in the XY shadow of an RF module on either side, at least 15 mm from GNSS, switch node and input loop on L8 with L7 solid above |

### 3.3 Frequency, mode and spread spectrum

- **LM76005 x 2: keep 400 kHz, RT open, forced PWM (SYNC/MODE high).** None of the 200 to 500 kHz settable range moves harmonics out of the GNSS bands (1.6), and forced PWM keeps the lines fixed and predictable for C7. The datasheet lists no spread-spectrum feature (SNVSBK5A §1, §7). Syncing both bucks to one clock (SYNC accepts 200 to 500 kHz) would merge two harmonic combs into one, but needs a clock source that runs before the CM5 boots. Not recommended unless C7 shows the two combs beating.
- **BQ25798:** both frequencies put harmonics on L1 (1575.0 MHz at both). Prefer 1.5 MHz (one line in the C/A lobe instead of two, smaller inductor and switch-node area). Set PFM_FWD_DIS = 1 when charging while operating, so the line stays fixed (SLUSDV2C REG0x16). The datasheet shows no spread spectrum.
- **Hub 1.1 V:** the TLV62568 runs in power-save mode at the hub's active load. Calculated: with 2.2 µH, 3.3 V in, 1.1 V out and 1.5 MHz, ripple is 1.1 × (1 − 1.1/3.3) / (2.2 µH × 1.5 MHz) = 0.222 A, so it enters discontinuous mode below about 111 mA and the hub's 98 mA active figure (GHO-10 proposal) is in power-save mode. Its harmonics then wander with load. It is 67.5 mm (hub block) from the GNSS block, so this is minor. Alternative for the GHO-10 owner: TI TPS62A01A, forced PWM at 2.4 MHz, 2.5 to 5.5 V in (SLUSEG9E). It is not pin-compatible with the TLV62568 DBV.
- **LTC3350:** active only while charging the stack and during a pack swap. Its harmonics at L1 appear in C7 with the bridge charging and in backup.
- **Spread spectrum: not recommended for GNSS here** (engineering judgement, **Unverified** by measurement). At harmonic order 1000 to 4500, a ± 5 % dither spreads each line over about ± 79 MHz, overlapping hundreds of neighbouring harmonics. The power in the 2 MHz GNSS band stays about the same, but it changes from CW lines into broadband noise. The u-blox receiver can suppress CW interference (manual R05 §3.5.2) but not broadband noise.

### 3.4 Shielding

| Area | Recommendation |
|---|---|
| GNSS block (MAX-M10S, SAW, bias tee, RF feed and connector launch; X 120.5 to 136.5, Y 7 to 21) | **Lay out a two-piece shield (frame plus removable lid) on every build.** Populate the lid on half the first build, so C7 and T8 give an A/B answer. The Wi-Fi card is 2.5 mm away and its PCIe pairs reach the socket 6.5 mm away. The lid height must clear the lid-to-board gap under D-035's finned lid (GHO-7). u-blox also suggests shielding for thermal stability of the receiver's oscillator (manual R05 §4.4), which helps next to an 8 W card |
| Wi-Fi card RF end | Not shieldable from the carrier. Whether the AW7916-AED has its own RF can is not published (**Unverified**; inspect a bench card) |
| Bucks, charger, LTC3350 | No can needed by analysis: 40 mm or more from GNSS, bottom side, L7 solid above. Keep the inductors shielded-body parts (already in v1-reference.md §13) |
| Enclosure | The aluminium enclosure is the main shield. Bond every cable shield and RF bulkhead at the wall (GHO-11 proposal §3). The GNSS bulkhead's shell to the wall is the most important of these |

### 3.5 Layout keepouts (in addition to v1-stackup-routing.md §4)

- GNSS block and feed: L2 to L8 under the shield frame carry no signals and no power pours, only stitched ground. The RF feed, SAW and bias tee are inside the shield.
- No high-speed pair (PCIe, USB, MDI) within 5 mm of the shield frame. The Wi-Fi socket's PCIe breakout is the one to watch.
- Switch-node copper (SW pins, boot capacitors, input loops) only on L8, with L7 unbroken above, and never in the XY shadow of an RF module.
- The 24 MHz hub crystal and its load capacitors: guard ring to ground, not on an outer edge facing the GNSS column. Both its 65th harmonic and USB's 130th harmonic of 12 MHz land on B1I.

## 4. Prototype measurements

These size or replace the existing tests in [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §4. They run under [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23) (V1 validation) and [GHO-22](https://linear.app/ghostnet-labs/issue/GHO-22) (radio validation); C2 and C4 can also run on the Track A bench under [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31). Results go on the Linear issues, not here. All use the final antennas, bulkheads and enclosure unless stated, and never transmit into an open port.

Equipment beyond the T-test list: GNSS SAW evaluation board, RF signal generator with arbitrary waveform (802.11 20 MHz OFDM and 1 to 8 MHz HaLow-like OFDM), 1575 MHz band-reject and 900 MHz / 2.4 GHz notch filters for the analyzer input, directional couplers, a 50 Ω dummy load with a DC path for the antenna bias (about 12 mA), current probe for cables.

| ID | Test | Method | Pass criterion | Relates to |
|---|---|---|---|---|
| C1 | Conducted emissions at each transmitter port | Spectrum analyzer at the HaLow MMCX and each Wi-Fi IPEX through a notch for the carrier. 30 MHz to 18 GHz. HaLow swept across 902 to 928 MHz in its widest and narrowest channel (include 915.0 and 903.5 MHz); Wi-Fi at max power on channels 1, 6, 9, 11, a U-NII-2C channel containing 6f of the HaLow channel, and a 6 GHz channel containing 7f | 1555 to 1610 MHz density ≤ −178 + I(1575) dBm/Hz with I from C2 (−153 / −158 dBm/Hz with A6). HaLow 6f and 7f ≤ −102 + I(f) dBm in 20 MHz. Wi-Fi in 902 to 928 MHz ≤ −115 + I(915) dBm/MHz | Section 2.3, 2.4 |
| C2 | Antenna isolation | VNA S21 between every pair of antenna ports in the closed enclosure: HaLow → GNSS at 902–928 and 1559–1610 MHz; each Wi-Fi port → GNSS at 2.4, 5, 6 GHz and 1559–1610 MHz; HaLow ↔ each Wi-Fi port at 902–928 MHz, 2.4, 5.4–5.6 and 6.3–6.5 GHz. Repeat with the node hand-held and lying on its side | ≥ A5 and A6 (HaLow → GNSS 20 dB at 915 MHz, Wi-Fi → GNSS 15 dB at 2.4 GHz, 25 dB at 5/6 GHz; 25 / 20 dB at 1575 MHz), or the budget in 2.2 recomputed with the measured values still showing ≥ 0 dB margin | Replaces T11's single 35 dB figure (section 5, item 2) |
| C3 | Active antenna characterization | Gain and rejection vs. frequency (VNA, biased), input P1dB at 915 and 2440 MHz, two-tone IIP3 (2.4 + 6.4 GHz) and IIP2 (2462 + 903.5 MHz) at the antenna input | Meets the 2.5 antenna table | A1, A2; 1.4, 1.5 |
| C4 | Conducted GNSS blocking threshold | GNSS signal from live sky through a splitter (or a simulator) into the board's antenna port through a coupler. Inject a modulated blocker at 915, 2440, 5500 and 6400 MHz, step it up and record the level for a 1 dB drop in average C/N0, with the SAW populated and with 0 Ω; in bypass and low-gain LNA modes | Threshold ≥ the coupled level predicted by C2 + C3 + 6 dB, with the SAW populated | Sets the SAW verdict on hardware |
| C5 | Intermodulation | As C4, with two blockers: 2462 MHz (20 MHz OFDM) + 903.5 MHz (1 MHz), and 2412 MHz + 6399 MHz, at the levels C2 and C3 predict at the antenna input; then radiated with both radios on these channels | B1I C/N0 drop ≤ 1 dB (or B1I disabled by owner decision); L1 C/N0 drop ≤ 1 dB | 1.3, 1.4, 1.5 |
| C6 | Radiated desense, one aggressor at a time | T9 procedure. Each transmitter alone at maximum power and saturating duty cycle (iperf3), on the C1 channel set; UBX-MON-RF jamming state and UBX-MON-SPAN recorded | Average GPS L1 C/N0 drop ≤ 1 dB per single aggressor (design target, section 2); ITFM state 1 (OK) | T9 (its 3 dB all-on criterion stays the acceptance limit) |
| C7 | Board noise at RF_IN | Antenna port terminated in the biased dummy load. Analyzer with LNA at RF_IN (through a DC block) and UBX-MON-SPAN. Turn on one source at a time: each LM76005, BQ25798 charging at 1.5 MHz and at 750 kHz with PFM on and off, LTC3350 charging and in backup, hub 1.1 V buck, hub with traffic, PCIe link, CPU stress, Wi-Fi card idle and receiving, OpenVLM audio, Ethernet traffic. Shield lid on and off | Broadband ≤ −151 dBm/Hz at RF_IN; no discrete spur above −125 dBm within ± 2.046 MHz of 1561.098 or 1575.42 MHz | Extends T8 (which scans with the antenna attached) |
| C8 | Cable-borne emission | Current probe at 1575 MHz on the Ethernet cable and the OpenVLM USB-C cable, and C/N0 with each cable routed past the GNSS antenna | C/N0 drop ≤ 0.5 dB with the cable 10 cm from the GNSS antenna | T8's cable check |
| C9 | HaLow desense | HaLow sensitivity (lowest MCS, 10 % PER, conducted through an attenuator from a second node) with the Wi-Fi card at max on each band; with 2.4 + U-NII-3 DBDC (f(5) − 2 f(2.4) landing on the HaLow channel). Then the conducted blocking level B_H at 2440 MHz | Sensitivity loss ≤ 3 dB, or the combination recorded as a D-031 scheduling candidate. B_H recorded and the 2.4 table recomputed | 2.4 |
| C10 | Wi-Fi desense | Wi-Fi sensitivity on 2.4 GHz, on a 5 GHz channel containing 6 f_H and a 6 GHz channel containing 7 f_H, with HaLow at max. Then the conducted blocking level B_W at 915 MHz | Sensitivity loss ≤ 3 dB, or the channel pair added to the controller's exclusions. B_W recorded | 1.2, 2.4 |
| C11 | Switching frequency over temperature | Measure the actual f_sw of each converter at the D-028 endpoints during T4 | Recorded; reused to place spurs found in C7 | 1.6 |
| C12 | TTFF and fix under all transmitters | T10 and T12 unchanged | T10 and T12 criteria | – |

Order: C2 and C3 first (they replace A2, A5 and A6), then C1 and C4, then the system tests.

## 5. Proposed text for the records owner

Not applied here. Each item names the record and the text the owner can apply if the project owner agrees.

1. **v1-thermal-rf-plan.md §3, row "HaLow fundamental blocking", "What to check":** replace "Measure antenna isolation and C/N0." with "Budget in [v1-rf-coexistence.md](v1-rf-coexistence.md) §2.2: with a filtered active antenna and the external SAW, about 20 dB of HaLow-to-GNSS isolation leaves 21.5 dB of margin; without the SAW it needs about 38.5 dB. Measure isolation (C2) and C/N0." Add a row "Intermod: f(2.4 GHz) minus f(HaLow) on BeiDou B1I only when 2.4 GHz channels 9 to 11 run with HaLow's lower edge below 913 MHz (v1-rf-coexistence.md §1.4)."
2. **v1-thermal-rf-plan.md §4, T11 pass:** replace "HaLow to GNSS at least 35 dB (estimate from D-020; confirm against T9)." with "Each pair meets the isolation assumed in v1-rf-coexistence.md §2.1 (A5, A6), or the §2.2 budget recomputed with the measured values keeps a margin of 0 dB or more."
3. **v1-thermal-rf-plan.md §4:** add "C1 to C12 in v1-rf-coexistence.md §4 size and extend T8 to T11."
4. **v1-reference.md §9 (GNSS), after "integrated LNA and SAW filter":** add "An external GNSS SAW filter is populated between the antenna bias tee and RF_IN, and the internal LNA runs in bypass mode (CFG-HW-RF_LNA_MODE) because the external active antenna gives 10 dB or more of gain ([v1-rf-coexistence.md](v1-rf-coexistence.md) §2.2, §2.6). The active antenna must have a filter ahead of its LNA (§2.5)."
5. **GHO-11 proposal `v1-eth-gnss-protection.md` §2.4 item 3 (branch `gho11-eth-gnss`, not merged):** replace "Whether to populate the SAW is set by the T9 and T11 tests in v1-thermal-rf-plan.md." with "Populate the SAW by default ([v1-rf-coexistence.md](v1-rf-coexistence.md) §2.6); the 0 Ω option exists only for the C4 A/B test." Add the §2.5 antenna table to the B-21 selection criteria.
6. **v1-reference.md §18, placement rules, GNSS line:** add "The GNSS antenna connector sits in the right-hand wall level with the GNSS block, not on the top RF wall (v1-rf-coexistence.md §2.5); a two-piece shield frame surrounds the GNSS receiver, SAW, bias tee and feed." GHO-7 owns the decision and the latch check.
7. **firmware `docs/hardware/v1-mechanical/parts.yaml` (GHO-7):** rename `usb_hub` from "TI TUSB4020BI" to "TI TUSB4041IPAPRG4" (B-04, D-023). Add a `switching: true` envelope for the LTC3350 power stage and one for the hub 1.1 V buck with the §3.2 keepouts, and a `gnss_shield` keepout for the frame. Rerun the check.
8. **v1-selections.md, "PCB and thermal approach":** "No inductors, regulators, or tall parts go under the CM5" reads as forbidding the floorplan's bottom-side charger (X 38–60, Y 26–42) and eFuse block (X 62–80, Y 26–36), which sit in the CM5's XY shadow on the other side of the board. v1-reference.md §18 places them there deliberately. Proposed wording: "No inductors, regulators, or tall parts go between the CM5 and the carrier (top side, 2.5 mm clearance). Bottom-side power parts may sit in the CM5's shadow; the CM5 is not an RF module." This is not an RF conflict (the CM5008032 has no radio); it is listed because the RF rule uses the same "under" wording.
9. **GHO-10 proposal `v1-netplan-blocker-proposals.md` K-9 (branch `gho10-netplan-blockers`, not merged):** add after the TLV62568 part line: "At the hub's 98 mA active load the TLV62568 is in power-save mode (DCM below about 111 mA with 2.2 µH), so its frequency varies with load. If C7 shows its harmonics in the GNSS band, the forced-PWM TPS62A01A (2.4 MHz, SLUSEG9E) is the alternative; it is not pin-compatible."
10. **README.md ownership table:** add a row "V1 RF coexistence: frequency plan, isolation budget, switcher placement review and coexistence measurements C1 to C12 | `[hardware/v1-rf-coexistence.md](hardware/v1-rf-coexistence.md)` (supporting; registers and v1-thermal-rf-plan.md test IDs win)".

## 6. Decisions only the owner can make

1. **BeiDou B1I or B1C.** The default GPS + Galileo + B1I mode is exposed to the HaLow/2.4 GHz second-order product and to 1560 MHz clock harmonics (24 MHz × 65, 12 MHz × 130). GPS + Galileo + B1C (data sheet R08 Table 2: 28 s cold start against 27 s) avoids all three. The alternative is a channel-controller rule that keeps 2.4 GHz channels 9 to 11 away from HaLow channels starting below 913 MHz.
2. **External SAW populated as standard** (a BOM addition). Recommended.
3. **GNSS antenna type and location:** on the enclosure (patch, top face, right end) or remote on a cable. This sets A5 more than any other choice.
4. **Inline filters on the HaLow and Wi-Fi antenna paths**, if C1, C9 or C10 fail, including the test-lab question on the modular grants.
5. **Channel exclusions in openmanetd** (HaLow 6f and 7f against 5/6 GHz Wi-Fi channels; B1I item above) against D-029's all-band roles and D-041's admission rules, versus D-031 scheduling.
6. **GNSS shield lid** populated in production, after C7.

## 7. What is unverified

- GW16170 conducted power (+28.5 dBm is the MM8108-M20 figure from a news article and the record), harmonic and in-GNSS-band emission levels, synthesizer spurs and receiver blocking. No GW16170 or MM8108-M20 datasheet was obtained.
- AW7916-AED: 6 GHz power (A-band figure used), port-to-chain map, out-of-band emission, receiver blocking, and whether the card has RF shielding. AsiaRF publishes a one-page datasheet and a product page only.
- MAX-M10S immunity above 3300 MHz (−18 dBm assumed) and in bypass LNA mode (Table 43 is low-gain mode, typical, room temperature).
- Every assumption A1 to A9, in particular the antenna's pre-filter rejection, linearity and noise figure, and all isolation figures. The free-space values are orientation only.
- The LTC3350 spread-spectrum capability (its 500 kHz nominal frequency is now recorded from Rev. D).
- BQ25798 switching-frequency tolerance (typical values only in SLUSDV2C).
- Whether the CM5 has 25 MHz or 54 MHz references, its SoC and LPDDR clock plan, and whether its PCIe REFCLK uses spread spectrum.
- The 2 ns switch-node edge in the amplitude example and the 61 dB coupling it implies.
- The IIP2 and IIP3 figures in the intermodulation examples.
- Whether inline antenna-path filters are permissive changes under the module grants.
- The spread-spectrum recommendation is engineering judgement, not a measurement.

## Sources

Fetched 2026-10-09 unless stated.

- u-blox [MAX-M10S data sheet UBX-20035208 R08](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf) (30 Jan 2026): Table 2 (modes, TTFF, default B1I), Table 4 (signals), Table 12 (0 dBm RF_IN absolute maximum), Table 13 (NF 1.5 dB; external gain limits).
- u-blox [MAX-M10S integration manual UBX-20053088 R05](https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf) (28 Apr 2026): §3.5.2 (jamming detection), §4.2, §4.3 (front end, external SAW), §4.3.1 (LNA modes), §4.3.2 and Table 43 (immunity), §4.3.3 (rejection), §4.4 (layout).
- AsiaRF [AW7916-AED product page](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) (output power, sensitivity, bands, FCC ID TKZAW7916-NPD) and [datasheet V1](https://asiarf.com/wp-content/uploads/2026/07/260709_Datasheet_AW7916-AED_V1-1P.pdf) (G-band 2T2R, A-band 2T3R DBDC).
- [CNX Software, 2026-06-03](https://www.cnx-software.com/2026/06/03/morse-micro-mm8108-m20-high-power-wi-fi-halow-module-delivers-up-to-28-5-dbm-tx-output-power/): MM8108-M20 up to 28.5 dBm (secondary source).
- TI [LM76005 SNVSBK5A](https://www.ti.com/lit/ds/symlink/lm76005.pdf): §6.5 fOSC 350/400/450 kHz with RT open, 200 to 500 kHz range; SYNC/MODE pin; PFM and FPWM.
- TI [BQ25798 SLUSDV2C](https://www.ti.com/lit/ds/symlink/bq25798.pdf): FSW 1.5 MHz / 750 kHz, Table 7-1, PWM_FREQ, PFM_FWD_DIS.
- TI [TLV62568 SLVSD89B](https://www.ti.com/lit/ds/symlink/tlv62568.pdf): 1.5 MHz, power-save mode.
- TI [TPS62A0x SLUSEG9E](https://www.ti.com/lit/ds/symlink/tps62a01.pdf): 2.4 MHz, TPS62A0xA forced PWM.
- TI [TPS2663 SLVSE94G](https://www.ti.com/lit/ds/symlink/tps2663.pdf): no switching regulator.
- 47 CFR [15.205](https://www.ecfr.gov/current/title-47/part-15/section-15.205) (restricted bands, including 960–1240, 1435–1626.5, 2690–2900 MHz and 5.35–5.46 GHz) and [15.209](https://www.ecfr.gov/current/title-47/part-15/section-15.209) (500 µV/m at 3 m above 960 MHz), via the eCFR API.
- Firmware floorplan, [ghostnet-labs/firmware](https://github.com/ghostnet-labs/firmware) branch `gho7-usbc-magnetics`, commit `44aa670`: `docs/hardware/v1-mechanical/parts.yaml`, `out/report.md`.
