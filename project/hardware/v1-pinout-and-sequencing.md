# V1 pinout and radio sequencing evidence

**Owner:** GHO-9 — Verify carrier pinouts, GPIO muxes and radio sequencing  
**Status:** In progress. This is the canonical evidence record; proposed mappings are not a layout release.

## Authorities

- [Raspberry Pi CM5 datasheet](https://pip.raspberrypi.com/documents/RP-008180-DS-cm5-datasheet.pdf)
- [Raspberry Pi CM5 IO datasheet](https://pip.raspberrypi.com/documents/RP-008182-DS-cm5io-datasheet.pdf)
- [Advantech AIW-170BQ V1.4 User Manual](https://advdownload.advantech.com/productfile/Downloadfile4/1-2F5N99M/AIW-170BQ_%20V1.4%20User%20Manual.pdf)
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
| SCL0 GPIO39 / SDA0 GPIO38 | 80 / 82 |
| GNSS UART0 GPIO14 / GPIO15 | 55 / 51 |
| System I2C1 GPIO2 / GPIO3 | 58 / 56 |
| USB_HUB_RESET_N GPIO23 | 47 |
| HALOW_USB_FAULT_N GPIO24 | 45 |

These GPIO-to-connector mappings are from the CM5 datasheet. GPIO25 (CM5 pin 41) remains reserved.

CM5 is Gen2 x1. The CM5 TX path already has AC coupling; the peripheral TX path needs the documented 220 nF series capacitors. CM5 nWAKE is not supported in software.

## CM5 GPIO mux facts

The official alternate-function table verifies GPIO0/1 = I2C0 SDA/SCL, GPIO2/3 = I2C1 SDA/SCL, GPIO8/9 = UART3 TX/RX, and GPIO14/15 = UART0 TX/RX. The old V1 cross-reference that labels GPIO0/1 as GNSS UART is stale.

Resolution proposal: GNSS uses UART0 on GPIO14/15 and system I2C1 uses GPIO2/3, consistent with the board-configuration direction. Relocate USB_HUB_RESET_N to GPIO23 and HALOW_USB_FAULT_N to GPIO24; GPIO25–27 remain reserved. This removes the logical conflict without adding hardware. Verify the physical CM5 pins, boot defaults, and device-tree mux for GPIO23/24 before schematic/layout release.

| Logical signal | Current role | Status |
|---|---|---|
| GPIO4/5 | HALOW_PWR_EN / WIFI_PWR_EN | Logical; physical pin open |
| GPIO6/7 | HALOW_FAULT_N / WIFI_FAULT_N | Logical; physical pin open |
| GPIO8/9 | GNSS_RESET_N / GNSS_PPS | Logical; mux conflict to resolve |
| GPIO10/11 | SUPERVISOR_WDI / SUPERVISOR_WDO | Logical; physical pin open |
| GPIO12/13 | POWER_GOOD / EFUSE_FAULT | Logical; physical pin open |
| GPIO14/15 | Proposed GNSS UART0 TX/RX | Resolved proposal; verify physical pins/mux |
| GPIO18/19 | HALOW_RESET_N / HALOW_WAKE | Open-drain behavior required |
| GPIO20 | INA228_ALERT | Logical; physical pin open |
| GPIO21/22 | Wi-Fi W_DISABLE controls | Provisional |
| GPIO23 | USB_HUB_RESET_N | Proposed relocation; verify physical pin/mux |
| GPIO24 | HALOW_USB_FAULT_N | Proposed relocation; verify physical pin/mux |
| GPIO25–27 | Reserved | Unassigned |

## AIW-170BQ-001 verified M.2 signals

Advantech's V1.4 manual identifies PCIe WLAN and USB Bluetooth:

| M.2 pin | Signal |
|---:|---|
| 2,4,72,74 | 3.3 V |
| 3 / 5 | USB D+ / D- |
| 35 / 37 | PERp0 / PERn0 |
| 41 / 43 | PETp0 / PETn0 |
| 47 / 49 | REFCLKp0 / REFCLKn0 |
| 52 | PERST0# (active-low input) |
| 53 | CLKREQ0# (open drain) |
| 54 | W_DISABLE2# (Bluetooth enable) |
| 55 | PEWAKE0# (open drain) |
| 56 | W_DISABLE1# (reserved) |

Do not substitute a generic M.2 map. AIW pin 54 is not the HaLow pin-54 function.

## GW16170 / MM8108-M20 verified signals

Gateworks documents pins 2/4/72/74 as 3.3 V, pin 3/5 as USB D+/D-, pin 56 W_DISABLE1# to RESET_N with a 200 kΩ pull-up, and pin 54 W_DISABLE2# to WAKE with a 10 kΩ pull-up. No PCIe/PERST/CLKREQ/PEWAKE signals are listed; leave them unconnected unless Gateworks documents otherwise. Since pull-ups return to HALOW_3V3, GPIO18/19 must drive low to assert and input/high-Z to release, never high.

## Working sequence and recovery

1. Power-off defaults: radio rails and USB VBUS off, hub reset inactive, HaLow controls high-Z, AIW PERST0# asserted.
2. Bring up CM5 3.3 V and supervisor; keep USB VBUS switching separate from radio 3.3 V switches.
3. Enable the selected radio 3.3 V rail after supervisor-good.
4. Release HaLow reset/WAKE by high-Z GPIO18/19, then enable its USB VBUS and enumerate.
5. Enable WIFI_3V3; hold AIW pin 52 PERST0# until clock/reset timing is valid, then release. Connect CLKREQ0#; keep reserved W_DISABLE1# unassigned.
6. Deassert TUSB4020BI reset only after 3.3 V and 24 MHz are stable.
7. Recovery: reset USB device → reset hub → power-cycle radio → supervisor/watchdog → CM5 PMIC_Enable (pin 99).

## Open gates

- Verify the proposed GPIO23/GPIO24 relocation in the CM5 physical pin table, schematic, and device tree.
- Verify physical CM5 pin and device-tree mux/boot defaults for every retained logical GPIO.
- Confirm AIW PEWAKE host handling and leave W_DISABLE1 reserved.
- Confirm TE 2199119-6 footprint, hub VBUS/ESD/straps, and eight-contact battery allocation.
- Bench-validate PCIe/USB enumeration, sequencing, and PMIC_Enable recovery.

**Acceptance status:** CM5 PCIe/USB/power pins, CM5 mux facts, AIW pin table, Gateworks control behavior, and a conflict-free logical allocation proposal (GNSS on GPIO14/15; hub/fault on GPIO23/24) are recorded. Physical GPIO mapping, device-tree defaults, schematic implementation, and bench evidence remain open.
