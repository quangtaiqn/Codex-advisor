#!/usr/bin/env python3
"""Launcher admission: verify one adjacent transition against persisted runtime.

No checkpoint ledger, consumed-receipt storage, retries, or inference lives here.
The primary owns the in-session level budget; durable replay prevention is phase B.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from advisor_acceptance import verify_acceptance
from advisor_settings import ROLES, RUNTIME_EFFORTS, normalize_level
from advisor_state import (ACTIVE_MODEL, TRANSPORT_CONTRACT_VERSION, ConfigError,
                           _duplicate_key, _run_bounded_output, validate_response, resolve_runtime)


def bounded_file(path: Path) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1_000_000:
                raise ConfigError("admission evidence is not a bounded regular file")
            data = bytearray()
            while len(data) <= 1_000_000:
                chunk = os.read(fd, min(16384, 1_000_001 - len(data)))
                if not chunk:
                    return bytes(data)
                data.extend(chunk)
            raise ConfigError("admission evidence exceeds byte limit")
        finally:
            os.close(fd)
    except OSError as exc:
        raise ConfigError("admission evidence unavailable or unsafe") from exc


def parent_evidence(parent: str, sessions: str) -> dict[str, Any]:
    current = os.environ.get("CODEX_THREAD_ID")
    if current and current != parent:
        raise ConfigError("parent thread differs from current session")
    inspector = Path(__file__).with_name("inspect-parent-runtime.sh")
    code, output = _run_bounded_output(
        ["env", "CODEX_THREAD_ID=" + parent, "sh", str(inspector), "--sessions-dir", sessions],
        timeout_seconds=3, max_bytes=10000)
    result = json.loads(output, object_pairs_hook=_duplicate_key)
    if code or result.get("status") != "available" or result.get("thread_id") != parent:
        raise ConfigError("parent runtime unavailable")
    return result


def authorize(level: str, receipt_path: Path, packet: Path, parent: str,
              sessions: str, source_revision: str) -> dict[str, Any]:
    level = normalize_level(level)
    receipt = json.loads(bounded_file(receipt_path), object_pairs_hook=_duplicate_key)
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != 3
            or receipt.get("status") != "completed" or receipt.get("outcome") != "accepted"):
        raise ConfigError("previous result is not an accepted receipt")
    if receipt.get("runtime_source") != resolve_runtime(sessions_directory=sessions):
        raise ConfigError("previous transport source mismatch")
    selection = receipt.get("selection", {})
    if not isinstance(selection, dict):
        raise ConfigError("previous selection must be an object")
    previous_level = selection.get("level")
    if not isinstance(previous_level, str) or previous_level not in RUNTIME_EFFORTS or previous_level == "extra_high":
        raise ConfigError("invalid or terminal previous level")
    if (selection.get("tier") != "advisor" or selection.get("model") != ACTIVE_MODEL
            or selection.get("effort") != RUNTIME_EFFORTS[previous_level]
            or selection.get("role") not in ROLES
            or selection.get("transport_contract_version") != TRANSPORT_CONTRACT_VERSION
            or selection.get("source_revision") != source_revision):
        raise ConfigError("previous selection/contract/policy mismatch")
    response = receipt.get("advisor_response")
    if validate_response(previous_level, response)["next_level"] != level:
        raise ConfigError("previous response did not request this adjacent level; stop when sufficient")
    if receipt.get("escalation") != response["escalation"]:
        raise ConfigError("receipt escalation mismatch")
    attempts = receipt.get("attempts")
    if (not isinstance(attempts, list) or len(attempts) != 1
            or not isinstance(attempts[0], dict) or attempts[0].get("number") != 1 or attempts[0].get("outcome") != "accepted"):
        raise ConfigError("previous attempt is not one accepted child")
    digest = hashlib.sha256(bounded_file(packet)).hexdigest()
    if receipt.get("packet_identity") != {"sha256": digest}:
        raise ConfigError("previous packet identity mismatch")
    runtime = receipt.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ConfigError("previous runtime must be an object")
    child = runtime.get("thread_id")
    role = selection["role"]
    if (not isinstance(child, str) or child == parent or runtime.get("parent_thread_id") != parent
            or runtime.get("agent_role") != role):
        raise ConfigError("previous parent/child/role mismatch")
    inspector = Path(__file__).with_name("inspect-agent-runtime.sh")
    code, output = _run_bounded_output(
        ["sh", str(inspector), "--sessions-dir", sessions, "--expected-role", role,
         "--expected-model", ACTIVE_MODEL, "--expected-effort", RUNTIME_EFFORTS[previous_level],
         "--expected-parent", parent, child], timeout_seconds=3, max_bytes=10000)
    inspected = json.loads(output, object_pairs_hook=_duplicate_key)
    if code or runtime != inspected:
        raise ConfigError("previous persisted runtime mismatch")
    pe = parent_evidence(parent, sessions)
    if runtime["permission_profile_type"] != pe["permission_profile_type"]:
        raise ConfigError("previous managed permission provenance mismatch")
    matches = list(Path(sessions).rglob("rollout-*-" + child + ".jsonl"))
    if len(matches) != 1:
        raise ConfigError("ambiguous previous child")
    rows = [json.loads(line, object_pairs_hook=_duplicate_key) for line in bounded_file(matches[0]).splitlines() if line.strip()]
    def texts(message_role: str) -> list[str]:
        result = []
        for row in rows:
            p = row.get("payload", {})
            if row.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == message_role:
                result.append("".join(c.get("text", "") for c in p.get("content", []) if c.get("type") in {"input_text", "output_text"}))
        return result
    users, assistants = texts("user"), texts("assistant")
    if len(users) != 1 or not assistants:
        raise ConfigError("previous packet/response runtime evidence missing")
    prompt = users[0]
    expected_prefix = f"You are {role}, a consultation-only technical advisor.\n"
    if not prompt.startswith(expected_prefix) or f"POLICY LEVEL: {previous_level}\n" not in prompt:
        raise ConfigError("previous runtime role/level mismatch")
    start, end = "BEGIN ADVISOR PACKET\n", "END ADVISOR PACKET\n"
    if prompt.count(start) != 1 or prompt.count(end) != 1:
        raise ConfigError("previous runtime packet boundary mismatch")
    original = prompt.split(start, 1)[1].split(end, 1)[0]
    if hashlib.sha256(original.encode()).hexdigest() != digest:
        raise ConfigError("previous runtime packet identity mismatch")
    observed_response = json.loads(assistants[-1], object_pairs_hook=_duplicate_key)
    validate_response(previous_level, observed_response)
    if observed_response != response:
        raise ConfigError("previous receipt response differs from persisted response")
    verify_acceptance(receipt)
    return {"status": "ok", "previous_response": response, "packet_digest": digest, "previous_child": child}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", required=True)
    parser.add_argument("--sessions-dir", required=True)
    parser.add_argument("--level")
    parser.add_argument("--previous-result", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    try:
        if args.previous_result:
            if not args.level or args.packet is None or not args.source_revision:
                raise ConfigError("incomplete escalation admission")
            result = authorize(args.level, args.previous_result, args.packet, args.parent,
                               args.sessions_dir, args.source_revision)
        else:
            result = {"status": "ok", "parent": parent_evidence(args.parent, args.sessions_dir)}
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except (ConfigError, OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc)}, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
