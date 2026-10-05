# Track A: off-the-shelf POC part selections

## Expanded capability scope

The current capability contract is [Maer requirements](../requirements/maer-capabilities.md) (D-029 through D-032). This document describes the selected baseline and does not by itself demonstrate the expanded contract. GHO-50 owns POC hardware reconciliation; GHO-55 owns V1 impact and freeze disposition. 


Wiring, firmware revision, safety rules and arrival checks are in [bench-bom-and-topology.md](bench-bom-and-topology.md). The cross-track comparison is in [../hardware/v1-selections.md](../hardware/v1-selections.md#track-a-versus-track-b).

## Goal

Show HaLow mesh between nodes, Wi-Fi client access, GPS, and battery operation using purchased parts only, and collect the numbers a product design needs: power draw, heat, GPS coexistence, Wi-Fi mesh behavior, and run time. There is no custom PCB. Track A prioritizes testability over size, so the carrier is larger than a product would use. Finding an acceptable size is part of the POC, and compactness is a Track B problem.

## Parts register

This register owns which part fills each function and why. Every row is Selected. Order quantities, vendors, prices, buy links and order status live only in the Linear doc [OpenMANET POC — Purchase BOM](https://linear.app/ghostnet-labs/document/openmanet-poc-purchase-bom-ff58aa264535) and in [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36). The A-nn numbers match the rows of the retired Google BOM sheet. The first order buys two sets (D-015).

| ID | Function | Part | Notes |
|---|---|---|---|
| A-01 | Compute | Raspberry Pi CM5 Wireless, 4 GB RAM, 16 GB eMMC (CM5104016 / SC1594) | The wireless variant is kept as a spare service access point, not the main mesh radio. |
| A-02 | Carrier | Waveshare CM5-IO-WIRELESS-BASE, 145 x 90 mm (SKU 34618) | CM5 socket, Gigabit Ethernet, M.2 B-key with an included Mini-PCIe adapter, M.2 M-key, USB 3.2, two USB 2.0 ports plus a USB 2.0 header, RTC holder, GPIO terminal, fan header, and 7 to 36 V input. The size is acceptable because Track A prioritizes testability. Sold directly by Waveshare. |
| A-03 | CM5 service antenna | Raspberry Pi Compute Module 4/5 Antenna Kit (SC0480) | Optional external antenna for the CM5 wireless variant. Install it only if the CM5 radio is used, and set dtparam=ant2. The main mesh Wi-Fi remains the GW17032. |
| A-04 | HaLow radio | Gateworks GW16167, Morse Micro MM8108, M.2 2230 E-key, up to 26 dBm | Same second-generation MM8108 family and supported Morse software path as the Track B GW16170, and orderable from distribution. Worst-case RF, GNSS, and thermal testing must be repeated with the GW16170 before Track B is frozen. Gateworks marketplace shipping is a separate $42. |
| A-05 | HaLow carrier | Pier42 NGFF M.2 Simple Carrier A/E-Key, configured for E-key / 2230 | USB-connected carrier that lets the GW16167 attach to the CM5 carrier over USB 2.0. The price is converted from EUR and shipping is not included. |
| A-06 | Internal HaLow USB link | Adafruit 4472, USB-A to USB-C, 6 in (1 plus 1 spare) | Short USB 2.0 link from a Waveshare USB-A port to the Pier42 USB-C port. Verify there is no brownout during HaLow transmit. |
| A-07 | HaLow pigtail | GCT CAB724RF-0150-00-A-1, MMCX right-angle plug to SMA female bulkhead, RG178, 150 mm (1 plus 1 spare) | Matches the GW16167 MMCX port and keeps the card on a 900 MHz antenna path. |
| A-08 | HaLow antenna | Pulse W1063M, 868 to 928 MHz SMA-male whip (1 plus 1 spare) | The spare covers RF damage and debugging. |
| A-09 | Wi-Fi radio | Gateworks GW17032 / Compex WLE900VX, Mini-PCIe 3x3 Wi-Fi 5, QCA9880, ath10k | Gateworks recommends and has tested the WLE900VX for 802.11s mesh. It was meant to mount in the carrier's included Mini-PCIe adapter, but that adapter sits on the USB-only B-key slot, so the card can't work there ([bench-bom-and-topology.md §4.1](bench-bom-and-topology.md)). The replacement is the open decision on [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36). It is end of life with remaining stock, so it is a deliberate POC-only part and not a Track B candidate. Marketplace shipping applies. |
| A-10 | Wi-Fi pigtails | Digi JF1R6-CR3-6I, U.FL to RP-SMA female bulkhead, 6 in (3 plus 1 spare) | The card is 3x3 with three U.FL ports. The pigtails move all antennas outside the POC box and keep them movable. |
| A-11 | Wi-Fi antennas | Data Alliance ADD5RA, dual-band 2.4/5 GHz 5 dBi RP-SMA-male (3 plus 1 spare) | Keep placement movable during GPS coexistence tests. |
| A-12 | GPS | SparkFun GPS Breakout, chip antenna, SAM-M10Q, Qwiic (GPS-21834) | UART GNSS with a built-in SAW filter and LNA. Small, needs no USB port, and uses four short 3.3 V UART wires. |
| A-13 | GPS and UPS wiring | SparkFun PRT-11367, 22 AWG solid-core hookup wire assortment | Four wires for GPS (3.3 V, GND, UART TX, UART RX). SDA, SCL, and GND run from the UPS INA219 I2C header to the CM5 GPIO terminal. Keep them away from the 5 V power cable and verify the I2C address on arrival. |
| A-14 | UPS | Waveshare UPS Module 3S with 12.6 V charger and XH2.54-to-USB-C output cable (SKU 23884 / PiShop 1940) | Standalone 5 V at up to 5 A with its own charger and INA219 telemetry. Unplug it while flashing the CM5 over USB-C. See [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36) for the power-input question. |
| A-15 | UPS cells | Molicel INR-18650-M35A flat-top unprotected 18650 cells (3) | About 37 Wh nominal before UPS losses. Same cell baseline as Track B, but run time must still be measured. Do not mix old and new cells. Battery shipping restrictions apply. |
| A-16 | RTC battery | Panasonic CR1220 3 V coin cell, non-rechargeable | Fits the carrier RTC holder. Keep RTC charging off and do not add rtc_bbat_vchg. The rechargeable ML1220 is discontinued. |
| A-17 | Mounting hardware | Adafruit 3299 M2.5 nylon screw and standoff assortment, plus the hardware included with the UPS | Nonconductive mixed-height standoffs for the Pier42 carrier, GPS breakout, strain relief, and dry-fit stackups. Final lengths are chosen after the first fit-up. |
| A-18 | POC enclosure | Bud Industries PN-1324-C polycarbonate IP65 box, 171 x 121 x 55 mm, or an equivalent temporary lab enclosure | A lab and dry-fit box, not the Track B package. Drill antenna bulkhead holes only after a dry fit. |
| A-19 | Bring-up cable | Adafruit 4474, USB Type-A to Type-C, about 1 m | Host flashing and console bring-up for CM5 eMMC work. Keep it separate from the UPS power cable. The price is an estimate. |
| A-20 | Bring-up cable | Ethernet cable, Cat5e or Cat6 (assumed on hand) | Used for SSH and wired bring-up. |
| A-21 | Shipping | Gateworks/DigiKey marketplace flat shipping allowance, $42 | Should cover the Gateworks marketplace items if they are ordered together. Confirm in the cart. |

**Software.** The OpenMANET firmware tree (OpenWrt 24.10, Morse 2.x drivers) plus the CM5 board target ekh-bcm2712 from the ghostnet-labs/firmware fork (D-021). Hardware validation is tracked in [GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28).

## Expanded candidate register

These rows are **Candidate**, not Selected. They support the D-032 comparison and do not replace the baseline above. [Candidate integration and qualification](maer-hardware-qualification.md) owns wiring/source evidence and procedures; GHO-50 owns selection/qualification, GHO-57 exact SKU/environment/sourcing, and GHO-36 plus the Purchase BOM own all orders/prices/quantities.

| ID | Function | Candidate | Rationale / qualification boundary |
|---|---|---|---|
| A-22 | Networking compute | SolidRun CN9130 SoM | Separate carrier networking paths; exact grade/clock/RAM/eMMC and full workload remain gated by GHO-57/GHO-61. No new production compute selected. |
| A-23 | CN9130 carrier | SolidRun ClearFog CN9130 Pro | Two documented PCIe x1 slots, SATA, USB and native high-speed Ethernet; shipping revision/power and image integration remain GHO-56/GHO-58. |
| A-24 | Expanded DBDC Wi-Fi | AsiaRF AW7916-NPD, mini-PCIe MT7916 | Avoids an M.2 adapter for the Pro slots. [Manufacturer specification](https://asiarf.com/product/wi-fi-6e-mini-pcie-module-mt7916-aw7916-npd/) requests 3.3 V/3 A supply; published -10°C minimum does not establish required cold operation. Two-card four-PHY modes/power/environment require GHO-56/57/58. Not a replacement of V1 B-03. |
| A-25 | Alternative compute | Variscite DART-MX8M-PLUS | Auxiliary M7/NPU may help only workloads integrated for them; A53 application workload capacity must be measured under GHO-61. |
| A-26 | DART carrier | Variscite Sonata | DART integration candidate; bus/radio/receiver topology remains in GHO-50. Do not confuse this platform with the older MX95 study. |
| A-27 | Scanner receiver | SDRplay RSPduo | Independent dual capture is useful but limited in usable simultaneous bandwidth; GHO-60 maps actual systems and qualifies API/ARM64 dependencies. Not a frozen receiver BOM. |
| A-28 | CM5 comparison carrier | Raspberry Pi official Compute Module 5 IO Board | Controlled CM5 comparison baseline for D-032; the existing A-02 bench is a distinct configuration and must be labeled separately in results. |

## Physical notes

- The CM5 plugs directly into the CM5-IO-WIRELESS-BASE. The GW17032 mounts in the included Mini-PCIe adapter on the carrier. The GW16167 mounts on the Pier42 carrier, which connects to a Waveshare USB 2.0 port through the Adafruit 4472 cable. The SAM-M10Q mounts on short standoffs near the edge or top of the assembly and connects through the carrier's GPIO terminals after the pinout is verified.
- The 145 x 90 mm carrier is the primary mounting platform. The Pier42 carrier and the SAM-M10Q sit adjacent to it or on standoffs with short, strain-relieved cables, and the Waveshare UPS goes underneath or beside it. All antennas stay movable for RF and GNSS coexistence tests.
- Track A does not target MPU5-class packaging.

## Key technical trade-offs

**GPS next to the transmitters.** The SAM-M10Q tolerates about 0 dBm out-of-band at its antenna. With a target of at most about -6 dBm at the GPS, the required isolation is the transmit power plus 6 dB. Free-space estimates at 915 MHz: about 19 dB at 6 in (tolerates about 13 dBm of HaLow power), 25 dB at 1 ft (19 dBm), 30 dB at 1.6 ft (24 dBm), and 36 dB at 3.3 ft (the full 28.5 dBm). In a compact box the GPS cannot be far enough from the whip for full power. Options, in order: reposition the GPS, reduce HaLow transmit power in software, add a grounded copper-tape shield, or use an external active GPS antenna. Track A puts the GPS in the far corner and measures the limit with a HaLow power sweep (D-020).

**CM5 cooling.** Start with the CM5 bare, or with the standard low-profile passive cooler if available. Measure closed and loaded temperatures, and add active cooling only if required. Record the cooling configuration used for every power and thermal measurement.

## Ordering constraints

- Availability rule: every selected core component must be currently orderable in small quantities from its manufacturer or a major retailer. Gateworks Marketplace parts may have per-30-day purchase limits and additional shipping charges, so confirm that two of each part can be bought immediately before the two-node order.
- The accessory rows were refreshed on 2026-09-30: antenna paths, GPS and UPS wiring, the internal USB link, standoff hardware, the M35A cells, and the temporary enclosure. Final checkout must reconfirm live stock, marketplace shipping, and any purchase limits.
- The POC enclosure is a lab box. Drill or cut it only after the first physical fit check.

## Mounting plan

Moved from the BOM sheet's "Mounting & Enclosure" and "Physical Audit" tabs. Record standoff heights, hole locations, cable bends and GPS-to-radio spacing at the first dry fit.

| # | Component | Mounting / hardware | Notes | Status |
|---|---|---|---|---|
| 1 | Waveshare CM5-IO-WIRELESS-BASE (A-02) | Primary board on M2.5 standoffs inside the Bud box | The 145 x 90 mm carrier drives the enclosure footprint. Keep USB, Ethernet, GPIO terminal and RTC access reachable. | Dry-fit |
| 2 | CM5 module and optional cooler (A-01) | CM5 mounts on the carrier; cooler only if the thermal test needs it | Test bare first if height is tight. Track B should use enclosure conduction instead of a tall heatsink if possible. | Measure |
| 3 | GW16167 on Pier42 carrier (A-04, A-05) | Pier42 board mounted separately on nylon standoffs; short USB-A to USB-C cable to the carrier | Strain-relieve the USB cable and MMCX pigtail. Keep away from the GPS if possible. | Dry-fit |
| 4 | GW17032 / WLE900VX (A-09) | Waveshare's included Mini-PCIe adapter | Attach all three U.FL pigtails before transmit. Strain-relieve the pigtails near the card. | Dry-fit |
| 5 | HaLow SMA bulkhead (A-07) | GCT MMCX-to-SMA pigtail through the enclosure wall | Drill after radio placement. Keep the bend radius gentle and avoid pulling on the MMCX. | Pending holes |
| 6 | Wi-Fi RP-SMA bulkheads (A-10) | Three U.FL-to-RP-SMA bulkheads through the enclosure wall | Spread antennas for testing; final placement depends on GPS C/N0 data. | Pending holes |
| 7 | SAM-M10Q GPS breakout (A-12) | Small standoffs or adhesive mount, antenna face skyward | Far corner from the HaLow whip (D-020). | Dry-fit |
| 8 | UPS Module 3S (A-14, A-15) | Separate board with cells; use its included hardware and cable | Keep charger access and the power switch reachable. Never connect the UPS and the flashing host to the CM5 USB-C at the same time. | Dry-fit |
| 9 | Wire routing (A-13) | 22 AWG solid wire for GPS UART and UPS I2C | Short color-coded runs. Separate signal wires from the 5 V power cable where practical. | Build |
| 10 | Bud PN-1324-C enclosure (A-18) | Temporary lab enclosure / mounting plate | The IP rating no longer applies after drilling unless sealed glands are added. Not the Track B package. | Selected |
| 11 | CM5 service antenna (A-03) | Bulkhead on the enclosure wall | Only if the CM5 Wi-Fi is used; cable reach limits placement. | Optional |

## Selection risks

Moved from the BOM sheet's "Compatibility Review" tab.

| Area | Risk / action |
|---|---|
| Carrier (A-02) | Large for a product; Track B uses a custom carrier. |
| HaLow (A-04, A-05) | Power and current under transmit must be measured. |
| Wi-Fi (A-09) | EOL and not a Track B candidate; buy and verify quickly. |
| Wi-Fi antennas (A-10, A-11) | Never transmit with a missing antenna; strain-relieve the pigtails. |
| GPS (A-12) | RF coexistence must be measured near HaLow and Wi-Fi. |
| Power (A-14, A-15) | USB-C behavior and run time need bench verification. |
| RTC (A-16) | Charging must stay off in config.txt. |
| Enclosure (A-18) | Not waterproof after cuts unless sealed; not the Track B mechanical package. |
