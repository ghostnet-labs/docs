# Historical Maer beast POC planning study — 2026-10-04

This is a provenance snapshot of Maer_Beast_POC_Builds.md. It includes the initial benchmark and later discussions; it is not authoritative for requirements, selected parts, purchase quantities/prices or live status. Use [Maer requirements](../requirements/maer-capabilities.md), the [project ownership index](../README.md), and Linear GHO-49 through GHO-55 instead.

Correction established during project reconciliation: D-004 records that two HaLow radios on one Linux host were unsupported in the Morse engineer's 2026-08-26 statement. Any single-host dual-HaLow proposal below is unverified and gated by GHO-39; physical feasibility does not establish driver support.

---

# Maer: three beast-mode POC builds

Design date: October 4, 2026. Status: proposed engineering builds, documentation checked; no hardware assembled or measured. Quantities below are **per complete node**, unless stated otherwise.

## Design decision

Build all three platforms around the same demanding radio payload. Choose **CN9130 + ClearFog Pro** for the strongest networking experiment, **CM5 + official IO board** for the software reference and application-compute experiment, and **DART-MX8M-PLUS + Sonata** for the industrial module and hardware-supervisor experiment. These are feature-complete architectural targets, with procurement and integration gates explicitly listed below. They are not yet purchase-ready validated assemblies.

Size, active cooling, battery chemistry and power architecture are open. Preserve the intended capabilities: HaLow-first backhaul, simultaneous 2.4 GHz mesh and 5 GHz EUD access, GNSS/PPS, radio-managed voice/PTT, wired networking, offline headless administration, hardware-aware telemetry, charging while operating and at least ten seconds of full-node battery-swap continuity. Add continuous aircraft tracking and public-safety/aviation receive monitoring as accepted features. 5 GHz node-to-node backup must coexist with EUD access; the clarified redundancy section below defines the current allocation.

## Accepted feature update: aircraft tracking and scanner reception

Updated October 4, 2026 following the radio-role and SDR discussion. This section takes precedence over the original benchmark payload below. The original dual-4x4 mesh-card/external-AP assembly remains useful as a performance comparison, but is no longer the required radio topology. Its procurement totals and power/runtime estimates exclude the new receive payload and must be revised before purchasing.

| Accepted feature | POC implementation target | Limits and qualification |
|---|---|---|
| Aircraft tracking | Continuous 1090 MHz ADS-B reception; add continuous 978 MHz UAT for US coverage. Show aircraft identifier when transmitted, position, altitude, motion, source and age on the offline EUD map | Reception requires usable RF coverage and transmitted data; not every aircraft broadcasts usable position. UAT ground information/weather is conditional on ground-station reception |
| Public-safety scanner | Selected analog FM and unencrypted P25 Phase I/II systems, including trunked control-channel tracking and call reception | Preload the operating area's frequencies, system identifiers and talkgroups offline. Other protocols require separately verified decoders. Encrypted calls are identified where possible and provide no intelligible audio |
| Aviation voice | Selected airband AM reception with local frequency presets and EUD audio selection | Uses available scanner receive capacity. Continuous aviation voice alongside two occupied scanner windows requires another independent path |
| EUD controls | Local aircraft map, scanner selection, audio playback, receiver status and optional recording | Explicitly display stale tracks, unavailable receivers, encryption and exhausted tuner/decoder capacity |
| Mesh sharing | Timestamped aircraft reports with deduplication and selected compressed audio streams | Do not send continuous raw I/Q over HaLow. Prioritize mesh control and user voice; sharing must tolerate outages and recover without duplicate-track floods |

### Proposed receive allocation for every beast POC

Four independently tunable receive paths are the engineering target, not necessarily four separate devices. Dedicated ADS-B USB receivers plus a dual-tuner scanner SDR are one candidate arrangement. No exact receive BOM is locked yet.

| Receive path | Assigned role | Benefit of its independence |
|---|---|---|
| RX1 | Fixed 1090 MHz aircraft reception | Scanner tuning never interrupts this aircraft feed |
| RX2 | Fixed 978 MHz UAT reception | Both aircraft bands remain active simultaneously |
| RX3 | Scanner control and voice channels within one usable instantaneous bandwidth window | Can decode multiple in-window channels if software and compute allow; one tuner is not necessarily one call |
| RX4 | Second scanner frequency window; otherwise a selected aviation channel | Covers calls outside RX3's captured span or another system without abandoning RX3. It cannot provide every out-of-window service simultaneously |

A fifth path is justified only if continuous aviation audio must remain available while both scanner windows are occupied, or a measured local system needs additional frequency coverage. More receivers on the same antenna do not automatically increase range. A separate antenna may enable diversity, but only with implemented selection/combining logic and measured benefit.

An SDRplay RSPduo is a scanner candidate because it has two tuners, subject to simultaneous-mode bandwidth, Linux ARM64 API availability and driver validation on each compute. Do not equate its single-tuner bandwidth with dual-tuner operation or assume it replaces both dedicated aircraft receivers. SDRtrunk can pool supported tuners and decode multiple channels inside their captured bandwidth. Reserve aircraft receivers explicitly: SDRtrunk otherwise attempts to claim discovered SDRs. Use stable receiver identities and service ownership.

### RF, compute and integration acceptance

