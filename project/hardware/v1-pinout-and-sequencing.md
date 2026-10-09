# V1 pinout and radio sequencing evidence

**Owner:** GHO-9 — Verify carrier pinouts, GPIO muxes and radio sequencing  
**Status:** In progress. This is the canonical CM5 physical-pin, GPIO-allocation, and sequencing record; proposed mappings are not a layout release. Other project records link here instead of maintaining a second GPIO map.

## Authorities

- [Raspberry Pi CM5 datasheet](https://pip.raspberrypi.com/documents/RP-008180-DS-cm5-datasheet.pdf)
- [Raspberry Pi CM5 IO datasheet](https://pip.raspberrypi.com/documents/RP-008182-DS-cm5io-datasheet.pdf)
- [AsiaRF AW7916-AED datasheet](https://asiarf.com/wp-content/uploads/2026/07/260709_Datasheet_AW7916-AED_V1-1P.pdf)
- [Gateworks GW16167/GW16170 M.2 pinout](https://trac.gateworks.com/wiki/expansion/gw16167)
- [TI TPS22975, SLVSDD0B](https://www.ti.com/lit/ds/symlink/tps22975.pdf), §6 and §10.1.1
- [TI TPS2663, SLVSE94G](https://www.ti.com/lit/ds/symlink/tps2663.pdf), §5, §8.3.2 and §8.3.10
- [TI TPS386000, SBVS105F](https://www.ti.com/lit/ds/symlink/tps386000.pdf), §5 and §8.3.3

## CM5 physical carrier pins

These are CM5 connector pin numbers, not BCM GPIO numbers.

| Function | CM5 pin(s) |
|---|---:|
| PCIe CLK_nREQ / nRST | 102 / 109 |
| PCIe REFCLK P/N | 110 / 112 |
| PCIe RX P/N | 116 / 118 |
| PCIe TX P/N | 122 / 124 |
| USB2 D-/D+ (B-07 service port, device role; rpiboot) | 103 / 105 |
| USB3-0 USB 2.0 pair DP/DM (TUSB4041I upstream) | 134 / 136 |
| GPIO_VREF | 78 |
| CM5 3.3 V | 84 / 86 |
| PMIC_Enable / nRPIBOOT | 99 / 93 |
| Ethernet_SYNC_OUT (dedicated PHY timing pin) | 18 |
| SCL0 GPIO39 / SDA0 GPIO38 | 80 / 82 |

USB_OTG_ID (101) is left unconnected (internal pull-up, device role) with a DNP 0 Ω to GND (D-044).

GPIO signal ownership and physical CM5 connector pin numbers are maintained together in the allocation table below (D-024).

CM5 is Gen2 x1. The CM5 TX path already has AC coupling; Raspberry Pi's own M.2 socket (CM5 IO datasheet Figure 6) has no carrier capacitors on the card TX path, because add-in cards couple their own transmitters. V1 lays out 0 Ω links in capacitor footprints (D-046). PCIE_PWR_EN (pin 106) goes to a test pad only. CM5 nWAKE is not supported in software.

## CM5 GPIO mux facts

The official alternate-function table verifies GPIO0/1 = I2C0 SDA/SCL, GPIO2/3 = I2C1 SDA/SCL, GPIO8/9 = UART3 TX/RX, and GPIO14/15 = UART0 TX/RX. The old V1 cross-reference that labels GPIO0/1 as GNSS UART is stale.

Allocation decision D-024: GNSS uses UART0 on GPIO14/15; system I2C1 uses GPIO2/3; USB_HUB_RESET_N uses GPIO23; HALOW_USB_FAULT_N uses GPIO24; VLM_USB_FAULT_N uses GPIO25; GPIO26–27 remain reserved. All GPIO0–27 physical connector mappings below were checked on 2026-10-02 against CM5 datasheet Release 3 (build 08/06/2026), §4.2 Table 4, printed page 18. GPIO0/1 appear there as ID_SD/ID_SC. Verification covers connector identity only, not software defaults or the attached circuit. These are logical allocations, not a schematic/layout release; verify boot defaults, device-tree behavior, electrical polarity, and schematic connectivity before release.

| GPIO | CM5 connector pin | Signal | Function / verification status |
|---:|---:|---|---|
| 0 | 36 | Reserved | I2C0 alternate function; unassigned |
| 1 | 35 | Reserved | I2C0 alternate function; unassigned |
| 2 | 58 | SYS_I2C_SDA | System I2C1; physical pin verified |
| 3 | 56 | SYS_I2C_SCL | System I2C1; physical pin verified |
| 4 | 54 | HALOW_PWR_EN | TPS22975 ON, active-high output; chip polarity verified; carrier bias/boot timing open |
| 5 | 34 | WIFI_PWR_EN | TPS22975 ON, active-high output; chip polarity verified; carrier bias/boot timing open |
| 6 | 30 | HALOW_FAULT_N | Planned input from TPS3780D OUT2: low when HALOW_3V3 is below about 2.92 V. 10 kΩ pull-up to CM5_3V3. Low while HALOW_PWR_EN is low is the normal off state, not a fault. Candidate (D-046); bench verification open |
| 7 | 37 | WIFI_FAULT_N | Planned input from TPS3780D OUT1: low when WIFI_3V3 is below about 2.92 V. 10 kΩ pull-up to CM5_3V3. Low while WIFI_PWR_EN is low is the normal off state, not a fault. Candidate (D-046); bench verification open |
| 8 | 39 | GNSS_RESET_N | GNSS reset; physical pin verified; boot/electrical verification open |
| 9 | 40 | GNSS_PPS | GNSS timing; physical pin verified; boot/electrical verification open |
| 10 | 44 | SUPERVISOR_WDI | TPS386000 WDI input, either-edge heartbeat; carrier boot/arming open |
| 11 | 38 | SUPERVISOR_ARM | TPS386000 MR watchdog arm, active-high output; 10 kΩ pull-down keeps it disarmed while the CM5 is off or in reset (D-044); carrier bias Unverified |
| 12 | 31 | POWER_GOOD | Planned input; eFuse PGOOD active-high open-drain; battery-domain pull-up needs translation |
| 13 | 28 | EFUSE_FAULT | TPS26633 FLT active-low open-drain input; CM5-domain pull-up/connectivity open |
| 14 | 55 | GNSS_UART_TX | GNSS UART0 TX; physical pin verified |
| 15 | 51 | GNSS_UART_RX | GNSS UART0 RX; physical pin verified |
| 16 | 29 | Reserved | Freed: was BT_USB_FAULT_N, and V1 has no Bluetooth (D-026). Unassigned spare. Preferred pin for a future simple digital input such as BRIDGE_ACTIVE_N or PACK_PRESENT (GHO-13). No carrier connection until allocated (D-046) |
| 17 | 50 | Reserved | Unassigned spare (D-033); no connection to the dedicated PHY timing pin |
| 18 | 49 | HALOW_RESET_N | HaLow reset; active-low open-drain, physical pin verified; boot/electrical verification open |
| 19 | 26 | HALOW_WAKE_N | HaLow wake; active-low open-drain, optional; physical pin verified; boot/electrical verification open |
| 20 | 27 | INA228_ALERT_N | Battery monitor alert; physical pin verified; boot/electrical verification open |
| 21 | 25 | WIFI_WDIS1_N | Wi-Fi RF disable to AW7916-AED pin 56. Open-drain use: drive low to assert, input/high-Z to release, 10 kOhm pull-up to WIFI_3V3 on the carrier. Physical pin verified; boot/electrical verification open |
| 22 | 46 | Reserved | Freed: was WIFI_WDIS2_N, and AW7916-AED pin 54 (W_DISABLE2#) is not connected on the card. Unassigned spare. Preferred pin for a future simple digital input such as BRIDGE_ACTIVE_N or PACK_PRESENT (GHO-13). No carrier connection until allocated (D-046). Cannot form an I2C bus: its I2C3_SCL partner, GPIO23, is USB_HUB_RESET_N |
| 23 | 47 | USB_HUB_RESET_N | USB hub reset; physical pin verified |
| 24 | 45 | HALOW_USB_FAULT_N | HaLow USB fault; physical pin verified |
| 25 | 41 | VLM_USB_FAULT_N | OpenVLM port-3 VBUS switch / downstream overcurrent fault; physical pin verified |
| 26 | 24 | Reserved | Unassigned; physical pin verified |
| 27 | 48 | Reserved | Unassigned; physical pin verified |

## Ethernet timing interface

Verified 2026-10-04 against Raspberry Pi CM5 datasheet Release 3, §2.2.2 (printed page 7) and §4.2 Table 4 (printed pages 17–18): Ethernet_SYNC_OUT is the dedicated PHY timing signal on connector pin 18, with 3.3 V signalling and optional input configuration. GPIO17 is a separate RP1 GPIO on connector pin 50; it is not an alternate name or mux for the PHY signal.

D-033 routes connector pin 18 as net ETH_SYNC_OUT to internal test point TP_ETH_SYNC only. Do not connect it to GPIO17 or GNSS_PPS. GPIO17 remains unassigned, with no GPIO consumer, output drive, or timing overlay. GNSS_PPS retains its allocation in the GPIO table above. This preserves a probe point without selecting a PHY-to-GPIO capture circuit. Any future GPIO capture or PHY sync-input circuit needs a separately reviewed allocation, direction, boot-state and driver design. PHY timing-driver support, pulse configuration and waveform measurements are not verified by the connector mapping. GHO-9/GHO-13 retain schematic and bench implementation gates.

## AW7916-AED M.2 signals

Source: AsiaRF's [AW7916-AED pin-out drawing](https://asiarf.com/wp-content/uploads/2023/09/AW7916-AED_pins-out.jpg) from the [product page](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/). The drawing labels each gold finger but prints no pin numbers; the numbers below come from finger order and the A and E key positions (odd pins on the top side, even on the bottom). Check them against the card itself when the bench cards arrive.

| M.2 pin | Card signal | Carrier connection |
|---:|---|---|
| 2, 4, 72, 74 | 3.3 V | WIFI_3V3 (see [v1-3v3-rail.md](v1-3v3-rail.md) for the 0.5 A per contact risk) |
| 1, 7, 18, 33, 39, 45, 51, 57, 63, 69, 75 and others marked GND | GND | GND. Pin 69 is labelled 'GNDX' in the drawing; it is wired to GND (D-046) |
| 3, 5 | not connected (no USB) | leave open; hub port 2 is spare |
| 35 / 37 | PCIe lane 0 receive pair (labelled PERp0 / PERn0 from the card's side) | CM5 PCIe TX P/N, pins 122 / 124 (CM5 already AC-couples this direction) |
| 41 / 43 | PCIe lane 0 transmit pair (labelled PETp0 / PETn0) | CM5 PCIe RX P/N, pins 116 / 118, through 0 Ω links in capacitor footprints (220 nF fitted only if the bench shows the card has no TX AC coupling; D-046) |
| 47 / 49 | REFCLKp0 / REFCLKn0 | CM5 REFCLK P/N, pins 110 / 112 |
| 52 | PERST0# | CM5 PCIe nRST, pin 109 |
| 53 | CLKREQ0# | CM5 PCIe CLK_nREQ, pin 102 |
| 55 | PEWAKE0# | not used by the CM5 (nWAKE unsupported): 10 kOhm pull-up to WIFI_3V3 and a test pad |
| 56 | W_DISABLE1# | GPIO21 WIFI_WDIS1_N, open-drain, 10 kOhm pull-up to WIFI_3V3. Card behaviour (RF kill, reset or ignored) is undocumented; Unverified |
| 54 | not connected (W_DISABLE2#) | leave open; GPIO22 freed |
| 6 / 16 | LED1 / LED2 | test pads only (sealed enclosure) |
| all other pins | not connected | leave open |

The drawing names the PCIe pairs from the card's point of view, which matches the M.2 rule that pins 35/37 carry host transmit and 41/43 carry host receive. The pull-ups return to WIFI_3V3 so nothing back-feeds the card while its rail is off; for the same reason GPIO21 must never drive high, like GPIO18/19 on the HaLow card. Whether the card already has internal pull-ups is not documented; the carrier pull-ups are harmless either way.

## GW16170 / MM8108-M20 verified signals

Gateworks documents pins 2/4/72/74 as 3.3 V, pin 3/5 as USB D+/D-, pin 56 W_DISABLE1# to RESET_N with a 200 kΩ pull-up, and pin 54 W_DISABLE2# to WAKE with a 10 kΩ pull-up. No PCIe/PERST/CLKREQ/PEWAKE signals are listed; leave them unconnected unless Gateworks documents otherwise. Since pull-ups return to HALOW_3V3, GPIO18/19 must drive low to assert and input/high-Z to release, never high.

## Electrical sources and boot evidence

Checked 2026-10-04 against the TI authorities above. Manufacturer pin behavior is Verified; carrier connectivity and startup waveforms remain Unverified.

| Signal | Device pin / source | Interface evidence |
|---|---|---|
| HALOW_PWR_EN / WIFI_PWR_EN | TPS22975 ON, pin 3 | Active high; ON must not float. External bias must hold the intended state before firmware runs |
| HALOW_FAULT_N / WIFI_FAULT_N | TPS3780D dual voltage detector (D-046) | SENSE1 from WIFI_3V3 and SENSE2 from HALOW_3V3 through 147 kΩ / 100 kΩ, VDD from +3V3_RADIO, open-drain outputs. The TPS22975 itself has no fault output; its thermal shutdown and any rail short show up as a collapsed rail |
| SUPERVISOR_WDI / SUPERVISOR_ARM | TPS386000 WDI 20 / MR 1 | WDI accepts either edge. MR arms the watchdog when high; 10 kΩ to GND holds it low. WDO 19 is not a CM5 input: it pulls the SENSE4L tap (D-044) |
| POWER_GOOD | TPS26633RGER PGOOD 16 is a candidate source | Active-high open-drain. The reference circuit pulls it to OUT for buck enables; that node cannot connect directly to CM5 GPIO |
| EFUSE_FAULT | TPS26633RGER FLT 14 | Active-low open-drain; provide a CM5-compatible pull-up, with power-off leakage checked |
| HALOW_USB_FAULT_N / VLM_USB_FAULT_N | Downstream VBUS switch / hub overcurrent path | Exact switch outputs, hub wiring, pull-ups and polarity still require GHO-11/GHO-13 closure |

The [supervisor section](v1-reference.md#supervisor-and-watchdog-ti-tps386000rgpr) owns watchdog timing and latch-clear behavior. The startup, arming and reset topology is the D-044 working default, with GPIO11 as the arming output.

Firmware source inspection is separate from physical validation. [Firmware PR #23](https://github.com/ghostnet-labs/firmware/pull/23), inspected at `c77cd924` (the GPIO lines are unchanged from `37f8e8d2`), contains:

| Boot configuration | Requested state / role |
|---|---|
| `gpio=4,5=op,dh` | Both radio power enables output high |
| `gpio=18,19=ip,pn`; `gpio=21=ip,pn` | HaLow controls and Wi-Fi disable released as inputs without pulls |
| `gpio=23=op,dh` | Hub reset output high (released) |
| `dtoverlay=pps-gpio,gpiopin=9` | GNSS PPS input consumer |
| `dtparam=uart0=on`; `dtparam=i2c_arm=on` | GNSS UART0 and system I2C requested |

[Official GPIO configuration semantics](https://www.raspberrypi.com/documentation/computers/config_txt.html#gpio) verify `op,dh` means output high and `ip,pn` means input without pulls. These directives apply during firmware configuration and can be overridden by kernel pinctrl; they do not guarantee reset-time levels, rail-ready ordering or daemon handoff. The listed file does not explicitly configure the fault inputs, supervisor pins or reserved GPIO17. GHO-9/GHO-19 retain full boot/device-tree validation, including GPIO23/24/25.

RP1 GPIO reset state: function NULL, output disabled, input disabled; per-pin pull Unverified (RP1 peripherals §3.1.4). `gpio=` directives apply a few seconds after power-up. The bring-up image adds the boot lines in [v1-gpio-and-m2-audit.md](v1-gpio-and-m2-audit.md) §5.2 (D-046, GHO-19); firmware PR #23 does not carry them yet.

## Working sequence and recovery

This is the intended hardware-controlled order, not evidence that the bring-up firmware implements it. GHO-9/GHO-10/GHO-19 must reconcile firmware release of enables/reset with rail-ready interlocks before carrier freeze.

1. While supplies are absent, software establishes no GPIO state. Hardware bias/interlocks must keep radio enables and USB VBUS off, hold hub reset asserted until its supply/clock are valid, avoid backfeed through radio controls, and meet PCIe PERST# requirements.
2. Bring up CM5 3.3 V and supervisor; keep USB VBUS switching separate from radio 3.3 V switches.
3. Enable the selected radio 3.3 V rail after supervisor-good.
4. Release HaLow reset/WAKE by high-Z GPIO18/19, then let it enumerate. An M.2 card takes no VBUS; its USB runs from HALOW_3V3.
5. Enable WIFI_3V3 with GPIO21 released; the CM5 holds PERST# (pin 109 to card pin 52) until clock/reset timing is valid, then releases it. CLKREQ# runs from card pin 53 to CM5 pin 102.
6. Deassert TUSB4041I reset only after CM5_3V3, HUB_1V1 and 24 MHz are stable (at least 3 ms after both supplies, SLLSEK3F §5.6); the 2.2 kΩ pull-down holds it until then.
7. Recovery: reset USB device → reset hub → power-cycle radio → supervisor/watchdog → CM5 PMIC_Enable (pin 99).

## Open gates

- Verify GPIO23/24/25 boot defaults, device-tree behavior, electrical polarity, and schematic connectivity.
- Verify device-tree mux/boot defaults and circuit direction for every retained logical GPIO; physical connector identity is verified in the table.
- Confirm the AW7916-AED pin numbers above against a bench card (the AsiaRF drawing has no numbers), and whether the card holds W_DISABLE1# or PEWAKE# internally. GPIO16 and GPIO22 are freed (D-026).
- Confirm TE 2199119-6 footprint, hub VBUS/ESD/straps, and eight-contact battery allocation.
- Bench-validate PCIe/USB enumeration, sequencing, and PMIC_Enable recovery.
- Allocate BRIDGE_ACTIVE_N (B-24 bridge), PACK_PRESENT and the pack I2C bus; none has a GPIO yet ([GHO-13](https://linear.app/ghostnet-labs/issue/GHO-13)). Spares: GPIO16, 17, 22, 26 and 27.

**Acceptance status:** CM5 PCIe/USB/power pins, CM5 mux facts, Gateworks control behavior, and a D-024 logical allocation (GNSS on GPIO14/15; hub reset on GPIO23; HaLow/VLM USB faults on GPIO24/25) are recorded. GPIO0–27 physical connector mappings are verified from the manufacturer table. Device-tree defaults, schematic implementation, and bench evidence remain open.
