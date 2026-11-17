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

The node app does not create this wired mesh link today. It would be one new setting. Not started.

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
