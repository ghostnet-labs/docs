# VP2430e bench node: power budget

Every figure here is **paper** evidence: a datasheet or vendor figure, a third-party figure, or an estimate where marked. Nothing has been measured yet. The bench measurements that replace these figures are in [bring-up.md](bring-up.md#5-power).

## Loads at the 12 V input

| Load | Typical | Peak | Source |
|---|---|---|---|
| VP2430e with 8 GB DDR5, NVMe, links up | about 9 W idle | about 20 W, an estimate: four cores at full load with NVMe and Ethernet traffic | Idle: [AstLinux](https://doc.astlinux-project.org/userdoc:board_protectli_vp2430), method not given, **Unverified**. Peak: estimate. Protectli rates the whole box, slots included, at 45 W maximum ([datasheet](https://protectli.com/wp-content/uploads/2026/06/VP2430e-Datasheet-20260527.pdf)) |
| AW7916-AED in the E-key slot | about 3 W while associated, 5 W average under traffic | 9.9 W at the card (3.3 V x 3 A), about 11 W at 12 V after the board's 3.3 V regulator (estimate: 90%) | [AsiaRF](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) gives 9 W maximum and asks for 3.3 V 3 A; Protectli's [kit page](https://protectli.com/product/protectli-m-2-802-11ax-wifi-kit/) gives 5 W average and 8 W maximum |
| GW16167 HaLow (MM8108) on the Pier42 USB carrier | 0.5 W | about 1.2 W | [Gateworks GW16167](https://trac.gateworks.com/wiki/expansion/gw16167), same figures as the CM5 track |
| MAX-M10S + ANN-MB1, MAX3232 | about 0.15 W | about 0.2 W | [MAX-M10S data sheet](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf) plus the ANN-MB1 LNA and the MAX3232 supply current |
| MCP2221A + INA228 | under 0.1 W | under 0.1 W | Estimate |
| **Total at 12 V** | **about 13 W** | **about 33 W** (sum of the peaks above; design bound: 45 W, Protectli's rating) | |

The typical row assumes a node that is meshing with light traffic. The peak row adds every load's maximum at once, which is a design bound and not an expected operating point. The 9 W idle figure may or may not include a Wi-Fi card; the bench measurement settles it.

## At the 3S pack

The Victron Orion-Tr 12/12-9 isolated converter is 87% efficient and draws under 50 mA with no load ([datasheet](https://www.victronenergy.com/upload/documents/Datasheet-Orion-Tr-DC-DC-converters-isolated-100-250-400W-EN.pdf)). The figures below use 87% at every load, which is an estimate; real efficiency drops at light load.

| Case | At 12 V | From the pack | 3S at 9.0 V (empty) | 3S at 11.1 V (nominal) | 3S at 12.6 V (full) |
|---|---|---|---|---|---|
| Typical | 13 W | about 15 W | 1.7 A | 1.35 A | 1.2 A |
| Peak | 33 W | about 38 W | 4.2 A | 3.4 A | 3.0 A |
| Box rating | 45 W | about 52 W | 5.7 A | 4.7 A | 4.1 A |

What these numbers mean for the bench parts:
- **Converter headroom.** The Orion-Tr 12/12-9 is rated at 110 W at 25 °C and 85 W at 40 °C. Even the box-rating case uses about half of that.
  - Input range is 8 to 17 V. Shutdown is at 7 V and restart at 7.5 V. The output holds 12.2 V across the whole pack range, so an empty pack does not drop the box.
  - The rejected Mean Well DDR-60G-12 cuts out at 8.5 V, restarts only at 9 V, and is limited to 51 W below 18 V input ([datasheet](https://www.meanwell.com/Upload/PDF/DDR-60/DDR-60-SPEC.PDF)). That leaves almost no margin at 9.0 V.
  - The Pololu S18V20F12 gives only about 2 A near 12 V in, which is too little.
- **Wiring and protection.** The pack side carries 5.7 A in the worst case. Use 16 AWG or heavier from the pack to the converter, a fuse above 6 A, and an ideal-diode board rated above 6 A. That rating is higher than the CM5 track needs, so check it against the part chosen for the shared bench kit.
- **INA228 range.** At a 15 mΩ shunt (Adafruit 5832) and 5.7 A, the shunt drop is 86 mV. That is inside the INA228's ±163.84 mV range at the driver's default ADC range (gain 4). The shunt dissipates about 0.5 W at that current, within the breakout's 10 A rating.
- **Runtime.** These are estimates for comparing tracks, not field figures:
  - A 3S2P pack of 3.5 Ah cells (7 Ah, about 78 Wh, the same pack the CM5 track uses) gives about 5.2 h at the typical load. The CM5 track's figure is about 7.4 h.
  - A 3S1P pack (about 39 Wh) gives about 2.6 h.

## Comparison hooks

The four tracks report the same rows (typical and peak, at the board input and from the pack), so the scorecard can compare them directly.

The VP2430e's costs are:
- a higher idle draw, which is x86 platform overhead
- a second conversion stage, since 12 V must be made from the pack
- 1.19 kg of chassis

Its strengths are:
- mainline drivers
- a vendor-qualified 3052 Wi-Fi slot with a heatsink path
- a native UART with DCD for PPS
