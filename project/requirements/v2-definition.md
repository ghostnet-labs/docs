# V2 node definition

Agreed by Justin on 2026-11-06 (D-058). This file owns what the V2 node is for. Every V2 design choice is checked against it. The working copy, with comments, is the [V2 node definition doc](https://claude.ai/artifact/Xma7QKaBnV3uzhKsL3aD1m). The radio approach is in the [V2 software-defined radio plan](https://claude.ai/artifact/QwgQ3oXPN7X62NtSBd3Ry4) and [GHO-92](https://linear.app/ghostnet-labs/issue/GHO-92).

V2 is a body-worn mesh radio for small civilian teams on foot. Its job is to keep push-to-talk voice and position sharing getting through when someone jams it, in a node close to MPU5 size, on unlicensed bands only.

## Requirements

| Area | V2 target | Why |
|---|---|---|
| Users | Small civilian teams on foot: search and rescue, security, hobby groups | Justin, 2026-11-06 |
| Who it is for | A product sold in small numbers, not only our own team | Justin, 2026-11-06. FCC certification is required before any sale |
| Main job | Push-to-talk voice and position sharing must get through. Video and data are a bonus when the link is good | Justin, 2026-11-06 |
| Spectrum | Unlicensed only: 902–928 MHz, 2.4 GHz, 5 GHz and 6 GHz very-low-power (5,925–6,425 and 6,525–6,875 MHz) | V2 spectrum choice and Justin, 2026-11-06 (keep 6 GHz). The AD9361 and ADRV9002 stop at 6,000 MHz, so the 6 GHz path needs a frequency converter on each antenna chain, and its power counts against the 12 W budget |
| Range | 1 to 3 km between two people on the ground, body-worn. Farther by relaying | Justin, 2026-11-06 |
| Jamming | Voice and position keep working against cheap wideband jammers and a jammer parked on our channel. Speed may drop | Justin, 2026-11-06; D-056 |
| Size | Close to an MPU5, omni whip or gooseneck antennas, no patch as the main antenna | Earlier size and antenna decisions |
| Runtime | A 12-hour shift on two packs: at least 6 h per pack | Justin, 2026-11-06 |
| Power budget | Whole node averages 12 W or less | Calculated: 75.6 Wh ÷ 6 h = 12.6 W, less about 5% conversion loss |
| Battery | Hot-swappable pack with an internal bridge cell | D-053 |
| Control link | LoRa control radio stays as a path that survives a radio or FPGA crash | D-057 |
| Talking to V1 | Nice to have, not required | Justin, 2026-11-06 |
| Clean sheet | No V1 hardware or software is required in V2: the CM5, the V1 carrier and the current software stack are all open to change | Justin, 2026-11-06 (D-059) |
| Host and board | One design from day one: a Zynq UltraScale+ chip on our own board, radio parts on both sides of the radio board, about 76 × 47 × 215 mm | Justin, 2026-11-06 (D-060) |
| Features | V2 keeps every V1 feature: voice, transcripts, mesh and topology, channel migration, phone access point, GPS, cameras, mesh-join QR, BLOS, settings and firmware updates, battery readout, hot swap, and the scanner | Justin, 2026-11-06 (D-059) |

## What "gets through" means

Justin accepted these targets on 2026-11-06. They are the pass marks for V2 bench tests.

| Measure | Target | Note |
|---|---|---|
| Link rate under jamming | 50 kbps or more per hop | One voice stream at about 16 kbps plus position reports, with room for overhead |
| Link rate with no jamming | 10 Mbps or more at 500 m | One video stream to a phone or tablet |
| Voice gap when a jammer starts | 2 s or less | V1 channel migration can take up to 215 s, so V2 must move inside the radio |
| Time to spot a jammer | 0.5 s or less | Needed for the 2 s voice gap |
| Position updates under jamming | Every node at least every 10 s | Also fits the LoRa control link |
| Team size | Up to 16 nodes in one mesh | Small teams on foot |

## Not in V2

- Government, military or licensed bands.
- Guaranteed talk with V1 HaLow nodes.
- Pole or building mounts on 6 GHz, which the very-low-power rules forbid.

## Open questions

- Exact Zynq UltraScale+ part and memory size (D-060 fixes the family and the chip-on-board approach). Sources: [V2 host computer options](https://claude.ai/artifact/Xxa1F6D7EByfGLjwhU1eFu), [V2 size check](https://claude.ai/artifact/2BeZ9KSiV7MtPV58nrRwUF).
- Pack shape for a true MPU5 outline (67 × 38 mm): 18650 cells laid crosswise set the 76 mm width.
- Scanner power: the four scanner receivers add about 6 W (estimate), which the 12 W budget does not include. Lean: switch them on when wanted.
- Price per node.
- Weight limit.
- Ruggedness: same sealing and temperature range as V1?
- Encryption: is the V1 approach enough, or do buyers need a certified one?
