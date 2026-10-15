# Venice bench node: power budget

All figures are from published sources and have not been measured. The bench steps that replace each estimate with a measurement are in [bring-up.md](bring-up.md). Open questions are on [GHO-85](https://linear.app/ghostnet-labs/issue/GHO-85).

## 1. Input

| Item | Value | Status |
|---|---|---|
| Board input range | 8 to 60 VDC, reverse-voltage protected, dedicated DC jack. Also 802.3at PoE input, not isolated. | Verified 2026-10-12, [GW7200 product page](https://www.gateworks.com/products/industrial-single-board-computers/imx8-single-board-computers-gateworks-venice/gw7200-rugged-industrial-single-board-computer/), [PoE wiki](https://trac.gateworks.com/wiki/poe) |
| Pack | 3S Li-ion, 9.0 V (3.0 V/cell cut-off) to 12.6 V (full) | Same cells as B-11 in [v1-selections.md](../../hardware/v1-selections.md) |
| Margin at an empty pack | 9.0 V against the 8 V minimum is 1.0 V. The LM74700 ideal diode drops tens of mV at these currents, so it does not eat that margin. | Calculated |
| On-board supply | The product page says "wide-range DC input power supply provides up to 15W", and separately "15W Available for Mini-PCIe Sockets". | Verified as quoted. Whether 15 W caps the whole board or only the sockets is **Unverified** (GHO-85, question 2). |

The pack plugs straight in. No buck-boost is needed, unlike the Protectli track, and no 5 V regulator, unlike a bare CM5.

## 2. Load, one node

| Load | Typical | Worst case | Source |
|---|---|---|---|
| GW7201-01 board (SoC, RAM, eMMC, GbE, GSC, on-board GNSS) | 3.9 W | 3.9 W (no maximum published; the GbE links and CPU load add to it) | Gateworks: 3.9 W at 25 °C typical, 163 mA at 24 V |
| AsiaRF AW7916-NPD | 4 to 8 W | 9 to 10 W (3.3 V, "provide 3 A, minimum 2.5 A") | [AsiaRF](https://asiarf.com/product/wi-fi-6e-mini-pcie-module-mt7916-aw7916-npd/). The page states both 9 W and 10 W maximum; this budget uses 10 W. |
| GW16151 adapter | 0.66 W (0.2 A at 3.3 V) | 0.66 W | [Gateworks](https://www.gateworks.com/products/mini-pcie-expansion-cards/gw16151-mini-pcie-to-wifi-e-key-m-2-adapter-card/) |
| GW16167 HaLow | 0.33 W (0.1 A at 3.3 V) | about 1.2 W | [Gateworks wiki](https://trac.gateworks.com/wiki/expansion/gw16167) |
| ANN-MB1 active antenna (board bias, 3.3 V) | about 0.05 W | about 0.05 W | 15 mA typical at 5 V ([data sheet](https://cdn.sparkfun.com/assets/3/3/3/8/d/ANN-MB1_DataSheet_UBX-21005551.pdf)) |
| **Node total** | **about 9 to 13 W** | **about 15.8 W** | Sum |

The worst case assumes the 3.3 V loads reach the input at about the efficiency already folded into the board's 3.9 W. The on-board 3.3 V converter's efficiency is not published, so the real input power is somewhat higher than the sum. **Unverified.**

## 3. The mini-PCIe socket question

This is the main risk on this track. Each part of it is stated with its evidence:

- **The card asks for 3.3 V at 3 A, with a 2.5 A minimum** (AsiaRF). That is 8.3 to 9.9 W from one socket.
- **The PCI Express Mini Card pinout puts 3.3 V on three contacts**: pins 2, 24 (3.3Vaux) and 52. At an assumed 0.5 A per contact, three contacts give about 1.5 A, well short of 3 A. The per-contact rating is an assumption; it has not been checked against the spec or a connector data sheet (**Unverified**).
- **The screen estimated about 2.4 A per socket** ("5 pins x 0.5 A"). That only works if Gateworks puts 3.3 V on two more pins. Gateworks does not route 1.5 V to the slots (Verified, [Venice PCIe wiki](https://trac.gateworks.com/wiki/venice/PCIe)), but whether those pins carry 3.3 V instead is **Unverified**.
- **Gateworks calls these "High-Power Gen 2 Mini-PCIe Sockets"** and gives 15 W across both. The per-socket figure is in the GW7200 manual, which sits behind an email form and has not been read.
- **Gateworks does not list any MediaTek card as tested** on Venice ([Wi-Fi wiki](https://trac.gateworks.com/wiki/wireless/wifi)). For high-power radios it recommends a separate DC/DC from VIN instead of the slot rail (same page, "FES Power Discussion").

So the AW7916 directly in the socket is **plausible but unproven**. The bench measures it before relying on it:

1. Seat the card with the board on the kit supply, TX power at the regulatory minimum (bring-up step 6).
2. Step TX power up on both bands with traffic running, while logging input power (INA228) and the board's own rail readings (`/sys/class/hwmon` for the GSC). Watch for resets, PCIe link drops (`dmesg`), and `mt7915e` firmware crashes (bring-up step 10).
3. Pass: full regulatory TX on both bands for 30 minutes with no reset, link drop or firmware crash.

## 4. Fallback if the socket fails

Take these in order:

1. **Cap TX power** to the highest level that passed, and record the cap in the scorecard.
2. **Powered interposer.** Feed the card's 3.3 V from the pack through a dedicated 3.3 V / 3 A or larger buck, and leave only PCIe and the sideband signals on the socket. This is the same pattern GHO-50 proposes for the CN9130 (GHO-56), so one interposer design could serve both. It needs host-rail isolation, so the socket's 3.3 V never back-feeds the buck or the reverse.
3. **Swap to a lower-power MT7915 mini-PCIe card.** The card must stay MT7915/MT7916, because openmanetd only offers the `batmesh1` mesh on those chips.

## 5. Run time on the pack

The pack is the B-11 cell set: 3S2P Molicel M35A, about 75.6 Wh nominal.

| Load | Run time |
|---|---|
| 9 W (light traffic) | about 8.4 h |
| 13 W (busy mesh) | about 5.8 h |
| 15.8 W (worst case) | about 4.8 h |

These assume the full nominal capacity is usable. The pack's own cut-off and ageing reduce them. The board needs no extra regulator in the path, which is this track's advantage over the 12 V Protectli.

## 6. Thermal note

The AW7916-NPD is rated -10 to +70 °C (AsiaRF). The board is rated -40 to +85 °C. **The card, not the board, sets the node's temperature range.** The 10 mm heatsink's clearance to the board and to any lid is unverified (GHO-85, question 6).
