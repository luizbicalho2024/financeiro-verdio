from __future__ import annotations

import unittest

from app_core.simulator_pricing import (
    billing_type_for_product,
    calculate_contract_margin,
    eligible_billing_periods,
    first_three_billings,
    legacy_equipment_pricing,
    resolve_product_name,
    select_plan_name,
)

PRICING = {
    "PLANOS_PJ": {
        "12 Meses": {"GPRS / Gsm": 80.0, "Satélite": 190.0, "Leitor de Rede CAN / Telemetria": 75.0},
        "24 Meses": {"GPRS / Gsm": 60.0, "Satélite": 140.0, "Leitor de Rede CAN / Telemetria": 55.0},
        "36 Meses": {"GPRS / Gsm": 50.0, "Satélite": 110.0, "Leitor de Rede CAN / Telemetria": 45.0},
    },
    "CUSTOS_PJ": {
        "12 Meses": {"GPRS / Gsm": 40.0, "Satélite": 100.0, "Leitor de Rede CAN / Telemetria": 35.0},
        "24 Meses": {"GPRS / Gsm": 30.0, "Satélite": 80.0, "Leitor de Rede CAN / Telemetria": 30.0},
        "36 Meses": {"GPRS / Gsm": 25.0, "Satélite": 70.0, "Leitor de Rede CAN / Telemetria": 25.0},
    },
}


class SimulatorPricingTests(unittest.TestCase):
    def test_select_plan_uses_exact_or_nearest_term(self):
        self.assertEqual(select_plan_name(PRICING, 24), "24 Meses")
        self.assertEqual(select_plan_name(PRICING, 18), "12 Meses")
        self.assertEqual(select_plan_name(PRICING, 30), "24 Meses")

    def test_product_aliases_map_billing_types(self):
        self.assertEqual(billing_type_for_product("GPRS / Gsm"), "GPRS")
        self.assertEqual(billing_type_for_product("Satélite"), "SATELITE")
        self.assertEqual(billing_type_for_product("Leitor de Rede CAN / Telemetria"), "CAN")
        self.assertEqual(resolve_product_name("SATELITAL", PRICING), "Satélite")

    def test_contract_margin_is_weighted_by_mix(self):
        result = calculate_contract_margin(
            PRICING,
            24,
            {"GPRS / Gsm": 60.0, "Satélite": 160.0},
            {"GPRS / Gsm": 2, "Satélite": 1},
        )
        self.assertTrue(result["costs_complete"])
        self.assertAlmostEqual(result["margin_percent"], 50.0, places=6)

    def test_missing_cost_blocks_margin_proof(self):
        pricing = {
            "PLANOS_PJ": {"12 Meses": {"GPRS / Gsm": 80.0}},
            "CUSTOS_PJ": {"12 Meses": {"GPRS / Gsm": 0.0}},
        }
        result = calculate_contract_margin(
            pricing,
            12,
            {"GPRS / Gsm": 80.0},
            {"GPRS / Gsm": 1},
        )
        self.assertFalse(result["costs_complete"])
        self.assertIsNone(result["margin_percent"])

    def test_legacy_prices_follow_simulator_terms(self):
        legacy = legacy_equipment_pricing(PRICING)
        self.assertEqual(legacy["GPRS"]["price1"], 80.0)
        self.assertEqual(legacy["GPRS"]["price2"], 60.0)
        self.assertEqual(legacy["GPRS"]["price3"], 50.0)

    def test_eligible_periods_start_after_contract_month(self):
        self.assertEqual(
            eligible_billing_periods("2026-06-20"),
            ["2026-07", "2026-08", "2026-09"],
        )

    def test_eligible_periods_cross_year_boundary(self):
        self.assertEqual(
            eligible_billing_periods("2026-12-20"),
            ["2027-01", "2027-02", "2027-03"],
        )

    def test_missing_month_is_not_replaced_by_m4(self):
        history = [
            {"cliente": "ACME", "period_key": "2026-06", "valor_total": 60},
            {"cliente": "ACME", "period_key": "2026-07", "valor_total": 70},
            {"cliente": "ACME", "period_key": "2026-09", "valor_total": 90},
            {"cliente": "ACME", "period_key": "2026-10", "valor_total": 100},
        ]
        result = first_three_billings(history, "ACME", "2026-06-20")
        periods = [item["period_key"] for item in result]
        self.assertEqual(periods, ["2026-07", "2026-09"])
        self.assertNotIn("2026-10", periods)

    def test_billings_are_returned_in_m1_m2_m3_order(self):
        history = [
            {"cliente": "ACME", "period_key": "2026-09", "valor_total": 90},
            {"cliente": "ACME", "period_key": "2026-07", "valor_total": 70},
            {"cliente": "ACME", "period_key": "2026-08", "valor_total": 80},
        ]
        result = first_three_billings(history, "ACME", "2026-06-20")
        self.assertEqual(
            [item["period_key"] for item in result],
            ["2026-07", "2026-08", "2026-09"],
        )


if __name__ == "__main__":
    unittest.main()
