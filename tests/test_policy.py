import unittest

from earn_or_halt.policy import EconomicPolicy


class PolicyTests(unittest.TestCase):
    def base_stats(self, **overrides):
        value = {
            "revenue_cents": 0,
            "cost_cents": 0,
            "daily_cost_cents": 0,
            "succeeded_jobs": 0,
            "consecutive_failures": 0,
        }
        value.update(overrides)
        return value

    def test_continues_during_grace_period(self):
        policy = EconomicPolicy(starting_credit_cents=10, grace_jobs=3)
        decision = policy.evaluate(self.base_stats(), next_cost_cents=1)
        self.assertFalse(decision.should_halt)

    def test_halts_when_next_cost_exceeds_credit(self):
        policy = EconomicPolicy(starting_credit_cents=2)
        decision = policy.evaluate(self.base_stats(cost_cents=2), next_cost_cents=1)
        self.assertTrue(decision.should_halt)
        self.assertIn("insufficient", decision.reason)

    def test_halts_on_bad_margin_after_grace(self):
        policy = EconomicPolicy(grace_jobs=1, minimum_margin_percent=50)
        decision = policy.evaluate(
            self.base_stats(revenue_cents=100, cost_cents=60, succeeded_jobs=1)
        )
        self.assertTrue(decision.should_halt)
        self.assertIn("margin", decision.reason)

    def test_halts_on_daily_cap(self):
        policy = EconomicPolicy(daily_cost_cap_cents=10)
        decision = policy.evaluate(self.base_stats(daily_cost_cents=9), next_cost_cents=2)
        self.assertTrue(decision.should_halt)

    def test_external_halt_wins(self):
        policy = EconomicPolicy()
        decision = policy.evaluate(self.base_stats(), external_halt_reason="operator")
        self.assertEqual(decision.reason, "operator")
        self.assertTrue(decision.should_halt)


if __name__ == "__main__":
    unittest.main()
