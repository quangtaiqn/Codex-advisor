"""Production launcher replay/race/recovery proof; fake provider, no inference."""

from __future__ import annotations
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from advisor_transport_support import AdvisorTransportTestCase, PACKET, PARENT, ROOT


def competing_launch(barrier, queue, command, env, packet):
    barrier.wait(timeout=10)
    result = subprocess.run(
        command, env=env, input=packet, capture_output=True, text=True, timeout=40
    )
    queue.put((result.returncode, result.stdout, result.stderr))


class AdvisorLedgerTests(AdvisorTransportTestCase):
    def command(self, *args):
        return [
            "sh",
            str(self.transport),
            "--issue-id",
            "durable-issue",
            *args,
            "--parent-thread",
            self.env["CODEX_THREAD_ID"],
            "--sessions-dir",
            str(self.home / "sessions"),
        ]

    def launch(self, *args, packet=PACKET, case="adjacent", env=None):
        return subprocess.run(
            self.command(*args),
            env={**self.env, "FAKE_CASE": case, **(env or {})},
            input=packet,
            text=True,
            capture_output=True,
            timeout=35,
        )

    def ledger(self, action, *args, issue="durable-issue"):
        return subprocess.run(
            [
                sys.executable,
                str(self.plugin_root / "scripts/advisor_ledger.py"),
                "--ledger-dir",
                str(self.root / "ledger"),
                "--project-root",
                str(ROOT.parents[1]),
                "--issue-id",
                issue,
                action,
                *args,
            ],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=12,
        )

    def issue_state(self):
        result = self.ledger("status")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return next(iter(json.loads(result.stdout)["registry"]["issues"].values()))

    def save_receipt(self, result, name="receipt.json"):
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.root / name
        path.write_text(result.stdout)
        path.chmod(0o600)
        return path

    def test_same_issue_alias_session_clone_and_canonical_id_replay(self):
        previous = self.save_receipt(self.launch("--tier", "standard"))
        for args, packet in [
            (("--tier", "specialist"), PACKET),
            (
                ("--issue-id", "renamed-issue"),
                PACKET.replace("evidence", "  evidence  "),
            ),
        ]:
            replay = self.launch(*args, packet=packet)
            self.assertNotEqual(replay.returncode, 0, replay.stderr)
            self.assertIn("consumed", replay.stderr)
            self.assertEqual(len(self.rows()), 1)
            self.assertEqual(json.loads(replay.stdout)["attempts"], [])
        clone = self.root / "cloned.json"
        clone.write_bytes(previous.read_bytes())
        clone.chmod(0o600)
        medium = self.launch(
            "--level",
            "medium",
            "--previous-result",
            str(clone),
            "--authorize-escalation",
        )
        self.assertEqual(medium.returncode, 0, medium.stderr)
        replay = self.launch(
            "--level",
            "medium",
            "--previous-result",
            str(previous),
            "--authorize-escalation",
        )
        self.assertNotEqual(replay.returncode, 0)
        self.assertEqual(len(self.rows()), 2)
        new_parent = "12121212-1212-7212-8212-121212121212"
        source = self.home / f"sessions/fixture/rollout-fake-{PARENT}.jsonl"
        (source.parent / f"rollout-fake-{new_parent}.jsonl").write_text(
            source.read_text().replace(PARENT, new_parent)
        )
        self.env["CODEX_THREAD_ID"] = new_parent
        changed = self.launch("--role", "advisor-sol")
        self.assertNotEqual(changed.returncode, 0)
        self.assertEqual(len(self.rows()), 2)

    def test_windows_project_case_alias_cannot_grant_another_low(self):
        common = Path(
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(ROOT.parents[1]),
                    "rev-parse",
                    "--path-format=absolute",
                    "--git-common-dir",
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        original = str(common.parent)
        alternate = original.lower()
        if (
            not original.startswith("/mnt/")
            or original == alternate
            or not Path(alternate).is_dir()
        ):
            self.skipTest(
                "requires the actual Windows drive case alias; ordinary Linux paths preserve case"
            )
        first = self.launch(env={"ADVISOR_PROJECT_ROOT": original})
        self.assertEqual(first.returncode, 0, first.stderr)
        replay = self.launch(env={"ADVISOR_PROJECT_ROOT": alternate})
        self.assertNotEqual(replay.returncode, 0, replay.stderr)
        self.assertIn("consumed", replay.stderr)
        self.assertEqual(len(self.rows()), 1)

    def test_two_process_same_issue_barrier_reserves_exactly_one_child(self):
        context = multiprocessing.get_context("fork")
        barrier = context.Barrier(2)
        queue = context.Queue()
        env = {**self.env, "FAKE_CASE": "adjacent"}
        workers = [
            context.Process(
                target=competing_launch,
                args=(barrier, queue, self.command(), env, PACKET),
            )
            for _ in range(2)
        ]
        for worker in workers:
            worker.start()
        try:
            results = [queue.get(timeout=45) for _ in workers]
            self.assertEqual(sorted(code for code, _, _ in results), [0, 1], results)
            self.assertEqual(len(self.rows()), 1)
            self.assertIn("consumed", next(err for code, _, err in results if code))
            self.assertEqual(len(self.issue_state()["executions"]), 1)
        finally:
            for worker in workers:
                worker.join(timeout=3)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=3)
            queue.close()

    def test_two_process_same_receipt_barrier_consumes_one_next_level(self):
        previous = self.save_receipt(self.launch())
        context = multiprocessing.get_context("fork")
        barrier = context.Barrier(2)
        queue = context.Queue()
        command = self.command(
            "--level",
            "medium",
            "--previous-result",
            str(previous),
            "--authorize-escalation",
        )
        workers = [
            context.Process(
                target=competing_launch,
                args=(
                    barrier,
                    queue,
                    command,
                    {**self.env, "FAKE_CASE": "adjacent"},
                    PACKET,
                ),
            )
            for _ in range(2)
        ]
        for worker in workers:
            worker.start()
        try:
            results = [queue.get(timeout=45) for _ in workers]
            self.assertEqual(sorted(code for code, _, _ in results), [0, 1], results)
            accepted = json.loads(next(out for code, out, _ in results if code == 0))
            self.assertEqual(accepted["selection"]["level"], "medium")
            self.assertEqual(accepted["outcome"], "accepted")
            self.assertIn("consumed", next(err for code, _, err in results if code))
            self.assertEqual(len(self.rows()), 2)
            records = self.issue_state()["executions"]
            self.assertEqual(set(records), {"low", "medium"})
            self.assertTrue(records["low"]["consumed"])
            self.assertEqual(records["medium"]["state"], "accepted")
            self.assertFalse(records["medium"]["consumed"])
        finally:
            for worker in workers:
                worker.join(timeout=3)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=3)
            queue.close()

    def test_independent_issue_and_material_revision_do_not_share_quota(self):
        self.save_receipt(self.launch(case="valid"))
        second = self.launch(
            "--issue-id",
            "independent",
            packet=PACKET.replace("question", "different real question"),
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        revision = self.launch(
            "--issue-id",
            "revision",
            "--supersedes",
            "durable-issue",
            "--revision-reason",
            "new evidence changes the boundary",
            "--evidence-digest",
            "a" * 64,
            packet=PACKET.replace("evidence", "new independently observed evidence"),
        )
        self.assertEqual(revision.returncode, 0, revision.stderr)
        invalid = self.launch(
            "--issue-id",
            "invalid-revision",
            "--supersedes",
            "durable-issue",
            packet=PACKET.replace("evidence", "other evidence"),
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("material revision", invalid.stderr)
        self.assertEqual(len(self.rows()), 3)

    def test_preflight_error_does_not_reserve_and_after_reserve_failure_never_retries(
        self,
    ):
        missing = self.launch(env={"ADVISOR_CODEX_BIN": str(self.root / "absent")})
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(json.loads(missing.stdout)["attempts"], [])
        state = json.loads(self.ledger("status").stdout)["registry"]
        self.assertEqual(state["issues"], {})
        failed = self.launch(case="wrong-effort")
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(self.issue_state()["executions"]["low"]["state"], "failed")
        again = self.launch()
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_unsafe_corrupt_or_missing_storage_rejects_before_spawn(self):
        root = self.root / "ledger"
        original = (root / "registry.json").read_bytes()
        for fault in ("mode", "symlink", "hardlink", "corrupt", "missing"):
            with self.subTest(fault=fault):
                file = root / "registry.json"
                if fault == "mode":
                    file.chmod(0o644)
                elif fault == "symlink":
                    file.rename(root / "preserved")
                    file.symlink_to(root / "preserved")
                elif fault == "hardlink":
                    os.link(file, root / "extra-link")
                elif fault == "corrupt":
                    file.write_text('{"truncated":')
                else:
                    file.rename(root / "missing-original")
                result = self.launch()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.rows(), [])
                self.assertEqual(json.loads(result.stdout)["attempts"], [])
                if fault == "symlink":
                    file.unlink()
                    (root / "preserved").rename(file)
                elif fault == "hardlink":
                    (root / "extra-link").unlink()
                elif fault == "missing":
                    (root / "missing-original").rename(file)
                else:
                    file.chmod(0o600)
                    file.write_bytes(original)
        # Test-only repair above restores private fixture bytes, never a user namespace.
        root.chmod(0o755)
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.rows(), [])
        root.chmod(0o700)

    def pause_launcher(self, phase):
        marker = self.root / "paused"
        real = sys.executable
        wrapper = self.bin / ("cat" if phase == "output" else "python3")
        pattern = '*advisor_ledger.py*" ' + phase + ' "*'
        if phase == "spawn":
            pattern = '*advisor_process.py*" -- "*'
        if phase == "output":
            pattern = "*/sealed.json"
        if phase == "output":
            real = "/usr/bin/cat"
        wrapper.write_text(f"""#!/bin/sh
case "$*" in
  {pattern})
    printf '%s\\n' "$*" >'{marker}'
    while :; do sleep 1; done ;;
esac
exec '{real}' "$@"
""")
        wrapper.chmod(0o700)
        process = subprocess.Popen(
            self.command(),
            env={**self.env, "FAKE_CASE": "adjacent"},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        process.stdin.write(PACKET)
        process.stdin.close()
        process.stdin = None
        deadline = time.monotonic() + 12
        while not marker.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.02)
        if not marker.exists():
            os.killpg(process.pid, signal.SIGKILL)
            out, err = process.communicate(timeout=5)
            self.fail("did not reach deterministic crash barrier: " + out + err)
        return process, wrapper, marker

    def test_crash_after_started_before_spawn_stays_consumed(self):
        process, wrapper, _ = self.pause_launcher("spawn")
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        wrapper.unlink()
        self.assertEqual(self.issue_state()["executions"]["low"]["state"], "started")
        self.assertEqual(self.rows(), [])
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertEqual(self.rows(), [])

    def test_crash_after_commit_before_stdout_preserves_consumed_acceptance(self):
        process, wrapper, _ = self.pause_launcher("output")
        self.assertEqual(self.issue_state()["executions"]["low"]["state"], "accepted")
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        wrapper.unlink()
        self.assertEqual(len(self.rows()), 1)
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_crash_after_reserve_before_started_is_consumed_unknown(self):
        process, wrapper, _ = self.pause_launcher("start")
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        wrapper.unlink()
        record = self.issue_state()["executions"]["low"]
        self.assertEqual(record["state"], "reserved")
        again = self.launch()
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(self.rows(), [])
        reconciled = self.ledger("reconcile", "--execution", record["id"])
        self.assertEqual(reconciled.returncode, 0, reconciled.stdout)
        self.assertEqual(self.issue_state()["executions"]["low"]["state"], "unknown")
        self.assertNotEqual(self.launch().returncode, 0)

    def test_crash_after_runtime_acceptance_reconciles_same_execution_without_spawn(
        self,
    ):
        process, wrapper, marker = self.pause_launcher("accept")
        argv = marker.read_text().split()
        receipt = self.root / "recovery.json"
        receipt.write_bytes(Path(argv[argv.index("--receipt") + 1]).read_bytes())
        receipt.chmod(0o600)
        record = self.issue_state()["executions"]["low"]
        self.assertEqual(record["state"], "started")
        active = self.ledger("reconcile", "--execution", record["id"])
        self.assertNotEqual(active.returncode, 0)
        self.assertIn("active owned", active.stdout)
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        wrapper.unlink()
        packet = self.root / "packet.txt"
        packet.write_text(PACKET)
        packet.chmod(0o600)
        recovered = self.ledger(
            "reconcile",
            "--execution",
            record["id"],
            "--receipt",
            str(receipt),
            "--packet",
            str(packet),
            "--sessions-dir",
            str(self.home / "sessions"),
        )
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertEqual(self.issue_state()["executions"]["low"]["state"], "accepted")
        self.assertEqual(len(self.rows()), 1)
        self.assertNotEqual(self.launch().returncode, 0)

    def test_transfer_requires_runtime_proof_and_preserves_previous_parent_guard(self):
        receipt = self.save_receipt(self.launch())
        packet = self.root / "packet.txt"
        packet.write_text(PACKET)
        packet.chmod(0o600)
        parent = "12121212-1212-7212-8212-121212121212"
        source = self.home / f"sessions/fixture/rollout-fake-{PARENT}.jsonl"
        (source.parent / f"rollout-fake-{parent}.jsonl").write_text(
            source.read_text().replace(PARENT, parent)
        )
        self.env["CODEX_THREAD_ID"] = parent
        blocked = self.launch(
            "--level",
            "medium",
            "--previous-result",
            str(receipt),
            "--authorize-escalation",
        )
        self.assertNotEqual(blocked.returncode, 0)
        moved = self.ledger(
            "transfer",
            "--receipt",
            str(receipt),
            "--packet",
            str(packet),
            "--parent",
            parent,
            "--sessions-dir",
            str(self.home / "sessions"),
        )
        self.assertEqual(moved.returncode, 0, moved.stdout + moved.stderr)
        next_result = self.launch(
            "--level",
            "medium",
            "--previous-result",
            str(receipt),
            "--authorize-escalation",
        )
        self.assertEqual(next_result.returncode, 0, next_result.stderr)
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.issue_state()["parent"], parent)

    def test_accept_fsync_failure_never_publishes_accepted_or_restores_quota(self):
        wrapper = self.bin / "python3"
        injection = (
            "import os,runpy,sys; "
            "exec(\"def fail_sync(fd):\\n raise OSError(28, 'fixture durable accept unavailable')\"); "
            "os.fsync=fail_sync; sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')"
        )
        import shlex

        wrapper.write_text(
            '#!/bin/sh\ncase "$*" in\n'
            ' *advisor_ledger.py*" accept "*) exec '
            + shlex.quote(sys.executable)
            + " -c "
            + shlex.quote(injection)
            + ' "$@" ;;\n'
            "esac\nexec " + shlex.quote(sys.executable) + ' "$@"\n'
        )
        wrapper.chmod(0o700)
        failed = self.launch()
        self.assertNotEqual(failed.returncode, 0, failed.stderr)
        self.assertIn("accepted persistence unavailable", failed.stderr)
        envelope = json.loads(failed.stdout)
        self.assertEqual(envelope["status"], "unavailable")
        self.assertIsNone(envelope["runtime"])
        self.assertIsNone(envelope["response"])
        self.assertEqual(len(envelope["attempts"]), 1)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.issue_state()["executions"]["low"]["state"], "failed")
        wrapper.unlink()
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_retention_and_legacy_receipt_do_not_reopen_budget(self):
        receipt = self.save_receipt(self.launch(case="valid"))
        self.assertEqual(self.ledger("prune").returncode, 0)
        self.assertNotEqual(self.launch().returncode, 0)
        payload = json.loads(receipt.read_text())
        payload["schema_version"] = 3
        payload["selection"]["transport_contract_version"] = "1.5"
        payload.pop("ledger")
        payload.pop("acceptance_proof")
        receipt.write_text(json.dumps(payload))
        sealed = subprocess.run(
            [
                sys.executable,
                str(self.plugin_root / "scripts/advisor_acceptance.py"),
                "--seal",
                str(receipt),
            ],
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(sealed.returncode, 0, sealed.stderr)
        receipt.write_text(sealed.stdout)
        old = self.launch(
            "--level",
            "medium",
            "--previous-result",
            str(receipt),
            "--authorize-escalation",
        )
        self.assertNotEqual(old.returncode, 0)
        self.assertEqual(len(self.rows()), 1)
        # Import into a separately provisioned private migration fixture.
        migration = self.root / "migration-ledger"
        initialized = subprocess.run(
            [
                sys.executable,
                str(self.plugin_root / "scripts/advisor_ledger.py"),
                "--ledger-dir",
                str(migration),
                "init",
            ],
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(initialized.returncode, 0, initialized.stdout)
        self.env["ADVISOR_LEDGER_DIR"] = str(migration)
        packet = self.root / "packet.txt"
        packet.write_text(PACKET)
        packet.chmod(0o600)
        imported = subprocess.run(
            [
                sys.executable,
                str(self.plugin_root / "scripts/advisor_ledger.py"),
                "--ledger-dir",
                str(migration),
                "--issue-id",
                "durable-issue",
                "import-a",
                "--receipt",
                str(receipt),
                "--packet",
                str(packet),
                "--sessions-dir",
                str(self.home / "sessions"),
            ],
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertEqual(len(self.rows()), 1)
