import unittest

from earn_or_halt.providers import MockProvider


class ProviderTests(unittest.TestCase):
    def test_mock_provider_returns_three_variants(self):
        result = MockProvider(1).generate(
            {"recipient_name": "Anna", "company": "Example", "offer": "automate intake"},
            {},
        )
        self.assertEqual(result.cost_cents, 1)
        self.assertEqual(len(result.output["variants"]), 3)


if __name__ == "__main__":
    unittest.main()
