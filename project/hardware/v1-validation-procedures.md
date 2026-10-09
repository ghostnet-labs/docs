# V1 hardware validation procedures

**Owner:** [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23) (validate GNSS, calibrated telemetry, Ethernet, power and thermal recovery)  
**Status:** Procedures written 2026-10-09. No V1 board exists yet; nothing here has been run and no result is claimed.

This file turns the validation matrix in [v1-reference.md §27](v1-reference.md#27-validation-plan) and the bench tests in [v1-hw-telemetry-recovery.md §9](../software/v1-hw-telemetry-recovery.md#9-bench-tests) into numbered procedures, each with setup, equipment, steps and a measurable pass criterion.

It owns the procedures only. It does not own any design value:

- Electrical values are owned by v1-reference.md §12 and §13 and by [v1-3v3-rail.md](v1-3v3-rail.md).
- GPIO numbers and sequencing are owned by [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md).
- Software thresholds and the recovery ladder are owned by v1-hw-telemetry-recovery.md.

A pass criterion that cites one of those records uses the value there at the time of the run. If a cited value changes, the criterion changes with it; do not copy it here.

Thermal and RF tests are owned by [v1-thermal-rf-plan.md §4](v1-thermal-rf-plan.md#4-first-board-test-plan) (T0 to T12). They are listed in [Thermal and RF](#thermal-and-rf), not copied.

## Rules for every run

1. **Tie every result to exact revisions.** Each result row records:
   - board serial, PCB revision and BOM/assembly variant
   - firmware image (repository commit and build ID)
   - openmanetd version
   - the docs commit of this file and the helper scripts used
   - each instrument's model, serial number and calibration due date
   - ambient temperature

   A result without these is not evidence.
2. **Measured, not inferred.** Missing data is "not measured", never a pass. A test skipped because a prerequisite is missing is recorded as **Blocked** with the issue that owns the prerequisite.
3. **Failures become issues.** Every failed or unexplained result gets a Linear issue in the GHO team that names the test ID, the revisions and the raw log. That issue is linked in the result row. A failure is never waived in the results table.
4. **Fault and protection tests need qualified methods.** Tests marked **Q** in the index inject reverse polarity, overvoltage, surge, short circuit or ESD. Run them only with all of the following:
   - **Written plan:** a fault-injection plan reviewed before the run that states the source, energy limit, pulse shape and abort conditions.
   - **Instruments:** calibrated and rated for that energy.
   - **Lab source, never the cell pack:** a current-limited lab source in place of the cell pack. Never short, reverse or overvolt a Li-ion pack.
   - **Protections stay on:** protections are never disabled or bypassed to get a result.

   Without such a plan the test is Blocked, not run informally.
5. **Raw logs are kept.** Attach CSV, JSONL and scope captures to GHO-23 (or the issue a failure opens), named `<board-serial>-<test-id>-<date>`.
6. **Where results go.** The results tables below are the template. Fill one copy per board revision and attach it to GHO-23. Do not record results in this file.

## Common equipment

| Item | Used by | Requirement |
|---|---|---|
| Programmable DC supply with current readout | PW, TM, RC | Covers the full input window in v1-reference §11–§12, current limit settable, remote sense |
| Calibrated DMM (two units) | TM, PW | Basic DC accuracy at least 4 times better than the criterion it checks (0.1 % or better for TM-1) |
| Electronic DC load | TM, PW, US | Constant-current mode, covering 0.2 A to the eFuse current limit, transient (step) mode |
| Four-channel oscilloscope with current probe | PW, RC, GN-3 | 100 MHz or more, at least one isolated or differential channel |
| Time-interval counter or a second disciplined PPS reference | GN-3 | Resolves 100 ns or better |
| GNSS reference receiver, splitter and open-sky active antenna | GN | Same arrangement as thermal T7 |
| Bench host with `iperf3`, a gigabit switch or direct cable, Cat5e patch leads | ET | Host NIC known to sustain 1 Gb/s |
| USB-C breakout with VBUS current shunt | US | Rated for the OpenVLM port current |
| Qualified fault equipment | Tests marked Q | Per rule 4: transient/surge generator, reverse-polarity rig, overvoltage source, ESD simulator |

Helper scripts (this folder; each prints CSV to stdout and is read-only apart from what its header says):

- [`gnss-ttff.sh`](gnss-ttff.sh): cold/warm/hot TTFF through gpsd, then a PPS pulse count with `ppstest`. One command, for example `sh gnss-ttff.sh -m cold -n 10 -p 3600 > gn1.csv`.
- [`ina228-log.sh`](ina228-log.sh): INA228 hwmon CSV in the [`bench-log.sh`](../poc/bench-log.sh) pattern, with a per-setpoint label and averaged mode. For example `sh ina228-log.sh -n 20 -i 0.5 -a -l 9.0V_1.0A >> tm1.csv`.
- [`eth-sweep.sh`](eth-sweep.sh): advertises 10, 100 and 1000 Mb/s in turn, records the negotiated link and runs `iperf3` both ways. For example `sh eth-sweep.sh -s 192.168.1.10 -t 60 > et2.csv`.

## Test index

| ID | Area | Test | Q | Prerequisite |
|---|---|---|---|---|
| GN-1 | GNSS | Cold start TTFF and constellations | | Antenna selected (GHO-11) |
| GN-2 | GNSS | Warm and hot start TTFF | | GN-1 |
| GN-3 | GNSS | UART and PPS | | `pps-gpio` on GNSS_PPS |
| GN-4 | GNSS | Active antenna bias | short case only | Antenna and bias protection (GHO-11) |
| GN-5 | GNSS | Backup retention | | V_BCKP storage selected (GHO-11) |
| GN-6 | GNSS | Signal loss, reset and recovery | | GN-1 |
| TM-1 | Telemetry | INA228 voltage and current vs calibrated meters | | — |
| TM-2 | Telemetry | INA228 power and energy | | TM-1 |
| TM-3 | Telemetry | INA228 die temperature | | — |
| TM-4 | Telemetry | ALERT, thresholds and shutdown | | hwmgr (GHO-20) |
| ET-1 | Ethernet | Negotiation at 10/100/1000 | | Magnetics selected |
| ET-2 | Ethernet | Throughput per speed | | ET-1 |
| ET-3 | Ethernet | Sustained traffic and errors | | ET-2 |
| ET-4 | Ethernet | PHY timing interface | | D-033 test point |
| ET-5 | Ethernet | ESD, shield and chassis | Q | ESD device selected (GHO-11) |
| US-1 | USB | Enumeration of HaLow and OpenVLM | | — |
| US-2 | USB | OpenVLM VBUS overcurrent and short | short case | VBUS switch selected (GHO-11) |
| US-3 | USB | HaLow port fault | | HALOW_USB_FAULT_N source (GHO-9) |
| US-4 | USB | Concurrent HaLow and OpenVLM use | | US-1 |
| PW-1 | Power | Minimum input and UVLO | | — |
| PW-2 | Power | Maximum input | | Input window set (GHO-10) |
| PW-3 | Power | Cold and hot start, sequencing | | — |
| PW-4 | Power | Internal load transients | | — |
| PW-5 | Power | Input transients and surge | Q | Transient environment defined (GHO-10) |
| PW-6 | Power | Current limit and output short | Q | — |
| PW-7 | Power | Reverse battery | Q | Reverse-FET topology verified (GHO-10) |
| PW-8 | Power | Overvoltage | Q | — |
| RC-1 to RC-13 | Recovery | Line, ladder, watchdog and PMIC tests | RC-8 | hwmgr (GHO-20), supervisor topology (GHO-10) |

## GNSS

Common setup: open-sky active antenna on a splitter to the V1 node and the reference receiver, as in thermal T7. Radios off (WIFI_PWR_EN and HALOW_PWR_EN low), Ethernet unplugged, CPU idle, unless the test says otherwise. gpsd owns `/dev/ttyAMA0`; `pps-gpio` provides `/dev/pps0` ([pinout record](v1-pinout-and-sequencing.md)).

**GN-1. Cold start TTFF and constellations.**
- Equipment: as above; u-center on the reference receiver.
- Steps:
  1. Run `sh gnss-ttff.sh -m cold -n 10 -t 300 > gn1.csv`.
  2. After the last fix, save `gpspipe -w -n 20` and note satellites used per constellation (GPS, Galileo, BeiDou, GLONASS as configured).
- Pass: the cold-start criterion of thermal T7 (median near the datasheet value and every run under 60 s). At least two constellations contribute satellites to the fix. No FAIL rows.

**GN-2. Warm and hot start TTFF.**
- Steps: `sh gnss-ttff.sh -m warm -n 10 > gn2w.csv`, then `-m hot`.
- Pass:
  - Hot: the hot-start criterion of thermal T7.
  - Warm (proposed; no recorded requirement): median warm TTFF no longer than the GN-1 cold median, and every run under 60 s.

**GN-3. UART and PPS.**
- Equipment: scope or counter on the GNSS_PPS test point against the reference receiver's PPS.
- Steps:
  1. With a 3D fix, run `sh gnss-ttff.sh -m none -n 1 -p 3600 > gn3.csv`.
  2. At the same time, log `gpspipe -r` for 10 minutes and count sentences with bad checksums.
  3. Capture the PPS-to-reference offset on the counter for 10 minutes.
- Pass:
  - PPS: pulses = elapsed seconds (±1 for the start and stop edges), `seq_gaps` 0, kernel-timestamp `max_dev_us` recorded.
  - UART: no checksum errors, and gpsd reports the configured baud rate.
  - Counter offset: recorded against the reference.
- If I2C is routed, also read the receiver over I2C once (`i2cdetect` shows the module) and record the result.

**GN-4. Active antenna bias.**
- Steps:
  1. Measure VCC_RF at the antenna connector with the antenna connected, and its current through an inline meter.
  2. Then, only if the carrier has bias current limiting, short the bias through the current-limited fixture defined in the fault plan.
- Pass:
  - Bias voltage and current are inside the selected antenna's rated supply range.
  - With a short, the bias current stays inside the protection's rating, the receiver and the +3V3_GNSS rail survive, and GN-1 passes after the short is removed.
- Without bias limiting on the board, the short case is **Blocked** under GHO-11.

**GN-5. Backup retention.**
- Applies only once V_BCKP storage is selected. Until then the test is **Blocked** under GHO-11.
- Steps:
  1. Get a 3D fix, then remove main power for the retention time the selected storage is designed for.
  2. Restore power and run `sh gnss-ttff.sh -m none -n 1`.
- Pass: the fix after restore meets the GN-2 hot-start criterion. A cold-start time means backup failed.

**GN-6. Signal loss, reset and recovery.**
- Steps:
  1. With a 3D fix and `gpspipe -w` logging, disconnect the antenna for 60 s, then reconnect it. Repeat 5 times.
  2. Then pulse GNSS_RESET_N (the `ExecuteGnssReset` RPC when hwmgr exists, otherwise a manual pulse at the test point) and time the recovery.
- Pass:
  - gpsd reports the loss (mode below 3) within 5 s of disconnection.
  - The fix returns within the GN-2 hot-start criterion after reconnection.
  - PPS stops while there is no fix, unless timing holdover is configured.
  - After the reset, a fix returns within the GN-1 cold-start criterion.
  - No gpsd or kernel restart is needed in any cycle.

## Battery telemetry (INA228)

Common setup: V1 on the programmable supply in place of the pack, with the electronic load on the protected bus so the current is known. One calibrated DMM is in series to read current and one at the INA228 bus-voltage sense point. INA228 configuration is as in v1-reference §12.

**TM-1. Voltage and current against calibrated meters** (telemetry §9 T10).
- Steps: for each bus voltage of 9.0, 10.5, 11.1 and 12.6 V and each load of 0.2, 1, 2, 3, 4 and 5 A (not above the eFuse limit), let the reading settle for 10 s. Then run `sh ina228-log.sh -n 20 -i 0.5 -a -H -l <V>_<A> >> tm1.csv` and record both DMM readings in the same row.
- Pass: at every point, bus voltage is within 0.5 % and current within 1 % of the meters (T10).

**TM-2. Power and energy.**
- Steps:
  1. At 11.1 V and 2 A, log `sh ina228-log.sh -i 1 > tm2.csv` for 30 minutes.
  2. Integrate the meter readings, or use a calibrated power analyzer's energy count, over the same window.
- Pass:
  - `power_mw` within 1.5 % of V×I from the meters.
  - The `energy_uj` increase over 30 minutes within 1.5 % of the reference energy. This is proposed: the sum of the TM-1 voltage and current limits.
  - The `charge_mah` integration in hwmgr is checked the same way once it exists (telemetry §6).

**TM-3. Die temperature.**
- Steps: thermocouple on the INA228 package. Log at idle and at 5 A for 30 minutes each.
- Pass: `temp_c` within the INA228 datasheet temperature-sensor accuracy of the thermocouple, after the thermocouple's own tolerance.

**TM-4. ALERT, thresholds and shutdown** (telemetry §9 T11).
- Steps:
  1. Ramp the supply down in 0.1 V steps of 60 s each from 12.6 V, through each level in the telemetry §6 threshold table, to the ALERT backstop.
  2. Scope INA228_ALERT_N.
- Pass:
  - Each action fires at its tabled level after the tabled hold time.
  - ALERT asserts at the backstop level.
  - The shutdown is clean and logged.
  - Clearing obeys the tabled hysteresis.

## Ethernet

Common setup: bench host running `iperf3 -s`, connected through the sealed feed-through and pigtail (B-06, D-025) with a 2 m Cat5e lead. Run from the serial console, because each speed change drops the link.

**ET-1. Negotiation at 10, 100 and 1000 Mb/s.**
- Steps: `sh eth-sweep.sh -s <host> -t 10 > et1.csv`, repeated 5 times. Also connect to a 100 Mb/s-only switch port and record the result.
- Pass:
  - Every row shows the advertised speed at full duplex, `link_s` 5 s or less, and no NOLINK or WRONGSPEED rows.
  - The 100 Mb/s-only port links at 100 full.

**ET-2. Throughput per speed.**
- Steps: `sh eth-sweep.sh -s <host> -t 60 > et2.csv`.
- Pass (proposed, about 94 % of line rate after TCP/IP overhead; no project requirement exists): TCP both ways at least 940 Mb/s at 1000, 94 at 100 and 9.4 at 10, and `err_delta` 0.

**ET-3. Sustained traffic.**
- Steps:
  1. At 1000 Mb/s, run `iperf3 -c <host> -t 7200 --bidir` with `ina228-log.sh` and thermal logging in parallel.
  2. Save `ethtool -S eth0` before and after.
- Pass: no link drop, error counters unchanged, and throughput over the last 10 minutes within 5 % of the first 10 minutes.

**ET-4. PHY timing interface.**
- Steps:
  1. Run `ethtool -T eth0` and record the hardware timestamping capabilities.
  2. Probe TP_ETH_SYNC (D-033) with the PHY sync output enabled by the selected driver method and record the waveform.
- Pass: hardware timestamping is reported and the waveform is captured. This is a measurement, not a requirement; D-033 selects no consumer.

**ET-5. ESD, shield and chassis** (Q).
- Steps: IEC 61000-4-2-style contact and air discharge on the connector shell and cap. Use levels set in the fault plan once the ESD device and chassis strategy exist.
- Pass: no damage, link recovers without reboot, and GN-1 and ET-2 still pass afterwards.
- Until the ESD device is selected (GHO-11) this test is **Blocked**.

## USB

**US-1. Enumeration.**
- Steps: cold boot 10 times; record `lsusb -t` and `dmesg` each time.
- Pass: the hub, GW16170 and OpenVLM device enumerate every boot at their expected speed, with no USB errors in `dmesg`.

**US-2. OpenVLM VBUS overcurrent and short.**
- Steps:
  1. Put the USB-C breakout with the electronic load on the OpenVLM port. Step the load from 0 to above the selected VBUS switch's current limit.
  2. Then, as a Q step, apply a hard short through the breakout per the fault plan.
- Pass:
  - The switch limits current inside its datasheet range.
  - VLM_USB_FAULT_N asserts and is reported (telemetry §5).
  - +5V_SYS stays inside the CM5 input range on the scope.
  - The HaLow device stays enumerated.
  - The port recovers after the fault is removed with a hub-port power cycle only.

**US-3. HaLow port fault.**
- Steps: force HALOW_USB_FAULT_N from its selected source, as in RC-5.
- Pass: per RC-5.

**US-4. Concurrent use.**
- Steps: for 30 minutes, run saturating HaLow traffic (mesh test M4 pattern) while the OpenVLM plays and records audio in loopback with PTT keyed every 30 s.
- Pass: no USB disconnects or resets in `dmesg`, no audio underruns or overruns reported by the comms snapshot, and HaLow throughput within 10 % of a HaLow-only run (proposed).

## Power input and protection

Common setup: lab supply in place of the pack. Scope channels on input, +5V_SYS, +3V3_RADIO and the eFuse PGOOD. Electronic load or full radio load as stated.

**PW-1. Minimum input and UVLO.**
- Steps:
  1. At full radio load, ramp the input down at 0.1 V/s until the eFuse turns off.
  2. Ramp back up.
  3. Repeat at idle.
- Pass:
  - The eFuse falling and rising thresholds are inside the tolerance band calculated in v1-reference §12.
  - All rails stay in regulation down to the falling threshold.
  - Restart is clean.

**PW-2. Maximum input.**
- Steps: run at the top of the pack range and at the top of the approved input window (set by GHO-10 with the charger power path) for 30 minutes at full load each.
- Pass: rails in regulation, the eFuse never enters its clamp, and no component exceeds its rating (thermal T2 survey points).
- If GHO-10 has not set the window, test only the pack maximum and record the rest as **Blocked**.

**PW-3. Cold and hot start, sequencing.**
- Steps:
  1. Power on 20 times at the minimum and 20 times at the maximum input, at room temperature.
  2. Scope the rail order and PMIC_Enable.
- Pass:
  - The order and timing match the working sequence in the pinout record.
  - The eFuse output ramp matches §12.
  - All 40 boots reach the OS.
- Temperature endpoints are thermal T4.

**PW-4. Internal load transients.**
- Steps: scope WIFI_3V3 at the M.2 socket pins and +5V_SYS during Wi-Fi transmit bursts, with HaLow transmitting at the same time, and during a CPU stress start.
- Pass: the minimum at the M.2 pins stays at or above the M.2 limit in [v1-3v3-rail.md](v1-3v3-rail.md), and +5V_SYS stays inside the CM5 datasheet input range.

**PW-5. Input transients and surge** (Q).
- Steps: apply the positive and negative pulses defined in the fault plan at the pack contacts, with the TVS and reverse FET populated as in §12.
- Pass: no damage, the TVS clamp stays below the eFuse and Q1 ratings, the node keeps running or recovers by auto-retry, and the event is logged.
- **Blocked** until GHO-10 defines the transient environment.

**PW-6. Current limit and output short** (Q).
- Steps:
  1. Step the electronic load on the protected bus past the eFuse limit.
  2. Then short the protected bus through the fault rig.
- Pass:
  - The steady limit and the pulse behaviour match §12.
  - EFUSE_FAULT asserts.
  - Auto-retry runs at the §12 interval.
  - The node recovers after the short is removed.

**PW-7. Reverse battery** (Q).
- Steps: apply reverse polarity at the pack contacts from the current-limited source per the fault plan.
- Pass: no reverse current beyond leakage, no damage, and the node starts normally when correct polarity is restored.
- **Blocked** until GHO-10 verifies the reverse-FET topology.

**PW-8. Overvoltage** (Q).
- Steps: raise the input above the approved window into the eFuse clamp region, per the fault plan.
- Pass: the eFuse clamps and turns off as described in §12, downstream rails stay in rating, and the node restarts when the input returns to the window.

## Watchdog, PMIC and recovery

These expand [v1-hw-telemetry-recovery.md §9](../software/v1-hw-telemetry-recovery.md#9-bench-tests) T1 to T13 one-to-one (RC-n is Tn). If a §9 row changes, change the matching RC test in the same PR.

Prerequisites: hwmgr exists (GHO-20), line names are in the device tree, and for RC-7 to RC-9 the supervisor arming and latch-clear circuit exists (GHO-10).

Common equipment: scope, lab supply, and `logread -f` captured to a file.

**RC-1. Line names and polarity.**
- Steps: run `gpioinfo` and save it. Toggle each output with `gpioset` and scope its pin.
- Pass: every name is present, and each output asserts at the level in the telemetry §2 signal inventory.

**RC-2. Open-drain lines never go high.**
- Steps: scope GPIO18, 19 and 21 with the radio rails off through boot, daemon start, daemon stop and RC-3 to RC-5.
- Pass: the pin never rises above the radio rail, and no voltage appears on HALOW_3V3 or WIFI_3V3 while they are off.

**RC-3. Step 1, USB device reset.**
- Steps: unbind the HaLow driver under traffic, then call `ExecuteRadioRecovery`.
- Pass: the netdev is back within 30 s and the event is logged with the telemetry §5 fields.

**RC-4. Step 2, hub reset.**
- Steps: hold the HaLow device unresponsive so step 1 fails.
- Pass:
  - USB_HUB_RESET_N pulses low.
  - HaLow and OpenVLM re-enumerate.
  - comms receives its notice before the reset.
  - No hub reset happens while PTT is active.

**RC-5. Step 3, radio power cycle.**
- Steps:
  1. Kill the Wi-Fi card: PCI remove, then block rescan.
  2. Separately, force WIFI_FAULT_N and HALOW_USB_FAULT_N low.
- Pass:
  - The power cycle follows the telemetry §4 timings.
  - The scope shows the rail off for 2 s or more.
  - A PCIe rescan restores the Wi-Fi.

**RC-6. Backoff and `failed`.**
- Steps: remove the HaLow card.
- Pass:
  - Retry count and backoff are exactly as in telemetry §5, then the state is `failed`.
  - Wi-Fi traffic is unaffected throughout.

**RC-7. Step 4, supervisor and watchdog.**
- Steps:
  1. Run `echo c > /proc/sysrq-trigger`.
  2. Separately, `kill -STOP` hwmgr.
  3. Scope SUPERVISOR_WDI and SUPERVISOR_WDO.
- Pass:
  - With the watchdog armed, WDO asserts within the interval in v1-reference §13, measured from the last WDI edge.
  - With hwmgr stopped, the userspace timeout in telemetry §7 elapses before WDI stops.
  - Validate the complete reset path separately.

**RC-8. Step 5, PMIC_Enable** (Q for the rail excursions).
- Steps:
  1. With the lab supply, drag each SVS rail out of its window.
  2. Separately, stop WDI.
- Pass:
  - A bounded PMIC_Enable pulse occurs.
  - The supervisor latch clears.
  - The node reboots and the boot counter is retained.
  - There is no permanent PMIC-low latch.

**RC-9. Boot gap.**
- Steps: cold boot 20 times with the watchdog populated.
- Pass:
  - Zero watchdog resets during boot.
  - Arming happens only after WDI service starts.
  - No stale latched WDO.

**RC-10. Battery accuracy.** Same as TM-1.

**RC-11. Thresholds and shutdown.** Same as TM-4.

**RC-12. Loop protection.**
- Steps: force step 5 three times within one hour.
- Pass: the fourth boot comes up telemetry-only.

**RC-13. Timing kept.**
- Steps: run RC-3 to RC-5 with PPS on the counter (GN-3 setup).
- Pass: no PPS gap except during a GNSS reset.

## Thermal and RF

Run [v1-thermal-rf-plan.md §4](v1-thermal-rf-plan.md#4-first-board-test-plan) as written; it owns their setup, equipment and pass criteria. The V1 ones (T1 to T12) are part of this validation:

- Power: T1 power map.
- Thermal: T2 to T4 open-board and enclosed thermal, including the D-028 endpoints and no-throttling; T6 pad A/B.
- Protection: T5 emergency protection (Q, rule 4 applies).
- RF and GNSS: T7 to T12 GNSS baseline, spectrum, desense, TTFF under load, antenna isolation and hot GNSS.

Record their results in the same template with the T ID.

Pack-swap ride-through (D-027) is outside this file. It is sized under [GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38) and measured with the GHO-61 workload tooling in the firmware repository.

## Results template

Copy per board revision; one row per test run. Attach the filled copy to GHO-23.

Run header (once per copy):

| Field | Value |
|---|---|
| Board serial / PCB rev / BOM variant | |
| Firmware commit and build ID | |
| openmanetd version | |
| Docs commit (procedures and scripts) | |
| Operator | |

| Test | Date | Ambient °C | Instruments (model, serial, cal due) | Measured | Criterion source | Result (Pass / Fail / Blocked) | Raw log | Issue |
|---|---|---|---|---|---|---|---|---|
| GN-1 | | | | | | | | |
| GN-2 | | | | | | | | |
| GN-3 | | | | | | | | |
| GN-4 | | | | | | | | |
| GN-5 | | | | | | | | |
| GN-6 | | | | | | | | |
| TM-1 | | | | | | | | |
| TM-2 | | | | | | | | |
| TM-3 | | | | | | | | |
| TM-4 | | | | | | | | |
| ET-1 | | | | | | | | |
| ET-2 | | | | | | | | |
| ET-3 | | | | | | | | |
| ET-4 | | | | | | | | |
| ET-5 | | | | | | | | |
| US-1 | | | | | | | | |
| US-2 | | | | | | | | |
| US-3 | | | | | | | | |
| US-4 | | | | | | | | |
| PW-1 | | | | | | | | |
| PW-2 | | | | | | | | |
| PW-3 | | | | | | | | |
| PW-4 | | | | | | | | |
| PW-5 | | | | | | | | |
| PW-6 | | | | | | | | |
| PW-7 | | | | | | | | |
| PW-8 | | | | | | | | |
| RC-1 … RC-13 | | | | | | | | |
| Thermal T1 … T12 | | | | | | | | |

"Criterion source" names the record and section the pass criterion came from, at the docs commit in the header. Every Fail or Blocked row links an issue.
