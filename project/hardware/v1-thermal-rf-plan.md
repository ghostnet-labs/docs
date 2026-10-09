# V1 thermal budget and RF coexistence plan

**Owner:** [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12), model the fanless enclosure thermal paths and RF coexistence.  
**Status:** first-pass estimate revised against D-028 on 2026-10-03; enclosure model re-run for the bridge tray on 2026-10-09 in [v1-thermal-update-tray.md](v1-thermal-update-tray.md) (D-051). No hardware measured yet; no qualification claimed. Validation runs under [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23); rail sizing is [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10).

This file models heat and GNSS interference for the V1 carrier and sets the first-board tests. Decisions it depends on live in [decisions.md](../decisions.md): D-028 (requirement) and D-035 (finned lid). Part values come from [v1-selections.md](v1-selections.md), [v1-reference.md](v1-reference.md), [v1-3v3-rail.md](v1-3v3-rail.md) and [v1-battery-pack.md](v1-battery-pack.md); if they change, those files win. Every number here is tagged as a datasheet fact, an estimate, or "to measure".

## Summary

- Internal heat is about **16 W typical and 25 W peak** (estimate). Track A's 10 W typical figure predates the AW7916-AED, whose vendor average alone is 8 W. The closure case is **18.5 W** (typical with the card at its 10 W maximum), with 25.4 W as a stress case (D-051).
- The sealed 145 x 74 x 50 mm aluminum body (27 mm plus the D-048 bridge tray) with the D-035 fins sheds about **0.64 to 0.91 W/K** (estimate). At 18.5 W and the 43.3 °C D-028 endpoint the case runs at about **64 to 72 °C**. Model and per-part results: [v1-thermal-update-tray.md](v1-thermal-update-tray.md) §3.
- **Results at the hot endpoint (calculated, 18.5 W, planning h):** the AW7916-AED is about 27 K over its 70 °C rating with or without the tray; the CM5 has +1.7 K to its 85 °C throttle point; the GW16170 is about 7 K over an assumed 70 °C; GNSS and the LM76005 die are marginal; the hottest bridge supercaps reach 75 to 82 °C against 85 °C.
- **Thermal requirement: D-028.** Normal operation must not depend on performance throttling. Passive thermal pads, heat spreaders/heatsinks and enclosure area must close the heat budget; the current flat-shell model is not proof of compliance.
- **Selected passive path: D-035, a finned lid.** External fins on the enclosure lid, with the AW7916-AED and the CM5 padded to the lid. Software temperature throttling is only a last-resort emergency backstop. Fin geometry, the height it adds and the pad stack are still to size ([GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7)).
- **Top component risk: B-03.** AsiaRF's [product specification](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) states operating −10 to +70 °C (checked 2026-10-03). D-028's cold endpoint is below that published range. Supplier clarification/qualification is required; storage temperature is not an operating rating. The published upper bound is not identified as a shield-surface or junction limit, so the model cannot establish a component pass/fail by comparing a thermocouple with 70 °C.
- RF: the largest GNSS risks are the GW16170 at up to +28.5 dBm (blocking) and the Wi-Fi card 2.5 mm from the GNSS receiver (near-field noise). Two intermod products and two clock harmonics land on GNSS bands and need targeted tests.

## 1. Heat sources

