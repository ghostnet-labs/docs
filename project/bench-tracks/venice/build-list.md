# Venice bench node: build list

This is one node. Prices are the sellers' listed prices, checked on 2026-10-12. They are a planning reference, not a purchase record: nothing is ordered, and any order goes through Justin and the [POC Purchase BOM](https://linear.app/ghostnet-labs/document/openmanet-poc-purchase-bom-ff58aa264535).

Antennas for Wi-Fi and HaLow, the 300 mm ground bar and the bench supply are shared across all tracks, as in the [bench compute screen](https://claude.ai/artifact/Sm3hWVZPsHHcJnTMRVeCXe). They are not listed here.

## Parts

| # | Part | Why | Seller, price, stock (2026-10-12) | Source |
|---|---|---|---|---|
| V-1 | **Gateworks GW11048-2 development kit**. Contents: GW7201-01 board (i.MX8M Mini, 4 GB RAM, 64 GB eMMC, GPS, TPM), power supply, cables, GW16099 JTAG/serial programmer. | Compute, on-board GNSS with PPS, 8 to 60 V input, console | DigiKey 2518-GW11048-2-ND, $940.00, 22 in stock | [Product page](https://www.gateworks.com/products/industrial-single-board-computers/imx8-single-board-computers-gateworks-venice/gw7200-rugged-industrial-single-board-computer/), [DigiKey](https://www.digikey.com/en/products/result?keywords=GW11048-2) |
| V-2 | **AsiaRF AW7916-NPD**. MT7916AN, Wi-Fi 6E AX3000, 2.4 GHz 2T2R plus 5/6 GHz 2T3R, full-size mini-PCIe (51 x 30 mm), 3 IPEX ports. Comes with a 30 x 30 x 10 mm heatsink. | Wi-Fi mesh backhaul. Same chip and `mt7915e` driver as the V1 card (AW7916-AED). Mini-PCIe fits the Venice socket directly. | AsiaRF, $29.90 | [Product page](https://asiarf.com/product/wi-fi-6e-mini-pcie-module-mt7916-aw7916-npd/), [dimension sheet](https://asiarf.com/wp-content/uploads/2023/09/AW7916-NPD_dimension-sheet.jpg) |
| V-3 | **Gateworks GW16151**, mini-PCIe to M.2 E-key adapter. Passive, carries USB 2.0 and one PCIe lane, 0.2 A typical. | Seats the M.2 HaLow card in a mini-PCIe socket. Gateworks names it as the Venice adapter for the GW16167. | DigiKey, $33 | [Product page](https://www.gateworks.com/products/mini-pcie-expansion-cards/gw16151-mini-pcie-to-wifi-e-key-m-2-adapter-card/), [wiki](https://trac.gateworks.com/wiki/expansion/gw1614xminipciem2adapter) |
| V-4 | **Gateworks GW16167**, MM8108 HaLow, M.2 2230 E-key, USB 2.0 | HaLow radio, the same one the other tracks use | DigiKey, $59 | [Wiki](https://trac.gateworks.com/wiki/expansion/gw16167) |
| V-5 | **u-blox ANN-MB1** multiband active GNSS antenna. SMA, 3.0 to 5.0 V, 15 mA typical at 5 V. | Filtered antenna that clears the HaLow coexistence budget in the screen (+5.4 dB at 1 ft against 26 dBm HaLow) | SparkFun, $99.95 | [Data sheet](https://cdn.sparkfun.com/assets/3/3/3/8/d/ANN-MB1_DataSheet_UBX-21005551.pdf) |
| V-6 | **SMA female to MMCX male adapter cable**, for example Gateworks GW10074 | The board's GNSS port is MMCX; the ANN-MB1 ends in SMA. | Gateworks shop, price not recorded | [Gateworks GPS wiki](https://trac.gateworks.com/wiki/gps) |
| V-7 | **LM74700 ideal-diode board and INA228 monitor board** | Reverse/ORing protection on the pack lead, and logged input power | Pololu and Adafruit, $19.90 together | Same parts as every track in the screen |
| V-8 | **Pack-to-board DC lead** | Pack to V-7 to the board's DC jack | Not chosen. The jack type is in the GW7200 manual, which has not been read (GHO-85, question 5). | Unverified |

**About $1,182 for one node before the shared items, the adapter cable (V-6) and the DC lead (V-8).** That is $940 + $29.90 + $33 + $59 + $99.95 + $19.90.

### Photos

| GW7200-family board, bottom | GW16151 adapter | GW16167 HaLow | AW7916-NPD |
|---|---|---|---|
| ![GW7200 bottom, labelled (Gateworks)](https://www.gateworks.com/wp-content/uploads/GW7200_BottomLabled.png) | ![GW16151 (Gateworks)](https://www.gateworks.com/wp-content/uploads/gw16151v2.png) | ![GW16167 (Gateworks)](https://www.gateworks.com/wp-content/uploads/GW16167_angled.jpg) | ![AW7916-NPD (AsiaRF)](https://asiarf.com/wp-content/uploads/2023/11/AW7916-NPD_1-1.jpg) |

The board's top side is in [README.md](README.md). All photos are the makers' own, loaded from their sites.

## Board variants (Verified 2026-10-12, Gateworks ordering options)

| Part | SoC | RAM / eMMC | GPS, TPM | Notes |
|---|---|---|---|---|
| GW7200-00 | i.MX8M Mini | 1 GB / 8 GB | no | In the GW11048-7 HaLow kit |
| **GW7201-01** | i.MX8M Mini | 4 GB / 64 GB | yes | **This track** (GW11048-2 kit) |
| GW7200-20 | i.MX8M Plus | 1 GB / 8 GB | no | |
| GW7201-21 | i.MX8M Plus | 4 GB / 64 GB | yes | Adds USB 3.0. The 8MP board.d fix in [firmware #52](https://github.com/ghostnet-labs/firmware/pull/52) is unproven on hardware. |

**Which GNSS ships** ([Gateworks GPS wiki](https://trac.gateworks.com/wiki/gps)):
- GW7201 revision H and later carry the u-blox **MIA-M10Q**, which talks at 38400 baud.
- Earlier revisions carry the **ZOE-M8Q**, at 9600 baud.

gpsd detects either baud rate on its own. The product page still names the ZOE-M8. Read the board revision on the U-Boot banner when the board arrives (GHO-85, question 4).

## Alternates

- **GW11048-7 HaLow kit.** DigiKey 2518-GW11048-7-ND, $731, 25 in stock. It contains a GW7200-00 with a GW16167, a GW16151, an antenna, a supply and the JTAG adapter, so V-3 and V-4 come in the kit.
  - It is about $300 cheaper than V-1 + V-3 + V-4.
  - The catch: the GW7200-00 has no on-board GNSS, 1 GB RAM and 8 GB eMMC. GNSS would then come from an external receiver, with PPS wired to a free GPIO on the off-board header, which is the same work as the CM5 track.
  - Not chosen, because on-board GNSS with PPS is this board's main advantage in the scorecard.
- **GW7300/GW7301.** Three mini-PCIe sockets, but only from revision F on. See the screen.
- **Wi-Fi fallback if the socket cannot carry the AW7916.** Two options, both on the fallback path in [power-budget.md](power-budget.md) §4:
  - a powered mini-PCIe interposer that feeds the card's 3.3 V from the pack through its own buck;
  - a lower-power MT7915 mini-PCIe card.

  openmanetd only builds the `batmesh1` Wi-Fi mesh on MT7915/MT7916, so the card must stay in that family.
