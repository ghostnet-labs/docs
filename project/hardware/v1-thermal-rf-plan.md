# V1 thermal budget and RF coexistence plan

**Owner:** [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12), model the fanless enclosure thermal paths and RF coexistence.  
**Status:** first-pass estimate, 2026-10-02. No hardware measured yet. Validation runs under [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23); rail sizing is [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10).

This file models heat and GNSS interference for the V1 carrier and sets the first-board tests. It records no decisions. Part values come from [v1-selections.md](v1-selections.md), [v1-reference.md](v1-reference.md), [v1-3v3-rail.md](v1-3v3-rail.md) and [v1-battery-pack.md](v1-battery-pack.md); if they change, those files win. Every number here is tagged as a datasheet fact, an estimate, or "to measure".

## Summary

- Internal heat is about **16 W typical and 25 W peak** (estimate). Track A's 10 W typical figure predates the AW7916-AED, whose vendor average alone is 8 W.
- A sealed 145 x 74 x 27 mm aluminum body sheds about **0.27 to 0.38 W/K** to still air (estimate). At 16 W the case runs **42 to 59 K over ambient**.
- **Top risk: the Wi-Fi card.** AsiaRF rates the AW7916-AED for -10 to +70 °C operating. At the 8 W vendor average it exceeds 70 °C even at 25 °C ambient, with or without a thermal pad. A pad to the lid is required, and the card needs a transmit power cap.
- Plan for about **10 to 12 W sustained** at 25 °C ambient. A 45 °C ambient soak is not met by a sealed box of this size at any useful load without more surface area. This needs a requirement decision in the records thread.
- RF: the largest GNSS risks are the GW16170 at up to +28.5 dBm (blocking) and the Wi-Fi card 2.5 mm from the GNSS receiver (near-field noise). Two intermod products and two clock harmonics land on GNSS bands and need targeted tests.

## 1. Heat sources

| Source | Typical W | Peak W | Basis |
|---|---:|---:|---|
| CM5 (SoC, LPDDR, eMMC, Gigabit PHY) | 4.5 | 7 (estimate) | CM5 datasheet §3.3: operating about 900 mA at 5 V, idle about 400 mA. Peak is an estimate; to measure. |
| Wi-Fi, AsiaRF AW7916-AED | 8 | 10 | AsiaRF datasheet and product page: 10 W max, 8 W average at 3.3 V. The heatsink bundle listing on the same page says 9 W max, 4 to 8 W average. |
| HaLow, GW16170 | 1 (estimate) | 3.3 | 1.0 A peak at 3.3 V, earlier estimate in v1-3v3-rail.md. Typical to measure. |
| GNSS, MAX-M10S plus antenna bias | 0.03 | 0.33 | 25 mW tracking (u-blox datasheet); peak is the 0.1 A rail allocation. |
| USB hub, TUSB4041I | 0.2 (estimate) | 0.3 (estimate) | To measure. |
| Misc 3.3 V (INA228, supervisor, pull-ups) | 0.3 | 0.8 | 0.25 A misc allocation, v1-3v3-rail.md. |
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
| Bucks, switch, eFuse | Copper pours and thermal vias to a chassis contact (§15) | Bottom side, X 30 to 66, Y 3 to 17. |
| Everything else | Board copper and internal air | Small. |

**Enclosure assumptions (estimates).** Radio body 145 x 74 x 27 mm: footprint from M-01, and 27 mm is the upper-bound body height in v1-reference.md §18. The battery pack covers the bottom face, so only the top and four sides shed heat: about 0.0226 m². Natural convection h_c = 5 to 10 W/m²K. Radiation h_r = 4εσT³ is about 6.9 W/m²K for an anodized or painted finish (ε = 0.85, mean surface about 330 K) and under 1 W/m²K for bare aluminum (ε about 0.1). Combined h is 12 to 17 W/m²K anodized, 6 to 11 bare. **Finish the enclosure anodized or painted; bare aluminum roughly halves the heat it can shed.**

