#!/bin/sh
# Emit only allowlisted isolation evidence for the current Codex parent thread.

set -eu

unavailable() {
  printf '%s\n' '{"status":"unavailable","reason_type":"parent_runtime_unavailable","redacted":true}'
  exit 0
}

sessions_dir=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --sessions-dir)
      [ "$#" -ge 2 ] && [ -n "$2" ] || unavailable
      sessions_dir=$2
      shift 2
      ;;
    *) unavailable ;;
  esac
done

parent_thread_id=${CODEX_THREAD_ID-}
printf '%s\n' "$parent_thread_id" | LC_ALL=C grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' || unavailable

if [ -z "$sessions_dir" ]; then
  if [ -n "${CODEX_HOME-}" ]; then
    sessions_dir=$CODEX_HOME/sessions
  elif [ -n "${HOME-}" ]; then
    sessions_dir=$HOME/.codex/sessions
  else
    unavailable
  fi
fi

[ -d "$sessions_dir" ] && [ ! -L "$sessions_dir" ] || unavailable

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd) || unavailable
helper=$script_dir/advisor_parent.py
[ -f "$helper" ] && [ ! -L "$helper" ] || unavailable
python3 "$helper" --sessions-dir "$sessions_dir" --thread-id "$parent_thread_id" 2>/dev/null || unavailable
