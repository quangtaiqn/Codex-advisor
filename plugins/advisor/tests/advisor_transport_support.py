"""Shared test fixtures, constants, and subprocess helpers for Advisor transport tests."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_WRAPPER = ROOT / "scripts" / "advisor-config.sh"
TRANSPORT = ROOT / "scripts" / "run-advisor.sh"
PROCESS = ROOT / "scripts" / "advisor_process.py"
CONFIG_MODULE = ROOT / "scripts" / "advisor_config.py"
# Every sibling module is checked, so a module the shell helper list forgets fails these tests.
HELPERS = (
    *sorted(path.name for path in CONFIG_MODULE.parent.glob("advisor_*.py")),
    "inspect-agent-runtime.sh",
)
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
schema = json.loads(Path(args[args.index("--output-schema") + 1]).read_text())
rows.append({"model": model, "effort": effort, "prompt": prompt, "output_schema": schema})
log.write_text(json.dumps(rows))

# Inspect the schema actually sent by the launcher, not a template-only check.
# Reject documented unsupported composition; this is not a live provider probe
# or an exhaustive implementation of the provider's JSON Schema validator.
def provider_schema(node):
    unsupported = set(node) & {"allOf", "not", "dependentRequired", "dependentSchemas",
                               "if", "then", "else"}
    if unsupported:
        raise ValueError("unsupported provider schema keywords: " + ", ".join(sorted(unsupported)))
    assert "type" in node, "provider schema node must declare a type"
    if node["type"] == "object":
        assert node["additionalProperties"] is False
        assert set(node["required"]) == set(node["properties"])
        for child_schema in node["properties"].values():
            provider_schema(child_schema)
    if node["type"] == "array":
        provider_schema(node["items"])
assert schema["type"] == "object"
provider_schema(schema)
attempt = len(rows)
case = os.environ.get("FAKE_CASE", "valid")

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
        '[standard]\nmodel = "gpt-6.1-sol"\neffort = "ultra"\n\n'
        '[specialist]\nmodel = "gpt-6-astra"\neffort = "max"\n'
    )

child = os.environ.get("FAKE_REUSED_CHILD") or f"{attempt:08x}-1111-7111-8111-{attempt:012x}"
runtime_model = "wrong/model" if case == "wrong-model" else model
runtime_effort = ("high" if effort == "low" else "low") if case == "wrong-effort" else effort
events = [
    {"type": "session_meta", "payload": {"id": child, "source": "exec", "originator": "codex_exec"}},
    {"type": "turn_context", "payload": {"model": runtime_model, "effort": runtime_effort, "sandbox_policy": {"type": "read-only"}, "permission_profile": {"type": "managed"}}},
]
if case == "tool":
    events.append({"type": "function_call", "name": "forbidden"})
if case == "reroute":
    events.append({"type": "model_reroute", "from": model, "to": runtime_model})
sessions = Path(os.environ["CODEX_HOME"]) / "sessions" / "fixture"
sessions.mkdir(parents=True, exist_ok=True)
(sessions / f"rollout-fake-{child}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in events))
print(json.dumps({"type": "thread.started", "thread_id": child}))
response = {
    "recommendation": "neutral path", "why": "reason", "strongest_objection": "objection",
    "change_my_mind": "evidence", "acceptance_checks": ["check"], "risks": "none",
    "follow_up_areas": "none",
    "escalation": {"next_level": None, "reason": "sufficient", "unresolved_difficulty": "", "required_resolution": ""}
}
if case == "mutate-retry" and attempt == 1:
    response.pop("risks")
if case in {"adjacent", "ambiguous-adjacent"}:
    response["escalation"] = {"next_level": {"low":"medium", "medium":"high", "high":"extra_high", "xhigh":None}[effort],
        "reason":"material ambiguity", "unresolved_difficulty":"ordering remains unresolved", "required_resolution":"compare state traces"}
if case == "skip": response["escalation"]["next_level"] = "high"
if case.startswith("blank-escalation-"):
    response["escalation"] = {"next_level":"medium", "reason":"material ambiguity",
        "unresolved_difficulty":"ordering remains unresolved", "required_resolution":"compare state traces"}
    response["escalation"][case.removeprefix("blank-escalation-")] = " \t "
if case == "terminal": response["escalation"]["next_level"] = "extra_high"
if case == "blank": response["recommendation"] = "  "
if case == "malformed": response.pop("escalation")
if case == "wrong-sandbox": events[1]["payload"]["sandbox_policy"]["type"] = "workspace-write"
if case == "wrong-permission": events[1]["payload"]["permission_profile"]["type"] = "other"
if case == "wrong-provenance": events[0]["payload"]["originator"] = "untrusted"
if case in {"duplicate-child", "ambiguous-adjacent"}: print(json.dumps({"type":"thread.started", "thread_id":child}))
events += [
    {"type":"response_item", "payload":{"type":"message", "role":"user", "content":[{"type":"input_text", "text":prompt}]}},
    {"type":"response_item", "payload":{"type":"message", "role":"assistant", "content":[{"type":"output_text", "text":json.dumps(response)}]}}
]
(sessions / f"rollout-fake-{child}.jsonl").write_text("".join(json.dumps(row)+"\n" for row in events))
if case == "duplicate-response":
    output.write_text(json.dumps(response)[:-1] + ',"risks":"duplicate"}')
else:
    output.write_text(json.dumps(response))
"""

