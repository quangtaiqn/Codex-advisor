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
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_nlink)


def windows_path(path):
    """Translate only a real 64-bit 9p DrvFS drive, not a guessed /mnt path."""
    import struct
    if struct.calcsize("P") != 8:
        raise ParentUnavailable("native_platform")
    path = Path(os.path.abspath(path))
    selected = None
    with open("/proc/self/mountinfo", encoding="utf-8") as mounts:
        for line in mounts:
            left, right = line.rstrip().split(" - ", 1)
            fields, filesystem = left.split(), right.split()
            mount = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4]))
            if path.is_relative_to(mount) and (selected is None or len(mount.parts) > len(selected[0].parts)):
                selected = (mount, fields, filesystem)
    if selected is None:
        raise ParentUnavailable("native_mount")
    mount, fields, filesystem = selected
    drive = re.search(r"(?:^|[,;])aname=drvfs;path=([A-Z]):\\;", filesystem[2])
    if fields[3] != "/" or filesystem[0] != "9p" or drive is None:
        raise ParentUnavailable("native_mount")
    return drive[1] + ":\\" + "\\".join(path.relative_to(mount).parts)


class NativeParent:
    """Keep native handles alive while the POSIX reader proves provenance."""

    def __init__(self, sessions, relative, deadline):
        # Linux single-link callers do not need Windows process machinery.
        import base64
        import selectors
        import subprocess

        self.process = None
        self.deadline = deadline
        self.buffer = bytearray()
        self.selector = selectors.DefaultSelector()
        try:
            helper = Path(__file__).with_name("windows-parent-metadata.ps1")
            helper_info = helper.lstat()
            if not stat.S_ISREG(helper_info.st_mode) or helper_info.st_size > 65536:
                raise ParentUnavailable("native_helper")
            script = windows_path(helper)
            # Only the trusted helper path is encoded as code. User paths use stdin.
            encoded_path = base64.b64encode(script.encode("utf-8")).decode("ascii")
            bootstrap = "& ([scriptblock]::Create([IO.File]::ReadAllText([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded_path + "')),[Text.Encoding]::UTF8)))"
            encoded = base64.b64encode(bootstrap.encode("utf-16le")).decode("ascii")
            request = {"root": windows_path(sessions),
                       "path": windows_path(Path(sessions) / relative)}
            check_deadline(deadline)
            self.process = subprocess.Popen(
                ["/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
                 "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            os.set_blocking(self.process.stdout.fileno(), False)
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            self.process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
            self.process.stdin.flush()
            # Startup can overlap the authoritative namespace scan. The first
            # native snapshot must still be checked before any JSONL is parsed.
            self.initial = None
        except BaseException:
            self.close()
            raise

    def begin(self, root_info, file_info):
        self.initial = self.snapshot(root_info, file_info)

    def snapshot(self, root_info, file_info):
        while b"\n" not in self.buffer:
            check_deadline(self.deadline)
            if not self.selector.select(max(0, self.deadline - time.monotonic())):
                raise ParentUnavailable("native_deadline")
            chunk = os.read(self.process.stdout.fileno(), 8192)
            if not chunk or len(self.buffer) + len(chunk) > 8192:
                raise ParentUnavailable("native_output")
            self.buffer.extend(chunk)
        raw, _, self.buffer = self.buffer.partition(b"\n")
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=duplicate_keys,
                           parse_constant=nonfinite)
        if not isinstance(value, dict) or value.get("schema") != 1 or value.get("ok") is not True:
            raise ParentUnavailable("native_proof")
        if set(value) != {"schema", "ok", "file_id", "root_id", "volume", "size", "mtime_ns",
                          "change_time", "file_security", "root_security", "links", "aliases", "ntfs", "local"}:
            raise ParentUnavailable("native_schema")
        for field in ("file_id", "root_id", "volume", "size", "mtime_ns", "change_time"):
            if not isinstance(value.get(field), str) or not re.fullmatch(r"[0-9]{1,20}", value[field]):
                raise ParentUnavailable("native_schema")
        for field in ("file_security", "root_security"):
            if not isinstance(value.get(field), str) or not re.fullmatch(r"[0-9a-f]{64}", value[field]):
                raise ParentUnavailable("native_schema")
        # Microsoft 64-bit 9p maps qid.path to inode with the reserved +2 offset.
        if (int(value["file_id"]) + 2 != file_info.st_ino
                or int(value["root_id"]) + 2 != root_info.st_ino
                or file_info.st_dev != root_info.st_dev
                or int(value["size"]) != file_info.st_size
                or int(value["mtime_ns"]) != file_info.st_mtime_ns
                or value.get("links") != 2 or file_info.st_nlink != 2
                or value.get("aliases") != 2
                or value.get("ntfs") is not True or value.get("local") is not True):
            raise ParentUnavailable("native_identity")
        check_deadline(self.deadline)
        return value

    def recheck(self, root_info, file_info):
        from subprocess import TimeoutExpired

        self.process.stdin.write(b"recheck\n")
        self.process.stdin.flush()
        if self.snapshot(root_info, file_info) != self.initial:
            raise ParentUnavailable("native_changed")
        self.process.stdin.close()
        try:
            code = self.process.wait(timeout=max(0.001, self.deadline - time.monotonic()))
        except TimeoutExpired as exc:
            raise ParentUnavailable("native_deadline") from exc
        if code or self.buffer or os.read(self.process.stdout.fileno(), 8192):
            raise ParentUnavailable("native_output")
        check_deadline(self.deadline)

    def close(self):
        self.selector.close()
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()


def prewarm_native(root, sessions, root_info, thread, deadline):
    """Find a possible two-link file without treating this as uniqueness proof.

    Directory entry types make this a cheap hint on DrvFS. Both complete
    metadata scans below still inspect every entry and establish identity.
    """
    # This only skips an optional startup hint on block-device filesystems.
    # A potential DrvFS file still needs the actual mount and native proofs.
    if os.major(root_info.st_dev) != 0:
        return None
    try:
        windows_path(sessions)
    except (ParentUnavailable, OSError, ValueError):
        return None
    entries = 0

    def visit(directory, relative):
        nonlocal entries
        with os.scandir(directory) as items:
            for entry in items:
                check_deadline(deadline)
                entries += 1
                if entries > MAX_ENTRIES:
                    raise ParentUnavailable("entry_bound")
                path = relative / entry.name
                if entry.name.startswith("rollout-") and entry.name.endswith("-" + thread + ".jsonl"):
                    fd = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                                 dir_fd=directory)
                    try:
                        info = os.fstat(fd)
                        if stat.S_ISREG(info.st_mode) and info.st_nlink == 2 and info.st_uid == os.getuid():
                            native = NativeParent(sessions, path, deadline)
                            return fd, path, native
                    except BaseException:
                        os.close(fd)
                        raise
                    os.close(fd)
                    return None
                if entry.is_dir(follow_symlinks=False):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                    dir_fd=directory)
                    try:
                        found = visit(child, path)
                        if found is not None:
                            return found
                    finally:
                        os.close(child)
        return None

    return visit(root, Path("."))


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
    directory = fd = native = None
    try:
        info = os.fstat(root)
        if info.st_uid not in (0, os.getuid()):
            raise ParentUnavailable("sessions_owner")
        root_identity = (info.st_dev, info.st_ino)
        warmed = prewarm_native(root, sessions, info, thread, deadline)
        if warmed is not None:
            fd, warmed_path, native = warmed
        directory, name, relative = select_rollout(root, thread, deadline)
        if warmed is not None:
            if warmed_path != relative:
                raise ParentUnavailable("rollout_changed")
        else:
            fd = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=directory,
            )
        initial = os.fstat(fd)
        if not stat.S_ISREG(initial.st_mode) or initial.st_nlink not in (1, 2):
            raise ParentUnavailable("rollout_link_or_type")
        if initial.st_uid != os.getuid():
            raise ParentUnavailable("rollout_owner")
        if initial.st_size > MAX_FILE_BYTES:
            raise ParentUnavailable("file_bound")
        expected = fingerprint(initial)
        if initial.st_nlink == 2:
            if native is None:
                native = NativeParent(sessions, relative, deadline)
            native.begin(info, initial)
        elif native is not None:
            raise ParentUnavailable("rollout_changed")
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
        if native is not None:
            native.recheck(os.fstat(root), os.fstat(fd))
            if fingerprint(os.fstat(fd)) != expected:
                raise ParentUnavailable("rollout_changed")
            recheck_path(root, relative, expected)
            linked = os.stat(sessions, follow_symlinks=False)
            if not stat.S_ISDIR(linked.st_mode) or (linked.st_dev, linked.st_ino) != root_identity:
                raise ParentUnavailable("sessions_changed")
        check_deadline(deadline)
        return result
    finally:
        if native is not None:
            native.close()
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
