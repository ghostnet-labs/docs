# VP2430e bench node: build list and wiring

**This is a screening snapshot from 2026-10-12, not a purchasing record.** Nothing on this list has been bought. Purchases go through [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36) and the Linear "OpenMANET POC — Purchase BOM", and only once Justin decides. Prices and stock come from the seller pages as read on 2026-10-12.

## Parts for one node

| Part | Why | Price | Seller (2026-10-12) |
|---|---|---|---|
| [Protectli VP2430e](https://protectli.com/product/vp2430/) | Compute: N150, 4x 2.5 GbE, E-key Wi-Fi slot, RS-232 header with DCD, 12 V input. The base price includes no RAM and no SSD | $419 | Protectli configurator. Choose AMI firmware (the default); coreboot is also offered at no charge |
| 8 GB DDR5-4800 SO-DIMM (Kingston, configurator option) | RAM. 8 GB is plenty for OpenWrt | $160 | Protectli configurator. Protectli's [compatibility list](https://kb.protectli.com/kb/vp2430-component-compatibility/) also names Crucial CT8G48C40S5.M4A1 and Kingston KVR48S40BS6-8 for self-sourcing, at prices not checked |
| 500 GB Kingston NV3 NVMe (configurator option) | Boot drive. Any small M.2 2280 NVMe works | $140 | Protectli configurator. Self-sourcing is likely cheaper; not checked |
| [Protectli M.2 802.11ax Wi-Fi 6E kit](https://protectli.com/product/protectli-m-2-802-11ax-wifi-kit/) (WM-M2-004): AsiaRF AW7916-AED, 3 IPEX cables, 3 antennas | Wi-Fi mesh backhaul (MT7916), the V1 card, in a kit Protectli qualifies for this box | $84 | Protectli, in stock. The bare card is $29.90 at [AsiaRF](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/), but then the IPEX-to-bulkhead cables have to be matched to the chassis holes |
| [Gateworks GW16167](https://trac.gateworks.com/wiki/expansion/gw16167) HaLow (MM8108) + Pier42 USB-C carrier | HaLow radio on USB | $88.14 | Same as the CM5 track: $59 DigiKey + $29.14 Lectronz |
| [SparkFun MAX-M10S breakout](https://www.sparkfun.com/sparkfun-gnss-receiver-breakout-max-m10s-qwiic.html) (GPS-18037) + u-blox ANN-MB1 | GNSS with PPS. 3.3 V only, with no regulator on the board. It has a rechargeable backup cell for warm starts | $145.90 | SparkFun, the same pair as the CM5 track. The breakout's stock shows both "In stock" and "Backorder" |
| [SparkFun MAX3232 breakout](https://www.sparkfun.com/sparkfun-transceiver-breakout-max3232.html) (BOB-11189) | 3.3 V TTL to RS-232 for NMEA and PPS. Two drivers and two receivers on a plain header, with no DB9 | $7.26 | SparkFun, in stock |
| [Adafruit INA228](https://www.adafruit.com/product/5832) (5832) | Battery telemetry, the same chip as the CM5 track and V1. 15 mΩ shunt, 85 V, address 0x40 | $14.95 | Adafruit, in stock |
| [Adafruit MCP2221A](https://www.adafruit.com/product/4471) (4471) | USB to I2C for the INA228, over STEMMA QT | $6.50 | **Out of stock at Adafruit on 2026-10-12.** Other MCP2221A boards were not checked |
| [Victron Orion-Tr 12/12-9 isolated](https://ussolarsupplier.com/products/victron-energy-orion-tr-12-12-9a-110w-isolated-dc-dc-converter-ori121210110) (ORI121210110) | 3S pack to a regulated 12.2 V across 9.0 to 12.6 V. 110 W | $63.75 | US Solar Supplier; stock not shown |
| **Total** | | **about $1,130** | Before the ideal diode, the cables and the shared bench kit |

Small parts, with prices not checked:
- 2.0 mm pitch female jumper wires for the COM2 header.
- A 4-pin 1.25 mm PicoBlade-compatible cable for JNTP1.
- A 5.5 x 2.5 mm barrel plug pigtail.
- A fuse holder with a 7.5 A fuse.

These are shared across all four tracks and not counted above:
- the HaLow W1063M whip
- the U.FL and MMCX pigtails
- the 300 mm aluminium ground bar
- the 3S2P pack
- a current-limited bench supply

The ideal-diode board is also shared, but it must be rated above 6 A for this track ([power-budget.md](power-budget.md#at-the-3s-pack)).

![VP2430 rear: four 2.5 GbE ports, SIM tray, 12 V jack (Protectli)](https://protectli.com/wp-content/uploads/2025/02/VP2430_NIC_1600x1600.jpg)

## Wiring

### Power

```
3S2P pack (9.0-12.6 V) -> 7.5 A fuse -> ideal diode (>6 A) -> INA228 shunt (VIN+ to VIN-) -> Orion-Tr 12/12-9 in
Orion-Tr out (12.2 V) -> 5.5 x 2.5 mm barrel plug (centre positive) -> VP2430 12 V jack
```

- **Where the INA228 sits.** It is high-side on the pack side of the converter, so it measures what the pack delivers, converter losses included. That is the figure runtime depends on. Its VBUS pin goes to the shunt's load side to read the pack voltage.
- **Ground.** The Orion-Tr is isolated, but the INA228's ground is the VP2430's ground through USB. Tie the converter's input negative to its output negative with one short wire at the converter. The pack, the INA228 and the VP2430 then share one ground, and the INA228's bus voltage reads the pack.
- Run 16 AWG or heavier on the pack side.
- Set the Orion-Tr output to its 12.2 V nominal or lower. Victron states that the buck-boost regulation across the input range holds only at or below nominal.
- The front USB-C port marked COM is the serial console and works only with the supplied console cable; Protectli states it is not a USB port. The HaLow carrier and the MCP2221A go on the USB-A ports.

### COM2 header, MAX3232 and GNSS

The GNSS breakout and the MAX3232 take 3.3 V from JNTP1 pin 3, so the GNSS runs off the box with no extra supply. The pin's current limit is not published. The two boards draw about 40 mA together.

| From | To | Signal |
|---|---|---|
| JNTP1 pin 3 (+3.3 V) | MAX3232 VCC, MAX-M10S 3.3V | Supply |
| JNTP1 pin 4 (GND) | MAX3232 GND, MAX-M10S GND, COM2 pin 5 | Ground |
| MAX-M10S TXO | MAX3232 T1IN | NMEA out |
| MAX3232 T1OUT | COM2 pin 2 (RX) | NMEA at RS-232 levels |
| COM2 pin 3 (TX) | MAX3232 R1IN | Commands at RS-232 levels |
| MAX3232 R1OUT | MAX-M10S RXI | Commands in |
| MAX-M10S PPS | MAX3232 T2IN | PPS (100 ms high, rising edge on the second) |
| MAX3232 T2OUT | COM2 pin 1 (DCD) | PPS, inverted; gpsd takes the clear edge ([hardware.md](hardware.md#serial-ports)) |

Wire the MAX-M10S breakout's 8-pin header by its silkscreen labels. The pin order read from the SparkFun schematic is not confirmed. Put the ANN-MB1 on the breakout's SMA, about 1 ft from the radios on the ground bar, as in the screen's coexistence layout.

### Battery monitor

| From | To | Notes |
|---|---|---|
| MCP2221A USB-C | VP2430 USB-A, through a USB-C to A cable | Appears as an I2C adapter named `MCP2221 ...`; `bsp-x86` binds the INA228 on it |
| MCP2221A STEMMA QT | INA228 STEMMA QT | 3.3 V, GND, SDA, SCL. Leave A0 and A1 at GND (address 0x40) |

### Radios

| Radio | Where | Notes |
|---|---|---|
| AW7916-AED | Internal E-key slot, standoff in the 3052 position | Fit Protectli's Wi-Fi thermal pad between the card and the large heatsink: 34 x 30 x 3 mm, or 32 x 30 x 4 mm if the 3 mm pad does not touch. Route the three IPEX cables to the side or rear antenna holes, away from the front holes used for HaLow |
| GW16167 on the Pier42 carrier | Any USB 2.0 Type-A port, on a short USB-C to A cable | The W1063M whip goes on the carrier's MMCX, outside the chassis |
| MAX-M10S | COM2 header and JNTP1 as above | Mount outside the chassis on the ground bar; the aluminium box shields anything inside |
