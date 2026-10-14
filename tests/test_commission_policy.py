import unittest
from decimal import Decimal
from app_core.commission_policy import (
    contract_discount, discount_is_eligible, target_for_seller,
    installation_attainment, first_month_percent, recurring_percent,
    percent_reward, shift_month,
)


class TestCommissionPolicy(unittest.TestCase):
    def test_target(self):
        self.assertEqual(target_for_seller(2), Decimal("12.5"))
        self.assertEqual(installation_attainment(10, 2), Decimal("80"))

    def test_invalid_target(self):
        with self.assertRaises(ValueError):
            target_for_seller(0)

    def test_first_month_brackets(self):
        for value, expected in [(0,0), (79.99,0), (80,10), (99.99,10),
                                (100,15), (109.99,15), (110,20), (150,20)]:
            with self.subTest(value=value):
                self.assertEqual(first_month_percent(value), Decimal(expected))

    def test_recurring_brackets(self):
        for value, expected in [(0,0), (2000,0), (2000.01,2),
                                (5000,2), (5000.01,3), (9000,3),
                                (12000,3), (12000.01,4)]:
            with self.subTest(value=value):
                self.assertEqual(recurring_percent(value), Decimal(expected))

    def test_example(self):
        self.assertEqual(percent_reward(9000, 10), 900)
        self.assertEqual(percent_reward(9000, recurring_percent(9000)), 270)

    def test_discount(self):
        d, reason = contract_discount({"GPRS": 85}, {"GPRS": 2}, {"GPRS": 100})
        self.assertEqual(d, 15)
        self.assertTrue(discount_is_eligible(d))
        d, _ = contract_discount({"GPRS": 84.99}, {"GPRS": 2}, {"GPRS": 100})
        self.assertFalse(discount_is_eligible(d))

    def test_weighted_discount(self):
        d, _ = contract_discount({"A": 90, "B": 80}, {"A": 2, "B": 1}, {"A": 100, "B": 100})
        self.assertAlmostEqual(d, 13.3333, places=4)
        self.assertTrue(discount_is_eligible(d))

    def test_missing_table_blocks(self):
        d, reason = contract_discount({"A": 100}, {"A": 1}, {})
        self.assertIsNone(d)
        self.assertIn("referencia", reason)
        self.assertFalse(discount_is_eligible(d))

    def test_no_devices_blocks(self):
        d, _ = contract_discount({"A": 100}, {"A": 0}, {"A": 100})
        self.assertIsNone(d)

    def test_shift_month(self):
        self.assertEqual(shift_month("2026-12", 1), "2027-01")
        self.assertEqual(shift_month("2026-01", -1), "2025-12")


if __name__ == "__main__":
    unittest.main()