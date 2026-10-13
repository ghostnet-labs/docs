# CM5 bench node: power budget

Every figure is **paper** evidence, taken from a datasheet or vendor page, or estimated where marked. Nothing here has been measured yet. The bench measurements that replace these figures are listed in [bring-up.md](bring-up.md).

## Loads at 5 V (`CM4_5V`)

| Load | Typical | Peak | Source |
|---|---|---|---|
| CM5 module | 2.0 W idle, 4.5 W working | about 10 W (estimate: all four A76 cores at full load plus PCIe and USB) | [CM5 datasheet](https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf), about 400 mA idle and 900 mA operating at 5 V |
| AW7916-AED on the M.2 slot | about 3 W while associated | 3.3 V x 3 A = 9.9 W at the card, about 11 W at 5 V through the MP1658 (about 90% efficient) | [AsiaRF AW7916-AED datasheet](https://asiarf.com/wp-content/uploads/2026/07/260709_Datasheet_AW7916-AED_V1-1P.pdf) maximum current |
| GW16167 HaLow (MM8108) on the Pier42 USB carrier | 0.5 W (0.1 A at 5 V) | about 1.2 W | [Gateworks GW16167](https://trac.gateworks.com/wiki/expansion/gw16167) |
| 2.5 GbE USB NIC | about 0.7 W | about 1 W | **Unverified.** The chip is not named on the schematic, so this assumes an RTL8156-class part |
| MAX-M10S + ANN-MB1 active antenna | about 0.1 W | about 0.15 W | [MAX-M10S data sheet](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf) plus the ANN-MB1 LNA |
| INA228, LM74700, EEPROM, ATSHA | under 0.05 W | under 0.05 W | |
| Fan (5 V, PWM) | about 0.3 W | about 0.5 W | Estimate for a 30 mm 5 V fan |
| Carrier overhead (hub, PWR_3V3 buck losses, LEDs) | about 0.3 W | about 0.3 W | Estimate |
| **Total at 5 V** | **about 9.5 W** (CM5 at 4.5 W) | **about 24 W** | |

The typical row assumes a node that is meshing with light traffic. The peak row adds up every load's maximum at once. That is a design bound, not an expected operating point.

## At the 3S pack

The MP9447 buck runs at about 90% efficiency at these loads (estimate, from the MP9447 efficiency curves at 12 V in and 5 V out). The LM74700 ideal diode adds tens of millivolts, which is negligible here.

| Case | At 5 V | From the pack | 3S at 9.0 V (empty) | 3S at 11.1 V (nominal) | 3S at 12.6 V (full) |
|---|---|---|---|---|---|
| Typical | 9.5 W | about 10.5 W | 1.17 A | 0.95 A | 0.84 A |
| Peak | 24 W | about 27 W | 3.0 A | 2.4 A | 2.1 A |

- **Barrel jack and wiring:** 3 A at the empty end. Use 18 AWG or heavier from the pack to the jack, and choose an LM74700 board and fuse rated above 3 A.
- **Buck output:** 24 W at 5 V is 4.8 A, within the MP9447's 6 A inductor and the part's rating. The USB ports' 2 A switches are not involved, since the HaLow carrier draws well under 0.5 A.
- **INA228 range:** at a 15 mΩ shunt (Adafruit 5832) and 3 A, the shunt drop is 45 mV, inside the INA228's ±163.84 mV range. The overlay's default ADC range (`ti,shunt-gain = <4>`) covers it.
- **Runtime:** a 3S2P pack of 3.5 Ah cells (7 Ah, about 78 Wh) gives about 7.4 h at the typical load. This is an estimate for comparison between tracks, not a field figure.

## Open item: the 5.40 V output

The schematic's feedback divider computes to about 5.40 V ([carrier.md](carrier.md#power-input)). That is above the CM5's 5.25 V input range but below its 6.0 V absolute maximum. If the measurement confirms it:
- At 5.40 V, power for the same loads is unchanged, but USB devices and the fan also see 5.40 V.
- The fix is to change R54 or R60 so the output is 5.10 V (for example R54 = 38.3 kΩ with R60 = 7.32 kΩ gives 5.08 V), or to use the CM5-DUAL-ETH-BOX-A's matching board revision if Waveshare confirms a different value.

## Comparison hooks

The other three tracks report the same two rows (typical and peak, at the board input and from the pack) so the scorecard can compare them directly. The CM5's advantage is the low idle draw of the module itself. Its risk is the carrier's 5 V buck sitting above the CM5's limit until measured.
