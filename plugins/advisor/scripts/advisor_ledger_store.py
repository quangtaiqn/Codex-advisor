"""Single owner-only, lock-serialized durable registry. Never auto-init or repair."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from advisor_state import ConfigError, _duplicate_key

VERSION = 1
MAX_BYTES = 8 * 1024 * 1024
MAX_ISSUES = 1024


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def process_identity(pid):
    """A PID alone is never ownership evidence; unavailable identity fails closed."""
    try:
        if Path(f"/proc/{int(pid)}").stat().st_uid != os.getuid():
            return None
        text = Path(f"/proc/{int(pid)}/stat").read_text()
        start = text[text.rindex(")") + 2 :].split()[19]
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return {"pid": int(pid), "start": start, "boot": boot}
    except (OSError, ValueError, IndexError):
        return None


class Store:
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or ".." in self.root.parts:
            raise ConfigError("ledger root must be an absolute private Linux path")

    def directory(self, create=False):
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            parts = self.root.parts[1:]
            for i, part in enumerate(parts):
                if create and i == len(parts) - 1:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                nxt = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=fd,
                )
                info = os.fstat(nxt)
                if i == len(parts) - 1:
                    safe = (
                        info.st_uid == os.getuid()
                        and stat.S_IMODE(info.st_mode) == 0o700
                    )
                else:
                    safe = info.st_uid in (0, os.getuid()) and (
                        not info.st_mode & 0o022 or bool(info.st_mode & stat.S_ISVTX)
                    )
                if not safe:
                    os.close(nxt)
                    raise ConfigError("ledger directory owner/mode is unsafe")
                os.close(fd)
                fd = nxt
            fs = subprocess.run(
                ["stat", "-f", "-c", "%T", f"/proc/self/fd/{fd}"],
                pass_fds=(fd,),
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if fs.returncode or fs.stdout.strip() not in (
                "ext2/ext3",
                "btrfs",
                "xfs",
                "zfs",
            ):
                raise ConfigError(
                    "ledger requires persistent Linux storage; tmpfs/DrvFS is unsupported"
                )
            return fd, fs.stdout.strip()
        except BaseException:
            os.close(fd)
            raise

    def file(self, directory, name, create=False):
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        fd = os.open(name, flags, 0o600, dir_fd=directory)
        info = os.fstat(fd)
        linked = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)
        ):
            os.close(fd)
            raise ConfigError("ledger file owner/mode/link is unsafe")
        return fd

    @contextmanager
    def locked(self, init=False):
        directory, fs = self.directory(create=init)
        lock = None
        try:
            if init:
                if os.listdir(directory):
                    raise ConfigError(
                        "ledger legacy/partial/initialized state; preserve entries and never reset"
                    )
                try:
                    lock = self.file(directory, "lock", create=True)
                    os.fsync(lock)
                    os.fsync(directory)
                except FileExistsError:
                    raise ConfigError(
                        "ledger initialization already claimed; preserve partial state"
                    ) from None
            else:
                lock = self.file(directory, "lock")
            deadline = time.monotonic() + 5
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ConfigError("ledger lock contention deadline")
                    time.sleep(0.02)
            info = os.fstat(lock)
            linked = os.stat("lock", dir_fd=directory, follow_symlinks=False)
            if (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino):
                raise ConfigError("ledger lock inode changed")
            yield directory, fs
        finally:
            if lock is not None:
                os.close(lock)
            os.close(directory)

    def read(self, directory, name):
        fd = self.file(directory, name)
        try:
            if os.fstat(fd).st_size > MAX_BYTES:
                raise ConfigError("ledger file exceeded bounds")
            data = bytearray()
            while block := os.read(fd, 65536):
                data.extend(block)
                if len(data) > MAX_BYTES:
                    raise ConfigError("ledger file exceeded bounds")
            value = json.loads(data, object_pairs_hook=_duplicate_key)
            if (
                not isinstance(value, dict)
                or set(value) != {"body", "sha256"}
                or digest(value["body"]) != value["sha256"]
            ):
                raise ConfigError("ledger integrity checksum mismatch")
            if not isinstance(value["body"], dict):
                raise ConfigError("ledger body schema must be an object")
            return value["body"]
        finally:
            os.close(fd)

    def write(self, directory, name, body):
        data = encoded({"body": body, "sha256": digest(body)})
        if len(data) > MAX_BYTES:
            raise ConfigError(
                "ledger registry full; consumed identities cannot be pruned"
            )
        temporary = ".write-" + uuid.uuid4().hex
        fd = self.file(directory, temporary, create=True)
        try:
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise ConfigError("ledger durable write unavailable")
                view = view[count:]
            os.fsync(fd)
            # Check any old destination without following links before replacement.
            try:
                existing = self.file(directory, name)
                os.close(existing)
            except FileNotFoundError:
                pass
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            os.close(fd)
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass

    def initialize(self):
        with self.locked(init=True) as (directory, _filesystem):
            names = set(os.listdir(directory))
            if names != {"lock"}:
                raise ConfigError(
                    "ledger already initialized or legacy/partial state; never reset"
                )
            epoch = {
                "version": VERSION,
                "namespace": uuid.uuid4().hex,
                "uid": os.getuid(),
            }
            self.write(directory, "epoch.json", epoch)
            self.write(
                directory,
                "registry.json",
                {**epoch, "revision": 0, "issues": {}, "canonical": {}},
            )
            return epoch

    @contextmanager
    def transaction(self, mutate=False):
        with self.locked() as (directory, _filesystem):
            epoch = self.read(directory, "epoch.json")
            body = self.read(directory, "registry.json")
            if (
                not isinstance(epoch, dict)
                or set(epoch) != {"version", "namespace", "uid"}
                or type(epoch.get("version")) is not int
                or type(epoch.get("uid")) is not int
                or not isinstance(epoch.get("namespace"), str)
                or len(epoch["namespace"]) != 32
                or epoch.get("version") != VERSION
                or epoch.get("uid") != os.getuid()
                or any(body.get(k) != v for k, v in epoch.items())
                or set(body) != {*epoch, "revision", "issues", "canonical"}
                or type(body.get("revision")) is not int
                or body["revision"] < 0
                or not isinstance(body.get("issues"), dict)
                or not isinstance(body.get("canonical"), dict)
                or len(body["issues"]) > MAX_ISSUES
            ):
                raise ConfigError(
                    "ledger schema/version/epoch mismatch; migration requires explicit review"
                )
            for key, issue in body["issues"].items():
                if (
                    not isinstance(issue, dict)
                    or key != issue.get("key")
                    or not isinstance(issue.get("executions"), dict)
                    or body["canonical"].get(issue.get("canonical_key")) != key
                ):
                    raise ConfigError("ledger issue/index schema mismatch")
                levels = ("low", "medium", "high", "extra_high")
                executions = issue["executions"]
                if list(executions) != [
                    level for level in levels if level in executions
                ] and set(executions) - set(levels):
                    raise ConfigError("ledger unknown level")
                used = [level for level in levels if level in executions]
                if (
                    used != list(levels[: len(used)])
                    or type(issue.get("closed")) is not bool
                ):
                    raise ConfigError("ledger nonadjacent consumed-level schema")
                for level, record in executions.items():
                    if (
                        not isinstance(record, dict)
                        or record.get("state")
                        not in (
                            "reserved",
                            "started",
                            "accepted",
                            "failed",
                            "cancelled",
                            "timed_out",
                            "unknown",
                        )
                        or not isinstance(record.get("id"), str)
                        or not isinstance(record.get("owner"), dict)
                        or type(record.get("consumed")) is not bool
                    ):
                        raise ConfigError("ledger execution schema mismatch")
                    if record["state"] == "accepted" and (
                        not isinstance(record.get("receipt_digest"), str)
                        or record.get("next")
                        != (
                            levels[levels.index(level) + 1]
                            if level != "extra_high"
                            else None
                        )
                        and record.get("next") is not None
                    ):
                        raise ConfigError("ledger accepted transition schema mismatch")
            if len(body["canonical"]) != len(body["issues"]):
                raise ConfigError("ledger canonical index cardinality mismatch")
            before = digest(body)
            yield body
            if digest(body) != before:
                if not mutate:
                    raise ConfigError("read-only ledger transaction attempted mutation")
                body["revision"] += 1
                self.write(directory, "registry.json", body)
