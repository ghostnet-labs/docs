# CM5 bench node: build list and wiring

**This is a screening snapshot from 2026-10-12, not a purchasing record.** Nothing on this list has been bought. Purchases go through [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36) and the Linear "OpenMANET POC — Purchase BOM", and only once Justin decides. Prices and stock come from the seller pages the bench compute screen checked on 2026-10-12 ([screen](https://claude.ai/artifact/Sm3hWVZPsHHcJnTMRVeCXe)).

## Parts for one node

| Part | Why | Price | Seller (2026-10-12) |
|---|---|---|---|
| Raspberry Pi CM5104016 (4 GB RAM, 16 GB eMMC, Wi-Fi) | Compute. The on-module Wi-Fi is not used for the mesh | $130 | [Seeed](https://www.seeedstudio.com/Raspberry-Pi-Compute-Module-CM5104016-p-6270.html), 3 in stock, ships from CN. Alternative: [SparkFun CM5104064](https://www.sparkfun.com/raspberry-pi-compute-module-5-64gb-4gb-ram-wireless.html) at $150. The [CM5 product brief](https://datasheets.raspberrypi.com/cm5/cm5-product-brief.pdf) lists CM5104016 at $130 and CM5104064 at $140 |
| [Waveshare CM5-DUAL-ETH-BASE](https://www.waveshare.com/cm5-dual-eth-base.htm) | Carrier: 7 to 36 V input, M.2 M-key slot on its own 3 A rail, 40-pin header | $54.99 | Waveshare, orderable |
| CM5 passive cooler (Raspberry Pi SC1570 class) | Keeps the CM5 below throttling during the power peak test | $5 | [DigiKey](https://www.digikey.com/en/products/result?keywords=CM5%20cooler) |
| Sintech M.2 M-key to A+E-key adapter | Puts the M.2 3052 A+E card in the M-key slot | $9.99 | Amazon |
| [AsiaRF AW7916-AED](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) | Wi-Fi mesh backhaul (MT7916), the V1 card | $29.90 | AsiaRF, in stock |
| [Gateworks GW16167](https://trac.gateworks.com/wiki/expansion/gw16167) HaLow (MM8108) + Pier42 USB-C carrier | HaLow radio on USB | $88.14 | $59 DigiKey + $29.14 Lectronz |
| MAX-M10S breakout + u-blox ANN-MB1 antenna | GNSS with PPS. The ANN-MB1's filtered LNA gives the coexistence margin the SAM-M10Q lacks | $145.90 | SparkFun |
| LM74700 ideal diode + INA228 monitor ([Adafruit 5832](https://www.adafruit.com/product/5832), 15 mΩ shunt, address 0x40) | Reverse-polarity protection the carrier lacks, and battery telemetry | $19.90 | Pololu + Adafruit |
| **Total** | | **about $484** | Before the shared antennas, ground bar and bench supply |

Shared across all four tracks and not counted above: the HaLow W1063M whip, three ADD5RA Wi-Fi dipoles, U.FL and MMCX pigtails, the 300 mm aluminium ground bar, the 3S2P pack and a current-limited bench supply.

Alternate carrier from the screen: the Oratek TOFU5+ (5 to 36 V, 3.3 V/10 A shared, two M.2 slots) at CHF 189, pre-order from one seller.

![CM5-DUAL-ETH-BASE with a CM5 fitted (Waveshare)](https://www.waveshare.com/img/devkit/CM5-DUAL-ETH-BASE/CM5-DUAL-ETH-BASE-details-1.jpg)

## Wiring

### Power

```
3S2P pack (9.0-12.6 V) -> fuse (5 A) -> LM74700 ideal diode -> INA228 shunt (IN+ to IN-) -> DC barrel (CN1) -> MP9447 buck -> CM4_5V
```

- The INA228 sits high-side, after the ideal diode, so it measures exactly what the carrier draws. Its VBUS pin goes to the shunt's load side to read the pack voltage.
- Use 18 AWG or heavier for the pack run. Peak draw is about 3 A at an empty 3S pack ([power-budget.md](power-budget.md)).
- Never connect the USB-C port to a PC while the barrel jack is powered. With DC present the carrier drives 5 V out of the USB-C port.

### 40-pin header

| Header pin | Signal | Connects to |
|---|---|---|
| 1 | 3.3 V | MAX-M10S breakout 3.3 V |
| 6 | GND | MAX-M10S GND |
| 8 | GPIO14, UART0 TX | MAX-M10S RX |
| 10 | GPIO15, UART0 RX | MAX-M10S TX |
| 12 | GPIO18 | MAX-M10S PPS (TIMEPULSE) |
| 17 | 3.3 V | INA228 VCC |
| 9 | GND | INA228 GND |
| 3 | GPIO2, SDA1 | INA228 SDA |
| 5 | GPIO3, SCL1 | INA228 SCL |
| 13, 15 | GPIO27/22 | Leave unused. The image's i2c-gpio overlay claims them |

The INA228 shares i2c-1 with the carrier's CAT24C32 EEPROM (0x50) and ATSHA204 (0x64). Keep the INA228 at 0x40 (A0 and A1 to GND, the Adafruit default).

### Radios

| Radio | Where | Notes |
|---|---|---|
| AW7916-AED | M.2 slot through the Sintech adapter | The card is 30 x 52 mm and overhangs the adapter's 2230 position. Support its far end on the carrier's 2242 or 2260 nut. Three U.FL pigtails to the ADD5RA dipoles |
| GW16167 on the Pier42 carrier | USB-C port (J4, the BCM2712's own dwc2 controller) | Not shared with the 2.5 GbE NIC or the CH334 hub. Fallback: Type-A ports J1/J2 on the hub |
| MAX-M10S | 40-pin header, UART0 and GPIO18 | ANN-MB1 on the breakout's antenna connector. Confirm on the bench that the breakout feeds antenna bias to the ANN-MB1's LNA |

### Antenna layout

From the screen's "Antennas within one foot" section: all bulkheads on one 300 mm aluminium ground bar, all vertical.
- x = 0 mm: HaLow W1063M whip.
- x = about 90, 150 and 210 mm: the three Wi-Fi dipoles, at least 60 mm apart. The 5/6 GHz-only port goes nearest the GNSS, and the two 2.4 GHz-capable ports go nearest the HaLow end. AsiaRF does not publish the port-to-chain map, so find it on the bench.
- x = 300 mm: the ANN-MB1 on a 100 mm or larger steel or ground plate, zenith up, at or above the whip's feed height.
- Route the GNSS coax away from the Wi-Fi U.FL and HaLow MMCX pigtails.
- A second node goes at least 1 m away, or is cabled through attenuators.

Isolation figures for this layout are calculated (Friis), not measured. At 1 ft, 915 MHz gives 21.4 dB of free-space isolation, matching the corrected figures in [track-a.md](../../poc/track-a.md).
