#!/usr/bin/env python3
"""Private, persistent WSL-to-Windows Codex CLI bridge configuration."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


CONFIG_NAME = "transport.json"
BRIDGE_NAME = "codex-wsl-bridge.py"
BRIDGE_PREFIX = "codex-wsl-bridge-"
CONFIG_KEYS = {
    "schema_version",
    "adapter_path",
    "adapter_sha256",
    "windows_node_executable",
    "windows_codex_entrypoint",
    "sessions_directory",
}
WINDOWS_PATH = re.compile(r"^[A-Za-z]:/(?:[^\r\n]*)$")
WINDOWS_PATH_VALUE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
CODEX_PATH_OPTIONS = {"-C", "--output-schema", "--output-last-message"}


class TransportConfigError(ValueError):
    pass


def default_config_path() -> Path:
    configured = os.environ.get("ADVISOR_TRANSPORT_CONFIG")
    path = Path(configured) if configured else Path.home() / ".codex-advisor" / "transport" / CONFIG_NAME
    if not path.is_absolute():
        raise TransportConfigError("transport config path must be absolute")
    return path


def _check_private(path: Path, expected_mode: int, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise TransportConfigError("transport config is unavailable") from exc
    if stat.S_ISLNK(info.st_mode):
        raise TransportConfigError("transport config contains a symlink")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise TransportConfigError("transport config directory is invalid")
    if not directory and not stat.S_ISREG(info.st_mode):
        raise TransportConfigError("transport config file is invalid")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise TransportConfigError("transport config owner is invalid")
    if stat.S_IMODE(info.st_mode) != expected_mode:
        raise TransportConfigError("transport config permissions are invalid")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TransportConfigError("transport config contains duplicate fields")
        result[key] = value
    return result


def _absolute_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise TransportConfigError(f"transport {label} is invalid")
    return value


def _entrypoint_path(value: str) -> Path:
    if Path(value).is_absolute():
        result = Path(value)
    elif WINDOWS_PATH.fullmatch(value):
        try:
            mapped = subprocess.run(
                ["wslpath", "-u", value],
                check=True,
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise TransportConfigError("Codex CLI entrypoint is unavailable") from exc
        result = Path(mapped)
    else:
        raise TransportConfigError("Codex CLI entrypoint is invalid")
    try:
        info = result.lstat()
    except OSError as exc:
        raise TransportConfigError("Codex CLI entrypoint is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise TransportConfigError("Codex CLI entrypoint is unsafe")
    return result


def _windows_path_argument(value: str) -> str:
    """Map one absolute WSL path to a Windows path for the native CLI."""
    if not value.startswith("/"):
        return value
    try:
        mapped = subprocess.run(
            ["wslpath", "-w", value],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise TransportConfigError("Codex path argument cannot be mapped") from exc
    if not mapped or "\n" in mapped or "\r" in mapped or not WINDOWS_PATH_VALUE.match(mapped):
        raise TransportConfigError("Codex path argument mapping is invalid")
    return mapped


def _windows_path_arguments(arguments: list[str]) -> list[str]:
    """Convert only Codex options whose values are filesystem paths."""
    result: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        option, separator, value = argument.partition("=")
        if separator and option in CODEX_PATH_OPTIONS:
            result.append(f"{option}={_windows_path_argument(value)}")
            index += 1
            continue
        result.append(argument)
        if argument in CODEX_PATH_OPTIONS and index + 1 < len(arguments):
            result.append(_windows_path_argument(arguments[index + 1]))
            index += 2
        else:
            index += 1
    return result


def load_transport_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_config_path()
    if not config_path.is_absolute() or config_path.name != CONFIG_NAME:
        raise TransportConfigError("transport config path is invalid")
    _check_private(config_path.parent.parent, 0o700, directory=True)
    _check_private(config_path.parent, 0o700, directory=True)
    _check_private(config_path, 0o600, directory=False)
    try:
        value = json.loads(
            config_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransportConfigError("transport config cannot be read") from exc
    if not isinstance(value, dict) or set(value) != CONFIG_KEYS:
        raise TransportConfigError("transport config schema is invalid")
    if value["schema_version"] != 1 or isinstance(value["schema_version"], bool):
        raise TransportConfigError("transport config version is unsupported")

    adapter_path = Path(_absolute_text(value["adapter_path"], "adapter path"))
    node_path = Path(_absolute_text(value["windows_node_executable"], "Node path"))
    sessions_path = Path(_absolute_text(value["sessions_directory"], "sessions path"))
    entrypoint = _absolute_text(value["windows_codex_entrypoint"], "CLI entrypoint")
    digest = value["adapter_sha256"]
    managed_adapter = (
        adapter_path.parent == config_path.parent
        and (
            adapter_path.name == BRIDGE_NAME
            or re.fullmatch(r"codex-wsl-bridge-[0-9a-f]{16}\.py", adapter_path.name)
        )
    )
    if not adapter_path.is_absolute() or not managed_adapter:
        raise TransportConfigError("transport adapter path is invalid")
    if not node_path.is_absolute() or not sessions_path.is_absolute():
        raise TransportConfigError("transport paths must be absolute")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise TransportConfigError("transport adapter digest is invalid")
    _check_private(adapter_path, 0o700, directory=False)
    try:
        actual_digest = hashlib.sha256(adapter_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise TransportConfigError("transport adapter is unavailable") from exc
    if actual_digest != digest:
        raise TransportConfigError("transport adapter digest mismatch")
    try:
        node_info = node_path.lstat()
        sessions_info = sessions_path.lstat()
        if (
            stat.S_ISLNK(node_info.st_mode)
            or not stat.S_ISREG(node_info.st_mode)
            or not os.access(node_path, os.X_OK)
            or stat.S_ISLNK(sessions_info.st_mode)
            or not stat.S_ISDIR(sessions_info.st_mode)
        ):
            raise TransportConfigError("configured Codex transport is unsafe")
    except OSError as exc:
        raise TransportConfigError("configured Codex transport is unavailable") from exc
    _entrypoint_path(entrypoint)
    return value


def resolve_runtime(*, sessions_directory: str | None = None) -> dict[str, str]:
    explicit = os.environ.get("ADVISOR_CODEX_BIN")
    config_path = default_config_path() if explicit is None else None
    if explicit is not None:
        path = Path(explicit)
        if not path.is_absolute() or not path.is_file() or path.is_symlink() or not os.access(path, os.X_OK):
            raise TransportConfigError("ADVISOR_CODEX_BIN is unsafe or unavailable; no fallback")
        executable, source = str(path), "explicit"
        sessions = sessions_directory or os.environ.get("ADVISOR_SESSIONS_DIR") or str(Path(os.environ.get("CODEX_HOME", str(Path.home()/".codex")))/"sessions")
    elif config_path is not None and (config_path.exists() or config_path.is_symlink() or os.environ.get("ADVISOR_TRANSPORT_CONFIG")):
        config = load_transport_config(config_path)
        executable, source = config["adapter_path"], "installed-wsl-bridge"
        sessions = config["sessions_directory"]
        if sessions_directory is not None and Path(sessions_directory) != Path(sessions):
            raise TransportConfigError("sessions directory does not match installed transport")
    else:
        executable = shutil.which("codex") or ""
        if not executable:
            raise TransportConfigError("codex CLI is unavailable")
        source = "PATH"
        sessions = sessions_directory or str(Path(os.environ.get("CODEX_HOME", str(Path.home()/".codex")))/"sessions")
    if not Path(sessions).is_absolute():
        raise TransportConfigError("sessions directory must be absolute")
    return {"executable": executable, "sessions_directory": sessions, "source": source}


def resolve(field: str) -> str:
    config = load_transport_config()
    if field == "codex_executable":
        return config["adapter_path"]
    if field == "sessions_directory":
        return config["sessions_directory"]
    raise TransportConfigError("unsupported transport field")


def _private_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        _check_private(path, 0o700, directory=True)
    else:
        path.mkdir(mode=0o700)
        _check_private(path, 0o700, directory=True)


def install(node_executable: str, entrypoint: str, sessions_directory: str) -> dict[str, str]:
    if os.name == "nt" or not os.environ.get("WSL_DISTRO_NAME"):
        raise TransportConfigError("WSL transport installer must run inside WSL")
    node_path = Path(node_executable)
    sessions_path = Path(sessions_directory)
    if not node_path.is_absolute() or not sessions_path.is_absolute():
        raise TransportConfigError("installer paths must be absolute")
    node_info = node_path.lstat()
    sessions_info = sessions_path.lstat()
    if (
        stat.S_ISLNK(node_info.st_mode)
        or not stat.S_ISREG(node_info.st_mode)
        or not os.access(node_path, os.X_OK)
        or stat.S_ISLNK(sessions_info.st_mode)
        or not stat.S_ISDIR(sessions_info.st_mode)
    ):
        raise TransportConfigError("installer paths are unsafe or unavailable")
    _entrypoint_path(entrypoint)
    try:
        probe = subprocess.run(
            [str(node_path), entrypoint, "--version"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        version = probe.stdout.decode("utf-8").strip()
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise TransportConfigError("Codex CLI preflight failed") from exc
    if not version.startswith("codex-cli ") or "\n" in version or "\r" in version:
        raise TransportConfigError("Codex CLI preflight returned an invalid version")

    root = Path.home() / ".codex-advisor"
    transport_dir = root / "transport"
    if root.exists() or root.is_symlink():
        _check_private(root, 0o700, directory=True)
    else:
        root.mkdir(mode=0o700)
    _private_directory(transport_dir)

    config_path = transport_dir / CONFIG_NAME
    source = Path(__file__).absolute()
    source_info = source.lstat()
    if stat.S_ISLNK(source_info.st_mode) or not stat.S_ISREG(source_info.st_mode):
        raise TransportConfigError("packaged transport adapter is unsafe")
    source_bytes = source.read_bytes()
    adapter_digest = hashlib.sha256(source_bytes).hexdigest()
    adapter = transport_dir / f"{BRIDGE_PREFIX}{adapter_digest[:16]}.py"
    old_config: bytes | None = None
    if config_path.exists() or config_path.is_symlink():
        if not config_path.is_file() or config_path.is_symlink():
            raise TransportConfigError("existing WSL transport config is invalid")
        load_transport_config(config_path)
        old_config = config_path.read_bytes()
    if adapter.exists() or adapter.is_symlink():
        _check_private(adapter, 0o700, directory=False)
        if hashlib.sha256(adapter.read_bytes()).hexdigest() != adapter_digest:
            raise TransportConfigError("managed adapter digest collision")

    payload = {
        "schema_version": 1,
        "adapter_path": str(adapter),
        "adapter_sha256": adapter_digest,
        "windows_node_executable": str(node_path),
        "windows_codex_entrypoint": entrypoint,
        "sessions_directory": str(sessions_path),
    }
    backups: list[str] = []
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = 0
    while True:
        tag = f"{stamp}-{suffix}"
        backup_config = transport_dir / f"{CONFIG_NAME}.backup-{tag}"
        if not backup_config.exists() and not backup_config.is_symlink():
            break
        suffix += 1
    if old_config is not None:
        backup_config.write_bytes(old_config)
        backup_config.chmod(0o600)
        backups = [str(backup_config)]

    adapter_tmp: Path | None = None
    config_tmp: Path | None = None
    adapter_created = False

    def rollback_config() -> None:
        if old_config is None:
            config_path.unlink(missing_ok=True)
            return
        restore_tmp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=transport_dir, prefix=".restore-config-", delete=False
            ) as handle:
                restore_tmp = Path(handle.name)
                handle.write(old_config)
            restore_tmp.chmod(0o600)
            os.replace(restore_tmp, config_path)
            restore_tmp = None
        finally:
            if restore_tmp is not None:
                restore_tmp.unlink(missing_ok=True)

    try:
        if not adapter.exists():
            with tempfile.NamedTemporaryFile(dir=transport_dir, prefix=".adapter-", delete=False) as handle:
                adapter_tmp = Path(handle.name)
                handle.write(source_bytes)
            adapter_tmp.chmod(0o700)
            os.replace(adapter_tmp, adapter)
            adapter_tmp = None
            adapter_created = True
        with tempfile.NamedTemporaryFile(dir=transport_dir, prefix=".config-", mode="w", encoding="utf-8", delete=False) as handle:
            config_tmp = Path(handle.name)
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
        config_tmp.chmod(0o600)
        os.replace(config_tmp, config_path)
        config_tmp = None
    except OSError as exc:
        if adapter_tmp is not None:
            adapter_tmp.unlink(missing_ok=True)
        if config_tmp is not None:
            config_tmp.unlink(missing_ok=True)
        try:
            rollback_config()
        except OSError as rollback_exc:
            raise TransportConfigError("transport rollback failed; preserve installer backups") from rollback_exc
        if adapter_created:
            adapter.unlink(missing_ok=True)
        raise TransportConfigError("transport install could not be committed") from exc

    try:
        load_transport_config(config_path)
        installed_probe = subprocess.run(
            [str(adapter), "--version"],
            check=True,
            capture_output=True,
            timeout=5,
            env={**os.environ, "ADVISOR_TRANSPORT_CONFIG": str(config_path)},
        )
        installed_version = installed_probe.stdout.decode("utf-8").strip()
        if installed_version != version or "\n" in installed_version or "\r" in installed_version:
            raise TransportConfigError("installed bridge preflight did not match")
    except (OSError, subprocess.SubprocessError, UnicodeError, TransportConfigError) as exc:
        try:
            rollback_config()
        except OSError as rollback_exc:
            raise TransportConfigError("transport rollback failed; preserve installer backups") from rollback_exc
        if adapter_created:
            adapter.unlink(missing_ok=True)
        if isinstance(exc, TransportConfigError):
            raise
        raise TransportConfigError("installed bridge preflight failed") from exc
    return {
        "status": "installed",
        "codex_version": version,
        "adapter": str(adapter),
        "configuration": str(config_path),
        "sessions_directory": str(sessions_path),
        "backups": json.dumps(backups, separators=(",", ":")),
    }


def _run_as_adapter(arguments: list[str]) -> int:
    try:
        config = load_transport_config()
        node = config["windows_node_executable"]
        entrypoint = config["windows_codex_entrypoint"]
        if Path(entrypoint).is_absolute():
            entrypoint = str(Path(entrypoint))
        os.execv(node, [node, entrypoint, *_windows_path_arguments(arguments)])
    except (OSError, TransportConfigError) as exc:
        print(f"ADVISOR WSL TRANSPORT: unavailable ({exc})", file=sys.stderr)
        return 127
    return 127


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args and args[0] == "--runtime":
            if len(args) > 2:
                raise TransportConfigError("invalid runtime request")
            print(json.dumps(resolve_runtime(sessions_directory=args[1] if len(args) == 2 else None)))
            return 0
        if args and args[0] == "--resolve":
            if len(args) != 2:
                raise TransportConfigError("invalid resolver request")
            print(resolve(args[1]))
            return 0
        if args and args[0] == "--install":
            parser = argparse.ArgumentParser(add_help=False)
            parser.add_argument("--install", action="store_true")
            parser.add_argument("--node-executable", required=True)
            parser.add_argument("--codex-entrypoint", required=True)
            parser.add_argument("--sessions-directory", required=True)
            values = parser.parse_args(args)
            print(json.dumps(install(values.node_executable, values.codex_entrypoint, values.sessions_directory), separators=(",", ":")))
            return 0
        return _run_as_adapter(args)
    except (TransportConfigError, OSError, ValueError) as exc:
        print(f"ADVISOR WSL TRANSPORT: unavailable ({exc})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
