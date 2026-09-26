"""Black-box coverage for configurable Advisor discovery and consultation transport."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shlex
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CONFIG_WRAPPER = ROOT / "scripts" / "advisor-config.sh"
TRANSPORT = ROOT / "scripts" / "run-advisor.sh"
PROCESS = ROOT / "scripts" / "advisor_process.py"
CONFIG_MODULE = ROOT / "scripts" / "advisor_config.py"
ADAPTER_MODULE = ROOT / "scripts" / "advisor_transport.py"
SPEC = importlib.util.spec_from_file_location("transport_advisor_config", CONFIG_MODULE)
assert SPEC and SPEC.loader
config = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = config
SPEC.loader.exec_module(config)

PARENT = "56565656-5656-7565-8565-565656565656"
PACKET = """DECISION
question
CONTEXT
evidence
OPTIONS
choice
BOUNDARIES
limits
REQUEST
challenge
"""

FAKE_CODEX = r"""#!/usr/bin/env python3
import json, os, signal, sys, time
from pathlib import Path

if sys.argv[1:] == ["--version"]:
    print(os.environ.get("FAKE_CODEX_VERSION", "codex-cli 0.153.2"))
    raise SystemExit(0)
if sys.argv[1:] == ["app-server", "--help"]:
    if os.environ.get("FAKE_DISCOVERY_UNSUPPORTED"):
        print("Usage: codex app-server")
    else:
        print("--ignore-user-config --ignore-rules")
    raise SystemExit(0)
if len(sys.argv) > 1 and sys.argv[1] == "app-server":
    for line in sys.stdin:
        request = json.loads(line)
        method = request.get("method")
        if method == "initialize":
            print(json.dumps({"id": request["id"], "result": {"serverInfo": {}}}), flush=True)
        elif method == "model/list":
            print(json.dumps({"id": request["id"], "result": {"data": [{
                "id": "friendly", "model": "provider/model", "displayName": "Friendly",
                "description": "model", "hidden": False, "isDefault": False,
                "defaultReasoningEffort": "high", "supportedReasoningEfforts": [
                    {"reasoningEffort": "high", "description": "default", "future": True}
                ], "unknownOptionalField": {"safe": True}
            }], "nextCursor": None}}), flush=True)
    raise SystemExit(0)

args = sys.argv[1:]
model = args[args.index("--model") + 1]
effort = args[args.index("-c") + 1].split('"')[1]
output = Path(args[args.index("--output-last-message") + 1])
workdir = Path(args[args.index("-C") + 1])
assert args[0] == "exec" and args[args.index("--sandbox") + 1] == "read-only"
assert workdir.is_dir() and workdir.parent.name.startswith("run.")
prompt = sys.stdin.read()
log = Path(os.environ["FAKE_INVOCATIONS"])
rows = json.loads(log.read_text()) if log.exists() else []
rows.append({"model": model, "effort": effort, "prompt": prompt})
log.write_text(json.dumps(rows))
attempt = len(rows)
case = os.environ.get("FAKE_CASE", "valid")

if case == "launcher-failure":
    raise SystemExit(98)

if case == "exit-124":
    raise SystemExit(124)

if case == "hang":
    marker = Path(os.environ["FAKE_TERM_MARKER"])
    def stopped(*_args):
        marker.write_text("terminated")
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, stopped)
    Path(os.environ["FAKE_READY_MARKER"]).write_text(str(os.getpid()))
    while True:
        time.sleep(1)

if case == "mutate-retry" and attempt == 1:
    Path(os.environ["ADVISOR_LIVE_CONFIG"]).write_text(
        '[advisor]\nmodel = "gpt-6-astra"\neffort_ladder = ["low", "bad", "high", "xhigh"]\n'
    )

child = f"{attempt:08x}-1111-7111-8111-{attempt:012x}"
runtime_model = "wrong/model" if case == "wrong-model" else model
runtime_effort = ("medium" if effort == "low" else "low") if case == "wrong-effort" else effort
events = [
    {"type": "session_meta", "payload": {"id": child, "source": "exec", "originator": "codex_exec"}},
    {"type": "turn_context", "payload": {"model": runtime_model, "effort": runtime_effort, "sandbox_policy": {"type": "read-only"}, "permission_profile": {"type": "managed"}}},
]
if case == "tool":
    events.append({"type": "function_call", "name": "forbidden"})
if case == "reroute":
    events.append({"type": "model_reroute", "from": model, "to": runtime_model})
