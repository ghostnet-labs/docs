# Maer capabilities and qualification contract

Accepted by the project owner on 2026-10-04. This file owns the current expanded capability requirements for the OpenMANET POC and V1 tracks. Decisions are recorded in [D-029 through D-032](../decisions.md); status, blockers and execution evidence belong in Linear. Documentation acceptance is not hardware qualification.

The prior selected bench and V1 component registers remain implementation baselines, not proof that this contract is met. Any selection change must update the owning register and its dependents before purchase or carrier freeze. [GHO-55](https://linear.app/ghostnet-labs/issue/GHO-55) owns V1 reconciliation.

## 1. All-band networking

| Requirement | Accepted behavior | Qualification evidence |
|---|---|---|
| Band roles | HaLow, 2.4 GHz and 5 GHz each support node transport/backhaul, control/discovery/recovery, telemetry, voice/application traffic and access for compatible EUDs | With the other two bands disabled, demonstrate the surviving band's required services and missed-switch recovery |
| Preferred paths | HaLow will often serve long-range contact and 5 GHz nearby EUD access, but neither assignment is permanent | Measured selection follows conditions rather than fixed band labels |
| EUD compatibility | Direct HaLow access requires a HaLow-capable EUD or adapter/bridge; conventional phone Wi-Fi is not assumed to support HaLow | Endpoint and connection method recorded for every access test |
| Redundancy | Independent usable paths protect management and essential communications during failures or migrations where physically possible | Identify shared hardware, antenna, power and firmware failure points; record interruption limits |
| Concurrency | Supporting all roles is distinct from supporting every role simultaneously on separate channels | Exact AP/mesh/interface combinations, channel constraints and scheduling controls tested per radio/driver |
| Reachability | Recovery occurs once a compatible RF path becomes reachable | No guarantee of live updates while outside all usable coverage |

## 2. Adaptive controller

[GHO-51](https://linear.app/ghostnet-labs/issue/GHO-51) owns implementation and qualification.

Select per destination and traffic class using actual reachability, available capacity, latency/jitter, loss/retries and channel occupancy. Signal strength alone is insufficient. Favor reliable control/recovery, low-delay voice/PTT and spare capacity for bulk traffic. Reserve essential-service resources, use hysteresis to prevent oscillation, preserve healthy sessions where practical, and react quickly to failed links.

Expose selected path, reason, alternatives, stale/unavailable metrics, scheduling impacts and overrides in the EUD. Path selection does not automatically supply bandwidth aggregation, packet duplication or seamless session migration; implementations must define and test those semantics.

## 3. Channel migration and returning-node recovery

[GHO-52](https://linear.app/ghostnet-labs/issue/GHO-52) owns implementation; [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) owns mesh evidence. The protocol design, recovery bound and default timers are in [channel-migration.md](../software/channel-migration.md).

Peers coordinate authenticated, versioned band/channel/width plans and activation timing over working paths. Establish and verify an alternate path before abandoning the old one where hardware permits. Resolve competing decisions from separated partitions. Do not let independent retuning strand the mesh.

A returning node must recover after missing one or multiple switches, including a powered-off interval. Retain mesh credentials and allowed channel/width search information offline. Try last-known configurations, reachable alternate bands and a predefined rendezvous/search procedure; learn current configuration through authenticated advertisements. A fixed rescue channel alone is insufficient because it may also be interfered with. Define a bounded search policy and measure recovery time after RF coverage returns.

Acceptance includes missed announcements, multiple missed switches, cold boot, HaLow-only reachability, rendezvous-channel loss, clock/coordinator loss, partition merge and radio failure. No internet, cellular or manual mesh retuning is required for recovery.

## 4. Networking hardware exploration

[GHO-50](https://linear.app/ghostnet-labs/issue/GHO-50) owns the expanded compute/radio comparison and procurement reconciliation. [Candidate integration and qualification](../poc/maer-hardware-qualification.md) supplies the source audit, fixture and procedures; candidate part identities are in [Track A](../poc/track-a.md#expanded-candidate-register). Publication and offline feasibility do not close physical gates.

| Candidate experiment | Boundary |
|---|---|
| CM5 + official IO, CN9130 + ClearFog Pro, DART-MX8M-PLUS + Sonata | Compare full workloads and integration; no new production compute has been selected |
| Two HaLow paths plus two concurrent dual-band Wi-Fi modules | Candidate six-path networking arrangement, not a validated four-module assembly |
| Same-channel AP plus mesh, or dedicated role radios | Exact concurrent mode support must be verified; two tunable paths cannot occupy three independent channels at once |
| Multiple HaLow radios in one enclosure | Physically possible with independent hosts, but dual-device support on one Linux host remains a gate |

**Known constraint:** D-004 records a Morse Micro engineer's 2026-08-26 statement that the Linux driver did not support two HaLow radios on one host. [GHO-39](https://linear.app/ghostnet-labs/issue/GHO-39) must establish exact current driver/firmware support and bench evidence before any single-host dual-HaLow design is selected. Separate embedded radio hosts linked by Ethernet are an architectural fallback to evaluate, not a selected solution. USB enumeration alone does not establish simultaneous radio operation.

POC power architecture, active cooling and physical size are open. The POC must retain the existing full-node pack-swap continuity requirement [D-027](../decisions.md). Removing POC size/power limits does not waive RF, driver or bus qualification. The existing compact V1 thermal/power rules remain owned by their registers pending GHO-55.

## 5. Independent aircraft and scanner monitoring

[GHO-53](https://linear.app/ghostnet-labs/issue/GHO-53) owns receiver selection, implementation and evidence.

| Service | Accepted scope |
|---|---|
| Aircraft | Continuous 1090 MHz ADS-B; US 978 MHz UAT for additional coverage; offline map with transmitted identity/position/altitude/motion, source and age. UAT ground weather/information depends on reception |
| Public safety | Selected analog FM and unencrypted P25 Phase I/II, including trunk control and voice; other protocols only after decoder qualification |
| Aviation voice | Selected airband AM; capacity and continuous-monitoring limits explicit |
| EUD | Local map/audio selection/status, offline presets and optional recording; encrypted, stale, exhausted and unavailable states visible |
| Mesh distribution | Timestamped deduplicated aircraft reports and selected compressed audio with control/PTT priority; no continuous raw-IQ backhaul |

Four independent receive paths are the initial candidate: fixed 1090, fixed 978 and two scanner frequency windows. One window may decode multiple channels if bandwidth/software/compute permit. Continuous aviation reception while both scanner windows are occupied needs additional capacity. These are receive paths, not a frozen count of boxes or protruding antennas. Reserve receivers to their services using stable identities; avoid scanner software claiming aircraft receivers. Aircraft without usable broadcasts are not guaranteed visible; encrypted calls yield no intelligible audio.

## 6. RF construction and selective scheduling

[GHO-54](https://linear.app/ghostnet-labs/issue/GHO-54) owns coexistence evidence and scheduling qualification; V1 consumes that evidence through GHO-32/GHO-55.

Start with grounded board shields/compartments, deliberate cable routing and bonding, clean/filtered power, suitable RF filters, antenna placement and sensible channel/transmit-power selection. Shielding does not stop interference entering through the antenna. Same-band radios on different channels can still desensitize each other. Any antenna sharing/splitting must have measured insertion loss and isolation; it is not lossless.

Use scheduling only for combinations that measurably conflict. Keep other paths operating independently. Protect control/recovery and voice, defer bulk traffic first, and coordinate neighbors only when local controls are insufficient. Hard deterministic whole-mesh timing is a conditional experiment, not the default architecture.

| Tradeoff | Required treatment |
|---|---|
| Capacity | Alternating radios loses simultaneous airtime; avoided retries may improve delivered goodput. Measure rather than assume a fixed penalty |
| Delay | Waiting adds latency/jitter; shorter windows may increase overhead |
| RF silence | Pausing application traffic does not stop hardware queues, retries, ACKs or beacons; verify actual driver/firmware control |
| External reception | Aircraft/scanner transmitters do not follow Maer's schedule; quiet windows cannot recover missed messages/audio |
| Mesh mobility | Handle hidden neighbors, moving peers, timing loss and partition/rejoin |
| EUD | Do not assume ordinary phones obey custom transmit schedules |

Compare scheduled/unscheduled goodput, control reliability, voice delay/loss, GNSS and receiver decoding under own and neighboring transmissions. Run sustained testing with at least ten nodes in approximately 100 square feet. Define a control/recovery fallback when scheduling coordination fails; expose the active policy and its cost through the EUD.

The eventual external-antenna preference is ideally three or fewer, with six as the upper target. POC packaging is unrestricted; this is not evidence that the eventual antenna goal is met.

## 7. Closure and source trail

[GHO-33](https://linear.app/ghostnet-labs/issue/GHO-33) owns the expanded POC exit report; [GHO-32](https://linear.app/ghostnet-labs/issue/GHO-32) maps evidence to PCB inputs. GHO-55 blocks carrier freeze until every material requirement has an explicit disposition.

The [2026-10-04 planning study](../poc/history-2026-10-04-maer-beast-poc.md) preserves Maer_Beast_POC_Builds.md for provenance. Its initial layouts, budgets and later amendments are historical planning, not selected parts, current purchase quotes or qualification evidence. Current requirements are owned here; part choices remain in the A/B registers and purchasing remains in the Linear Purchase BOM.

Primary technical references: [Gateworks HaLow integration](https://trac.gateworks.com/wiki/expansion/gw16167), [AsiaRF AW7916-AED](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/), [SDRtrunk tuner capabilities](https://github.com/DSheirer/sdrtrunk/wiki/Tuners), [Linux mac80211 controls](https://cdn.kernel.org/doc/html/latest/driver-api/80211/mac80211.html), [Morse Micro HaLowLink guide](https://morsemicro.com/resources/user_guides/HaLowLink%20-%20User%20Guide%20-%202.11.2.pdf).
