"""Bounded parent-inspector proof using generated sessions, never inference."""

from __future__ import annotations

import base64
import importlib
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from collections import Counter
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

    def test_slow_metadata_full_namespace_stays_inside_parent_budget(self):
        helper = importlib.import_module("advisor_parent")
        names = {f"noise-{index:03d}.txt" for index in range(80)}
        for name in sorted(names):
            (self.sessions / name).write_bytes(b"generated\n")
        real_scandir = helper.os.scandir
        calls = Counter()
        lock = threading.Lock()

        class SlowEntry:
            def __init__(self, entry):
                self.entry = entry

            def __getattr__(self, name):
                return getattr(self.entry, name)

            def stat(self, **kwargs):
                time.sleep(0.02)
                result = self.entry.stat(**kwargs)
                with lock:
                    calls[self.entry.name] += 1
                return result

        class Directory:
            def __init__(self, fd):
                self.iterator = real_scandir(fd)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.iterator.close()

            def __iter__(self):
                for entry in self.iterator:
                    yield SlowEntry(entry) if entry.name in names else entry

        with patch.object(helper.os, "scandir", side_effect=Directory):
            started = time.monotonic()
            result = helper.inspect_parent(self.sessions, THREAD)
            elapsed = time.monotonic() - started
        self.assertEqual(
            result,
            {"status": "available", "thread_id": THREAD,
             "sandbox_policy_type": "workspace-write",
             "permission_profile_type": "managed"},
        )
        self.assertEqual(set(calls), names)
        self.assertTrue(all(count >= 2 for count in calls.values()))
        self.assertLess(elapsed, 2.5)

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


