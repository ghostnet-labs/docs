# V1 control radio option (LoRa)

**Owner:** [GHO-90](https://linear.app/ghostnet-labs/issue/GHO-90). Channel migration design stays in [software/channel-migration.md](../software/channel-migration.md); requirements stay in [requirements/maer-capabilities.md §3](../requirements/maer-capabilities.md#3-channel-migration-and-returning-node-recovery).
**Status:** Option, 2026-11-06. Justin asked for it to be written up as an option; it is not selected. This file edits no register and assigns no B, D or R number. Nothing was bought.

## Why this exists

At long range HaLow is often the only link between two nodes. 2.4 GHz backhaul reaches medium range, and 5 GHz is the EUD access point (D-055). If HaLow is jammed between two distant nodes, nothing is left to carry a channel-migration plan, so the mesh cannot agree on a new HaLow channel. Each node can only fall back to the blind sweep and rendezvous search in channel-migration.md §5.

A small, low-rate LoRa radio would carry only migration traffic: adverts with the signed plan, and acks. It does not carry user data. Its job is to keep coordination alive while HaLow is jammed, so the mesh moves HaLow together instead of searching blind.

## Tags

- **Verified:** read from the linked source on 2026-11-06.
- **Calculated:** derived here from Verified values; arithmetic shown.
- **Unverified:** from memory or general practice; to be checked before any selection.

## Summary

- **What it is.** A sub-GHz LoRa module on a spare USB hub port, with its own antenna, that floods channel-migration adverts and acks in parallel with HaLow and Wi-Fi.
- **Why LoRa.** LoRa's chirp spread spectrum decodes far below the noise floor. Semtech gives SX1262 sensitivity down to −148 dBm and a 170 dB link budget (Verified, [Semtech SX1262](https://www.semtech.com/products/wireless-rf/lora-connect/SX1262)). A jammer sitting on one HaLow channel does not stop it. A wideband jammer across the whole 902–928 MHz band would hurt both, but LoRa keeps a large margin over HaLow (Unverified: size depends on spreading factor; check SX1262 datasheet SNR limits per SF).
- **Power.** Negligible against an 18.5 W budget. Receive is 4.2 to 4.6 mA on the SX1262 (Verified, Semtech). The RAK3172 module lists 5.22 mA receive and 87 mA transmit at 20 dBm (Verified, [RAK3172 datasheet](https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/)). At 3.3 V that is about 17 mW listening and 0.29 W only while transmitting (Calculated). Plans are rare, so the average is well under 0.1 W (Calculated from the duty cycle in §3).
- **Biggest risk: same band as HaLow.** US LoRa uses 902–928 MHz, the same band as HaLow. HaLow transmitting at up to +28.5 dBm will desensitize the LoRa receiver unless the antennas are isolated, and the reverse. This needs an isolation budget and a bench test before selection.
- **Enclosure cost.** One more 915 MHz antenna port on the radio, which competes with the knob and SMA spacing that already sets the body depth.

## 1. Candidate parts

| Part | What it is | Interface | Notes |
|---|---|---|---|
| RAKwireless RAK3172 (H variant, US915) | STM32WLE5 SoC with an SX126x-class radio in a module | UART AT commands; LoRa P2P mode supported | −40 to +85 °C on the -T and -F variants; 2.0 to 3.6 V; FCC, IC and RCM marked variant offered (Verified, RAK3172 datasheet). Max TX power not stated beyond the 20 dBm test point |
| Semtech SX1262 on the carrier | Bare transceiver, +22 dBm, 150 to 960 MHz, up to 62.5 kbps LoRa | SPI plus BUSY, DIO1 and reset GPIOs | Needs RF layout, a TCXO and matching on the carrier, and SPI pins the CM5 no longer has free (SPI0 and SPI1 pins are allocated in [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md)) |

**Working preference: RAK3172 behind a USB-UART bridge on TUSB4041I port 2** (B-04 lists ports 2 and 4 as spare). It needs no new CM5 GPIO, keeps the RF design inside a certified module, and Linux sees it as a serial port.

## 2. How it fits channel migration

- The control radio is one more transport for the existing advert and ack messages (channel-migration.md §2), inside the same alfred payload codec and with the same Ed25519 plan signature. No new trust path.
- Every node listens on one fixed LoRa channel and spreading factor, provisioned at setup with the mesh credentials. Because LoRa is not being retuned, it is always where its peers expect it.
- A coordinator sends a new plan on HaLow, 2.4 GHz and LoRa at once. Acks come back on whichever path works.
- A node in rediscovery (§5) keeps LoRa listening while its other radios sweep. The first authenticated LoRa advert gives it the current plan, so it tunes straight to the right HaLow channel instead of sweeping.
- The LoRa channel itself is a single known frequency, which maer-capabilities §3 says is not enough on its own. It is an addition to the rendezvous lists, not a replacement for them.

## 3. Airtime and duty cycle

- An advert with a three-band plan is about 65 bytes of plan plus a 64-byte signature (channel-migration.md §2), so roughly 140 bytes with headers (Calculated, header size estimated).
- At the lowest LoRa rates that takes several seconds on air; at mid spreading factors it is well under a second (Unverified: compute with the Semtech airtime calculator for the chosen SF and bandwidth).
- **US rule check needed.** Under FCC 15.247, 125 kHz LoRa is normally run as frequency hopping with a 400 ms dwell limit, while 500 kHz channels can qualify as digital modulation without the dwell limit (Unverified; see Semtech's [LoRa and FCC Part 15.247 measurement guidance](https://dtsheet.com/doc/1842140/lora%E2%84%A2-and-fcc-part-15.247--measurement-guidance)). The chosen spreading factor and bandwidth must keep one advert inside whatever limit applies.
- Plans are rare (minutes to hours apart) and the periodic advert interval on LoRa can be much longer than on Wi-Fi, so average transmit time is a small fraction of a percent (Calculated in principle; set the interval in the design).

## 4. Before selection

The open checks (antenna isolation and desense against HaLow, FCC mode and airtime, range against HaLow at its narrowest width on the [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) sites, a fourth antenna port on the enclosure under [GHO-7](https://linear.app/ghostnet-labs/issue/GHO-7), and a LoRa transport for openmanetd `internal/chanmig` under [GHO-52](https://linear.app/ghostnet-labs/issue/GHO-52)) are tracked on [GHO-90](https://linear.app/ghostnet-labs/issue/GHO-90).

## 5. Alternatives considered

| Alternative | Why not the first choice |
|---|---|
| Second HaLow radio | Carries real traffic, but a second HaLow on one host is blocked on driver support ([GHO-39](https://linear.app/ghostnet-labs/issue/GHO-39)) and costs far more power |
| 2.4 GHz LoRa (Semtech SX1280 class) | Avoids sharing the band with HaLow, but shares it with Wi-Fi backhaul and the GNSS's weakest margin, and has shorter range than sub-GHz (Unverified) |
| Raise transmit power instead | Already near the 1 W conducted limit on HaLow; 3 dB per doubling does not beat a nearby jammer and costs battery, heat and signature |
| Software only (never move every band at once) | Free and still worth doing, but it only helps where a second band reaches, which at long range it often does not |
