"""Portable unit coverage for the Astra checkpoint policy."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "advisor_policy_under_test", ROOT / "scripts" / "advisor_policy.py"
)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class AdvisorPolicyTests(unittest.TestCase):
    def test_approved_plan_material_checkpoint_consults(self) -> None:
        self.assertTrue(
            policy.should_consult(
                approved_plan=True,
                uncertainty=True,
                material_impact=True,
            )
        )

    def test_routine_and_cheaply_resolved_work_skips(self) -> None:
        for flags in (
            {"routine": True, "uncertainty": True, "material_impact": True},
            {
                "approved_plan": True,
                "uncertainty": True,
                "material_impact": True,
                "cheap_check_resolved": True,
            },
            {
                "approved_plan": True,
                "uncertainty": True,
                "material_impact": True,
                "implementation_started": True,
            },
            {
                "approved_plan": True,
                "uncertainty": True,
                "material_impact": True,
                "completion_check": True,
            },
            {
                "approved_plan": True,
                "uncertainty": True,
                "material_impact": True,
                "checkpoint_consulted": True,
            },
            {
                "approved_plan": True,
                "uncertainty": True,
                "material_impact": True,
                "no_delegation": True,
            },
        ):
            self.assertFalse(policy.should_consult(**flags))

    def test_explicit_standalone_material_request_consults(self) -> None:
        self.assertTrue(
            policy.should_consult(
                standalone=True,
                explicit_advisor=True,
                uncertainty=True,
                material_impact=True,
            )
        )
        self.assertFalse(
            policy.should_consult(
                standalone=True,
                explicit_advisor=False,
                uncertainty=True,
                material_impact=True,
            )
        )

    def test_default_selection_is_astra_low(self) -> None:
        self.assertEqual(
            policy.resolve_selection(),
            {
                "level": "low",
                "model": "gpt-6-astra",
                "effort": "low",
            },
        )

    def test_higher_level_requires_verified_chain(self) -> None:
        with self.assertRaises(policy.PolicyError):
            policy.resolve_selection("medium")
        self.assertEqual(
            policy.resolve_selection("medium", chain_authorized=True)["effort"],
            "medium",
        )

    def test_extra_high_maps_only_to_xhigh(self) -> None:
        self.assertEqual(
            policy.resolve_selection("extra_high", chain_authorized=True),
            {"level": "extra_high", "model": "gpt-6-astra", "effort": "xhigh"},
        )
        with self.assertRaises(policy.PolicyUnavailable):
            policy.resolve_selection(
                "extra_high", chain_authorized=True, supported_efforts={"high"}
            )

    def test_escalation_must_be_immediate_and_explain_why(self) -> None:
        valid = {
            "next_level": "medium",
            "reason": "The low pass cannot distinguish two compatible state models.",
            "unresolved_difficulty": "The ordering invariant remains ambiguous.",
            "required_resolution": "Compare both state-transition traces.",
        }
        self.assertEqual(policy.validate_escalation("low", valid), "medium")
        self.assertIsNone(
            policy.validate_escalation(
                "medium",
                {
                    "next_level": None,
                    "reason": "Evidence is sufficient.",
                    "unresolved_difficulty": "",
                    "required_resolution": "",
                },
            )
        )
        with self.assertRaises(policy.PolicyError):
            policy.validate_escalation("low", {**valid, "next_level": "high"})


if __name__ == "__main__":
    unittest.main()