sessions = Path(os.environ.get("FAKE_SESSIONS_DIR", str(Path(os.environ["CODEX_HOME"]) / "sessions"))) / "fixture"
sessions.mkdir(parents=True, exist_ok=True)
(sessions / f"rollout-fake-{child}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in events))
print(json.dumps({"type": "thread.started", "thread_id": child}))
response = {
    "recommendation": "neutral path", "why": "reason", "strongest_objection": "objection",
    "change_my_mind": "evidence", "acceptance_checks": ["check"], "risks": "none",
    "follow_up_areas": "none",
    "escalation": {"next_level": None, "reason": "sufficient", "unresolved_difficulty": "", "required_resolution": ""}
}
if case == "qualification":
    next_level = {"low": "medium", "medium": "high", "high": "extra_high", "xhigh": None}[effort]
    response["escalation"] = {
        "next_level": next_level,
        "reason": "synthetic qualification stage",
        "unresolved_difficulty": "staged qualification boundary",
        "required_resolution": "exercise the next adjacent runtime effort",
    }
if case == "mutate-retry" and attempt == 1:
    response.pop("risks")
output.write_text(json.dumps(response))
"""


class AdvisorTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "codex"
        self.home.mkdir(mode=0o700)
        self.plugin_root = self.root / "plugin"
        shutil.copytree(ROOT, self.plugin_root)
        self.config_wrapper = self.plugin_root / "scripts" / "advisor-config.sh"
        self.transport = self.plugin_root / "scripts" / "run-advisor.sh"
        self.process = self.plugin_root / "scripts" / "advisor_process.py"
        self.live_config_path = self.plugin_root / "advisor.toml"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fake = self.bin / "codex"
        self.fake.write_text(FAKE_CODEX, encoding="utf-8")
        self.fake.chmod(0o700)
        self.invocations = self.root / "invocations.json"
        self.transport_calls = 0
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home),
            "WSL_DISTRO_NAME": "",
            "ADVISOR_CODEX_BIN": "",
            "ADVISOR_TRANSPORT_CONFIG": str(self.home / "no-wsl-transport-config.json"),
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FAKE_INVOCATIONS": str(self.invocations),
            "ADVISOR_LIVE_CONFIG": str(self.live_config_path),
        }
        self.paths = config.state_paths(self.home)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @contextmanager
    def live_config(self, standard: dict[str, str], specialist: dict[str, str]):
        """Write one active Astra policy to this test's private plugin copy."""
        self.live_config_path.write_text(
            "[advisor]\n"
            f'model = "{standard["model"]}"\n'
            'effort_ladder = ["low", "medium", "high", "xhigh"]\n',
            encoding="utf-8",
        )
        yield self.live_config_path

    def run_transport(
        self, *arguments: str, case: str = "valid", env: dict[str, str] | None = None,
        include_sessions_dir: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        args = list(arguments)
        if "--checkpoint-key" not in args:
            self.transport_calls += 1
            args.extend(("--checkpoint-key", f"test-checkpoint-{self.transport_calls}"))
        command = ["/bin/sh", str(self.transport), *args, "--parent-thread", PARENT]
        if include_sessions_dir:
            command.extend(("--sessions-dir", str(self.home / "sessions")))
        return subprocess.run(
            command,
            input=PACKET,
            text=True,
            capture_output=True,
            check=False,
            env={**self.env, "FAKE_CASE": case, **(env or {})},
            timeout=10,
        )

    def rows(self) -> list[dict[str, str]]:
        return (
            json.loads(self.invocations.read_text())
            if self.invocations.exists()
            else []
        )

    def qualify(self, model: str, effort: str = "high") -> None:
        config.add_manual_candidate(model, paths=self.paths)
        config.record_compatibility(
            {"model": model, "effort": effort},
            codex_version="codex-cli 0.153.2",
            paths=self.paths,
        )

    def test_discovery_accepts_protocol_without_jsonrpc_and_ignores_optional_fields(
        self,
    ) -> None:
        result = subprocess.run(
            [str(self.config_wrapper), "--json", "models", "refresh"],
            text=True,
            capture_output=True,
            check=False,
            env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        candidate = json.loads(result.stdout)["catalog"]["candidates"][0]
        self.assertEqual(candidate["model"], "provider/model")
        self.assertEqual(candidate["advertised_efforts"], ["high"])

    def test_discovery_is_safely_unavailable_when_cli_cannot_ignore_config(
        self,
    ) -> None:
        result = subprocess.run(
            [str(self.config_wrapper), "--json", "models", "refresh"],
            text=True,
            capture_output=True,
            check=False,
            env={**self.env, "FAKE_DISCOVERY_UNSUPPORTED": "1"},
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.paths.root.exists())

    def test_live_tiers_ignore_stale_saved_selections_and_legacy_roles_remain_fixed(self) -> None:
        standard = self.run_transport("--tier", "standard")
        specialist = self.run_transport("--tier", "specialist")
        self.assertEqual((standard.returncode, specialist.returncode), (0, 0))
        self.qualify("gpt-6-astra")
        settings = config.load_settings(self.paths)
        settings["selections"]["standard"] = {"model": "gpt-6-astra", "effort": "high"}
        config.save_settings(
            settings, expected_revision=settings["revision"], paths=self.paths
        )
        configured = self.run_transport("--tier", "standard")
        legacy = self.run_transport("--role", "advisor-terra")
        self.assertEqual(configured.returncode, 0, configured.stderr)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(
            [(row["model"], row["effort"]) for row in self.rows()],
            [
                ("gpt-6-astra", "low"),
                ("gpt-6-astra", "low"),
                ("gpt-6-astra", "low"),
                ("gpt-6-astra", "low"),
            ],
        )

    def test_legacy_preset_cannot_change_active_astra_policy(self) -> None:
        self.qualify("future/model", "max")
        config.save_preset(
            "future",
            {"model": "future/model", "effort": "max"},
            paths=self.paths,
        )
        result = self.run_transport(
            "--tier", "standard", "--preset", "future",
            env={"FAKE_CODEX_VERSION": "codex-cli 0.154.0"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.rows(), [])
        self.assertEqual(
            config.load_settings(self.paths)["selections"]["standard"]["model"],
            "gpt-6-astra",
        )

    def test_live_astra_and_independent_effort_launch_without_optional_config_state(self) -> None:
        with self.live_config(
            {"model": "gpt-6-astra", "effort": "low"},
            {"model": "gpt-6-astra", "effort": "low"},
        ):
            standard = self.run_transport("--tier", "standard")
            specialist = self.run_transport("--tier", "specialist")
        self.assertEqual((standard.returncode, specialist.returncode), (0, 0))
        self.assertEqual(
            [(row["model"], row["effort"]) for row in self.rows()],
            [("gpt-6-astra", "low"), ("gpt-6-astra", "low")],
        )
        self.assertTrue((self.paths.root / "chains").is_dir())
        self.assertFalse(self.paths.settings.exists())
        self.assertFalse(self.paths.catalog.exists())
        self.assertFalse(self.paths.canaries.exists())
        self.assertFalse(self.paths.journal.exists())
        selection = json.loads(standard.stdout)["selection"]
        self.assertEqual(selection["source"], "legacy-tier-alias")
        self.assertTrue(selection["source_revision"].startswith("sha256:"))

    def test_non_astra_active_policy_and_malformed_toml_launch_nothing(self) -> None:
        with self.live_config(
            {"model": "future/provider-2049", "effort": "low"},
            {"model": "gpt-6-astra", "effort": "low"},
        ):
            future = self.run_transport("--tier", "standard")
        self.assertNotEqual(future.returncode, 0)
        self.assertEqual(self.rows(), [])
        self.live_config_path.write_text(
            "[advisor]\nmodel = \"bad\"\neffort_ladder = [\"low\", \"medium\", \"high\", \"xhigh\"]\n"
        )
        invalid = self.run_transport("--tier", "standard")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("advisor.toml", invalid.stderr)
        self.assertEqual(len(self.rows()), 0, "invalid config must fail before child launch")
        self.live_config_path.write_text(
            '[advisor]\nmodel = "gpt-6-astra"\neffort_ladder = ["low", "bad", "high", "xhigh"]\n'
        )
        invalid_selector = self.run_transport("--tier", "standard")
        self.assertNotEqual(invalid_selector.returncode, 0)
        self.assertIn("advisor.toml", invalid_selector.stderr)
        self.assertEqual(len(self.rows()), 0, "invalid effort must fail before child launch")

    def test_saved_selection_is_ignored_and_mixed_route_is_rejected(self) -> None:
        config.add_manual_candidate("future/model", paths=self.paths)
        settings = config.baseline_settings()
        settings["selections"]["standard"] = {"model": "future/model", "effort": "max"}
        config.save_settings(settings, expected_revision=0, paths=self.paths)
        unqualified = self.run_transport("--tier", "standard")
        mixed = self.run_transport("--tier", "standard", "--role", "advisor-terra")
        self.assertEqual(unqualified.returncode, 0, unqualified.stderr)
        self.assertNotEqual(mixed.returncode, 0)
        self.assertEqual(
            [(row["model"], row["effort"]) for row in self.rows()],
            [("gpt-6-astra", "low")],
        )

    def test_legacy_role_alias_cannot_bypass_invalid_active_policy(self) -> None:
        self.live_config_path.write_text(
            '[advisor]\nmodel = "gpt-5.6-terra"\neffort_ladder = ["low", "medium", "high", "xhigh"]\n',
            encoding="utf-8",
        )
        result = self.run_transport("--role", "advisor-terra")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.rows(), [])

    def test_checkpoint_reservation_prevents_replay_after_a_completed_pass(self) -> None:
        first = self.run_transport("--tier", "standard", "--checkpoint-key", "stable-checkpoint")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_transport("--tier", "standard", "--checkpoint-key", "stable-checkpoint")
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_synthetic_qualification_is_opt_in_and_uses_an_isolated_production_ledger(self) -> None:
        run_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        qualification_root = self.home / ".codex-advisor" / f"qualification-{run_id}"
        common = (
            "--level", "low", "--checkpoint-key", "controlled-full-chain",
            "--qualification-scenario", "full-adjacent-escalation-v1",
            "--qualification-run-id", run_id,
        )

        disabled = self.run_transport(*common, case="qualification")
        self.assertNotEqual(disabled.returncode, 0)
        self.assertIn("qualification requires explicit opt-in", disabled.stderr)
        self.assertEqual(self.rows(), [])
        self.assertFalse(qualification_root.exists())
        self.assertFalse((self.paths.root / "chains").exists())

        low = self.run_transport(
            *common, case="qualification",
            env={
                "ADVISOR_ENABLE_SYNTHETIC_QUALIFICATION": "1",
                "HOME": str(self.home),
            },
        )
        self.assertEqual(low.returncode, 0, low.stderr)
        low_envelope = json.loads(low.stdout)
        self.assertIs(low_envelope["synthetic_scenario"], True)
        self.assertEqual(low_envelope["qualification_scenario"], "full-adjacent-escalation-v1")
        self.assertEqual(low_envelope["qualification_run_id"], run_id)
        self.assertEqual(low_envelope["escalation"]["next_level"], "medium")
        self.assertIn("SYNTHETIC QUALIFICATION", self.rows()[0]["prompt"])
        self.assertTrue(qualification_root.is_dir())
        qualification_states = list(qualification_root.glob("*.json"))
        self.assertEqual(len(qualification_states), 1)
        low_state = json.loads(qualification_states[0].read_text(encoding="utf-8"))
        self.assertEqual(low_state["next_action"], "reserve:medium")
        self.assertFalse((self.paths.root / "chains").exists())

        medium = self.run_transport(
            "--level", "medium", "--chain-authorized",
            "--checkpoint-key", "controlled-full-chain",
            "--qualification-scenario", "full-adjacent-escalation-v1",
            "--qualification-run-id", run_id,
            case="qualification",
            env={
                "ADVISOR_ENABLE_SYNTHETIC_QUALIFICATION": "1",
                "HOME": str(self.home),
            },
        )
        self.assertEqual(medium.returncode, 0, medium.stderr)
        medium_envelope = json.loads(medium.stdout)
        self.assertIs(medium_envelope["synthetic_scenario"], True)
        self.assertEqual(medium_envelope["selection"]["effort"], "medium")
        self.assertEqual(medium_envelope["escalation"]["next_level"], "high")
        self.assertEqual(len(list(qualification_root.glob("*.json"))), 1)
        state = json.loads(next(qualification_root.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(state["next_action"], "reserve:high")
        self.assertEqual(state["levels"]["low"]["next_level"], "medium")
        self.assertEqual(state["levels"]["medium"]["status"], "completed")

        production = self.run_transport(
            "--level", "low", "--checkpoint-key", "controlled-full-chain"
        )
        self.assertEqual(production.returncode, 0, production.stderr)
        production_envelope = json.loads(production.stdout)
        self.assertNotIn("synthetic_scenario", production_envelope)
        self.assertEqual(len(list((self.paths.root / "chains").glob("*.json"))), 1)
        self.assertEqual(len(self.rows()), 3)

    def test_launch_failure_finalizes_failed_ledger_without_replay(self) -> None:
        first = self.run_transport(
            "--tier", "standard", "--checkpoint-key", "failed-launch-checkpoint", case="launcher-failure"
        )
        self.assertNotEqual(first.returncode, 0)
        self.assertNotIn("checkpoint safety state could not be finalized", first.stderr)
        self.assertEqual(len(self.rows()), 1)
        chain_files = list((self.paths.root / "chains").glob("*.json"))
        self.assertEqual(len(chain_files), 1)
        state = json.loads(chain_files[0].read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["levels"]["low"]["failure_code"], "launch_failed")

        second = self.run_transport(
            "--tier", "standard", "--checkpoint-key", "failed-launch-checkpoint"
        )
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_child_exit_124_is_not_mistaken_for_supervisor_timeout(self) -> None:
        result = self.run_transport(
            "--tier", "standard", "--checkpoint-key", "child-exit-124", case="exit-124"
        )
        self.assertNotEqual(result.returncode, 0)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope["outcome"], "failed")
        self.assertEqual(envelope["attempts"][0]["outcome"], "launch_failed")
        state_file = next((self.paths.root / "chains").glob("*.json"))
        state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["levels"]["low"]["failure_code"], "launch_failed")

    def test_codex_preflight_fails_before_reservation(self) -> None:
        broken_bin = self.root / "broken-bin"
        broken_bin.mkdir()
        broken = broken_bin / "codex"
        broken.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
        broken.chmod(0o700)
        result = self.run_transport(
            "--tier", "standard", "--checkpoint-key", "preflight-failure-checkpoint",
            env={"PATH": f"{broken_bin}:{os.environ['PATH']}"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Codex CLI preflight failed", result.stderr)
        self.assertFalse((self.paths.root / "chains").exists())
        self.assertEqual(self.rows(), [])

    def test_explicit_codex_binary_is_used_for_preflight_and_launch(self) -> None:
        broken_bin = self.root / "broken-bin"
        broken_bin.mkdir()
        broken = broken_bin / "codex"
        broken.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
        broken.chmod(0o700)
        result = self.run_transport(
            "--tier", "standard", "--checkpoint-key", "explicit-binary-checkpoint",
            env={"PATH": f"{broken_bin}:{os.environ['PATH']}", "ADVISOR_CODEX_BIN": str(self.fake)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.rows()), 1)

    def _install_test_transport_config(
        self, adapter_bytes: bytes, *, node_executable: Path, entrypoint: Path,
        sessions_directory: Path,
    ) -> tuple[Path, Path]:
        private_root = self.home / ".codex-advisor"
        private_root.mkdir(mode=0o700)
        transport_dir = private_root / "transport"
        transport_dir.mkdir(mode=0o700)
        bridge = transport_dir / "codex-wsl-bridge.py"
        bridge.write_bytes(adapter_bytes)
        bridge.chmod(0o700)
        config_path = transport_dir / "transport.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "adapter_path": str(bridge),
                    "adapter_sha256": hashlib.sha256(adapter_bytes).hexdigest(),
                    "windows_node_executable": str(node_executable),
                    "windows_codex_entrypoint": str(entrypoint),
                    "sessions_directory": str(sessions_directory),
                }
            ),
            encoding="utf-8",
        )
        config_path.chmod(0o600)
        return bridge, config_path

    def test_wsl_bridge_preserves_argument_boundaries_and_unicode_stdin(self) -> None:
        node = self.root / "fake-node"
        node.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "print(json.dumps({'argv':sys.argv[1:],'stdin':sys.stdin.read()},ensure_ascii=False))\n",
            encoding="utf-8",
        )
        node.chmod(0o700)
        entrypoint = self.root / "codex.js"
        entrypoint.write_text("fixture", encoding="utf-8")
        sessions = self.home / "sessions"
        sessions.mkdir(mode=0o700)
        bridge, config_path = self._install_test_transport_config(
            ADAPTER_MODULE.read_bytes(),
            node_executable=node,
            entrypoint=entrypoint,
            sessions_directory=sessions,
        )

        result = subprocess.run(
            [str(bridge), "exec", "--config", "value with spaces", "Tiếng Việt"],
            input="packet\nTiếng Việt\n",
            text=True,
            capture_output=True,
            check=False,
            env={**self.env, "ADVISOR_TRANSPORT_CONFIG": str(config_path)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "argv": [str(entrypoint), "exec", "--config", "value with spaces", "Tiếng Việt"],
                "stdin": "packet\nTiếng Việt\n",
            },
        )

    def test_wsl_bridge_maps_only_codex_path_options_to_windows_paths(self) -> None:
        node = self.root / "fake-node"
        node.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "print(json.dumps(sys.argv[1:],ensure_ascii=False))\n",
            encoding="utf-8",
        )
        node.chmod(0o700)
        entrypoint = self.root / "codex.js"
        entrypoint.write_text("fixture", encoding="utf-8")
        sessions = self.home / "sessions"
        sessions.mkdir(mode=0o700)
        bridge, config_path = self._install_test_transport_config(
            ADAPTER_MODULE.read_bytes(),
            node_executable=node,
            entrypoint=entrypoint,
            sessions_directory=sessions,
        )
        mapper_dir = self.root / "path-mapper-bin"
        mapper_dir.mkdir()
        mapper = mapper_dir / "wslpath"
        mapper.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "if sys.argv[1] != '-w' or not sys.argv[2].startswith('/'):\n"
            "    raise SystemExit(2)\n"
            "print('Z:/mapped' + sys.argv[2])\n",
            encoding="utf-8",
        )
        mapper.chmod(0o700)
        paths = [
            "/tmp/advisor work/準備",
            "/tmp/advisor schema/契約.json",
            "/tmp/advisor output/回答.json",
        ]
        other_path = "/tmp/leave unchanged/保留"
        arguments = [
            "exec",
            "-C",
            paths[0],
            "--output-schema",
            paths[1],
            f"--output-last-message={paths[2]}",
            "--other-file",
            other_path,
        ]
        result = subprocess.run(
            [str(bridge), *arguments],
            text=True,
            capture_output=True,
            check=False,
            env={
                **self.env,
                "PATH": f"{mapper_dir}:{os.environ['PATH']}",
                "ADVISOR_TRANSPORT_CONFIG": str(config_path),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                str(entrypoint),
                "exec",
                "-C",
                "Z:/mapped" + paths[0],
                "--output-schema",
                "Z:/mapped" + paths[1],
                "--output-last-message=Z:/mapped" + paths[2],
                "--other-file",
                other_path,
            ],
        )

    def test_app_server_discovery_uses_configured_wsl_bridge_without_path_codex(self) -> None:
        node = self.root / "configured-node"
        node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        node.chmod(0o700)
        entrypoint = self.root / "codex.js"
        entrypoint.write_text("fixture", encoding="utf-8")
        sessions = self.home / "sessions"
        sessions.mkdir(mode=0o700)
        bridge, config_path = self._install_test_transport_config(
            ADAPTER_MODULE.read_bytes(),
            node_executable=node,
            entrypoint=entrypoint,
            sessions_directory=sessions,
        )
        probed: list[list[str]] = []
        launched: list[list[str]] = []

        def probe(command: list[str], **_kwargs: object) -> tuple[int, bytes]:
            probed.append(command)
            return 0, b"--ignore-user-config --ignore-rules"

        def process(command: list[str], **kwargs: object) -> str:
            launched.append(command)
            callback = kwargs.get("on_close")
            if callable(callback):
                callback()
            return "connection"

        with patch.dict(
            os.environ,
            {
                **self.env,
                "HOME": str(self.home),
                "WSL_DISTRO_NAME": "Ubuntu",
                "ADVISOR_TRANSPORT_CONFIG": str(config_path),
                "ADVISOR_CODEX_BIN": "",
                "PATH": str(self.root / "empty-path"),
            },
        ), patch.object(config, "_run_bounded_output", side_effect=probe), patch.object(
            config, "JsonRpcProcess", side_effect=process
        ):
            result = config.AppServerDiscovery()._connection()

        self.assertEqual(result, "connection")
        self.assertEqual(probed, [[str(bridge), "app-server", "--help"]])
        self.assertEqual(
            launched,
            [[str(bridge), "app-server", "--ignore-user-config", "--ignore-rules"]],
        )

    def test_wsl_installer_writes_private_persistent_transport_from_windows_paths(self) -> None:
        installer = self.plugin_root / "scripts" / "install-wsl-transport.sh"
        windows_profile = r"C:\fixture-user"
        windows_appdata = r"C:\fixture-user\AppData\Roaming"
        entrypoint = self.root / "codex.js"
        entrypoint.write_text("fixture", encoding="utf-8")
        sessions = self.root / "windows-sessions"
        sessions.mkdir(mode=0o700)
        fake_bin = self.root / "installer-bin"
        fake_bin.mkdir()

        cmd_exe = fake_bin / "cmd.exe"
        cmd_exe.write_text(
            "#!/bin/sh\n"
            'case "$*" in\n'
            '  *USERPROFILE*) printf \'%s\\r\\n\' "$FAKE_WINDOWS_PROFILE" ;;\n'
            '  *APPDATA*) printf \'%s\\r\\n\' "$FAKE_WINDOWS_APPDATA" ;;\n'
            '  *) exit 2 ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        cmd_exe.chmod(0o700)

        wslpath = fake_bin / "wslpath"
        wslpath.write_text(
            "#!/bin/sh\n"
            'case "$2" in\n'
            '  *"@openai/codex/bin/codex.js") printf \'%s\\n\' "$FAKE_CODEX_ENTRYPOINT" ;;\n'
            '  *".codex/sessions") printf \'%s\\n\' "$FAKE_WINDOWS_SESSIONS" ;;\n'
            '  *) exit 2 ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        wslpath.chmod(0o700)

        node = fake_bin / "node.exe"
        node.write_text(
            "#!/bin/sh\n"
            "shift\n"
            'if [ "${1-}" = --version ]; then printf \'codex-cli 0.155.0\\n\'; exit 0; fi\n'
            "exit 97\n",
            encoding="utf-8",
        )
        node.chmod(0o700)
        installer_home = self.root / "installer-home"
        installer_home.mkdir(mode=0o700)

        installer_env = {
            **self.env,
            "HOME": str(installer_home),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "WSL_DISTRO_NAME": "Ubuntu",
            "FAKE_WINDOWS_PROFILE": windows_profile,
            "FAKE_WINDOWS_APPDATA": windows_appdata,
            "FAKE_CODEX_ENTRYPOINT": str(entrypoint),
            "FAKE_WINDOWS_SESSIONS": str(sessions),
        }
        result = subprocess.run(
            ["/bin/sh", str(installer)],
            text=True,
            capture_output=True,
            check=False,
            env=installer_env,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ADVISOR WSL INSTALL: verified (codex-cli 0.155.0)", result.stdout)
        config_path = installer_home / ".codex-advisor" / "transport" / "transport.json"
        config_value = json.loads(config_path.read_text(encoding="utf-8"))
        bridge = Path(config_value["adapter_path"])
        self.assertEqual(config_value["sessions_directory"], str(sessions))
        self.assertEqual(bridge.stat().st_mode & 0o777, 0o700)
        self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(config_path.parent.stat().st_mode & 0o777, 0o700)

        previous_config = config_value
        transport_source = self.plugin_root / "scripts" / "advisor_transport.py"
        transport_source.write_bytes(transport_source.read_bytes() + b"\n# candidate update fixture\n")
        updated_sessions = self.root / "updated-windows-sessions"
        updated_sessions.mkdir(mode=0o700)
        updated = subprocess.run(
            ["/bin/sh", str(installer)],
            text=True,
            capture_output=True,
            check=False,
            env={**installer_env, "FAKE_WINDOWS_SESSIONS": str(updated_sessions)},
            timeout=10,
        )
        self.assertEqual(updated.returncode, 0, updated.stderr)
        update_result = json.loads(updated.stdout.splitlines()[0])
        updated_config = json.loads(config_path.read_text(encoding="utf-8"))
        config_backups = json.loads(update_result["backups"])
        self.assertEqual(len(config_backups), 1)
        self.assertEqual(
            json.loads(Path(config_backups[0]).read_text(encoding="utf-8")),
            previous_config,
        )
        self.assertEqual(updated_config["sessions_directory"], str(updated_sessions))
        self.assertNotEqual(updated_config["adapter_path"], previous_config["adapter_path"])
        self.assertTrue(Path(previous_config["adapter_path"]).is_file())
        self.assertTrue(Path(updated_config["adapter_path"]).is_file())

    def test_wsl_transport_uses_installed_bridge_and_sessions_config(self) -> None:
        self.fake.write_text(FAKE_CODEX, encoding="utf-8")
        self.fake.chmod(0o700)
        entrypoint = self.root / "codex.js"
        entrypoint.write_text("fixture", encoding="utf-8")
        sessions = self.home / "sessions"
        sessions.mkdir(mode=0o700)
        bridge, config_path = self._install_test_transport_config(
            (
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> {shlex.quote(str(self.root / 'bridge-calls'))}\n"
                f"exec {shlex.quote(str(self.fake))} \"$@\"\n"
            ).encode("utf-8"),
            node_executable=self.fake,
            entrypoint=entrypoint,
            sessions_directory=sessions,
        )
        result = self.run_transport(
            "--level", "low", env={
                "WSL_DISTRO_NAME": "Ubuntu",
                "ADVISOR_CODEX_BIN": "",
                "ADVISOR_TRANSPORT_CONFIG": str(config_path),
                "FAKE_SESSIONS_DIR": str(sessions),
                "PATH": os.environ["PATH"],
            }, include_sessions_dir=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Codex CLI preflight passed", result.stderr)
        self.assertEqual([(row["model"], row["effort"]) for row in self.rows()], [("gpt-6-astra", "low")])
        self.assertTrue((sessions / "fixture").is_dir())
        bridge_calls = (self.root / "bridge-calls").read_text(encoding="utf-8").splitlines()
        self.assertEqual(bridge_calls[0], "--version")
        self.assertTrue(bridge_calls[1].startswith("exec --json"))
        self.assertEqual(bridge.stat().st_mode & 0o077, 0)

    def test_wsl_transport_rejects_modified_bridge_before_checkpoint_reservation(self) -> None:
        entrypoint = self.root / "codex.js"
        entrypoint.write_text("fixture", encoding="utf-8")
        sessions = self.home / "sessions"
        sessions.mkdir(mode=0o700)
        bridge, config_path = self._install_test_transport_config(
            FAKE_CODEX.encode("utf-8"),
            node_executable=self.fake,
            entrypoint=entrypoint,
            sessions_directory=sessions,
        )
        bridge.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        bridge.chmod(0o700)
        result = self.run_transport(
            "--level", "low", env={
                "WSL_DISTRO_NAME": "Ubuntu",
                "ADVISOR_CODEX_BIN": "",
                "ADVISOR_TRANSPORT_CONFIG": str(config_path),
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("configured WSL Codex transport is unavailable", result.stderr)
        self.assertFalse((self.paths.root / "chains").exists())
        self.assertEqual(self.rows(), [])

    def test_doctor_reports_installed_wsl_transport_and_rejects_bad_path_safely(self) -> None:
        entrypoint = self.root / "codex.js"
        entrypoint.write_text("fixture", encoding="utf-8")
        sessions = self.root / "windows-sessions"
        sessions.mkdir(mode=0o700)
        bridge, config_path = self._install_test_transport_config(
            ADAPTER_MODULE.read_bytes(),
            node_executable=self.fake,
            entrypoint=entrypoint,
            sessions_directory=sessions,
        )
        env = {
            "HOME": str(self.home),
            "WSL_DISTRO_NAME": "Ubuntu",
            "ADVISOR_CODEX_BIN": "",
            "ADVISOR_TRANSPORT_CONFIG": str(config_path),
        }
        probe_calls: list[list[str]] = []

        def doctor_probe(argv: list[str], **_kwargs: object) -> dict[str, str]:
            probe_calls.append(list(argv))
            if argv[0] == "/bin/sh":
                return {
                    "status": "available",
                    "detail": json.dumps(
                        {
                            "status": "available",
                            "thread_id": PARENT,
                            "sandbox_policy_type": "workspace-write",
                            "permission_profile_type": "managed",
                        }
                    ),
                }
            return {
                "status": "available",
                "detail": "codex-cli 0.155.0 --ignore-user-config --ignore-rules",
            }

        with patch.dict(os.environ, env, clear=False):
            with patch.object(
                config, "_doctor_probe", side_effect=doctor_probe,
            ):
                report = config.doctor_report(paths=self.paths)
            codex = report["dependencies"]["codex"]
            self.assertEqual(codex["path"], str(bridge))
            self.assertEqual(codex["source"], "installed-wsl-bridge")
            self.assertEqual(codex["sessions_directory"], str(sessions))
            self.assertEqual(report["parent_runtime"]["thread_id"], PARENT)
            parent_probe = next(argv for argv in probe_calls if argv[0] == "/bin/sh")
            self.assertEqual(parent_probe[-2:], ["--sessions-dir", str(sessions)])

        with patch.dict(
            os.environ,
            {**env, "ADVISOR_TRANSPORT_CONFIG": "relative/transport.json"},
            clear=False,
        ):
            self.assertEqual(
                config._codex_transport_source(),
                (None, "invalid-wsl-config", None),
            )
            with self.assertRaises(config.ConfigError):
                config._resolve_codex_executable()

    def test_cli_version_change_does_not_replace_live_tier_before_launch(self) -> None:
        self.qualify("future/model")
        settings = config.load_settings(self.paths)
        settings["selections"]["standard"] = {
            "model": "future/model",
            "effort": "high",
        }
        config.save_settings(
            settings, expected_revision=settings["revision"], paths=self.paths
        )
        result = subprocess.run(
            [
                "/bin/sh",
                str(self.transport),
                "--tier",
                "standard",
                "--parent-thread",
                PARENT,
                "--sessions-dir",
                str(self.home / "sessions"),
            ],
            input=PACKET,
            text=True,
            capture_output=True,
            check=False,
            env={**self.env, "FAKE_CODEX_VERSION": "codex-cli 0.154.0"},
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [(row["model"], row["effort"]) for row in self.rows()],
            [("gpt-6-astra", "low")],
        )

    def test_pristine_defaults_launch_on_newer_cli_without_optional_config_state(self) -> None:
        result = subprocess.run(
            [
                "/bin/sh",
                str(self.transport),
                "--tier",
                "standard",
                "--parent-thread",
                PARENT,
                "--sessions-dir",
                str(self.home / "sessions"),
            ],
            input=PACKET,
            text=True,
            capture_output=True,
            check=False,
            env={**self.env, "FAKE_CODEX_VERSION": "codex-cli 0.153.4"},
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows()[0]["model"], "gpt-6-astra")
        self.assertTrue((self.paths.root / "chains").is_dir())
        self.assertFalse(self.paths.settings.exists())
        self.assertFalse(self.paths.catalog.exists())
        self.assertFalse(self.paths.canaries.exists())
        self.assertFalse(self.paths.journal.exists())

    def test_default_runtime_mismatch_still_rejects_actual_consultation(self) -> None:
        result = self.run_transport("--tier", "standard", case="wrong-model")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_authorized_canary_records_exact_cli_pair_without_selecting_it(
        self,
    ) -> None:
        config.add_manual_candidate("future/model", paths=self.paths)
        result = subprocess.run(
            [
                str(self.config_wrapper),
                "--json",
                "models",
                "test",
                "future/model",
                "--effort",
                "max",
                "--authorize-usage",
                "--parent-thread",
                PARENT,
                "--sessions-dir",
                str(self.home / "sessions"),
            ],
            text=True,
            capture_output=True,
            check=False,
            env=self.env,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = config.load_catalog(self.paths)["compatibility"][0]
        self.assertEqual(
            (receipt["model"], receipt["effort"], receipt["codex_version"]),
            ("future/model", "max", "codex-cli 0.153.2"),
        )
        self.assertEqual(
            config.load_settings(self.paths)["selections"],
            config.baseline_settings()["selections"],
        )
        self.assertIn("content-free transport canary", self.rows()[0]["prompt"])

    def test_response_validation_is_terminal_and_does_not_retry(self) -> None:
        result = self.run_transport("--tier", "standard", case="mutate-retry")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.rows()), 1)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope["status"], "unavailable")
        self.assertEqual(
            [row["outcome"] for row in envelope["attempts"]],
            ["rejected_response"],
        )
        self.assertNotIn("second consultation attempt", result.stderr)

    def test_runtime_mismatch_reroute_and_tool_use_are_terminal(self) -> None:
        for case in ("wrong-model", "wrong-effort", "reroute", "tool"):
            self.invocations.unlink(missing_ok=True)
            result = self.run_transport("--role", "advisor-terra", case=case)
            self.assertNotEqual(result.returncode, 0, case)
            self.assertEqual(len(self.rows()), 1, case)

    def test_term_reaps_owned_group_cleans_private_state_and_spares_unrelated(
        self,
    ) -> None:
        unrelated = subprocess.Popen(["sleep", "20"])
        ready = self.root / "ready"
        terminated = self.root / "terminated"
        process = subprocess.Popen(
            [
                "/bin/sh",
                str(self.transport),
                "--role",
                "advisor-terra",
                "--parent-thread",
                PARENT,
                "--sessions-dir",
                str(self.home / "sessions"),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={
                **self.env,
                "FAKE_CASE": "hang",
                "FAKE_READY_MARKER": str(ready),
                "FAKE_TERM_MARKER": str(terminated),
            },
        )
        assert process.stdin
        process.stdin.write(PACKET)
        process.stdin.close()
        try:
            for _ in range(50):
                if ready.exists():
                    break
                time.sleep(0.05)
            self.assertTrue(ready.exists())
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=6)
            assert process.stdout and process.stderr
            process.stdout.close()
            process.stderr.close()
            self.assertTrue(terminated.exists())
            transport_root = self.home / ".tmp" / "advisor-transport"
            self.assertFalse(any(transport_root.glob("run.*")))
            self.assertIsNone(unrelated.poll())
        finally:
            if process.poll() is None:
                process.kill()
            unrelated.terminate()
            unrelated.wait(timeout=3)

    def test_wrapper_total_deadline_terminates_child_and_cleans_private_state(
        self,
    ) -> None:
        settings = config.baseline_settings()
        settings["deadline_seconds"] = 30
        config.save_settings(settings, expected_revision=0, paths=self.paths)
        ready = self.root / "deadline-ready"
        terminated = self.root / "deadline-terminated"
        started = time.monotonic()
        result = subprocess.run(
            [
                "/bin/sh",
                str(self.transport),
                "--tier",
                "standard",
                "--checkpoint-key",
                "deadline-checkpoint",
                "--parent-thread",
                PARENT,
                "--sessions-dir",
                str(self.home / "sessions"),
            ],
            input=PACKET,
            text=True,
            capture_output=True,
            check=False,
            env={
                **self.env,
                "FAKE_CASE": "hang",
                "FAKE_READY_MARKER": str(ready),
                "FAKE_TERM_MARKER": str(terminated),
            },
            timeout=36,
        )
        elapsed = time.monotonic() - started
        self.assertNotEqual(result.returncode, 0)
        self.assertGreaterEqual(elapsed, 28)
        self.assertLess(elapsed, 35)
        self.assertTrue(ready.exists())
        self.assertTrue(terminated.exists())
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope["outcome"], "timed_out")
        self.assertEqual(envelope["attempts"][0]["outcome"], "timed_out")
        state_file = next((self.paths.root / "chains").glob("*.json"))
        state = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "uncertain")
        self.assertEqual(state["levels"]["low"]["failure_code"], "timed_out")
        transport_root = self.home / ".tmp" / "advisor-transport"
        self.assertFalse(any(transport_root.glob("run.*")))

    def test_cancel_while_waiting_for_packet_is_prompt_and_cleans_capture(self) -> None:
        process = subprocess.Popen(
            [
                "/bin/sh",
                str(self.transport),
                "--role",
                "advisor-terra",
                "--parent-thread",
                PARENT,
                "--sessions-dir",
                str(self.home / "sessions"),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        transport_root = self.home / ".tmp" / "advisor-transport"
        try:
            for _ in range(50):
                if any(transport_root.glob("run.*")):
                    break
                time.sleep(0.05)
            self.assertTrue(any(transport_root.glob("run.*")))
            started = time.monotonic()
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=4)
            self.assertLess(time.monotonic() - started, 3)
            self.assertFalse(any(transport_root.glob("run.*")))
            self.assertEqual(self.rows(), [])
        finally:
            if process.poll() is None:
                process.kill()
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

    def test_process_deadline_bounds_partial_json_line(self) -> None:
        server = self.root / "partial.py"
        server.write_text(
            "import sys,time; sys.stdout.write('{'); sys.stdout.flush(); time.sleep(5)"
        )
        script = f"""import sys; sys.path.insert(0,{str(self.process.parent)!r}); from advisor_process import JsonRpcProcess\np=JsonRpcProcess([sys.executable,{str(server)!r}],deadline_seconds=.2)\ntry:\n p.request('x',{{}})\nfinally:\n p.close()\n"""
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(time.monotonic() - started, 2)

    def test_jsonrpc_rejects_server_requests_and_notification_floods(self) -> None:
        cases = {
            "request": "import json,sys; r=json.loads(sys.stdin.readline()); print(json.dumps({'id':99,'method':'ask','params':{}}),flush=True)",
            "flood": "import json,sys; r=json.loads(sys.stdin.readline()); [print(json.dumps({'method':'note','params':{}}),flush=True) for _ in range(513)]",
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                server = self.root / f"{name}.py"
                server.write_text(source)
                script = f"""import sys; sys.path.insert(0,{str(self.process.parent)!r}); from advisor_process import JsonRpcProcess
p=JsonRpcProcess([sys.executable,{str(server)!r}],deadline_seconds=1)
try:
 p.request('x',{{}})
finally:
 p.close()
"""
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=3,
                )
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
