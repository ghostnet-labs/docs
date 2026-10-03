# V1 OpenVLM USB-C host power design review

**Scope:** GHO-11 desk review, checked 2026-10-02. This is supporting engineering analysis, not a selected BOM or released schematic. B-04/B-22/B-23 in [v1-selections.md](v1-selections.md) own the hardware selection; [v1-pinout-and-sequencing.md](v1-pinout-and-sequencing.md) owns GPIO allocation. D-027/D-028 remain applicable.

## Non-negotiable behavior

The external OpenVLM connector is a source/DFP, not the charge/service connector. TI's TUSB320LAI datasheet §8.2.1.2 requires a source to wait for Attached.SRC before supplying VBUS. Static Rp plus permanently energized VBUS is therefore not a complete design.

Treat `PORT_ENABLE = HUB_ALLOW AND ATTACHED_SRC AND SUPPLY_GOOD AND NOT FAULT_LATCH` as a schematic-review invariant, not a firmware-only promise. An integrated controller may implement the attach predicate internally. Reset, detach, loss of supply or a latched fault must override a software enable. Avoid analog Type-C audio-adapter confusion: OpenVLM is a USB audio/HID device.

| Hub allows port | Sink attached | Fault inhibited | VBUS permission |
|---|---|---|---|
| No | Either | Either | Off |
| Yes | No | No | Off |
| Yes | Yes | Yes | Off |
| Yes | Yes | No | On, subject to valid supply |

## Two viable component approaches

| Approach | Manufacturer evidence | Consequence for this carrier |
|---|---|---|
| TUSB320LAI CC controller + TPS2553 power switch | TUSB320LAI Rev D: fixed DFP via PORT high; open-drain ID goes low on source attachment. TPS2553 Rev F: adjustable 75–1700 mA typical limit, active-high enable, active-low fault, reverse-voltage protection; SOT-23 or WSON options. | Leading **analysis option** when the accessory budget is below 1.5 A. Requires attach/power-enable logic, VBUS discharge circuit, cable/VCONN policy and correct default-level design. ID cannot directly drive an active-high switch. No exact ordering suffix or resistor is selected. |
| TPS25810 integrated DFP + switch | Rev C: source attach/detach handling, VBUS discharge, VCONN and fault output; 3 A rated path; default/1.5 A advertisements use 1.7 A typical limit, 3 A advertisement uses 3.4 A typical limit. | Fewer functional blocks, but high fault-current allowance must be supported by the 5 V rail even when advertising default USB current. Not a drop-in low-current limiter; do not choose it solely to reduce chip count. |

TPS2553 continuous current is limited to 1.2 A through 125 °C junction or 1.5 A through 105 °C junction (§7.3). Junction limits are not enclosure ambient ratings. D-028 does not authorize relying on thermal shutdown during normal operation.

## Hub integration checks

TUSB4041I Rev F, Table 4-1 identifies port-3 PWRCTL3/BATEN3 at pin 1 and OVERCUR3z at pin 12. The latter expects a low fault indication. PWRCTL3 is also a reset-sampled battery-charging strap: the added attach logic must not alter its intended reset level. Configure and verify individual port power management and PWRCTL polarity; a ganged fault must not accidentally remove HaLow when only the accessory fails. Fault telemetry follows the canonical allocation, without a duplicate GPIO map here.

Pull-ups must use compatible powered domains. Check controller/switch/CM5 power-off leakage, not just signal polarity. A source on the other end of the cable must not back-power the node; the switch's reverse-voltage comparator is not a substitute for system testing.

## Sizing evidence required before selection

Capture OpenVLM USB descriptor power request, idle/record/playback/PTT load and startup inrush. Reconcile USB current advertisement with sustained capacity remaining after CM5 and other USB loads. GHO-10 owns rail capacity; selection cannot consume that capacity twice.

Use guaranteed minimum current limit above the supported device load and guaranteed maximum below the safe upstream fault budget. Example: TPS2553 with 49.9 kOhm has 475/520/565 mA minimum/typical/maximum across its specified temperature range (§7.5); it does **not** guarantee a 500 mA load. Evaluate resistor tolerance and the full min/max curves, not a nominal-only “500 mA” label.

Check worst-case switch drop and cable/trace loss, `Vconnector_min = Vrail_min - Iload × (Rswitch_max + Rtrace + Rcable)`; verify both normal delivery and regulator response to a short. Include bulk capacitance, inrush, discharge time and switch dissipation in the review.

## Release evidence

Before schematic release: exact part suffix/package and manufacturer land pattern; current-limit tolerance worksheet; attach gate and reset truth table; discharge/backfeed review; fault pull-up domains; USB data/CC/VBUS ESD parts and loading review. Before qualification: both plug orientations, detach/reattach during audio, short/reverse-source cable, simultaneous HaLow/CM5 loading, hub reset and repeated fault recovery. GHO-11 stays open; this work does not select Ethernet/GNSS protection.

## Primary references

- [TUSB320LAI Rev D](https://www.ti.com/lit/ds/symlink/tusb320lai.pdf), §§5, 8.2.
- [TPS2553 Rev F](https://www.ti.com/lit/ds/symlink/tps2553.pdf), §§7.3, 7.5, 9.5.
- [TPS25810 Rev C](https://www.ti.com/lit/ds/symlink/tps25810.pdf), §§5, 7.3.
- [TUSB4041I Rev F](https://www.ti.com/lit/ds/symlink/tusb4041i.pdf), Table 4-1 and application schematic.
