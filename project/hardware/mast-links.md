# Mast links (home hub)

**Status:** Selected topology, 2026-11-17 (D-062). Radio models are Candidate. Nothing was bought, and no node software supports the wired mesh link yet.
**Visual write-up:** [Mast-to-Mast Links](https://claude.ai/artifact/VxW7wNcMgJYCLcdc2Qn5Ys) (maps, side-view clearance, options compared). Terrain scripts: project files `mast-links/` (`hub.py`, `prof.py`).

## Tags

- **Verified:** read from the linked source on 2026-11-17.
- **Calculated:** derived here from public terrain data or free-space maths; method stated.
- **Unverified:** an assumption or typical figure, to be checked on the bench or at the site.

## What was decided

Masts link to each other over 5 GHz directional radios in a star around a home hub. HaLow and the 2.4 GHz mesh stay on every mast, unchanged, as the people-facing radios and as the automatic backup between masts.

- **Home hub.** A standard mast node, the same as every other mast: HaLow, Wi-Fi, LoRa control radio (D-057), GNSS and the node web app. On top of that it carries three 5 GHz point-to-multipoint sector radios, 120° each, covering 360°. A fourth sector is added only if one sector gets crowded.
- **Town masts.** Four standard mast nodes around town (`tak.role: mast`, [docs/atak.md](../../docs/atak.md)). Each adds one 5 GHz dish radio aimed at the home sector that covers it.
- **People still reach a mast over HaLow and Wi-Fi.** The dishes carry mast-to-mast traffic only. They do not extend how far a person's radio reaches a mast.

## Why a home hub

Calculated from 30 m public terrain data (AWS terrarium tiles, the same data as the [Eagle Mountain mast map](https://claude.ai/artifact/EAbZy3pbFRQQrzmAxV58xG)). Assumptions: home at Eagle Mountain city center (40.3141 N, 112.0069 W, an assumption until Justin gives the real spot), town = 5 km circle, all masts 15.24 m (50 ft), person 1.8 m, HaLow reach to a person 4 km (Unverified, never measured), mast-to-mast paths need 60% of the first Fresnel zone clear at 5.8 GHz with k = 4/3. No buildings or trees in the data.

| Layout | Town area in sight of a mast | Radios needed |
|---|---|---|
| Home hub + 4 town masts (selected) | 91% (62% by two or more) | 3 sectors + 4 dishes |
| Home hub + 3 town masts | 88% | 3 sectors + 3 dishes |
| Three valley masts in a dish triangle | 82% | 6 dishes |
| One mast at home, nothing else | 58% | none |

- 83% of the town area can see a 50 ft mast at home, so most town-mast spots work.
- The four town-mast spots the search picked, measured from home: south 2.1 km, north-west 2.0 km, east 3.5 km on the Lake Mountains foothills (1,853 m), north 4.0 km (1,603 m). These are terrain picks, not sites anyone owns or has power at.
- Most of the gain over the triangle comes from having four town masts and one on the foothills, not from the hub itself.
- Point-to-multipoint does not suit three masts on the valley floor: seen from the middle mast, the other two are 157° apart. From home the town masts are spread all round, so sectors fit.

## Link budget

Calculated, free space. LiteBeam 5AC (23 dBi) at 20 dBm to a 16 dBi sector at 4 km is about −63 dBm, enough for high rates. HaLow omni to omni between masts at 4.7 km is about −71 dBm (24 dBm, 6 dBi each end, 1 dB cable each end): it works, slowly, and shares airtime with every person on the channel. At 5.8 GHz the first Fresnel zone at mid-path of a 4.7 km link is about 8 m tall, against about 20 m at 915 MHz, so the 5 GHz link clears rooftops that the HaLow path brushes.

## Candidate radios

List prices are for scale only. Purchasing lives in Linear, not here.

| Role | Candidate | Verified facts (2026-11-17) |
|---|---|---|
| Home sector | [Ubiquiti LiteAP AC (LAP-120)](https://store.ui.com/us/en/products/lap-120) | $89, 120° sector, 16 dBi, 8 W max |
| Town mast dish | [Ubiquiti LiteBeam 5AC](https://store.ui.com/us/en/products/lbe-5ac-gen2) | $65, 23 dBi, 450+ Mbps, 7 W max, 24 V passive PoE |
| Town mast dish, longer reach | [MikroTik LHG XL 5 ax](https://mikrotik.com/product/lhg_5_ax_xl) | $119, 27 dBi, 5 W max, 12–28 V passive PoE, −40 to 70 °C |

The sector and dish should come from the same vendor so they speak the same protocol. Mixing vendors is not planned.

Rules: 47 CFR 15.247 ([eCFR](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-C/subject-group-ECFR2f2e5828339709e/section-15.247)) lets fixed point-to-point links at 5725–5850 MHz use high-gain antennas with no power cut. At 2.4 GHz power drops 1 dB per 3 dB of extra gain, and at 902–928 MHz 1 dB per 1 dB, which is why the backbone does not use 900 MHz or 2.4 GHz dishes.

## How it joins the mesh

1. Each radio runs as a transparent bridge.
2. **Town mast:** the dish plugs into the node's sealed Ethernet port (D-022) through its PoE injector. No switch.
3. **Home hub:** the three sectors plug into a small PoE switch, and the switch plugs into the node's Ethernet port.
4. The whole star is one VLAN. On each node that VLAN on `eth0` joins `bat0` as a `batadv_hardif`, next to `batmesh0` (HaLow) and `batmesh1` (2.4 GHz). A star has only one wired path between any two masts, so one VLAN cannot loop.
5. The VLAN must never be bridged into `br-ahwlan` ([docs/networking.md](../../docs/networking.md)). That would join two masts' client LANs through the radios while `bat0` also joins them, which is a loop.
6. Set `throughput_override` on that hardif to the radio's real rate. Without it batman-adv reads the cable as 1 Gbps. The netifd proto in [packages](https://github.com/ghostnet-labs/packages/blob/main/routing/batman-adv/files/lib/netifd/proto/batadv_hardif.sh) already passes the option to `batctl`.
7. batman-adv V then prefers the dish path and falls back to HaLow or 2.4 GHz by itself if it drops.
8. If the Starlink mast is the mesh gate, its Ethernet port is also the WAN (docs/networking.md), so that mast needs a VLAN-capable switch to carry WAN and the star VLAN apart.

**Routing algorithm.** The mesh already runs BATMAN_V: the node app writes `routing_algo 'BATMAN_V'` on `bat0` ([openmanetd internal/network/uci_network.go](https://github.com/ghostnet-labs/openmanetd/blob/main/internal/network/uci_network.go), checked by `setup_compat_test.go`), and [docs/networking.md](../../docs/networking.md) says the same. BATMAN_V picks routes by estimated throughput, so a dish link at a few hundred Mbps beats a HaLow link at a few Mbps with no extra work. Details:

- On Ethernet, BATMAN_V reads the link speed from the port (1000 Mbps), hence `throughput_override` above.
- The whole star is one VLAN, so one `throughput_override` value covers every neighbor on it. Set it to the slowest sector link, not the fastest. Two town masts in the same sector talk dish to sector to dish, which batman-adv sees as one hop.
- Unlike a Wi-Fi hop, BATMAN_V does not halve the estimate when traffic arrives on one interface and leaves on a different one (Ethernet in, HaLow out), so routes that mix the dish and HaLow are not penalized beyond the normal hop penalty.

The node app does not create this wired mesh link today. It would be one new setting. Not started.

## Mast build: node on the ground, antennas up the mast

**Status:** Selected, 2026-11-17 (D-063). Coax, antenna and surge parts are Candidate; nothing bought.

Each mast node stays in a box at ground level. Only antennas go up the pole, so field radios reach the mast's antennas from far off while the node stays easy to reach. No separate access point is needed: the node is the access point for field radios (HaLow, 2.4 GHz mesh) and for phones (5 GHz, D-055). The home hub is built the same way, with its three sectors on the pole.

| Item | Where | Feed |
|---|---|---|
| HaLow omni | Very top of the pole, so nothing shadows it | LMR-600 coax |
| LoRa antenna (B-28) | 1 to 2 m below the HaLow omni, because both use 902–928 MHz; size the gap with the isolation check on [GHO-90](https://linear.app/ghostnet-labs/issue/GHO-90) | LMR-400 coax |
| 2.4 GHz mesh omni | Below the LoRa antenna. The AW7916 2.4 GHz radio is 2x2, so use a dual-feed omni or two antennas | Two LMR-600 runs |
| 5 GHz dish or home sectors | Below the omnis, pointing sideways. Radio and antenna are one unit | Ethernet, PoE injector at the base |
| GNSS antenna | On the node box at ground level; a fixed mast does not move | Node's own lead |
| 5 GHz phone access point | On the node box at ground level; phones at a mast are near its base | Node's own antennas |

### Losses and gains

| Choice | Effect on a field radio | Basis |
|---|---|---|
| 50 ft of coax plus jumpers and a surge protector | LMR-600: 1.8 dB at 900 MHz, 2.7 dB at 2.4 GHz. LMR-400: 2.5 dB and 3.9 dB | Calculated from the [LMR-600](https://www.rfparts.com/old_site/pdf_docs/LMR/LMR-600.pdf) (2.5 / 4.4 dB per 100 ft) and [LMR-400](https://www.rfparts.com/old_site/pdf_docs/LMR/LMR-400.pdf) (3.9 / 6.8 dB per 100 ft) datasheets, plus an assumed 0.5 dB for jumpers and the protector |
| Mast antenna at 15 m instead of 3 m | About 14 dB past about 330 m; net of LMR-600 loss about +12 dB on HaLow, close to twice the range over flat ground. In town it mostly clears roofs and trees | Calculated, two-ray model: 20 log10(15/3); breakpoint 4 h_t h_r / λ with h_r = 1.8 m at 915 MHz. The 30 m terrain data shows only 88% vs 91% town coverage for 3 m vs 15 m because it has no buildings or trees |
| 6 dBi HaLow omni instead of the 1 dBi certified antenna | About 5 dB both ways | Calculated. Legal only if the antenna is on the module's grant: [47 CFR 15.204(c)(4)](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-C/section-15.204) allows only same type and equal or lower gain without retesting, and the GW16170's certified antenna is the Pulse W1063, 1.0 dBi ([v1-rf-coexistence.md](v1-rf-coexistence.md)). Unverified whether its grant lists any higher-gain antenna |
| Mast-top amplifier | Not used | 47 CFR 15.204(a) and (b) bar an external power amplifier on a Part 15 radio unless radio, amplifier and antenna were authorized together as a system. The height gain makes one unnecessary |

### Lightning and grounding

- Ground each coax shield at the top of the mast and again at the entry.
- Bring every coax and the dish Ethernet through one grounded entry panel with a surge protector on each line, bonded to the mast ground rod and the building's grounding electrode, following NEC Article 810. Parts not chosen.
- Leave a drip loop on each cable before the entry.

### Open before a mast is built

- **Antenna grants.** Check the GW16170, RAK3172 and AW7916 grants before choosing any antenna other than a certified one.
- **Node antenna ports.** The node's antenna connectors and any bulkheads for a mast jumper follow the enclosure design (B-21); confirm them before ordering coax ends.
- **Rough parts per mast** beyond the node and pole (Unverified, typical prices): 900 MHz omni $50–150, LoRa omni $30–80, dual-feed 2.4 GHz omni $60–150, about 200 ft of coax $300–600, N connectors $10–15 each, four coax surge protectors $25–60 each, ground bar, rod and grounding kits $50–150; about $600–1,200.

## Home hub radio plan

- The node's own 5 GHz radio is the EUD access point (D-055). Keep the sectors on 5 GHz channels apart from it, and mount the sectors away from the node's antennas. Exact channels and spacing: Unverified, to set at install.
- HaLow, the LoRa control radio and the 2.4 GHz mesh are unaffected by the 5 GHz sectors.

## Known weaknesses

- **One spot everything fast depends on.** If home loses power or its mast, every dish link drops. Town masts still reach each other and home over HaLow: 5 of the 6 town-mast pairs have a clear 915 MHz path (Calculated). North to south (6.0 km) does not.
- **Jamming at the hub.** Each sector listens across 120°, so a jammer near home inside one sector's slice degrades every town mast in that sector. The town masts' dishes reject jammers off their beam, by a typical 20 to 30 dB (Unverified, to measure on the real antenna). This is weaker than a dish triangle, where both ends are dishes. Fits D-056 only because HaLow remains as the backup.
- **The hub is easy to find.** A fixed, busy transmitter can be located with direction finding, and it marks the owner's home.
- **Fixed channel.** These radios do not hop channels quickly. A jammer parked on the backbone channel drops it until the channel is changed.
- **Power at home:** about 24 W for three sectors at their stated maximum, plus the PoE switch. Each town mast adds up to 7 W (LiteBeam) or 5 W (LHG XL). A battery backup at home is assumed.

Later options, not selected: one dish between two neighboring town masts (north-west to south is 3.6 km) so losing home does not drop every fast link; a hilltop hub on the Lake Mountains (2,194 m, about 4.5 km east), where all three valley masts fit inside a 42° slice.

## Open before any purchase

- Home location (city center is assumed) and real town-mast sites with power and permission. Rerun `hub.py` with them.
- HaLow reach from a mast to a person, which sets coverage. Never measured.
- Free bench check: two nodes joined by an Ethernet VLAN as a `batadv_hardif`, then unplug HaLow and confirm failover.