| Case | h (W/m²K) | Area (m²) | R case to ambient (K/W) |
|---|---:|---:|---:|
| Planning (anodized, still air, body only) | 12 | 0.0226 | 3.7 |
| Good (anodized, better convection) | 17 | 0.0226 | 2.6 |
| Pack sides also shed heat (upper bound) | 12 | 0.043 | 1.9 |

The third row adds the 46 mm pack sidewalls. It would help, but it heats the cells; see risks below.

**Internal rises (estimates).** CM5 SoC to lid through a pad: 2 to 3 K/W, so +9 to 14 K at 4.5 W. Wi-Fi card to lid through a pad: 2 to 3 K/W, so +16 to 24 K at 8 W. Wi-Fi card with no pad: 10 K/W or more through the socket and air, so +80 K or more. Internal air sits 5 to 15 K above the case.

**Predicted temperatures, still air, steady state (estimates, °C).** Wi-Fi card assumes a pad at 2.5 K/W.

| Load | Ambient | Case (planning / good) | Wi-Fi card (planning / good) | CM5 SoC (planning / good) |
|---|---:|---:|---:|---:|
| 10 W (Wi-Fi about 2 W) | 25 | 62 / 51 | 67 / 56 | 73 / 62 |
| 16 W typical (Wi-Fi 8 W) | 25 | 84 / 67 | 104 / 87 | 95 / 78 |
| 10 W | 45 | 82 / 71 | 87 / 76 | 93 / 82 |
| 16 W typical | 45 | 104 / 87 | 124 / 107 | 115 / 98 |

The 25 W peak is a transient. The body's heat capacity is roughly 250 J/K (estimate), giving a time constant near 15 minutes, so bursts of a few minutes are averaged out. Sustained 25 W would put the case 65 to 93 K over ambient.

**What this means.**

1. **The Wi-Fi card needs a thermal pad to the lid.** Without one it cannot stay under 70 °C at any useful load. AsiaRF sells the card with a 30 x 30 x 10 mm heatsink; it is a useful bench reference, but 10 mm likely does not fit under the lid, so plan a pad to the lid instead. Whether the 70 °C rating is ambient or card surface is not stated; ask AsiaRF.
2. **The card's sustained power budget is about 2.5 to 4.7 W at 25 °C ambient** (keeping it under 70 °C with the other loads at about 8 W). That is well under the 8 W vendor average.
3. **45 °C ambient does not close.** With the Wi-Fi card on, it exceeds 70 °C at 45 °C ambient in every case above. With Wi-Fi off, the whole body can carry only about 6.8 W before the case reaches 70 °C. The project has no recorded ambient requirement; 45 °C is this plan's test value. Options for the records thread: fins or a larger lid, deliberate heat flow into the pack frame, Wi-Fi off above a set ambient, or a lower ambient rating.
4. **Touch temperature.** A handheld case at 60 to 85 °C is too hot to hold. Check against IEC 62368-1 touch limits once the case temperature is measured.
5. **GNSS sits 2.5 mm from the Wi-Fi card** (§18). The MAX-M10S is rated to +85 °C ambient, and its TCXO drifts with temperature. Measure its local temperature.
6. **Battery cells sit under the radio.** Li-ion charge temperature limits are low. Check the Molicel M35A charge and discharge limits against the measured pack top temperature, and keep a gap or insulation layer if needed.

**Throttling plan (proposed thresholds, to tune after tests 4 and 5).** Software reads the MT7916 temperature (the mt76 driver exposes a hwmon sensor for mt7915-family chips; confirm on this card), the CM5 SoC temperature, and the INA228 power. Steps, in order:

