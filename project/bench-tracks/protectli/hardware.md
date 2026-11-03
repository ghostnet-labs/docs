# Protectli VP2430e: what the vendor documents say

These notes cover the VP2430e as it applies to the bench node. Each fact is taken from Protectli's documents, checked on 2026-10-12, or is marked Unverified.

Sources:
- the product page: https://protectli.com/product/vp2430/
- the [VP2430e datasheet dated 2026-05-27](https://protectli.com/wp-content/uploads/2026/06/VP2430e-Datasheet-20260527.pdf)
- the [hardware overview](https://kb.protectli.com/kb/vp2430-hardware-overview/)
- the [component compatibility page](https://kb.protectli.com/kb/vp2430-component-compatibility/) in Protectli's KB

The VP2430e has replaced the VP2430. Protectli says it is the same board without the 32 GB eMMC, so everything here applies to both.

![VP2430 board (Protectli)](https://protectli.com/wp-content/uploads/2025/02/VP2430_Motherboard_C_1600x1600.jpg)

![Annotated internal view (Protectli KB)](https://kb.protectli.com/wp-content/uploads/sites/9/2025/02/InternalViewAnnotated-768x698.jpg)

## Summary

| Item | Value | Status |
|---|---|---|
| CPU | Intel N150, 4 cores | Verified 2026-10-12 (datasheet) |
| RAM | 1x DDR5-4800 SO-DIMM, up to 64 GB. Not included in the base price | Verified 2026-10-12 (datasheet, configurator) |
| Storage | 1x M.2 2280 M-key NVMe (PCIe 3.0 x2), 1x internal 2.5" SATA. No eMMC on the "e" model | Verified 2026-10-12 (datasheet) |
| Ethernet | 4x Intel i226-V, 2.5 GbE (`igc`) | Verified 2026-10-12 (datasheet) |
| USB | 4x USB 2.0 Type-A and 2x USB 3.2 Gen 2 Type-C with DisplayPort. Per-port current is not stated | Verified 2026-10-12 (datasheet). Port current: Unverified |
| Firmware | AMI (default) or coreboot (Dasharo). UEFI only, no legacy BIOS | Verified 2026-10-12 (datasheet) |
| Super I/O | ITE IT8659E. Linux 6.6 `it87_wdt` lists the IT8659, and `kmod-it87-wdt` is in the image | Verified 2026-10-12 (datasheet, kernel source) |
| Chassis | Fanless aluminium, 144 x 143 x 55 mm, 1.19 kg. Operating range -10 to +50 °C. A 4-pin fan header is present | Verified 2026-10-12 (datasheet) |
| Antenna holes | 8 in total: 2 front, 2 rear, 2 per side, all plugged when unused. SMA or RP-SMA is not stated | Verified 2026-10-12 (datasheet). Connector type: Unverified |

## Power input

- The input is 12 V DC on a threaded barrel jack, centre positive. The jack takes a 5.5 x 2.5 mm plug; Protectli's replacement brick has a 5.5 x 2.5 mm locking collar. Verified 2026-10-12 (datasheet, [PSU page](https://protectli.com/product/protectli-threaded-60w-power-supply-brick/)).
- The box ships with a 12 V 5 A (60 W) brick. Verified 2026-10-12.
- Protectli rates power use at "Max 45W". Verified 2026-10-12.
- **Input tolerance around 12 V is not published.** The bench design feeds a regulated 12.2 V from the Orion-Tr rather than raw pack voltage ([power-budget.md](power-budget.md)).
- **Idle draw:** a third-party page, [AstLinux](https://doc.astlinux-project.org/userdoc:board_protectli_vp2430), says 9 W idle without HDMI and gives no method. Unverified.
- Jumper JPWR1 defaults to powering on automatically after power loss, on both AMI and coreboot. Verified 2026-10-12 (datasheet). A node that browns out therefore comes back without a button press.

## M.2 slots

| Slot | Interface | Use on this node |
|---|---|---|
| M-key 2280 | PCIe 3.0 x2 | NVMe boot drive |
| E-key 2230/3030/3052 | PCIe 3.0 x1 | AsiaRF AW7916-AED (3052). Move the standoff to the 3052 position |
| B-key 3052 | USB 3.2 Gen 1 only, no PCIe; SW1 switches set pins 20 and 22; nano SIM on the rear | Unused. A USB-attached HaLow card in this slot would free a USB-A port, but no M.2 B-key HaLow card is in the screen |

On the Wi-Fi card:
- **Protectli sells the AW7916-AED itself.** Its "M.2 802.11ax WiFi 6E Kit" ([WM-M2-004](https://protectli.com/product/protectli-m-2-802-11ax-wifi-kit/), $84, in stock 2026-10-12) is described as an MT7916AN card in the M.2 3052 form factor. Its product image and datasheet link are AsiaRF's AW7916-AED, and the page states it is compatible with the VP2430. The kit includes three IPEX cables and three antennas. Verified 2026-10-12.
- Protectli rates the card at 5 W average and 8 W maximum. AsiaRF's own page says 9 W maximum and asks the host for "3.3V 3A, minimum 3.3V 2.5A".
- **Protectli does not publish the E-key slot's 3.3 V current limit.** Unverified. The best evidence that the slot is adequate is that Protectli qualifies this card in it. The bench step in [bring-up.md](bring-up.md) checks the card under a TX burst.
- Protectli supplies two Wi-Fi thermal pads (34 x 30 x 3 mm and 32 x 30 x 4 mm) between the card and the large heatsink. Verified 2026-10-12. AsiaRF's optional 30 x 30 x 10 mm heatsink probably cannot fit together with Protectli's large heatsink (Unverified), so use the Protectli pad.

![Wi-Fi slot with a 3052 card fitted (Protectli KB)](https://kb.protectli.com/wp-content/uploads/sites/9/2025/02/VP2430_WiFiSlot.png)

![AsiaRF AW7916-AED as sold in the Protectli kit (Protectli)](https://protectli.com/wp-content/uploads/2025/06/AW7916AED_front_01.png)

## Serial ports

The box has two serial ports:
- **COM0 is the front USB-C console port.** It runs at 115200 8N1, and it is not a USB port despite the connector. It is COM0 in the AMI menu. Verified 2026-10-12 (datasheet, KB).
- **The internal header, board label COM2, is a true RS-232 port.** It uses about ±12 V levels on a 2x5 header at **2.0 mm pitch**, with pin 10 clipped. It is "COM1" in the AMI and coreboot menus, and it must be enabled there. Verified 2026-10-12 (datasheet p.11).

| COM2 pin | Signal | Used for |
|---|---|---|
| 1 | DCD | GNSS PPS, through the MAX3232 |
| 2 | RX | GNSS NMEA in (MAX3232 T1OUT) |
| 3 | TX | Commands to the GNSS (MAX3232 R1IN) |
| 4 | DTR | — |
| 5 | GND | MAX3232 GND |
| 6 | DSR | — |
| 7 | RTS | — |
| 8 | CTS | — |
| 9 | RI | — |

![COM header close-up (Protectli KB)](https://kb.protectli.com/wp-content/uploads/sites/9/2025/02/VP2430COMPort-768x247.png)

Common 2.54 mm IDC-to-DB9 brackets do not fit this header. The bench node uses 2.0 mm female jumper housings straight onto the header, so no DB9 is involved.

**Which `ttyS` the header becomes is Unverified.** The [upstream coreboot patch for the VP2430](https://mail.coreboot.org/archives/list/coreboot-gerrit@coreboot.org/thread/MXQUSE2DY6KA7SV2PKOB4XASTLLDMIWX/) maps the ports as follows:
- The USB-C console is 0x3F8 IRQ 4, which is normally `ttyS0`.
- The header is 0x2F8 IRQ 3, which is normally `ttyS1`. Its IRQ is marked "low level".

The AMI mapping is not published. `bsp-x86` assumes `/dev/ttyS1`. The first boot confirms it with `dmesg | grep ttyS` and `/proc/interrupts` ([bring-up.md](bring-up.md#3-serial-and-pps)).

How PPS reaches the kernel:
- gpsd sets the tty's line discipline to pps-ldisc, which turns each DCD change into a `/dev/pps0` event on both edges.
- The MAX3232 driver inverts the signal. The u-blox default pulse is 100 ms high with its rising edge on the second (`CFG-TP-POL_TP1 = 1`, `CFG-TP-LEN_LOCK_TP1 = 100000`), and no pulse is sent until GNSS time is valid. Through the MAX3232 that pulse becomes 900 ms asserted then 100 ms deasserted, so the top of the second is the *clear* edge.
- [gpsd 3.25 `ppsthread.c`](https://gitlab.com/gpsd/gpsd/-/blob/release-3.25/gpsd/ppsthread.c) classifies each edge by the time since the previous opposite edge. An edge after more than about 555 ms is the 1 Hz leading edge, and one after less than 450 ms is a trailing edge. It therefore takes the clear edge and ignores the assert, with no configuration needed.
- Anything that reads `/dev/pps0` directly instead of through gpsd (for example chrony's PPS refclock) must be told to use the clear edge. This image uses ntpd through gpsd's SHM, so that does not apply.

## I2C

- **JNTP1 header:** a 1x4 PicoBlade-compatible header at 1.25 mm. Pin 1 is I2C0 SCL, pin 2 I2C0 SDA, pin 3 +3.3 V and pin 4 GND. Protectli describes it as "commonly used for GPS capabilities". Verified 2026-10-12 (datasheet).
  - On Linux that controller is very likely an Intel LPSS I2C behind the `intel-lpss-pci` driver. That driver is not enabled in our x86 kernel config, and OpenWrt has no package for it. Unverified until `lspci` on the unit.
  - So the bench node puts the INA228 on a USB-I2C bridge instead (MCP2221A, `kmod-usb-hid-mcp2221`).
  - The JNTP1 +3.3 V pin is still the cleanest supply for the GNSS breakout and the MAX3232 ([build-list.md](build-list.md#wiring)). Its current limit is not published.
- **GPIO1 header:** 2x3 at 2.54 mm. It carries +5 V, GND and four Super I/O GPIOs at 5 V levels. Unused here.

![Heatsink side view (Protectli KB)](https://kb.protectli.com/wp-content/uploads/sites/9/2025/02/VP2430_Heatsink_SideViewOpen-768x391.jpg)

## Gaps tracked in Linear

These are tracked on [GHO-86](https://linear.app/ghostnet-labs/issue/GHO-86), not here:
- the ttyS mapping under AMI
- the E-key slot's 3.3 V current limit
- the 12 V input tolerance
- the antenna hole connector type
- USB per-port current
- the board's RS-232 transceiver part