| Check | Required evidence |
|---|---|
| Concurrent operation | Aircraft feeds, selected scanner calls, HaLow backhaul, 2.4 GHz mesh and 5 GHz EUD AP all run together without receiver ownership conflicts or unexplained sample loss |
| Own-transmitter interference | Compare aircraft message rate and scanner sensitivity with HaLow/Wi-Fi idle and under transmit load. Repeat with at least 10 nodes in approximately 100 square feet, including sustained operation |
| RF construction | Qualify band-select filters, high-linearity amplification where needed, shielded receiver compartment, converter/USB noise control and antenna placement. Additional SDRs do not cure front-end overload |
| Antenna distribution | Receiver count does not dictate protruding antenna count. Evaluate a 978/1090 antenna with suitable diplexing and a separate scanner antenna; characterize insertion loss and isolation. Same-band splitting adds loss and any active distribution stage must tolerate nearby transmitters |
| Compute and USB | Record CPU load per decoder/call, dropped samples, USB topology, memory use, temperatures and mesh latency under simultaneous decoding and recording on all three platforms. Reassess the compute recommendation from measurements |
| Power continuity | Measure the added receiver/filter/LNA load, revise the total power and runtime budgets, and repeat full-node pack-swap tests with receive services active |
| Recovery | Confirm cold boot, unplug/replug, scanner tuner exhaustion, unsupported/encrypted calls, stale aircraft data and service restart have visible states and do not take down networking |

The external-antenna preference remains ideally three or fewer, with six as the upper target for the eventual node. POC packaging is unrestricted; antenna distribution is a measured experiment rather than a promise of lossless sharing.

### Current mesh/AP roles and coordinated channel changes

HaLow is the primary range-extension backhaul; 2.4 GHz is an alternate mesh path and 5 GHz serves nearby user devices. A GW16170 HaLow radio plus a concurrent dual-band AW7916-AED host radio is a candidate for reducing module count, pending exact driver/firmware AP-plus-mesh validation. Keep dedicated radios as the comparison build. SDR receive monitoring supplements these radios; it is not a turnkey replacement for their Wi-Fi/HaLow PHY and MAC.

Channel management must combine peer observations, channel occupancy, retries and link quality; agree a future switch time; preserve an alternate control path; and provide rendezvous/rollback after missed switches. Apply hysteresis and permitted regional channels. Validate HaLow channel-switch support and phone reconnection behavior. Do not let nodes independently retune and partition the mesh. The proposed sub-2-GHz scanner receivers cannot directly monitor 2.4/5-GHz spectrum; use networking-radio telemetry or separate suitable instrumentation for that experiment.

