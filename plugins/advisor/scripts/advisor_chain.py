"""Durable, content-free checkpoint budget for Advisor consultations.

The ledger is deliberately separate from the optional usage journal.  A
persisted reservation is consumed even when the process later becomes
uncertain; reopening a reservation never grants another launch at that level.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

try:  # POSIX runtime; the Windows development host uses the msvcrt fallback.
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None

try:  # pragma: no cover - exercised on Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX has no msvcrt
    msvcrt = None


MODEL = "gpt-6-astra"
LEVELS = ("low", "medium", "high", "extra_high")
RUNTIME_EFFORTS = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "extra_high": "xhigh",
}
NEXT_LEVEL = {
    level: LEVELS[index + 1] if index + 1 < len(LEVELS) else None
    for index, level in enumerate(LEVELS)
}
SCHEMA_VERSION = 1
MAX_STATE_BYTES = 64 * 1024
LOCK_DEADLINE_SECONDS = 5.0
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SELECTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
ENTRY_STATUSES = frozenset(("reserved", "completed", "failed", "uncertain"))
CHAIN_STATUSES = frozenset(("active", "completed", "complete", "uncertain", "blocked"))
FAILURE_CODES = frozenset(
    (
        "launch_failed",
        "runtime_failed",
        "rejected_response",
        "timed_out",
        "cancelled",
        "unknown",
    )
)


class ChainError(ValueError):
    """The ledger is invalid or the requested transition is not authorized."""


class ChainUnavailable(ChainError):
    """The local locking or durable-state backend is unavailable."""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _digest(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
        raise ChainError(f"invalid {label}")
    return value


def checkpoint_digest(checkpoint_key: str) -> str:
    if not isinstance(checkpoint_key, str) or not checkpoint_key.strip():
        raise ChainError("checkpoint key is empty")
    if len(checkpoint_key) > 512:
        raise ChainError("checkpoint key is too long")
    return "sha256:" + hashlib.sha256(checkpoint_key.encode("utf-8")).hexdigest()


def _uuid(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise ChainError(f"invalid {label}")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ChainError(f"invalid {label}") from exc
    if parsed.version != 4:
        raise ChainError(f"invalid {label}")
    return str(parsed)


def _safe_directory(path: Path, *, create: bool) -> None:
    if not path.is_absolute():
        raise ChainError("chain directory must be absolute")
    if create:
        try:
            path.mkdir(mode=0o700, parents=False, exist_ok=True)
        except OSError as exc:
            raise ChainUnavailable("cannot create chain directory") from exc
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ChainUnavailable("chain directory is missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ChainError("chain directory is unsafe")
    if os.name != "nt":
        uid = getattr(os, "getuid", lambda: info.st_uid)()
        if info.st_uid != uid or info.st_mode & 0o077:
            raise ChainError("chain directory is not owner-only")


def _safe_file(path: Path, *, missing_ok: bool = False) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return
        raise ChainUnavailable(f"chain state is missing: {path.name}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ChainError(f"unsafe chain state: {path.name}")
    if os.name != "nt":
        uid = getattr(os, "getuid", lambda: info.st_uid)()
        if info.st_uid != uid or info.st_mode & 0o077:
            raise ChainError(f"chain state is not owner-only: {path.name}")
    if info.st_size > MAX_STATE_BYTES:
        raise ChainError("chain state is too large")


def _duplicate_key(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ChainError("duplicate chain state key")
        result[key] = value
    return result


def _validate_entry(level: str, value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ChainError(f"invalid {level} ledger entry")
    required = {
        "status",
        "attempt_id",
        "model",
        "effort",
        "packet_digest",
        "result_digest",
        "next_level",
        "failure_code",
    }
    if set(value) != required:
        raise ChainError(f"invalid {level} ledger entry keys")
    if value["status"] not in ENTRY_STATUSES:
        raise ChainError(f"invalid {level} ledger status")
    _uuid(value["attempt_id"], label="attempt id")
    if not isinstance(value["model"], str) or not SELECTOR_RE.fullmatch(value["model"]):
        raise ChainError(f"invalid {level} ledger model")
    if value["effort"] not in set(RUNTIME_EFFORTS.values()):
        raise ChainError(f"invalid {level} ledger effort")
    _digest(value["packet_digest"], label="packet digest")
    if value["result_digest"] is not None:
        _digest(value["result_digest"], label="result digest")
    if value["next_level"] is not None and value["next_level"] not in LEVELS:
        raise ChainError(f"invalid {level} next level")
    failure = value["failure_code"]
    if failure is not None and failure not in FAILURE_CODES:
        raise ChainError(f"invalid {level} failure code")
    if value["status"] == "completed" and value["result_digest"] is None:
        raise ChainError(f"completed {level} ledger entry lacks result digest")
    if value["status"] in ("failed", "uncertain") and failure is None:
        raise ChainError(f"terminal {level} ledger entry lacks failure code")
    return dict(value)


def _validate_state(value: Any) -> dict[str, Any]:
    required = {
        "schema_version",
        "checkpoint_key_digest",
        "chain_id",
        "policy_digest",
        "packet_digest",
        "created_at",
        "updated_at",
        "status",
        "implementation_started",
        "next_action",
        "levels",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ChainError("invalid chain state keys")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ChainError("unsupported chain state schema")
    _digest(value["checkpoint_key_digest"], label="checkpoint digest")
    _uuid(value["chain_id"], label="chain id")
    _digest(value["policy_digest"], label="policy digest")
    _digest(value["packet_digest"], label="packet digest")
    if value["status"] not in CHAIN_STATUSES:
        raise ChainError("invalid chain status")
    for name in ("created_at", "updated_at"):
        if not isinstance(value[name], str) or len(value[name]) > 64:
            raise ChainError("invalid chain timestamp")
    if not isinstance(value["implementation_started"], bool):
        raise ChainError("invalid implementation state")
    if not isinstance(value["next_action"], str) or not 0 < len(value["next_action"]) <= 128:
        raise ChainError("invalid chain next action")
    levels = value["levels"]
    if not isinstance(levels, dict) or set(levels) != set(LEVELS):
        raise ChainError("invalid chain levels")
    clean_levels = {
        level: _validate_entry(level, levels[level]) for level in LEVELS
    }
    status_values = [entry["status"] for entry in clean_levels.values() if entry]
    if value["implementation_started"]:
        if any(status == "reserved" for status in status_values):
            raise ChainError("implementation lock cannot have a reserved level")
    return {**value, "levels": clean_levels}


def _default_root(codex_home: str | os.PathLike[str] | None = None) -> Path:
    home = Path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    if not home.is_absolute():
        raise ChainError("CODEX_HOME must be absolute")
    return home / "advisor" / "chains"


@contextmanager
def _state_lock(root: Path) -> Iterator[None]:
    parent = root.parent
    if not parent.exists():
        try:
            parent.mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:
            raise ChainUnavailable("cannot create Advisor state parent") from exc
    _safe_directory(parent, create=False)
    _safe_directory(root, create=True)
    lock_path = root / ".lock"
    try:
        fd = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        raise ChainUnavailable("cannot open chain lock") from exc
    os.set_inheritable(fd, False)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ChainError("chain lock is unsafe")
        if os.name != "nt":
            uid = getattr(os, "getuid", lambda: info.st_uid)()
            if info.st_uid != uid or info.st_mode & 0o077:
                raise ChainError("chain lock is not owner-only")
        if os.name == "nt" and msvcrt is not None:
            if info.st_size == 0:
                os.write(fd, b"0")
                os.fsync(fd)
            deadline = time.monotonic() + LOCK_DEADLINE_SECONDS
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise ChainUnavailable("chain lock timed out") from exc
                    time.sleep(0.05)
        elif fcntl is not None:
            deadline = time.monotonic() + LOCK_DEADLINE_SECONDS
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise ChainUnavailable("chain lock timed out") from exc
                    time.sleep(0.05)
        else:
            raise ChainUnavailable("no supported chain locking backend")
        yield
    finally:
        try:
            if os.name == "nt" and msvcrt is not None:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            elif fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _atomic_write(path: Path, state: Mapping[str, Any]) -> None:
    encoded = (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    if len(encoded) > MAX_STATE_BYTES:
        raise ChainError("chain state is too large")
    _safe_directory(path.parent, create=False)
    _safe_file(path, missing_ok=True)
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    staged = Path(staged_name)
    try:
        os.set_inheritable(descriptor, False)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except Exception:
        staged.unlink(missing_ok=True)
        raise


class ChainStore:
    """One process-independent, content-free ledger namespace."""

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root) if root is not None else _default_root()
        if not self.root.is_absolute():
            raise ChainError("chain directory must be absolute")

    def _path(self, checkpoint_key: str) -> tuple[str, Path]:
        digest = checkpoint_digest(checkpoint_key)
        return digest, self.root / f"{digest.removeprefix('sha256:')}.json"

    def _load_unlocked(self, path: Path) -> dict[str, Any] | None:
        try:
            _safe_file(path)
        except ChainUnavailable:
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_duplicate_key)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ChainError("invalid chain state JSON") from exc
        return _validate_state(value)

    @staticmethod
    def _check_identity(
        state: Mapping[str, Any], *, checkpoint: str, policy_digest: str
    ) -> None:
        if state["checkpoint_key_digest"] != checkpoint:
            raise ChainError("checkpoint identity mismatch")
        if state["policy_digest"] != policy_digest:
            raise ChainError("policy digest changed for consumed checkpoint")

    @staticmethod
    def _new_state(checkpoint: str, policy_digest: str, packet_digest: str) -> dict[str, Any]:
        now = _now()
        return {
            "schema_version": SCHEMA_VERSION,
            "checkpoint_key_digest": checkpoint,
            "chain_id": str(uuid.uuid4()),
            "policy_digest": policy_digest,
            "packet_digest": packet_digest,
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "implementation_started": False,
            "next_action": "reserve:low",
            "levels": {level: None for level in LEVELS},
        }

    @staticmethod
    def _entry(level: str, packet_digest: str) -> dict[str, Any]:
        return {
            "status": "reserved",
            "attempt_id": str(uuid.uuid4()),
            "model": MODEL,
            "effort": RUNTIME_EFFORTS[level],
            "packet_digest": packet_digest,
            "result_digest": None,
            "next_level": None,
            "failure_code": None,
        }

    def _validate_request(
        self,
        *,
        level: str,
        policy_digest: str,
        packet_digest: str,
    ) -> tuple[str, str, str]:
        if level not in LEVELS:
            raise ChainError("unsupported advisor level")
        policy_digest = _digest(policy_digest, label="policy digest")
        packet_digest = _digest(packet_digest, label="packet digest")
        return level, policy_digest, packet_digest

    def reserve(
        self,
        checkpoint_key: str,
        *,
        policy_digest: str,
        packet_digest: str,
        level: str = "low",
        authorize_escalation: bool = False,
    ) -> dict[str, Any]:
        level, policy_digest, packet_digest = self._validate_request(
            level=level, policy_digest=policy_digest, packet_digest=packet_digest
        )
        checkpoint, path = self._path(checkpoint_key)
        with _state_lock(self.root):
            state = self._load_unlocked(path)
            if state is None:
                if level != "low":
                    raise ChainError("low must be the first advisor level")
                state = self._new_state(checkpoint, policy_digest, packet_digest)
                state["levels"][level] = self._entry(level, packet_digest)
                state["next_action"] = "launch:low"
                _atomic_write(path, state)
                return {"action": "launch", "state": _validate_state(state)}

            self._check_identity(state, checkpoint=checkpoint, policy_digest=policy_digest)
            if state["implementation_started"]:
                raise ChainError("implementation has started for this checkpoint")
            if state["status"] in ("uncertain", "blocked"):
                raise ChainError("checkpoint is terminal and cannot be replayed")
            entry = state["levels"][level]
            if entry is not None:
                if entry["packet_digest"] != packet_digest:
                    raise ChainError("packet digest changed for consumed advisor level")
                if entry["status"] == "reserved":
                    return {"action": "resume_required", "state": state}
                raise ChainError(f"advisor level is already {entry['status']}")
            if level == "low":
                raise ChainError("low advisor level is already consumed")
            previous = LEVELS[LEVELS.index(level) - 1]
            previous_entry = state["levels"][previous]
            if not authorize_escalation:
                raise ChainError("higher advisor levels require verified escalation")
            if (
                previous_entry is None
                or previous_entry["status"] != "completed"
                or previous_entry["next_level"] != level
            ):
                raise ChainError("higher advisor level lacks adjacent verified escalation")
            state["levels"][level] = self._entry(level, packet_digest)
            state["updated_at"] = _now()
            state["next_action"] = f"launch:{level}"
            _atomic_write(path, state)
            return {"action": "launch", "state": _validate_state(state)}

    def complete(
        self,
        checkpoint_key: str,
        *,
        policy_digest: str,
        level: str,
        next_level: str | None,
        result_digest: str,
    ) -> dict[str, Any]:
        if level not in LEVELS:
            raise ChainError("unsupported advisor level")
        policy_digest = _digest(policy_digest, label="policy digest")
        result_digest = _digest(result_digest, label="result digest")
        if next_level is not None and next_level != NEXT_LEVEL[level]:
            raise ChainError("completion disposition is not adjacent")
        checkpoint, path = self._path(checkpoint_key)
        with _state_lock(self.root):
            state = self._load_unlocked(path)
            if state is None:
                raise ChainError("checkpoint reservation is missing")
            self._check_identity(state, checkpoint=checkpoint, policy_digest=policy_digest)
            entry = state["levels"][level]
            if entry is None or entry["status"] != "reserved":
                raise ChainError("checkpoint level is not actively reserved")
            entry = dict(entry)
            entry.update(
                {
                    "status": "completed",
                    "result_digest": result_digest,
                    "next_level": next_level,
                }
            )
            state["levels"][level] = entry
            state["updated_at"] = _now()
            if next_level is None:
                state["status"] = "complete"
                state["next_action"] = "stop"
            else:
                state["status"] = "completed"
                state["next_action"] = f"reserve:{next_level}"
            _atomic_write(path, state)
            return _validate_state(state)

    def _finish_failure(
        self,
        checkpoint_key: str,
        *,
        policy_digest: str,
        level: str,
        status: str,
        failure_code: str,
    ) -> dict[str, Any]:
        if level not in LEVELS:
            raise ChainError("unsupported advisor level")
        if status not in ("failed", "uncertain") or failure_code not in FAILURE_CODES:
            raise ChainError("invalid terminal ledger disposition")
        policy_digest = _digest(policy_digest, label="policy digest")
        checkpoint, path = self._path(checkpoint_key)
        with _state_lock(self.root):
            state = self._load_unlocked(path)
            if state is None:
                raise ChainError("checkpoint reservation is missing")
            self._check_identity(state, checkpoint=checkpoint, policy_digest=policy_digest)
            entry = state["levels"][level]
            if entry is None or entry["status"] != "reserved":
                raise ChainError("checkpoint level is not actively reserved")
            entry = dict(entry)
            entry.update({"status": status, "failure_code": failure_code})
            state["levels"][level] = entry
            state["status"] = status
            state["next_action"] = "reconcile:no-replay"
            state["updated_at"] = _now()
            _atomic_write(path, state)
            return _validate_state(state)

    def mark_failed(
        self,
        checkpoint_key: str,
        *,
        policy_digest: str,
        level: str,
        failure_code: str,
    ) -> dict[str, Any]:
        return self._finish_failure(
            checkpoint_key,
            policy_digest=policy_digest,
            level=level,
            status="failed",
            failure_code=failure_code,
        )

    def mark_uncertain(
        self,
        checkpoint_key: str,
        *,
        policy_digest: str,
        level: str,
        failure_code: str,
    ) -> dict[str, Any]:
        return self._finish_failure(
            checkpoint_key,
            policy_digest=policy_digest,
            level=level,
            status="uncertain",
            failure_code=failure_code,
        )

    def mark_implementation_started(
        self, checkpoint_key: str, *, policy_digest: str
    ) -> dict[str, Any]:
        policy_digest = _digest(policy_digest, label="policy digest")
        checkpoint, path = self._path(checkpoint_key)
        with _state_lock(self.root):
            state = self._load_unlocked(path)
            if state is None:
                raise ChainError("checkpoint reservation is missing")
            self._check_identity(state, checkpoint=checkpoint, policy_digest=policy_digest)
            if any(
                entry is not None and entry["status"] == "reserved"
                for entry in state["levels"].values()
            ):
                raise ChainError("cannot start implementation with a reserved advisor level")
            state["implementation_started"] = True
            state["status"] = "blocked"
            state["next_action"] = "implementation:started"
            state["updated_at"] = _now()
            _atomic_write(path, state)
            return _validate_state(state)

    def inspect(self, checkpoint_key: str) -> dict[str, Any] | None:
        checkpoint, path = self._path(checkpoint_key)
        with _state_lock(self.root):
            state = self._load_unlocked(path)
            if state is None:
                return None
            if state["checkpoint_key_digest"] != checkpoint:
                raise ChainError("checkpoint identity mismatch")
            return state


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the durable Advisor checkpoint ledger.")
    parser.add_argument("--root", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    reserve = sub.add_parser("reserve")
    reserve.add_argument("--checkpoint-key", required=True)
    reserve.add_argument("--policy-digest", required=True)
    reserve.add_argument("--packet-digest", required=True)
    reserve.add_argument("--level", choices=LEVELS, default="low")
    reserve.add_argument("--authorize-escalation", action="store_true")

    complete = sub.add_parser("complete")
    complete.add_argument("--checkpoint-key", required=True)
    complete.add_argument("--policy-digest", required=True)
    complete.add_argument("--level", choices=LEVELS, required=True)
    complete.add_argument("--next-level", choices=LEVELS, default=None)
    complete.add_argument("--result-digest", required=True)

    for name in ("failed", "uncertain"):
        terminal = sub.add_parser(name)
        terminal.add_argument("--checkpoint-key", required=True)
        terminal.add_argument("--policy-digest", required=True)
        terminal.add_argument("--level", choices=LEVELS, required=True)
        terminal.add_argument("--failure-code", choices=sorted(FAILURE_CODES), required=True)

    started = sub.add_parser("implementation-started")
    started.add_argument("--checkpoint-key", required=True)
    started.add_argument("--policy-digest", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--checkpoint-key", required=True)
    args = parser.parse_args(argv)
    store = ChainStore(args.root)
    try:
        if args.command == "reserve":
            result = store.reserve(
                args.checkpoint_key,
                policy_digest=args.policy_digest,
                packet_digest=args.packet_digest,
                level=args.level,
                authorize_escalation=args.authorize_escalation,
            )
        elif args.command == "complete":
            result = {"status": "ok", "state": store.complete(
                args.checkpoint_key,
                policy_digest=args.policy_digest,
                level=args.level,
                next_level=args.next_level,
                result_digest=args.result_digest,
            )}
        elif args.command == "failed":
            result = {"status": "ok", "state": store.mark_failed(
                args.checkpoint_key,
                policy_digest=args.policy_digest,
                level=args.level,
                failure_code=args.failure_code,
            )}
        elif args.command == "uncertain":
            result = {"status": "ok", "state": store.mark_uncertain(
                args.checkpoint_key,
                policy_digest=args.policy_digest,
                level=args.level,
                failure_code=args.failure_code,
            )}
        elif args.command == "implementation-started":
            result = {"status": "ok", "state": store.mark_implementation_started(
                args.checkpoint_key, policy_digest=args.policy_digest
            )}
        else:
            result = {"status": "ok", "state": store.inspect(args.checkpoint_key)}
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except (ChainError, OSError, ValueError) as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc)}, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
