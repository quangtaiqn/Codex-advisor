#!/usr/bin/env python3
"""Launcher admission: verify one adjacent transition against persisted runtime.

Runtime acceptance owner; durable quota/transfer state lives in advisor_ledger.
No retries or inference live here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
              sessions: str, source_revision: str, *, verify_only: bool = False,
              allow_legacy: bool = False) -> dict[str, Any]:
    level = normalize_level(level)
    receipt = json.loads(bounded_file(receipt_path), object_pairs_hook=_duplicate_key)
    expected_version = 3 if allow_legacy else 4
    expected_contract = "1.5" if allow_legacy else TRANSPORT_CONTRACT_VERSION
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != expected_version
            or receipt.get("status") != "completed" or receipt.get("outcome") != "accepted"):
        raise ConfigError("previous result is not an accepted receipt")
    if receipt.get("runtime_source") != resolve_runtime(sessions_directory=sessions):
        raise ConfigError("previous transport source mismatch")
    selection = receipt.get("selection", {})
    if not isinstance(selection, dict):
        raise ConfigError("previous selection must be an object")
    previous_level = selection.get("level")
    if not isinstance(previous_level, str) or previous_level not in RUNTIME_EFFORTS or (previous_level == "extra_high" and not verify_only):
        raise ConfigError("invalid or terminal previous level")
    if (selection.get("tier") != "advisor" or selection.get("model") != ACTIVE_MODEL
            or selection.get("effort") != RUNTIME_EFFORTS[previous_level]
            or selection.get("role") not in ROLES
            or selection.get("transport_contract_version") != expected_contract
            or selection.get("source_revision") != source_revision):
        raise ConfigError("previous selection/contract/policy mismatch")
    response = receipt.get("advisor_response")
    requested = validate_response(previous_level, response)["next_level"]
    if not verify_only and requested != level:
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
    contexts = [row["payload"] for row in rows if row.get("type") == "turn_context"]
    session_cwd = next(row["payload"].get("cwd") for row in rows if row.get("type") == "session_meta")
    def native_turn(metadata: Any) -> bool:
        if not isinstance(metadata, dict) or not isinstance(session_cwd, str):
            return False
        turn = metadata.get("turn_id")
        return (isinstance(turn, str) and bool(turn)
                and any(c.get("turn_id") == turn and c.get("cwd") == session_cwd for c in contexts))

    def consultation(payload: dict[str, Any]) -> bool:
        content = payload.get("content")
        if (not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict)
                or content[0].get("type") != "input_text" or not isinstance(content[0].get("text"), str)):
            return False
        if "internal_chat_message_metadata_passthrough" not in payload:
            return True  # Legacy untyped prompts have a distinct compatibility branch.
        metadata = payload["internal_chat_message_metadata_passthrough"]
        return native_turn(metadata) and metadata.get("content_item_kinds") == ["user.text"]

    def bootstrap(payload: dict[str, Any]) -> bool:
        metadata = payload.get("internal_chat_message_metadata_passthrough")
        content = payload.get("content")
        if not native_turn(metadata) or not isinstance(content, list):
            return False
        kinds = metadata.get("content_item_kinds")
        if kinds == ["environments.environment_context"] and len(content) == 1:
            pass
        elif kinds == ["agents_md.instructions", "environments.environment_context"] and len(content) == 2:
            text = content[0].get("text") if isinstance(content[0], dict) else None
            if not isinstance(text, str) or not re.fullmatch(
                    r"# AGENTS\.md instructions\n\n<INSTRUCTIONS>\n(?:(?!</?INSTRUCTIONS\b).)*\n</INSTRUCTIONS>\s*", text, re.S):
                return False
        else:
            return False
        if not all(isinstance(c, dict) and c.get("type") == "input_text" and isinstance(c.get("text"), str)
                   and "BEGIN ADVISOR PACKET" not in c["text"] and "END ADVISOR PACKET" not in c["text"] for c in content):
            return False
        environment = re.fullmatch(
            r"<environment_context>\s*<cwd>([^<>]*)</cwd>(?:(?!</?(?:environment_context|cwd)\b|<!--|-->).)*</environment_context>\s*",
            content[-1]["text"], re.S)
        return environment is not None and environment[1] == session_cwd

    def texts(message_role: str) -> list[str]:
        result = []
        bootstrap_seen = False
        for row in rows:
            p = row.get("payload", {})
            if row.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == message_role:
                if message_role == "user" and bootstrap(p):
                    if bootstrap_seen or result:
                        raise ConfigError("previous bootstrap context order mismatch")
                    bootstrap_seen = True
                    continue
                if message_role == "user" and not consultation(p):
                    raise ConfigError("previous typed user context or prompt mismatch")
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
    parser.add_argument("--ledger-dir")
    parser.add_argument("--project-root")
    parser.add_argument("--issue-id")
    args = parser.parse_args()
    try:
        if args.previous_result:
            if not args.level or args.packet is None or not args.source_revision:
                raise ConfigError("incomplete escalation admission")
            receipt_parent = args.parent
            if args.ledger_dir:
                preliminary = json.loads(bounded_file(args.previous_result), object_pairs_hook=_duplicate_key)
                runtime = preliminary.get("runtime") if isinstance(preliminary, dict) else None
                if isinstance(runtime, dict) and runtime.get("parent_thread_id") != args.parent:
                    from advisor_ledger import verify_transfer
                    from advisor_ledger_store import Store
                    args.receipt = args.previous_result
                    args.issue = args.issue_id
                    try:
                        receipt_parent = verify_transfer(Store(args.ledger_dir), args)["receipt_parent"]
                    except ConfigError as exc:
                        raise ConfigError("previous parent/child/role mismatch; transfer proof invalid") from exc
                    parent_evidence(args.parent, args.sessions_dir)
            prior_parent = os.environ.get("CODEX_THREAD_ID")
            os.environ["CODEX_THREAD_ID"] = receipt_parent
            try:
                result = authorize(args.level, args.previous_result, args.packet, receipt_parent,
                               args.sessions_dir, args.source_revision)
            finally:
                if prior_parent is None:
                    os.environ.pop("CODEX_THREAD_ID", None)
                else:
                    os.environ["CODEX_THREAD_ID"] = prior_parent
        else:
            result = {"status": "ok", "parent": parent_evidence(args.parent, args.sessions_dir)}
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except (ConfigError, OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc)}, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
