"""Launcher acceptance authentication; no ledger, consumption, or replay state.

Trust boundary: repository helpers and owner-only Codex home are trusted, as are
persisted runtime sessions. This does not defend against their filesystem owner
rewriting code, sessions, or the key. Untrusted receipt bytes cannot attest a
launch rejected before acceptance. The key stores no prompts or per-run records.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from advisor_state import ConfigError, _safe_directory, read_json


def _key(*, create: bool) -> bytes:
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    if not home.is_absolute():
        raise ConfigError("launcher acceptance proof home is unsafe")
    info = home.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ConfigError("launcher acceptance proof home is unsafe")
    temporary = home / ".tmp"
    _safe_directory(temporary, create=create)
    root = temporary / "advisor-acceptance"
    _safe_directory(root, create=create)
    flags = os.O_RDWR if create else os.O_RDONLY
    flags |= os.O_NONBLOCK | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    created = False
    try:
        if create:
            try:
                fd = os.open(root / "key", flags | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
            except FileExistsError:
                fd = os.open(root / "key", flags)
        else:
            fd = os.open(root / "key", flags)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if created else fcntl.LOCK_SH)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise ConfigError("launcher acceptance proof key is unsafe")
            if created:
                if os.write(fd, os.urandom(32)) != 32:
                    raise ConfigError("launcher acceptance proof key unavailable")
                os.fsync(fd)
                os.lseek(fd, 0, os.SEEK_SET)
            value = os.read(fd, 33)
            if len(value) != 32:
                raise ConfigError("launcher acceptance proof key unavailable")
            return value
        finally:
            os.close(fd)
    except OSError as exc:
        raise ConfigError("launcher acceptance proof key unavailable") from exc


def _content(receipt: dict[str, Any]) -> bytes:
    body = {key: value for key, value in receipt.items() if key != "acceptance_proof"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def verify_acceptance(receipt: dict[str, Any]) -> None:
    proof = receipt.get("acceptance_proof")
    if (not isinstance(proof, dict) or set(proof) != {"algorithm", "mac"}
            or proof["algorithm"] != "hmac-sha256-v1"
            or not isinstance(proof["mac"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", proof["mac"])):
        raise ConfigError("launcher acceptance proof missing or invalid")
    observed = hmac.new(_key(create=False), _content(receipt), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(observed, proof["mac"]):
        raise ConfigError("launcher acceptance proof mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seal", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = read_json(args.seal)
        if (not isinstance(receipt, dict) or receipt.get("status") != "completed"
                or receipt.get("outcome") != "accepted" or "acceptance_proof" in receipt):
            raise ConfigError("launcher acceptance proof requires an accepted result")
        mac = hmac.new(_key(create=True), _content(receipt), hashlib.sha256).hexdigest()
        receipt["acceptance_proof"] = {"algorithm": "hmac-sha256-v1", "mac": mac}
        print(json.dumps(receipt, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
        return 0
    except (ConfigError, OSError, ValueError, TypeError, RecursionError):
        print('{"status":"unavailable","error":"launcher acceptance proof unavailable"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
