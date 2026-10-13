# V1 Wi-Fi card alternatives (GHO-12)

**Owner:** [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12), fanless enclosure thermal paths. Card selection stays with B-03 in [v1-selections.md](v1-selections.md).
**Status:** Candidate, 2026-10-09. Desk research only. This file edits no record, selects no part and assigns no D, B or R number. Nothing was bought and no vendor was contacted. The owning records win (README rule 6).

## Why this exists

B-03 is the AsiaRF AW7916-AED (MediaTek MT7916, `mt7915e`, M.2 3052 A+E key). Wi-Fi mesh backhaul is a hard requirement (D-026). The thermal update on docs branch `gho12-thermal-tray` ([v1-thermal-update-tray.md](https://github.com/ghostnet-labs/docs/blob/gho12-thermal-tray/project/hardware/v1-thermal-update-tray.md), commit 7a572a7, not merged) puts the card at about 97 °C at the D-028 hot endpoint (43.3 °C ambient, 18.5 W, finned lid). AsiaRF rates the card −10 to +70 °C. That is about 27 K over.

This file looks for M.2 Wi-Fi 6/6E cards that run on mainline OpenWrt `mt76` and carry an industrial or extended temperature rating. It also checks what AsiaRF's 70 °C means.

## Tags

- **Verified:** read from the linked source on 2026-10-09. It is a fact about the source, not about a card on the bench.
- **Calculated:** derived here from Verified values or from the thermal update. The arithmetic is shown.
- **Unverified:** no primary source, a reseller or forum source, or a source that contradicts itself.

## Summary

- **No candidate meets both rules.** I found no M.2 card with an `mt76` chip (MT7915, MT7916, MT7981-class or MT799x) and an operating rating of +85 °C or higher. Every AsiaRF MT79xx M.2 card is rated −10 to +70 °C. (Verified, AsiaRF product pages)
- **The only MT79xx card with an extended rating is the Wallys DR7915.** It is MT7915 + MT7975, rated −40 to +70 °C. It is Mini PCIe, not M.2, so it does not fit the V1 socket. Its top limit is still 70 °C. (Verified, Wallys page)
- **Industrial M.2 cards that do exist use chips without 802.11s.** The Cervoz MEC-WIFI-2042B-30W (−40 to +85 °C) and the Quectel FME163R industrial grade use Realtek RTL8852, whose `rtw89` driver offers no mesh point. SparkLAN's −40 to +85 °C parts use Qualcomm client chips or SDIO. (Verified, vendor pages and kernel source)
- **Qualcomm QCN9074 has mesh point and industrial grades,** but it is not `mt76`. openmanetd's Wi-Fi backhaul runs only on MT7915/MT7916 (D-034). The industrial QCN9074 card found is Mini PCIe, and the M.2 one is 57 × 63 mm on 5 V. (Verified driver; card data partly Unverified)
- **AsiaRF does not say what 70 °C means.** The product page and the one-page datasheet give "Operating: −10 °C ~ +70 °C" with no ambient, case or junction note. No AW7916 variant has a wider rating. (Verified, 2026-10-09)
- **A higher rating alone would not close the gap.** An 85 °C card on today's 2.5 K/W pad still fails by about 12 K. It passes only with a pad path of 1.3 K/W or less. (Calculated, §4)
- **Recommended default: keep the AW7916-AED.** Ask AsiaRF what the 70 °C is measured on and whether an extended grade or screening exists. Bench-test the card's own die sensor at the hot endpoint. Keep the AsiaRF AW7915-AED as a pin-compatible, same-driver second source for supply, not for heat.

## 1. Sources

| ID | Source | Date or revision | Used for |
|---|---|---|---|
| S1 | AsiaRF [AW7916-AED product page](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) | Fetched 2026-10-09 | Temperature, power, TX power, heatsink, price, certification |
| S2 | AsiaRF [AW7916-AED datasheet](https://asiarf.com/wp-content/uploads/2026/07/260709_Datasheet_AW7916-AED_V1-1P.pdf) | File V1-1P, footer "Last Updated: 04/22/2026" | Features only. No temperature, power or pin data |
| S3 | AsiaRF [AW7916-AED pin-out drawing](https://asiarf.com/wp-content/uploads/2023/09/AW7916-AED_pins-out.jpg) | Uploaded 2023-09 | Pin comparison |
| S4 | AsiaRF [AW7916-AED bundle page](https://asiarf.com/product/wifi-6e-ax3000-module-aw7916-aed-package/) | Fetched 2026-10-09 | Temperature, power |
| S5 | AsiaRF [AW7916-NPD page](https://asiarf.com/product/wi-fi-6e-mini-pcie-module-mt7916-aw7916-npd/) and [NPD bundle page](https://asiarf.com/product/aw7916-npd-wi-fi-6e-ax3000-module-precision-coaxial-cables-and-wi-fi-7-antennas/) | Fetched 2026-10-09 | Temperature, FCC ID |
| S6 | AsiaRF [AW7915-AED product page](https://asiarf.com/product/wifi-6-11ax-m-2-ae-key-module-aw7915-aed/), [datasheet](https://asiarf.com/wp-content/uploads/2026/05/260505_Datasheet_AW7915-AED-1P.pdf), [pin-out drawing](https://asiarf.com/wp-content/uploads/2023/09/AW7915-AED_pins-out.jpg) | Fetched 2026-10-09; datasheet file 260505 | AW7915-AED data |
| S7 | AsiaRF [AW7915-AE1 product page](https://asiarf.com/product/wifi-6-11ax-m-2-ae-key-mt7915-aw7915-ae1/) and [datasheet](https://asiarf.com/wp-content/uploads/2026/05/260505_Datasheet_AW7915-AE1_1P.pdf) | Fetched 2026-10-09 | AW7915-AE1 data |
| S8 | AsiaRF [AW7915-BMD product page](https://asiarf.com/product/wifi-6-11ax-m-2-bm-key-module-mt7915-aw7915-bmd/) | Fetched 2026-10-09 | AW7915-BMD data |
| S9 | AsiaRF [AW7991-AE2 product page](https://asiarf.com/product/wifi-7-be5000-m-2-ae-key-module-aw7991-ae2/), [datasheet](https://asiarf.com/wp-content/uploads/2026/09/260921_Datasheet_AW7991-AE2_V1_1P.pdf), [pin-out drawing](https://asiarf.com/wp-content/uploads/2024/10/AW7991-AE2_pins-out-1.jpg) | Fetched 2026-10-09 | AW7991-AE2 data |
| S10 | Wallys [DR7915 product page](https://www.wallystech.com/Network_Card/DR7915-wifi6-MT7915-MT7975-2T2R-support-OpenWRT-802.11AX-supporting-MiniPCIe-Module.html) and [DR7915 PDF](https://www.wallystech.com/upload/DR7915-20230131(1).pdf) | Fetched 2026-10-09; PDF dated 2023-01-31 | DR7915 data |
| S11 | Cervoz [MEC-WIFI-2042B-30W product page](https://www.cervoz.com/products/industrial-wifi-m.2-pcie-expansion-card-MEC-WIFI-2042B-30W/detail) | Fetched 2026-10-09 | Industrial Realtek card |
| S12 | openwrt/mt76 at [467ae2e](https://github.com/openwrt/mt76/tree/467ae2e3f190baf737e15e318906da0dc7d0ab91): `mt7915/init.c`, `mt7915/pci.c`, `mt7915/mt7915.h`, `mt7996/init.c` | master head on 2026-10-09 | Mesh point, PCI IDs, thermal defaults |
| S13 | torvalds/linux at [af32da4](https://github.com/torvalds/linux/tree/af32da41b0327b9c6a37856ba82b6760d6c8d10e/drivers/net/wireless): `realtek/rtw89/core.c`, `ath/ath11k/core.c`, `ath/ath12k/wifi7/hw.c` | master head on 2026-10-09 | Mesh point for non-MediaTek chips |
| S14 | [WikiDevi mt76 page](https://wikidevi.wi-cat.ru/Mt76) | Fetched 2026-10-09 | Card list, FCC IDs (community source) |
| S15 | Search-result extracts only (pages not fetched): [SparkLAN WNFQ-291BEI](https://www.sparklan.com/wifi-7-industrial-capable-module-wnfq-291bei), [Quectel FME163R](https://www.quectel.com/news-and-pr/fme163r-wifi-bt-module-m2-2230-key-e-embedded-world-usa/), [Quectel FCU865R](https://www.quectel.com/product/wi-fi-bluetooth-fcu865r/), [Silex SX-PCEAX at Mouser](https://www.mouser.in/new/silex-technology/silex-tech-sx-pceax-wi-fi-6e-modules), [Compex WLE3000HX datasheet (Arrow copy)](https://static6.arrow.com/aropdfconversion/56afda2ba32f307a8a03f0c868b5250ecc6da0f6/wle3000hx.pdf), [Wallys DR9074-6E repost](https://bbs.21ic.com/icview-3237280-1-1.html) | Searched 2026-10-09 | Rejected or out-of-family options |
| S16 | ghostnet-labs/firmware branch 24.10 at 3ac1495, [`docs/hardware/v1-mechanical/parts.yaml`](https://github.com/ghostnet-labs/firmware/blob/24.10/docs/hardware/v1-mechanical/parts.yaml) | 2026-10-09 | Socket and card envelope |
| S17 | [v1-gpio-and-m2-audit.md](v1-gpio-and-m2-audit.md) §2 at docs main 53b0528 | 2026-10-09 | AW7916-AED pin table |

Not reachable from this session: fccid.io and the FCC EAS site (HTTP 403), the OpenWrt Table of Hardware pages (bot wall), 524wifi.net and 524wifi.com (HTTP 403), and the Compex catalogue on Arrow (empty reply). Data from those sites below is from search extracts and is tagged Unverified.

## 2. The V1 slot a replacement must fit

From S16 and S17 (Verified):

- **Socket:** TE 2199119-6, an M.2 **E-key** socket, at board X 92.05, Y 7.0. Card slot height 1.6 mm.
- **Card envelope:** 30 × 52 mm (type 3052), X 88 to 118, Y 10.9 to 62.9, antenna end toward the top wall. Card thickness 2.4 mm is assumed. No hold-down standoff is modelled yet.
- **Key:** an A+E-key card fits an E-key socket. A B-, M- or B+M-key card does not.
- **Carrier signals used:** 3.3 V (pins 2, 4, 72, 74), PCIe lane 0 (pins 35/37, 41/43), REFCLK (47/49), PERST# (52), CLKREQ# (53), PEWAKE# (55, pulled up, unused), W_DISABLE1# (56, WIFI_WDIS1_N). LEDs to test pads. USB (3/5), SDIO, UART, I2C, COEX and lane 1 are open.
- **Size fit for smaller cards:** a 2230 or 2242 card seats in the same socket but needs a standoff at 30 or 42 mm. That is a layout change, not a respin of the socket. A 3042 card would also need its own standoff.

The brief describes the card as "M.2 3052 M-key". The records and S16 say A+E key in an E-key socket. This file follows the records (see [Record conflicts](#record-conflicts)).

## 3. What AsiaRF's 70 °C means

- S1 lists "Temperature — Operating: −10°C ~ +70°C, Storage: −20°C ~ +90°C". There is no ambient, case, shield or junction qualifier. (Verified)
- S2, the datasheet, has no temperature line at all. (Verified)
- S4 (bundle) and S5 (Mini PCIe AW7916-NPD and its bundle) give the same −10 to +70 °C. (Verified)
- A search extract said the AW7916-NPD bundle was rated −20 to +85 °C. On the page, that line belongs to the bundled **antenna**, not the card. (Verified, S5 bundle page)
- AsiaRF's other MT79xx M.2 cards (AW7915-AED, AW7915-AE1, AW7915-BMD, AW7991-AE2) all give −10 to +70 °C operating. (Verified, S6 to S9)
- **No AW7916 variant with an industrial or extended rating was found.** AsiaRF's site says it builds "standard and custom form factors", but no extended-temperature SKU is listed. (Verified absence on 2026-10-09; whether AsiaRF would screen or build one is Unverified)

**What the driver tells us.** The `mt7915e` driver sets the MT7915/MT7916 firmware thermal protection at 110 °C (critical) and 120 °C (maximum) on the chip's own sensor, and exposes it as hwmon `temp1_input`, `temp1_crit`, `temp1_max` (S12, `mt7915.h` lines 82 to 85, Verified). So the chip's die limit is well above 70 °C. That makes it likely, not proven, that AsiaRF's 70 °C is a module or ambient rating set by board parts (crystal, FEMs, regulator) or by test conditions. It also means the die sensor can be logged on the bench. The 110 °C trip is a throttle, so D-028 forbids relying on it (R-21). (Inference; Unverified until AsiaRF answers)

**Heatsink.** S1 sells the AW7916-AED with a 30 × 30 × 10 mm heatsink in the listing ("Module: AW7916-AED ×1, Heatsink: 30x30x10mm ×1"). S6 to S8 offer a 30 × 30 × 4 mm aluminium heatsink as an add-on. No AsiaRF page gives a thermal resistance for either, or says whether the card has an RF shield can. (Verified listing; thermal data Unverified)

## 4. Does a higher rating close the gap?

Inputs from the thermal update (Calculated there, Unverified inputs): case 72.0 °C at 43.3 °C ambient, 18.5 W, finned lid, planning h. Card at 10 W. Pad 2.5 K/W (range 2 to 3). Internal air 77 to 87 °C.

| Card limit | Pad needed so card ≤ limit at a 72.0 °C case | Result at 2.5 K/W pad | Result at 1.0 K/W pad |
|---|---|---:|---:|
| 70 °C (AW7916-AED today) | (70 − 72.0) / 10 = negative; no pad works | −27 K | −12 K |
| 85 °C (industrial) | (85 − 72.0) / 10 = **1.3 K/W** | −12 K | +3 K |

(Calculated)

So an 85 °C card helps only together with a pad path of 1.3 K/W or less from the card's hot side to the lid. If the 85 °C were an **ambient** rating, internal air at 77 to 87 °C would sit at or just over it. (Calculated)

A cooler card would help more than a hotter rating. Each watt saved at 2.5 K/W is 2.5 K on the card and about 1.55 K on the case. No mt76 M.2 card found draws less than the AW7916-AED: the AW7915-AED and AW7915-AE1 list the same "9 W maximum, 4 to 8 W average" (S6, S7), and the AW7991-AE2 lists 15 W maximum (S9). (Verified)

## 5. Candidates

### 5.1 Comparison table

"Fits" means it seats in the V1 E-key 3052 socket without a carrier change. All data Verified from the source column on 2026-10-09 unless tagged.

| Card | Chip and driver | Form factor, key | Interface | Bands, streams | Max TX power (per chain, vendor table) | Power and supply | Operating temp | Heatsink or shield | 802.11s evidence | Price, availability | FCC ID | Fits V1 socket |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **AsiaRF AW7916-AED** (incumbent, B-03) [S1](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) | MT7916AN, `mt7915e` (PCI ID 14c3:7906) | M.2 3052, A+E key, 3 × IPEX | PCIe 2.1 x1 | 2.4 GHz 2T2R + 5 or 6 GHz 2T3R, 2 ss, DBDC | 2.4 GHz 23 dBm (11b), 21 dBm (11g); 5 GHz 20 dBm (HE20) | 3.3 V ±5 %. 10 W max, 8 W avg, "3.3V-3A minimum". Same page also says 9 W max, 4 to 8 W avg, 2.5 A minimum. 10 W at 3.135 V is 3.19 A (Calculated) | **−10 to +70 °C**, basis not stated | 30 × 30 × 10 mm heatsink in the listing; shield not stated | `mt7915/init.c` advertises MESH_POINT (S12). Not yet bench-proven on V1 ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)) | US$29.90 (1 to 99), US$28.00 (100+), AsiaRF direct. Stock not shown | Page shows placeholder "TKZXXXXXX-XXX"; certification block lists TKZAW7916-NPD (the Mini PCIe card). Unverified for the M.2 card | Yes (selected) |
| **AsiaRF AW7915-AED** [S6](https://asiarf.com/product/wifi-6-11ax-m-2-ae-key-module-aw7915-aed/) | MT7915DAN, `mt7915e` (14c3:7915) | M.2 3052 (52 × 30 mm), A+E key, 2 × IPEX | PCIe x1 | 2.4 + 5 GHz, 2T2R, DBDC. No 6 GHz | 2.4 GHz 23 dBm (11b), 20 dBm (11g); 5 GHz 19.5 dBm (11a) | 3.3 V. 9 W max, 4 to 8 W avg; 3 A, minimum 2.5 A | **−10 to +70 °C** | 30 × 30 × 4 mm heatsink sold separately | Same driver as B-03: MESH_POINT (S12). Not bench-proven | US$24.00, AsiaRF direct. Stock not shown | TKZAW7915-AED per WikiDevi (S14), Unverified | Yes. Pin-compatible (§5.3) |
| AsiaRF AW7915-AE1 [S7](https://asiarf.com/product/wifi-6-11ax-m-2-ae-key-mt7915-aw7915-ae1/) | MT7915AN, `mt7915e` | M.2 A+E key, 4 × IPEX. Length not re-read | PCIe x1 | 2.4 or 5 GHz 4T4R (2401 Mbps PHY) | Not re-read | 9 W max, 4 to 8 W avg; 3 A, min 2.5 A | **−10 to +70 °C** | 30 × 30 × 4 mm sold separately | MESH_POINT (S12) | US$24.00 | Not found | Needs 4 antennas; Unverified fit |
| AsiaRF AW7915-BMD [S8](https://asiarf.com/product/wifi-6-11ax-m-2-bm-key-module-mt7915-aw7915-bmd/) | MT7915DAN, `mt7915e` | M.2 **B+M key** | PCIe | 2.4 + 5 GHz 2T2R | Not re-read | 9 W max | −10 to +70 °C | Add-on | MESH_POINT (S12) | US$20.00, "80 in stock" | TKZAW7915-BMD per WikiDevi (S14), Unverified | **No** (wrong key) |
| AsiaRF AW7991-AE2 [S9](https://asiarf.com/product/wifi-7-be5000-m-2-ae-key-module-aw7991-ae2/) | MT7991A + MT7976C, `mt7996e` | M.2 A+E key, 3 × IPEX | PCIe 3.0, **x2** | 2.4 GHz 2T2R + 5 GHz 3T3R, Wi-Fi 7 | Not re-read | **15 W max**; 1.7 W standby, 8.6 W full iPerf | −10 to +70 °C | Not stated | `mt7996/init.c` advertises MESH_POINT (S12). openmanetd does not support this chip (D-034) | US$58.00 | Not found | Seats, but no W_DISABLE1 (§5.3) and over the 3.3 V rail budget |
| Wallys DR7915 [S10](https://www.wallystech.com/Network_Card/DR7915-wifi6-MT7915-MT7975-2T2R-support-OpenWRT-802.11AX-supporting-MiniPCIe-Module.html) | MT7915 + MT7975, `mt7915e` | **Mini PCIe**, 51 × 30 × 5.8 mm, 2 × U.FL | Mini PCIe 2.1 | 2.4 + 5 GHz 2T2R | 2.4 GHz 23 dBm, 5 GHz 20 dBm max | 3.3 V; "Power Consumption TBD" | **−40 to +70 °C** | Not stated | MESH_POINT (S12) | Price not published; quote from Wallys. Unverified | Not found | **No** (Mini PCIe) |
| Cervoz MEC-WIFI-2042B-30W [S11](https://www.cervoz.com/products/industrial-wifi-m.2-pcie-expansion-card-MEC-WIFI-2042B-30W/detail) | Realtek RTL8852BE, `rtw89` | M.2 2230, A+E key | PCIe 1.1 (Wi-Fi), USB 2.0 (BT) | 2.4 + 5 GHz 2T2R, Wi-Fi 6 | Not given | Not given | **−40 to +85 °C** ("Operation Temp."; basis not stated) | Not stated | **None.** `rtw89` interface modes are STATION, AP, P2P_CLIENT, P2P_GO (S13, `core.c` ~line 7516) | Not published | Not found | Seats with a 30 mm standoff; fails the mesh requirement |

### 5.2 Searched and rejected

| Vendor, part | Why rejected | Tag |
|---|---|---|
| Quectel FME163R (M.2 2230 E key, Realtek RTL8852, industrial −40 to +85 °C option) | `rtw89`, no mesh point (S13) | Card data from search extract, Unverified |
| Quectel FCU865R (FCU series) | LCC package, USB 2.0, 1T1R, −20 to +70 °C. Not M.2, not PCIe | Search extract, Unverified |
| SparkLAN WNFQ-291BEI (Qualcomm WCN7851, −40 to +85 °C) | `ath12k` WCN7850 entry lists no MESH_POINT (S13); client chip | Driver Verified; card data Unverified |
| SparkLAN WNFS-267AXI / WNFS-161AXI (Synaptics, −40 to +85 °C) | SDIO, not PCIe; no `mt76` | Search extract, Unverified |
| Silex SX-PCEAX (Qualcomm QCA2066, −20 to +65 °C) | Same chip family as the retired AIW-170BQ (R-19); `ath11k` QCA2066 lists no mesh point (S13); colder top limit | Driver Verified; card data Unverified |
| Compex WLE3000HX industrial grade (Qualcomm QCN9074, −40 to +85 °C) | `ath11k` QCN9074 does list MESH_POINT (S13). But it is Mini PCIe, not `mt76`, and openmanetd's backhaul needs MT7915/MT7916 (D-034). D-026 records QCN9074 Mini PCIe as out of stock until 2027 | Driver Verified; card data Unverified |
| Wallys DR9074-6E (QCN9074, M.2 E key) | 57 × 63 × 6 mm, 5 V supply, −20 to +70 °C (reposted datasheet) | Unverified |
| Wallys DR7916 | No such product found on wallystech.com or in search | Verified absence on 2026-10-09 |
| Gateworks | Its M.2 cards are HaLow. Its Wi-Fi 6 path is the Silex SX-PCEAX. No MediaTek card | Search, Unverified |
| Compex, 8devices, Senao/EnGenius, UNEX, JJPlus | No MediaTek MT79xx M.2 card found | Search, Unverified |
| MT7981 / MT7986-class on M.2 | These are router SoCs with built-in Wi-Fi. No M.2 card form exists | Verified (S14 chip list) |
| 524WiFi resold AsiaRF cards and 524WiFi MT7927 | Same AsiaRF hardware; MT7927 is a client chip (−10 to +70 °C) | Search extract, Unverified |

### 5.3 Pin compatibility against the V1 carrier

Compared finger by finger against S3 and the audit table (S17). The drawings print no pin numbers, so this is by finger order, as in the audit. (Verified against the drawings; pin numbers Unverified until a bench card is checked)

| Signal (V1 pin) | AW7916-AED (S3) | AW7915-AED (S6 drawing) | AW7991-AE2 (S9 drawing) |
|---|---|---|---|
| 3.3 V (2, 4, 72, 74) | Yes | Yes | Yes |
| PCIe lane 0, REFCLK, CLKREQ#, PEWAKE# (35 to 55) | Yes | Yes, same fingers | Yes, same fingers |
| PERST# (52) | Yes | Yes | Yes |
| W_DISABLE1# (56) | Yes | Yes | **Not connected** (X) |
| LED1 (6) / LED2 (16) | Both | LED1 only; LED2 finger is X | Both |
| USB D+/D− (3, 5) | X | **Labelled USB_D+/USB_D−** | X |
| PCIe lane 1 (top-side pins between 9 and 25) | X | X | **Lane 1 TX/RX present** |
| GNDX (69) | "GNDX" | "GNDX" | Not shown as GNDX |

- **AW7915-AED is a drop-in.** The carrier leaves pins 3 and 5 open, so the card's USB lines float. Nothing on V1 uses LED2. No carrier change. (Calculated from the drawings)
- **AW7991-AE2 is not a drop-in.** The CM5 has one lane, so the card would train at x1, which is fine. But WIFI_WDIS1_N would do nothing. At 15 W and the 3.135 V minimum it draws 15 / 3.135 = 4.78 A, above the 4.5 A WIFI_3V3 allocation (B-18), and it adds 5 W to a thermal model that already fails at 10 W. (Calculated)

## 6. Recommended default

**Keep the AsiaRF AW7916-AED (B-03) and run a bench test.** No `mt76` M.2 card with a higher rating exists in the market today, as far as this search could find. The two cards that seat in the socket and run the same driver (AW7916-AED, AW7915-AED) share the same 70 °C rating and the same power. A Qualcomm or Realtek card would trade the thermal problem for a mesh or software problem.

The steps that follow from it:

1. **Ask AsiaRF** (Justin's call; no vendor was contacted): what the 70 °C is measured on (ambient air, shield can, PCB); whether an extended or industrial grade, screening or a derating curve exists for the AW7916-AED; the heatsink's thermal resistance; whether the card has a shield can; and the FCC ID of the M.2 card.
2. **Bench-test the card hot.** In thermal test T4 (hot endpoint) and T6 (Wi-Fi pad A/B) of [v1-thermal-rf-plan.md](v1-thermal-rf-plan.md), log the MT7916 die sensor (`temp1_input` under the card's hwmon node) and `throttle1`, plus a thermocouple on the shield or the hottest part. Run sustained mesh traffic at full TX power. Pass means no throttle state, no link loss and a die reading with margin to the 110 °C trip. This turns the unknown "70 °C" into a measured margin.
3. **Treat the pad as the main lever.** §4 shows that even an 85 °C card needs a card-to-lid path of 1.3 K/W or less. The AsiaRF heatsink, a better pad, or a lid boss down to the card are worth sizing under [GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7) whatever card is used.
4. **Keep the AsiaRF AW7915-AED as a named second source.** Same vendor, same driver, same pins, same size. It drops 6 GHz and costs US$24.00. It is a supply backup, not a thermal fix.
5. **Hold the Wallys DR7915** as the only MT79xx part with a −40 °C lower limit. It would need a Mini PCIe socket. It fixes D-028's cold endpoint (−17.8 °C, below AsiaRF's −10 °C), not the hot one.

Switch to another card only if AsiaRF says the 70 °C is a die or shield limit with no extended grade, **and** the bench shows throttling at the hot endpoint. Even then there is no `mt76` M.2 card to switch to; the choice would be a QCN9074 card plus openmanetd work, or a Mini PCIe socket.

## Proposed record text

For the records owner to apply only if the project owner accepts. No IDs are assigned.

**[v1-selections.md](v1-selections.md) B-03, Status column, append:**
"Temperature: AsiaRF rates −10 to +70 °C operating with no ambient, case or junction basis (checked 2026-10-09). No `mt76` M.2 card with a wider rating was found ([v1-wifi-card-alternatives.md](v1-wifi-card-alternatives.md)). Second source: AsiaRF AW7915-AED (MT7915DAN, same driver and pins, no 6 GHz). Bench gate adds the MT7916 die temperature and throttle state at the D-028 hot endpoint (T4, T6)."

**[v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) §4, T4 and T6, add:**
"Log the MT7916 hwmon `temp1_input` and `throttle1` with a shield thermocouple under sustained full-power mesh traffic."

**[v1-thermal-rf-plan.md](v1-thermal-rf-plan.md) summary, B-03 risk bullet, add:**
"An 85 °C-rated card would still need a card-to-lid path of 1.3 K/W or less at the hot endpoint ([v1-wifi-card-alternatives.md](v1-wifi-card-alternatives.md) §4)."

## Decisions for the project owner

Each has a recommended default. **Any purchase or vendor contact is Justin's decision.** This file buys nothing and contacts no one.

1. **Card for V1.** (a) Keep the AW7916-AED and bench-test it hot; (b) switch now to a QCN9074 card and port the openmanetd backhaul; (c) redesign for a Mini PCIe socket and the Wallys DR7915. **Default: (a).** Nothing found beats it on rating within `mt76`.
2. **Vendor question to AsiaRF.** Ask what the 70 °C means and whether an extended grade exists (§6 step 1). **Default: ask.** It costs nothing and decides whether the bench test is the whole answer.
3. **Second source.** Name the AW7915-AED as an alternate for B-03, and buy one for the bench alongside the two AW7916-AED cards. **Default: name it; buying one is Justin's call** (US$24.00 at AsiaRF, recheck at checkout).
4. **Heatsink and pad.** Size the card-to-lid path for 1.3 K/W or less, and decide whether to use AsiaRF's 30 × 30 × 10 mm heatsink inside it. **Default: size it under GHO-7** before the lid design freezes.

## Record conflicts

Found, not resolved. README rule 6 asks for a Linear issue for each. This file opens none.

1. **Key type.** The brief calls the card "M.2 3052 M-key". D-026, B-03, S1 and the firmware floorplan (S16) say A+E key in an E-key socket. This file follows the records.
2. **FCC ID.** The AW7916-AED page shows a placeholder ("TKZXXXXXX-XXX") in its description and TKZAW7916-NPD (the Mini PCIe card) in its spec block. The audit notes the card photo label reads TKZAW7916-AED. Not checked against the FCC database, which was unreachable.
3. **Power.** The AW7916-AED page gives both "10 W max, 8 W average, 3 A minimum" and "9 W max, 4 to 8 W average, 2.5 A minimum". Already noted in v1-gpio-and-m2-audit.md conflict 8 and the thermal update conflict 7.
4. **Thermal update not on main.** §4 uses numbers from v1-thermal-update-tray.md on branch `gho12-thermal-tray` (7a572a7). If that file changes before merge, §4 must be rerun.

## What remains unverified

- What AsiaRF's 70 °C is measured on, and whether any extended grade exists. Needs AsiaRF.
- The FCC IDs of the AW7916-AED and AW7915-AED. WikiDevi gives TKZAW7915-AED; the FCC site was not reachable.
- AsiaRF stock levels for both M.2 cards. The pages show prices but no stock count.
- Whether the AW7916-AED has a shield can, and the heatsink's thermal resistance.
- Pin numbers for all three AsiaRF drawings (no numbers printed).
- 802.11s on any of these cards on V1 hardware. Driver support is Verified from source; a link is not (GHO-37).
- Every non-AsiaRF, non-Wallys, non-Cervoz figure in §5.2, which comes from search extracts.
- That no industrial MT79xx M.2 card exists. This is a negative search result. A vendor (AsiaRF, Wallys) might build one to order.
- All thermal inputs carried over from v1-thermal-update-tray.md (h values, pad resistance, internal air, 10 W sustained).
