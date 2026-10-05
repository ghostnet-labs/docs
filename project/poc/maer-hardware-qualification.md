# Maer candidate hardware integration and qualification

This record owns expanded candidate wiring, source-audit evidence and qualification procedures. The [capability contract](../requirements/maer-capabilities.md) owns requirements; [track-a.md](track-a.md#expanded-candidate-register) owns candidate part identities and rationale. Selected CM5/V1 registers remain unchanged. Status, open specifications, tests and procurement belong to [GHO-50](https://linear.app/ghostnet-labs/issue/GHO-50) and its tasks; all prices/orders remain in the Linear Purchase BOM.

Sources were reviewed on 2026-10-04 America/Denver (2026-10-05 UTC). Documentation and source inspection do not qualify shipping hardware. No target benchmark has been run. A candidate fixture is not a purchase or production-selection decision.

## Findings

| Question | Disposition | Consequence for Maer |
|---|---|---|
| Can two PCIe radios coexist with USB 3 and 10GbE? | Resolved in documented lane assignment; live operation remains untested | Pro uses SERDES 4/5 for PCIe ports 1/2, each x1. SERDES 1 is USB 3, 2 is XFI, 3 feeds the Ethernet switch, 0 is SATA. No CM5-style common x1 expansion switch is needed |
| Are all six advertised PCIe lanes available on this carrier? | No, in the normal Pro configuration | Three controllers/up to six lanes is a configurable SoM capability, not six spare Pro lanes. The two slots are separate x1 paths; a Gen2 endpoint remains Gen2 |
| Is M.2 storage NVMe? | Not in the documented standard mapping | Linux configures SATA on the M.2 connector. Specify a mechanically compatible SATA SSD, not an arbitrary NVMe SSD |
| Can native power run two candidate Wi-Fi modules? | Published schematic does not substantiate it; identifies a likely hard limit | Rev 2.1 U10 feeds V_3V3 through an RT2875A, a 3 A converter; both radio sockets share V_3V3. AsiaRF asks for 3.3 V/3 A per AW7916-NPD. Two cards alone require a 6 A design provision, before other loads |
| Is every USB device forced through one common 480 Mb/s link? | Earlier description was too broad | Linux assigns USB 3 SuperSpeed on Type A to controller 0, Type A USB 2 to controller 1, and CON3 USB 2 to controller 0. SuperSpeed and USB 2 traffic are not one undifferentiated bandwidth pool |
| Does each mini-PCIe slot expose USB? | Current guide distinguishes slots | CON2 is PCIe only; CON3 is PCIe plus USB. Do not rely on an older generic diagram implying both have usable USB |
| Is 10GbE a direct host interface? | Yes in documented mapping | Use SFP+ DAC to the external high-speed switch. The onboard switch's Linux CPU link is 1 Gb/s; its copper ports do not each provide independent gigabit CPU bandwidth |
| Is software board support available? | Yes; full Maer image is not qualified | Mainline Linux has Pro/common board device trees; OpenWrt has a CN9130 ClearFog Pro target. SolidRun documents Debian 13 installation. These establish foundations, not radio/AP/mesh or decoder acceptance |
| Is industrial CPU speed 2.2 GHz? | Manual distinguishes grades | Hardware manual lists industrial 2.0 GHz and commercial 2.2 GHz. Benchmark the purchased grade; do not promise commercial clocks for industrial equipment |
| Can we order 16 GB RAM confidently? | Unresolved supplier discrepancy | Product listings emphasize 8 GB; manual permits 16 GB; newer datasheet mixes 8 GB with a SO-DIMM description inconsistent with the soldered-memory SoM. Start with an exact quoted 8 GB/64 GB SKU; larger RAM remains a supplier question |

The slot power result is an engineering inference from the published schematic and regulator/radio specifications, not a measurement of the currently shipping carrier. Obtain its actual revision and assembly/BOM before treating Rev 2.1 as definitive.

### Pinned image USB mapping boundary

The USB findings above describe the cited Linux mainline DTS. Our current [OpenWrt target DTS at firmware revision d994d3b6e8871ce518b15f9bac14699ee859b285](https://github.com/ghostnet-labs/firmware/blob/d994d3b6e8871ce518b15f9bac14699ee859b285/target/linux/mvebu/files-6.6/arch/arm64/boot/dts/marvell/cn9130-clearfog-pro.dts) instead describes `cp0_usb3_0` as slot USB2-only and `cp0_usb3_1` as Type A SuperSpeed. The target exists in the current fork, but controller names/UTMI routing cannot be transferred between these source descriptions without reconciliation. [GHO-65](https://linear.app/ghostnet-labs/issue/GHO-65), under GHO-58, owns comparison of controller/register definitions, bootloader lane configuration and the shipping schematic, followed by target `lsusb -t` and mixed-load verification. This discrepancy is not proof of a hardware fault. Keep controller-specific wiring conditional on the selected image's verified topology.

## Candidate wiring that reduces the known risks

1. **Two concurrent Wi-Fi modules:** evaluate two mini-PCIe AW7916-NPD cards in CON2 and CON3, rather than adapting M.2 AW7916-AED cards. Each module advertises dual-band concurrency; exact independent 2.4/5 GHz operation and AP/mesh interface combinations must be tested. This is a candidate for the expanded all-band requirement, not a silent replacement of the component register. Marketing mentions of three bands do not establish three simultaneously independent PHYs.
2. **Radio power:** use engineered interposers with externally regulated 3.3 V and at least the vendor's 3 A provision per card. Isolate host supply pins so rails cannot backfeed; preserve ground, reference clock, reset, PCIe pairs and required sidebands. Check sequencing and transient droop with both transmitters active. A separate supply cannot fix inadequate connector contact ratings without checking the complete path.
3. **Bulk recording:** move recordings to SATA M.2 if the exact host kernel successfully probes the drive. Keep eMMC for the OS. This removes SSD payload from USB, but introduces a kernel validation gate rather than eliminating storage qualification.
4. **Receivers:** powered hub on Type A. Calculate USB 2 and SuperSpeed loads separately. Multiple USB 2 receivers behind one hub still share that hub's high-speed upstream link; a USB 3 label does not make those receivers SuperSpeed devices.
5. **HaLow:** initially use one powered USB/E-key host adapter. An interposer on CON3 could expose its USB 2 signals alongside the Wi-Fi PCIe connection, separating HaLow from Type A USB 2 receiver traffic. This is an unbuilt electrical-integration option, not a ready adapter recommendation. Dual-HaLow on one Linux host remains blocked by GHO-39; an independent Ethernet radio host is a fallback to evaluate.
6. **Network uplink:** SFP+ DAC to the external switch. The Linux board description limits SFP module power to 2 W; validate module/cable compatibility rather than substituting a hot copper transceiver without checking.
7. **Power and timing:** regulated 12 V POC branch, separately powered radios/hubs and measured whole-node draw. Confirm GPIO voltage/pinmux for GNSS PPS; do not substitute an I2C GPIO expander for precise PPS capture. Keep kernel/GNSS fallback timing and recovery working without a GNSS fix.

All six default SERDES lanes are allocated. Adding another SuperSpeed controller or NVMe path on the stock Pro would require changing that allocation or extra expansion on an existing PCIe path, potentially displacing a radio. More USB connectors on a hub do not create another controller.

## Software issues now made concrete

- **MT7916:** Linux Wireless lists it under mt76 support. Still verify firmware, two-device loading, DBDC mode, channel independence, AP plus mesh combinations, scanning interruption and unplug/reset recovery. Driver existence is not concurrency qualification.
- **HaLow:** Gateworks documents an out-of-tree Morse driver and matching firmware/board configuration for MM8108. A Gateworks Venice image cannot be flashed onto CN9130. Port the packages to the selected CN9130 kernel and test single-device operation before attempting dual-device work.
- **Debian storage:** SolidRun's current installer notes describe a SATA-port issue on Linux 6.12 when the controller's first port is disabled. This matches why SATA recording needs explicit validation. Verify the actual kernel and patch status rather than treating a generic upgrade as sufficient; the notes also describe a subsequent regression. Do not transfer CN9132-specific PCIe/eMMC warnings to CN9130 without evidence.
- **Deployment image:** Debian is a useful full decoder integration environment; OpenWrt is a useful networking baseline. Decide on one supported deployment image after confirming decoder native dependencies, headless lifecycle, packet classification and radio packages. Different distro results must be reported separately.
- **Timing:** SoM manual explicitly calls specialized PPS/PTP/Sync-E support untested. Plain GPIO PPS is a separate integration path to verify. CN9130 cannot guarantee radio silence or deterministic mesh scheduling without driver/firmware controls.

## Resource constraint source audit (2026-10-04 owner local date)

The board has not been bench tested. The findings below distinguish documented resource limits, source-review risks and measurements still required. A larger CPU cannot remove a shortage of independent radio channels or captured RF bandwidth.

| Constraint | Evidence and practical consequence | Closure or mitigation |
|---|---|---|
| Wi-Fi channels per band | Two candidate DBDC cards provide a candidate two independently tunable PHYs per band. Virtual interfaces on one PHY do not create independent channels. | Enumerate actual PHYs/interface combinations; qualify simultaneous AP/mesh roles and all four paths. |
| Mesh channel migration plus EUD service | Old mesh channel, new mesh channel and a distinct unchanged EUD channel require three independent paths in the same band. Two paths cannot provide all three simultaneously. This is a conditional operating case, not a newly imposed requirement. | Permit AP/mesh channel sharing, define a controlled transition, or add a third physical path if uninterrupted distinct-channel service is required. |
| HaLow concurrency | Current Morse source creates per-device state but this does not override the existing unsupported dual-device gate in GHO-39. Each wiphy advertises one different channel. | Same-kernel/firmware dual-device tests, probe-order and recovery tests; preserve the gate until evidence closes it. |
| Scanner frequency coverage | SDRtrunk documents RSPduo single-tuner operation up to 10 MS/s, but dual-tuner operation is two streams up to 2 MS/s each. SDRplay specifies up to 1.536 MHz low-IF bandwidth in dual mode. Two tuners are not two 10 MHz capture windows. | Map selected trunked systems' control and voice frequencies into actual simultaneous capture windows. Add tuners or a wider receiver when they do not fit. Retuning creates coverage gaps. |
| Spectrum awareness | RSPduo's documented upper frequency is 2 GHz, below the 2.4/5 GHz Wi-Fi bands. | Use radio survey/scan telemetry or suitable separate RF equipment; account for disruption caused by scanning an active PHY. |
| Native card power | Previously inspected shared 3 A carrier rail is insufficient to assume two cards each requesting a 3 A supply. | Current shipping BOM plus powered-interposer design and electrical/thermal qualification. |
| Low-rate HaLow airtime | Gateworks lists 1 MHz MCS10 at 0.15 Mbps PHY and MCS0 at 0.3 Mbps. Application throughput is lower and varies with retries, hops and topology. | Admission control, essential traffic priority and range/load tests; do not promise bulk throughput at the longest range. |
| Whole-node compute, USB and storage | No full workload benchmark exists for the proposed CN9130 assembly. | Run the pinned full-load fixture; measure CPU headroom, overruns, queue growth, voice latency and sustained recording together. |

### Driver source review

Source was cloned and inspected, not executed on target hardware. The mt76 revision was `be5ce7910521492d4a2e4ce7ee3843680a46c047`. In `mt7915/init.c`, the advertised interface combination has `num_different_channels = 1`; mesh participation depends on the kernel configuration. DBDC registers an additional PHY when supported by the board/EEPROM configuration. Runtime `iw phy` output, firmware and purchased card revision must confirm the proposed resource count and allowed combinations. Source: [pinned mt7915 initialization](https://github.com/openwrt/mt76/blob/be5ce7910521492d4a2e4ce7ee3843680a46c047/mt7915/init.c).

Morse revision `4ce0a0272f8ac8e2fa58eea8ff08116e493399de` corresponds to tag `mm8108-2.1.0`; the earlier `mm8108-2.0.0` revision was also reviewed. USB probe creates a device instance and associates interface data with it. However, `morse_mac_config_wiphy` still advertises one different channel per wiphy, and several mutable structures are shared: `mors_band_5ghz`, `mors_ops`, the CSSID cache and the channel-map selection. These are reasons to test mixed capabilities, initialization order and unplug/replug, not proof that two devices fail. No source change inspected establishes supported dual-HaLow operation. Sources: [pinned USB implementation](https://github.com/MorseMicro/morse_driver/blob/4ce0a0272f8ac8e2fa58eea8ff08116e493399de/usb.c), [pinned MAC implementation](https://github.com/MorseMicro/morse_driver/blob/4ce0a0272f8ac8e2fa58eea8ff08116e493399de/mac.c). GHO-39 remains open.

### Airtime and receiver tests

Illustrative budget, not a product requirement or measured result: a 24 kbps voice stream with 20 ms packets carries 60 payload bytes per packet. Assuming another 80 bytes per packet gives 56 kbps per unicast forwarding instance before Wi-Fi/MAC overhead, retransmissions or extra hops. Twelve such independent instances would total 672 kbps. One talker distributed to multiple listeners is a different workload: routing, multicast and rebroadcast policy determine copy count. Test both patterns rather than equating listeners with talkers. The lowest HaLow PHY rates cannot sustain arbitrary voice copies and bulk traffic simultaneously.

Gateworks also documents MM8108 TX shutdown at 85°C chip temperature. Cooling must prevent reaching this boundary during the defined workload; disabling protection is not a mitigation. Radio-to-radio desensitization and interference still require simultaneous transmit/receive tests with the intended antenna spacing, enclosure and channels. A spare tuning path cannot guarantee immunity to broad-band interference.

The next receiver fixture must include the chosen trunked frequency plans, the required simultaneous calls, two aircraft feeds and recording. Treat capture bandwidth, demodulation load and storage load as separate limits. Host sample-format arithmetic is not proof of USB wire traffic or available bus service; measure controller topology and overruns on the assembled node.

With identical peripherals, CM5 and DART-MX8M-PLUS inherit the same radio and receiver resource limits. Supplier specifications, source inspection and a populated bench node establish different evidence; none substitutes for the others.

Additional sources: [SDRtrunk tuner documentation](https://github.com/DSheirer/sdrtrunk/wiki/Tuners), [SDRplay RSPduo datasheet](https://www.sdrplay.com/wp-content/uploads/2018/05/RSPduoDatasheetV0.5.pdf), [SDRplay product specifications](https://sdrplay.com/product/rspduo/), and [Gateworks MM8108 rates, software and thermal notes](https://trac.gateworks.com/wiki/expansion/gw16167).

## Source register

- [SoM hardware manual](https://dev.solid-run.com/marvell/cn913x/com-som/cn9130-som-hardware-user-manual): revision log through December 2024; SERDES assignments and grade distinctions.
- [Pro quick-start guide](https://dev.solid-run.com/marvell/cn913x/sbc-platform/clearfog-cn9130-pro-quick-start-guide): February 2025 CON2/CON3 interface clarification.
- [Pro Rev 2.1 schematic, sheet 3 sockets and sheet 13 regulators](https://www.solid-run.com/wp-content/uploads/2023/11/clearfog-pro-cn9130-schematics-2.1.pdf): visually inspected; file title/date retain older carrier heritage and shipping population must be confirmed.
- [RT2875A/B regulator datasheet](https://www.richtek.com/assets/product_file/RT2875A%3DRT2875B/DS2875AB-04.pdf).
- [Linux common carrier device tree](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/marvell/cn9130-cf.dtsi) and [Pro-specific device tree](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/marvell/cn9130-cf-pro.dts): source read through GitHub; SATA, USB, SFP and PCIe mappings.
- [OpenWrt CN9130 Pro image definition](https://github.com/openwrt/openwrt/blob/main/target/linux/mvebu/image/cortexa72.mk): source read through GitHub.
- [SolidRun Debian installation and known issues](https://github.com/SolidRun/debian-builder/blob/develop-pure/README.arm64.cn913x.md).
- [AsiaRF AW7916-NPD specifications](https://asiarf.com/product/wi-fi-6e-mini-pcie-module-mt7916-aw7916-npd/).
- [Linux Wireless MediaTek support](https://wireless.docs.kernel.org/en/latest/en/users/drivers/mediatek.html).
- [Gateworks MM8108 integration](https://trac.gateworks.com/wiki/expansion/gw16167).
- [2026 carrier datasheet](https://www.solid-run.com/wp-content/uploads/2026/04/ClearFog-CN9130-Pro-Datasheet-2026.pdf) and [SoM product listing](https://www.solid-run.com/embedded-networking/marvell-octeon-tx2-family/cn9130-som/): conflicting memory/assembly specifications recorded, not silently reconciled.

## Qualification procedures and execution ownership

| Issue | Deliverable / evidence owner |
|---|---|
| [GHO-56](https://linear.app/ghostnet-labs/issue/GHO-56) | Current shipping rail/contact data, powered interposer electrical design and measurements |
| [GHO-57](https://linear.app/ghostnet-labs/issue/GHO-57) | Exact assembly SKU, memory/temperature disposition and sourcing reconciliation |
| [GHO-58](https://linear.app/ghostnet-labs/issue/GHO-58) | Pinned reproducible CN9130 image, USB/PCIe/SATA/PPS integration evidence |
| [GHO-59](https://linear.app/ghostnet-labs/issue/GHO-59) | Runtime physical channel accounting and explicit migration/EUD capacity policy |
| [GHO-60](https://linear.app/ghostnet-labs/issue/GHO-60) | Selected frequency coverage, receiver topology and ARM64/native dependency qualification |
| [GHO-61](https://linear.app/ghostnet-labs/issue/GHO-61) | Comparable complete workload, no-throttling and pack-swap evidence |
| [GHO-62](https://linear.app/ghostnet-labs/issue/GHO-62) | Portable inventory/resource tooling; independently closable implementation slice |
| [GHO-63](https://linear.app/ghostnet-labs/issue/GHO-63) | Independent Ethernet HaLow-host fallback architecture and qualification |
| [GHO-64](https://linear.app/ghostnet-labs/issue/GHO-64) | Source audit and procedures publication; independently closable implementation slice |

This table identifies ownership, not current status. GHO-39 owns supported dual-HaLow disposition, GHO-54 coexistence/dense-node evidence, GHO-50 compute selection and GHO-55 V1 reconciliation. Obtain supplier evidence through GHO-56/GHO-57; questions prepared during the audit have not been sent.

### Powered interposer design inputs (GHO-56)

This is a design acceptance specification, not a released schematic. Obtain exact shipping socket/card pin tables before assigning nets. Document every contact's function/current rating, host supply disconnection, local supply/returns, reset/enable defaults, PCIe reference-clock routing and any USB breakout. Do not join regulator outputs or assume an extension cable isolates power.

Size local regulators from each card's peak/transient requirement with design margin and supply extremes, not idle measurements. Budget both cards, compute, storage, receiver hub and audio together. Include protection/inrush control, discharge, rail-good sequencing, probe points and bounded recovery. Preserve signal reference grounds while preventing power backfeed into an unpowered host/card. Review connector contacts, traces, harness drop and regulator/contact temperatures. Component values and fabrication drawings require verified electrical inputs.

Bring-up order: unpowered continuity/isolation; unloaded current-limited regulator test; dummy-load/transient tests; one card enumeration/TX peaks; second card alone; both cards plus full node load; reset, power-cycle and host-off cases. Capture rail min/max/ripple, current, temperatures and errors in every case. A supply design does not qualify the card's cold environment or RF isolation.

### Single-host HaLow and independent-host fallback (GHO-39/GHO-63)

Establish single-radio behavior first using an exact host, driver, firmware and board-config tuple. Add a second identical device and repeat reversed probe order. Record independent identity/channel/role/traffic behavior. Replug/reset each device while the other carries control/PTT; check common failures, stale telemetry and corruption. Mixed versions/capabilities need separate tests only if intended in the supported matrix. USB enumeration cannot close the gate.

Fallback experiment: two independent embedded Linux hosts, each with one radio and Ethernet to primary compute. Host prerequisites are verified support for the exact radio/interface/image tuple, sufficient power/cooling and recovery control. Select routed versus bridged/mesh transport explicitly; document multicast, addressing, loops and path semantics before configuring it. Each host needs stable identity, authenticated management, versioned channel-plan acknowledgment/activation, fresh health, boot ordering and local recovery. Primary control treats host loss as path loss and cannot acknowledge an unconfirmed switch. Test simultaneous traffic, Ethernet loss, host restart, delayed plans and partition/rejoin. Compare latency, whole-node power, cabling and management before choosing hosts. This procedure does not select a host or approve purchases.

### Receiver frequency and native-software matrix (GHO-60)

For each required simultaneous service, record center and occupied bandwidth, control-channel alternatives, possible voice frequencies, concurrency, continuous/intermittent reception and allowable gaps. Fit the complete signal into actual usable guarded windows, not nominal sample-rate intervals. Include all relevant trunk traffic frequencies, not just one successful call. Extra demodulators do not extend RF coverage. Add a tuner/wider receiver or expose constrained retuning gaps where required. Reserve stable 1090/978 identities from the scanner pool; continuous aviation during two occupied scanner windows requires separate capacity.

Per image, record CPU architecture, Java/native-library versions, SDRplay API/license/service lifecycle, decoder build/options, permissions and receiver identity. Qualify headless installation, offline replay, restart/replug and recording before live RF acceptance. Save fixture hashes/reference decode counts. Generic Linux support does not establish ARM64 API or target-image compatibility.

### Full workload comparison (GHO-61)

Use the [GHO-62 tooling](https://github.com/ghostnet-labs/firmware/tree/24.10/scripts/hardware-qualification) on each target. Capture before/after inventories with distinct filenames. Construct resource inputs from verified PHY combinations/capture windows; examples are synthetic and unqualified. Record SKU/revisions, CPU grade/clock, image/kernel/radio/decoder versions, topology, supply/cooling, ambient, antenna positions and fixture hashes. An x86 tool smoke test is not a candidate-board run. Label the existing CM5 bench and official-IO comparison as different configurations.

Run identical fixtures: routing load at 25/50/75/100% of independently measured capacity, active PTT with endpoints/hops/forwarding pattern recorded, continuous aircraft feeds, scanner calls, recordings and EUD service together. Explore 1/2/4/8 calls without treating those counts as accepted product requirements. Run the full required bundle for two hours three times. Capture per-core CPU, memory, sample overruns, decode counts, queue growth, voice delay/jitter/loss, delivered throughput, recording integrity, device/kernel errors, whole-node watts/peak current, rail transients, temperature/protection and recovery behavior.

Proposed screening: 20% CPU/memory reserve, p95 voice delay <=150 ms, voice loss <=1%, identical IQ replay decode counts within 1%, and no overruns, unbounded queues or OOM. These are screening proposals, not new accepted guarantees. Missing measurement is unknown, not pass. Temperature/frequency snapshots alone cannot prove no throttling; include CPU, radio protection, undervoltage and storage behavior. Never disable thermal protection to meet the owner's no-throttling requirement.

Test full-node pack-swap continuity at required load under D-027 with timestamped services and power capture, including compute, radios, receivers, storage and audio. Repeat cold start/operation for the actual assembly/environment resolved by GHO-57. SoM grade alone cannot qualify the assembled node. GHO-38 consumes measured bridge power and GHO-55 consumes the complete requirement disposition before carrier freeze.
