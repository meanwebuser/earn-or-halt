import tempfile
import unittest
from pathlib import Path

from earn_or_halt.storage import Storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temporary.name) / "test.sqlite3")

    def tearDown(self):
        self.temporary.cleanup()

    def test_job_and_ledger_lifecycle(self):
        job = self.storage.enqueue_job(
            {"company": "Example", "offer": "Automation"},
            price_cents=29,
            estimated_cost_cents=1,
        )
        claimed = self.storage.claim_next_job()
        self.assertEqual(claimed["id"], job["id"])
        self.storage.complete_job(job["id"], {"variants": []}, actual_cost_cents=1)
        current = self.storage.get_job(job["id"])
        self.assertEqual(current["status"], "succeeded")
        stats = self.storage.stats()
        self.assertEqual(stats["revenue_cents"], 29)
        self.assertEqual(stats["cost_cents"], 1)
        self.assertEqual(stats["profit_cents"], 28)

    def test_halt_is_persistent(self):
        self.storage.request_halt("operator")
        self.assertEqual(self.storage.halt_reason(), "operator")
        self.storage.clear_halt()
        self.assertIsNone(self.storage.halt_reason())


if __name__ == "__main__":
    unittest.main()