| Step | Trigger (proposed) | Action |
|---|---|---|
| 1 | Wi-Fi card 60 °C, or rail power above budget | Cap Wi-Fi `txpower` in UCI and narrow channel width. Also keeps socket current under 2 A (v1-3v3-rail.md). |
| 2 | Wi-Fi card 65 °C | Cap HaLow TX power. Also helps GNSS. |
| 3 | CM5 SoC 75 °C | Cap the CPU frequency (cpufreq `scaling_max_freq`). The SoC firmware also throttles itself to stay under 85 °C (CM5 datasheet §4.4). |
| 4 | Wi-Fi card 68 °C | Turn off the 5/6 GHz band, then the card (WIFI_PWR_EN). HaLow stays up as the mesh backbone. |
| 5 | Any part at its rating | Orderly shutdown, then PMIC_EN low. |

Each step needs hysteresis and must show in the EUD telemetry.

## 3. RF coexistence with GNSS

The MAX-M10S tracks GPS L1 at 1575.42 MHz and, by default, Galileo E1 and BeiDou B1I (1561.098 MHz), plus QZSS and SBAS (u-blox datasheet). It has an LNA and SAW filter. Absolute maximum RF input is 0 dBm. For the related SAM-M10Q, u-blox states typical out-of-band immunity of 0 dBm across 400 to 1460 MHz and 1710 to 3300 MHz. The external active antenna has its own LNA, which can saturate before the module's filter.

| Mechanism | Frequencies | Risk | Mitigation in the design | What to check |
|---|---|---|---|---|
| HaLow fundamental blocking | 902 to 928 MHz at up to +28.5 dBm | High | GNSS in the far corner, about 116 mm from the HaLow card; external antennas | D-020 estimate: about 21 dB isolation is clean to about 15 dBm, so +28.5 dBm needs about 35 dB (estimate). Measure antenna isolation and C/N0. |
| HaLow harmonics | 2nd 1804 to 1856 MHz, 3rd 2706 to 2784 MHz | Medium | Module filtering; 2nd is about 230 MHz above L1 | Blocking only, not in band. Check with HaLow at max power. |
| Wi-Fi blocking | 2.4, 5, 6 GHz at up to 23 dBm (11b, AsiaRF) | Medium | External antennas; 2.4 GHz is in the 0 dBm immunity range | C/N0 per band at max power. |
| Wi-Fi card near-field noise | Broadband digital and PA noise | High | None yet; card is 2.5 mm edge to edge from GNSS | Near-field probe scan; consider a shield fence or moving GNSS. |
| Intermod: f(2.4 GHz) minus f(HaLow) | 1472 to 1571 MHz (US channels 1 to 11) | Medium | Antenna separation | Lands on BeiDou B1I and near L1. Test HaLow plus 2.4 GHz channels 6 to 11 together. |
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
- Pass: the card's sustained and peak power are known, so §1 can be replaced with numbers. Sustained card current under 2 A, or the txpower cap that achieves it is recorded (v1-3v3-rail.md).

**T1. Power map.**
- Setup: V1 board on a bench supply, open.
- Procedure: read INA228 and supply current in each state: idle; CPU stress; Wi-Fi each band at max; HaLow at max; all at once; charging while operating.
- Pass: totals within 20 % of §1, or §1 updated. Peak input under the eFuse limit.

**T2. Open-board thermal survey.**
- Setup: board open on a stand at 25 °C, all loads at max for 30 minutes.
- Equipment: IR camera, emissivity tape.
- Pass: hot spots identified and thermocouple sites confirmed. Nothing above its rating.

**T3. Closed enclosure, 25 °C ambient.**
- Setup: sealed V1 enclosure with pads fitted, pack attached, still air.
- Thermocouples: Wi-Fi card shield, M.2 socket contacts, GW16170, MAX-M10S, CM5 lid above the SoC, LM76005 (3.3 V) and its inductor, TPS22975, eFuse, internal air, lid centre, each side wall, pack top. Also log the SoC sensor and the MT7916 hwmon.
- Procedure: run idle, 10 W and typical load profiles to steady state (rate of rise under 1 K per 10 minutes).
- Pass: no part above its rating with 10 K margin (AW7916-AED 70 °C, MAX-M10S and GW16170 85 °C, TPS22975 105 °C, LM76005 junction 125 °C estimated from case). No CM5 throttling at the typical profile. Measured R case to ambient compared with §2.

