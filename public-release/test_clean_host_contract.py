"""Regression checks for the clean-host synthetic contract and current docs label."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CleanHostContractTests(unittest.TestCase):
    def test_synthetic_runtime_uses_requested_low_effort(self) -> None:
        script = (ROOT / "public-release" / "verify-clean-host.sh").read_text(encoding="utf-8")
        self.assertIn("effort:$effort", script)
        self.assertNotIn('effort:"high"', script)

    def test_retired_acceptance_record_is_explicitly_historical(self) -> None:
        walkthrough = (ROOT / "docs" / "candidate-walkthrough.md").read_text(encoding="utf-8")
        self.assertIn("Historical 1.3.4 acceptance record", walkthrough)
        self.assertIn("does not describe the current 1.4.5 active routing contract", walkthrough)


if __name__ == "__main__":
    unittest.main()
