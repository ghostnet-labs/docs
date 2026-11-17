# Mast dock

**Status:** Selected, 2026-11-17 (D-064). Concept geometry; no part is chosen beyond Candidate, nothing was bought, and no node software supports the dock yet.
**Visual write-up and 3D model:** [Mast Dock](https://claude.ai/artifact/6WuHzrhFTe4tQbRQNC5yNx). Model source and CAD: project files `mast-dock/` (`src/dock.js` is the one source for the page viewer and `cad/build_step.py`, which writes the STEP and STL).

## Tags

- **Verified:** read from the linked source on 2026-11-17.
- **Calculated:** derived here from datasheet figures; method stated.
- **Unverified:** an assumption or typical figure, to be checked on the bench.

## What was decided

At each mast the node sits in a rock-in dock at the base of the pole. Setting the radio in the dock moves its HaLow, LoRa control radio and both 2.4 GHz mesh chains from the radio's own whips to the mast antennas (D-063), connects the dish Ethernet, and runs the radio on mast power. Lifting it out puts every band back on its whips with nothing to unplug. The whips stay attached the whole time.

The backup is plug-in jumpers. Every mast keeps the jumper path working, so a mast with no dock, or a broken dock, still runs: take the whips off, screw the entry-panel jumpers onto the radio's top antenna ports, plug the dish Ethernet into the sealed Ethernet port (B-06), and charge over the USB-C service port (B-07).

## How it docks

1. The battery end goes into a foot pocket on the dock, with the radio tipped forward.
2. Leaning the radio back, two tapered guide pins on the dock enter sealed blind bushings in the radio's back wall, and two magnets in the dock pull on steel strike plates in the radio (the aluminium walls are not magnetic) and hold it against the spring contacts.
3. To leave, tip it forward and lift. The radio pivots on the battery, so the top of the contact patch separates first. The dock-detect contact is the shortest and the highest, so it opens before any RF contact.

All springs and moving parts are in the dock, which stays in one place and is cheap to replace. The radio side is flat, sealed pads.

## Radio side

| Item | Design | Status |
|---|---|---|
| Contact patch (B-29) | One sealed insert flush in the back wall, about 50 × 28 mm, X ±25 mm, 98 to 126 mm above the battery's bottom face on the stacked concept body, below the CM5 heat pad and behind board A. Top to bottom: dock detect; four coax pads (centre pad and ground ring) for HaLow, LoRa, Wi-Fi 2.4 GHz A and B; eight Gigabit Ethernet pads; four power pads (2 +, 2 −). Guide bushings at X ±21 mm, steel strike plates at X ±21 mm | Concept. The same patch is expected to fit the back of the selected body (D-054); CAD check open under [GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7) |
| Antenna switches (B-30) | One SPDT RF switch per switched band between the radio card and its top-face port: one throw to the whip, one to the dock coax pad. Wi-Fi port C (5/6 GHz only) and GNSS have no switch and stay on the radio (D-063) | Candidate part SKY13330-397LF |
| Switch control | The dock-detect contact, with a pull-up, drives all four switches through logic. Software is not in that path. The CM5 reads the same signal and has one output that can force the whips, never the dock path. Undocked or unpowered, the whips are selected | Concept. Both signals need GPIOs, not allocated ([v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md)) |
| Dock Ethernet (B-31) | A USB Gigabit Ethernet controller on the CM5's second USB 3.0 port, with its own magnetics, to the eight Ethernet pads. It is a second interface (eth1); the sealed Ethernet port (B-06) is unchanged. It starts on that port's USB 2.0 pair, because USB 3.0 SuperSpeed traffic radiates broadband noise into the 2.4 GHz band; SuperSpeed is enabled only if the coexistence bench shows no desense | Candidate part RTL8153B |
| Dock power | The four power pads feed a second input of the radio's charger (B-09) through its dual-input selector, with a fuse, TVS and reverse-polarity block at the pads | Concept |

**Switch figures.** [SKY13330-397LF datasheet](https://www.skyworksinc.com/-/media/SkyWorks/Documents/Products/601-700/SKY13330_397LF_201407E.pdf), Verified: 0.1 to 6 GHz, 2 × 2 mm QFN, insertion loss 0.30 dB typical below 1 GHz and 0.35 dB at 2.2 to 2.5 GHz, isolation about 42 dB below 1 GHz and 33 dB at 2.4 GHz (the min/typical column reading is Unverified), P0.1dB +38.5 dBm, control high 1.65 to 2.7 V. The highest power through any switch is 24.5 dBm per Wi-Fi chain ([v1-rf-coexistence.md](v1-rf-coexistence.md)). The alternative, [pSemi PE42424](https://www.psemi.com/pdf/datasheets/pe42424ds.pdf), has 45 dB minimum isolation to 2.5 GHz but 0.8 dB typical loss, which every undocked use would pay.

**Wi-Fi ports.** Wi-Fi ports A and B carry 2.4 GHz and 5 GHz on the same lead. While docked, the node app limits the 5 GHz radio to port C, so the 5 GHz phone access point (D-055) stays on the radio's whip and nothing at 5 GHz goes up the 2.4 GHz coax. Which ports carry 2.4 GHz is the port-to-chain map that [v1-rf-coexistence.md](v1-rf-coexistence.md) lists as Unverified; it decides which two ports get switches.

## Dock side

| Item | Design |
|---|---|
| Cradle | Base plate, foot pocket with side walls and a low front lip (low enough that the radio can tip out), fixed back plate and a rear block for the cable entry. Printed nylon or bent aluminium |
| Contact plate | Floats about ±1 mm on four springs. Carries spring pins (the Mill-Max family of B-12) for detect, Ethernet and power, four spring coax probes, two tapered guide pins and two magnets. Coax probe part not chosen |
| RF | Four short jumpers from the coax probes to the grounded entry panel (D-063). They end in the same connector type as the backup jumpers, so either plugs into the panel |
| Ethernet | From the dish's PoE injector, data only |
| Power | 12 to 24 V DC from the mast power box, fused and surge-clamped in the dock. The dock powers the radio only |

The mast power box, not the radio or the dock, powers the dish, its PoE injector and anything else on the pole. The power box itself is not designed yet ([mast-links.md](mast-links.md)).

The dock lives in a box at the mast base whose lid is non-metal, so GNSS and the 5 GHz phone access point work through it. The radio with whips stands about 0.45 m, so the box is roughly 300 × 200 × 500 mm inside (Unverified).

## Powering a docked radio

The dock powers the radio directly through the back pads. The radio's charger is a power-path part: it runs the radio from the outside input and charges the battery only when needed, as it does on USB-C. Docked for days or weeks, the battery charges once and then rests, and it can be swapped while docked without the radio losing power. The charge voltage is settable, so a parked radio can hold its battery a little under full. [TI BQ25798](https://www.ti.com/product/BQ25798), Verified: 3.6 to 24 V operating input, 30 V absolute maximum, dual-input power mux controller, up to 5 A charge. Its input current limit, and so the power available at 12 V, is Unverified.

Charging through the battery's bottom contacts was considered and not used. The PRC-148 battery appears to have them: the [Bren-Tronics BT-70716BV datasheet](https://www.bren-tronics.com/amfile/file/download/file/425/product/1949) lists "flat contacts (bottom)" and a single-wire DQ data interface, and the [Bren-Tronics BTC-70716-1 charger](https://www.bren-tronics.com/btc-70716-1.html) charges a battery with or without the radio attached. That path would make the battery carry the radio's load all day while being topped up, which wears it, and every dock would need a charger that speaks the battery's unpublished data interface. The L3Harris PRC-152 battery may have no bottom contacts.

## Losses

| Path | 915 MHz | 2.4 GHz | Basis |
|---|---|---|---|
| Added to every undocked (whip) use | about 0.4 dB | about 0.5 dB | Switch loss above plus one more micro-coax joint (joint loss typical, Unverified). About 5% less free-space range |
| Radio to the dock's jumper, docked | about 0.8 to 1.2 dB | about 1.0 to 1.6 dB | Switch, about 150 mm of internal micro-coax, the spring coax contact (0.2 to 0.5 dB typical) and the dock's jumper. Unverified until measured |
| Docked on the mast against a whip at head height | about +11 dB | about +10 dB | Calculated: about 14 dB height gain less coax loss, from [mast-links.md](mast-links.md#losses-and-gains), less the dock path above |
| Whips while docked | about 42 dB down | about 33 dB down | Switch isolation |

## Node software

The switching works with no software. The node app (openmanetd) would add, none of it started:

- Dock state from the detect signal, shown on the node page on phone and desktop.
- A per-band transmit power profile while docked, from each mast's antenna gain and coax loss, so the radiated power stays within the FCC limits; restored on undock.
- The wired mesh link that [mast-links.md](mast-links.md) lists as missing, working on eth1 in the dock and on the sealed Ethernet port when a mast runs on the jumper backup.
- 5 GHz limited to Wi-Fi port C while docked.

## Rough cost

Typical prices for scale, Unverified. Purchasing lives in Linear.

- **Each radio:** about $50 to $70. Four switches about $4, four micro-coax leads about $12, Ethernet controller with magnetics and ESD about $5, power input protection and selector FETs about $5, sealed 17-pad insert about $20 to $40 at low volume, bushings and strike plates about $5.
- **Each dock:** about $215 to $550. Four spring coax probes about $60 to $160, thirteen spring pins about $15 to $40, floating plate and guide pins about $40 to $100, cradle about $30 to $120, magnets about $10, four jumpers about $40 to $80, glands, fuse and TVS about $20 to $40.

## Options compared

| Option | Result |
|---|---|
| A. Rock-in dock with sealed pads on the radio (this design) | Selected |
| B. Off-the-shelf docking connector, such as an [ODU-MAC](https://odu-connectors.com/news-center/news/high-frequency-new-odu-mac-12-ghz-coax-module/) frame with coax modules (0 to 12 GHz, 10,000 cycles) or floating [Molex BMA](https://www.everythingrf.com/products/connectors/molex/63-363-bma-blind-mate-rf-connectors) blind-mate coax (1.27 mm axial, 0.5 mm radial) | Not picked: much larger than the 66.8 × 38.6 mm body allows, open sockets on the radio, higher cost |
| C. No dock, plug-in jumpers | Kept as the backup |

Also rejected: docking through the battery shoe (the battery would have to come off) and contactless RF coupling across four bands at these powers.

## Open before it is built

- **FCC modular approval.** The HaLow, LoRa and Wi-Fi modules are certified with a defined antenna path. A switch and a second antenna path are host changes that may need host testing or a permissive change under each module's grant (FCC KDB 996369). This adds to the mast antenna grant check in [mast-links.md](mast-links.md). Unverified.
- **Wi-Fi port-to-chain map** on the bench cards ([GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37)).
- **USB 3.0 desense** of 2.4 GHz if the dock Ethernet runs at SuperSpeed, measured with the coexistence tests in [v1-rf-coexistence.md](v1-rf-coexistence.md).
- **Contact life** of the spring coax probes and pads with dust and damp; the radio comes in from the field dirty.
- **Thermal.** The contact plate covers part of the back wall below the CM5 heat pad ([GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12)).
- **Enclosure fit** of the patch, bushings and strike plates on the selected body, and the RF and GPIO connections inside ([GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7), [GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9)).
