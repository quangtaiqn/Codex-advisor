#!/bin/sh
# Install a private, persistent bridge to the Windows Codex CLI for WSL hosts.

set -eu

fail() { printf '%s\n' "ADVISOR WSL INSTALL: unavailable ($*)" >&2; exit 1; }

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd) || fail "plugin script directory is unavailable"
[ -n "${WSL_DISTRO_NAME-}" ] || fail "run this installer inside the configured WSL distribution"
command -v python3 >/dev/null 2>&1 || fail "python3 is unavailable"
command -v wslpath >/dev/null 2>&1 || fail "wslpath is unavailable"
command -v node.exe >/dev/null 2>&1 || fail "Windows Node executable is unavailable"
command -v cmd.exe >/dev/null 2>&1 || fail "Windows environment lookup is unavailable"

# Avoid launching Windows helpers from a UNC working directory.
cd /mnt/c 2>/dev/null || fail "Windows user profile mount is unavailable"
windows_profile=$(cmd.exe /d /c echo %USERPROFILE% 2>/dev/null | tr -d '\r') || fail "Windows profile lookup failed"
windows_appdata=$(cmd.exe /d /c echo %APPDATA% 2>/dev/null | tr -d '\r') || fail "Windows application-data lookup failed"
[ -n "$windows_profile" ] && [ -n "$windows_appdata" ] || fail "Windows profile paths are unavailable"

profile_forward=$(printf '%s' "$windows_profile" | tr '\\' '/')
appdata_forward=$(printf '%s' "$windows_appdata" | tr '\\' '/')
codex_entrypoint=$appdata_forward/npm/node_modules/@openai/codex/bin/codex.js
codex_posix_path=$(wslpath -u "$codex_entrypoint" 2>/dev/null) || fail "Windows Codex CLI path could not be mapped"
sessions_directory=$(wslpath -u "$profile_forward/.codex/sessions" 2>/dev/null) || fail "Windows Codex sessions path could not be mapped"
node_executable=$(command -v node.exe 2>/dev/null || :)
[ -n "$node_executable" ] && [ -x "$node_executable" ] || fail "Windows Node executable is not runnable"
[ -f "$codex_posix_path" ] && [ ! -L "$codex_posix_path" ] || fail "Windows Codex CLI package is unavailable"
[ -d "$sessions_directory" ] && [ ! -L "$sessions_directory" ] || fail "Windows Codex sessions directory is unavailable"

result=$(python3 "$script_dir/advisor_transport.py" --install \
  --node-executable "$node_executable" \
  --codex-entrypoint "$codex_entrypoint" \
  --sessions-directory "$sessions_directory") || fail "persistent bridge installation failed"
printf '%s\n' "$result"

bridge_path=$(printf '%s' "$result" | python3 -c 'import json, sys; print(json.load(sys.stdin)["adapter"])') || fail "installer result is invalid"
config_path=$(printf '%s' "$result" | python3 -c 'import json, sys; print(json.load(sys.stdin)["configuration"])') || fail "installer result is invalid"
if ! bridge_version=$(ADVISOR_TRANSPORT_CONFIG="$config_path" "$bridge_path" --version 2>/dev/null); then
  fail "installed bridge preflight failed"
fi
configured_version=$(printf '%s' "$result" | python3 -c 'import json, sys; print(json.load(sys.stdin)["codex_version"])') || fail "installer result is invalid"
[ "$bridge_version" = "$configured_version" ] || fail "installed bridge version does not match preflight"
printf '%s\n' "ADVISOR WSL INSTALL: verified ($bridge_version)"
printf 'configuration: %s\n' "$config_path"
