# OpenMANET POC bench BOM and topology (GHO-27)

Linear: [GHO-27 Define the POC bench BOM and topology](https://linear.app/ghostnet-labs/issue/GHO-27/define-the-poc-bench-bom-and-topology)
· Project: [OpenMANET POC](https://linear.app/ghostnet-labs/project/openmanet-poc-66239aa64a35)
· Purchase record: [OpenMANET POC — Purchase BOM](https://linear.app/ghostnet-labs/document/openmanet-poc-purchase-bom-ff58aa264535)
· Ordering and receiving: [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36/place-receive-and-inventory-the-two-node-bench-hardware-order)

Revision: 2026-10-01. Nothing below has been received or powered yet.

This document defines the off-the-shelf bench that the POC tests run on
([GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28) to
[GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31)). It is built from the
two-node cart verified on 2026-09-30 (decisions D-015 and D-018 in [../decisions.md](../decisions.md)).
Part selections (A-nn) are owned by [track-a.md](track-a.md). Quantities, prices
and buy links live only in the Linear purchase BOM. This file owns the bench
configuration, wiring, firmware revision, safety rules and arrival checks.

## 1. Bench parts vs. the V1 carrier

The bench deliberately does **not** use the V1 radio set. Results from it are
evidence for the architecture, not validation of the V1 parts.

| Function | POC bench part | V1 carrier part ([BOM Baseline](https://linear.app/ghostnet-labs/document/openmanet-v1-bom-baseline-face23229279)) | What the bench can and cannot prove |
| -- | -- | -- | -- |
| Compute | CM5 Wireless 4 GB / 16 GB eMMC (CM5104016) | CM5 8 GB / 32 GB, no wireless (CM5008032) | Same SoC, kernel and firmware target. Not RAM/eMMC headroom. |
| HaLow | Gateworks GW16167 (MM8108, M.2 2230 E-key) on a Pier42 USB carrier | Gateworks GW16170 (MM8108-M20, high power) | Same MM8108 USB driver/firmware path. Not GW16170 TX power, current draw or thermals. |
| Wi-Fi | Gateworks GW17032 / Compex WLE900VX, QCA9880 3x3 Wi-Fi 5, ath10k, Mini-PCIe | Advantech AIW-170BQ Wi-Fi 6E 2T2R, PCIe + USB Bluetooth | 802.11s mesh on 2.4/5 GHz and dual-radio behavior. Not 6 GHz, not the AIW-170BQ driver, not its Bluetooth. |
| Bluetooth | CM5 onboard (only) | AIW-170BQ over USB | Only that the OS Bluetooth stack works. |
| GNSS | SparkFun SAM-M10Q breakout (u-blox M10, chip antenna), UART | u-blox MAX-M10S with external active antenna, UART + PPS | Same M10 protocol and gpsd path; RF coexistence trend. Not the active-antenna design. PPS only if wired (see §6). |
| Ethernet | Carrier RJ45 | B-06 (connector choice open in [GHO-41](https://linear.app/ghostnet-labs/issue/GHO-41)) | Link and throughput through the CM5 MAC. |
| Power | Waveshare UPS Module 3S (3 × Molicel M35A), 5 V / 5 A out, INA219 on I2C | Custom 3S2P pack (B-11), TPS26633 eFuse, LM76005 rails, INA228 | Node power draw by state and the hwmon telemetry path. Not the V1 power path or INA228. |
| Enclosure | Bud PN-1324-C IP65 box (dry fit / thermal only) | TBD | Closed-box thermal trend only. |

Everything in the bench BOM is POC-only. None of it carries over to the V1 fab
BOM except as a reference design for software.

## 2. Bench BOM

Two identical nodes (Node 1, Node 2), each with the full Track A register in
[track-a.md](track-a.md) (A-01 to A-21). Per-node and two-node quantities,
vendors, prices and order status are in the Linear doc
[OpenMANET POC — Purchase BOM](https://linear.app/ghostnet-labs/document/openmanet-poc-purchase-bom-ff58aa264535)
and [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36).

## 3. Missing hardware

Bench hardware that is not in the cart (serial console adapter, switch and
extra Ethernet cables, bench supply, USB-C power meter, CM5 coolers, 900 MHz
attenuators, multimeter) is listed with quantities, the POC issue each one
unblocks, and its sourcing status under "Still to source" in the Linear doc
[OpenMANET POC — Purchase BOM](https://linear.app/ghostnet-labs/document/openmanet-poc-purchase-bom-ff58aa264535).
Why each is needed:

- **Serial adapter (3.3 V USB-TTL):** GHO-28 needs serial boot logs; the image keeps the kernel console on the CM5 debug UART (`ttyAMA10`), whose carrier pins must be confirmed on arrival.
- **Switch and Ethernet cables:** host plus two nodes on one wired LAN for SSH and iperf3 (GHO-29).
- **12 V bench supply:** runs a node without the battery, isolates power faults, and answers former Q-06 (UPS 5 V USB-C vs. the carrier's 7–36 V input).
- **USB-C power meter:** Pier42/HaLow USB draw and UPS-to-carrier draw during TX (GHO-30).
- **CM5 cooler:** the thermal check compares with and without one (GHO-30, GHO-31).
- **Attenuators:** two nodes on one bench saturate each other's receivers (GHO-31).

Voice/PTT hardware (CM108B OpenVLM device) is out of POC scope; see GHO-35.

## 4. Topology

### Per node

```mermaid
flowchart LR
  subgraph ENC[Bud PN-1324-C enclosure]
    subgraph CAR[Waveshare CM5-IO-WIRELESS-BASE]
      CM5[CM5104016<br/>CM5 Wireless 4 GB / 16 GB]
      MPCIE[Mini-PCIe adapter<br/>on PCIe x1]
      USBA[USB-A]
      GPIO[GPIO terminal]
      RTC[RTC holder<br/>CR1220]
      RJ45[RJ45]
      USBC[USB-C power / flash]
    end
    WIFI[GW17032 / WLE900VX<br/>QCA9880, ath10k]
    PIER[Pier42 carrier<br/>USB-C]
    HALOW[GW16167<br/>MM8108]
    GNSS[SAM-M10Q breakout]
    UPS[Waveshare UPS 3S<br/>3x M35A, INA219]
  end
  MPCIE --- WIFI
  WIFI -- 3x U.FL pigtail --> WANT[3x ADD5RA<br/>2.4/5 GHz]
  USBA -- Adafruit 4472 --> PIER
  PIER --- HALOW
  HALOW -- MMCX pigtail --> HANT[W1063M<br/>900 MHz]
  GPIO -- 3V3, GND, TX, RX on GPIO14/15 --> GNSS
  GPIO -- SDA, SCL, GND on GPIO2/3 --> UPS
  UPS -- 5 V, XH2.54 to USB-C --> USBC
  RJ45 --- LAN[Bench LAN]
  CHG[12.6 V charger] --> UPS
```

### Two-node bench

```mermaid
flowchart LR
  HOST[Host laptop<br/>SSH, iperf3, flashing] --- SW[Gigabit switch]
  SW --- N1[Node 1]
  SW --- N2[Node 2]
  N1 <-. HaLow 902–928 MHz 802.11s .-> N2
  N1 <-. Wi-Fi 2.4/5 GHz 802.11s .-> N2
  HOST -. USB-C flash, UPS unplugged .-> N1
  HOST -. 3.3 V serial console .-> N1
```

Wired Ethernet is the management and reference path; mesh tests run over the
radios with the wired path either kept for control or unplugged per test.

### Connections

| # | From | To | Cable | Notes |
| -- | -- | -- | -- | -- |
| 1 | UPS 5 V output | Carrier USB-C power | UPS XH2.54-to-USB-C cable | Which carrier input the UPS feeds is open (former Q-06, arrival check 12). |
| 2 | Host | Carrier USB-C | Adafruit 4474 | Flashing only, with the UPS disconnected. |
| 3 | Carrier USB-A | Pier42 USB-C | Adafruit 4472 | HaLow data and power. Watch for brownout during TX. |
| 4 | Pier42 E-key socket | GW16167 | Socket + 2230 standoff | Carrier set to E-key / 2230. |
| 5 | GW16167 MMCX | SMA bulkhead → W1063M | CAB724RF pigtail | Strain-relieve the pigtail. |
| 6 | Carrier Mini-PCIe adapter | GW17032 | Socket | Use all retention hardware. |
| 7 | GW17032 U.FL ×3 | ADD5RA ×3 | JF1R6 pigtails | All three fitted before any TX. |
| 8 | Carrier GPIO14/15 (UART0, `/dev/ttyAMA0`) | SAM-M10Q RX/TX | 22 AWG | 3.3 V and GND too. Cross TX/RX. Check pinout before power. |
| 9 | Carrier GPIO2/3 (I2C1, `/dev/i2c-1`) | UPS INA219 | 22 AWG | SDA, SCL, GND. Image expects address 0x41; confirm with `i2cdetect -y 1`. |
| 10 | RTC holder | CR1220 | — | RTC charging stays off. |
| 11 | RJ45 | Bench switch | Cat5e/6 | SSH and iperf3. |
| 12 | CM5 debug UART | Host | USB-TTL adapter | Serial console; pins to confirm on the carrier. |

## 5. Firmware and build revision

| Item | Value |
| -- | -- |
| Firmware repo | [ghostnet-labs/firmware](https://github.com/ghostnet-labs/firmware), OpenWrt 24.10, kernel 6.6 |
| Board / device | `ekh-bcm2712` / `bcm2712_mm8108-usb` (`board_name` `bcm2712,mm8108-usb`) |
| Source | PR [#1](https://github.com/ghostnet-labs/firmware/pull/1), merged to `24.10` as `1a00cf7` on 2026-10-01 (D-021) |
| openmanet feed | `ghostnet-labs/packages` 24.10 @ `c9ea22b` (CM5 Wi-Fi defaults, INA219 UPS init, openmanetd from `ghostnet-labs/openmanetd`) |
| Image build | "Build ekh-bcm2712" on `01324a2`, Actions run [36805820451](https://github.com/ghostnet-labs/firmware/actions/runs/36805820451), green 2026-10-01. Artifact `firmware-ekh-bcm2712`, 5-day retention. |
| Image config | `distroconfig.txt`: UART0 on (GNSS), `i2c_arm` on (UPS), `pciex1` on (Wi-Fi), no `rtc_bbat_vchg`, `ant2` off; `bcm2712-morse-fix` stops morsechipreset from unbinding the boot eMMC. |

The image actually flashed for [GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28)
is built from `24.10`; that issue records its commit, run, artifact name
and SHA-256 when it is flashed. Rebuild if the artifact has expired.

## 6. Known firmware gaps for this bench

| Gap | Effect | Proposed fix |
| -- | -- | -- |
| No PPS input configured | The SAM-M10Q breakout has a PPS pad but the image has no `pps-gpio` overlay, so GNSS PPS (in [GHO-29](https://linear.app/ghostnet-labs/issue/GHO-29) acceptance) can't be measured. | Wire PPS to a free GPIO (e.g. GPIO18) and add `dtoverlay=pps-gpio,gpiopin=18` plus `kmod-pps-gpio` to the board. Needs its own issue. |
| Serial console pins unknown | Kernel console is on `ttyAMA10`; the carrier may not break it out. | Check the Waveshare schematic on arrival; fall back to moving the console to UART0 temporarily if needed. |
| INA219 address assumed | `/etc/config/ups` defaults to 0x41. | Confirm and edit on first boot. |

## 7. Power and RF safety assumptions

Power:
- Use three matched new M35A cells per UPS; never mix old and new cells. Charge only with the supplied 12.6 V charger, attended, on a non-flammable surface.
- Disconnect the UPS before flashing the CM5 over USB-C from the host.
- RTC uses a non-rechargeable CR1220: never set `rtc_bbat_vchg`.
- First power of each node is on a current-limited bench supply where possible, radios fitted but idle, before running from the UPS.
- Nylon standoffs only; no exposed conductors under the boards.

RF:
- Never transmit with an open antenna port. All three Wi-Fi chains and the HaLow port must have an antenna or a 50 Ω load/attenuator attached.
- Operate under US rules: HaLow in 902–928 MHz, Wi-Fi country code `US`, default (regulatory) TX power. No TX power increases beyond regulatory limits.
- Use only the selected antennas (5 dBi Wi-Fi, W1063M HaLow) so radiated power stays within the module's intended use.
- Keep nodes at least 1 m apart, or use attenuators, so receivers aren't overloaded and throughput numbers mean something.
- GNSS coexistence: log idle C/N0 first, then during HaLow and Wi-Fi TX; a drop of more than about 3 dB means move antennas or reduce TX power.

## 8. Arrival checks

Moved from the BOM sheet's "Verify on Arrival" tab on 2026-10-01. Results are
recorded on [GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28) and
[GHO-29](https://linear.app/ghostnet-labs/issue/GHO-29) (and
[GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) for power and thermal),
not in this file.

| # | Check | Why it matters | How |
| -- | -- | -- | -- |
| 1 | CM5 carrier boots and flashes | Confirms the carrier and CM5 path before radios are attached. | Flash eMMC over USB-C with BOOT asserted and no peripherals attached. Boot, SSH over Ethernet, and log firmware versions. |
| 2 | GW16167 enumerates through the Pier42 | This is the HaLow path (A-04, A-05, D-003). | Connect carrier USB-A to Pier42 USB-C with the Adafruit 4472. Confirm `lsusb` shows Morse Micro, `dmesg` loads the mm8108 USB firmware, and `morse_cli` reports MM8108. |
| 3 | Pier42/GW16167 power stays stable | The internal USB link and carrier current budget are unproven under transmit. | Run sustained HaLow traffic while logging `dmesg` for resets or brownouts. Measure the 5 V input and the Pier42 3.3 V output if accessible. |
| 4 | GW17032 enumerates and meshes | The POC Wi-Fi link depends on ath10k and 802.11s. | Install in the Mini-PCIe adapter. Confirm ath10k loads, all three antennas are attached, `iw` lists mesh point, and AP plus mesh works on the same channel if needed. |
| 5 | Wi-Fi pigtails and antennas are correct | The WLE900VX is 3x3 and needs every RF path populated. | Fit three U.FL pigtails to RP-SMA bulkheads and three ADD5RA antennas. Verify no open ports during transmit. |
| 6 | GPS UART and RF coexistence | GPS can degrade near 900 MHz and 2.4/5 GHz transmitters. | Wire 3.3 V, GND, TX, RX. Confirm a gpsd fix, log C/N0 idle, then repeat during HaLow TX and Wi-Fi TX. Adjust placement or TX power if average C/N0 drops more than about 3 dB. Record the HaLow power where C/N0 starts to fall (D-020). |
| 7 | UPS powers the node and reports telemetry | The UPS power cable and INA219 telemetry must work in the actual stack. | Boot from the UPS, unplug the charger, run the radios, check for undervoltage warnings, and read voltage, current and power over I2C. |
| 8 | RTC keeps time with the CR1220 | The CR1220 is non-rechargeable, so charging must stay off. | Confirm `config.txt` has no `rtc_bbat_vchg`. Set `hwclock`, power off, and verify the time after restart. |
| 9 | Enclosure dry fit | Bulkhead, Pier42, GPS and UPS clearances are unknown until parts arrive. | Place the boards in the Bud box before drilling. Mark antenna holes, standoff heights, wire routes and strain relief. Do not seal until the RF/GPS tests pass. |
| 10 | Thermal check | Track B power and enclosure sizing depend on real heat data. | Run closed-box HaLow and Wi-Fi traffic while logging CM5 and radio temperatures. Repeat with and without a CM5 cooler if needed. |
| 11 | Adapter and USB link retention | The Mini-PCIe adapter and the Pier42 USB link could loosen in a closed box. | Check that the GW17032 and adapter, the Pier42 and the USB cable stay seated. Add standoffs, clips or strain relief if anything can move. |
| 12 | Confirm how the UPS feeds the carrier (former Q-06) | The carrier lists a 7 to 36 V DC input while the UPS supplies 5 V over USB-C. | Check the carrier documentation and the UPS cable on arrival. Record which input is used and whether the USB-C signaling works, on [GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36). |
