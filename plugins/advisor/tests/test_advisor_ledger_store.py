"""OS durability/corruption failures at the storage API's real boundary."""

import errno
import fcntl
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from advisor_transport_support import config
from advisor_ledger_store import Store, MAX_ISSUES
from advisor_ledger import canonical_packet, project_identity


class LedgerStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "ledger"
        self.store = Store(self.root)
        self.store.initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def test_tmpfs_namespace_is_rejected_without_epoch_or_registry(self):
        if not Path("/dev/shm").is_dir():
            self.skipTest("requires a Linux tmpfs mount")
        with tempfile.TemporaryDirectory(dir="/dev/shm") as temporary:
            root = Path(temporary) / "ledger"
            with self.assertRaises(config.ConfigError):
                Store(root).initialize()
            self.assertFalse((root / "epoch.json").exists())
            self.assertFalse((root / "registry.json").exists())

    def test_explicit_init_never_repairs_partial_or_missing_state(self):
        (self.root / "registry.json").unlink()
        with self.assertRaises((OSError, config.ConfigError)):
            with self.store.transaction():
                pass
        marker = (self.root / "epoch.json").read_bytes()
        with self.assertRaises(config.ConfigError):
            self.store.initialize()
        self.assertEqual((self.root / "epoch.json").read_bytes(), marker)
        self.assertFalse((self.root / "registry.json").exists())

    def test_canonical_packet_normalizes_text_but_preserves_order_and_evidence(self):
        first = Path(self.tmp.name) / "first.txt"
        second = first.with_name("renamed.txt")
        first.write_bytes("DECISION\nCafé  evidence\nREQUEST\nchallenge\n".encode())
        first.chmod(0o600)
        second.write_bytes(
            "DECISION\r\n  Cafe\u0301\t evidence \r\n\r\nREQUEST\r\nchallenge\r\n".encode()
        )
        second.chmod(0o600)
        self.assertEqual(canonical_packet(first), canonical_packet(second))
        second.write_text("REQUEST\nchallenge\nDECISION\nCafé evidence\n")
        self.assertNotEqual(canonical_packet(first), canonical_packet(second))
        second.write_text("DECISION\nCafé evidence changed\nREQUEST\nchallenge\n")
        self.assertNotEqual(canonical_packet(first), canonical_packet(second))
        first.write_text(
            "DECISION\nobserved 2026-10-12T12:00:00Z evidence\nREQUEST\nchallenge\n"
        )
        second.write_text(
            "DECISION\nobserved 2026-10-13T13:00:00Z evidence\nREQUEST\nchallenge\n"
        )
        self.assertEqual(canonical_packet(first), canonical_packet(second))

    def test_project_identity_is_stable_across_real_git_worktrees(self):
        import subprocess

        root = Path(self.tmp.name) / "project"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=fixture",
                "-c",
                "user.email=fixture@invalid",
                "commit",
                "--allow-empty",
                "-qm",
                "fixture",
            ],
            check=True,
        )
        other = root.with_name("linked")
        subprocess.run(
            ["git", "-C", str(root), "worktree", "add", "--detach", "-q", str(other)],
            check=True,
        )
        self.assertEqual(project_identity(root), project_identity(other))

    def test_disk_write_and_fsync_errors_do_not_report_committed_success(self):
        original = (self.root / "registry.json").read_bytes()
        for operation in ("write", "fsync"):
            with (
                self.subTest(operation=operation),
                patch(
                    "advisor_ledger_store.os." + operation,
                    side_effect=OSError(errno.ENOSPC, "fixture disk full"),
                ),
            ):
                with self.assertRaises(OSError):
                    with self.store.transaction(mutate=True) as body:
                        body["revision"] += 1
            self.assertEqual((self.root / "registry.json").read_bytes(), original)
        calls = 0
        original_fsync = os.fsync

        def fail_directory(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError(errno.EIO, "fixture directory durability failure")
            return original_fsync(fd)

        with patch("advisor_ledger_store.os.fsync", side_effect=fail_directory):
            with self.assertRaises(OSError):
                with self.store.transaction(mutate=True) as body:
                    body["revision"] += 1
        # Atomic replace may already have committed; no success was returned.
        with self.store.transaction() as body:
            self.assertGreater(body["revision"], 0)

    def test_version_integrity_and_read_only_mutation_fail_closed(self):
        with self.assertRaises(config.ConfigError):
            with self.store.transaction() as body:
                body["revision"] += 1
        with self.store.locked() as (directory, _):
            body = self.store.read(directory, "registry.json")
            body["version"] = 99
            self.store.write(directory, "registry.json", body)
        before = (self.root / "registry.json").read_bytes()
        with self.assertRaises(config.ConfigError):
            with self.store.transaction():
                pass
        self.assertEqual((self.root / "registry.json").read_bytes(), before)

    def test_lock_contention_is_bounded_and_cannot_replace_lock_inode(self):
        fd = os.open(self.root / "lock", os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            with patch("advisor_ledger_store.time.monotonic", side_effect=[0, 10]):
                with self.assertRaisesRegex(config.ConfigError, "lock contention"):
                    with self.store.transaction():
                        pass
        finally:
            os.close(fd)
        os.link(self.root / "lock", self.root / "lock-alias")
        with self.assertRaises(config.ConfigError):
            with self.store.transaction():
                pass

    def test_valid_checksum_nonobject_state_is_typed_fail_closed(self):
        with self.store.locked() as (directory, _):
            self.store.write(directory, "registry.json", ["corrupt-schema"])
        with self.assertRaises(config.ConfigError):
            with self.store.transaction():
                pass

    def test_legacy_init_failure_preserves_every_original_entry(self):
        root = Path(self.tmp.name) / "legacy"
        root.mkdir(mode=0o700)
        original = root / "legacy.json"
        original.write_text('{"version":0}')
        original.chmod(0o600)
        with self.assertRaises(config.ConfigError):
            Store(root).initialize()
        self.assertEqual(set(p.name for p in root.iterdir()), {"legacy.json"})
        self.assertEqual(original.read_text(), '{"version":0}')

    def test_wrong_file_uid_fails_at_owner_guard(self):
        import stat
        from types import SimpleNamespace

        original_fstat = os.fstat

        def wrong_owner(fd):
            info = original_fstat(fd)
            if stat.S_ISREG(info.st_mode):
                return SimpleNamespace(
                    st_mode=info.st_mode,
                    st_uid=info.st_uid + 1,
                    st_nlink=info.st_nlink,
                    st_dev=info.st_dev,
                    st_ino=info.st_ino,
                )
            return info

        with patch("advisor_ledger_store.os.fstat", side_effect=wrong_owner):
            with self.assertRaisesRegex(config.ConfigError, "ledger file owner"):
                with self.store.transaction():
                    pass

    def test_registry_bound_does_not_drop_tombstones(self):
        # A valid over-limit registry must be rejected, never auto-pruned/reset.
        with self.store.locked() as (directory, _):
            body = self.store.read(directory, "registry.json")
            body["issues"] = {str(i): {} for i in range(MAX_ISSUES + 1)}
            self.store.write(directory, "registry.json", body)
        before = (self.root / "registry.json").read_bytes()
        with self.assertRaises(config.ConfigError):
            with self.store.transaction():
                pass
        self.assertEqual((self.root / "registry.json").read_bytes(), before)
