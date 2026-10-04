#!/usr/bin/env python3
"""Conditional conservative capacitor budget; never a hardware qualification."""
import argparse
import json
import math


def budget(*, cells, cell_f, capacitance_factor, stack_esr_ohm,
           start_v, terminal_min_v, average_current_a, efficiency,
           load_w, gap_s, shutdown_w, shutdown_s):
    values = locals().copy()
    if not isinstance(cells, int) or isinstance(cells, bool) or cells < 1:
        raise ValueError("cells must be a positive integer")
    if any(not math.isfinite(v) for v in values.values()):
        raise ValueError("all inputs must be finite")
    if not 0 < capacitance_factor <= 1 or not 0 < efficiency <= 1:
        raise ValueError("capacitance factor and efficiency must be in (0, 1]")
    if min(cell_f, start_v, terminal_min_v, average_current_a, load_w) <= 0:
        raise ValueError("capacitance, voltages, current and load must be positive")
    if min(stack_esr_ohm, shutdown_w, shutdown_s) < 0:
        raise ValueError("ESR and shutdown inputs must not be negative")
    if gap_s < 10:
        raise ValueError("D-027 requires a full-node gap of at least 10 seconds")
    if shutdown_s > 0 and shutdown_w == 0:
        raise ValueError("a nonzero shutdown interval requires shutdown load")

    # For constant-power input: Vcap = Vterminal + I*ESR and I=P/Vterminal.
    # Stay on the high-voltage (stable) branch, Vterminal >= sqrt(P*ESR).
    peak_input_w = max(load_w, shutdown_w) / efficiency
    terminal_floor = max(terminal_min_v, peak_input_w / average_current_a,
                         math.sqrt(peak_input_w * stack_esr_ohm))
    stack_floor = terminal_floor + peak_input_w * stack_esr_ohm / terminal_floor
    c_effective = cell_f * capacitance_factor / cells
    voltage_window = max(0.0, start_v**2 - stack_floor**2)
    usable_j = 0.5 * c_effective * voltage_window

    def draw_bound(w):
        p = w / efficiency
        # Current never exceeds P/terminal_floor while voltage remains in range.
        return p + (p / terminal_floor)**2 * stack_esr_ohm

    gap_j = draw_bound(load_w) * gap_s
    reserve_j = draw_bound(shutdown_w) * shutdown_s
    required_j = gap_j + reserve_j
    return {
        "classification": "conditional desk budget; not hardware qualification",
        "inputs": values,
        "effective_stack_f": c_effective,
        "terminal_floor_v": terminal_floor,
        "open_circuit_stack_floor_v": stack_floor,
        "usable_energy_j": usable_j,
        "gap_energy_bound_j": gap_j,
        "shutdown_reserve_bound_j": reserve_j,
        "energy_margin_j": usable_j - required_j,
        "gap_duration_lower_bound_s": usable_j / draw_bound(load_w),
        "gap_plus_reserve_budget_satisfied": usable_j >= required_j,
        "required_nominal_cell_f": (
            2 * required_j * cells / (capacitance_factor * voltage_window)
            if voltage_window > 0 else None),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=int, required=True)
    for name in ("cell-f", "capacitance-factor", "stack-esr-ohm", "start-v",
                 "terminal-min-v", "average-current-a", "efficiency", "load-w",
                 "gap-s", "shutdown-w", "shutdown-s"):
        parser.add_argument("--" + name, type=float, required=True)
    try:
        result = budget(**vars(parser.parse_args()))
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