@unittest.skipUnless(os.environ.get("TEST_WINDOWS_PARENT_ROOT"), "Windows NTFS fixture not configured")
class WindowsNativeParentInspectorTests(unittest.TestCase):
    """Exercise the public parser on a private, Windows-owned NTFS fixture."""

    def setUp(self):
        base = Path(os.environ["TEST_WINDOWS_PARENT_ROOT"])
        self.assertTrue(base.is_dir(), f"Missing TEST_WINDOWS_PARENT_ROOT: {base}")
        self.temporary = tempfile.TemporaryDirectory(prefix="parent-native-", dir=base)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sessions = self.root / "sessions"
        self.alias_dir = self.root / "alias"
        self.sessions.mkdir()
        self.alias_dir.mkdir()
        self.name = f"rollout-generated-{THREAD}.jsonl"
        self.rollout = self.sessions / self.name
        self.alias = self.alias_dir / self.name
        self.safe = [
            {"type": "session_meta", "payload": {"id": THREAD}},
            {"type": "turn_context", "payload": {
                "sandbox_policy": {"type": "workspace-write"},
                "permission_profile": {"type": "managed"},
            }},
        ]
        self.write(self.safe)
        os.link(self.rollout, self.alias)
        self.windows_acl(self.root, self.sessions, self.alias_dir, self.rollout)
        self.assertEqual(self.rollout.stat().st_nlink, 2, "Fixture needs two real NTFS links")
        self.assertEqual(self.rollout.stat().st_uid, os.getuid())

    def write(self, rows):
        self.rollout.write_bytes(b"".join(json.dumps(row).encode("utf-8") + b"\n" for row in rows))

    def windows_acl(self, *paths, everyone_write=False):
        windows_paths = []
        for path in paths:
            converted = subprocess.run(
                ["wslpath", "-w", str(path)], capture_output=True, text=True,
                check=True, timeout=10,
            )
            windows_paths.append("'" + converted.stdout.strip().replace("'", "''") + "'")
        mode = "$true" if everyone_write else "$false"
        script = f"""
$env:PSModulePath = [IO.Path]::Combine($PSHOME, 'Modules')
$ErrorActionPreference = 'Stop'
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$admins = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
foreach ($p in @({','.join(windows_paths)})) {{
    if ({mode}) {{
        & "$env:WINDIR\\System32\\icacls.exe" $p /grant '*S-1-1-0:(W)' /Q | Out-Null
        if ($LASTEXITCODE -ne 0) {{ throw 'Fixture DACL update failed' }}
        continue
    }} else {{
        $acl = Get-Acl -LiteralPath $p
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($old in @($acl.Access)) {{ $acl.RemoveAccessRuleAll($old) }}
        $acl.SetOwner($current)
        $inherit = if ([System.IO.Directory]::Exists($p)) {{
            [System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
        }} else {{ [System.Security.AccessControl.InheritanceFlags]::None }}
        foreach ($sid in @($current, $system, $admins)) {{
            $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
                $sid, [System.Security.AccessControl.FileSystemRights]::FullControl,
                $inherit, [System.Security.AccessControl.PropagationFlags]::None,
                [System.Security.AccessControl.AccessControlType]::Allow)
            $acl.AddAccessRule($rule)
        }}
    }}
    Set-Acl -LiteralPath $p -AclObject $acl
}}
"""
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        completed = subprocess.run(
            ["/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
             "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def available(self):
        helper = importlib.import_module("advisor_parent")
        self.assertEqual(helper.inspect_parent(self.sessions, THREAD), {
            "status": "available", "thread_id": THREAD,
            "sandbox_policy_type": "workspace-write",
            "permission_profile_type": "managed",
        })

    def unavailable(self):
        helper = importlib.import_module("advisor_parent")
        # The CLI also redacts JSON/encoding/OS errors from the strict parser.
        with self.assertRaises((ValueError, OSError)):
            helper.inspect_parent(self.sessions, THREAD)

    def test_safe_same_basename_two_link_mirror_is_available(self):
        started = time.monotonic()
        self.available()
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 2.5)
        print(json.dumps({"native_fixture_bytes": self.rollout.stat().st_size,
                          "reader_seconds": elapsed, "budget_seconds": 2.5}))
        import advisor_admission
        with patch.dict(os.environ, {"CODEX_THREAD_ID": THREAD}):
            evidence = advisor_admission.parent_evidence(THREAD, str(self.sessions))
        self.assertEqual(evidence["thread_id"], THREAD)

    def test_native_proof_large_history_and_namespace_fit_reader_budget(self):
        # The small native fixture cannot expose serialized startup plus two
        # metadata scans and a full history parse competing for the same bound.
        payload = {"type": "event_msg", "payload": {"text": "x" * 250000}}
        self.write([*self.safe, *([payload] * 100)])
        for number in range(32):
            directory = self.sessions / f"unrelated-{number}"
            directory.mkdir()
            for item in range(64):
                (directory / f"unrelated-{item}.jsonl").write_bytes(b"{}\n")
        started = time.monotonic()
        self.available()
        self.assertLess(time.monotonic() - started, 2.5)

    def test_third_link_and_other_basename_are_rejected(self):
        self.available()
        third_dir = self.root / "third"
        third_dir.mkdir()
        self.windows_acl(third_dir)
        third = third_dir / self.name
        os.link(self.rollout, third)
        self.assertEqual(self.rollout.stat().st_nlink, 3)
        self.unavailable()
        third.unlink()
        self.available()
        wrong_name = self.alias.with_name("other-" + self.name)
        self.alias.rename(wrong_name)
        self.assertEqual(self.rollout.stat().st_nlink, 2)
        self.unavailable()

    def test_everyone_write_acl_is_rejected_without_wsl_owner_change(self):
        self.available()
        uid = self.rollout.stat().st_uid
        self.windows_acl(self.rollout, everyone_write=True)
        self.assertEqual(self.rollout.stat().st_uid, uid)
        self.unavailable()

    def test_malformed_and_mixed_provenance_are_rejected(self):
        self.available()
        for change in ("malformed", "mixed"):
            with self.subTest(change=change):
                self.write(self.safe)
                if change == "malformed":
                    with self.rollout.open("ab") as stream:
                        stream.write(b'{"type":"event_msg"\n')
                else:
                    self.write([*self.safe, {"type": "turn_context", "payload": {
                        "sandbox_policy": {"type": "read-only"},
                        "permission_profile": {"type": "managed"},
                    }}])
                self.assertEqual(self.rollout.stat().st_nlink, 2)
                self.unavailable()

    def test_native_path_replacement_during_read_is_rejected(self):
        self.available()
        helper = importlib.import_module("advisor_parent")
        replacement = self.root / "replacement.jsonl"
        replacement.write_bytes(self.rollout.read_bytes())
        self.windows_acl(replacement)
        real_read = helper.read_records
        changed = []

        def replace_after_read(*args, **kwargs):
            result = real_read(*args, **kwargs)
            os.replace(replacement, self.rollout)
            changed.append(True)
            return result

        with patch.object(helper, "read_records", side_effect=replace_after_read):
            self.unavailable()
        self.assertEqual(changed, [True], "Mutation must occur inside inspect_parent")

    def test_link_or_alias_change_during_read_is_rejected(self):
        # Extend the public owner boundary: static bad-link inputs do not prove
        # that the native handle and the POSIX fd stay bound during parsing.
        self.available()
        helper = importlib.import_module("advisor_parent")
        real_read = helper.read_records
        for action in ("third-link", "rename-alias"):
            changed = []
            target = self.alias_dir / ("other-" + self.name)

            def mutate(*args, **kwargs):
                result = real_read(*args, **kwargs)
                if action == "third-link":
                    os.link(self.rollout, target)
                else:
                    self.alias.rename(target)
                changed.append(True)
                return result

            try:
                with self.subTest(action=action), patch.object(helper, "read_records", side_effect=mutate):
                    with self.assertRaisesRegex(helper.ParentUnavailable, "changed|native_proof"):
                        helper.inspect_parent(self.sessions, THREAD)
                self.assertEqual(changed, [True])
            finally:
                if action == "third-link":
                    target.unlink(missing_ok=True)
                elif target.exists():
                    target.rename(self.alias)


if __name__ == "__main__":
    unittest.main()