FAKE_OLD_PYTHON = r"""#!{interpreter}
import builtins
import json
import os
import runpy
import sys

sys.version_info = (3, 9, 18, "final", 0)
_real_import = builtins.__import__
def _old_python_import(name, *args, **kwargs):
    if name == "tomllib":
        raise ImportError("No module named 'tomllib' (Python 3.11+ required)")
    return _real_import(name, *args, **kwargs)
builtins.__import__ = _old_python_import

argv = sys.argv[1:]
log = os.environ.get("FAKE_PYTHON_INVOCATIONS")
if log:
    with open(log, "a") as handle:
        handle.write(json.dumps(argv) + "\n")
if argv and argv[0] == "-c":
    sys.argv = argv
    exec(argv[1], {"__name__": "__main__", "__file__": "<string>"})
elif argv and argv[0] == "-":
    sys.argv = argv
    exec(sys.stdin.read(), {"__name__": "__main__", "__file__": "<stdin>"})
elif argv:
    sys.argv = argv
    runpy.run_path(argv[0], run_name="__main__")
"""

FAKE_MKDIR = r"""#!/usr/bin/env python3
import os
import subprocess
import sys
import time
from pathlib import Path

args = sys.argv[1:]

def run_real_mkdir(cmd_args):
    real = "/bin/mkdir" if os.path.exists("/bin/mkdir") else "/usr/bin/mkdir"
    return subprocess.run([real, *cmd_args]).returncode

if "-p" in args or not any("run." in arg for arg in args):
    sys.exit(run_real_mkdir(args))

case = os.environ.get("FAKE_MKDIR_CASE", "passthrough")
target = Path(args[-1])

if case == "collision":
    capture_path = os.environ.get("FAKE_MKDIR_CAPTURE")
    if capture_path:
        Path(capture_path).write_text(str(target), encoding="utf-8")
    target.mkdir(parents=True, exist_ok=True)
    (target / "sentinel.txt").write_text("preserve me", encoding="utf-8")
    sys.exit(run_real_mkdir(args))

elif case == "fail":
    capture_path = os.environ.get("FAKE_MKDIR_CAPTURE")
    if capture_path:
        Path(capture_path).write_text(str(target), encoding="utf-8")
    sys.exit(1)

elif case == "delay":
    ret = run_real_mkdir(args)
    if ret != 0:
        sys.exit(ret)
    ready = os.environ.get("FAKE_MKDIR_READY")
    release = os.environ.get("FAKE_MKDIR_RELEASE")
    if ready:
        Path(ready).write_text("ready", encoding="utf-8")
    if release:
        release_path = Path(release)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if release_path.exists():
                break
            time.sleep(0.01)
    sys.exit(0)

else:
    sys.exit(run_real_mkdir(args))
"""