Primary references checked October 4, 2026: [SDRtrunk tuner capabilities and ownership](https://github.com/DSheirer/sdrtrunk/wiki/Tuners), [SDRplay RSPduo](https://www.sdrplay.com/product/rspduo/), [FlightAware receiver filtering](https://support.flightaware.com/hc/en-us/articles/37946861012375-Signal-Amplifiers-and-Filters), and [FAA ADS-B information](https://www.faa.gov/air_traffic/technology/adsb).

## Clarified redundancy requirement

The user's subsequent clarification makes 5 GHz node-to-node backup a required capability, superseding its earlier optional status. Required roles are: HaLow primary long-range node contact and data/metrics backhaul; 2.4 GHz alternate node transport when coverage or capacity favors it; 5 GHz EUD access plus another node transport; and separate aircraft/public-safety monitoring. Select routes using measured reachability, loss, latency and capacity, rather than a permanently fixed band preference. Metrics/control receive priority; data streaming is admission-controlled against actual available capacity.

An isolated or powered-off node must rediscover an authenticated mesh after missing one or multiple channel changes, once at least one compatible path becomes physically reachable. Receiving an announcement before departure is insufficient. The node must retain its allowed channel/width search list and mesh credentials offline; returning nodes must not require internet, cellular or manual EUD retuning of the mesh.

### Recommended POC networking allocation

| Independent radio role | Purpose | Qualification |
|---|---|---|
| HaLow A | Primary long-range data path | Candidate GW16170; exact host and mesh support remain gates |
| HaLow B | Alternate long-range channel, authenticated recovery advertisements, discovery and staged migration | Second independent HaLow transceiver; multi-device driver enumeration and adjacent-channel coexistence must be tested. May carry spare-capacity data, but preserve recovery/control service |
| 2.4 GHz mesh | Alternate node-to-node data/control | A single radio can rediscover by scanning, but cannot provide uninterrupted simultaneous service on two independent channels. Add another 2.4 mesh radio if that continuity becomes required |
| 5 GHz mesh | Additional node-to-node backup | Independent of the EUD AP for this unrestricted POC, allowing mesh retuning without retuning the user's AP |
| EUD AP, 5 GHz preferred | Local user access | Independently retain AP service during mesh channel changes |
| EUD AP, 2.4 GHz fallback | User access when 5 GHz is unusable or unavailable | Dual-band AP may provide both EUD roles if hardware truly supports concurrent bands. Phone reassociation is distinct from node routing failover; seamless roaming is not assumed |

These are six concurrently available radio roles, not a promise of six modules or six antennas. A verified concurrent dual-band module may implement two roles. Sharing an AP and mesh interface on one PHY may be possible, but often imposes a shared channel and hardware/driver constraints; this is a later consolidation experiment, not the beast POC's continuity baseline. Antenna sharing and the eventual protrusion target still require RF measurements.

### Channel discovery and migration behavior

1. Connected peers share channel-quality observations over any working transport. Agree a versioned plan identifying mesh, band, channel, width and activation time. Authenticate coordination and discovery information.
2. Prefer bringing up the alternate HaLow path on the destination channel before moving the primary path. Verify actual peer reachability; do not simultaneously abandon both long-range paths. The policy must also handle competing decisions in temporarily separate mesh partitions.
3. Keep discovery advertisements on active channels and provide a known rendezvous schedule/channel set. A permanently fixed control channel alone is insufficient because it may also be interfered with. Recovery service must advertise current configurations, not merely the last planned switch.
4. A returning node tries its last-known configuration, any reachable alternate band, the rendezvous procedure, then the supported channel/width search list. Matching authenticated advertisements allow it to rejoin and learn current routes. Define and measure the recovery-time target after compatible RF coverage returns.
5. Test missed announcements, multiple switches while absent, cold boot, loss of the rendezvous channel, separated partitions choosing different channels, a failed HaLow radio, and nodes reachable only over HaLow. A node outside all compatible RF coverage cannot learn live changes until a path becomes reachable.

Two HaLow radios improve simultaneous discovery, staged migration and hardware resilience, but do not guarantee immunity to interference. Nearby same-band transmissions may desensitize the other receiver even on a different channel. Qualify channel separation, filtering, power control and scheduling under the dense-node test. The selected GW16170 dual-device and extended-channel-switch behavior is not yet validated on any of the three candidate computes.

This allocation supersedes the earlier one-HaLow/concurrent-dual-band simplification. Procurement totals, USB/PCIe topology, antennas and power estimates below remain the original benchmark until the expanded radio BOM is qualified and recosted. Aircraft/scanner SDRs remain a separate receive subsystem and are not substitutes for these networking transceivers.

## Settled networking capability and controller requirement

This requirement supersedes fixed band-to-task assignments above. HaLow, 2.4 GHz and 5 GHz must each support node transport, discovery/recovery, telemetry, voice/application traffic and access for compatible EUDs. HaLow EUD access requires a HaLow-capable endpoint or a suitable adapter/bridge; conventional phone Wi-Fi must not be assumed to support HaLow. Aircraft/public-safety reception remains separate.

The controller selects paths per destination and traffic class using reachability, measured available capacity, latency, jitter, loss, retry rate and channel occupancy. Favor reliable control/recovery, low-latency voice and spare capacity for bulk transfers. Maintain hysteresis and session stability, react to failed links, reserve essential-service capacity, and expose selection reasons and manual overrides through the EUD. Channel changes require peer coordination and disconnected-node rediscovery. Routing selection does not by itself provide seamless transport migration, aggregation or duplication.

Acceptance: with either two other networking bands disabled, demonstrate surviving-band mesh transport, management, metrics, voice and compatible EUD access, including recovery after missed channel changes. Record interruptions and capacity limits explicitly.

### Physical feasibility and allocation experiment

With POC size/power/cooling unrestricted, the architecture is physically plausible using standard networking transceivers and separate SDR receivers. A candidate compact radio allocation is two USB HaLow modules plus two PCIe dual-band-concurrent Wi-Fi modules, producing two independent radio paths in each networking band. AsiaRF AW7916-AED or its mini-PCIe counterpart are candidates for concurrent 2.4/5 operation; exact carriers, electrical interfaces, driver modes, antennas and multi-device support require validation before selection.

Each radio can be assigned eligible roles by the controller; supporting a role does not guarantee simultaneous AP/mesh/scanning on independent channels. Two HaLow paths can serve separate AP and mesh channels, or old/new mesh channels during migration. They cannot provide three independent HaLow channels at once. Qualify same-channel AP-plus-mesh concurrency, temporary role reassignment or a third HaLow radio if uninterrupted HaLow EUD access plus two-channel migration is required. Use the same reasoning for 2.4/5 GHz.

Physical gates are same-band receiver desensitization, RF filtering/isolation, antenna placement/distribution, powered USB and PCIe expansion, decoder CPU load, sustained cooling and full-load power continuity. Separate channels alone do not establish simultaneous-transmit/receive isolation. Evaluate time scheduling when isolation is inadequate. This is feasible as an engineering POC, not a validated guarantee of zero interruptions or a completed compact V1 layout.

### Accepted RF coexistence and scheduling decision

Decision recorded October 4, 2026: maximize practical filtering, shielding, antenna isolation and sensible channel/transmit-power selection first. Use adaptive scheduling only for radio combinations that measurements show interfere; retain independent simultaneous operation elsewhere. Scheduling is a resilience mechanism, not the default requirement for every mesh transmission.

Protect control/recovery and voice/PTT capacity. Throttle or defer bulk transfers before essential traffic. Prefer local coexistence decisions where sufficient; coordinate with neighboring nodes when their transmissions cause interference. Ten or more nodes in approximately 100 square feet must be tested because silencing a transmitter inside one enclosure does not silence nearby nodes.

| Scheduling level | Engineering difficulty | Principal tradeoff |
|---|---|---|
| Traffic priority and bulk rate limiting | Relatively straightforward | Lower bulk-transfer rate; does not guarantee RF silence |
| Alternating conflicting radios within a node | Moderate and driver/firmware dependent | Reduced simultaneous capacity and packet waiting time |
| Neighbor-coordinated transmit/receive windows | Substantial | Synchronization, hidden-neighbor handling, topology changes and partition/rejoin recovery |
| Guaranteed precise quiet windows across mesh and EUDs | Very high; may require firmware support | Compatibility constraints; ordinary EUDs cannot be assumed to follow a custom schedule |

Stopping application traffic is not equivalent to stopping RF emissions: hardware/firmware queues, acknowledgments, beacons and retries must be accounted for. Verify actual radio activity and timing controls before relying on quiet windows. HaLow sleep/airtime features must not be assumed to provide cross-radio mesh scheduling.

Record airtime allocation, achieved goodput, voice latency/jitter/loss, control reliability and scanner/aircraft decoding with scheduling enabled and disabled. A roughly equal alternating schedule gives each radio about half the allocated airtime before overhead; delivered throughput can nevertheless improve if scheduling avoids heavy interference and retries. Shorter windows reduce waiting but may increase overhead. Do not claim an exact throughput or latency penalty before measurement.

External aircraft and scanner transmitters do not follow Maer's schedule. Receive protection can improve decoding during quiet periods but cannot recover messages or audio missed during interfering transmissions. Show monitoring degradation through receiver metrics where measurable.

Acceptance must include voice plus bulk traffic, both local and neighboring interference, moving/hidden peers, lost timing or coordination, and disconnected-node return. Define a fallback that preserves control/recovery when scheduling coordination fails, and expose the active schedule, its reason and capacity impact in the EUD. Hard deterministic mesh-wide scheduling remains a conditional experiment rather than a locked implementation choice.

Reference: [Linux mac80211 queue and driver behavior](https://cdn.kernel.org/doc/html/latest/driver-api/80211/mac80211.html).

## Platform comparison

| Build item | CM5 beast POC | CN9130 beast POC | DART-MX8M-PLUS beast POC |
|---|---|---|---|
| Compute selection | **CM5116064: 16 GB RAM, 64 GB eMMC, wireless**; integrated wireless reserved for recovery/service | **8 GB RAM, 64 GB eMMC CN9130**, ClearFog Pro bundle; confirm exact module speed/grade with supplier | **Current commercial V2 starter-kit module: quad A53 at 1.8 GHz, 4 GB RAM, 16 GB eMMC**; quote larger-memory configuration separately if available |
| Carrier | **Official Raspberry Pi CM5 IO Board**; exposed GPIO, UART and fan connector | **ClearFog CN9130 Pro**, not Base; two mini-PCIe sockets and stronger Ethernet topology | **Sonata Board** from the current starter kit; usable peripheral headers and debug access |
| 2.4 GHz mesh | AW7915-NP1, dedicated to 2.4 GHz, four antenna chains | Same radio in first native mini-PCIe PCIe socket, subject to slot-power qualification | Same radio through powered expansion chassis |
| 5 GHz mesh | Second AW7915-NP1, dedicated to 5 GHz, four antenna chains | Same radio in second native mini-PCIe PCIe socket, subject to lane configuration and slot-power qualification | Same radio through powered expansion chassis |
| Host-radio expansion | M-key → Delock 64134 riser → ASM1184 PCIe-Packet-Switch-4P → two ACPCX1-M01 radio adapters | Native PCIe paths; powered mini-PCIe interposers if the carrier cannot sustain 3.3 V/3 A per radio | Active PCIe-connected Sonata M-key slot → same riser/switch/adapters as CM5; confirm slot designation for purchased revision |
| Radio expansion limit | Both mesh cards share **PCIe Gen 2 x1**; about 500 MB/s before protocol and software overhead, not two full-speed links | Native socket layout avoids adding the CM5-style shared expansion switch; actual negotiated links and SerDes configuration must be verified | Both mesh cards share the SoC's **one PCIe lane**; ASM1184 makes the proposed expansion path Gen 2 x1 even if the root supports a higher rate |
| HaLow | GW16170, external powered USB/E-key bench carrier | Same; USB path keeps both mini-PCIe slots available for Wi-Fi | Same |
| EUD access | U7 Pro XG on the Ethernet switch, separate from mesh cards | Same | Same |
| Compute-to-local-switch link | Dedicated **USB 3 → 2.5GbE**, retain native 1GbE for external/service connection | **Native 10GbE SFP+ → DAC**; retain carrier's native copper Ethernet ports | Dedicated **USB 3 → 2.5GbE**, retain native Ethernet for external/service connection |
| Storage | eMMC for OS; **1 TB USB SSD** for logs, packet capture and local content | Same; place SSD and low-bandwidth peripherals on powered hub | Same; 16 GB eMMC is sufficient for lean OS, with bulk data on SSD |
| Timing | mosaic-X5 USB data plus direct SoC GPIO PPS | Same, with verified GPIO level/pin mapping | Same, PPS to a real SoC GPIO; M7 supervision is an optional software extension |
| Audio | OpenVLM-compatible USB audio/PTT plus Kenwood-style speaker microphone | Same | Same |
| Cooling | CM5 active cooler, radio heatsinks, chassis airflow | SoM heatsink/fan, radio airflow, SFP+ cooling | SoM heatsink/fan, radio airflow; do not assume stock passive heatsink is enough |
| Software work | Closest to current CM5 firmware; new PCIe/radio/power/UI integration still required | OpenWrt board support is a useful starting point; Maer image and HaLow/voice/GPIO integration remain | Vendor BSP is a starting point; Maer/OpenWrt port, drivers, GPIO and optional M7 work remain |
| Biggest strength | A76 CPU and abundant RAM for services, diagnostics and software development | Native networking and cleaner multi-radio expansion | Vendor module/carrier ecosystem plus M7/NPU peripherals for future experiments |
| Remaining tradeoff | Shared PCIe; USB Ethernet; more adapters | More expensive kit; older A72 application CPU; native radio-slot power is unproven | A53 application CPU, smaller stock RAM, shared PCIe, largest firmware-port burden |

The CPU descriptions support an architectural expectation, not measured Maer rankings. CN9130 is the networking favorite; it is not automatically the fastest application CPU. Extra CM5 RAM does not create PCIe bandwidth. The DART NPU does not accelerate routing or voice automatically.

Platform sources: [CM5 specifications](https://www.raspberrypi.com/products/compute-module-5/), [CM5 IO board](https://www.raspberrypi.com/products/compute-module-5-io-board/), [ClearFog CN9130](https://www.solid-run.com/embedded-networking/marvell-octeon-tx2-family/clearfog-cn9130/), [CN9130 Pro block diagram](https://www.solid-run.com/wp-content/uploads/2022/04/ClearFog-CN9130-SOM-Pro-block-diagram-1.png), [DART starter-kit configuration](https://shop.variscite.com/product/evaluation-kit/dart-mx8m-plus-evaluation-kits/), [Sonata carrier documentation](https://variscite.com/carrier-boards/sonata-board/).

## Common radio, timing, voice and networking payload

| Subsystem | Quantity / selected part | Purpose and improvement over current POC | Integration condition |
|---|---|---|---|
| Host Wi-Fi mesh | **2 × AsiaRF AW7915-NP1**, MT7915, band-selectable 4T4R | Independent 2.4 and 5 GHz paths with four RF chains each; EUD AP duties use separate hardware | Qualify mt7915/mt76 mesh mode and HE behavior on exact kernel; 3.3 V/3 A supply target per card; four chains do not guarantee four-stream range/throughput |
| Wi-Fi antennas | **8 × matching 2.4/5 GHz antennas and 8 pigtails**, connector type matched to purchased cards | Four antennas per mesh card; replace original three-antenna layout | Select vendor-approved connector/gain combinations; initially use modest-gain omnis, then compare directional antennas as a separate RF experiment |
| Long-range HaLow | **1 × Gateworks GW16170 MM8108-M20** | Current high-power USB HaLow module rather than retaining the lower-power old POC module by default | Manufacturer pages disagree on 27.5 versus 28.5 dBm; use conservative 27.5 dBm planning ceiling and actual approved board/antenna settings; host mesh operation still requires driver/firmware qualification |
| HaLow power carrier | **1 × purpose-built USB 2/E-key 2230 bench breakout**, externally supplied 3.3 V with margin; Pololu D36V50F3 is a regulator candidate | Removes the old small USB adapter's power bottleneck and avoids consuming PCIe | Engineering item, not a verified purchasable assembly. Implement USB differential routing, reset/control pins as required, local capacitance, protection and no host-VBUS backfeed. Regulator alone is not a complete carrier |
| HaLow antenna | **1 × suitable 902–928 MHz antenna**, MMCX pigtail and bulkhead | Physically separate sub-GHz RF path | Match the module's permitted antenna configuration; stronger PA/antenna is not a promised distance multiplier |
| EUD AP | **1 × Ubiquiti U7 Pro XG** | Dedicated tri-band Wi-Fi 7 access with 10GbE port; supports local clients without adding another host PCIe radio | AP remains separate equipment. Maer integration requires control/telemetry work; 6 GHz capability is for the appropriate AP operating environment, not an assumed third outdoor mesh band |
| Local AP controller | **1 × CloudKey+ SSD UCK-G2-SSD** | Offline EUD-accessible AP configuration independent of Maer compute load | Direct Ubiquiti store currently sold out; distributor stock or replacement local controller must be confirmed. Configure local credentials and local management, no cloud dependency |
| Local switch | **1 × MikroTik CRS305-1G-4S+IN** | Four 10GbE SFP+ ports, VLAN-capable local network; useful even when host uplink is slower | Use hardware switching, not its small CPU as the Maer router; stable regulated 12 V supply |
| Copper transceivers | **2 × MikroTik S+RJ10** for CM5/DART; **1 × S+RJ10 + 1 × compatible DAC** for CN9130 | AP has copper 10GbE; USB Ethernet reaches switch at 2.5GbE; CN host uses DAC at 10GbE | Verify multi-rate copper negotiation. Space hot copper modules in nonadjacent switch ports and add airflow |
| PoE power | **2 × Tycon TP-DC-12BT60-10G**, one AP and one controller | Battery-backed standards-based PoE, without AC inverter or 1GbE injector bottleneck | Verify negotiated power class and cold start with each device; powered from protected node rail |
| Position/timing | **1 × SparkFun GPS-23088 mosaic-X5**, plus **1 × compatible active L1/L2/L5 antenna** such as SPK6618H | Multi-band GNSS, RTK capability, raw logs and direct PPS; substantial step above SAM-M10Q | Centimeter RTK needs corrections and suitable reception. USB provides data/configuration; PPS separately goes to SoC GPIO at correct voltage |
| Voice/PTT | **1 × OpenVLM-compatible CM108 design** plus **1 × compatible Kenwood two-pin speaker mic** | Completes node-side mic, speaker and hardware PTT rather than EUD-only voice | VLMKW0100 listing is sold out and lacks ESD/volume hardware. Assemble published design or source a completed protected board; validate HID/ALSA pairing, PTT polarity, mic bias and reconnect recovery |
| USB expansion | **1 × StarTech ST7300USBME**, externally powered | Ports for HaLow, voice, GNSS, SSD, UPS monitoring and expansion | Confirm purchased revision's total/per-port USB current budget; do not bus-power the entire payload |
| Bulk storage | **1 × 1 TB USB 3 SSD**, Samsung T7 Shield class | Packet captures, telemetry history, software recovery, offline files/maps as application scope permits | Not a substitute for eMMC boot testing; SSD traffic shares its USB path with other devices |
| Telemetry | UPS USB plus voltage/current sensing, temperature probes and fan tach capture | Hardware inventory, link metrics, timing state, battery reserve, thermal and fault visibility in EUD UI | Choose exact sensing/protection modules during wiring design; firmware/UI additions are required |

Primary sources: [AW7915-NP1](https://asiarf.com/product/wifi-6-11ax-4t4r-mini-pcie-module-mt7915-aw7915-np1/), [GW16170](https://www.gateworks.com/products/wireless-options/gw16170-mm8108-m20-802-11ah-halow-wifi-m2-card/), [U7 Pro XG specifications](https://techspecs.ui.com/unifi/wifi/u7-pro-xg), [CloudKey SSD](https://store.ui.com/us/en/category/accessories-advanced-hosting/products/uck-g2-ssd), [UniFi local management](https://help.ui.com/hc/en-us/articles/28457353760919-UniFi-Local-Management), [CRS305](https://mikrotik.com/product/crs305_1g_4s_in), [S+RJ10 thermal guidance](https://help.mikrotik.com/docs/spaces/ROS/pages/240156916/S%2BRJ10%2Bgeneral%2Bguidance), [Tycon DC PoE](https://www.tyconsystems.com/products/tp-dc-12bt60-10g/6026428000003329913), [mosaic-X5 breakout](https://www.sparkfun.com/sparkfun-triband-gnss-rtk-breakout-mosaic-x5.html), [GNSS hookup guide](https://docs.sparkfun.com/SparkFun_GNSS_mosaic-X5/), [VLM-KW listing and design links](https://www.buildsbyshane.com/shop/p/product-3-szb2y-gzh2r-tzhkx-xahl8), [USB hub manual](https://sgcdn.startech.com/005329/media/sets/ST7300USBME_manual/ST7300USBME_manual_Rev1.pdf), [3.3 V regulator candidate](https://www.pololu.com/product/4090).

## Expansion and USB wiring

| Connection | CM5 | CN9130 | DART-MX8M-PLUS |
|---|---|---|---|
| Mesh radio A | Shared switch slot 1 → ACPCX1-M01 → AW7915-NP1 | Native mini-PCIe A → AW7915-NP1; powered interposer if required | Shared switch slot 1 → ACPCX1-M01 → AW7915-NP1 |
| Mesh radio B | Shared switch slot 2 → ACPCX1-M01 → AW7915-NP1 | Native mini-PCIe B → AW7915-NP1; powered interposer if required | Shared switch slot 2 → ACPCX1-M01 → AW7915-NP1 |
| Main USB 3 path | Root port A → powered hub | Root USB 3 port → powered hub | Host port A → powered hub |
| 2.5GbE USB | Root port B, directly attached | Not needed; use native SFP+ | Other USB 3 host path, directly attached; confirm role/configuration |
| Hub allocation | P1 HaLow, P2 voice/PTT, P3 GNSS, P4 SSD, P5 UPS monitoring, P6 telemetry, P7 spare | Same | Same |
| PPS | Direct GPIO, Linux PPS + chrony | Direct GPIO, voltage/DT verified | Direct SoC GPIO, voltage/DT verified; not an I2C expander |
| AP data | Local switch → S+RJ10 → Tycon injector → U7 Pro XG | Same | Same |
| Controller data | Switch copper port → second PoE injector → controller | Same | Same |

**Important electrical gate:** Waveshare limits each switch slot's 3.3 V output to below 1.5 A; the Wi-Fi cards ask for 3 A. ACPCX1-M01 converts the slot's 12 V to local 3.3 V, but its public page does not establish a 3 A continuous rating. Obtain that rating or replace its power stage with a properly engineered supply/interposer. Never tie independent 3.3 V outputs together or inject power into host pins without isolating the existing supply. The switch is not a power-budget solution by itself.

Use the Delock riser only after verifying connector compatibility, M-key edge placement, reset/clock behavior and **no power backfeed**. Waveshare warns against directly plugging its switch into a PC motherboard; treat the full CM5/Sonata riser chain as an engineering qualification item. Its discontinued M2-PCIe-Switch-4P is deliberately excluded.

Sources: [Delock 64134](https://www.delock.com/produkt/64134/merkmale.html), [Waveshare switch documentation](https://www.waveshare.com/wiki/PCIe-Packet-Switch-4P), [ACPCX1-M01](https://asiarf.com/product/converter-card-mini-pcie-to-pcie-adapter-card/), [2.5GbE adapter](https://plugable.com/products/usbc-e2500). Exact adapter availability and compatibility are not established by connector shape alone.

## Power: deliberately oversized, with genuine field pack swapping

| Stage | Proposed selection / target | Behavior |
|---|---|---|
| Removable main pack | **25.6 V, 20 Ah LiFePO4 pack, 512 Wh nominal**, integrated BMS, matching external charger; exact pack SKU still open | Feeds the node and replenishes its reserve; no old 3S constraint |
| Main DC conversion | **Victron Orion-Tr 24/12-20 isolated converter**, adjusted to reserve charger input voltage, approximately 14.6 V | Provides regulated source into UPS; verify adjustment, derating and load-plus-charge capacity |
| Bench supply | Adjustable **14.6 V / 20 A supply**, source selected with a break-before-make switch before UPS input | Operate indefinitely and charge reserve on bench; reserve covers selector transitions; do not parallel arbitrary supply outputs |
| UPS/power path | **West Mountain Radio Epic PWRgate**, configured for actual LiFePO4 reserve specifications; start with 3 A reserve charging | Main source feeds load; loss of main automatically selects reserve; USB monitoring |
| Internal reserve | **12.8 V, 10 Ah LiFePO4 pack, 128 Wh nominal**, BMS and fuse; never removed during ordinary main-pack swaps | Keeps compute, radios, AP, controller, switch, USB devices and fans running while main pack is absent |
| Stable carrier/expansion rail | **Regulated 12 V, at least 100 W** branch; Mean Well DDR-120A-12 is a candidate rated 12 V/8.3 A | Stops raw battery changes reaching PCIe expansion and compute carriers |
| CM5 feed | Separate regulated **5.1 V / ≥5 A** branch with proper carrier input/USB-C source wiring; do not accidentally apply 12 V to official IO board | Full-load compute headroom; negotiate/advertise required USB-C current or use documented carrier feed |
| HaLow feed | Separate regulated **3.3 V with ≥3 A design headroom**, current limit and decoupling | Stable transmission bursts; characterize actual demand rather than using typical current alone |
| AP/controller feed | Protected UPS output → two DC PoE injectors | Full-node backup includes EUD access and configuration |
| Protection/measurement | Pack-adjacent fuses, branch fuses, reverse-polarity protection, appropriately rated connectors/wire, low-voltage cutoff and current sensing | Size from final measured loads and wire ampacity; UPS does not include internal fuses |

This architecture removes the ten-second energy squeeze rather than trying to stretch the old UPS. The reserve is a second battery, not the V1 supercapacitor bridge. UPS transfer continuity and every branch still need oscilloscope/traffic testing.

**Planning load:** 80–110 W at the UPS output, with a 150 W node distribution target and separate reserve-charge headroom. These are engineering allowances, not measurements. At 75% usable-energy allowance, main-pack runtime is approximately **3.5–4.8 hours** and reserve runtime approximately **52–72 minutes**. Include conversion loss in real measurements; 128 Wh at 75% is 96 Wh, vastly more than 110 W × 10 seconds = 0.31 Wh. A charged reserve is required for swapping. Main pack charges with its own compatible charger; PWRgate charges the reserve only.

Sources: [Epic PWRgate manual](https://www.westmountainradio.com/pdf/epic-pwrgate-manual.pdf), [Orion-Tr isolated converters](https://www.victronenergy.com/dc-dc-converters/orion-tr-dc-dc-converters-isolated), [DDR-120 specifications](https://www.meanwell.com/Upload/PDF/DDR-120/DDR-120-SPEC.PDF). Pack, 5 V supply and source selector remain wiring-design procurement items.

## Mechanical and RF layout

| Area | POC implementation |
|---|---|
| Chassis | Large open aluminum baseplate or ventilated equipment case; separate removable battery bay and RF mounting rail. No V1 size limit |
| Compute cooling | Direct heatsink contact plus controlled fan; target no thermal throttling during continuous traffic, capture and voice |
| Radios | Separate heatsinks and airflow; four antennas for each host Wi-Fi card. Keep Wi-Fi and HaLow antenna feeds short |
| RF separation | Place AP away from mesh antennas; select nonoverlapping channels where possible. Separate hardware removes shared-radio scheduling, but does not remove same-band RF interference |
| GNSS | Active antenna with clear sky view, separated from digital converters and RF transmitters; route PPS separately from high-current wiring |
| Power electronics | Separate from GNSS/RF; test switching-converter noise during receive and simultaneous transmit |
| Service | Protected test points, labeled wiring, serial debug and recoverable boot media; no operational dependence on external buttons or LEDs |

## Procurement picture and cost allowances

Prices are USD, before shipping/tax unless noted. Listed observations are not reservations. Allowances include uncertainty and must not be mistaken for supplier quotes. Assembly, PCB engineering, firmware development and professional RF test equipment are excluded.

| Common item group per node | Budget allowance | Sourcing observation |
|---|---:|---|
| Two host Wi-Fi cards | $60 | AW7915-NP1 listed $30 each; stock quantity not established. M.2 AW7915-AE1 rejected because maker says no mass-production plan and MOQ 500 |
| HaLow module and engineered powered breakout | $180–350 | GW16170 pricing/stock needs confirmation; includes carrier fabrication allowance, not completed design |
| Wi-Fi/HaLow antennas, pigtails and mounting | $180–300 | Exact connector and approved antenna selection pending |
| mosaic-X5 + active triband antenna + cables | $900–980 | Breakout $719.95 and in stock; antenna/cabling allowance covers the rest |
| U7 Pro XG | $219–250 | Observed store price $199 plus $20 surcharge; recheck variant/stock |
| Local AP controller | $274–350 | CloudKey+ SSD observed $274 including surcharge, sold out at direct store; replacement/source gate |
| CRS305, copper SFPs/DAC, Ethernet cables | $300–380 | CRS305 suggested $149; transceiver/cable prices are allowances |
| Two battery-fed PoE injectors | $80–120 | TP-DC-12BT60-10G observed legacy listing $39.95; current fulfillment/price needs confirmation |
| Powered USB hub and USB cabling | $150–220 | Exact stock and power budget pending |
| 1 TB USB SSD | $100–160 | Comparable product allowance |
| Protected OpenVLM assembly and speaker mic | $100–200 | Finished $40 VLM-KW sold out; assembly/protection allowance is higher |
| Main/reserve batteries, chargers, UPS, converters, fuses, wiring | $850–1,300 | Architecture specified, exact pack and power SKUs partly open |
| Baseplate/case, fans, sensors and mechanical consumables | $200–400 | POC allowance |
| **Common payload subtotal** | **$3,593–5,070** | Rounded build estimates below include platform-specific items |

| Platform-specific group | Additional allowance | Complete one-node estimate |
|---|---:|---:|
| CM5 16 GB/64 GB, official IO board, cooler, riser/switch/adapters and USB 2.5GbE | $500–750 | **$4,100–5,800** |
| CN9130 8 GB/64 GB ClearFog Pro kit, cooling and possible powered radio interposers | $1,350–1,650 | **$4,950–6,750** |
| DART commercial starter kit, cooling, riser/switch/adapters and USB 2.5GbE | $650–850 | **$4,250–5,950** |

DART's directly listed starter kit is $449, commercial 4 GB/16 GB, with advertised dispatch within four working days. Industrial/custom configurations are separate quotes. CN9130's roughly $1,350 kit allowance is not a bare-SoM price. CM5 prices have changed materially; the currently indexed official brief lists CM5116064 at $330, so the old launch price is not used. None of these estimates is a final cart.

Three unlike nodes can test interoperability and three-node routing, but cannot establish every platform's same-platform peak throughput. For that, temporarily swap a second compute/carrier into the same payload or build matching peer pairs; do not infer performance ceilings from a slower peer.

## Software scope and acceptance

The accepted feature update above defines the current radio roles and receive requirements. Wi-Fi 7 host mesh and the original dedicated Wi-Fi 7 AP remain optional benchmark experiments; promotion requires measured benefits and exact concurrent driver support.

| Feature | Required implementation / acceptance evidence |
|---|---|
| Mesh and AP concurrency | Demonstrate HaLow backhaul, 2.4 GHz mesh and 5 GHz EUD AP independently and concurrently; verify exact radio/firmware support. Required 5 GHz backup mesh must not disrupt EUD access; test both HaLow paths and missed-switch recovery as specified above. Do not substitute an opaque client-only HaLow dongle |
| Routing | Loss of one eligible link causes routing recovery without losing EUD management; expose per-link metrics and avoid uncontrolled L2 loops. Multiple radios are not automatic bandwidth bonding |
| EUD access | Phones/tablets associate with the 5 GHz AP; offline Maer UI and local network controls remain accessible. AP may be a concurrent host radio or external comparison unit; one unified Maer screen is an acceptance target |
| Hardware awareness | Inventory compute/carrier/radio identities, negotiated PCIe/USB/Ethernet speeds, temperatures, current/voltage, reserve state, GNSS/PPS and audio/PTT state; distinguish unknown/stale values |
| GNSS/PPS | Verify fix and direct GPIO PPS on every platform; test timing under CPU/network load and GNSS loss. RTK demonstration includes an actual correction source |
| Voice/PTT | Speaker/mic operation and hardware PTT between nodes under traffic load; deterministic audio/HID pairing, correct routing, unplug/replug recovery and priority scheduling |
| Full-node pack swap | Remove main pack **for ≥10 seconds**, at maximum simultaneous workload, with AP/controller/switch also on reserve. No reboot, USB re-enumeration, mesh loss, EUD disconnect or audio reset |
| Charging | Operate under load while charging reserve; test main-pack external charging separately. Verify PSU/converter/BMS margins and no backfeed |
| Thermal/RF | Sustained compute plus concurrent radio traffic and logging; no throttling. Compare GNSS lock and packet error rates with all converters/radios active |
| Recovery | Cold boot, power interruption, service-network recovery, clean shutdown and image reflash procedure; headless recovery from EUD where achievable |
| Performance | Record goodput, latency, packet loss, voice behavior and power for individual links, simultaneous links, encrypted traffic and multi-hop. Report PHY rate separately from measured payload rate |

## What changes from the old POC

| Old choice | Beast-mode disposition |
|---|---|
| Compact Waveshare CM5 carrier | Replace with official IO board for easier GPIO/peripheral access; use larger vendor carriers for the other platforms |
| WLE900VX Wi-Fi 5 card | Replace with two 4T4R Wi-Fi 6 mesh cards; keep any owned old card as recovery/debug equipment |
| Small HaLow USB carrier | Replace with qualified externally powered carrier; do not assume it sustains high-power TX |
| SAM-M10Q and CH340 UART workaround | Replace with native-USB mosaic-X5 plus direct PPS; old GNSS can remain a basic-function regression reference |
| 3S five-volt UPS and small enclosure | Replace with full-system two-battery DC UPS and spacious cooled chassis |
| Voice omitted from purchase cart | Add complete audio, mic, speaker and hardware PTT now |
| One Wi-Fi subsystem serving several roles | Separate two host mesh radios from EUD AP; still manage channel coexistence |
| V1 carrier assumptions | Keep these experiments separate from production selection; results inform a later V1 decision |

The remaining blockers are concrete: radio-adapter current capability, CN9130 native-slot power/lane configuration, the powered HaLow carrier design, exact Sonata PCIe/GPIO mapping, local-controller sourcing, voice-board sourcing/assembly and platform firmware integration. Removing size/power limits solves packaging constraints; it cannot remove driver support or bus topology. These three builds make those limits measurable without sacrificing the intended feature set.