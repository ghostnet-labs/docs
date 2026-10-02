# V1 3.3 V radio rail sizing

**Owner:** [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10) — size the +3V3_RADIO supply for the AsiaRF AW7916-AED (D-026)  
**Status:** Calculated. No new part. Bench measurement on the two AW7916-AED cards closes it.

The AW7916-AED needs a 3.3 V supply of at least 3 A (10 W maximum, 8 W average, [datasheet](https://asiarf.com/wp-content/uploads/2026/07/260709_Datasheet_AW7916-AED_V1-1P.pdf)). The old 4 A allocation for +3V3_RADIO does not cover it together with HaLow and GNSS. This file sizes the rail; [v1-reference.md](v1-reference.md) sections 13 and 14 carry the summary.

## Result

| Item | Before | Now |
|---|---|---|
| +3V3_RADIO allocation | 4 A, 13.2 W | **4.5 A, about 15.3 W** (5 A hard ceiling) |
| Regulator | TI LM76005 | TI LM76005 (unchanged; 5 A part) |
| Output setpoint | 3.28 V, R_FBB 44.2 kOhm 1 % | **3.39 V, R_FBB 42.2 kOhm 0.1 %** |
| Inductor | 4.7 µH, Isat ≥ 8 A | 4.7 µH, Isat ≥ 8 A, **Irms ≥ 6 A, DCR ≤ 15 mOhm**, shielded |
| Buck output capacitors | 3 x 47 µF | **4 x 47 µF 10 V X7R** plus 47 pF feedforward |
| Capacitors at the M.2 socket | none listed | **2 x 22 µF X7R + 100 µF low-ESR polymer on WIFI_3V3** |
| WIFI_3V3 switch | TPS22975 | TPS22975 (unchanged; 6 A, 16 mOhm) with about 1 ms rise |
| Input eFuse limit | 5.56 A | 5.56 A (unchanged) |

## Load

| Load | Peak | Typical | Source |
|---|---:|---:|---|
| Wi-Fi, AW7916-AED | 3.03 A (10 W) | 2.4 A (8 W) | AsiaRF datasheet |
| HaLow, GW16170 / MM8108 | 1.0 A | to measure | earlier estimate |
| GNSS, MAX-M10S via +3V3_GNSS | 0.1 A | under 0.05 A | earlier estimate |
| Misc | 0.25 A | to measure | earlier estimate |
| **Total** | **4.38 A** | about 3 A | |

4.5 A covers every load at its peak at the same time. The typical figure is what the regulator and the enclosure will see most of the time.

## Regulator headroom

The LM76005 high-side current limit is 6.0 A minimum (7.8 A maximum). Inductor ripple with 4.7 µH at 400 kHz and 3.39 V out:

| Input | Ripple p-p | Peak at 4.5 A | Peak at 5 A |
|---:|---:|---:|---:|
| 8 V | 1.04 A | 5.02 A | 5.52 A |
| 12.6 V | 1.32 A | 5.16 A | 5.66 A |
| 33 V | 1.62 A | 5.31 A | 5.81 A |

At the 4.5 A allocation the peak stays at least 0.69 A under the minimum current limit. At 5 A it is 0.19 A under, so 5 A is the ceiling and not a design point. The inductor saturation current must stay above the 7.8 A maximum limit, so 8 A or more stands.

## Setpoint and voltage drop

The M.2 card needs 3.3 V ± 5 %, 3.135 to 3.465 V, at its pins. Between the regulator and the card sit the TPS22975 (16 mOhm typical, about 22 mOhm hot), board copper (budget 10 mOhm) and four 3.3 V socket contacts in parallel (budget 14 mOhm). At 3.03 A that is about 0.14 V.

V_FB is 0.987 to 1.017 V (1.006 V typical). With R_FBT = 100 kOhm and 0.1 % resistors:

| R_FBB | Nominal | Range | Lowest at the card at 3.03 A |
|---:|---:|---:|---:|
| 44.2 kOhm (old) | 3.28 V | 3.21 to 3.33 V | 3.07 V: **fails** |
| 43.2 kOhm | 3.34 V | 3.27 to 3.38 V | 3.13 V: **fails by 5 mV** |
| **42.2 kOhm** | **3.39 V** | **3.32 to 3.43 V** | **3.18 V: passes** |

At no load the card sees at most 3.43 V, under the 3.465 V limit. The GW16170 is also an M.2 card with the same tolerance, and the MAX-M10S accepts up to 3.6 V. Use 0.1 %, 25 ppm/C resistors: 1 % parts would add about 1.4 % and lose the margin on both ends. The TPS386000 SVS3 threshold for +3V3_RADIO must be set against the new 3.32 V minimum.

## Load steps

Wi-Fi transmit bursts step the load by about 2 A in microseconds. With a loop crossover near 40 kHz (a tenth of the switching frequency) and about 220 µF of effective capacitance, the dip is about 2 A / (2π x 40 kHz x 220 µF) = 36 mV, about 1 %. 4 x 47 µF 10 V X7R at the buck gives roughly 120 µF after DC bias; the 100 µF polymer and 2 x 22 µF at the socket bring the total over 220 µF and put charge next to the card. Confirm the loop and the dip on the bench.

## WIFI_3V3 switch

The TPS22975 carries up to 6 A and dissipates about 0.15 W at 3.03 A (0.2 W hot). Set its rise time to about 1 ms with the CT capacitor from the TPS22975 datasheet table: charging about 150 µF downstream in 1 ms draws about 0.5 A of inrush, which the buck absorbs without reaching its limit.

## Losses and heat

At 4.5 A and about 88 % efficiency from 12 V the buck loses about 2.0 W, about 0.3 W of it in the inductor. With the LM76005 WQFN at 29.6 C/W (JEDEC, [datasheet](https://www.ti.com/lit/ds/symlink/lm76005.pdf)) the die rises about 50 C over its surroundings; on a well poured board it will be less. At a 60 C internal enclosure temperature that is about 110 C, under the 125 C limit. This is the peak case; at the typical 3 A the loss is about 1.2 W. The card itself (8 W average) is the larger heat source and belongs to the thermal plan ([GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12)).

## Input side

+5V_SYS 10 W plus +3V3_RADIO 15.3 W is about 25.3 W out, about 28 W in at 90 % efficiency, which is 3.5 A at 8 V. The 5.56 A eFuse limit and the 35 W capability target stay as they are.

## Open risk: socket contact rating

The TE 2199119-6 socket is rated 0.5 A per contact ([TE](https://www.te.com/en/product-2199119-6.html)). The card draws 3.3 V through four contacts (pins 2, 4, 72 and 74), 2 A in total. The card's 2.4 A average and 3 A peak exceed that rating. Brief bursts are normal for M.2 Wi-Fi and accelerator cards, but a sustained 2.4 A would run the contacts hot. Actions:

1. Bench gate: measure the card's current on the CM5 at full-rate 802.11s traffic on both bands for 30 minutes, with a thermocouple on the socket.
2. If the sustained current is above 2 A, cap transmit power in firmware (`txpower` in the radio's UCI) until it is under 2 A, and record the range cost.
3. Ask TE (and JAE or Attend) for a 3052 A+E socket with a higher per-contact rating before layout freeze.

## Bench checks

- Sustained and peak current of the AW7916-AED (above).
- +3V3_RADIO dip during Wi-Fi transmit bursts and during HaLow transmit at the same time.
- Voltage at the M.2 socket pins at full load.
- Buck and inductor temperature at 4.5 A in the closed enclosure.
