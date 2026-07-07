from __future__ import annotations

import unittest

from models.pricing import estimate_cost


class PricingTests(unittest.TestCase):
    def test_gemini_pro_short_and_long_context_tiers(self) -> None:
        short = estimate_cost(
            "google",
            "gemini-3.1-pro-preview",
            input_tokens=200_000,
            output_tokens=1_000_000,
            cached_input_tokens=10_000,
        )
        long = estimate_cost(
            "google",
            "gemini-3.1-pro-preview",
            input_tokens=200_001,
            output_tokens=1_000_000,
            cached_input_tokens=10_000,
        )
        self.assertEqual(short["tier"], "short_context")
        self.assertEqual(long["tier"], "long_context")
        self.assertLess(short["total"], long["total"])
        self.assertEqual(short["cached_input"], 0.002)
        self.assertEqual(long["cached_input"], 0.004)

    def test_gemini_flash_paid_list_estimate(self) -> None:
        cost = estimate_cost("google", "gemini-3.5-flash", input_tokens=1_000_000, output_tokens=1_000_000)
        self.assertEqual(cost["input"], 0.75)
        self.assertEqual(cost["output"], 4.5)
        self.assertEqual(cost["total"], 5.25)
        self.assertIn("Free Tier", cost["note"])

    def test_gemini_reasoning_tokens_are_billable_output(self) -> None:
        cost = estimate_cost(
            "google",
            "gemini-3.5-flash",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            reasoning_tokens=1_000_000,
        )
        self.assertEqual(cost["output"], 4.5)
        self.assertEqual(cost["reasoning"], 4.5)
        self.assertEqual(cost["total"], 9.75)

    def test_grok_rates(self) -> None:
        grok = estimate_cost("xai", "grok-4.3", input_tokens=1_000_000, output_tokens=1_000_000, cached_input_tokens=100_000)
        build = estimate_cost("xai", "grok-build-0.1", input_tokens=1_000_000, output_tokens=1_000_000, cached_input_tokens=100_000)
        self.assertEqual(grok["input"], 1.125)
        self.assertEqual(grok["cached_input"], 0.02)
        self.assertEqual(grok["output"], 2.5)
        self.assertEqual(build["input"], 0.9)
        self.assertEqual(build["cached_input"], 0.02)
        self.assertEqual(build["output"], 2.0)

    def test_glm_rates_and_exact_free_flash(self) -> None:
        paid = estimate_cost("zai", "glm-5.2", input_tokens=1_000_000, output_tokens=1_000_000, cached_input_tokens=100_000)
        free = estimate_cost("zai", "glm-4.7-flash", input_tokens=1_000_000, output_tokens=1_000_000, cached_input_tokens=100_000)
        flashx = estimate_cost("zai", "glm-4.7-flashx", input_tokens=1_000_000, output_tokens=1_000_000, cached_input_tokens=100_000)
        self.assertEqual(paid["input"], 1.26)
        self.assertEqual(paid["cached_input"], 0.026)
        self.assertEqual(paid["output"], 4.4)
        self.assertEqual(free["total"], 0.0)
        self.assertGreater(flashx["total"], 0.0)


if __name__ == "__main__":
    unittest.main()
