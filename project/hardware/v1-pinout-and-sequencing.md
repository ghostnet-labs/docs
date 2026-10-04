# V1 pinout and radio sequencing evidence

**Owner:** GHO-9 — Verify carrier pinouts, GPIO muxes and radio sequencing  
**Status:** In progress. This is the canonical CM5 physical-pin, GPIO-allocation, and sequencing record; proposed mappings are not a layout release. Other project records link here instead of maintaining a second GPIO map.

## Authorities

- [Raspberry Pi CM5 datasheet](https://pip.raspberrypi.com/documents/RP-008180-DS-cm5-datasheet.pdf)
- [Raspberry Pi CM5 IO datasheet](https://pip.raspberrypi.com/documents/RP-008182-DS-cm5io-datasheet.pdf)
- [AsiaRF AW7916-AED datasheet](https://asiarf.com/wp-content/uploads/2026/07/260709_Datasheet_AW7916-AED_V1-1P.pdf)
- [Gateworks GW16167/GW16170 M.2 pinout](https://trac.gateworks.com/wiki/expansion/gw16167)

## CM5 physical carrier pins

These are CM5 connector pin numbers, not BCM GPIO numbers.

| Function | CM5 pin(s) |
|---|---:|
| PCIe CLK_nREQ / nRST | 102 / 109 |
| PCIe REFCLK P/N | 110 / 112 |
| PCIe RX P/N | 116 / 118 |
| PCIe TX P/N | 122 / 124 |
| USB2 D-/D+ | 103 / 105 |
| GPIO_VREF | 78 |
| CM5 3.3 V | 84 / 86 |
| PMIC_Enable / nRPIBOOT | 99 / 93 |
| Ethernet_SYNC_OUT (dedicated PHY timing pin) | 18 |
| SCL0 GPIO39 / SDA0 GPIO38 | 80 / 82 |

GPIO signal ownership and physical CM5 connector pin numbers are maintained together in the allocation table below (D-024).

CM5 is Gen2 x1. The CM5 TX path already has AC coupling; the peripheral TX path needs the documented 220 nF series capacitors. CM5 nWAKE is not supported in software.

## CM5 GPIO mux facts

The official alternate-function table verifies GPIO0/1 = I2C0 SDA/SCL, GPIO2/3 = I2C1 SDA/SCL, GPIO8/9 = UART3 TX/RX, and GPIO14/15 = UART0 TX/RX. The old V1 cross-reference that labels GPIO0/1 as GNSS UART is stale.

Allocation decision D-024: GNSS uses UART0 on GPIO14/15; system I2C1 uses GPIO2/3; USB_HUB_RESET_N uses GPIO23; HALOW_USB_FAULT_N uses GPIO24; VLM_USB_FAULT_N uses GPIO25; GPIO26–27 remain reserved. All GPIO0–27 physical connector mappings below were checked on 2026-10-02 against CM5 datasheet Release 3 (build 08/06/2026), §4.2 Table 4, printed page 18. GPIO0/1 appear there as ID_SD/ID_SC. Verification covers connector identity only, not software defaults or the attached circuit. These are logical allocations, not a schematic/layout release; verify boot defaults, device-tree behavior, electrical polarity, and schematic connectivity before release.

| GPIO | CM5 connector pin | Signal | Function / verification status |
|---:|---:|---|---|
| 0 | 36 | Reserved | I2C0 alternate function; unassigned |
| 1 | 35 | Reserved | I2C0 alternate function; unassigned |
| 2 | 58 | SYS_I2C_SDA | System I2C1; physical pin verified |
| 3 | 56 | SYS_I2C_SCL | System I2C1; physical pin verified |
| 4 | 54 | HALOW_PWR_EN | HaLow power enable; physical pin verified; boot/electrical verification open |
| 5 | 34 | WIFI_PWR_EN | Wi-Fi power enable; physical pin verified; boot/electrical verification open |
| 6 | 30 | HALOW_FAULT_N | HaLow fault; physical pin verified; boot/electrical verification open |
| 7 | 37 | WIFI_FAULT_N | Wi-Fi fault; physical pin verified; boot/electrical verification open |
| 8 | 39 | GNSS_RESET_N | GNSS reset; physical pin verified; boot/electrical verification open |
| 9 | 40 | GNSS_PPS | GNSS timing; physical pin verified; boot/electrical verification open |
| 10 | 44 | SUPERVISOR_WDI | Watchdog heartbeat; physical pin verified; boot/electrical verification open |
| 11 | 38 | SUPERVISOR_WDO | Watchdog status; physical pin verified; boot/electrical verification open |
| 12 | 31 | POWER_GOOD | Power-good; physical pin verified; boot/electrical verification open |
| 13 | 28 | EFUSE_FAULT | eFuse fault; physical pin verified; boot/electrical verification open |
| 14 | 55 | GNSS_UART_TX | GNSS UART0 TX; physical pin verified |
| 15 | 51 | GNSS_UART_RX | GNSS UART0 RX; physical pin verified |
| 16 | 29 | Reserved | Freed: was BT_USB_FAULT_N, and V1 has no Bluetooth (D-026). Unassigned spare |
| 17 | 50 | Reserved | Unassigned spare (D-033); no connection to the dedicated PHY timing pin |
| 18 | 49 | HALOW_RESET_N | HaLow reset; active-low open-drain, physical pin verified; boot/electrical verification open |
| 19 | 26 | HALOW_WAKE_N | HaLow wake; active-low open-drain, optional; physical pin verified; boot/electrical verification open |
| 20 | 27 | INA228_ALERT_N | Battery monitor alert; physical pin verified; boot/electrical verification open |
| 21 | 25 | WIFI_WDIS1_N | Wi-Fi RF disable to AW7916-AED pin 56. Open-drain use: drive low to assert, input/high-Z to release, 10 kOhm pull-up to WIFI_3V3 on the carrier. Physical pin verified; boot/electrical verification open |
| 22 | 46 | Reserved | Freed: was WIFI_WDIS2_N, and AW7916-AED pin 54 (W_DISABLE2#) is not connected on the card. Unassigned spare; firmware leaves it unconfigured |
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
| 1, 7, 18, 33, 39, 45, 51, 57 and others marked GND | GND | GND |
| 3, 5 | not connected (no USB) | leave open; hub port 2 is spare |
| 35 / 37 | PCIe lane 0 receive pair (labelled PERp0 / PERn0 from the card's side) | CM5 PCIe TX P/N, pins 122 / 124 (CM5 already AC-couples this direction) |
| 41 / 43 | PCIe lane 0 transmit pair (labelled PETp0 / PETn0) | CM5 PCIe RX P/N, pins 116 / 118, through 220 nF series capacitors |
| 47 / 49 | REFCLKp0 / REFCLKn0 | CM5 REFCLK P/N, pins 110 / 112 |
| 52 | PERST0# | CM5 PCIe nRST, pin 109 |
| 53 | CLKREQ0# | CM5 PCIe CLK_nREQ, pin 102 |
| 55 | PEWAKE0# | not used by the CM5 (nWAKE unsupported): 10 kOhm pull-up to WIFI_3V3 and a test pad |
| 56 | W_DISABLE1# | GPIO21 WIFI_WDIS1_N, open-drain, 10 kOhm pull-up to WIFI_3V3 |
| 54 | not connected (W_DISABLE2#) | leave open; GPIO22 freed |
| 6 / 16 | LED1 / LED2 | test pads only (sealed enclosure) |
| all other pins | not connected | leave open |

The drawing names the PCIe pairs from the card's point of view, which matches the M.2 rule that pins 35/37 carry host transmit and 41/43 carry host receive. The pull-ups return to WIFI_3V3 so nothing back-feeds the card while its rail is off; for the same reason GPIO21 must never drive high, like GPIO18/19 on the HaLow card. Whether the card already has internal pull-ups is not documented; the carrier pull-ups are harmless either way.

## GW16170 / MM8108-M20 verified signals

Gateworks documents pins 2/4/72/74 as 3.3 V, pin 3/5 as USB D+/D-, pin 56 W_DISABLE1# to RESET_N with a 200 kΩ pull-up, and pin 54 W_DISABLE2# to WAKE with a 10 kΩ pull-up. No PCIe/PERST/CLKREQ/PEWAKE signals are listed; leave them unconnected unless Gateworks documents otherwise. Since pull-ups return to HALOW_3V3, GPIO18/19 must drive low to assert and input/high-Z to release, never high.

## Working sequence and recovery

1. Power-off defaults: radio rails and USB VBUS off, hub reset inactive, HaLow controls high-Z, Wi-Fi PERST# asserted.
2. Bring up CM5 3.3 V and supervisor; keep USB VBUS switching separate from radio 3.3 V switches.
3. Enable the selected radio 3.3 V rail after supervisor-good.
4. Release HaLow reset/WAKE by high-Z GPIO18/19, then enable its USB VBUS and enumerate.
5. Enable WIFI_3V3 with GPIO21 released; the CM5 holds PERST# (pin 109 to card pin 52) until clock/reset timing is valid, then releases it. CLKREQ# runs from card pin 53 to CM5 pin 102.
6. Deassert TUSB4041I reset only after 3.3 V and 24 MHz are stable.
7. Recovery: reset USB device → reset hub → power-cycle radio → supervisor/watchdog → CM5 PMIC_Enable (pin 99).

## Open gates

- Verify GPIO23/24/25 boot defaults, device-tree behavior, electrical polarity, and schematic connectivity.
- Verify device-tree mux/boot defaults and circuit direction for every retained logical GPIO; physical connector identity is verified in the table.
- Confirm the AW7916-AED pin numbers above against a bench card (the AsiaRF drawing has no numbers), and whether the card holds W_DISABLE1# or PEWAKE# internally. GPIO16 and GPIO22 are freed (D-026).
- Confirm TE 2199119-6 footprint, hub VBUS/ESD/straps, and eight-contact battery allocation.
- Bench-validate PCIe/USB enumeration, sequencing, and PMIC_Enable recovery.

**Acceptance status:** CM5 PCIe/USB/power pins, CM5 mux facts, Gateworks control behavior, and a D-024 logical allocation (GNSS on GPIO14/15; hub reset on GPIO23; HaLow/VLM USB faults on GPIO24/25) are recorded. GPIO0–27 physical connector mappings are verified from the manufacturer table. Device-tree defaults, schematic implementation, and bench evidence remain open.
