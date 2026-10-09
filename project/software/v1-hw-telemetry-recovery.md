# V1 hardware telemetry, radio power and fault recovery

**Owner:** [GHO-20](https://linear.app/ghostnet-labs/issue/GHO-20) (define hardware telemetry, radio power and fault-recovery software)  
**Status:** Proposal, 2026-10-02. Nothing here is implemented. No GPIO may be driven by software until its physical pin, boot default and polarity are Verified in the pinout record.

This file defines how software on the V1 carrier reads hardware telemetry, switches the radios, and recovers from faults. It consumes three records and does not own any of their facts:

- [../hardware/v1-pinout-and-sequencing.md](../hardware/v1-pinout-and-sequencing.md) owns every GPIO allocation, the sequencing order and the recovery order (D-024). The GPIO numbers below are copied from it for readability; if they disagree, the pinout record wins and this file is fixed in the same PR.
- [../hardware/v1-reference.md](../hardware/v1-reference.md) sections 12, 13, 16, 21, 22 and 23 own the INA228, eFuse, TPS22975 and TPS386000 details and the recovery hierarchy.
- [../hardware/v1-3v3-rail.md](../hardware/v1-3v3-rail.md) owns the +3V3_RADIO sizing and the WIFI_3V3 rise time.

Where it lands in code: the OpenMANET daemon `openmanetd`, and the V1 firmware target `bcm2712_ghostnet-v1` in [ghostnet-labs/firmware](https://github.com/ghostnet-labs/firmware).

## 1. What exists today

Read from the code on 2026-10-02. Everything after this section is new.

| Item | Where | What it does now |
|---|---|---|
| Board name `ghostnet,v1` | firmware `target/linux/bcm27xx/image/Makefile` (`SYSINFO_BOARD_NAME`) | Lands in `/etc/board.json` as `model.id` |
| `board.GhostnetV1` constant | openmanetd `internal/util/board/board_type.go` | Gates GNSS and BLOS support. Its comment still names the AIW-170BQ; the Wi-Fi card is the AW7916-AED (D-026) |
| Boot GPIO states | firmware `boards/bcm2712/distroconfig-ghostnet-v1.txt` | GPIO4/5 output high, GPIO18/19/21 input no pull, GPIO23 output high, `pps-gpio` on GPIO9, I2C1 on |
| INA228 driver | firmware backport `811-v6.17-hwmon-ina238-add-INA228-support.patch`, package `kmod-hwmon-ina238` | hwmon device named `ina228` with `in0`, `in1`, `curr1`, `power1`, `temp1` and `energy1_input`. No charge attribute |
| Battery reader | openmanetd `internal/system/battery.go` (`HwmonBatteryProvider`) | Finds the first hwmon `name` starting `ina2`, reads `in1_input`, `curr1_input`, `power1_input`, estimates charge from voltage |
| Battery in the API | openmanetd `DashboardService` (`BatteryStatus`) | Voltage, current, power, charge percent, cell count |
| GPIO library | openmanetd `internal/comms/gpio` uses `github.com/warthog618/go-gpiocdev` | Character-device GPIO, no sysfs GPIO |
| Snapshot framework | openmanetd `internal/instrumentation`, doc `docs/instrumentation-snapshot.md` (schema 1.6.0) | Registry of named `Snapshotter` sections |

No GPIO power, fault, watchdog or recovery code exists in openmanetd today.

## 2. Signal inventory

"hwmgr" is the proposed openmanetd hardware manager (section 8). Manufacturer polarity and output type are recorded in the canonical [electrical evidence](../hardware/v1-pinout-and-sequencing.md#electrical-sources-and-boot-evidence). Carrier connectivity remains Unverified (GHO-9). Unselected or unconnected fault sources must be reported as unavailable, never healthy or faulted from a floating GPIO.

| GPIO | Line name | Linux interface | Dir | Active | Owner | Notes |
|---:|---|---|---|---|---|---|
| 2/3 | SYS_I2C_SDA/SCL | `/dev/i2c-1`, kernel `ina238` driver | n/a | n/a | kernel | INA228 only; userspace reads hwmon, never raw I2C |
| 4 | HALOW_PWR_EN | libgpiod line by name | out | high | hwmgr | TPS22975 U303 ON pin |
| 5 | WIFI_PWR_EN | libgpiod line by name | out | high | hwmgr | TPS22975 U302 ON pin |
| 6 | HALOW_FAULT_N | libgpiod, both-edge events | in | low | hwmgr | Source not recorded: the TPS22975 has no fault pin |
| 7 | WIFI_FAULT_N | libgpiod, both-edge events | in | low | hwmgr | Same question as GPIO6 |
| 8 | GNSS_RESET_N | libgpiod | out (open-drain use) | low | hwmgr | Drive low to reset, input to release. gpsd keeps the UART |
| 9 | GNSS_PPS | `pps-gpio` overlay, `/dev/pps0` | in | rising | kernel, read by gpsd/chrony | hwmgr never requests it |
| 10 | SUPERVISOR_WDI | kernel `gpio-wdt` (`linux,wdt-gpio`) | out | toggle | kernel, armed by hwmgr | See section 7 |
| 11 | SUPERVISOR_ARM | libgpiod | out | high | hwmgr | TPS386000 MR arm (D-044). Driven high only after WDI service runs; dropped before a deliberate poweroff |
| 12 | POWER_GOOD | libgpiod, both-edge events | in | high | hwmgr | Source/translation Unverified; the reference PGOOD pull-up is battery-domain, not an intrinsic output-high voltage |
| 13 | EFUSE_FAULT | libgpiod, both-edge events | in | low (TPS26633 FLT is open-drain low) | hwmgr | Chip active-low behavior verified; name retained; pull-up/connectivity open |
| 14/15 | GNSS_UART_TX/RX | `/dev/ttyAMA0` | n/a | n/a | gpsd | Unchanged |
| 17 | Reserved | not requested | n/a | n/a | none | Unassigned; dedicated PHY sync test point is separate (D-033, canonical pinout record) |
| 18 | HALOW_RESET_N | libgpiod, open-drain flag | out | low | hwmgr | Never driven high |
| 19 | HALOW_WAKE_N | libgpiod, open-drain flag | out | low | hwmgr | Never driven high; optional |
| 20 | INA228_ALERT_N | libgpiod, falling-edge events | in | low | hwmgr | Hardware backstop for battery limits (section 6) |
| 21 | WIFI_WDIS1_N | libgpiod, open-drain flag | out | low | hwmgr | Never driven high. Low = RF off (hardware RF disable) |
| 23 | USB_HUB_RESET_N | libgpiod | out | low | hwmgr | Resets HaLow and OpenVLM together |
| 24 | HALOW_USB_FAULT_N | libgpiod, both-edge events | in | low | hwmgr | HaLow hub-port overcurrent |
| 25 | VLM_USB_FAULT_N | libgpiod, both-edge events | in | low | hwmgr | OpenVLM port overcurrent; reported to the comms subsystem |

**Open-drain rule.** GPIO18, GPIO19 and GPIO21 are requested with the open-drain drive flag and only ever set to "asserted" (low) or "released" (high-Z). Code must not offer a path that drives them high, because the pull-ups return to the switched radio rail and a high GPIO back-feeds a card whose rail is off. GPIO8 follows the same pattern as a precaution.

**Line ownership on restart.** The kernel does not promise that an output keeps its value after the requesting process releases it. Boot defaults in `distroconfig-ghostnet-v1.txt` set the radios on, and hwmgr must request each output with its current value as the initial value so a daemon restart does not glitch a radio.

## 3. Proposed device-tree line names

Add `gpio-line-names` to the RP1 GPIO controller (`&rp1_gpio`) in the V1 overlay, so software finds lines with `gpiocdev.FindLine("HALOW_PWR_EN")` and never hard-codes a number. The property replaces the base list, so entries 28 to 53 must be copied from the CM5 base device tree.

```dts
&rp1_gpio {
    gpio-line-names =
        "", "", "SYS_I2C_SDA", "SYS_I2C_SCL",                        /* 0-3 */
        "HALOW_PWR_EN", "WIFI_PWR_EN", "HALOW_FAULT_N", "WIFI_FAULT_N",  /* 4-7 */
        "GNSS_RESET_N", "GNSS_PPS", "SUPERVISOR_WDI", "SUPERVISOR_ARM",  /* 8-11 */
        "POWER_GOOD", "EFUSE_FAULT", "GNSS_UART_TX", "GNSS_UART_RX",     /* 12-15 */
        "", "", "HALOW_RESET_N", "HALOW_WAKE_N",                          /* 16-19 */
        "INA228_ALERT_N", "WIFI_WDIS1_N", "", "USB_HUB_RESET_N",         /* 20-23 */
        "HALOW_USB_FAULT_N", "VLM_USB_FAULT_N", "", "",                  /* 24-27 */
        /* 28-53: copy from the CM5 base device tree */;
};
```

Same overlay, proposed: an `ina228` node on I2C1 (`compatible = "ti,ina228"`, `shunt-resistor = <10000>` micro-ohms, `ti,shunt-gain = <4>` for the 163.84 mV range named in reference section 12; I2C address Unverified), and a `linux,wdt-gpio` node on GPIO10 (section 7). Line names must match the pinout record's signal column exactly.

## 4. Radio power state machine

One state machine per radio (HaLow, Wi-Fi). GNSS has no power switch on V1 and only gets the reset line.

| State | Meaning | Exit |
|---|---|---|
| `off` | Rail off by request (user, low battery, or RF disable policy) | Power-on request → `powering` |
| `powering` | Enable high, controls held, waiting for the rail | Timer done → `enumerating` |
| `enumerating` | Waiting for the bus device and its network interface | Device and netdev present → `up`; timeout → `fault` |
| `up` | Interface present and health checks pass | Health failure or fault line → `fault`; off request → `off` |
| `fault` | Recovery ladder running (section 5) | Step succeeds → `enumerating`; step needs power off → `cooldown`; ladder exhausted → `failed` |
| `cooldown` | Rail off, waiting before the next power-on | Backoff timer done → `powering` |
| `failed` | Ladder exhausted; radio left off | Manual `ExecuteRadioRecovery` or reboot |

Proposed timings (all to bench-confirm in GHO-21):

| Step | HaLow (GW16170, USB) | Wi-Fi (AW7916-AED, PCIe) |
|---|---|---|
| Before enable | Assert HALOW_RESET_N low, WAKE_N released | WIFI_WDIS1_N released; PCIe device removed from sysfs if present |
| Rail rise and settle | 20 ms after enable (switch rise about 1 ms) | 100 ms after enable (PCIe power-stable to PERST# release minimum) |
| Release | Release HALOW_RESET_N (high-Z) | `echo 1 > /sys/bus/pci/rescan`; kernel drives PERST# |
| Enumeration timeout | 10 s for the USB device, 30 s for the netdev after driver firmware load | 5 s for the PCI function, 20 s for the netdev |
| Power off | Unbind driver, assert reset, enable low | Remove PCI device, enable low |
| Minimum off time | 2 s (rail discharge) | 2 s |
| Cooldown backoff | 10 s, 30 s, 2 min, 10 min, then 10 min cap | Same |

The pinout record also lists a HaLow USB VBUS enable between reset release and enumeration. No GPIO is allocated for it, so whether it is a hub port-power control or a separate switch is open (GHO-9).

## 5. Fault-recovery ladder

The order is the pinout record's recovery step 7 and reference section 22. Each radio climbs its own ladder; a lower step is always tried before a higher one unless a hardware fault line skips it.

| Step | Action | Applies to | Trigger | Retries and backoff |
|---|---|---|---|---|
| 1. Reset USB device | `USBDEVFS_RESET` on the HaLow device, then driver unbind and bind if it does not return | HaLow | Netdev missing, driver timeout, no TX completions or station dump failing for 60 s while the rail is on | 2 tries, 15 s apart |
| 1w. Reset PCIe function | Let mt76 firmware self-recovery run first; then `/sys/bus/pci/devices/<bdf>/reset`, then remove and rescan | Wi-Fi | Same health signals on the Wi-Fi netdev | 2 tries, 15 s apart |
| 2. Reset hub | USB_HUB_RESET_N low 10 ms, then high; wait for re-enumeration | HaLow (also drops OpenVLM) | Step 1 failed, or the hub itself disappears | 1 try per 10 min. Skipped while a PTT transmit is active; comms is told first |
| 3. Power-cycle radio | `fault` → `cooldown` → `powering` (section 4) | Both | Step 2 failed (Wi-Fi: step 1w), or HALOW_FAULT_N, WIFI_FAULT_N or HALOW_USB_FAULT_N asserted | 3 tries, backoff from section 4, then `failed` |
| 4. Supervisor and watchdog | Host-level: CM5 internal watchdog, then TPS386000 (section 7) | Whole node | Kernel or userspace hang. Never used for a single radio | Hardware-timed |
| 5. PMIC_Enable | TPS386000 path pulls CM5 PMIC_Enable (pin 99) low | Whole node | Supervisor rail fault or watchdog expiry | Hardware-timed; boot counter below |

Rules:

- One radio failing never escalates to steps 4 or 5. The node stays on the mesh with the other radio.
- Step 4/5 is requested by software only when both mesh radios are `failed` for 30 min, the battery is above the warning level, and fewer than 3 such requests happened in the last 24 h. Software requests it by stopping the WDI heartbeat (section 7); it cannot drive PMIC_Enable directly.
- A boot counter in `/etc/openmanetd/hwrecovery.json` records each recovery-caused reset. Three resets within 1 h puts hwmgr into telemetry-only mode for that boot (no power-cycling) so a bad radio cannot cause a reboot loop.
- EFUSE_FAULT or POWER_GOOD low is a power fault, not a radio fault: log it, mark both radios `fault` with reason `power`, and do not power-cycle until POWER_GOOD is back for 5 s.
- VLM_USB_FAULT_N is reported to comms and the API; recovery for the OpenVLM port is a hub-port power cycle only, never a hub reset on its own.

Every step logs one structured line (`radio`, `step`, `attempt`, `trigger`, `result`, `duration_ms`) at Warn, and Error when a radio reaches `failed`. The same fields go into a bounded ring of the last 64 recovery events, exposed by the API and the snapshot. `ramoops` (already in the boot config) keeps the kernel log across a step 4 or 5 reset.

## 6. Battery telemetry

Values come from hwmon (`/sys/class/hwmon/hwmonN`, `name` = `ina228`), with units as the driver reports them:

| Value | hwmon file | Unit | API field (proposed) | Sample |
|---|---|---|---|---|
| Bus voltage | `in1_input` | mV | `bus_voltage_mv` | 1 Hz |
| Shunt voltage | `in0_input` | mV | not exposed (debug only) | n/a |
| Current | `curr1_input` | mA | `current_ma` | 1 Hz |
| Power | `power1_input` | µW | `power_mw` | 1 Hz |
| Energy since INA228 power-up | `energy1_input` | µJ | `energy_mwh` | 10 s |
| Charge | none in the driver | mAh | `charge_mah`, integrated in hwmgr from current | 1 Hz integration |
| Die temperature | `temp1_input` | m°C | `monitor_temp_c` | 10 s |
| Alarms | `in1_min_alarm`, `in0_max_alarm`, `power1_max_alarm`, `temp1_max_alarm` | flag | `alarms` bitmask | on ALERT edge and 10 s |

Each reading carries `sampled_at`. A reading older than 5 s is reported as stale (`stale = true`, values kept), and after 30 s the battery block reports `present = false` with reason `monitor_unreachable`. The existing `HwmonBatteryProvider` already matches `ina228` by its `ina2` prefix and should be reused, extended with the files above.

**Measurement point.** The shunt sits after the eFuse (reference section 12) and, with charging in the radio (section 11), after the charger output. It therefore measures system load, not battery current. While charging, `current_ma` is the node's draw and coulomb counting from it is wrong. Charge state while charging needs the BQ25798 battery-current reading, which has no software interface allocated yet.

**Low-battery thresholds (proposal, 3S2P Molicel M35A, D-013).** Compare a load-compensated voltage, `V_comp = V_bus + I x R_pack`, with `R_pack` = 0.06 Ohm as a starting value to measure on the bench, and require the condition for 30 s continuously.

| Level | Per cell | Pack (V_comp) | Action |
|---|---:|---:|---|
| Full | 4.20 V | 12.6 V | none |
| Warning | 3.50 V | 10.5 V | API event and EUD notice |
| Critical | 3.30 V | 9.9 V | Wi-Fi radio off (largest load), HaLow and GNSS stay up, EUD notice |
| Shutdown | 3.20 V | 9.6 V | Graceful shutdown |
| INA228 ALERT backstop | 3.10 V | 9.3 V (`in1_min`, no compensation) | Immediate graceful shutdown on GPIO20 edge |
| Pack protection cutoff | 2.8 to 3.0 V | 8.4 to 9.0 V | Hardware, owned by GHO-8 |
| eFuse UVLO falling | n/a | 7.43 V | Hardware, reference section 12 |

Clearing a level needs V_comp 0.2 V above its threshold for 60 s (hysteresis).

**Graceful shutdown.** Publish a `shutdown_pending` event to API streams and log it; wait up to 10 s for EUD clients; bring both radios to `off` through the state machine; sync and call `poweroff`. With no power button, how the node starts again after a low-battery halt while a charger keeps the bus up is open (the CM5 stays halted while power is present); this needs a hardware answer before the shutdown level is enabled in the field.

## 7. Watchdog

Proposed layered watchdogs; reset precedence depends on which service stops making progress.

| Layer | Device | Who pets it | Timeout | Effect |
|---|---|---|---|---|
| CM5 internal | `bcm2835-wdt` | OpenWrt `procd`, its default `/dev/watchdog` handling | 30 s, pinged every 5 s | SoC reset |
| Kernel gpio-wdt on SUPERVISOR_WDI | `linux,wdt-gpio`, `hw_algo = "toggle"`, `hw_margin_ms` = 400, `always-running` | Kernel heartbeat target 200 ms; hwmgr pets the userspace side (unvalidated) | Userspace timeout 60 s | Kernel stops toggling WDI |
| TPS386000 | Hardware | WDI edges from the gpio-wdt driver | See reference §13 for verified hardware interval | Latched WDO low; PMIC path and latch-clear circuit unimplemented |

The proposed heartbeat target must meet the worst-case interval in reference §13 under load. `hw_margin_ms` declares the supported hardware heartbeat to the kernel; it does not reconfigure the supervisor. The proposed value keeps that declaration below the chip's minimum timeout, with measured scheduling margin still required.

hwmgr would pet the software watchdog every 10 s while its loops are healthy. A wedged hwmgr does not necessarily stop procd from petting the CM5 watchdog, so comparing the 30 s and 60 s settings alone does not guarantee a softer reset first. Select watchdogs by identity and verify procd's device choice. Linux [v6.6 gpio_wdt.c](https://github.com/torvalds/linux/blob/v6.6/drivers/watchdog/gpio_wdt.c) starts `always-running` at probe and retains hardware-running state on stop; magic-close support does not disable this external timer. Boot, restart and shutdown behavior require tests of the actual target kernel.

Boot gap: no WDI service is guaranteed before gpio-wdt probe, so the watchdog is armed by software after boot (D-044). hwmgr starts WDI service first, then drives SUPERVISOR_ARM high. It must drop SUPERVISOR_ARM before a deliberate poweroff, or the watchdog power-cycles a node meant to stay off. The bootloader and `config.txt` must never drive GPIO11 high, or the node boot-loops. Validate shutdown and daemon restart as well as startup; the proposed userspace/kernel watchdog behavior is not implemented or qualified.

TPS386000 WDO is not a CM5 input (D-044), so a watchdog trip is not logged directly. Reset-cause attribution needs validated retained evidence; missing logs must be reported as unknown.

## 8. Where it lives in openmanetd (proposal)

Nothing below exists. Layout follows the repo's CLAUDE.md conventions.

| Path | Contents |
|---|---|
| `internal/hardware/board.go` | Detect V1: `board.NewBoardConfigInfo()` returns `model.id == board.GhostnetV1`, and every required line name resolves with `gpiocdev.FindLine`. If either fails, hwmgr runs telemetry-only and drives nothing |
| `internal/hardware/lines.go` | Line requests by name, open-drain flag for GPIO8/18/19/21, edge watchers with kernel debounce |
| `internal/hardware/radio.go` | Per-radio state machine (section 4), one goroutine per radio, context-cancelled |
| `internal/hardware/recovery.go` | Ladder, retry counters, boot counter, bounded event ring |
| `internal/hardware/battery.go` | Thresholds, charge integration, shutdown; wraps `system.HwmonBatteryProvider` |
| `internal/hardware/watchdog.go` | gpio-wdt open by identity, pet loop |
| `internal/hardware/snapshot.go` | `Snapshotter` for section `hardware` |
| `internal/openmanet/server/handlers/hardware.go` | `HardwareService` handler |
| `proto/openmanet/hardware/v1/hardware_service.proto`, `hardware.proto` | API |

Supported-feature helper: add `HardwareControlSupported()` next to `GNSSsupoorted()` in `internal/util/board/supported_features.go`, true only for `GhostnetV1`.

**`openmanet.hardware.v1.HardwareService`**

| RPC | Purpose |
|---|---|
| `GetHardwareStatus` | Radios (state, reason, last transition, attempt counts), fault lines, POWER_GOOD, battery block, watchdog state, board detected or telemetry-only |
| `StreamHardwareStatus` | Server stream of the same message on change, at most 1 Hz |
| `SetRadioPower` | `radio` enum, `enabled` bool; goes through the state machine, never sets a GPIO directly |
| `SetRadioRfDisable` | Wi-Fi hardware RF disable through WIFI_WDIS1_N (low = disabled) |
| `ExecuteRadioRecovery` | Run the ladder from step 1 now, or clear `failed` |
| `ListRecoveryEvents` | The bounded event ring |
| `ExecuteGnssReset` | Pulse GNSS_RESET_N low for 100 ms |

Enums use the `RADIO_HALOW` / `RADIO_WIFI` style with an `_UNSPECIFIED` zero value. All control RPCs require an authenticated admin session; read RPCs follow the dashboard's privilege. The dashboard keeps its `BatteryStatus` and reads it from hwmgr. Every control action is logged with the caller.

**Snapshot section `hardware`** (additive, minor schema bump, rows added to `docs/instrumentation-snapshot.md` in the same change):

| Key | Unit | Meaning |
|---|---|---|
| `board_detected` | bool | V1 detected and all lines resolved |
| `radios[*].name`, `.state`, `.state_since_ns` | string, ns | Current state and when it was entered |
| `radios[*].recoveries_total`, `.power_cycles_total`, `.failed_total` | count | Ladder activity since daemon start |
| `fault_edges_total` | count per line | Edges seen on each fault input |
| `battery_bus_mv`, `battery_current_ma`, `battery_stale` | mV, mA, bool | Last battery reading |
| `watchdog_pets_total`, `wdo_edges_total` | count | Heartbeat and supervisor output activity |
| `recovery_boots_last_hour` | count | Boot counter used for loop protection |

**Timing paths left alone.** hwmgr never requests the GNSS PPS line or the reserved GPIO17 and never touches the GNSS UART. The dedicated PHY sync signal terminates at an internal test point under D-033; it is not a GPIO consumer. The canonical [pinout record](../hardware/v1-pinout-and-sequencing.md#ethernet-timing-interface) owns the mapping. PPS and Ethernet timing stay independent of recovery. A GNSS reset is the only action that touches the GNSS, and it is manual.

## 9. Bench tests

Run under [GHO-21](https://linear.app/ghostnet-labs/issue/GHO-21) (first power and boot) and [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23) (telemetry and recovery validation). Record the board and firmware revision with each result. Each row is expanded into a full procedure (RC-n is Tn) in [../hardware/v1-validation-procedures.md](../hardware/v1-validation-procedures.md#watchdog-pmic-and-recovery).

| # | Proves | Method | Pass |
|---|---|---|---|
| T1 | Line names and polarity | `gpioinfo` on the V1 image; toggle each output with a scope on the pin | Every name present; each output asserts at the documented level |
| T2 | Open-drain lines never go high | Scope GPIO18/19/21 with radio rails off through boot, daemon start, stop and recovery | Pin never above the rail; no back-feed on HALOW_3V3 or WIFI_3V3 |
| T3 | Step 1 | Wedge the HaLow driver (unbind under traffic), then `ExecuteRadioRecovery` | Netdev back within 30 s; event logged |
| T4 | Step 2 | Hold the HaLow device unresponsive so step 1 fails | Hub reset, HaLow and OpenVLM re-enumerate; comms told first |
| T5 | Step 3 | Kill the Wi-Fi card (hold PERST# via PCI remove and block rescan), and separately force WIFI_FAULT_N and HALOW_USB_FAULT_N low | Power cycle with the section 4 timings; scope shows rail off for 2 s or more; PCIe rescan brings the Wi-Fi back |
| T6 | Backoff and `failed` | Remove the HaLow card | Exactly the retry count and backoff in section 5, then `failed`, Wi-Fi unaffected |
| T7 | Step 4 | `echo c > /proc/sysrq-trigger` (kernel hang), and `kill -STOP` hwmgr | When armed, measure WDO assertion from the last WDI edge against reference §13; validate the complete reset path separately. Verify the proposed userspace timeout with hwmgr stopped |
| T8 | Step 5 | Drag SVS rails out of window with a lab supply; let WDI stop | Verify PMIC_Enable pulse, supervisor latch clearing, reboot and retained boot counter; no permanent PMIC-low latch |
| T9 | Boot gap | Cold boot 20 times with the watchdog populated | No watchdog reset during boot; arm only after WDI service, with no stale latched WDO |
| T10 | Battery accuracy | INA228 against a calibrated DMM and electronic load across 9 to 12.6 V and 0.2 to 5 A | Voltage within 0.5 %, current within 1 % |
| T11 | Thresholds and shutdown | Lab supply ramped down through each level | Each action at its level, ALERT backstop at 9.3 V, clean shutdown logged |
| T12 | Loop protection | Force step 5 three times in an hour | Fourth boot comes up telemetry-only |
| T13 | Timing kept | Run T3 to T5 with PPS on a counter | No PPS gap except during a GNSS reset |

## 10. Dependencies

Items this proposal relies on that other issues must settle are listed with the issue that owns them: supervisor boot inhibition/arming/latch-clear topology ([GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)); GPIO physical pins, boot defaults and fault-line sources ([GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9)); HaLow VBUS control and hub port power wiring ([GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11)); pack cutoff and charger telemetry ([GHO-8](https://linear.app/ghostnet-labs/issue/GHO-8), [GHO-38](https://linear.app/ghostnet-labs/issue/GHO-38)); thermal telemetry and limits ([GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12)). New questions raised here are filed as Linear issues, not kept in this file.
