# V1 carrier schematic net plan

**Owner:** [GHO-13](https://linear.app/ghostnet-labs/issue/GHO-13), complete and review the seven-sheet carrier schematic.  
**Status:** Planning record, 2026-10-09. This is not a schematic and releases nothing. GHO-13 is blocked by [GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9), [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10), [GHO-11](https://linear.app/ghostnet-labs/issue/GHO-11) and [GHO-35](https://linear.app/ghostnet-labs/issue/GHO-35), so no sheet has been drawn. This file lays out, sheet by sheet, the connections a schematic capture would follow, built only from what the records already fix. It names every open item and the ticket that owns it. It creates no decision, no D-number and no selection.

## How this file relates to the records

This file owns none of the facts it uses. If it disagrees with an owning record, the record wins, and the disagreement belongs in [Conflicts between records](#conflicts-between-records).

| Fact | Owner |
|---|---|
| Part selections (B-nn) and status | [v1-selections.md](v1-selections.md) |
| Decisions (D-nnn, R-nn) | [../decisions.md](../decisions.md) |
| CM5 physical pins, GPIO signal ownership, M.2 pin tables, sequencing | [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md) (the GPIO ledger). This file never restates a GPIO number for a signal; it uses the ledger's signal names as net names. |
| Sheet list | [v1-reference.md](v1-reference.md) §17 (the GHO-13 ticket text calls it "Handoff §26"; see conflict K-1) |
| Calculated values (eFuse, bucks, shunt, supervisor) | [v1-reference.md](v1-reference.md) §12 and §13, [v1-3v3-rail.md](v1-3v3-rail.md) |
| OpenVLM host port behavior | [v1-openvlm-usbc-power.md](v1-openvlm-usbc-power.md) |
| Routing and impedance | [v1-stackup-routing.md](v1-stackup-routing.md) (proposal, GHO-14/GHO-15) |
| Pack-swap bridge | [v1-hot-swap-bridge.md](v1-hot-swap-bridge.md) and B-24 (candidate) |

Candidate documents still in open pull requests were read from their branches on 2026-10-09. Anything taken from them is marked **(PR #nn, candidate)** and is not a record yet:

- `v1-eth-gnss-protection.md`, branch `gho11-eth-gnss`, [PR #57](https://github.com/ghostnet-labs/docs/pull/57) (GHO-11)
- `v1-bom-baseline.md`, branch `gho26-bom-baseline`, PR #61 (GHO-26)
- `v1-ethernet-header.md`, branch `gho45-eth-header`, PR #63 (GHO-45)
- `v1-battery-pack-gates.md`, branch `gho8-pack-gates`, PR #64 (GHO-8)

Datasheets checked for pin names on 2026-10-09:

| Part | Document |
|---|---|
| CM5 | [Raspberry Pi CM5 datasheet](https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf), Release 3, build 08/06/2026: Table 4 (pinout), §2.2 to §2.12, §3, §4.2.1, Table 13 |
| TUSB4041I | [TI SLLSEK3F](https://www.ti.com/lit/ds/symlink/tusb4041i.pdf), revised June 2026: Table 4-1, §5.6, §6.3.5, §6.3.7, §7.2.2, §7.3 |
| TPS22975 | [TI SLVSDD0B](https://www.ti.com/lit/ds/symlink/tps22975.pdf): Pin Functions |
| TPS386000 | [TI SBVS105F](https://www.ti.com/lit/ds/symlink/tps386000.pdf): Pin Functions, Electrical Characteristics |
| TPS26633RGER | [TI SLVSE94G](https://www.ti.com/lit/ds/symlink/tps2663.pdf): Table 5-1, VQFN-24 column |
| INA228 | [TI INA228](https://www.ti.com/lit/ds/symlink/ina228.pdf): Table 5-1, Table 7-2 |
| LM76005 | [TI SNVSBK5A](https://www.ti.com/lit/ds/symlink/lm76005.pdf): Pin Functions |
| MAX-M10S | [u-blox UBX-20035208 R08](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf): Table 10, Table 11 |

Not fetched, so no pin numbers are given for them: TPS25751A (package not recorded, PR #61 conflict C-9), BQ25798, LTC3350, GCT USB4720-03-A, the TE 2199119-6 socket, the Molex 504050-0891 land pattern, and every part still open.

## Conventions

- **Record** means the value or name comes from a merged project record. **Datasheet** means it was read from the manufacturer document above. **Proposed** means this file suggests it so capture has something concrete to start from; the owner can replace it. **Unverified** means nobody has checked it against a primary source or hardware. **Open** means no source exists and a ticket owns the answer.
- Net names that already appear in the records are used exactly as written. New names are listed once in [Proposed net names](#proposed-net-names) and are all Proposed.
- Pin numbers are part pin numbers, never BCM GPIO numbers, unless a column says otherwise.
- "TP_" prefixes test pads. Every test pad is internal: the product has no external debug connector (§4, §24).

## Proposed net names

These names are not in any record. They follow the ledger's style (upper case, `_N` for active low). The records name only the GPIO signals and the power rails listed in the next section.

| Group | Proposed names |
|---|---|
| CM5 USB 2.0 to hub upstream | USB_UP_DP, USB_UP_DM |
| Hub port 1 to HaLow card | USB_HALOW_DP, USB_HALOW_DM |
| Hub port 3 to OpenVLM host port | USB_VLM_DP, USB_VLM_DM (hub side), USB_VLM_C_DP, USB_VLM_C_DM (connector side of the ESD part), VLM_VBUS, VLM_CC1, VLM_CC2, HUB_PWRCTL3 |
| Hub support | HUB_1V1, HUB_3V3, HUB_XI, HUB_XO, HUB_VBUS_DET |
| PCIe | PCIE_TX_P, PCIE_TX_N, PCIE_RX_P, PCIE_RX_N (CM5 side of the 220 nF capacitors), PCIE_RX_C_P, PCIE_RX_C_N (card side), PCIE_REFCLK_P, PCIE_REFCLK_N, PCIE_RST_N, PCIE_CLKREQ_N, WIFI_PEWAKE_N, WIFI_LED1, WIFI_LED2 |
| Ethernet | ETH_TRD0_P/N to ETH_TRD3_P/N (CM5 to magnetics, PHY side), ETH_MDI0_P/N to ETH_MDI3_P/N (magnetics to header, line side), ETH_CT_PHY, ETH_CT_LINE |
| GNSS | GNSS_RF_IN, GNSS_ANT_FEED, GNSS_ANT_BIAS, GNSS_LNA_EN, GNSS_V_BCKP, GNSS_SAFEBOOT_N, GNSS_EXTINT, GNSS_SDA, GNSS_SCL |
| Battery and charge | VBAT_PACK (pack BAT+ contacts), PACK_SDA, PACK_SCL, PACK_SPARE, VBUS_SVC, SVC_CC1, SVC_CC2, SVC_DP, SVC_DM, VSYS_CHG, EFUSE_OUT, EFUSE_PGOOD, EFUSE_BGATE, EFUSE_DRV, BUCK_EN |
| Supervisor | SUP_SENSE1 to SUP_SENSE4, SUP_RESET1_N to SUP_RESET4_N, SUP_MR_N |

Names that do come from the records and are used as is: the ledger signal names, VBAT_PROTECTED, IN_SYS, +VBUS_HOLD, BRIDGE_ACTIVE_N and PACK_PRESENT (bridge study), SYS_PMIC_EN (§13 and the bridge study), +5V_SYS, +5V_CM5, +3V3_RADIO, WIFI_3V3, HALOW_3V3, +3V3_GNSS, CM5_3V3 (written "CM5 3.3 V" in the ledger), CHASSIS_GND, GND, ETH_SYNC_OUT, TP_ETH_SYNC, TP_PWR_BUTTON and TP_NBOOT.

## Inter-sheet ports

Each row is one hierarchical port. "Fixed" means a record fixes the connection, even if the parts at either end are still open.

| Net | Driven or sourced on | Used on | Fixed by |
|---|---|---|---|
| +5V_SYS | 06_POWER (LM76005 5 V) | 01 (as +5V_CM5), 03 (hub upstream detect, VLM_VBUS source), 07 (supervisor sense) | Record: B-18, §3 |
| +5V_CM5 | 06_POWER | 01_CM5 | Record: §4. Relation to +5V_SYS open (K-12) |
| +3V3_RADIO | 06_POWER (LM76005 3.3 V) | 06 (radio switches, GNSS filter), 07 (sense) | Record: B-18, [v1-3v3-rail.md](v1-3v3-rail.md) |
| WIFI_3V3 | 06_POWER (Wi-Fi TPS22975) | 02_PCIE_WIFI | Record: B-19, §5 |
| HALOW_3V3 | 06_POWER (HaLow TPS22975) | 03_USB_HALOW_AUDIO | Record: B-19, §7 |
| +3V3_GNSS | 06_POWER (filter from +3V3_RADIO) | 05_GNSS | Record: §9 |
| CM5_3V3 | 01_CM5 (pins 84, 86) | 01 (GPIO_VREF), 06 (INA228 VS), 07 (pull-ups, sense), 03 (HUB_3V3, Proposed) | Record: §4, §12 |
| VBAT_PROTECTED | 06_POWER | 06, 07 (SVS4 sense, see K-13) | Record: §3 |
| +VBUS_HOLD | 06_POWER (LTC3350, candidate) | 06 (buck inputs) | Candidate: B-24, bridge study §4 |
| GND | all | all | Record |
| CHASSIS_GND | 04, 05, 06 (connector shells) | wall bonds | Record: reserved (§10). Strategy open, GHO-11 |
| USB_UP_DP / USB_UP_DM | 01_CM5 | 03 | Record: ledger pins 103/105, §3 |
| PCIE_* (TX, RX, REFCLK, RST_N, CLKREQ_N) | 01_CM5 | 02 | Record: ledger, §6 |
| ETH_TRD0..3_P/N | 01_CM5 | 04 | Record: CM5 Table 4, §10 |
| ETH_SYNC_OUT | 01_CM5 | 04 (TP_ETH_SYNC) | Record: D-033 |
| SYS_I2C_SDA / SYS_I2C_SCL | 01_CM5 | 06 (INA228, charger, PD controller, bridge controller), 05 (optional), 06 (pack bus, open) | Record: ledger. Device list Proposed |
| GNSS_UART_TX, GNSS_UART_RX, GNSS_RESET_N, GNSS_PPS | 01_CM5 | 05 | Record: ledger |
| HALOW_PWR_EN, WIFI_PWR_EN | 01_CM5 | 06 (TPS22975 ON) | Record: ledger |
| HALOW_RESET_N, HALOW_WAKE_N | 01_CM5 | 03 (GW16170 pins 56, 54) | Record: ledger |
| WIFI_WDIS1_N | 01_CM5 | 02 (AW7916-AED pin 56) | Record: ledger |
| USB_HUB_RESET_N | 01_CM5 | 03 (TUSB4041I GRSTz) | Record: ledger |
| VLM_USB_FAULT_N | 03 | 01_CM5 | Record: ledger |
| HALOW_USB_FAULT_N | none | 01_CM5 | Record: ledger. No source (K-4) |
| HALOW_FAULT_N, WIFI_FAULT_N | none | 01_CM5 | Record: ledger says source unselected |
| SUPERVISOR_WDI, SUPERVISOR_WDO | 01 / 07 | 07 / 01 | Record: ledger |
| SYS_PMIC_EN | 07 (recovery path, open) | 01_CM5 pin 99 | Record: §13 |
| POWER_GOOD | 06 via a translator in 07 (open) | 01_CM5 | Record: ledger |
| EFUSE_FAULT | 06 (TPS26633 FLT) | 01_CM5 | Record: ledger |
| INA228_ALERT_N | 06 (INA228 ALERT) | 01_CM5 | Record: ledger |
| PACK_PRESENT, BRIDGE_ACTIVE_N | 06 | 01_CM5 | Candidate: bridge study. No GPIO allocated (K-19) |

---

## 01_CM5

**Scope (§17):** CM5, two Amphenol connectors, +5V_CM5, GPIO_VREF, PCIe, USB2, Ethernet, UART, I2C, PPS, PMIC_Enable, internal test pads.

**Parts:** B-01 (Raspberry Pi CM5008032 on 2 x Amphenol 10164227-1004A1RLF).

### CM5 connector pins

GPIO0 to GPIO27: every GPIO pin takes the net in the Signal column of the [canonical ledger](v1-pinout-and-sequencing.md#cm5-gpio-mux-facts), row for row. Rows marked Reserved are left unconnected. That table is the capture source, and this file does not copy it. Every pin that CM5 datasheet Table 4 names GND connects to GND, on both connectors (§4.2.1).

The remaining pins, from CM5 datasheet Table 4:

| CM5 pin | Datasheet name | Net | Source |
|---:|---|---|---|
| 12 / 10 | Ethernet_Pair0_P / _N | ETH_TRD0_P / _N, port to 04 | Datasheet; net name Proposed |
| 4 / 6 | Ethernet_Pair1_P / _N | ETH_TRD1_P / _N | Datasheet |
| 11 / 9 | Ethernet_Pair2_P / _N | ETH_TRD2_P / _N | Datasheet |
| 3 / 5 | Ethernet_Pair3_P / _N | ETH_TRD3_P / _N | Datasheet |
| 15, 17 | Ethernet_nLED3, Ethernet_nLED2 | No connect | Record: no LEDs (§4, §24) |
| 18 | Ethernet_SYNC_OUT | ETH_SYNC_OUT to TP_ETH_SYNC only | Record: D-033 |
| 16, 19 | Fan_Tacho, Fan_PWM | No connect (no fan, D-028/D-035) | Proposed |
| 20 | EEPROM_nWP | Open: float (boot EEPROM writable) or GND (write protected). Proposed: TP plus a DNP 0 Ω to GND | Open, GHO-9/GHO-19 |
| 21, 95 | LED_nACT, LED_nPWR | No connect | Record: §4. Optional TP on LED_nACT for boot error codes is Proposed |
| 57, 61 to 64, 67 to 70, 72, 73, 75 | SD_* | No connect (CM5Lite only; B-01 has eMMC) | Datasheet |
| 76 | VBAT (RTC) | Open: no RTC backup recorded | Open; PR #57 §2.5 says it needs its own issue |
| 77, 79, 81, 83, 85, 87 | 5V (Input) | +5V_CM5 | Record: §4 |
| 78 | GPIO_VREF | CM5_3V3 (must not float or go to GND) | Record: §4; Datasheet |
| 80 / 82 | SCL0 (GPIO39) / SDA0 (GPIO38) | No connect, unless chosen as a separate pack bus (open) | Proposed; GHO-8/GHO-9 |
| 84, 86 | CM5_3.3V (Output) | CM5_3V3 (600 mA total) | Datasheet |
| 88, 90 | CM5_1.8V (Output) | No connect; optional TP | Proposed |
| 89, 91 | WL_nDisable, BT_nDisable | No connect (no-wireless SKU) | Proposed |
| 92 | PWR_Button | TP_PWR_BUTTON (internal 10 kΩ pull-up to 5 V) | Record: §4 |
| 93 | nRPIBOOT | TP_NBOOT (internal 10 kΩ pull-up to CM5_3.3V) | Record: §4 |
| 94, 96 | CC1, CC2 | Open: records are silent. The CM5 uses them to negotiate 5 A from a USB-C supply; V1 feeds 5 V from a buck | Open, GHO-10/GHO-19 |
| 97, 100 | CAM_GPIO0, CAM_GPIO1 | No connect | Proposed |
| 99 | PMIC_Enable | SYS_PMIC_EN (internal 100 kΩ pull-up to 5 V, so every driver must be open drain) | Record: §4, §13; Datasheet |
| 101 | USB_OTG_ID | Open. The datasheet says tie to GND for a fixed host role, which the hub needs. That blocks device mode for B-07 service and rpiboot (K-3) | Open, GHO-9/GHO-11 |
| 102 | PCIe_CLK_nREQ | PCIE_CLKREQ_N (must be connected) | Record: ledger; Datasheet §2.3.2 |
| 103 / 105 | USB_N / USB_P | USB_UP_DM / USB_UP_DP, port to 03 | Record: ledger |
| 104 | PCIE_nWAKE | No connect (unsupported in software) | Record: §6 |
| 106 | PCIE_PWR_EN | No connect, optional TP. Wi-Fi power uses WIFI_PWR_EN instead | Proposed; GHO-9 to confirm |
| 109 | PCIe_nRST | PCIE_RST_N | Record: ledger |
| 110 / 112 | PCIe_CLK_P / _N | PCIE_REFCLK_P / _N | Record: ledger |
| 111 | VBUS_EN | No connect (USB 3.0 unused) | Proposed |
| 116 / 118 | PCIe_RX_P / _N | PCIE_RX_P / _N | Record: ledger |
| 122 / 124 | PCIe_TX_P / _N | PCIE_TX_P / _N (AC coupling is on the CM5) | Record: ledger |
| 115 to 200, other | MIPI0/1, USB3-0, USB3-1, HDMI0/1 | No connect | Proposed: none of these interfaces is in V1 |

### Defaults and rules on this sheet

- All CM5 GPIO run at 3.3 V (GPIO_VREF on CM5_3V3). Total GPIO load at most 50 mA (datasheet §2.9).
- RP1 internal pulls are 37 to 86 kΩ (up) and 35 to 98 kΩ (down) at 3.3 V (datasheet §4.3). The default pull of each GPIO at reset is not in the CM5 datasheet: **Unverified**, owned by GHO-9/GHO-19. Every carrier default below is set by an external resistor so it holds before firmware runs.
- SYS_I2C has 1.8 kΩ pull-ups on the CM5 (datasheet §2.9). Proposed: no extra carrier pull-ups on SYS_I2C_SDA/SCL.
- The CM5 must see no external voltage on any pin while it is powered down (datasheet §4.2.1). Every port from an always-on domain into this sheet needs a check against that rule (K-7).
- USB 2.0 needs `dtoverlay=dwc2,dr_mode=host` (datasheet §2.4.2). This is a firmware item for GHO-19, recorded here because capture of USB_OTG_ID depends on it.

### Test pads

TP_PWR_BUTTON, TP_NBOOT (Record). Proposed: TP on +5V_CM5, CM5_3V3, SYS_PMIC_EN, SYS_I2C_SDA, SYS_I2C_SCL, and a GND pad next to each group. The CM5 debug UART is only on the module's own test points TP35/TP36 (datasheet Table 13), not on the connector, so the carrier cannot route it (K-3).

---

## 02_PCIE_WIFI

**Scope (§17, D-026):** AW7916-AED, M.2 socket, PCIe Gen2 x1, 100 MHz REFCLK, PERST#, CLKREQ#, 220 nF capacitors on the card TX, Wi-Fi switch sized for at least 3 A, three IPEX.

**Parts:** B-03 (AsiaRF AW7916-AED, M.2 3052 A+E), TE 2199119-6 socket (no B-ID; mechanical reference only, not a released Wi-Fi power connector, [v1-3v3-rail.md](v1-3v3-rail.md)), 2 x 220 nF (0201 or 0402, [v1-stackup-routing.md](v1-stackup-routing.md) §4), WIFI_3V3 bulk: 2 x 22 µF X7R plus 100 µF low-ESR polymer at the socket (Record, [v1-3v3-rail.md](v1-3v3-rail.md)). B-21 Wi-Fi antennas are three IPEX on the card; the carrier has no RF trace for them (§19).

The Wi-Fi TPS22975 is drawn on 06_POWER in this plan, with WIFI_3V3 as a port. §17 lists it on both sheets (K-2).

### AW7916-AED socket pins

Pin numbers come from the ledger's [AW7916-AED table](v1-pinout-and-sequencing.md#aw7916-aed-m2-signals), which reads them from finger order. They are **Unverified** until a bench card is checked (GHO-9).

| M.2 pin | Card signal | Net | Default |
|---:|---|---|---|
| 2, 4, 72, 74 | 3.3 V | WIFI_3V3 | Off while WIFI_PWR_EN is low |
| 1, 7, 18, 33, 39, 45, 51, 57 and every other GND pin | GND | GND | |
| 35 / 37 | PERp0 / PERn0 (host TX) | PCIE_TX_P / _N | |
| 41 / 43 | PETp0 / PETn0 (host RX) | PCIE_RX_C_P / _N, then 220 nF in series to PCIE_RX_P / _N | Capacitors next to the socket |
| 47 / 49 | REFCLKp0 / REFCLKn0 | PCIE_REFCLK_P / _N | |
| 52 | PERST0# | PCIE_RST_N | CM5 holds it low until clock and reset timing is valid (ledger sequence step 5) |
| 53 | CLKREQ0# | PCIE_CLKREQ_N | CM5 has an internal pull-up |
| 55 | PEWAKE0# | WIFI_PEWAKE_N: 10 kΩ pull-up to WIFI_3V3 and TP_WIFI_PEWAKE | Record |
| 56 | W_DISABLE1# | WIFI_WDIS1_N: 10 kΩ pull-up to WIFI_3V3 | Record. The CM5 side is open drain only, never driven high |
| 54 | W_DISABLE2# (not connected on the card) | No connect | Record |
| 6 / 16 | LED1 / LED2 | TP_WIFI_LED1, TP_WIFI_LED2 | Record |
| 3, 5 and all others | not connected (no USB) | No connect | Record |

### Rules carried into capture

- PCIe pairs: P and N may swap within a pair (CM5 datasheet §2.3.1). Intra-pair match 0.1 mm. Impedance target 90 Ω (CM5) or 85 Ω (M.2) is open for GHO-15 ([v1-stackup-routing.md](v1-stackup-routing.md) §3).
- Pull-ups return to WIFI_3V3 so nothing back-feeds the card while it is off (ledger).
- **Unverified:** while WIFI_3V3 is off, the CM5 still drives PCIE_RST_N and pulls PCIE_CLKREQ_N up to CM5 3.3 V. Whether that back-feeds the unpowered card through pins 52 and 53 is not checked. GHO-9 owns sequencing.

### Test pads

TP_WIFI_PEWAKE, TP_WIFI_LED1, TP_WIFI_LED2 (Record). Proposed: TP on WIFI_3V3 at the socket (for the drop measurement in [v1-3v3-rail.md](v1-3v3-rail.md)) and on PCIE_RST_N.

---

## 03_USB_HALOW_AUDIO

**Scope (§17, D-023, D-026, GHO-13):** TUSB4041I with a 24 MHz crystal, CM5 USB2 upstream, GW16170 on port 1, port 2 spare, the external OpenVLM USB-C host (DFP) on port 3, port 4 reserved, switched and current-limited VBUS, CC termination, USB ESD, hub reset and per-port overcurrent. "AUDIO" means the host port only: no CM108B, no analog microphone or speaker circuit and no PTT switch on the carrier (D-023).

**Parts:** B-04 (TI TUSB4041IPAPRG4, 64-HTQFP), B-02 (Gateworks GW16170) in a TE 2199119-6 socket (no B-ID; key type not recorded, PR #61 conflict C-11), B-23 (GCT USB4720-03-A) for the OpenVLM host port. Open parts: 24 MHz crystal, HUB_1V1 regulator (K-9), port-3 CC controller and VBUS switch (O-1, O-2 in PR #61), USB ESD (O-3). B-22 is the external accessory and has no carrier footprint.

### TUSB4041I pins (datasheet SLLSEK3F Table 4-1)

| Pin | Name | Net | Default or strap |
|---:|---|---|---|
| 21 / 22 | USB_DP_UP / USB_DM_UP | USB_UP_DP / USB_UP_DM | No P/N swap on USB 2.0 |
| 16 | USB_VBUS | HUB_VBUS_DET: 90.9 kΩ 1 % from the upstream VBUS, 10 kΩ 1 % to GND | Datasheet divider. Upstream is the CM5, which has no VBUS pin; Proposed source +5V_SYS, **Unverified** |
| 32 | USB_R1 | 9.53 kΩ 1 % to GND | Datasheet |
| 30 / 29 | XI / XO | HUB_XI / HUB_XO: 24 MHz fundamental crystal, 1 MΩ across XI-XO, load capacitors per the crystal (TI example 18 pF) | Datasheet §6.3.5: 12 to 24 pF load, ±100 ppm or better, ESR ≤ 50 Ω. Part open |
| 18 | GRSTz | USB_HUB_RESET_N | Proposed: external pull-down so the hub stays in reset until firmware releases it. It must overcome the internal pull-up; value **Unverified**. Release at least 3 ms after VDD and VDD33 are stable (§5.6) |
| 33 / 34 | USB_DP_DN1 / USB_DM_DN1 | USB_HALOW_DP / USB_HALOW_DM | Port 1 |
| 41 / 42 | USB_DP_DN2 / USB_DM_DN2 | No connect | Port 2 spare (D-026) |
| 49 / 50 | USB_DP_DN3 / USB_DM_DN3 | USB_VLM_DP / USB_VLM_DM | Port 3 |
| 56 / 57 | USB_DP_DN4 / USB_DM_DN4 | No connect | Port 4 reserved (D-023) |
| 4 | PWRCTL1/BATEN1 | No connect (internal pull-down: no battery charging) | Port 1 has no VBUS switch: the HaLow card takes HALOW_3V3 |
| 3 | PWRCTL2/BATEN2 | No connect | |
| 1 | PWRCTL3/BATEN3 | HUB_PWRCTL3, the hub's permission input to the port-3 enable logic | Must read low at reset (battery charging not supported) and must not be pulled up by the attach logic ([v1-openvlm-usbc-power.md](v1-openvlm-usbc-power.md)) |
| 64 | PWRCTL4/BATEN4 | No connect | |
| 14, 15, 11 | OVERCUR1z, OVERCUR2z, OVERCUR4z | No connect (internal pull-up reads "no fault") | Datasheet allows it |
| 12 | OVERCUR3z | VLM_USB_FAULT_N (shared with the CM5 input) | Low = fault |
| 8 | FULLPWRMGMTz/SMBA1 | Pull-down (or the internal pull-down): power switching and overcurrent inputs supported | Proposed. TI advises a resistor, not a hard tie |
| 10 | GANGED/SMBA2/HS_UP | Pull-down: individual port power | Proposed; required so a port-3 fault cannot drop HaLow ([v1-openvlm-usbc-power.md](v1-openvlm-usbc-power.md)) |
| 9 | PWRCTL_POL | Internal pull-up: PWRCTL active high | Proposed; must match the chosen port-3 enable logic |
| 7 | SMBUSz | Pull-up resistor (I2C mode, no EEPROM fitted) | Proposed; no hub EEPROM (§24) |
| 5 / 6 | SDA/SMBDAT, SCL/SMBCLK | No connect | No EEPROM, no SMBus host |
| 13 | AUTOENz/HS_SUSPEND | No connect (internal pull-up: automatic charge mode off) | Proposed |
| 17 | TEST | GND or no connect per the TI reference design | **Unverified** which the reference uses |
| 19, 25, 37, 45, 53, 60, 63 | VDD (1.1 V core) | HUB_1V1 (0.99 to 1.26 V), 0.1 µF per pin, 10 µF bulk, optional ferrite under 0.05 Ω | Datasheet. Regulator not in any record (K-9) |
| 2, 20, 31, 48 | VDD33 | HUB_3V3, 0.1 µF per pin, 10 µF bulk | Proposed source CM5_3V3, so the hub, its reset and the upstream pair share the CM5 power domain. **Unverified**; GHO-10 |
| 23, 24, 26, 27, 35, 36, 38, 39, 43, 44, 46, 47, 51, 52, 54, 55, 58, 59, 61, 62 | RSVD | No connect | Datasheet |
| 28, 40 | NC | No connect | Datasheet |
| PAD | Thermal pad | GND through vias | Datasheet |

Straps (FULLPWRMGMTz, GANGED, PWRCTL_POL, SMBUSz, BATEN1 to 4, AUTOENz) are sampled when GRSTz rises (§5.6). The bias network on each must hold its level then.

### GW16170 socket pins (Gateworks wiki, Record)

| M.2 pin | Card signal | Net | Default |
|---:|---|---|---|
| 2, 4, 72, 74 | 3.3 V | HALOW_3V3 | Off while HALOW_PWR_EN is low |
| 3 / 5 | USB D+ / D- | USB_HALOW_DP / USB_HALOW_DM | |
| 56 | W_DISABLE1# to module RESET_N, 200 kΩ pull-up on the card | HALOW_RESET_N | Open drain from the CM5: low asserts, input releases, never driven high |
| 54 | W_DISABLE2# to module WAKE, 10 kΩ pull-up on the card | HALOW_WAKE_N | Same rule |
| GND pins | GND | GND | Standard M.2 E-key GND positions; Gateworks does not list them: **Unverified** |
| PCIe, PERST#, CLKREQ#, PEWAKE#, others | not documented | No connect | Record (§7) |

The card does not enumerate while either control pin is held low (§7).

### Port 3: OpenVLM USB-C host (B-23)

The behavior is fixed by [v1-openvlm-usbc-power.md](v1-openvlm-usbc-power.md); the parts are not. Capture must implement:

`PORT_ENABLE = HUB_ALLOW AND ATTACHED_SRC AND SUPPLY_GOOD AND NOT FAULT_LATCH`

| Function | Net plan | Status |
|---|---|---|
| Hub permission | HUB_PWRCTL3 (active high with PWRCTL_POL high) into the enable logic | Fixed in behavior, logic open |
| Source termination (Rp) and attach detection | VLM_CC1, VLM_CC2 from the B-23 receptacle to the CC controller. Option A: TUSB320LAI in fixed DFP (PORT high), open-drain ID low on attach. Option B: TPS25810 integrated DFP and switch | Open, GHO-11 (O-2) |
| Switched, current-limited VBUS | +5V_SYS through the switch to VLM_VBUS. Option A: TPS2553 (active-high EN, active-low FAULT, adjustable limit). Option B: TPS25810. 22 µF or more low-ESR bulk on VLM_VBUS, plus a ferrite and 0.1 µF at the connector (TUSB4041I §7.3.2) | Open, GHO-11 (O-1); current budget GHO-10 |
| Overcurrent signal | Switch FAULT (open drain) to VLM_USB_FAULT_N, which joins OVERCUR3z and the CM5 input. One pull-up, in a domain that is powered whenever either reader is (Proposed: HUB_3V3 if that is CM5_3V3) | Net Record (D-024), pull-up domain open |
| VBUS discharge on detach or fault | Required | Open, GHO-11 |
| USB data ESD | Low-capacitance array between the B-23 pins and USB_VLM_DP/DM, at the connector. Also VBUS and CC protection | Open, GHO-11 (O-3) |
| Shell | Bond to the enclosure wall (PR #57 §3, candidate); CHASSIS_GND strategy open | Open, GHO-11 |

B-23 receptacle pin numbers are not given: the GCT drawing was not checked. Route B-23 separately from B-07: no shared net except GND and the chassis bond (D-023, §8). The VLM never connects to the charge and service port.

### Test pads

Proposed: TP on HUB_1V1, HUB_3V3, USB_HUB_RESET_N, VLM_VBUS, VLM_CC1, VLM_CC2, VLM_USB_FAULT_N and HALOW_3V3. TP on the spare port 2 and 4 pairs is not proposed (stubs on 480 Mb/s lines).

---

## 04_ETHERNET

**Scope (§17):** CM5 PHY interface, discrete 1000BASE-T magnetics, sealed connector path, four MDI pairs, Ethernet ESD, chassis and shield, ETH_SYNC_OUT. No external PHY, no PoE, no Ethernet LEDs (D-022, §24).

**Parts:** B-06 (Molex Pico-Lock 504050-0891 header, 504051-0801 housing and 504052-0098 terminals on the pigtail; RCP-5SPFFH-SCU7001 feed-through and cap in the wall). Open: the magnetics, 3.5 mm tall or less (D-025, O-9 in PR #61). Candidate (PR #57): two TI TPD4EUSB30 on the PHY side, PHY-side centre taps tied with 100 nF to GND, Bob Smith network on the line side (4 x 75 Ω to one 1000 pF high-voltage capacitor to CHASSIS_GND).

### Signal path

CM5 pins → ETH_TRDn (100 Ω, matched 0.15 mm) → PHY-side ESD at the magnetics → magnetics channel n → ETH_MDIn (line side, isolated, no logic ground under it) → header.

| CM5 pins (P / N) | PHY side net | Magnetics | Line side net | Header pins (Record, §10) | Pigtail RJ45 pins, T568B (Proposed) |
|---|---|---|---|---:|---|
| 12 / 10 | ETH_TRD0_P / _N | channel 0 | ETH_MDI0_P / _N | 1 / 2 | 1 / 2 |
| 4 / 6 | ETH_TRD1_P / _N | channel 1 | ETH_MDI1_P / _N | 3 / 4 | 3 / 6 |
| 11 / 9 | ETH_TRD2_P / _N | channel 2 | ETH_MDI2_P / _N | 5 / 6 | 4 / 5 |
| 3 / 5 | ETH_TRD3_P / _N | channel 3 | ETH_MDI3_P / _N | 7 / 8 | 7 / 8 |

The pigtail column is Proposed. It assumes CM5 pair n is IEEE 802.3 pair A to D in order, as on a standard MagJack, and that the odd header pin is the positive line. Neither is in a record; IEEE 802.3 was not fetched. The PHY corrects crossover and pair polarity (CM5 datasheet §2.2), which tolerates some errors but is not a reason to leave the map undefined. GHO-45 owns the pigtail drawing.

### Defaults and rules

- The header carries only MDI pairs; it has no ground and no spare pin for a shield (§10; PR #57 conflict 6).
- The magnetics module's isolation spacing sets the line-side keep-out ([v1-stackup-routing.md](v1-stackup-routing.md) §4). Part open.
- No TVS from a line-side conductor to logic ground (PR #57 §1.2, candidate).
- ETH_SYNC_OUT goes to TP_ETH_SYNC only, with no connection to any GPIO or to GNSS_PPS (D-033).

### Test pads

TP_ETH_SYNC (Record). No pads on the MDI lines (Proposed: they are 100 Ω pairs and the header is the probe point).

---

## 05_GNSS

**Scope (§17):** MAX-M10S-00B, UART, I2C, PPS, reset, VCC_RF, active antenna, optional RF protection and filter footprints, backup provision, test pads.

**Parts:** B-05 (u-blox MAX-M10S-00B). Open: B-21 GNSS antenna connector (GHO-11). Candidates (PR #57): TPS2553 antenna-bias limiter, 27 nH and 10 nF feed network, 0.33 to 0.47 F backup supercapacitor with Schottky and series resistor, DNP RF ESD footprint, 0 Ω SAW-filter footprint behind 47 pF.

### MAX-M10S pins (datasheet R08 Table 10)

| Pin | Name | Net | Default |
|---:|---|---|---|
| 1, 10, 12 | GND | GND | |
| 2 | TXD (PIO1) | GNSS_UART_RX (the CM5 receives) | Output in continuous mode |
| 3 | RXD (PIO0) | GNSS_UART_TX (the CM5 transmits) | Input with pull-up |
| 4 | TIMEPULSE (PIO4) | GNSS_PPS, plus TP_GNSS_PPS | Shared with SAFEBOOT_N through 1 kΩ inside the module (K-8) |
| 5 | EXTINT (PIO5) | GNSS_EXTINT to TP_GNSS_EXTINT | Record (§9). PR #57 would use this PIO as ANT_SHORT_N (K-11) |
| 6 | V_BCKP | GNSS_V_BCKP | Record: reserved, storage not selected. PR #57 candidate: supercapacitor |
| 7 | V_IO | +3V3_GNSS | |
| 8 | VCC | +3V3_GNSS | |
| 9 | RESET_N | GNSS_RESET_N | Internal pull-up; low at least 1 ms resets. A reset clears battery-backed RAM |
| 11 | RF_IN | GNSS_RF_IN | 50 Ω on L1, no vias ([v1-stackup-routing.md](v1-stackup-routing.md) §4) |
| 13 | LNA_EN | GNSS_LNA_EN | Record: no use. PR #57 candidate: enables the antenna-bias switch, with a pull-down |
| 14 | VCC_RF | GNSS_ANT_BIAS (Record §9: antenna bias), or unused if PR #57's limited switch is chosen | K-10 |
| 15 | VIO_SEL | No connect (open selects 3.3 V V_IO) | Datasheet |
| 16 / 17 | SDA / SCL (PIO2/3) | GNSS_SDA / GNSS_SCL, joined to SYS_I2C_SDA / SCL through DNP 0 Ω links | Proposed: I2C is secondary (§9), and these pins have internal pull-ups to the GNSS rail, which stays powered when the CM5 is off (K-7) |
| 18 | SAFEBOOT_N | GNSS_SAFEBOOT_N to TP_GNSS_SAFEBOOT | Record (§9). Leave otherwise open |

### Antenna path

Connector (open) → optional DNP RF ESD at the connector → bias injection (feed inductor and DC block) → optional 0 Ω or SAW footprint → GNSS_RF_IN. Do not populate a generic TVS (§9, §30 rule 13). Whether the SAW is fitted follows GHO-12 tests T9 and T11 (PR #57).

### Defaults and rules

- No GNSS power switch: +3V3_GNSS is always on while +3V3_RADIO is on (§9, §24). That makes this sheet an always-on domain relative to the CM5 (K-7).
- In hardware backup mode the PIOs must not be driven (datasheet Table 11 note). Firmware must not pulse GNSS_RESET_N on every boot if the backup is wanted (PR #57).

### Exposed timing signal

GNSS_PPS: TIMEPULSE pin 4 → (Proposed: series resistor footprint at the module) → TP_GNSS_PPS → the CM5 PPS input in the ledger. It is not connected to ETH_SYNC_OUT (D-033, §24).

### Test pads

TP_GNSS_SAFEBOOT, TP_GNSS_EXTINT (Record §9), TP_GNSS_PPS (Proposed; GHO-13 asks for PPS to be exposed), TP on +3V3_GNSS and GNSS_V_BCKP (Proposed).

---

## 06_POWER

**Scope (§17):** battery contacts, 10 mΩ shunt, INA228, SMBJ33CA, CSD19533Q5A, Q2 pull-down FET, TPS26633, LM76005 5 V, LM76005 3.3 V, two TPS22975, GNSS filtering, protection, fault and telemetry. The charge path (B-07, B-08, B-09) and the bridge (B-24) are not in the §17 list but sit in this power path (§11, bridge study §4), so this plan places them here (K-2).

**Parts:** B-12 contact interface, B-17 (candidate), B-16 (candidate), Q2 BSS138 or equivalent (candidate), B-15, B-14 (INA228 and shunt), B-18 x 2, B-19 x 2, B-07, B-08, B-09, B-24 (candidate). Pack-side parts B-10, B-11 and B-13 are not on the carrier.

### Power chain

The order is not settled (GHO-10; PR #61 conflict C-15). The two recorded versions:

| Source | Order |
|---|---|
| §3 and §20 | Contacts → SMBJ33CA → CSD19533Q5A → TPS26633 → shunt (INA228) → VBAT_PROTECTED → both LM76005 |
| §11 and bridge study §4 (newer) | Contacts (VBAT_PACK) → BQ25798 BAT to SYS (VSYS_CHG) → TVS, Q1, TPS26633 → shunt → VBAT_PROTECTED → LTC3350 input ideal diode → +VBUS_HOLD → both LM76005 |

Capture of the input stage waits for GHO-10. The tables below give the pins that do not depend on that choice.

### Battery contact interface (B-12, M-11)

| Contact (M-11) | Net | Notes |
|---|---|---|
| BAT+ x 2 | VBAT_PACK | Two contacts in parallel |
| BAT- x 2 | GND | Two contacts in parallel |
| SDA, SCL | PACK_SDA, PACK_SCL | Which bus, which voltage, and hot-plug buffering are open (GHO-8, GHO-9) |
| PACK_PRESENT/ID | PACK_PRESENT, pulled up on the radio side | Bridge study. Pull-up domain and GPIO open (K-19) |
| Spare or wake | PACK_SPARE | PR #64 candidate: BQ76942 BOTHOFF |

Contact positions on the 4 x 2 grid are a PR #64 proposal. The interconnect between the replaceable pogo daughterboard and the carrier is not selected (GHO-8, GHO-7).

### TPS26633RGER, VQFN-24 (datasheet Table 5-1; values Record §12)

| Pin | Name | Net and value |
|---:|---|---|
| 1, 2 | IN | Q1 drain |
| 3 | B_GATE | EFUSE_BGATE to Q1 gate |
| 4 | DRV | EFUSE_DRV to Q2 gate (Q2 from B_GATE to IN_SYS) |
| 5 | IN_SYS | IN_SYS (Q1 source, input side) |
| 6 | UVLO | Divider from IN_SYS: 464 kΩ over 82.5 kΩ |
| 7 | PLIM | 60.4 kΩ to GND |
| 8 | GND | GND |
| 9 | dVdT | 22 nF to GND |
| 10 | ILIM | 3.24 kΩ to GND |
| 11 | MODE | GND (auto-retry) |
| 12 | SHDN | Open |
| 13 | IMON | No connect |
| 14 | FLT | EFUSE_FAULT, open drain. Pull-up in the CM5 domain (ledger); value open |
| 15 | PGTH | Divider from OUT: 243 kΩ over 49.9 kΩ |
| 16 | PGOOD | EFUSE_PGOOD, 100 kΩ to OUT. Drives BUCK_EN (§12) or not (bridge study), K-13. Never connected directly to POWER_GOOD (ledger, §12) |
| 17, 18 | OUT | EFUSE_OUT → shunt |
| 19 to 24 | N.C. | No connect |
| PAD | PowerPAD | GND |

### INA228 (datasheet Table 5-1; Record §12)

| Pin | Name | Net |
|---:|---|---|
| 1, 2 | A1, A0 | Address straps, open: 16 addresses are possible (Table 7-2). Set when the SYS_I2C address map exists |
| 3 | ALERT | INA228_ALERT_N, pull-up to CM5_3V3 (Proposed) |
| 4 / 5 | SDA / SCL | SYS_I2C_SDA / SYS_I2C_SCL |
| 6 | VS | CM5_3V3 (§12) |
| 7 | GND | GND |
| 8 | VBUS | VBAT_PROTECTED |
| 10 / 9 | IN+ / IN- | Kelvin taps on the supply side / load side of the WFK0612 10 mΩ shunt |

Range: ±163.84 mV; starting calibration in §12.

### LM76005 x 2 (datasheet pin table; values Record §13 and v1-3v3-rail.md)

| Pin | Name | 5 V buck (+5V_SYS) | 3.3 V buck (+3V3_RADIO) |
|---:|---|---|---|
| 20, 21, 22 | PVIN | Input bus: VBAT_PROTECTED or +VBUS_HOLD (open, K-13); 2 x 4.7 µF 100 V X7R plus 47 nF | Same |
| 1 to 5 | SW | 6.8 µH, Isat ≥ 8 A | 4.7 µH, Isat ≥ 8 A, Irms ≥ 6 A, DCR ≤ 15 mΩ |
| 6 | BOOT | 470 nF to SW | 470 nF to SW |
| 8 | VCC | 2.2 µF | 2.2 µF |
| 9 | BIAS | +5V_SYS, 1 µF | +3V3_RADIO, 1 µF |
| 10 | RT | Open (400 kHz) | Open |
| 11 | SS/TRK | Open (6.3 ms) | Open |
| 12 | FB | 100 kΩ / 24.9 kΩ (1 %), 47 pF feedforward | 100 kΩ / 42.2 kΩ (0.1 %, 25 ppm/°C), 47 pF |
| 16 | PGOOD | Open drain; destination open (Proposed: TP, or a supervisor input under GHO-10) | Same |
| 17 | SYNC/MODE | Logic high (forced PWM); high source open | Same; SYNC between the two bucks is an option (§13) |
| 18 | EN | BUCK_EN (source open, K-13) | BUCK_EN |
| 24, 25, 26 | PGND | GND | GND |
| 13, 14, 15 | AGND | GND | GND |
| 7, 23 | NC | Leave floating (datasheet) | Same |
| 19, 27 to 30 | NC | No connect | No connect |
| EP | DAP | GND with thermal vias | Same |
| Output | | 3 x 47 µF 10 V X7R | 4 x 47 µF 10 V X7R |

The 3.3 V buck allocation is 4.5 A at 3.39 V (B-18, D-026), which covers the 3 A the AW7916-AED needs.

### TPS22975 x 2 (datasheet SLVSDD0B pin table)

| Pin | Name | Wi-Fi switch (U302, §13) | HaLow switch (U303) |
|---:|---|---|---|
| 1, 2 | VIN | +3V3_RADIO | +3V3_RADIO |
| 3 | ON | WIFI_PWR_EN. Proposed: pull-down to GND (ON must not float; off while the CM5 is absent) | HALOW_PWR_EN, same pull-down |
| 4 | VBIAS | Open: 2.5 to 5.7 V source not recorded (+5V_SYS or +3V3_RADIO) | Same |
| 5 | GND | GND | GND |
| 6 | CT | Capacitor for about 1 ms rise ([v1-3v3-rail.md](v1-3v3-rail.md)); value from the datasheet table, open | Open |
| 7, 8 | VOUT | WIFI_3V3 | HALOW_3V3 |
| PAD | Thermal pad | GND | GND |

The TPS22975 carries up to 6 A, so the WIFI_3V3 switch meets D-026's 3 A. The socket contacts do not yet (0.5 A per contact, GHO-10/GHO-26).

### Charge, PD and bridge blocks (functional only)

No pin numbers: the TPS25751A package is not recorded, and the BQ25798 and LTC3350 datasheets were not fetched for this plan.

| Block | Nets | Status |
|---|---|---|
| B-07 USB4720-03-A service port | VBUS_SVC, SVC_CC1, SVC_CC2, SVC_DP, SVC_DM, shell to the wall | SVC_DP/DM have no CM5 endpoint (K-3) |
| B-08 TPS25751A | SVC_CC1/2, VBUS_SVC, I2C (to the charger and as a target on SYS_I2C, Proposed), interrupt output (no GPIO) | Selected; integration GHO-10 |
| B-09 BQ25798 | VBUS_SVC in, VBAT_PACK at BAT, VSYS_CHG out, I2C on SYS_I2C (Proposed), interrupt (no GPIO) | Selected; integration GHO-10 |
| B-24 LTC3350 | Input from VBAT_PROTECTED, output +VBUS_HOLD, PFO to BRIDGE_ACTIVE_N, I2C (Proposed SYS_I2C), PFI divider 562 kΩ over 100 kΩ | Candidate, GHO-38 |
| GNSS filter | +3V3_RADIO → filter → +3V3_GNSS | Filter not specified |

### Test pads

Proposed: TP on VBAT_PACK, IN_SYS, EFUSE_OUT, VBAT_PROTECTED, +VBUS_HOLD, +5V_SYS, +3V3_RADIO, WIFI_3V3, HALOW_3V3, +3V3_GNSS, BUCK_EN, EFUSE_PGOOD, and the two shunt Kelvin taps; a GND pad at each group.

---

## 07_SYSTEM

**Scope (§17):** apply the canonical GPIO allocation, plus the supervisor, watchdog, PMIC_Enable recovery, radio power and fault, GNSS reset and PPS, USB hub reset and fault, and Ethernet timing.

**Parts:** B-20 (TI TPS386000RGPR). Open: POWER_GOOD level translator, recovery logic into SYS_PMIC_EN.

### TPS386000RGPR (datasheet SBVS105F; rails Record §13)

| Pin | Name | Net | Notes |
|---:|---|---|---|
| 14 | VDD | Open. VDD is 1.8 to 6.5 V, so it cannot come from VBAT_PROTECTED. Proposed: +5V_SYS | K-6 |
| 10 | SENSE1 | SUP_SENSE1: divider from CM5_3V3 to the 0.4 V threshold | Record SVS1. RESET1 also starts the watchdog (K-6) |
| 9 | SENSE2 | SUP_SENSE2: divider from +5V_SYS | Record SVS2 |
| 8 | SENSE3 | SUP_SENSE3: divider from +3V3_RADIO, set against the 3.32 V minimum | Record SVS3; [v1-3v3-rail.md](v1-3v3-rail.md) |
| 7 | SENSE4L | SUP_SENSE4: divider from VBAT_PROTECTED (§13) or +VBUS_HOLD (bridge study) | K-13 |
| 6 | SENSE4H | GND (overvoltage monitoring not used) | Datasheet: GND if unused. Proposed |
| 5, 4, 3, 2 | CT1 to CT4 | Reset delays: open, fixed (resistor to VDD or open) or capacitor | GHO-10 |
| 13 | VREF | No connect | Proposed |
| 1 | MR | SUP_MR_N: latch-clear path | GHO-10 owns it (§13) |
| 20 | WDI | SUPERVISOR_WDI | Record |
| 19 | WDO | SUPERVISOR_WDO, open drain, pull-up domain open | Record |
| 15 to 18 | RESET1 to RESET4 | SUP_RESET1_N to SUP_RESET4_N, open drain; where each goes is open | GHO-10 |
| 11 | NC | GND (datasheet recommends) | |
| 12 | GND | GND | |
| PAD | Thermal pad | GND | |

Watchdog: 450 ms minimum, 750 ms maximum, latching; edges on WDI alone do not clear it (§13).

### GPIO defaults

These are the carrier-side defaults that must hold before firmware runs. Signal names come from the ledger; GPIO numbers are in the ledger only.

| Ledger signal | Carrier default | Status |
|---|---|---|
| HALOW_PWR_EN, WIFI_PWR_EN | Pull-down at the TPS22975 ON pin: radios off while the CM5 is absent or in reset | Proposed; ledger says carrier bias open |
| HALOW_RESET_N, HALOW_WAKE_N | No carrier resistor (the card has its own pull-ups to HALOW_3V3). Open drain only | Record |
| WIFI_WDIS1_N | 10 kΩ pull-up to WIFI_3V3. Open drain only | Record |
| GNSS_RESET_N | No carrier resistor (MAX-M10S internal pull-up) | Proposed; back-feed K-7 |
| GNSS_PPS | Input; series-resistor footprint at the module | Proposed; K-8 |
| GNSS_UART_TX, GNSS_UART_RX | No pulls | Proposed; back-feed K-7 |
| SYS_I2C_SDA, SYS_I2C_SCL | CM5 1.8 kΩ pull-ups only | Datasheet; address map open |
| USB_HUB_RESET_N | Pull-down at GRSTz: hub held in reset until released | Proposed (ledger sequence step 1) |
| VLM_USB_FAULT_N | One pull-up shared with OVERCUR3z | Domain open |
| HALOW_USB_FAULT_N | Pull-up only (reads "no fault"); no source exists | K-4 |
| HALOW_FAULT_N, WIFI_FAULT_N | Pull-up to CM5_3V3 only; no source exists | Ledger: source unselected |
| SUPERVISOR_WDI | Weak pull-down so WDI does not float during boot | Proposed; arming GHO-10 |
| SUPERVISOR_WDO | Pull-up, domain open | Ledger |
| POWER_GOOD | Through a translator from EFUSE_PGOOD (battery domain) | Open, GHO-9/GHO-10/GHO-13 |
| EFUSE_FAULT | Pull-up to CM5_3V3 | Ledger asks for a CM5-domain pull-up; value open |
| INA228_ALERT_N | Pull-up to CM5_3V3 | Proposed |
| Reserved rows | No connect | Ledger |

### Recovery path

Order (ledger and §22): reset a USB device, reset the hub (USB_HUB_RESET_N), power-cycle a radio (HALOW_PWR_EN, WIFI_PWR_EN), supervisor and watchdog, then SYS_PMIC_EN. SYS_PMIC_EN is pulled up to 5 V inside the CM5, so any source (WDO, a RESET output, recovery logic) must be open drain. The gating logic is GHO-10 work.

### Exposed timing signals

| Signal | Path | Exposed at | Rule |
|---|---|---|---|
| GNSS PPS | MAX-M10S TIMEPULSE (pin 4) → GNSS_PPS → CM5 PPS input (ledger) | TP_GNSS_PPS (Proposed) | Independent of Ethernet timing (D-033, §24). Firmware consumer: `dtoverlay=pps-gpio` (ledger, firmware PR #23) |
| Ethernet PHY sync | CM5 pin 18 Ethernet_SYNC_OUT → ETH_SYNC_OUT | TP_ETH_SYNC (Record) | Test point only; no GPIO capture, no PHY sync input (D-033) |

---

## Not on any sheet

By decision: onboard CM108B, 93C46 EEPROM, GPIO1 identity strap, analog microphone or speaker circuitry and a PTT switch (D-023; they live in the external B-22); user buttons, user or status LEDs and Ethernet LEDs (§24, §30); an external Ethernet PHY and PoE (§24); Bluetooth (D-026); a GNSS power switch (§24); a hub EEPROM (§24); a generic GNSS RF TVS (§30 rule 13); HaLow SDIO or SPI (§24).

## Test pad register

| Pad | Net | Sheet | Status |
|---|---|---|---|
| TP_PWR_BUTTON | CM5 PWR_Button | 01 | Record |
| TP_NBOOT | CM5 nRPIBOOT | 01 | Record |
| TP_ETH_SYNC | ETH_SYNC_OUT | 04 | Record (D-033) |
| TP_WIFI_PEWAKE | WIFI_PEWAKE_N | 02 | Record |
| TP_WIFI_LED1, TP_WIFI_LED2 | WIFI_LED1, WIFI_LED2 | 02 | Record |
| TP_GNSS_SAFEBOOT | GNSS_SAFEBOOT_N | 05 | Record (§9) |
| TP_GNSS_EXTINT | GNSS_EXTINT | 05 | Record (§9) |
| TP_GNSS_PPS | GNSS_PPS | 05 | Proposed |
| Rail pads | +5V_CM5, CM5_3V3, HUB_1V1, HUB_3V3, VLM_VBUS, VBAT_PACK, IN_SYS, EFUSE_OUT, VBAT_PROTECTED, +VBUS_HOLD, +5V_SYS, +3V3_RADIO, WIFI_3V3, HALOW_3V3, +3V3_GNSS, GNSS_V_BCKP | 01 to 06 | Proposed |
| Control pads | SYS_PMIC_EN, USB_HUB_RESET_N, PCIE_RST_N, BUCK_EN, EFUSE_PGOOD, VLM_CC1, VLM_CC2, VLM_USB_FAULT_N, SYS_I2C_SDA, SYS_I2C_SCL, shunt Kelvin taps | 01 to 07 | Proposed |

Placement: test pads go on the bottom side (§20), not under the CM5 unless they fit its 2.5 mm clearance.

## Open before capture

Each gap maps to the issue that owns it. A sheet cannot be captured to a releasable state until its rows close. Rows marked "no issue found" need a Linear issue opened by the records owner (README rule 8).

| # | Gap | Sheets | Owner |
|---|---|---|---|
| 1 | AW7916-AED pin numbers from a bench card; whether the card holds W_DISABLE1# or PEWAKE# internally | 02 | GHO-9 |
| 2 | Boot and device-tree defaults for every retained GPIO, including the hub reset and both USB fault inputs; RP1 reset pull states | 01, 07 | GHO-9, GHO-19 |
| 3 | GPIO allocation for PACK_PRESENT, BRIDGE_ACTIVE_N and any charger, PD-controller or bridge interrupts | 01, 06 | GHO-9 with GHO-38/GHO-10 |
| 4 | Disposition of CM5 pins the records do not mention: USB_OTG_ID (101), CC1/CC2 (94/96), PCIE_PWR_EN (106), EEPROM_nWP (20), SCL0/SDA0 (80/82) | 01 | GHO-9, GHO-19 |
| 5 | Source, or removal, of HALOW_USB_FAULT_N, HALOW_FAULT_N and WIFI_FAULT_N | 03, 07 | GHO-9 |
| 6 | Power-chain order (charger, TVS, Q1, eFuse, shunt, bridge) and where B-16/B-17 sit | 06 | GHO-10 |
| 7 | BUCK_EN source and SVS4 sense point (eFuse PGOOD or +VBUS_HOLD) | 06, 07 | GHO-10, GHO-38 |
| 8 | Supervisor VDD source, CT values, RESET1 to RESET4 destinations, MR latch clear, arming, and how WDO reaches SYS_PMIC_EN | 07 | GHO-10 |
| 9 | POWER_GOOD logic-level interface from the battery-domain PGOOD | 06, 07 | GHO-10, GHO-9 |
| 10 | Isolation of always-on domains (GNSS, I2C devices on other rails, supervisor, eFuse) from CM5 pins while the CM5 is off | 01, 05, 06, 07 | GHO-9, GHO-10 |
| 11 | TUSB4041I supplies: HUB_1V1 regulator, HUB_3V3 source, HUB_VBUS_DET source | 03 | GHO-10 (rail), GHO-26 (part) |
| 12 | TPS22975 VBIAS source and CT values for both switches | 06 | GHO-10 |
| 13 | Relation between +5V_SYS and +5V_CM5; +5V_SYS budget including VLM_VBUS | 01, 06 | GHO-10 |
| 14 | Wi-Fi socket current rating or a redesigned power path (TE 2199119-6 at 0.5 A per contact) | 02 | GHO-10, GHO-26 |
| 15 | Port-3 CC controller and VBUS switch, current limit, discharge and fault latch | 03 | GHO-11 |
| 16 | USB ESD for B-07, B-23 data, CC and VBUS | 03, 06 | GHO-11 |
| 17 | Ethernet magnetics (≤ 3.5 mm), Ethernet ESD, Bob Smith network, surge requirement | 04 | GHO-11 |
| 18 | GNSS antenna connector, antenna bias source, backup storage, RF ESD and SAW population | 05 | GHO-11 (parts), GHO-12 (SAW tests) |
| 19 | Chassis and shield bonding strategy (CHASSIS_GND) | 03, 04, 05, 06 | GHO-11 |
| 20 | B-07 service data path to the CM5 (console and rpiboot) | 01, 03, 06 | GHO-11 and GHO-9; no issue found for the path itself |
| 21 | Pack contact positions, pack I2C bus and its hot-plug buffering and level, PACK_SPARE use, daughterboard-to-carrier interconnect | 06 | GHO-8, GHO-7 |
| 22 | Pigtail wiring: header pair to RJ45 pins and polarity; Molex land pattern SD-504050-001 | 04 | GHO-45 |
| 23 | Bridge population, power stage and current; whether +VBUS_HOLD exists | 06 | GHO-38, GHO-10 |
| 24 | SYS_I2C address map (INA228 straps, charger, PD controller, bridge, GNSS, pack) | 06, 07 | GHO-9, GHO-10 |
| 25 | Exact MPNs and packages for footprints: TPS25751A package, 24 MHz crystal, inductors, bulk capacitors | 03, 06 | GHO-26 |
| 26 | PCIe impedance target (85 or 90 Ω) and fabricator stackup | 02, 03, 04 | GHO-14, GHO-15 |
| 27 | Connector wall faces and CAD fit for B-23, GNSS connector and test-pad access | 03, 05 | GHO-7 |
| 28 | Voice/PTT integration closure (still In Progress and listed as a GHO-13 blocker) | 03 | GHO-35 |
| 29 | CM5 RTC backup on VBAT (pin 76) | 01 | No issue found (PR #57 §2.5) |
| 30 | GNSS_PPS input bias against the SAFEBOOT_N strap | 05, 07 | GHO-9, GHO-11 |

## Conflicts between records

Proposed text for the records owner. README rule 6 asks for a Linear issue per conflict; this file opens none and resolves none. Items already raised in an open PR are cited, not repeated.

**K-1. Sheet list location.** "GHO-13's description and the brief cite 'Handoff §26' for the seven sheets. In v1-reference.md the sheet list is §17 ('Schematic sheets'); §26 is 'Critical open items'. Update the ticket text, or note that §26 is the handoff's original numbering."

**K-2. §17 sheet contents lag the power path.** "v1-reference.md §17 lists the Wi-Fi TPS22975 on both 02_PCIE_WIFI and 06_POWER, and its 06_POWER list leaves out B-07, B-08, B-09 and B-24 (+VBUS_HOLD), which §11 and v1-hot-swap-bridge.md §4 put in the power path. Decide which sheet owns each radio switch and add the charge and bridge blocks to a sheet."

**K-3. B-07 service data has no CM5 endpoint.** "D-009 and B-07 say the USB-C DATA / CHARGE port carries CM5 console and service data. The CM5's only USB 2.0 port that can act as a device (pins 103/105, USB_OTG_ID on pin 101) is the TUSB4041I upstream link (ledger, §3), and the CM5 datasheet says to tie USB_OTG_ID to GND for a fixed host role. rpiboot recovery through nRPIBOOT also needs that port in device mode. The CM5 debug UART exists only on module test points TP35/TP36 (datasheet Table 13), not on the connector, so §4's 'internal debug UART/test points' cannot be routed on the carrier. Choose a service-data architecture (for example a USB 2.0 switch on the CM5 port, or a USB-to-UART bridge to a spare UART) or narrow D-009."

**K-4. HALOW_USB_FAULT_N has no source.** "D-024 and the ledger keep HALOW_USB_FAULT_N as a HaLow USB fault input. The GW16170 is an M.2 card powered from HALOW_3V3 by a TPS22975, which has no fault output, and hub port 1 has no VBUS switch, so nothing can drive this signal. Name a source or free the GPIO, as D-026 did for BT_USB_FAULT_N."

**K-5. INA228 telemetry is not pack-only in the charger-first path.** "v1-hot-swap-bridge.md §4 places the shunt after BQ25798 SYS and says the INA228 'sees pack current only'. With the charger ahead of the eFuse, the shunt carries the charger's system output, which includes USB-C power while charging, not pack current. §12 and §21 expect battery voltage, current, charge and energy. Decide whether battery telemetry needs a pack-side measurement (for example the BQ25798 or BQ76942 gauges) or a different shunt position."

**K-6. Supervisor topology against CM5 power-up.** "v1-reference.md §13 puts SVS1 on CM5_3V3 and has the TPS386000 able to pull PMIC_Enable low; the watchdog starts when RESET1 releases. The CM5 3.3 V rail only rises after PMIC_Enable rises (CM5 datasheet §3.1), so RESET1 cannot gate PMIC_Enable without holding the CM5 off. TPS386000 VDD is 1.8 to 6.5 V (SBVS105F), so VDD cannot come from VBAT_PROTECTED; the VDD source is not recorded. GHO-10 owns the fix."

**K-7. CM5 reverse-voltage rule against always-on domains.** "The CM5 datasheet §4.2.1 forbids external voltage on any pin while the CM5 is powered down. The recovery hierarchy (§22, step 5) powers the CM5 down through PMIC_Enable while +3V3_RADIO, +3V3_GNSS, the supervisor, the eFuse and the charger stay up. The MAX-M10S drives TXD and TIMEPULSE and pulls RESET_N, SDA and SCL up to its own rail; I2C devices on other rails share SYS_I2C. No record addresses isolation. Add a rule and the parts (series resistors, buffers or switched pull-ups) under GHO-9/GHO-10."

**K-8. GNSS TIMEPULSE and SAFEBOOT_N.** "MAX-M10S data sheet R08 Table 10, note 15: SAFEBOOT_N is joined to TIMEPULSE inside the module through 1 kΩ, and the receiver enters safeboot if it is low at start-up. TIMEPULSE is GNSS_PPS to a CM5 input. If the CM5 pin is pulled down, or the CM5 is unpowered when the GNSS starts, the GNSS can boot into safeboot. v1-reference.md §9 treats SAFEBOOT_N as a test pad only. Define the PPS input bias and any series isolation."

**K-9. No 1.1 V rail for the hub.** "TUSB4041I needs a 1.1 V core supply on seven VDD pins (0.99 to 1.26 V, SLLSEK3F Table 4-1 and §5.3). No record lists a 1.1 V regulator or the hub's 3.3 V source; §17 03_USB_HALOW_AUDIO lists only the crystal. Add the rail to the power tree and the BOM."

**K-10. GNSS antenna bias.** Already raised in PR #57 (conflict 2): §9 says VCC_RF biases the antenna; PR #57 proposes a current-limited switch.

**K-11. GNSS EXTINT.** "§9 keeps EXTINT as a test pad. PR #57 (candidate) uses the EXTINT PIO as ANT_SHORT_N for the two-pin antenna supervisor, which gives up time-mark and wake. Choose one."

**K-12. +5V_SYS and +5V_CM5.** "§4 ties all CM5 5 V pins to +5V_CM5; §3, §13 and the selections power tree feed the CM5 from +5V_SYS. No record says whether +5V_CM5 is the same net, a filtered branch or a switched branch."

**K-13. Buck EN and SVS4.** Already raised in PR #61 (C-13): §12/§13 against v1-hot-swap-bridge.md §4.

**K-14. eFuse PGOOD to POWER_GOOD.** "v1-hot-swap-bridge.md §4 says 'eFuse PGOOD goes to GPIO 12 POWER_GOOD only'. The ledger and §12 say this battery-domain open-drain node must not connect directly to the CM5 and needs a separate logic-level interface. Align the bridge study with the ledger."

**K-15. HaLow control-pin wording.** "v1-reference.md §7 says 'the CM5 GPIOs wired to pins 54 and 56 (GPIO 18 and 19 in section 16)'. Read in order, that pairs pin 54 with the first GPIO named; the ledger puts HALOW_RESET_N on pin 56 (W_DISABLE1#) and HALOW_WAKE_N on pin 54. Reword §7 to name the ledger signals instead of GPIO numbers."

**K-16. Ethernet header shield pin.** Already raised in PR #57 (conflict 6): §10 says extra header pins are chassis or shield only, but all eight carry MDI.

**K-17. +5V_SYS allocation in the stackup.** Already raised in PR #61 (C-5): v1-stackup-routing.md still cites 2 A against 2.5 A in §14 and B-18.

**K-18. PCIe impedance.** Already raised in v1-stackup-routing.md: 90 Ω (CM5 datasheet) against the 85 Ω ticket target.

**K-19. Bridge and pack signals with no GPIO.** "v1-hot-swap-bridge.md names BRIDGE_ACTIVE_N (LTC3350 PFO) and PACK_PRESENT as CM5 inputs, and M-11 gives the pack SDA and SCL contacts. The ledger allocates none of them and does not say which I2C bus the pack joins. The free rows are the ones the ledger marks Reserved."

## What this does not verify

- No schematic was drawn and no ERC was run. GHO-13's acceptance (ERC review, schematic review, freeze criteria) is not started.
- AW7916-AED pin numbers come from finger order (ledger) and are **Unverified**.
- GW16170 ground-pin positions are assumed from the M.2 E-key standard; Gateworks lists only the signals.
- RP1 reset pull states, CM5 behavior with CC1/CC2 open, and whether PERST# or CLKREQ# back-feed an unpowered Wi-Fi card are **Unverified**.
- TUSB4041I: the HUB_VBUS_DET source for an embedded host, the external pull-down needed on GRSTz against its internal pull-up, and the TEST pin treatment are **Unverified**.
- The header-to-RJ45 pair map and polarity are Proposed from MagJack convention; IEEE 802.3 was not fetched.
- TPS25751A, BQ25798, LTC3350, GCT USB4720-03-A, TE 2199119-6 and Molex 504050-0891 pin numbers were not checked.
- Every Proposed default and net name is a starting point for capture, not a reviewed design.
