# POC exit report (GHO-33) and PCB inputs (GHO-32)

**Status: template, no results yet.** The bench hardware is not ordered
([GHO-36](https://linear.app/ghostnet-labs/issue/GHO-36)). Fill each row from
the evidence on the linked issue. A row stays "Not run" until there is a log,
photo or CSV on that issue. Nothing here counts as V1 validation: the bench
radios and power path are not the V1 parts
([bench-bom-and-topology.md](bench-bom-and-topology.md) §1).

## 1. Setup under test

| Item | Node 1 | Node 2 |
| -- | -- | -- |
| Firmware commit (`24.10`) and CI run | | |
| Image file and `sha256` | | |
| packages feed pin (`feeds.conf.default`) | | |
| openmanetd version (`openmanetd version`) | | |
| CM5 serial / carrier | | |
| HaLow card and Morse firmware (`morse_cli version`) | | |
| Wi-Fi card, driver and firmware | | |
| GNSS module and firmware | | |
| Power source (UPS / bench supply) | | |

## 2. Exit criteria

| # | Criterion | Evidence issue | Result | Notes / follow-up |
| -- | -- | -- | -- | -- |
| E1 | CM5 boots the image from eMMC, storage and Ethernet work, boot log captured (Q-01) | [GHO-28](https://linear.app/ghostnet-labs/issue/GHO-28) | Not run | |
| E2 | HaLow, Wi-Fi, Bluetooth, GNSS (fix + PPS) and Ethernet each work on one node | [GHO-29](https://linear.app/ghostnet-labs/issue/GHO-29), [GHO-47](https://linear.app/ghostnet-labs/issue/GHO-47) | Not run | |
| E3 | Power by state (idle, HaLow TX, Wi-Fi TX, both) and SoC temperature, open and closed box (Q-13) | [GHO-30](https://linear.app/ghostnet-labs/issue/GHO-30) | Not run | |
| E4 | Two-node mesh on both radios: association, batman-adv routing, ping, throughput (mesh-test-plan M1–M6) | [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) | Not run | |
| E5 | ATAK multicast across the mesh (M7) | [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) | Not run | |
| E6 | Both radios at once, radio reset and node power-cycle recovery (M8–M11) | [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) | Not run | |
| E7 | GNSS C/N0 idle vs HaLow and Wi-Fi TX; power where C/N0 falls (Q-14, D-020) | [GHO-31](https://linear.app/ghostnet-labs/issue/GHO-31) | Not run | |
| E8 | 802.11s mesh point on the V1 Wi-Fi card (AW7916-AED) | [GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37) | Not run | Only if the card is on the bench |

## 3. Failures and workarounds

| Issue | Symptom | Workaround used on the bench | Needs a fix in |
| -- | -- | -- | -- |
| | | | |

## 4. PCB inputs (GHO-32)

Every result that changes, confirms or adds risk to the V1 carrier gets a row
and a link to the V1 issue that carries it.

| POC result | V1 effect (change / confirm / risk) | V1 issue or record |
| -- | -- | -- |
| Node power by state (E3) | Sizes the 3.3 V and 5 V rails, eFuse margin (D-019) and pack run time | [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10) |
| Closed-box temperature (E3) | Fanless thermal path and enclosure | [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12) |
| GNSS C/N0 vs TX (E7) | GNSS placement and HaLow power cap (RF coexistence) | [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12) |
| Radio reset recovery (E6) | Radio power/reset control lines and fault-recovery software | [GHO-9](https://linear.app/ghostnet-labs/issue/GHO-9), [GHO-20](https://linear.app/ghostnet-labs/issue/GHO-20) |
| Dual-radio mesh behaviour (E4–E6) | What the V1 dual-radio validation must repeat on V1 radios | [GHO-22](https://linear.app/ghostnet-labs/issue/GHO-22) |
| Wi-Fi mesh on the AW7916-AED (E8) | Closes the V1 Wi-Fi selection | [GHO-37](https://linear.app/ghostnet-labs/issue/GHO-37) |
| Test points and probes used during bring-up | Test points to keep on V1 | [GHO-13](https://linear.app/ghostnet-labs/issue/GHO-13) |

## 5. Remaining risks

| Risk | Why it is still open | Owner issue |
| -- | -- | -- |
| GW16170 transmit power, current and heat | The bench uses the GW16167 | [GHO-12](https://linear.app/ghostnet-labs/issue/GHO-12) |
| V1 power path and INA228 telemetry | The bench uses the Waveshare UPS and INA219 | [GHO-10](https://linear.app/ghostnet-labs/issue/GHO-10) |