**T4. 45 °C ambient soak.**
- Setup: as T3 inside a thermal chamber at 45 °C, still air.
- Procedure: 2 hours at the capped profile, then 30 minutes at typical. Log all channels. Cold start at 45 °C after a 1 hour unpowered soak.
- Pass: no component above its rating. If the Wi-Fi card cannot stay under 70 °C, record the highest load that does; this feeds the ambient requirement decision.

**T5. Throttle ladder.**
- Procedure: heat the unit (chamber or blocked convection) and confirm each step of the §2 ladder fires in order, cuts power, recovers with hysteresis, and reports to the EUD.
- Pass: every step observed; no oscillation; mesh stays up on HaLow at step 4.

**T6. Wi-Fi thermal interface A/B.**
- Procedure: repeat T3 typical load with no pad, two pad thicknesses, and the AsiaRF heatsink on the open bench as a reference.
- Pass: chosen pad keeps the card at least 10 K cooler than no pad and fits the lid gap with the specified compression.

**T7. GNSS baseline.**
- Setup: open-sky antenna on a splitter to V1 and the reference receiver. All radios off (WIFI_PWR_EN and HALOW_PWR_EN low), Ethernet unplugged, CPU idle.
- Procedure: 30 minutes of C/N0; 10 cold starts and 10 hot starts.
- Pass: C/N0 within 1 dB of the reference receiver. Cold TTFF near the datasheet's 29 s (GPS, open sky) and under 60 s; hot start about 1 s.

**T8. Spectrum scan near GNSS.**
- Equipment: spectrum analyzer or SDR with near-field probe; a DC block and LNA on the GNSS antenna port.
- Procedure: scan 1555 to 1610 MHz over the board and at the antenna port. Turn on one source at a time: each buck, hub, PCIe link up, CPU stress, Ethernet traffic, OpenVLM audio, Wi-Fi idle.
- Pass: no spur within ±2 MHz of 1561.098 or 1575.42 MHz above the noise floor at the antenna port. Any spur found is traced to a source and fixed or explained.

**T9. Radio desense.**
- Procedure: from the T7 baseline, measure C/N0 for each: HaLow stepped to +28.5 dBm; Wi-Fi 2.4, 5 and 6 GHz each at max with saturating `iperf3`; HaLow plus 2.4 GHz channels 6 to 11; 6 GHz plus 2.4 GHz; everything at max with CPU stress and Ethernet traffic.
- Pass: C/N0 drop of 3 dB or less with Wi-Fi and HaLow transmitting at max against all radios off. No loss of 3D fix. If it fails, record the TX power where the drop reaches 3 dB.

**T10. TTFF under load.**
- Procedure: 10 cold starts with all radios at max.
- Pass: median cold TTFF no more than 1.5 times the T7 median and under 60 s.

**T11. Antenna isolation.**
- Equipment: VNA.
- Procedure: measure S21 from the HaLow port and each Wi-Fi port to the GNSS antenna port, with final antennas mounted.
- Pass: HaLow to GNSS at least 35 dB (estimate from D-020; confirm against T9).

**T12. Hot GNSS.**
- Procedure: log C/N0, fix and PPS during T4.
- Pass: fix held, C/N0 within 2 dB of T7, PPS present throughout.

## 5. Unknowns to close

- AW7916-AED: real sustained power, whether 70 °C is ambient or surface, and where the hot side is (T0, AsiaRF).
- GW16170 typical power and CM5 peak power (T0, T1).
- Enclosure size, finish, wall thickness and lid gap ([GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7)).
- The ambient temperature requirement for V1 (records thread).
- Molicel M35A temperature limits against the measured pack top.
- CM5 clock frequencies near GNSS bands (T8).

## Links

- [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12): this work.
- [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23): V1 validation, where tests T1 to T12 run.
- [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10): 3.3 V rail and power path; uses T0 and T1 results.
- [GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) and [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31): Track A power, thermal and GPS coexistence, which feed T0.