| Source | Typical W | Peak W | Basis |
|---|---:|---:|---|
| CM5 (SoC, LPDDR, eMMC, Gigabit PHY) | 4.5 | 7 (estimate) | CM5 datasheet §3.3: operating about 900 mA at 5 V, idle about 400 mA. Peak is an estimate; to measure. |
| Wi-Fi, AsiaRF AW7916-AED | 8 | 10 | AsiaRF datasheet and product page: 10 W max, 8 W average at 3.3 V. The heatsink bundle listing on the same page says 9 W max, 4 to 8 W average. Worst case sustained 10 W (D-026); modelled in v1-thermal-update-tray.md. |
| HaLow, GW16170 | 1 (estimate) | 3.3 | 1.0 A peak at 3.3 V, earlier estimate in v1-3v3-rail.md. Typical to measure. |
| GNSS, MAX-M10S plus antenna bias | 0.03 | 0.33 | 25 mW tracking (u-blox datasheet); peak is the 0.1 A rail allocation. |
| USB hub, TUSB4041I | 0.2 (estimate) | 0.3 (estimate) | To measure. |
| Misc 3.3 V (INA228, supervisor, pull-ups) | 0.3 | 0.8 | 0.25 A misc allocation, v1-3v3-rail.md. |
| LTC3350 bridge stage (B-24) | 0.05 to 0.12 | 2.2 (charge mode, ≤ 210 s); 2.8 (backup, ≤ 13 s) | [v1-thermal-update-tray.md](v1-thermal-update-tray.md) §2. Transient losses do not change the case temperature. |
| 3.3 V buck loss (LM76005) | 1.2 | 2.0 | v1-3v3-rail.md: 3 A typical, 4.5 A peak, about 88 % efficient. |
| 5 V buck loss (LM76005) | 0.6 (estimate) | 1.0 (estimate) | About 90 % at 5 to 8 W out. To measure. |
| WIFI_3V3 switch, TPS22975 | 0.15 | 0.2 | v1-3v3-rail.md. |
| Input path (blocking FET, eFuse, shunt) | 0.1 (estimate) | 0.3 (estimate) | I²R at 1.5 to 2.5 A. To measure. |
| **Total inside the radio body** | **about 16** | **about 25** | Estimate. Under the 35 W capability target. |

