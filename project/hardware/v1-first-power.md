# V1 carrier first power and boot

**Owner:** [GHO-21](https://linear.app/ghostnet-labs/issue/GHO-21): assemble the prototype and verify safe first power and CM5 boot  
**Status:** Procedure, not yet run. No V1 board has been powered. Results, photos, scope captures and logs go on GHO-21, never in this file.

This file owns the first-power procedure: the order of steps, the bench current limits, which nets to probe, what to capture and when to stop. It does not own the circuit values it checks against. Those stay with their owners, and this file links to them:

| Fact | Owner |
|---|---|
| Rails, power tree, setpoints, eFuse UVLO and PGOOD, supervisor rails | [v1-reference.md](v1-reference.md) §12 and §13; [v1-selections.md](v1-selections.md#power-tree) |
| +3V3_RADIO setpoint, WIFI_3V3 rise time, the M.2 card's voltage window | [v1-3v3-rail.md](v1-3v3-rail.md) |
| CM5 connector pins, GPIO signals, polarity, boot states, working sequence | [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md) (canonical) |
| Pack voltage range | [v1-selections.md](v1-selections.md) (battery) and [v1-reference.md](v1-reference.md) §11 |
| Post-boot device and GPIO check | [`../poc/bench-check-v1.sh`](../poc/bench-check-v1.sh) |

Nets below use the names in those records. Test-pad designators are not assigned yet; take them from the schematic released under GHO-9/GHO-13 and note them in the GHO-21 record.

## 0. Equipment and setup

- A bench supply with an adjustable current limit and a readout good to 1 mA. It must hold the limit without overshoot when the output is enabled.
- A DMM, a four-channel scope with probes rated for the bus voltage, an IR thermometer or thermal camera, and a USB-to-UART adapter at 3.3 V for the internal debug UART (v1-reference §4).
- An ESD mat and wrist strap. Connect antennas or 50 Ω loads to every RF port before any radio is powered. Never transmit into an open port.
- Inject power at the battery interface contacts, with no pack and no USB-C charger connected. If the released schematic places the in-radio charger between the pack and the eFuse (v1-reference §11, under review in [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10)), follow the schematic's power path. Record where the supply was connected.
- Nominal test voltage: the pack's nominal voltage (v1-reference §11). The low and high ends of the pack's in-use range are used in step 5.

## 1. Assembly inspection

With nothing fitted (no CM5, no M.2 cards, no pack):

1. Inspect every power-path part under magnification: TVS, blocking FET and Q2, eFuse, shunt, both LM76005 bucks and inductors, both TPS22975 switches, supervisor, INA228, hub. Look for solder bridges, tombstones, missing parts and lifted pins.
2. Check orientation of every polarized or pin-1 part against the assembly drawing: the eFuse, FETs, regulators, load switches, supervisor, hub, polarized capacitors, and the CM5 and M.2 connectors.
3. Check that the M.2 sockets and the CM5 connectors seat flat, with no bent contacts and no flux or debris in the contact rows.
4. Record the result and photos of both sides on GHO-21.

Stop if a polarized part is reversed or a bridge sits on a power net. Fix and re-inspect before going on.

## 2. Resistance to ground, unpowered

Board unpowered for at least 1 minute, nothing fitted. Measure each net to GND with the DMM on resistance. Let the reading settle (capacitors charge from the meter). Then swap the leads and measure again; a large difference between the two is a diode or IC body path, which is expected.

No expected values are recorded yet. Board 1 sets the baseline, and later boards are compared with it.

| Net | Where to probe | Board 1 (Ω, + / −) | Fail |
|---|---|---|---|
| Battery input (before the TVS and blocking FET) | Battery interface positive contact | record | Under 10 Ω |
| VBAT_PROTECTED (eFuse output, after the shunt) | Shunt output side or its test pad | record | Under 10 Ω |
| +5V_SYS | 5 V buck output capacitor | record | Under 10 Ω |
| CM5_3V3 (carrier side; CM5 not fitted) | CM5 connector pins 84/86 | record | Under 10 Ω |
| GPIO_VREF | CM5 connector pin 78 | record | Under 10 Ω, or not equal to CM5_3V3 if the schematic ties them |
| +3V3_RADIO | 3.3 V buck output capacitor | record | Under 10 Ω |
| WIFI_3V3 | Wi-Fi M.2 socket 3.3 V pin (pin 2) | record | Under 10 Ω |
| HALOW_3V3 | HaLow M.2 socket 3.3 V pin (pin 2) | record | Under 10 Ω |
| +3V3_GNSS | GNSS supply filter output | record | Under 10 Ω |
| OpenVLM port VBUS | OpenVLM USB-C receptacle VBUS | record | Under 10 Ω |

Also measure between adjacent rails: battery input to VBAT_PROTECTED, VBAT_PROTECTED to +5V_SYS, +5V_SYS to +3V3_RADIO, +3V3_RADIO to WIFI_3V3 and to HALOW_3V3. Fail on any reading under 1 kΩ.

10 to 100 Ω on WIFI_3V3 or HALOW_3V3 can be the TPS22975 quick-output-discharge path while the switch is off. Explain any reading in that range from the schematic before continuing. For a later board, investigate any net that differs from board 1 by more than a factor of two.

## 3. Current-limited first power

Each stage adds load to a stage that passed. Set the voltage with the output off, then set the limit, then enable. Watch the supply current for the first 5 s. Stop at once and turn the output off if the supply enters constant-current mode, a part smells or discolours, a part goes above the temperature stop below, or a rail exceeds its owner's range. Temperature stop, for carrier parts (not the CM5 or the M.2 cards, which have their own throttling): 50 °C in stages 3a to 3c, where nothing on the carrier carries much current; 85 °C in stage 3d, below the load switch and buck ratings (v1-reference §13, [v1-3v3-rail.md](v1-3v3-rail.md#losses-and-heat)).

These limits are this procedure's starting values. Raise one only with the reason written on GHO-21.

| Stage | Fitted | Limit | Record |
|---|---|---|---|
| 3a | Carrier only | 150 mA | Input current at nominal; every rail in the table below |
| 3b | + CM5, no M.2 cards, Ethernet connected | 1.0 A | Input current at idle and at peak during boot; rails; boot log (section 5) |
| 3c | + GW16170 and AW7916-AED, antennas or loads fitted, no traffic | 2.0 A | Input current with both radios up and idle; rails |
| 3d | + OpenVLM device on its port; radios carrying traffic | 4.5 A | Peak and steady input current; rails under load; hottest part temperature after 10 min |

Why these limits: 150 mA covers the bucks' switching and quiescent current plus the eFuse and regulator soft-start inrush into the output capacitors (v1-reference §12 and §13), with no CM5 load. 1.0 A at nominal voltage is about 11 W, enough for a CM5 boot without radios. 2.0 A leaves room for both cards idle on top of the CM5. 4.5 A sits above the pack's peak draw and below the eFuse current limit (v1-reference §12), so the supply limits before the eFuse trips.

### Rail checks at each stage

Measure with the DMM at the probe points in section 2.

| Net | 3a | 3b to 3d | Pass |
|---|---|---|---|
| VBAT_PROTECTED | present | present | Within 0.2 V of the supply voltage, less the drop across the blocking FET, eFuse and shunt |
| +5V_SYS | present | present | Within the output range in v1-reference §13 (5 V buck, output setting) |
| CM5_3V3 | absent (CM5 not fitted) | present | Present and within the CM5 datasheet range |
| +3V3_RADIO | present | present | Within the output range in [v1-3v3-rail.md](v1-3v3-rail.md#setpoint-and-voltage-drop) |
| WIFI_3V3, HALOW_3V3 | record (enable bias only, no CM5) | present after boot | 3b to 3d: at the card's socket pins, inside the M.2 window in v1-3v3-rail.md, also under load in 3d |
| +3V3_GNSS | present | present | Present |

At stage 3a the radio switch enables have only their carrier bias, since nothing drives them. Record whether each switch is on or off. The pinout record says the bias must hold the intended state before firmware runs; a switch that is on with no CM5 fitted is a finding for [GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9), not a stop.

## 4. Rail sequence

Capture each set on the scope at stage 3b (carrier sets) and 3c (radio sets), triggered on the first rising edge in the set, with a 50 ms/div first pass and a zoom on each edge. Save the captures with the board ID and image commit in the filename and attach them to GHO-21.

The order to check against is the working sequence in the [pinout record](v1-pinout-and-sequencing.md#working-sequence-and-recovery). Connector pins and GPIO lines are in the same record.

| Capture | Channels | Pass |
|---|---|---|
| 1. Input | Battery input, VBAT_PROTECTED, eFuse PGOOD, +5V_SYS | VBAT_PROTECTED ramps only above the eFuse UVLO rising threshold; +5V_SYS and +3V3_RADIO start only after PGOOD (v1-reference §12) |
| 2. CM5 and supervisor | +5V_SYS, CM5_3V3, +3V3_RADIO, PMIC_Enable | CM5_3V3 follows +5V_SYS; PMIC_Enable is not pulled low during a normal start |
| 3. HaLow | HALOW_PWR_EN, HALOW_3V3, HALOW_RESET_N, HALOW_WAKE_N | HALOW_3V3 comes up after the supervisor is good; HALOW_RESET_N and HALOW_WAKE_N never rise above HALOW_3V3 (no back-feed); reset releases after the rail settles |
| 4. Wi-Fi | WIFI_PWR_EN, WIFI_3V3, WIFI_WDIS1_N, PCIe PERST# | WIFI_3V3 rise time as set in v1-3v3-rail.md; WIFI_WDIS1_N never above WIFI_3V3; PERST# stays asserted until WIFI_3V3 is stable and releases after it |
| 5. Hub | Hub 3.3 V supply, hub 24 MHz clock, USB_HUB_RESET_N, +5V_SYS | Hub reset releases only after its 3.3 V and clock are stable |

Repeat captures 1 and 2 with the supply turned off, to record the power-down order. A control line that stays high after its rail is gone is a back-feed finding.

## 5. Boot and corners

1. Before stage 3b, flash the `bcm2712_ghostnet-v1` image to the CM5 eMMC. The image comes from [firmware PR #23](https://github.com/ghostnet-labs/firmware/pull/23), or from `24.10` once it merges. Use `rpiboot` and the procedure in the [POC runbook](../poc/bring-up-runbook.md), step 1.
2. Connect the USB-to-UART adapter to the internal debug UART test points. Start capturing before enabling the supply: `picocom -b 115200 /dev/ttyUSB0 | tee v1-<board>-boot-<n>.log`. The kernel console belongs on the debug UART, never on the GNSS UART.
3. Enable the supply. The log must run from the bootloader banner to the OpenWrt login prompt.
4. Over Ethernet, SSH to the node and save:

   ```sh
   cat /etc/openwrt_release; uname -a; cat /tmp/sysinfo/board_name /tmp/sysinfo/model
   cat /proc/cmdline
   vcgencmd version; vcgencmd bootloader_version; vcgencmd get_throttled
   dmesg > /tmp/dmesg-boot.txt; logread > /tmp/logread-boot.txt
   ```

5. Copy [`bench-check-v1.sh`](../poc/bench-check-v1.sh) to the node and run `sh bench-check-v1.sh > /tmp/check-v1.txt 2>&1`. It is read-only. It checks the board name, the AW7916-AED on PCIe with mesh point, the dwc2 USB port, the hub, the GW16170, the INA228, GNSS and PPS, the OpenVLM, the absence of Bluetooth (D-026), and every GPIO state. Its FAIL table is in the [runbook's V1 section](../poc/bring-up-runbook.md).
6. Power-cycle 5 times at stage 3c (supply off for at least 10 s). Every boot must reach the login prompt and pass the same bench-check lines.
7. Corners at stage 3c: repeat one boot and the bench check at the low and at the high end of the pack's in-use range. Then ramp the supply slowly down from nominal and record the voltage where the eFuse turns off and the supply current drops. Compare it with the UVLO falling threshold in v1-reference §12.

## 6. Revision record

Paste this on GHO-21 once per board, filled in, before the results:

```text
Board ID / serial:
PCB revision and fab date:
Assembly house, BOM revision, assembly date:
Rework done before test (what, where, why):
CM5 part number (RAM / eMMC / wireless variant):
AW7916-AED serial and revision:
GW16170 serial and revision:
OpenVLM device (serial, EEPROM image):
Firmware image: repo@commit, Actions run URL, artifact name, sha256:
packages commit:
openmanetd version:
CM5 bootloader EEPROM version (vcgencmd bootloader_version):
Supply injection point:
Bench supply model; DMM model; scope model and probes:
Ambient temperature:
Operator and date (YYYY-MM-DD):
```

## 7. Pass and fail

A board passes first power when all of these hold, each with its evidence on GHO-21:

1. Assembly inspection found no reversed parts or bridges on power nets, or each one was fixed and re-inspected.
2. No net in section 2 reads under 10 Ω to GND, and no pair of adjacent rails reads under 1 kΩ.
3. No stage in section 3 entered constant-current mode at its limit, every rail met its pass condition, and no part reached its stage's temperature stop.
4. All five scope captures in section 4 show the working-sequence order, with no control line above its switched rail.
5. Every boot in section 5 reached the login prompt, with a complete serial log, and Ethernet was reachable.
6. `bench-check-v1.sh` reported no FAIL lines on any boot. Each WARN line is explained on GHO-21.
7. The board kept booting and passing at both corners, and the eFuse turn-off voltage was recorded.

Any FAIL stops that board until its cause is found and recorded. A FAIL that comes from a design question rather than an assembly fault goes to its owning issue (GHO-9 pins and sequencing, GHO-10 power path and supervisor, GHO-11 USB VBUS and ESD), linked from GHO-21. Radio and mesh validation beyond enumeration is [GHO-22](https://linear.app/ghostnet-labs/issue/GHO-22); telemetry and recovery validation is [GHO-23](https://linear.app/ghostnet-labs/issue/GHO-23).
