# NanoPC-T6 LTS bench node: build list

This is one node. Prices are the sellers' listed prices, checked on 2026-10-12, and come from the [bench compute screen](https://claude.ai/artifact/Sm3hWVZPsHHcJnTMRVeCXe) unless stated. They are a planning reference, not a purchase record: nothing is ordered, and any order goes through Justin and the [POC Purchase BOM](https://linear.app/ghostnet-labs/document/openmanet-poc-purchase-bom-ff58aa264535).

Shared across all tracks, as in the screen, and not listed here:
- antennas for Wi-Fi and HaLow;
- the 300 mm ground bar;
- the bench supply.

## Parts

| # | Part | Why | Seller, price (2026-10-12) | Source |
|---|---|---|---|---|
| N-1 | **FriendlyElec NanoPC-T6 LTS, 4 GB RAM / 64 GB eMMC** (PCB rev 2310) | Compute. Official 3.3 V / 3 A E-key, 5 to 20 V input, 40-pin header | FriendlyElec, $179, in stock | [Product page](https://www.friendlyelec.com/index.php?route=product/product&product_id=292), [wiki](https://wiki.friendlyelec.com/wiki/index.php/NanoPC-T6), [schematic](https://wiki.friendlyelec.com/wiki/images/4/44/NanoPC-T6_LTS_2310_SCH.pdf), [DXF](https://wiki.friendlyelec.com/wiki/images/0/08/NanoPC-T6_LTS_2310_DXF.zip) |
| N-2 | **AsiaRF AW7916-AED**: MT7916, M.2 3052 A+E key, 3.3 V / 3 A | Wi-Fi mesh backhaul, the V1 card. Fits only with the changes in [e-key-fit.md](e-key-fit.md) | AsiaRF, $29.90 | [Product page](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) |
| N-3 | **Gateworks GW16167**: MM8108 HaLow, M.2 2230 E-key, USB 2.0 | HaLow radio, the same one the other tracks use | DigiKey, $59 | [Wiki](https://trac.gateworks.com/wiki/expansion/gw16167) |
| N-4 | **Pier42 NGFF M.2 Simple Carrier, A/E key**: M.2 2230/3030/2242/3042 to USB | Puts the HaLow card on a USB port, because the board's one E-key slot holds the Wi-Fi card. Its switched 3.3 V is rated 500 mA (screen; GHO-87 question 3). | Lectronz, €23 (the screen recorded $29.14 delivered) | [Lectronz](https://lectronz.com/products/ngff-m2-simple-carrier-ae-key), [Tindie](https://www.tindie.com/products/pier42/ngff-m2-simple-carrier-ae-key/) |
| N-5 | **SparkFun GNSS Receiver Breakout, MAX-M10S (Qwiic)**, GPS-18037. 3.3 V, UART at 38400 baud by default, PPS pin, SMA. | GNSS with a PPS output for the header | SparkFun, $45.95 | [Hookup guide](https://learn.sparkfun.com/tutorials/gnss-receiver-breakout---max-m10s-qwiic-hookup-guide), [docs](https://docs.sparkfun.com/SparkFun_u-blox_MAX-M10S/single_page) |
| N-6 | **u-blox ANN-MB1** multiband active GNSS antenna. SMA, 3.0 to 5.0 V bias. | Filtered antenna that clears the HaLow coexistence budget in the screen (+5.4 dB at 1 ft against 26 dBm HaLow) | SparkFun, $99.95 | [Data sheet](https://cdn.sparkfun.com/assets/3/3/3/8/d/ANN-MB1_DataSheet_UBX-21005551.pdf) |
| N-7 | **Pololu ideal diode reverse-voltage protector (LM74700-Q1), 4 to 60 V** and **Adafruit 5832 INA228 breakout (15 mΩ shunt)** | Reverse protection is **required**: the board has none ([power-budget.md](power-budget.md) §1). The INA228 logs input power, the same part as every track. | Pololu and Adafruit, $19.90 together | [Pololu 12 A version via RobotShop](https://www.robotshop.com/products/pololu-ideal-diode-reverse-voltage-protector-4-60v-12a) |
| N-8 | **RK3588 heatsink and fan** for the NanoPC-T6 | The RK3588 needs active cooling; the board has a 5 V PWM fan header | Not chosen. FriendlyElec sells T6 cases and heatsinks; price not recorded. | Unverified |
| N-9 | **Pack lead with a 5.5 x 2.1 mm barrel plug**, and female-female 2.54 mm jumpers for the header | Pack to N-7 to the board; GNSS and INA228 to the header | Generic, price not recorded | Jack size Verified from the wiki |

**About $463 for one node before the shared items, the cooling (N-8) and the leads (N-9).** That is $179 + $29.90 + $59 + $29.14 + $45.95 + $99.95 + $19.90 = $462.84 at the screen's prices. Most of that is radios and GNSS that every track buys; the board itself is the cheapest compute in the comparison.

### Photos

| Top | Underside | Ports | Layout |
|---|---|---|---|
| ![NanoPC-T6 LTS top (FriendlyElec)](https://wiki.friendlyelec.com/wiki/images/6/60/NanoPC-T6LTS-A01.jpg) | ![NanoPC-T6 LTS underside (FriendlyElec)](https://wiki.friendlyelec.com/wiki/images/5/5f/NanoPC-T6LTS-B01.jpg) | ![NanoPC-T6 LTS ports (FriendlyElec)](https://wiki.friendlyelec.com/wiki/images/a/ad/T6LTS-01.jpg) | ![NanoPC-T6 LTS layout (FriendlyElec)](https://wiki.friendlyelec.com/wiki/images/8/8c/NanoPC-T6LTS_Layout-L.jpg) |

All photos are FriendlyElec's own, loaded from the wiki. The underside photo with the 3052 envelope drawn on it is in [e-key-fit.md](e-key-fit.md).

## Header wiring (Verified 2026-10-12 from the schematic; device tree in [firmware #55](https://github.com/ghostnet-labs/firmware/pull/55))

| Header pin | SoC pin and function | Connects to | Linux device |
|---|---|---|---|
| 1 | 3.3 V (0.5 A budget for the whole header) | MAX-M10S 3.3V, INA228 VIN (logic) | |
| 3 | GPIO1_D7, I2C8_SDA_M2 (2.2K pull-up on board) | INA228 SDA | `/dev/i2c-8` |
| 5 | GPIO1_D6, I2C8_SCL_M2 (2.2K pull-up on board) | INA228 SCL | |
| 6, 9 | GND | MAX-M10S GND, INA228 GND | |
| 8 | GPIO0_C5, UART0_TX_M0 | MAX-M10S RX | `/dev/ttyS0` |
| 10 | GPIO0_C4, UART0_RX_M0 | MAX-M10S TX | |
| 12 | GPIO3_B7, `pps-gpio` (pulled down) | MAX-M10S PPS | `/dev/pps0` |

These are the same physical positions as a Raspberry Pi GNSS HAT, so one harness serves this board and the CM5 on the DUAL-ETH-BASE.

## Alternates

- **A Morse Micro USB HaLow adapter instead of N-3 + N-4.** Morse Micro released MM8108 USB-A and USB-C HaLow adapters in September 2026 ([CNX Software](https://www.cnx-software.com/2026/09/14/morse-micro-wi-fi-halow-usb-adapters-add-802-11ah-connectivity-to-pcs-and-routers/)). It would drop the carrier, but it differs from the GW16167 the other tracks use, so it is not the default.
- **The internal 10-pin USB 2.0 header** (two host ports, 5 V / 2 A, wiki) instead of a Type-A port for the HaLow carrier. This is tidier in an enclosure and needs a 2.54 mm to USB-A pigtail.
- **A 2230 MT7915/MT7916 card** if the 3052 fit fails. None has been identified yet ([e-key-fit.md](e-key-fit.md) §5).
- **Other Rockchip boards** do not qualify (screen): the NanoPi R6S and R76S have no PCIe slot, and the ROCK 5A has a 2 A slot rail.