Not counted: the OpenVLM accessory (powered over VBUS, dissipates outside), and charger losses when the pack charges in the radio (BQ25798, B-09). Charging while operating adds heat; to measure. If the Wi-Fi card averages 4 W (low end of AsiaRF's range), the typical total drops to about 12 W.

## 2. Heat path

Each source reaches ambient through one of three paths:

| Source | Path to the enclosure | Notes |
|---|---|---|
| CM5 SoC | TIM pad from the SoC to the lid (v1-reference.md §15) | CM5 datasheet: CM5 has less passive heat sinking than a Pi 5. |
| AW7916-AED | Needs a TIM pad from the card's hot side to the lid | Without one, heat must leave through the M.2 socket contacts and still air. See below. |
| GW16170 | TIM pad to the lid if its temperature needs it | Lower power; to measure. |
| Bucks, switch, eFuse | Copper pours and thermal vias to a side-wall contact (§15, D-051) | Bottom side, X 30 to 66, Y 3 to 17. The bridge tray (D-048) covers the underside, with a 1 mm insulating sheet over the cells. |
| Everything else | Board copper and internal air | Small. |

**Enclosure assumptions (estimates).** Radio body 145 x 74 x 50 mm: 27 mm plus the 23.0 mm bridge tray (D-048). The battery pack covers the bottom face, so only the top and four sides shed heat: about 0.0326 m². Natural convection h_c = 5 to 10 W/m²K. Radiation h_r = 4εσT³ is about 6.9 W/m²K for an anodized or painted finish (ε = 0.85, mean surface about 330 K) and under 1 W/m²K for bare aluminum (ε about 0.1). Combined h is 12 to 17 W/m²K anodized, 6 to 11 bare. **Finish the enclosure anodized or painted; bare aluminum roughly halves the heat it can shed.** With fins (D-035) held at the decision card's estimate, R case to ambient is 1.55 K/W (planning) or 1.11 K/W (good). The pack interface is a thermal break, so the pack sidewalls do not count as shedding area (D-051, R-26).

**Internal rises (estimates).** CM5 SoC to lid through a pad: 2 to 3 K/W, so +9 to 14 K at 4.5 W. Wi-Fi card to lid through a pad: 2 to 3 K/W, so +20 to 30 K at 10 W. Wi-Fi card with no pad: 10 K/W or more through the socket and air, so +100 K or more. Internal air sits 5 to 15 K above the case.

The resistance table (27, 50 and 66 mm bodies, flat and finned), the load cases and the predicted part temperatures at 43.3 °C are in [v1-thermal-update-tray.md](v1-thermal-update-tray.md) §3 and §3.1; what it would take to pass is §3.2.

The 25 W peak is a transient. The body's heat capacity is roughly 420 J/K with the tray (estimate), giving a time constant near 11 minutes, so bursts of a few minutes are averaged out.

**What this means.**

1. **The Wi-Fi card needs an engineered heat path to the lid.** The no-pad model predicts a large temperature rise, but a surface-temperature pass/fail needs a supplier-defined limit. AsiaRF sells the card with a 30 x 30 x 10 mm heatsink; it is a useful bench reference, but 10 mm likely does not fit under the lid, so plan a pad to the lid instead. Whether the 70 °C rating is ambient or card surface is not stated; ask AsiaRF.
2. **No passive path meets a 70 °C card limit at 43.3 °C and 10 W.** It needs about 10.9 W/K at a 2.5 K/W pad against the 0.64 W/K modelled (v1-thermal-update-tray.md §3.2). The vendor rating is not a verified surface target, and D-028 does not allow a nominal power cap; the card choice is the open blocker (D-051).
3. **The model does not demonstrate D-028 compliance.** The finned lid (D-035) is modelled only as the decision card's "doubles shedding" estimate, held constant. Size the fins, pad stack and any spreader against the D-028 endpoints within the GHO-7 envelope; do not use Wi-Fi-off operation or a lower ambient rating to silently change the requirement. Heat flow into the pack requires explicit cell-temperature analysis, not treating the battery as a free heatsink.
4. **Touch temperature.** A handheld case at 60 to 85 °C is too hot to hold. Check against IEC 62368-1 touch limits once the case temperature is measured.
5. **GNSS sits 2.5 mm from the Wi-Fi card** (§18). The MAX-M10S is rated to +85 °C ambient, and its TCXO drifts with temperature. Measure its local temperature.
6. **Battery cells sit under the radio.** The M35A charge window ends at 45 °C, and the case runs at about 50 °C even at the 21.1 °C nominal ambient. The pack interface is a thermal break (D-051), and the pack does not charge in the radio at the hot endpoint. Check the charge and discharge limits against the measured pack top temperature.
7. **The bridge supercaps sit in the tray under the bottom-side bucks and charger.** They reach 75 to 82 °C at the hot endpoint and 18.5 W, against 85 °C at ≤ 2.3 V. Fit a 1 mm insulating sheet, put the bank NTC on the hottest cell (row A right) and step the charge code down when hot (D-051).

**Telemetry and emergency protection, not nominal throttling.** Read available radio/CM5 temperature sensors and INA228 power; verify sensor locations and meanings on the selected hardware. D-028 rejects the former throttle ladder. Do not disable built-in component or battery protections. An emergency reduction/shutdown outside the qualified envelope must be reported as a fault and does not count as meeting the normal operating requirement.

Passive-design evidence required before qualification:

| Evidence | Required result |
|---|---|
| Supplier limits | Operating ambient, measured sensor/surface limits and cold-start behavior distinguished for each limiting part |
| Thermal-interface stack | Actual gap, pad conductivity/compression, lid fin geometry (D-035), spreader geometry and contact pressure checked in GHO-7 |
| Continuous load | Measured simultaneous CPU/radio/accessory demand and charging losses used, not a throttled profile |
| Touch comfort | Contact surfaces and usage duration defined in GHO-12; measured case temperatures meet the agreed criterion |
| Qualification | Endpoint operation with no automatic CPU throttling or policy-driven TX/channel reduction; faults and protection events recorded |

The M.2 contact-current concern in v1-3v3-rail.md is a separate electrical gate: cooling does not increase connector current ratings, and TX limiting is not a substitute for a compliant power delivery design.

## 3. RF coexistence with GNSS

The MAX-M10S tracks GPS L1 at 1575.42 MHz and, by default, Galileo E1 and BeiDou B1I (1561.098 MHz), plus QZSS and SBAS (u-blox datasheet). It has an LNA and SAW filter. Absolute maximum RF input is 0 dBm. For the related SAM-M10Q, u-blox states typical out-of-band immunity of 0 dBm across 400 to 1460 MHz and 1710 to 3300 MHz. The external active antenna has its own LNA, which can saturate before the module's filter.

| Mechanism | Frequencies | Risk | Mitigation in the design | What to check |
|---|---|---|---|---|
| HaLow fundamental blocking | 902 to 928 MHz at up to +28.5 dBm | High | GNSS in the far corner, about 116 mm from the HaLow card; external antennas | D-020 estimate: about 21 dB isolation is clean to about 15 dBm, so +28.5 dBm needs about 35 dB (estimate). Budget in [v1-rf-coexistence.md](v1-rf-coexistence.md) §2.2: with a filtered active antenna and the external SAW, about 20 dB of HaLow-to-GNSS isolation leaves 21.5 dB of margin; without the SAW it needs about 38.5 dB. Measure isolation (C2) and C/N0. |
| HaLow harmonics | 2nd 1804 to 1856 MHz, 3rd 2706 to 2784 MHz | Medium | Module filtering; 2nd is about 230 MHz above L1 | Blocking only, not in band. Check with HaLow at max power. |
| Wi-Fi blocking | 2.4, 5, 6 GHz at up to 23 dBm (11b, AsiaRF) | Medium | External antennas; 2.4 GHz is in the 0 dBm immunity range | C/N0 per band at max power. |
| Wi-Fi card near-field noise | Broadband digital and PA noise | High | None yet; card is 2.5 mm edge to edge from GNSS | Near-field probe scan; consider a shield fence or moving GNSS. |
| Intermod: f(2.4 GHz) minus f(HaLow) | 1472 to 1571 MHz (US channels 1 to 11) | Medium | Antenna separation; GNSS tracks B1C, not B1I (D-045) | Lands on BeiDou B1I only when 2.4 GHz channels 9 to 11 run with HaLow's lower edge below 913 MHz (v1-rf-coexistence.md §1.4). Test HaLow plus 2.4 GHz channels 6 to 11 together. |
| Intermod: f(6 GHz) minus 2 × f(2.4 GHz) | about 980 to 2325 MHz | Low to medium | Same | DBDC can run both bands at once. Test 6 GHz plus 2.4 GHz together. |
| Buck switching harmonics | n × 400 kHz; orders about 3936 to 3941 fall in the C/A main lobe | Low to medium | Forced PWM, fixed frequency; SYNC can lock both bucks; bucks about 81 mm away; no inductor under RF; power at least 15 mm from GNSS | Exact spur positions shift with oscillator tolerance. Scan 1559 to 1610 MHz with each buck on and off. |
| USB hub 24 MHz crystal | 65 × 24 = 1560 MHz, 66 × 24 = 1584 MHz | Medium | Hub in lower centre, away from GNSS | 1560 MHz is 1.1 MHz from B1I. Scan with the hub active. |
| USB 2.0 high-speed data | Broadband, 480 Mb/s | Low | Short routes, ESD on ports | Scan during OpenVLM audio and HaLow traffic. |
| PCIe 100 MHz refclk and 5 GT/s data | 16 × 100 = 1600 MHz | Low to medium | PCIe routed on inner layers with GND reference | 1600 MHz is inside GLONASS L1, which is off by default. Scan anyway. |
| CM5 SoC and LPDDR clocks | Not in our documents | Unknown | CM5 metal shield; GNSS far from CM5 routing | Find by scan with CPU stress on and off. |
| Ethernet 1000BASE-T | Energy mostly under 125 MHz; 125 MHz harmonics | Low | Magnetics and feed-through at the left wall, about 128 mm away | Scan during sustained traffic; check cable common-mode near the GNSS antenna. |
| Supply noise into GNSS | Buck ripple on +3V3_RADIO | Low | Filtered +3V3_GNSS | Ripple at the module during Wi-Fi bursts. |

Rule from the records: do not add a generic TVS on the GNSS RF line (v1-reference.md §9). Pick an antenna with filtering ahead of its LNA if blocking shows up.

## 4. First-board test plan

Common equipment: K-type thermocouples (at least 12 channels) with a logger; IR camera with emissivity tape; bench supply at 12.0 V with current readout; USB-C power meter; spectrum analyzer or SDR (covering 1.5 to 1.7 GHz) with a near-field probe set; VNA for isolation; u-blox u-center for C/N0, fix type and TTFF; a reference GNSS receiver on a splitter from the same antenna; `iperf3`, `stress-ng`, and [`bench-log.sh`](../poc/bench-log.sh). Run all RF tests with the final antennas in their final positions.

**C/N0 metric.** Average C/N0 of all GPS L1 satellites above 30° elevation, over 10 minutes, minus the same from the reference receiver to cancel sky changes. "Drop" is this value against the all-radios-off baseline.

**T0. Baseline on the CM5 bench (Track A POC, before V1 exists).**
- Setup: Track A node (CM5, GW16167, SAM-M10Q) per [GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) and [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31); then one AW7916-AED on the CM5 PCIe x1 once the bench cards arrive.
- Equipment: inline DC current meter on the card's 3.3 V feed, USB-C meter, thermocouples on the card and socket, IR camera, u-center.
- Procedure: log power and temperature idle, then 30 minutes of full-rate 802.11s on both bands, open air and inside the Bud box. Record HaLow power where C/N0 starts to fall (D-020). Repeat C/N0 with the AW7916-AED transmitting on each band.
- Pass: sustained and peak card power are measured and replace the estimates in §1. Compare card/socket current with manufacturer ratings; any cap needed to keep the bench safe is recorded as a limitation, not a compliant V1 solution.

**T1. Power map.**
- Setup: V1 board on a bench supply, open.
- Procedure: read INA228 and supply current in each state: idle; CPU stress; Wi-Fi each band at max; HaLow at max; all at once; charging while operating.
- Pass: totals within 20 % of §1, or §1 updated. Peak input under the eFuse limit.

**T2. Open-board thermal survey.**
- Setup: board open on a stand at 25 °C, all loads at max for 30 minutes.
- Equipment: IR camera, emissivity tape.
- Pass: hot spots identified and thermocouple sites confirmed. Nothing above its rating.

**T3. Closed enclosure, nominal ambient from D-028.**
- Setup: sealed V1 enclosure with pads fitted, pack attached, still air.
- Thermocouples: Wi-Fi card shield, M.2 socket contacts, GW16170, MAX-M10S, CM5 lid above the SoC, LM76005 (3.3 V) and its inductor, TPS22975, eFuse, internal air, lid centre, each side wall, pack top. For the bridge tray also: the row A and row B right cells, the tray air, the bank NTC, the LTC3350 inductor and the pack plate. Also log the SoC sensor and the MT7916 hwmon.
- Procedure: run idle, 10 W and typical load profiles to steady state (rate of rise under 1 K per 10 minutes).
- Pass: no part exceeds its applicable supplier-defined limit, with the design margins recorded; distinguish ambient, case and junction limits rather than treating them as interchangeable. No CPU/radio throttling at the full continuous-load profile. Touch-comfort criterion passes. Compare measured case-to-ambient resistance with §2.

**T4. Hot and cold endpoint qualification.**
- Setup: as T3 at the D-028 hot endpoint in still air; repeat unpowered-soak startup and operation at its cold endpoint only after component operating limits and safe battery conditions are verified.
- Procedure: soak to thermal equilibrium, then run simultaneous full continuous-load profiles for at least 2 hours and until temperatures stabilize. Include charging while operating only inside the cell/charger permitted temperature range. Include a pack swap and a full bridge recharge, and log the bank NTC and meas_cap (bridge test B7). Log all channels, clocks, throttle/protection flags, TX settings, traffic, mesh continuity and audio/PTT.
- Pass: required functions operate without nominal throttling, link loss or reset; supplier limits, design margins and touch comfort pass. A rating conflict or unqualified cold startup is a failed/open gate, not waived by self-heating.

**T5. Emergency protection.**
- Procedure: with an approved controlled fault-injection plan, verify existing component/pack protections and EUD fault reporting without exceeding absolute maxima or disabling protection. Final setpoints belong to GHO-12/GHO-10.
- Pass: protections remain effective, fault events are visible, recovery is bounded, and no emergency behavior is used to claim a T3/T4 normal-operation pass.

**T6. Wi-Fi thermal interface A/B.**
- Procedure: repeat T3 typical load with no pad, two pad thicknesses, and the AsiaRF heatsink on the open bench as a reference.
- Pass: chosen pad keeps the card at least 10 K cooler than no pad and fits the lid gap with the specified compression.

**T7. GNSS baseline.**
- Setup: open-sky antenna on a splitter to V1 and the reference receiver. All radios off (WIFI_PWR_EN and HALOW_PWR_EN low), Ethernet unplugged, CPU idle.
- Procedure: 30 minutes of C/N0; 10 cold starts and 10 hot starts.
- Pass: C/N0 within 1 dB of the reference receiver. Cold TTFF near the datasheet's 29 s (GPS, open sky) and under 60 s; hot start about 1 s.

**T8. Spectrum scan near GNSS.**
- Equipment: spectrum analyzer or SDR with near-field probe; a DC block and LNA on the GNSS antenna port.
- Procedure: scan 1555 to 1610 MHz over the board and at the antenna port. Turn on one source at a time: each buck, hub, PCIe link up, CPU stress, Ethernet traffic, OpenVLM audio, Wi-Fi idle, and the LTC3350 stage in charge mode (after a swap; harmonic 3151 of 500 kHz is 1575.5 MHz).
- Pass: no spur within ±2 MHz of 1561.098 or 1575.42 MHz above the noise floor at the antenna port. Any spur found is traced to a source and fixed or explained.

**T9. Radio desense.**
- Procedure: from the T7 baseline, measure C/N0 for each: HaLow stepped to +28.5 dBm; Wi-Fi 2.4, 5 and 6 GHz each at max with saturating `iperf3`; HaLow plus 2.4 GHz channels 6 to 11; 6 GHz plus 2.4 GHz; everything at max with CPU stress and Ethernet traffic; the all-on case again during a bridge recharge.
- Pass: C/N0 drop of 3 dB or less with Wi-Fi and HaLow transmitting at max against all radios off. No loss of 3D fix. If it fails, record the TX power where the drop reaches 3 dB.

**T10. TTFF under load.**
- Procedure: 10 cold starts with all radios at max.
- Pass: median cold TTFF no more than 1.5 times the T7 median and under 60 s.

**T11. Antenna isolation.**
- Equipment: VNA.
- Procedure: measure S21 from the HaLow port and each Wi-Fi port to the GNSS antenna port, with final antennas mounted.
- Pass: each pair meets the isolation assumed in [v1-rf-coexistence.md](v1-rf-coexistence.md) §2.1 (A5, A6), or the §2.2 budget recomputed with the measured values keeps a margin of 0 dB or more.

C1 to C12 in [v1-rf-coexistence.md](v1-rf-coexistence.md) §4 size and extend T8 to T11.

**T12. Hot GNSS.**
- Procedure: log C/N0, fix and PPS during T4.
- Pass: fix held, C/N0 within 2 dB of T7, PPS present throughout.

## 5. Unknowns to close

- AW7916-AED: real sustained power, whether 70 °C is ambient or surface, and where the hot side is (T0, AsiaRF). An industrial-temperature MT7916 card is screened alongside (D-051).
- GW16170 typical power and CM5 peak power (T0, T1).
- Enclosure size, finish, wall thickness and lid gap ([GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7)).
- Thermal requirement is D-028; GHO-12 owns component-rating reconciliation, touch-comfort acceptance and passive-design closure.
- Molicel M35A temperature limits against the measured pack top.
- CM5 clock frequencies near GNSS bands (T8).

## Links

- [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12): this work.
- [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23): V1 validation, where tests T1 to T12 run alongside [v1-validation-procedures.md](v1-validation-procedures.md).
- [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10): 3.3 V rail and power path; uses T0 and T1 results.
- [GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) and [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31): Track A power, thermal and GPS coexistence, which feed T0.
