"""Bounded parent-inspector proof using generated sessions, never inference."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from advisor_transport_support import config

ROOT = Path(__file__).resolve().parents[1]
THREAD = "abababab-abab-7aba-8aba-abababababab"
INSPECTOR = Path(
    os.environ.get("TEST_PARENT_INSPECTOR", ROOT / "scripts/inspect-parent-runtime.sh")
)


class ParentInspectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sessions = self.root / "sessions"
        self.sessions.mkdir()
        self.rollout = self.sessions / f"rollout-generated-{THREAD}.jsonl"
        self.safe = [
            {"type": "session_meta", "payload": {"id": THREAD}},
            {
                "type": "turn_context",
                "payload": {
                    "sandbox_policy": {"type": "workspace-write"},
                    "permission_profile": {"type": "managed"},
                },
            },
        ]
        self.write(self.safe)

    def write(self, rows):
        self.rollout.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def inspect(self):
        started = time.monotonic()
        try:
            code, out = config._run_bounded_output(
                [
                    "env",
                    "CODEX_THREAD_ID=" + THREAD,
                    "sh",
                    str(INSPECTOR),
                    "--sessions-dir",
                    str(self.sessions),
                ],
                timeout_seconds=3,
                max_bytes=10000,
            )
            self.assertEqual(code, 0)
            result = json.loads(out)
        except config.ConfigError as error:
            result = {"status": "probe-unavailable", "diagnostic": str(error)}
        return result, time.monotonic() - started

    def available(self):
        result, elapsed = self.inspect()
        self.assertEqual(
            result,
            {
                "status": "available",
                "thread_id": THREAD,
                "sandbox_policy_type": "workspace-write",
                "permission_profile_type": "managed",
            },
        )
        self.assertLess(elapsed, 3)
        return elapsed

    def unavailable(self):
        result, _ = self.inspect()
        self.assertEqual(
            result,
            {
                "status": "unavailable",
                "reason_type": "parent_runtime_unavailable",
                "redacted": True,
            },
        )

    def test_large_safe_parent_matches_small_within_probe_budget(self):
        small = self.available()
        padding = (
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {"text": "generated harmless text " * 340},
                }
            ).encode()
            + b"\n"
        )
        with self.rollout.open("ab") as stream:
            for _ in range((24 * 1024 * 1024) // len(padding)):
                stream.write(padding)
        self.assertGreater(self.rollout.stat().st_size, 23 * 1024 * 1024)
        large = self.available()
        print(
            json.dumps(
                {
                    "fixture_bytes": self.rollout.stat().st_size,
                    "small_seconds": small,
                    "large_seconds": large,
                    "budget_seconds": 3,
                }
            ),
            flush=True,
        )

    def test_late_unsafe_mixed_and_conflicting_metadata_are_rejected(self):
        self.available()
        for late in (
            {
                "type": "turn_context",
                "payload": {
                    "sandbox_policy": {"type": "danger-full-access"},
                    "permission_profile": {"type": "managed"},
                },
            },
            {
                "type": "turn_context",
                "payload": {
                    "sandbox_policy": {"type": "workspace-write"},
                    "permission_profile": {"type": "disabled"},
                },
            },
            {"type": "session_meta", "payload": {"id": THREAD}},
        ):
            with self.subTest(late=late):
                self.write(
                    [
                        *self.safe,
                        {
                            "type": "event_msg",
                            "payload": {"text": "DO_NOT_LEAK_PARENT_CONTENT"},
                        },
                        late,
                    ]
                )
                self.unavailable()

    def test_invalid_duplicate_nonfinite_encoding_and_truncated_tail_fail_closed(self):
        self.available()
        clean = self.rollout.read_bytes()
        for tail in (
            b'{"type":"event_msg","payload":{"x":1,"x":2}}\n',
            b'{"type":"event_msg","payload":NaN}\n',
            b'{"type":"event_msg"\n',
            b"\xff\n",
            b'{"type":"event_msg"}',
            b"[]\n",
        ):
            with self.subTest(tail=tail):
                self.rollout.write_bytes(clean + tail)
                self.unavailable()

    def test_symlink_hardlink_nonregular_and_duplicate_matches_are_rejected(self):
        self.available()
        original = self.root / "original.jsonl"
        self.rollout.rename(original)
        self.rollout.symlink_to(original)
        self.unavailable()
        self.rollout.unlink()
        os.link(original, self.rollout)
        self.unavailable()
        self.rollout.unlink()
        original.rename(self.rollout)
        duplicate = self.sessions / f"rollout-second-{THREAD}.jsonl"
        duplicate.write_bytes(self.rollout.read_bytes())
        self.unavailable()
        duplicate.unlink()
        self.rollout.unlink()
        os.mkfifo(self.rollout)
        self.unavailable()

    def test_symlinked_sessions_root_is_rejected(self):
        self.available()
        alias = self.root / "alias"
        alias.symlink_to(self.sessions, target_is_directory=True)
        self.sessions = alias
        self.unavailable()

    def test_size_line_and_record_count_bounds_fail_closed(self):
        self.available()
        with self.rollout.open("ab") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        self.unavailable()
        self.write(self.safe)
        with self.rollout.open("ab") as stream:
            stream.write(b" " * (1024 * 1024 + 1) + b"\n")
        self.unavailable()
        self.write(self.safe)
        with self.rollout.open("ab") as stream:
            stream.write(b"{}\n" * 100001)
        self.unavailable()

    def test_wrong_rollout_owner_is_rejected_at_owner_guard(self):
        helper = importlib.import_module("advisor_parent")
        self.assertEqual(
            helper.inspect_parent(self.sessions, THREAD)["status"], "available"
        )
        real = helper.os.fstat

        def wrong_owner(fd):
            value = real(fd)
            if helper.stat.S_ISREG(value.st_mode):
                return SimpleNamespace(
                    **{
                        name: getattr(value, name)
                        for name in (
                            "st_mode",
                            "st_nlink",
                            "st_dev",
                            "st_ino",
                            "st_size",
                            "st_mtime_ns",
                            "st_ctime_ns",
                        )
                    },
                    st_uid=os.getuid() + 1,
                )
            return value

        with patch.object(helper.os, "fstat", side_effect=wrong_owner):
            with self.assertRaisesRegex(helper.ParentUnavailable, "rollout_owner"):
                helper.inspect_parent(self.sessions, THREAD)

    def test_append_or_replacement_during_read_is_rejected(self):
        helper = importlib.import_module("advisor_parent")
        real = helper.os.fdopen
        for action in ("append", "replace"):
            self.write(self.safe)
            replacement = self.root / "replacement.jsonl"
            replacement.write_bytes(self.rollout.read_bytes())

            def intercepted(fd, *args, **kwargs):
                stream = real(fd, *args, **kwargs)

                class ChangingReader:
                    changed = False

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return stream.__exit__(*args)

                    def readline(self, *args):
                        value = stream.readline(*args)
                        if value and not self.changed:
                            self.changed = True
                            if action == "append":
                                with self_outer.rollout.open("ab") as out:
                                    out.write(b"{}\n")
                            else:
                                os.replace(replacement, self_outer.rollout)
                        return value

                return ChangingReader()

            self_outer = self
            with (
                self.subTest(action=action),
                patch.object(helper.os, "fdopen", side_effect=intercepted),
            ):
                with self.assertRaisesRegex(helper.ParentUnavailable, "changed"):
                    helper.inspect_parent(self.sessions, THREAD)

    def test_admission_preserves_production_three_second_budget(self):
        import advisor_admission

        with patch.dict(os.environ, {"CODEX_THREAD_ID": THREAD}):
            evidence = advisor_admission.parent_evidence(THREAD, str(self.sessions))
        self.assertEqual(evidence["thread_id"], THREAD)
        self.assertEqual(evidence["sandbox_policy_type"], "workspace-write")

    def test_unreadable_subtree_never_proves_rollout_uniqueness(self):
        self.available()
        blocked = self.sessions / "unreadable"
        blocked.mkdir()
        (blocked / f"rollout-hidden-{THREAD}.jsonl").write_bytes(
            self.rollout.read_bytes()
        )
        blocked.chmod(0)
        try:
            self.unavailable()
        finally:
            blocked.chmod(0o700)

    def test_directory_entry_classification_io_error_fails_closed(self):
        helper = importlib.import_module("advisor_parent")
        self.available()
        real = helper.os.scandir

        class FailingEntry:
            name = "unreadable-entry"

            def is_dir(self, **_kwargs):
                raise OSError("generated entry classification failure")

            def stat(self, **_kwargs):
                raise OSError("generated entry classification failure")

            def is_symlink(self):
                return False

        class Directory:
            def __init__(self, fd):
                self.iterator = real(fd)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.iterator.close()

            def __iter__(self):
                yield from self.iterator
                yield FailingEntry()

        with patch.object(helper.os, "scandir", side_effect=Directory):
            with self.assertRaises(OSError):
                helper.inspect_parent(self.sessions, THREAD)


if __name__ == "__main__":
    unittest.main()
