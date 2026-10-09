# V1 GPIO and M.2 audit

**Owner:** [GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9), verify carrier pinouts, GPIO muxes and radio sequencing.  
**Status:** Candidate, 2026-10-09. Desk research only. This file edits no record, selects no part and assigns no D, B or R number. The canonical GPIO ledger is [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md). Until the project owner accepts something here, the ledger and the other owning records win (README rule 6).

It covers four desk items left on GHO-9:

1. The AsiaRF AW7916-AED M.2 pin table against manufacturer sources, and where the records assume generic M.2 behaviour (§2).
2. A role for GPIO16 and GPIO22, both freed by D-026 (§3).
3. A real source for HALOW_FAULT_N and WIFI_FAULT_N, or their deletion (§4).
4. RP1 / CM5 reset, firmware and device-tree defaults for every retained V1 GPIO (§5).

Then come record conflicts (§6), proposed record text (§7), decisions for the project owner (§8) and what remains unverified (§9).

## Tags

- **Verified:** read from the named source on 2026-10-09. It is a fact about the source, not about a built carrier.
- **Calculated:** derived here from Verified values. The arithmetic is shown.
- **Unverified:** no primary source found, or the source is ambiguous. Needs a bench check or a vendor answer.

## 1. Sources

| ID | Document | Revision / identity | Used for |
|---|---|---|---|
| S1 | AsiaRF [AW7916-AED pin-out drawing](https://asiarf.com/wp-content/uploads/2023/09/AW7916-AED_pins-out.jpg) | Image uploaded 2023-09; no revision, no pin numbers | Card signal per gold finger |
| S2 | AsiaRF [AW7916-AED datasheet](https://asiarf.com/wp-content/uploads/2026/07/260709_Datasheet_AW7916-AED_V1-1P.pdf) | File "V1-1P", footer "Last Updated: 04/22/2026", one page | Features only. It has no pin table, no power figures and no control-pin behaviour |
| S3 | AsiaRF [AW7916-AED product page](https://asiarf.com/product/wi-fi-6e-m-2-ae-key-module-mt7916-aw7916-aed/) | Fetched 2026-10-09 | Supply voltage and current, temperature |
| S4 | Raspberry Pi [CM5 datasheet](https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf), RP-008180-DS | Release 3, build 08/06/2026 | §2.3, §2.9, §4.2.1, §4.3, Table 4, §5.2 |
| S5 | Raspberry Pi [CM5 IO board datasheet](https://datasheets.raspberrypi.com/cm5/cm5io-datasheet.pdf), RP-008182-DS | Release 3, build 11/09/2026, build version db156e65241e | Figure 6, the Raspberry Pi M.2 socket schematic |
| S6 | Raspberry Pi [RP1 peripherals](https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf) | Revision 1.1 "Final draft", build 2023-11-07, b9b6f74 | §3.1.1 Table 4 (mux), §3.1.3 (pads), §3.1.4 register reset values |
| S7 | Raspberry Pi [config.txt GPIO control](https://github.com/raspberrypi/documentation/blob/62ba0a0c2dd5030fe9b19458fa9bd174a451f79b/documentation/asciidoc/computers/config_txt/gpio.adoc) | raspberrypi/documentation at 62ba0a0 | `gpio=` semantics and timing |
| S8 | raspberrypi/linux `rpi-6.6.y` at [bba53a1](https://github.com/raspberrypi/linux/tree/bba53a117a4a5c29da892962332ff1605990e17a/arch/arm64/boot/dts/broadcom): `rp1.dtsi`, `bcm2712-rpi-cm5.dtsi`, `overlays/pps-gpio-overlay.dts` | Commit bba53a1 | Kernel pinctrl defaults |
| S9 | TI [TPS22975, SLVSDD0B](https://www.ti.com/lit/ds/symlink/tps22975.pdf) | May 2016, revised September 2017 | Features, §5, §6, §7 |
| S10 | TI [TPS3779/TPS3780, SBVS250](https://www.ti.com/lit/ds/symlink/tps3780.pdf) | April 2015 | Proposed fault source (§4) |
| S11 | ghostnet-labs/firmware [PR #23](https://github.com/ghostnet-labs/firmware/pull/23), `distroconfig-ghostnet-v1.txt` | Head c77cd924, open, base 24.10. Branch 24.10 head 3ac1495 has no V1 board file | What GPIO config would ship |

The vendor's FCC filing might hold a fuller pin table, but fccid.io and fcc.report both blocked automated fetches. Note also that the card label in the product photo reads FCC ID TKZAW7916-AED, while the product page lists TKZAW7916-NPD. That is outside GHO-9; it is noted for whoever owns certification.

## 2. AW7916-AED M.2 pin audit

### 2.1 What the manufacturer sources actually give

S2, the datasheet, has no pin table. The only manufacturer pin source is the S1 drawing. It labels each finger but prints no numbers. I re-read the numbers from finger order on my own and got the same mapping as the ledger. Pin 1 is at the end nearest the A key. The bottom-side group next to that key reads 3.3V, 3.3V, LED1, which only fits pins 2, 4 and 6, so the order runs from that end (Verified against S1).

| M.2 pin | S1 label | Ledger connection | Audit result |
|---:|---|---|---|
| 2, 4, 72, 74 | 3.3V | WIFI_3V3 | Matches (Verified) |
| 1, 7, 18, 33, 39, 45, 51, 57, 63, 75 | GND | GND | Matches. The ledger lists the first eight and "others marked GND"; 63 and 75 are the others (Verified) |
| 69 | "GNDX", one column with GND and X stacked | GND | Ambiguous label. Wire it to GND, which is the M.2 assignment and is safe whether or not the card connects it (Unverified on the card) |
| 3, 5 | X | Open | Matches: no USB (Verified) |
| 6 / 16 | LED1 / LED2 (no "#") | Test pads only | Polarity and drive type are not given. The M.2 convention is an active-low open-drain LED#; that is assumed, not sourced (Unverified) |
| 35 / 37 | PERp0 / PERn0 | CM5 PCIe TX P/N, pins 122 / 124 | Matches. S1 names the pair from the card's side. S5 also names its M-key socket pins this way, and wires CM5 PCIE_TX to them (Verified) |
| 41 / 43 | PETp0 / PETn0 | CM5 PCIe RX P/N, pins 116 / 118, through 220 nF | Pin mapping matches. The carrier 220 nF capacitors do not match Raspberry Pi practice; see 2.2, item 1 |
| 47 / 49 | REFCLKp0 / REFCLKn0 | CM5 pins 110 / 112 | Matches (Verified) |
| 52 | PERST0 | CM5 PCIe_nRST, pin 109 | Matches. CM5 pin 109 is a 3.3 V active-low output (S4 Table 4, Verified) |
| 53 | CLKREQ0 (printed "CLKPEQ0") | CM5 PCIe_CLK_nREQ, pin 102 | Matches. The CM5 input has an internal pull-up and must be connected for the CM5 to drive REFCLK (S4 §2.3.2 and Table 4, Verified). The pull-up value is not given |
| 55 | PEWAKE0 | 10 kΩ to WIFI_3V3 and a test pad | Matches. CM5 nWAKE is unsupported in software (S4 §2.3.2, Verified) |
| 56 | W_DISABLE1 | WIFI_WDIS1_N, 10 kΩ to WIFI_3V3 | Pin matches. What the card does with it is not documented; see 2.2, item 3 |
| 54 | X | Open; GPIO22 freed | Matches: W_DISABLE2# is not connected on the card (Verified) |
| 17, 19, 21, 23 (top, between the keys) | X | Open | Matches. No SDIO (Verified) |
| 20, 22, 32 to 50, 58 to 70 (even) | X | Open | Matches. Pin 50 SUSCLK, the COEX pins, I2C on 58 / 60 and ALERT# on 62 are all unconnected on the card, so the carrier needs no 32.768 kHz clock (Verified) |
| 59 to 73 (odd), except 63 and 69 | X | Open | Matches. No second PCIe lane (Verified) |

Pin numbers stay **Unverified** until a bench card is checked, because S1 prints none. The finger order and the key positions leave little room for error.

The 3.3 V supply (S3, Verified): "DC 3.3V ± 5%", so 3.135 V to 3.465 V. S3 gives two different power statements on one page:

- "Power consumption maximum is 9W, average is 4 – 8W. Main board Power Supply design please provide 3.3V 3A, minimum 3.3V 2.5A."
- "Power consumption maximum is 10W, average is 8W. Main board should provide 3.3V-3A minimum."

The records quote only the second. At 10 W and the 3.135 V minimum, the card draws 10 / 3.135 = 3.19 A (Calculated). That is above the 3 A that D-026 states. At 9 W it is 2.87 A (Calculated). Four 3.3 V contacts at the 0.5 A per contact in [v1-3v3-rail.md](v1-3v3-rail.md) carry 2.0 A (Calculated), which is below even AsiaRF's 2.5 A minimum. That gap is already tracked under GHO-10/GHO-26; this audit only adds the 3.19 A figure.

S3 also gives an operating range of -10 °C to +70 °C. That is a D-028 / GHO-12 question, not a pin question.

### 2.2 Where the records assume generic M.2 or PCIe behaviour

1. **220 nF capacitors on the card-to-CM5 pair.** The ledger and v1-reference.md §6 put 220 nF series capacitors on the carrier, in pins 41/43 to CM5 RX. S4 §2.3.1 asks for 220 nF on each receive line only for a *direct IC connection*. For a connector it says the signals are labelled from the host's side and need no swap; it adds no capacitor rule. S5 Figure 6, Raspberry Pi's own M.2 socket on the CM5, wires PCIE_RX_P/N straight to the socket with no capacitors (Verified). PCIe add-in cards carry the AC coupling for their own transmitter, so the carrier capacitors would sit in series with the card's capacitors. S1 and S2 do not say whether the AW7916-AED has them (Unverified). If it does, say 100 nF, the series value is 100 x 220 / 320 = 69 nF (Calculated, using an example value). Whether that is acceptable depends on the PCIe Gen2 limits, which were not re-read here (Unverified). Recommended: lay out 0 Ω links in 0201/0402 capacitor footprints, so either build is possible without a respin. See §8, decision 4.
2. **CLKREQ# and PERST# with the card unpowered.** The records already flag possible back-feed through pins 52 and 53 (net plan, 02_PCIE_WIFI). S4 adds that CLKREQ# has an internal pull-up of unstated value and PERST# is a 3.3 V output. Neither the M.2 behaviour of the card nor the CM5 drive state while WIFI_3V3 is off is documented (Unverified).
3. **W_DISABLE1# as a clean RF kill.** [v1-hw-telemetry-recovery.md](../software/v1-hw-telemetry-recovery.md) §8 offers `SetRadioRfDisable` as "hardware RF disable" and assumes the card stays enumerated. That is the generic M.2 meaning. S1 shows only that the finger is connected. On some cards this pin goes to a chip reset or power enable instead, which would drop the PCIe link. Nothing from AsiaRF says which (Unverified). Whether the card has its own pull-up is also undocumented; the carrier pull-up is harmless either way.
4. **PERST# on a Wi-Fi power cycle.** v1-hw-telemetry-recovery.md §4 releases the card with `echo 1 > /sys/bus/pci/rescan` and says "kernel drives PERST#". A sysfs rescan re-enumerates devices behind an existing link. It is not known to re-assert PERST# or retrain the BCM2712 link after the card's rail has been cycled. PCIe also expects PERST# asserted while the card's power is off; the CM5 does not know that GPIO5 turned WIFI_3V3 off (Unverified, likely wrong). A bench test in GHO-22 must show which sequence recovers the card: rescan, unbind and rebind of the PCIe host controller, or only a reboot.
5. **PCIE_PWR_EN (CM5 pin 106) not used.** S4 Table 4 calls it "active high, used to signal that a PCIe device can be powered down when low". S5 Figure 6 uses it to enable the M.2 3.3 V regulator. The net plan leaves it as a no-connect and switches Wi-Fi power from WIFI_PWR_EN. That is a valid choice, but it means the kernel PCIe driver and hwmgr each control half of the power-and-reset sequence (item 4). This audit keeps WIFI_PWR_EN and adds a test pad on pin 106 so the bench can see what the driver does with it.
6. **USB VBUS for the HaLow card.** This one is about the GW16170, not the AW7916-AED, but it is the same generic assumption. Ledger sequence step 4 says "enable its USB VBUS and enumerate", and v1-hw-telemetry-recovery.md §4 looks for a HaLow VBUS enable. An M.2 card has no VBUS contact. Its USB pair (pins 3 and 5) runs from the card's 3.3 V, so there is no VBUS to switch for hub port 1. The same fact is why HALOW_USB_FAULT_N has no source (net plan K-4).

## 3. GPIO16 and GPIO22

Both lost their Bluetooth roles under D-026. The ledger already marks them Reserved. Facts (Verified, S4 Table 4 and S6 Table 4):

| GPIO | CM5 pin | RP1 functions | Notes |
|---:|---:|---|---|
| 16 | 29 | SPI1_CSn[2], DPI_D[12], MIPI0_DSI_TE, UART0_CTS, PIO[16] | UART0_CTS is the flow-control partner of the GNSS UART. The MAX-M10S UART does not use flow control, so it stays free |
| 22 | 46 | SDIO0_CLK, DPI_D[18], I2S0_SDI[1], I2C3_SDA, PIO[22] | Its I2C3_SCL partner is GPIO23, already USB_HUB_RESET_N. So GPIO22 cannot form an I2C bus with any free pin |

The candidates:

- **W_DISABLE2#.** Not possible. Card pin 54 is not connected (§2.1).
- **HALOW_FAULT_N / WIFI_FAULT_N.** Both already own GPIO6 and GPIO7 in the ledger. §4 gives them a real source on those pins. Moving them would only renumber v1-hw-telemetry-recovery.md and the `gpio-line-names` proposal for no gain.
- **GHO-13's unallocated inputs.** BRIDGE_ACTIVE_N (B-24 PFO) and PACK_PRESENT are simple digital inputs. GPIO16 and GPIO22 suit them. The pack I2C bus cannot use them (GPIO22 has no free SCL partner). If a separate pack bus is needed, GPIO0/1 (I2C0) are the only free pair.
- **WIFI_PEWAKE_N as a GPIO interrupt.** It would work electrically, but V1 has no wake-on-WLAN use. Not proposed.
- **Leave reserved.**

**Recommended default: keep GPIO16 and GPIO22 Reserved, with no connection on the carrier.** Note them as the preferred pins for BRIDGE_ACTIVE_N and PACK_PRESENT when GHO-13/GHO-38 fix those signals. Reasons: no consumer exists today, and a reserved pin with no connection is harmless if the wrong image boots. The stock `bcm2712/distroconfig.txt` on firmware 24.10 bit-bangs I2C on GPIO22 and GPIO27 under `[cm5]` (S11, Verified). A V1 board booting that image would drive GPIO22 low and could disturb whatever is wired there.

## 4. HALOW_FAULT_N and WIFI_FAULT_N sources

### 4.1 What the TPS22975 offers

S9 (Verified): the TPS22975 has VIN, ON, VBIAS, GND, CT, VOUT and a thermal pad. There is no fault, power-good or current-limit pin. Its feature list names thermal shutdown (160 °C rising, 20 °C hysteresis) and optional quick output discharge (230 Ω), and no current limit. The 6 A figure is the maximum continuous current. So a short on WIFI_3V3 is limited only upstream, by the LM76005 current limit, or ends in thermal shutdown. Either way the switched rail collapses. A rail-voltage monitor sees both cases, and it also sees a switch that never turns on.

S9 also says VIN must not exceed VBIAS (0.6 V to VBIAS). Both VBIAS candidates in the net plan (+5V_SYS, +3V3_RADIO) meet that.

### 4.2 Options

**Option A (recommended): one dual voltage detector on the two switched rails.** TI TPS3780D (open-drain, 1 % hysteresis), SOT-23-6 (S10, Verified figures below).

| Item | Value | Tag |
|---|---|---|
| VDD | +3V3_RADIO, 0.1 µF at the pin. The part runs from 1.5 V to 6.5 V | Verified (range) |
| SENSE1 | Divider from WIFI_3V3: 147 kΩ top, 100 kΩ bottom, 1 % | Proposed |
| SENSE2 | Divider from HALOW_3V3: same values | Proposed |
| OUT1 | WIFI_FAULT_N, 10 kΩ pull-up to CM5_3V3 | Proposed |
| OUT2 | HALOW_FAULT_N, 10 kΩ pull-up to CM5_3V3 | Proposed |
| Falling threshold, nominal | 1.182 V x 247 / 100 = 2.92 V | Calculated (VIT- 1.182 V, TPS37xxD) |
| Rising threshold, nominal | 1.194 V x 2.47 = 2.95 V | Calculated |
| Threshold band | ±1 % threshold plus about ±1.2 % from the 1 % divider: about 2.86 V to 2.98 V falling | Calculated |
| Margin to normal operation | The card sees at least 3.18 V at 3 A ([v1-3v3-rail.md](v1-3v3-rail.md)), so at least 0.2 V above the highest trip | Calculated |
| Divider load | 3.39 V / 247 kΩ = 14 µA per rail | Calculated |
| Output low | 0.25 V max at 2 mA (VDD ≥ 2.7 V); a 10 kΩ pull-up sinks 0.33 mA | Verified / Calculated |
| Output pull-up limit | Open drain, up to 6.5 V, independent of VDD | Verified |
| Response | 10 µs falling, 5.5 µs rising (typical) | Verified |
| Start-up | Outputs are undefined below V(POR) = 0.8 V and settle 570 µs after VDD passes 1.5 V | Verified |

Why it fits V1:

- No back-feed into the CM5. The outputs only sink current, and the pull-ups return to CM5_3V3. With the CM5 off, nothing drives these pins (S4 §4.2.1 rule).
- It runs from +3V3_RADIO, not from the rail it watches. So it still reports correctly when a rail has collapsed to 0 V. A supervisor powered from WIFI_3V3 itself would have an undefined output then.
- One part covers both radios. The cost is one SOT-23-6, five resistors and a capacitor.
- If +3V3_RADIO itself fails, the outputs become undefined, but the TPS386000 SVS3 already watches that rail and resets the node (v1-reference.md §13).

Software meaning. A low line means "the switched rail is below about 2.9 V". While the matching PWR_EN is low this is the normal "off" state, not a fault. hwmgr should report a fault only when PWR_EN is high and the line stays low after the settle time in v1-hw-telemetry-recovery.md §4 (20 ms HaLow, 100 ms Wi-Fi). The names stay as they are, so the ledger, the telemetry doc and the `gpio-line-names` proposal need no rename.

What it does not catch: a card that hangs with its rail healthy. The enumeration and health checks in the ladder still cover that.

The orderable part code (for example TPS3780DDBVR), its stock and its price are **Unverified**. S10 is the 2015 revision; a newer one may exist. The partial copy of S10 fetched here did not include the orderable addendum.

**Option B: a resistor divider straight into the GPIO.** WIFI_3V3 through 10 kΩ, with 100 kΩ to GND, into the GPIO. It needs no IC. But the threshold is only the GPIO's VIL 0.8 V / VIH 2.0 V window (S4 Table 8), so it trips anywhere between about 0.9 V and 2.2 V of rail (Calculated). And as the rails decay at shutdown, WIFI_3V3 can still be up for a moment after CM5_3V3 has gone, which puts a voltage on a CM5 pin against S4 §4.2.1. Not recommended.

**Option C: delete both lines.** Make GPIO6 and GPIO7 Reserved, and remove the fault-line trigger from ladder step 3 in v1-hw-telemetry-recovery.md §5. Recovery would then rely on enumeration timeouts only. The INA228 cannot stand in, because it measures the whole system load (v1-hw-telemetry-recovery.md §6). This saves about seven parts and loses the only way to tell a rail fault from a card fault.

**Recommended default: option A.**

HALOW_USB_FAULT_N (K-4) is a separate case. The TPS3780 cannot help it, because there is no VBUS to watch (§2.2, item 6). This audit leaves K-4 as it is.

## 5. Boot and device-tree defaults for retained GPIO

### 5.1 The stages a pin goes through

1. **CM5 unpowered.** S4 §4.2.1 (Verified): "when CM5 is powered-down or off, there must be no external voltage applied to any pin, otherwise CM5 might not power up again." S6 §3.1.3 (Verified) says the RP1 pads are "fault-tolerant ... very little current flows into the pin whilst it is below 3.63V and IOVDD is 0V". The two Raspberry Pi documents point different ways. The CM5 rule is the stricter one and stays the design rule. The RP1 statement does weaken the guess in the net plan and the K-8 proposal that an unpowered RP1 input "would hold GNSS_PPS near ground". See §6.
2. **RP1 reset, until firmware applies `config.txt`.** S6 §3.1.4 reset values (Verified): FUNCSEL = 0x1f (NULL, no function), pad OD = 1 (output disabled), pad IE = 0 (input disabled), drive 4 mA, Schmitt on. So **no RP1 GPIO drives during reset**. The pull-enable bits PUE and PDE reset to "varies", and S6 gives no per-pin table. S4 gives only the pull resistance: 37 to 86 kΩ up and 35 to 98 kΩ down at 3.3 V (Table 8). Each pin's pull at reset is therefore **Unverified**. S7 (Verified): `gpio=` lines take effect "a few seconds" after power is applied, longer for network or USB boot. So every carrier default must hold for seconds, not milliseconds, against a pull of 35 kΩ in either direction.
3. **Firmware `config.txt`.** S11 at c77cd924 is the only V1 file. S7 (Verified): these settings "can be overridden by `pinctrl` entries in the Device Tree".
4. **Kernel device tree.** S8 (Verified): `bcm2712-rpi-cm5.dtsi` only renames RP1 GPIO0–27 and sets no pinctrl on them. Its `&pinctrl` entries (gpio20 pull-up, for example) belong to the BCM2712 SoC controller, not RP1. Pin states change only when a peripheral claims them: `uart0` (GPIO14 no pull, GPIO15 pull-up), `i2c_arm` (GPIO2/3 pull-up, 12 mA) and `pps-gpio` (input, pull "off" by default). Whether the RP1 pinctrl driver leaves unclaimed pins exactly as firmware set them is **Unverified**.
5. **Userspace (hwmgr) requests the line** (v1-hw-telemetry-recovery.md §3).

One more boot item. S4 §5.2 tells users to "connect a USB serial cable to GPIO pins 14 and 15" for bootloader logs. On V1 those pins are the GNSS UART. Whether the CM5 bootloader writes to GPIO14 by default, or only to the debug UART (S4 §2.8), is **Unverified**. If it does, the GNSS receiver gets bootloader text on its RX line every boot. The bench should check the EEPROM `BOOT_UART` setting and capture GPIO14 during boot.

### 5.2 Per-pin table

"Reset" is stage 2 and "Firmware" is stage 3 (S11). "Kernel" is stage 4 (S8). "Carrier default" is the external bias that must hold through stages 1 and 2. It comes from the records where one exists, or from this audit where marked Proposed.

| GPIO | Ledger signal | Reset (stage 2) | Firmware (S11) | Kernel (S8) | Carrier default needed |
|---:|---|---|---|---|---|
| 2 | SYS_I2C_SDA | Hi-Z; CM5 1.8 kΩ pull-up (S4 §2.9) | `dtparam=i2c_arm=on` | I2C1, pull-up, 12 mA | None beyond the CM5 pull-up (record) |
| 3 | SYS_I2C_SCL | Same as GPIO2 | Same | Same | Same |
| 4 | HALOW_PWR_EN | Hi-Z, pull Unverified | `op,dh`: radio on, seconds after power-up | None | Pull-down at TPS22975 ON. 10 kΩ holds ON below its 0.5 V VIL against a 35 kΩ pull-up: 3.3 x 10 / 45 = 0.73 V. That fails. 4.7 kΩ gives 3.3 x 4.7 / 39.7 = 0.39 V (Calculated). Proposed: 4.7 kΩ |
| 5 | WIFI_PWR_EN | Same as GPIO4 | `op,dh` | None | Same: 4.7 kΩ pull-down (Proposed) |
| 6 | HALOW_FAULT_N | Hi-Z, pull Unverified | Not set | None | 10 kΩ pull-up to CM5_3V3 (option A) |
| 7 | WIFI_FAULT_N | Same | Not set | None | Same |
| 8 | GNSS_RESET_N | Hi-Z, pull Unverified | Not set | None | None: MAX-M10S internal pull-up (net plan). Open-drain use only |
| 9 | GNSS_PPS | Hi-Z | `dtoverlay=pps-gpio,gpiopin=9` | Input, no pull | Driven by the B-27 buffer; never an output (record) |
| 10 | SUPERVISOR_WDI | Hi-Z, pull Unverified | Not set | gpio-wdt proposed, not in S11 | Weak pull-down (net plan). Its level does not matter until the watchdog is armed |
| 11 | SUPERVISOR_ARM | Hi-Z, pull Unverified | Not set | None | 10 kΩ pull-down (D-044). The record's 0.70 V figure assumed a 37 kΩ pull-up minimum; S4 Table 8 gives the same 37 kΩ, so the figure stands (Calculated, record) |
| 12 | POWER_GOOD | Hi-Z, pull Unverified | Not set | None | Through the translator still open (GHO-10) |
| 13 | EFUSE_FAULT | Hi-Z, pull Unverified | Not set | None | Pull-up to CM5_3V3 (record; value open) |
| 14 | GNSS_UART_TX | Hi-Z | `dtparam=uart0=on` | UART0 TX, no pull | None. Possible bootloader output: §5.1 |
| 15 | GNSS_UART_RX | Hi-Z | `dtparam=uart0=on` | UART0 RX, pull-up | None. The kernel pull-up returns to the CM5 rail |
| 18 | HALOW_RESET_N | Hi-Z, pull Unverified | `ip,pn` | None | None: card's 200 kΩ pull-up to HALOW_3V3 (record). HALOW_3V3 is off during reset (ON pull-down), so the pin sees no pull-up then. If the rail were on, a 35 kΩ RP1 pull-down would hold RESET_N at 3.3 x 35 / 235 = 0.49 V and keep the card in reset until firmware releases it (Calculated) |
| 19 | HALOW_WAKE_N | Same | `ip,pn` | None | None: card's 10 kΩ pull-up (record) |
| 20 | INA228_ALERT_N | Hi-Z, pull Unverified | Not set | None | Pull-up to CM5_3V3 (net plan) |
| 21 | WIFI_WDIS1_N | Hi-Z, pull Unverified | `ip,pn` | None | 10 kΩ pull-up to WIFI_3V3 (record). WIFI_3V3 is off during reset, so this only matters if the rail is on first. Then a 35 kΩ RP1 pull-down gives 3.3 x 35 / 45 = 2.57 V (Calculated): above 2.0 V, but the card's own threshold is not documented (Unverified) |
| 23 | USB_HUB_RESET_N | Hi-Z, pull Unverified | `op,dh` | None | 2.2 kΩ pull-down (D-044, K-9) |
| 24 | HALOW_USB_FAULT_N | Hi-Z, pull Unverified | Not set | None | Pull-up only; no source (K-4) |
| 25 | VLM_USB_FAULT_N | Hi-Z, pull Unverified | Not set | None | One shared pull-up (record; domain open) |

The reserved pins (0, 1, 16, 17, 22, 26, 27) are Hi-Z at reset. S11 does not set them, and the kernel claims none of them.

Two findings come out of the table:

- **The TPS22975 ON pull-down needs to be stronger than a typical 10 kΩ.** ON's VIL is 0.5 V (S9 §7.3, Verified). A worst-case 35 kΩ RP1 pull-up at reset against 10 kΩ gives 0.73 V, which is above VIL. 4.7 kΩ gives 0.39 V (Calculated). The GPIO then sources 0.70 mA per enable when driven high, which is negligible against the 50 mA bank limit. The net plan only says "pull-down" with no value; this sets one.
- **S11 leaves eleven retained pins unset**, so they sit at an unknown reset pull until hwmgr claims them. That matters most for GPIO11 (it must never go high). The proposed directives below remove the doubt. Each takes effect only once firmware runs, so the carrier resistors are still needed.

Proposed additions to `distroconfig-ghostnet-v1.txt` (for GHO-19, not applied here):

```ini
# Watchdog disarmed and WDI quiet until hwmgr takes them (D-044).
gpio=10,11=op,dl
# Open-drain inputs with carrier pull-ups: no RP1 pull fighting them.
gpio=6,7,12,13,20,24,25=ip,pn
# GNSS reset released; the module pull-up holds it.
gpio=8=ip,pn
# Unconnected reserved pins: defined level, never driven.
gpio=16,17,22,26,27=ip,pd
```

GPIO0/1 are left alone, because the firmware may probe them as the ID EEPROM bus. Never set `enable_jtag_gpio=1` on V1: it puts GPIO22 to GPIO27 into JTAG mode (S7, Verified), which takes over USB_HUB_RESET_N and both USB fault inputs.

## 6. Record conflicts

README rule 6 says conflicts go to a Linear issue for the project owner. None is resolved here.

| # | Records | Conflict |
|---|---|---|
| 1 | Firmware PR #23 (S11) vs D-044 and the ledger | S11 sets `dtoverlay=dwc2,dr_mode=host` with the comment "CM5 USB 2.0 port (pins 103/105) feeds the carrier USB hub". D-044 moved the hub to the USB 2.0 pair of USB3-0 (pins 134/136), which needs no dwc2, and gave pins 103/105 to B-07 in the device role. The B-07 USB gadget console needs dwc2 in peripheral or OTG mode, not host |
| 2 | Net plan 01_CM5 "Defaults and rules" vs D-044 | The net plan still says "USB 2.0 needs `dtoverlay=dwc2,dr_mode=host` (datasheet §2.4.2)" and ties it to USB_OTG_ID capture. After D-044 that is stale for the same reason as #1 |
| 3 | Ledger "Electrical sources and boot evidence" vs S11 | The ledger cites PR #23 at 37f8e8d2. The PR head is now c77cd924. The GPIO lines the ledger lists are unchanged at the new head, so only the SHA is stale |
| 4 | Ledger and v1-reference.md §6 vs S4 §2.3.1 / S5 Figure 6 | Carrier 220 nF capacitors on the card-to-CM5 pair vs Raspberry Pi's own M.2 socket, which has none (§2.2, item 1) |
| 5 | Ledger sequence step 4 and v1-hw-telemetry-recovery.md §4 vs the M.2 connector | "Enable its USB VBUS" for an M.2 card that has no VBUS contact (§2.2, item 6) |
| 6 | v1-hw-telemetry-recovery.md §4 vs PCIe behaviour | "`echo 1 > /sys/bus/pci/rescan`; kernel drives PERST#" is a generic assumption (§2.2, item 4) |
| 7 | Net plan and v1-netplan-blocker-proposals.md K-8 vs S6 §3.1.3 | "An unpowered RP1 input's protection structures would hold GNSS_PPS near ground" vs RP1 pads that are fault-tolerant to 3.63 V with IOVDD at 0 V. The B-27 buffer is still justified by the CM5 no-voltage rule in S4 §4.2.1, so this changes the reasoning, not the part |
| 8 | Records (D-026, v1-reference.md §5) vs S3 | The records quote "10 W maximum, 8 W average, at least 3 A". The same S3 page also says "9 W maximum, 4 – 8 W average, 3 A recommended, 2.5 A minimum". At 10 W and 3.135 V the card draws 3.19 A, above D-026's 3 A (§2.1) |

## 7. Proposed record text

For the records owner, if the project owner accepts the defaults in §8. Each item names the file and the place.

1. **v1-pinout-and-sequencing.md, GPIO table, rows 6 and 7.** Replace the function text with: "Planned input from TPS3780D OUT2 (row 6) / OUT1 (row 7): low when HALOW_3V3 / WIFI_3V3 is below about 2.92 V. 10 kΩ pull-up to CM5_3V3. Low while the matching PWR_EN is low is the normal off state, not a fault. Candidate (v1-gpio-and-m2-audit.md §4); bench verification open."
2. **v1-pinout-and-sequencing.md, Electrical sources and boot evidence, HALOW_FAULT_N / WIFI_FAULT_N row.** Replace with: "TPS3780D dual voltage detector, SENSE1 from WIFI_3V3 and SENSE2 from HALOW_3V3 through 147 kΩ / 100 kΩ, VDD from +3V3_RADIO, open-drain outputs. The TPS22975 itself has no fault output; its thermal shutdown and any rail short show up as a collapsed rail."
3. **v1-pinout-and-sequencing.md, GPIO table, rows 16 and 22.** Append: "Preferred pin for a future simple digital input such as BRIDGE_ACTIVE_N or PACK_PRESENT (GHO-13). No carrier connection until allocated." Row 22 also gets: "Cannot form an I2C bus: its I2C3_SCL partner, GPIO23, is USB_HUB_RESET_N."
4. **v1-pinout-and-sequencing.md, AW7916-AED table.** Add 63, 69 and 75 to the GND row, with: "Pin 69 is labelled 'GNDX' in the drawing; it is wired to GND." Change the 41 / 43 row's carrier column to "CM5 PCIe RX P/N, pins 116 / 118, through 0 Ω links in capacitor footprints (220 nF fitted only if the bench shows the card has no TX AC coupling)". Add to the 56 row: "Card behaviour (RF kill, reset or ignored) is undocumented; Unverified."
5. **v1-pinout-and-sequencing.md, the paragraph after the CM5 physical pin table.** Replace "the peripheral TX path needs the documented 220 nF series capacitors" with "Raspberry Pi's own M.2 socket (CM5 IO datasheet Figure 6) has no carrier capacitors on the card TX path, because add-in cards couple their own transmitters. V1 lays out 0 Ω links in capacitor footprints."
6. **v1-pinout-and-sequencing.md, working sequence step 4.** Replace "then enable its USB VBUS and enumerate" with "then let it enumerate. An M.2 card takes no VBUS; its USB runs from HALOW_3V3."
7. **v1-pinout-and-sequencing.md, Electrical sources, the firmware paragraph.** Change the PR #23 SHA to c77cd924 and add: "RP1 GPIO reset state: function NULL, output disabled, input disabled; per-pin pull Unverified (RP1 peripherals §3.1.4). `gpio=` directives apply a few seconds after power-up."
8. **v1-schematic-netplan.md, 06_POWER TPS22975 table, ON row.** Replace "Proposed: pull-down to GND" with "Proposed: 4.7 kΩ pull-down to GND (holds ON under its 0.5 V VIL against a 35 kΩ RP1 pull-up at reset)". Make the same change in the 07_SYSTEM GPIO defaults row for HALOW_PWR_EN, WIFI_PWR_EN.
9. **v1-schematic-netplan.md, 07_SYSTEM.** Add TPS3780D to the parts list and change the HALOW_FAULT_N, WIFI_FAULT_N row of the GPIO defaults table to "10 kΩ pull-up to CM5_3V3; source TPS3780D (option A)". Add a TP on PCIE_PWR_EN (CM5 pin 106) in 01_CM5.
10. **v1-schematic-netplan.md, 01_CM5 Defaults and rules.** Remove the `dwc2,dr_mode=host` bullet, or replace it with "B-07 on pins 103/105 needs dwc2 in peripheral or OTG mode for the USB gadget console (GHO-19)".
11. **v1-reference.md §13, radio load switches.** Replace "the planned radio-fault input sources remain unselected" with "a TPS3780D dual voltage detector on WIFI_3V3 and HALOW_3V3 supplies the radio fault inputs (candidate)".
12. **v1-hw-telemetry-recovery.md §3, rows 6 and 7.** Replace the notes with "TPS3780D rail detector; a fault only when PWR_EN is high and the line stays low after the settle time". In §4, replace the rescan sentence with "Release PERST# and retrain the link: method to be chosen by bench test (rescan, host-controller unbind/bind, or reboot)", and delete the HaLow VBUS paragraph.

## 8. Decisions for the project owner

| # | Decision | Options | Recommended default | Why |
|---|---|---|---|---|
| 1 | GPIO16 and GPIO22 | Reserved; earmark for BRIDGE_ACTIVE_N / PACK_PRESENT; WIFI_PEWAKE_N input | **Reserved, no connection; earmarked for GHO-13 inputs** | No consumer today. A pin with no connection is harmless if a stock image bit-bangs I2C on GPIO22 |
| 2 | Radio fault source | A: TPS3780D rail detector; B: resistor divider into the GPIO; C: delete both lines | **A** | One SOT-23-6. Detects thermal shutdown, rail shorts and a switch that never turns on. No back-feed into the CM5 |
| 3 | TPS22975 ON pull-down value | 10 kΩ; 4.7 kΩ | **4.7 kΩ** | 10 kΩ does not hold ON under 0.5 V against a worst-case 35 kΩ RP1 pull-up during the seconds before firmware runs |
| 4 | Card TX AC coupling on the carrier | 220 nF fitted; 0 Ω fitted in capacitor footprints | **0 Ω in footprints; decide on the bench card** | Matches Raspberry Pi's own M.2 socket, and keeps both builds possible without a respin |
| 5 | PCIE_PWR_EN (CM5 pin 106) | No connect; test pad; use it as the Wi-Fi enable | **Test pad only; keep WIFI_PWR_EN** | Lets the bench see what the PCIe driver does with it without changing the power design |
| 6 | Firmware boot directives | Leave as S11; add the §5.2 lines | **Add the §5.2 lines (GHO-19)** | Removes unknown RP1 pulls on eleven retained pins once firmware runs, and holds GPIO11 low explicitly |

## 9. What remains unverified

- AW7916-AED pin numbers, which S1 does not print, and what pin 69 carries.
- What the card does with W_DISABLE1#, whether it has pull-ups on W_DISABLE1#, PEWAKE# or CLKREQ#, LED1/LED2 polarity, and whether it has TX AC capacitors.
- Back-feed into the unpowered card through PERST# and CLKREQ#, and the value of the CM5 CLKREQ# pull-up.
- How to recover the PCIe link after a WIFI_3V3 power cycle on the BCM2712 (rescan, controller unbind/bind, or reboot), and what the driver does with PCIE_PWR_EN.
- The RP1 per-pin pull at reset (S6 says "varies"). Whether the BCM2712 boot ROM or bootloader touches RP1 GPIO before `config.txt` is applied, including bootloader UART output on GPIO14.
- Whether the RP1 pinctrl driver leaves unclaimed pins as firmware set them.
- The TPS3780D orderable code, stock and price, and the current revision of SBVS250.
- The AW7916-AED's real peak current at 3.135 V, given AsiaRF's two power statements.

These belong on GHO-9 (desk), GHO-19 (firmware), GHO-21 (first power) and GHO-22 (radio validation).
