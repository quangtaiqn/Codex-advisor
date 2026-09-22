"""Portable state-machine tests for the durable Advisor checkpoint ledger."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "advisor_chain_under_test", ROOT / "scripts" / "advisor_chain.py"
)
assert SPEC and SPEC.loader
chain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chain)


POLICY = "sha256:" + "1" * 64
PACKET = "sha256:" + "2" * 64
RESULT = "sha256:" + "3" * 64


class AdvisorChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "chains"
        self.store = chain.ChainStore(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def reserve(self, key: str = "task/checkpoint-1", *, level: str = "low", packet: str = PACKET, authorize: bool = False):
        return self.store.reserve(
            key,
            policy_digest=POLICY,
            packet_digest=packet,
            level=level,
            authorize_escalation=authorize,
        )

    def test_reservation_is_durable_and_replay_never_relaunches(self) -> None:
        first = self.reserve()
        self.assertEqual(first["action"], "launch")
        second = self.reserve()
        self.assertEqual(second["action"], "resume_required")
        self.assertEqual(first["state"]["chain_id"], second["state"]["chain_id"])
        self.assertEqual(second["state"]["levels"]["low"]["status"], "reserved")

        state_file = next(self.root.glob("*.json"))
        persisted = state_file.read_text(encoding="utf-8")
        self.assertNotIn("task/checkpoint-1", persisted)
        self.assertEqual(json.loads(persisted)["levels"]["low"]["effort"], "low")

    def test_packet_change_cannot_reset_reserved_level(self) -> None:
        self.reserve()
        with self.assertRaises(chain.ChainError):
            self.reserve(packet="sha256:" + "4" * 64)

    def test_valid_adjacent_escalation_is_the_only_next_reservation(self) -> None:
        self.reserve()
        self.store.complete(
            "task/checkpoint-1", policy_digest=POLICY, level="low", next_level="medium", result_digest=RESULT
        )
        medium = self.reserve(level="medium", packet="sha256:" + "4" * 64, authorize=True)
        self.assertEqual(medium["action"], "launch")
        self.assertEqual(medium["state"]["levels"]["medium"]["effort"], "medium")
        with self.assertRaises(chain.ChainError):
            self.reserve(level="extra_high", packet="sha256:" + "5" * 64, authorize=True)

    def test_uncertain_is_terminal_and_implementation_started_blocks_chain(self) -> None:
        self.reserve()
        uncertain = self.store.mark_uncertain(
            "task/checkpoint-1", policy_digest=POLICY, level="low", failure_code="timed_out"
        )
        self.assertEqual(uncertain["status"], "uncertain")
        with self.assertRaises(chain.ChainError):
            self.reserve()

        self.store = chain.ChainStore(self.root.parent / "other")
        self.store.reserve(
            "task/checkpoint-2",
            policy_digest=POLICY,
            packet_digest=PACKET,
            level="low",
        )
        self.store.complete(
            "task/checkpoint-2", policy_digest=POLICY, level="low", next_level=None, result_digest=RESULT
        )
        locked = self.store.mark_implementation_started(
            "task/checkpoint-2", policy_digest=POLICY
        )
        self.assertTrue(locked["implementation_started"])
        with self.assertRaises(chain.ChainError):
            self.store.reserve(
                "task/checkpoint-2",
                policy_digest=POLICY,
                packet_digest=PACKET,
                level="low",
            )

    def test_extra_high_records_the_explicit_xhigh_runtime_mapping(self) -> None:
        key = "task/full-ladder"
        store = self.store
        for current, next_level in (
            ("low", "medium"),
            ("medium", "high"),
            ("high", "extra_high"),
        ):
            packet = "sha256:" + hashlib.sha256(current.encode()).hexdigest()
            store.reserve(
                key,
                policy_digest=POLICY,
                packet_digest=packet,
                level=current,
                authorize_escalation=current != "low",
            )
            store.complete(key, policy_digest=POLICY, level=current, next_level=next_level, result_digest=RESULT)
        final = store.reserve(
            key,
            policy_digest=POLICY,
            packet_digest="sha256:" + "6" * 64,
            level="extra_high",
            authorize_escalation=True,
        )
        self.assertEqual(final["state"]["levels"]["extra_high"]["effort"], "xhigh")
        done = store.complete(key, policy_digest=POLICY, level="extra_high", next_level=None, result_digest=RESULT)
        self.assertEqual(done["status"], "complete")


if __name__ == "__main__":
    unittest.main()
