# V1 Ethernet board header and pigtail options

**Owner:** [GHO-45](https://linear.app/ghostnet-labs/issue/GHO-45): select the 1000BASE-T board header and pigtail behind the D-022 feed-through (D-025)  
**Status:** Options study. The selection is B-06 in [v1-selections.md](v1-selections.md), and the signal-integrity limits are in [v1-reference.md](v1-reference.md) §10. This file holds the comparison, sources, prices and open checks behind them. The placement is `eth_header` in the firmware floorplan model ([`parts.yaml`](https://github.com/ghostnet-labs/firmware/blob/24.10/docs/hardware/v1-mechanical/parts.yaml)).

Research dates: 2026-10-02 and 2026-10-09. Molex, DigiKey, Mouser, RS, Farnell, LCSC and Octopart product pages refused scripted access in both sessions. Prices and stock below come from search-index snapshots of the distributor pages, not from live pages, and are marked as such. Product photos are on the linked distributor and maker pages; no image file was downloaded.

## Requirements

| Requirement | Source |
|---|---|
| 8 positions: four 100 ohm MDI pairs, MDI side of the magnetics, magnetics on the carrier | D-025, v1-reference.md §10 |
| 3.5 mm or less above the PCB (runs under the RJ45 plug, 4 mm above the board) | D-025 |
| Positive latch | GHO-45 |
| Orderable from stock | GHO-45 |
| Fits the floorplan slot near X 41, Y 2 beside the USB hub | v1-reference.md §18, firmware `parts.yaml` |

## Options

| | Option 1: Molex Pico-Lock 1.50 mm (recommended) | Option 2: Hirose DF52 0.80 mm | Option 3: JST GH 1.25 mm |
|---|---|---|---|
| Header | [504050-0891](https://www.digikey.com/en/products/detail/molex/5040500891/4693487), 8 ckt, right angle, SMT, gold | [DF52-8S-0.8H(21)](https://www.digikey.com/en/products/detail/hirose-electric-co-ltd/DF52-8S-0-8H-21/5721356), 8 pos, right angle, SMT, tin | [SM08B-GHS-TB(LF)(SN)](https://www.digikey.com/product-detail/en/jst-sales-america-inc./SM08B-GHS-TB(LF)(SN)/455-1570-2-ND/807792), 8 pos, side entry, SMT |
| Crimp housing | [504051-0801](https://www.digikey.com/en/products/detail/molex/5040510801/4693488) | [DF52-8P-0.8C](https://www.digikey.com/en/products/detail/hirose-electric-co-ltd/DF52-8P-0-8C/5721343) | GHR-08V-S (Unverified) |
| Crimp terminal | [504052-0098](https://www.digikey.in/en/products/detail/molex/5040520098/4357152), gold, 24-28 AWG | DF52-2832PCF, 28-32 AWG | SSHL-002T-P0.2, 26-30 AWG (Unverified) |
| Height above PCB | **2.00 mm mated** (Molex) | 1.75 mm mated (Hirose) | **4.25 mm** (distributor data): fails the 3.5 mm limit |
| Footprint (W x D) | Header body 15.75 x 6.10 mm, 6.61 mm deep with pads; housing 15.95 mm wide over its locks, 6.40 mm long, 1.92 mm tall | About 8.6 x 4.1 mm mated (search extract) | 13.25 x 4.85 mm (distributor data) |
| Lock | Positive side locks (Molex) | Positive lock with click (Hirose); one distributor lists it as friction | Positive (secure lock) |
| Rating | 2.0 A per contact, 150 V, -40 to +105 °C, 30 mating cycles (Molex datasheet, 2022-08-31) | 1.5 A, -40 to +85 °C, 20 cycles; voltage not recorded | 1 A, 50 V |
| Cable fit | Takes 24-28 AWG, so standard 24/26 AWG Cat5e or Cat6 conductors crimp directly | 28-32 AWG only, so it needs a slim 28 AWG cable or a splice | 26-30 AWG |
| Ready-made cable | Pico-Lock to Pico-Lock jumpers only: [15132-0800](https://uk.farnell.com/molex/15132-0800/cable-assy-8pos-crimp-socket-50mm/dp/2820727) (50 mm), 15132-0802 (150 mm), 15132-0803 (300 mm). No RJ45 version found | Single pre-crimped leads only | RJ45-to-GH cables exist (for example [ARK Gigabit Ethernet Adapter](https://arkelectron.com/product/gigabit-ethernet-adapter/)) |
| Header price, qty 1 (search snapshot, USD) | $1.56 (DigiKey WM14421CT-ND); $1.13 at 100 | about $0.56 at 10 (DigiKey) | $0.53 (DigiKey) |
| Housing price, qty 1 (search snapshot, USD) | $0.49 (DigiKey WM13368-ND) | not recorded | not recorded |
| Stock (search snapshot) | Header about 25,700 at DigiKey US, 19-week factory lead time; housing about 22,500; terminal about 470,000 (DigiKey India) | Header 0 at DigiKey US | About 10,800 at DigiKey |
| Hand crimp tool | Molex [63827-0800](https://www.newark.com/molex/63827-0800/crimp-tool-ratchet-28-24awg-contact/dp/42X3078) (24-28 AWG) | Hirose tool, not recorded | JST tool, not recorded |
| Datasheet / drawing | [Part datasheet](https://assets.testequity.com/te1/Documents/pdf/Molex/Molex_504050-0891_Headers-and-Wire-Housings_Datasheet.pdf); [housing drawing 5040510000-SD](https://www.farnell.com/cad/3578775.pdf); [product spec PS-504051-001](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/productspecificationpdf/504/504051/5040511001-PS-000.pdf); header drawing SD-504050-001 on the [Molex part page](https://www.molex.com/en-us/products/part-detail/5040500891) | [DF52 catalog](https://www.hirose.com/en/product/document?clcode=&productname=&series=DF52&documenttype=Catalog&lang=en&documentid=en_DF52_CAT) | [GH datasheet](https://www.jst-mfg.com/product/pdf/eng/eGH.pdf) |
| STEP | [Molex part page](https://www.molex.com/en-us/products/part-detail/5040500891) (not downloaded); KiCad has a footprint but no 3D model | [SnapEDA](https://www.snapeda.com/parts/DF52-8S-0.8H(21)/Hirose/view-part/) | Via SnapEDA or Octopart (Unverified) |
| Verdict | Meets every requirement | Fits, but forces 28 AWG wire and US stock is thin | Fails the height limit |

Families screened out on 2026-10-02: Molex Pico-Lock 1.00 mm (503763, 6 circuits at most), Molex Pico-Clasp (4.70 mm tall), Molex Micro-Lock Plus 1.25 mm (about 4.1-4.4 mm tall, Unverified), Harwin Gecko (5.50 mm), Hirose DF50 (about 6 mm, Unverified), JST SH and SHL (friction lock only), Molex PicoBlade, CLIK-Mate and Hirose DF13 (friction lock or too tall).

## Recommendation

Molex Pico-Lock 1.50 mm, as recorded in B-06: header 504050-0891, housing 504051-0801, terminals 504052-0098. It is the only verified positive-lock 8-position family under 3.5 mm whose terminals take ordinary 24/26 AWG Cat5e or Cat6 conductors, so the pairs can stay twisted up to the housing. All three parts showed stock at DigiKey. The pigtail is custom: Cat5e or Cat6 crimped to 504052-0098 with the 63827-0800 tool at the board end and a T568B plug at the other. For bring-up, a 15132-08xx jumper can be cut and fitted with an RJ45 plug, but it is 24 AWG discrete wire, not twisted pairs (Unverified), so it is not the production pigtail.

## Floorplan model

Firmware branch `gho45-eth-header` changes `eth_header` to 15.95 x 8.0 x 2.0 mm at X 41-56.95, Y 1.5-9.5:

- Width 15.95 mm: housing over its locks, Molex drawing 5040510000-SD rev B, dimension A for 8 circuits. The header body is 15.75 mm (10.5 mm pin span plus 2 x 2.625 mm, from the KiCad footprint data, which cites Molex SD-504050-001).
- Height 2.00 mm mated (Molex). The housing alone is 1.92 mm.
- Depth 8.0 mm, assumed: the header is 6.10 mm deep and 6.61 mm with its signal pads (KiCad data from SD-504050-001), plus 1.39 mm of housing assumed beyond the header face. The housing is 6.40 mm long; how far it enters the header has not been checked against a Molex drawing.

The floorplan check passes with this box. The slot named in GHO-45 (about 12 x 5 mm at X 41-53, Y 2-7) is too small for any 8-position Pico-Lock: the header body alone is 15.75 x 6.61 mm.

## Open checks

- The mated depth and the header land pattern need Molex sales drawing SD-504050-001 and application spec AS-504051-001. Neither could be downloaded.
- The wires leave the housing toward +Y, at about Z 1 mm, straight at the USB hub 0.5 mm away. The model does not include the bend up into the pigtail zone above 3.5 mm. In a scratch run, moving the header to X 54-69.95, Y 1.5-9.5, with a 12 mm bend zone above it and the pigtail zone widened to X 40.5-69.95, also passed the check. That move changes D-025 and v1-reference.md §18, so it is for the project owner.
- The maximum insulation diameter that the 504052-0098 terminal accepts has not been checked against the chosen Cat5e or Cat6 conductor.
- Prices and stock are search snapshots. Recheck the live pages before ordering.
