# V2 node definition

Agreed by Justin on 2026-11-06 (D-058). This file owns what the V2 node is for. Every V2 design choice is checked against it. The working copy, with comments, is the [V2 node definition doc](https://claude.ai/artifact/Xma7QKaBnV3uzhKsL3aD1m). The radio approach is in the [V2 software-defined radio plan](https://claude.ai/artifact/QwgQ3oXPN7X62NtSBd3Ry4) and [GHO-92](https://linear.app/ghostnet-labs/issue/GHO-92).

V2 is a body-worn mesh radio for small civilian teams on foot. Its job is to keep push-to-talk voice and position sharing getting through when someone jams it, in a node close to MPU5 size, on unlicensed bands only.

## Requirements

| Area | V2 target | Why |
|---|---|---|
| Users | Small civilian teams on foot: search and rescue, security, hobby groups | Justin, 2026-11-06 |
| Who it is for | A product sold in small numbers, not only our own team | Justin, 2026-11-06. FCC certification is required before any sale |
| Main job | Push-to-talk voice and position sharing must get through. Video and data are a bonus when the link is good | Justin, 2026-11-06 |
| Spectrum | Unlicensed only: 902–928 MHz, 2.4 GHz and 5 GHz. 6 GHz very-low-power only if cheap to add | V2 spectrum choice, 2026-11-06. The AD9361 and ADRV9002 stop at 6,000 MHz, so 6 GHz needs an extra converter |
| Range | 1 to 3 km between two people on the ground, body-worn. Farther by relaying | Justin, 2026-11-06 |
| Jamming | Voice and position keep working against cheap wideband jammers and a jammer parked on our channel. Speed may drop | Justin, 2026-11-06; D-056 |
| Size | Close to an MPU5, omni whip or gooseneck antennas, no patch as the main antenna | Earlier size and antenna decisions |
| Runtime | A 12-hour shift on two packs: at least 6 h per pack | Justin, 2026-11-06 |
| Power budget | Whole node averages 12 W or less | Calculated: 75.6 Wh ÷ 6 h = 12.6 W, less about 5% conversion loss |
| Battery | Hot-swappable pack with an internal bridge cell | D-053 |
| Control link | LoRa control radio stays as a path that survives a radio or FPGA crash | D-057 |
| Talking to V1 | Nice to have, not required | Justin, 2026-11-06 |

## What "gets through" means (proposed)

These targets are proposed and still need Justin's yes.

| Measure | Proposed target | Note |
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
- Pole or building mounts on 6 GHz.

## Open questions

- 6 GHz: keep (needs a converter per antenna) or drop. Lean: drop.
- Price per node.
- Weight limit.
- Ruggedness: same sealing and temperature range as V1?
- Encryption: is the V1 approach enough, or do buyers need a certified one?
