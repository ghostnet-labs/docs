import math
import unittest
from bridge_budget import budget


class BridgeBudgetTest(unittest.TestCase):
    def case(self, **changes):
        inputs = dict(cells=4, cell_f=50, capacitance_factor=.8,
                      stack_esr_ohm=0, start_v=8, terminal_min_v=3.5,
                      average_current_a=5.8, efficiency=.9, load_w=25,
                      gap_s=10, shutdown_w=5, shutdown_s=10)
        inputs.update(changes)
        return budget(**inputs)

    def test_hand_computed_current_floor_invalidates_50f(self):
        r = self.case()
        floor = 25 / (.9 * 5.8)
        energy = .5 * (50 * .8 / 4) * (8**2 - floor**2)
        self.assertAlmostEqual(r["open_circuit_stack_floor_v"], floor)
        self.assertAlmostEqual(r["usable_energy_j"], energy)
        self.assertFalse(r["gap_plus_reserve_budget_satisfied"])

    def test_series_capacitance_and_extra_reserve(self):
        r = self.case(cell_f=100)
        self.assertEqual(r["effective_stack_f"], 20)
        self.assertAlmostEqual(r["shutdown_reserve_bound_j"], 50/.9)
        self.assertTrue(r["gap_plus_reserve_budget_satisfied"])

    def test_esr_reduces_margin_and_raises_floor(self):
        a, b = self.case(), self.case(stack_esr_ohm=.08)
        self.assertGreater(b["open_circuit_stack_floor_v"], a["open_circuit_stack_floor_v"])
        self.assertLess(b["energy_margin_j"], a["energy_margin_j"])

    def test_conservative_duration_against_numerical_constant_power(self):
        # Independently integrate capacitor charge at the physical low-current root.
        r = self.case(stack_esr_ohm=.08)
        high, low = 8, r["open_circuit_stack_floor_v"]
        step = (high - low) / 20000
        power, resistance, elapsed = 25/.9, .08, 0
        for index in range(20000):
            voltage = low + (index + .5) * step
            current = (voltage - math.sqrt(voltage**2 - 4*resistance*power))/(2*resistance)
            elapsed += r["effective_stack_f"] * step / current
        self.assertLessEqual(r["gap_duration_lower_bound_s"], elapsed)

    def test_low_initial_charge_cannot_satisfy_budget(self):
        r = self.case(start_v=4)
        self.assertEqual(r["usable_energy_j"], 0)
        self.assertIsNone(r["required_nominal_cell_f"])

    def test_shutdown_can_set_worst_case_floor(self):
        r = self.case(shutdown_w=30)
        self.assertAlmostEqual(r["terminal_floor_v"], 30/(.9*5.8))

    def test_rejects_bad_inputs_and_shorter_requirement(self):
        for bad in (dict(efficiency=0), dict(load_w=math.nan),
                    dict(stack_esr_ohm=-1), dict(gap_s=9.9),
                    dict(cells=2.5), dict(capacitance_factor=1.1),
                    dict(shutdown_w=0)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.case(**bad)


if __name__ == "__main__":
    unittest.main()
