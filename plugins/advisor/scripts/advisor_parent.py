"""Bounded, strict JSONL parent inspection; never publish session contents."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import time
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_RECORDS = 100000
MAX_ENTRIES = 100000
PARSER_SECONDS = 2.5
THREAD = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


class ParentUnavailable(ValueError):
    """Internal reason is diagnostic only; the CLI always redacts it."""


def check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise ParentUnavailable("deadline")


def duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ParentUnavailable("json_duplicate")
        value[key] = item
    return value


def nonfinite(_value):
    raise ParentUnavailable("json_nonfinite")


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def select_rollout(root, thread, deadline):
    selected = None
    entries = 0

    def visit(fd, directory):
        nonlocal selected, entries
        # fwalk ignores some traversal errors and buffers whole directories.
        # Inspect each entry; incomplete enumeration cannot prove uniqueness.
        with os.scandir(fd) as items:
            iterator = iter(items)
            while True:
                pending = []
                try:
                    # Bound each directory batch and the shared worker pool.
                    for _ in range(16):
                        try:
                            entry = next(iterator)
                        except StopIteration:
                            break
                        check_deadline(deadline)
                        entries += 1
                        if entries > MAX_ENTRIES:
                            raise ParentUnavailable("entry_bound")
                        pending.append((entry, metadata.submit(entry.stat, follow_symlinks=False)))
                    if not pending:
                        break
                    for entry, future in pending:
                        check_deadline(deadline)
                        info = future.result()
                        check_deadline(deadline)
                        name = entry.name
                        if name.startswith("rollout-") and name.endswith(
                            "-" + thread + ".jsonl"
                        ):
                            if selected is not None:
                                raise ParentUnavailable("ambiguous_rollout")
                            selected = (os.dup(fd), name, Path(directory) / name)
                        if stat.S_ISDIR(info.st_mode):
                            child = os.open(
                                name,
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=fd,
                            )
                            try:
                                opened = os.fstat(child)
                                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                                    raise ParentUnavailable("directory_changed")
                                visit(child, Path(directory) / name)
                            finally:
                                os.close(child)
                finally:
                    # Finish metadata reads before this directory fd can close.
                    for _entry, future in pending:
                        future.cancel()
                    wait([future for _entry, future in pending])

    try:
        with ThreadPoolExecutor(max_workers=4) as metadata:
            visit(root, Path("."))
        if selected is None:
            raise ParentUnavailable("missing_rollout")
        return selected
    except BaseException:
        if selected is not None:
            os.close(selected[0])
        raise


def recheck_path(root, relative, expected):
    """Reopen each component without following a replacement directory link."""
    current = os.dup(root)
    try:
        for part in relative.parts[:-1]:
            nxt = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=current,
            )
            os.close(current)
            current = nxt
        linked = os.stat(relative.name, dir_fd=current, follow_symlinks=False)
        if not stat.S_ISREG(linked.st_mode) or fingerprint(linked) != expected:
            raise ParentUnavailable("rollout_changed")
    finally:
        os.close(current)


def read_records(fd, thread, deadline):
    metadata = 0
    contexts = 0
    sandbox = permission = None
    total = count = 0
    # One bounded record in RAM, even when irrelevant message payloads are large.
    with os.fdopen(fd, "rb", closefd=False) as stream:
        while True:
            check_deadline(deadline)
            raw = stream.readline(MAX_LINE_BYTES + 1)
            if not raw:
                break
            total += len(raw)
            count += 1
            if (
                total > MAX_FILE_BYTES
                or len(raw) > MAX_LINE_BYTES
                or count > MAX_RECORDS
            ):
                raise ParentUnavailable("record_bound")
            if not raw.endswith(b"\n"):
                raise ParentUnavailable("unpublished_tail")
            if not raw.strip(b" \t\r\n"):
                continue
            row = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=duplicate_keys,
                parse_constant=nonfinite,
            )
            if not isinstance(row, dict):
                raise ParentUnavailable("record_schema")
            kind = row.get("type")
            if kind not in ("session_meta", "turn_context"):
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                raise ParentUnavailable("metadata_schema")
            if kind == "session_meta":
                metadata += 1
                if metadata != 1 or payload.get("id") != thread:
                    raise ParentUnavailable("metadata_identity")
            else:
                contexts += 1
                policy = payload.get("sandbox_policy")
                profile = payload.get("permission_profile")
                if not isinstance(policy, dict) or not isinstance(profile, dict):
                    raise ParentUnavailable("provenance_schema")
                box, perm = policy.get("type"), profile.get("type")
                if (
                    box not in ("read-only", "workspace-write")
                    or not isinstance(perm, str)
                    or not perm
                ):
                    raise ParentUnavailable("unsafe_provenance")
                if sandbox is not None and (sandbox != box or permission != perm):
                    raise ParentUnavailable("mixed_provenance")
                sandbox, permission = box, perm
    check_deadline(deadline)
    if metadata != 1 or not contexts:
        raise ParentUnavailable("missing_metadata")
    return {
        "status": "available",
        "thread_id": thread,
        "sandbox_policy_type": sandbox,
        "permission_profile_type": permission,
    }


def inspect_parent(sessions, thread):
    if not isinstance(thread, str) or not THREAD.fullmatch(thread):
        raise ParentUnavailable("thread_identity")
    deadline = time.monotonic() + PARSER_SECONDS
    root = os.open(
        sessions, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    directory = fd = None
    try:
        info = os.fstat(root)
        if info.st_uid not in (0, os.getuid()):
            raise ParentUnavailable("sessions_owner")
        root_identity = (info.st_dev, info.st_ino)
        directory, name, relative = select_rollout(root, thread, deadline)
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=directory,
        )
        initial = os.fstat(fd)
        if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
            raise ParentUnavailable("rollout_link_or_type")
        if initial.st_uid != os.getuid():
            raise ParentUnavailable("rollout_owner")
        if initial.st_size > MAX_FILE_BYTES:
            raise ParentUnavailable("file_bound")
        expected = fingerprint(initial)
        result = read_records(fd, thread, deadline)
        if fingerprint(os.fstat(fd)) != expected:
            raise ParentUnavailable("rollout_changed")
        recheck_path(root, relative, expected)
        linked = os.stat(sessions, follow_symlinks=False)
        if (
            not stat.S_ISDIR(linked.st_mode)
            or (linked.st_dev, linked.st_ino) != root_identity
        ):
            raise ParentUnavailable("sessions_changed")
        # A new same-ID file during reading cannot silently replace uniqueness proof.
        again, _name, path = select_rollout(root, thread, deadline)
        os.close(again)
        if path != relative:
            raise ParentUnavailable("rollout_changed")
        if fingerprint(os.fstat(fd)) != expected:
            raise ParentUnavailable("rollout_changed")
        recheck_path(root, relative, expected)
        linked = os.stat(sessions, follow_symlinks=False)
        if (
            not stat.S_ISDIR(linked.st_mode)
            or (linked.st_dev, linked.st_ino) != root_identity
        ):
            raise ParentUnavailable("sessions_changed")
        check_deadline(deadline)
        return result
    finally:
        if fd is not None:
            os.close(fd)
        if directory is not None:
            os.close(directory)
        os.close(root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions-dir", required=True)
    parser.add_argument("--thread-id", required=True)
    args = parser.parse_args()
    try:
        result = inspect_parent(args.sessions_dir, args.thread_id)
    except (
        ParentUnavailable,
        OSError,
        ValueError,
        TypeError,
        RecursionError,
        AttributeError,
    ):
        result = {
            "status": "unavailable",
            "reason_type": "parent_runtime_unavailable",
            "redacted": True,
        }
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