FAKE_CHMOD = r"""#!/usr/bin/env python3
import os
import subprocess
import sys

args = sys.argv[1:]

def run_real_chmod(cmd_args):
    real = "/bin/chmod" if os.path.exists("/bin/chmod") else "/usr/bin/chmod"
    return subprocess.run([real, *cmd_args]).returncode

case = os.environ.get("FAKE_CHMOD_CASE", "passthrough")
if case == "fail" and any("run." in arg for arg in args):
    sys.exit(1)

sys.exit(run_real_chmod(args))
"""


class AdvisorTransportTestCase(unittest.TestCase):
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
        self.fake_mkdir = self.bin / "mkdir"
        self.fake_mkdir.write_text(FAKE_MKDIR, encoding="utf-8")
        self.fake_mkdir.chmod(0o700)
        self.fake_chmod = self.bin / "chmod"
        self.fake_chmod.write_text(FAKE_CHMOD, encoding="utf-8")
        self.fake_chmod.chmod(0o700)
        self.invocations = self.root / "invocations.json"
        self.env = {
            **os.environ,
            "CODEX_HOME": str(self.home),
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FAKE_INVOCATIONS": str(self.invocations),
            "ADVISOR_LIVE_CONFIG": str(self.live_config_path),
            "ADVISOR_CODEX_BIN": str(self.fake),
            "CODEX_THREAD_ID": PARENT,
            "ADVISOR_LEDGER_DIR": str(self.root / "ledger"),
            "ADVISOR_PROJECT_ROOT": str(ROOT.parents[1]),
            "ADVISOR_ISSUE_ID": "direct-fixture",
        }
        initialized = subprocess.run([sys.executable, str(self.plugin_root / "scripts/advisor_ledger.py"),
                                      "--ledger-dir", str(self.root / "ledger"), "init"],
                                     env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(initialized.returncode, 0, initialized.stderr + initialized.stdout)
        self.fixture_packets = {}
        self.last_issue = "direct-fixture"
        self.paths = config.state_paths(self.home)
        sessions = self.home / "sessions" / "fixture"
        sessions.mkdir(parents=True)
        rows = [{"type":"session_meta", "payload":{"id":PARENT,"agent_role":"root"}},
                {"type":"turn_context", "payload":{"sandbox_policy":{"type":"workspace-write"},"permission_profile":{"type":"managed"}}}]
        (sessions / f"rollout-fake-{PARENT}.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @contextmanager
    def live_config(self, standard: dict[str, str], specialist: dict[str, str]):
        """Edit only this test's private plugin copy."""
        self.live_config_path.write_text(
            "[standard]\n"
            f'model = "{standard["model"]}"\n'
            f'effort = "{standard["effort"]}"\n\n'
            "[specialist]\n"
            f'model = "{specialist["model"]}"\n'
            f'effort = "{specialist["effort"]}"\n',
            encoding="utf-8",
        )
        yield self.live_config_path

    def run_transport(
        self, *arguments: str, case: str = "valid", env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        # Separate scenarios carry explicit distinct evidence, not erased quotas.
        # Continuations keep their original issue and exact packet.
        if "--previous-result" in arguments:
            prior = json.loads(Path(arguments[arguments.index("--previous-result") + 1]).read_text())
            binding = prior.get("ledger", {}) if isinstance(prior, dict) else {}
            issue = binding.get("issue", self.last_issue)
            packet = self.fixture_packets.get(issue, PACKET)
        else:
            issue = "fixture-" + uuid.uuid4().hex
            packet = PACKET.replace("evidence\n", f"evidence scenario {case} execution {issue}\n")
            self.fixture_packets[issue] = packet
            self.last_issue = issue
        return subprocess.run(
            [
                "/bin/sh",
                str(self.transport),
                *arguments,
                "--parent-thread",
                PARENT,
                "--sessions-dir",
                str(self.home / "sessions"),
            ],
            input=packet,
            text=True,
            capture_output=True,
            check=False,
            env={**self.env, "FAKE_CASE": case, "ADVISOR_ISSUE_ID": issue, **(env or {})},
            timeout=20,
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
