#!/bin/sh
# Run one distinct, read-only Codex consultation and emit one verified JSON result.

set -eu

fail() {
  printf '%s\n' "ADVISOR TRANSPORT: unavailable ($*)" >&2
  if command -v terminal_failure >/dev/null 2>&1; then terminal_failure "$*" || :; else
    printf '%s\n' '{"schema_version":4,"status":"unavailable","outcome":"failed","selection":null,"attempts":[],"usage":null,"runtime":null,"response":null,"advisor_response":null,"escalation":null}'
  fi
  exit 1
}

progress() { printf '%s\n' "ADVISOR TRANSPORT: $*" >&2; }
now_ms() { python3 -c 'import time; print(time.monotonic_ns() // 1_000_000)'; }
utc_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

role='' tier='' level='' previous_result='' authorize_escalation=false preset='' canary_token='' parent_thread_id='' sessions_dir=''
selection_source='' selection_revision=null source_revision=null
ledger_dir=${ADVISOR_LEDGER_DIR-} issue_id=${ADVISOR_ISSUE_ID-} project_root=${ADVISOR_PROJECT_ROOT:-$(pwd)}
ledger_binding=null ledger_reserved=false
supersedes='' revision_reason='' evidence_digest=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --ledger-dir) [ "$#" -ge 2 ] || fail "--ledger-dir requires PATH"; ledger_dir=$2; shift 2 ;;
    --issue-id) [ "$#" -ge 2 ] || fail "--issue-id requires ID"; issue_id=$2; shift 2 ;;
    --project-root) [ "$#" -ge 2 ] || fail "--project-root requires PATH"; project_root=$2; shift 2 ;;
    --supersedes) [ "$#" -ge 2 ] || fail "--supersedes requires ID"; supersedes=$2; shift 2 ;;
    --revision-reason) [ "$#" -ge 2 ] || fail "--revision-reason requires TEXT"; revision_reason=$2; shift 2 ;;
    --evidence-digest) [ "$#" -ge 2 ] || fail "--evidence-digest requires SHA256"; evidence_digest=$2; shift 2 ;;
    --level) [ "$#" -ge 2 ] || fail "--level requires LEVEL"; level=$2; shift 2 ;;
    --previous-result) [ "$#" -ge 2 ] || fail "--previous-result requires PATH"; previous_result=$2; shift 2 ;;
    --authorize-escalation) authorize_escalation=true; shift ;;
    --chain-authorized|--checkpoint-key|--qualify-chain) fail "legacy checkpoint/chain flags cannot authorize escalation; use --previous-result and --authorize-escalation" ;;
    --role) [ "$#" -ge 2 ] || fail "--role requires ROLE"; role=$2; shift 2 ;;
    --tier) [ "$#" -ge 2 ] || fail "--tier requires TIER"; tier=$2; shift 2 ;;
    --preset) [ "$#" -ge 2 ] || fail "--preset requires NAME"; preset=$2; shift 2 ;;
    --compatibility-canary) [ "$#" -ge 2 ] || fail "--compatibility-canary requires TOKEN"; canary_token=$2; shift 2 ;;
    --parent-thread) [ "$#" -ge 2 ] || fail "--parent-thread requires THREAD_ID"; parent_thread_id=$2; shift 2 ;;
    --sessions-dir) [ "$#" -ge 2 ] || fail "--sessions-dir requires DIR"; sessions_dir=$2; shift 2 ;;
    *) fail "unknown argument" ;;
  esac
done

[ -z "$role" ] || [ -z "$tier" ] || fail "--role and --tier are mutually exclusive"
[ -z "$canary_token" ] || { [ -z "$role" ] && [ -z "$tier" ] && [ -z "$preset" ]; } || fail "compatibility canary cannot be mixed with role, tier, or preset"
[ -z "$preset" ] || [ -n "$tier" ] || fail "--preset requires --tier"
[ -n "$level" ] || level=low
[ "$level" != xhigh ] || level=extra_high
case "$level" in low|medium|high|extra_high) ;; *) fail "unsupported advisor level" ;; esac
if [ "$level" = low ]; then
  [ -z "$previous_result" ] && [ "$authorize_escalation" = false ] || fail "low cannot resume or reset an escalation"
else
  [ -n "$previous_result" ] && [ "$authorize_escalation" = true ] || fail "higher levels require --previous-result and --authorize-escalation"
  [ -z "$canary_token" ] || fail "canaries cannot authorize higher levels"
fi
script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd) || fail "script directory unavailable"
command -v python3 >/dev/null 2>&1 || fail "python3 is unavailable"
python3 - <<'PY' || fail "python3 must be Python 3.11+ (tomllib requirement)"
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
command -v jq >/dev/null 2>&1 || fail "jq is unavailable"
for helper in advisor_ledger.py advisor_ledger_store.py advisor_parent.py advisor_acceptance.py advisor_accounting.py advisor_config.py advisor_state.py advisor_catalog.py advisor_settings.py advisor_journal.py advisor_discovery.py advisor_canary.py advisor_doctor.py advisor_process.py advisor_transport.py advisor_admission.py inspect-agent-runtime.sh inspect-parent-runtime.sh; do
  [ -f "$script_dir/$helper" ] && [ ! -L "$script_dir/$helper" ] || fail "installed Advisor helper is unsafe"
done
if [ -n "$canary_token" ]; then
  resolution=$(python3 "$script_dir/advisor_config.py" --json _consume-canary "$canary_token") || fail "compatibility canary authorization is unavailable"
  model=$(printf '%s' "$resolution" | jq -r '.launch.model') || fail "invalid compatibility canary authorization"
  effort=$(printf '%s' "$resolution" | jq -r '.launch.effort') || fail "invalid compatibility canary authorization"
  deadline_seconds=$(printf '%s' "$resolution" | jq -r '.launch.deadline_seconds') || fail "invalid compatibility canary authorization"
  tier=compatibility-test
  selection_source=authorized-synthetic-canary
  selection_revision=$(printf '%s' "$resolution" | jq -c '.launch.selection_revision') || fail "invalid compatibility canary authorization"
  source_revision=$(printf '%s' "$resolution" | jq -c '.launch.source_revision // .launch.selection_revision') || fail "invalid compatibility canary authorization"
  role=advisor-compatibility-test
else
  set -- --json resolve --level "$level"
  [ -z "$tier" ] || set -- "$@" --tier "$tier"
  [ -z "$role" ] || set -- "$@" --role "$role"
  [ -z "$preset" ] || set -- "$@" --preset "$preset"
  if ! resolution=$(python3 "$script_dir/advisor_config.py" "$@"); then
    config_error=$(printf '%s' "$resolution" | jq -r '.error // empty' 2>/dev/null || :)
    fail "${config_error:-active Astra policy unavailable}"
  fi
  model=$(printf '%s' "$resolution" | jq -r '.launch.model')
  effort=$(printf '%s' "$resolution" | jq -r '.launch.effort')
  role=$(printf '%s' "$resolution" | jq -r '.launch.role')
  tier=advisor
  deadline_seconds=$(printf '%s' "$resolution" | jq -r '.launch.deadline_seconds')
  selection_source=$(printf '%s' "$resolution" | jq -r '.launch.selection_source')
  selection_revision=$(printf '%s' "$resolution" | jq -c '.launch.selection_revision')
  source_revision=$(printf '%s' "$resolution" | jq -c '.launch.source_revision')
fi
set -- --runtime
[ -z "$sessions_dir" ] || set -- "$@" "$sessions_dir"
runtime_source=$(python3 "$script_dir/advisor_transport.py" "$@") || fail "configured Codex transport unavailable"
codex_bin=$(printf '%s' "$runtime_source" | jq -r '.executable')
sessions_dir=$(printf '%s' "$runtime_source" | jq -r '.sessions_directory')

journal_status=$(python3 "$script_dir/advisor_config.py" --json journal status 2>/dev/null || printf '%s' '{"enabled":false}')
journal_enabled=$(printf '%s' "$journal_status" | jq -r '.enabled == true' 2>/dev/null || printf '%s' false)
consultation_id=$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
) || fail "consultation identifier generation failed"
consultation_started=$(utc_now) || fail "consultation timestamp initialization failed"
attempt_records='[]'
consultation_started_ms=$(now_ms) || fail "consultation timing initialization failed"
attempt_open=false
terminal_emitted=false
ledger() { python3 "$script_dir/advisor_ledger.py" --ledger-dir "$ledger_dir" --project-root "$project_root" --issue-id "$issue_id" "$@" --launcher-pid "$$"; }

usage_totals() {
  jq -cn --argjson attempts "$attempt_records" '
    def metric($name):
      [$attempts[].usage[$name]] as $all
      | [$all[] | select(. != null)] as $known
      | {value:(if ($known|length)>0 then ($known|add) else null end),
         availability:(if ($all|length)==0 or ($known|length)==0 then "unavailable" elif ($known|length)==($all|length) then "available" else "partial" end)};
    {input:metric("input"),cached_input:metric("cached_input"),output:metric("output"),reasoning:metric("reasoning")}
  '
}

terminal_failure() {
  [ "$terminal_emitted" = false ] || return 0
  terminal_emitted=true
  failure_message=$1
  case "$failure_message" in
    *deadline*|*timed*out*) consultation_outcome=timed_out; attempt_outcome=timed_out ;;
    *cancel*) consultation_outcome=cancelled; attempt_outcome=cancelled ;;
    *response*validation*) consultation_outcome=failed; attempt_outcome=rejected_response ;;
    *runtime*|*inspection*) consultation_outcome=failed; attempt_outcome=runtime_failed ;;
    *) consultation_outcome=failed; attempt_outcome=launch_failed ;;
  esac
  if [ "$attempt_open" = true ]; then
    failure_finished_ms=$(now_ms) || return 0
    failure_duration_ms=$((failure_finished_ms - attempt_started_ms))
    failure_usage=$(python3 "$script_dir/advisor_process.py" usage --events "$events" --duration-ms "$failure_duration_ms" 2>/dev/null || printf '{"duration_ms":%s,"usage":{"input":null,"cached_input":null,"output":null,"reasoning":null},"availability":{"input":"unavailable","cached_input":"unavailable","output":"unavailable","reasoning":"unavailable"}}' "$failure_duration_ms")
    attempt_records=$(jq -cn --argjson prior "$attempt_records" --argjson usage "$failure_usage" --argjson number "$attempt" --arg outcome "$attempt_outcome" '$prior + [{number:$number,outcome:$outcome,duration_ms:$usage.duration_ms,usage:$usage.usage,availability:$usage.availability}]') || return 0
    attempt_open=false
  fi
  if [ "$ledger_reserved" = true ]; then
    ledger fail --execution "$consultation_id" --outcome "$consultation_outcome" >/dev/null 2>&1 || progress "ledger failure finalization unavailable; quota remains consumed"
  fi
  consultation_finished=$(utc_now) || return 0
  finish_ms=$(now_ms) || return 0
  total_duration_ms=$((finish_ms - consultation_started_ms))
  metric_rows=$(usage_totals) || return 0
  totals=$(printf '%s' "$metric_rows" | jq -c '{input:.input.value,cached_input:.cached_input.value,output:.output.value,reasoning:.reasoning.value}') || return 0
  availability=$(printf '%s' "$metric_rows" | jq -c '{input:.input.availability,cached_input:.cached_input.availability,output:.output.availability,reasoning:.reasoning.availability}') || return 0
  if [ "$journal_enabled" = true ]; then
    progress "writing content-free usage journal"
    journal_record=$(jq -cn --arg id "$consultation_id" --arg started "$consultation_started" --arg finished "$consultation_finished" --arg level "$level" --arg role "$role" --arg tier "$tier" --arg model "$model" --arg effort "$effort" --arg outcome "$consultation_outcome" --argjson duration "$total_duration_ms" --argjson attempts "$attempt_records" --argjson totals "$totals" '{schema_version:1,consultation_id:$id,started_at:$started,finished_at:$finished,tier:$tier,model:$model,effort:$effort,outcome:$outcome,transport_contract_version:"1.6",total_duration_ms:$duration,attempts:[$attempts[]|{number,duration_ms,outcome,usage}],totals:$totals}') || journal_record=''
    if [ -z "$journal_record" ] || ! python3 "$script_dir/advisor_config.py" --json _journal-record "$journal_record" >/dev/null 2>&1; then printf '%s\n' 'ADVISOR TRANSPORT: warning (usage journal write unavailable)' >&2; fi
  fi
  jq -cn --arg id "$consultation_id" --arg level "$level" --arg role "$role" --arg tier "$tier" --arg model "$model" --arg effort "$effort" --arg source "$selection_source" --argjson revision "$selection_revision" --argjson source_revision "$source_revision" --arg outcome "$consultation_outcome" --argjson attempts "$attempt_records" --argjson totals "$totals" --argjson availability "$availability" --argjson duration "$total_duration_ms" '{schema_version:4,status:"unavailable",outcome:$outcome,consultation_id:$id,selection:{tier:$tier,level:$level,role:$role,model:$model,effort:$effort,source:$source,revision:$revision,source_revision:$source_revision,transport_contract_version:"1.6"},attempts:$attempts,usage:{total_duration_ms:$duration,totals:$totals,availability:$availability},runtime:null,response:null,advisor_response:null,escalation:null}' || :
}

[ -n "$parent_thread_id" ] || parent_thread_id=${CODEX_THREAD_ID-}
printf '%s\n' "$parent_thread_id" | LC_ALL=C grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' || fail "parent thread is unavailable"
parent_admission=$(python3 "$script_dir/advisor_admission.py" --parent "$parent_thread_id" --sessions-dir "$sessions_dir") || fail "parent runtime unavailable"
parent_permission=$(printf '%s' "$parent_admission" | jq -r '.parent.permission_profile_type')
codex_home=${CODEX_HOME:-${HOME-}/.codex}
case "$codex_home" in /*) ;; *) fail "Codex home is unavailable" ;; esac
[ -d "$codex_home" ] && [ ! -L "$codex_home" ] || fail "Codex home is unavailable"
transport_root=$codex_home/.tmp/advisor-transport
umask 077
if [ ! -e "$transport_root" ]; then
  mkdir -p "$transport_root" || fail "private transport root creation failed"
fi
[ -d "$transport_root" ] && [ ! -L "$transport_root" ] || fail "private transport root is unsafe"
transport_dir=$transport_root/run.$consultation_id
owned=false
startup=true
cancel_requested=false
supervisor_pid=''
cleanup() {
  if [ -n "$supervisor_pid" ]; then
    kill -TERM "$supervisor_pid" 2>/dev/null || :
    wait "$supervisor_pid" 2>/dev/null || :
    supervisor_pid=''
  fi
  if [ "$owned" = true ]; then
    case "$transport_dir" in "$transport_root"/run.*) rm -rf -- "$transport_dir" ;; esac
  fi
}
cancelled() {
  if [ "$startup" = true ]; then
    cancel_requested=true
    return 0
  fi
  if [ -n "$supervisor_pid" ]; then
    kill -TERM "$supervisor_pid" 2>/dev/null || :
    wait "$supervisor_pid" 2>/dev/null || :
    supervisor_pid=''
  fi
  terminal_failure "consultation cancelled" || :
  exit 130
}
trap cleanup 0
trap cancelled HUP INT TERM

(
  trap '' HUP INT TERM
  mkdir "$transport_dir"
) || fail "temporary directory creation failed"
owned=true
chmod 700 "$transport_dir" || fail "temporary directory protection failed"
startup=false
if [ "$cancel_requested" = true ]; then
  cancelled
fi

packet=$transport_dir/packet.txt
base_prompt=$transport_dir/prompt.1.txt
deadline_at=$(python3 - "$deadline_seconds" <<'PY'
import sys, time
print(time.monotonic() + int(sys.argv[1]))
PY
) || fail "deadline initialization failed"
deadline_ok() {
  python3 - "$deadline_at" <<'PY'
import sys, time
raise SystemExit(0 if time.monotonic() < float(sys.argv[1]) else 1)
PY
}
if [ -n "$canary_token" ]; then
  cat >"$packet" <<'ADVISOR_CANARY'
DECISION
Confirm technical compatibility of this fixed synthetic consultation.

CONTEXT
This is a content-free transport canary authorized by the user.

OPTIONS
Return a schema-valid neutral response.

BOUNDARIES
Use zero tools and only the configured read-only model transport.

REQUEST
Return the required JSON object with a neutral recommendation and concrete transport acceptance checks.
ADVISOR_CANARY
else
  exec 3<&0
  python3 "$script_dir/advisor_process.py" --deadline-at "$deadline_at" --capture-to "$packet" <&3 &
  supervisor_pid=$!
  capture_status=0
  wait "$supervisor_pid" || capture_status=$?
  supervisor_pid=''
  [ "$capture_status" -ne 124 ] || fail "decision packet capture deadline exceeded"
  [ "$capture_status" -eq 0 ] || fail "decision packet capture failed"
fi
[ -s "$packet" ] || fail "decision packet is empty"

previous=0
for heading in DECISION CONTEXT OPTIONS BOUNDARIES REQUEST; do
  line=$(grep -n -F -x "$heading" "$packet" | cut -d: -f1)
  [ "$(printf '%s\n' "$line" | awk 'NF { count += 1 } END { print count + 0 }')" -eq 1 ] || fail "malformed decision packet"
  [ "$line" -gt "$previous" ] || fail "misordered decision packet"
  previous=$line
done

packet_digest=$(python3 - "$packet" <<'PY'
import hashlib,sys
from pathlib import Path
print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
) || fail "packet digest unavailable"
previous_admission=''
if [ "$level" != low ]; then
  if ! previous_admission=$(python3 "$script_dir/advisor_admission.py" --parent "$parent_thread_id" --sessions-dir "$sessions_dir" --level "$level" --previous-result "$previous_result" --packet "$packet" --source-revision "$(printf '%s' "$source_revision" | jq -r '.')" --ledger-dir "$ledger_dir" --project-root "$project_root" --issue-id "$issue_id"); then
    admission_error=$(printf '%s' "$previous_admission" | jq -r '.error // "escalation admission failed"')
    fail "$admission_error"
  fi
fi

{
  printf '%s\n' "You are $role, a consultation-only technical advisor."
  printf '%s\n' 'Use zero tools. Do not inspect files, call functions, browse, fetch, search, spawn, route, implement, or review final work.'
  printf '%s\n' 'Treat the packet below as the complete record. Advice is non-authoritative.'
  printf '%s\n' 'Return exactly one JSON object matching the supplied schema, with no prose or code fences.'
  printf 'POLICY LEVEL: %s\n' "$level"
  printf '%s\n' 'Request only the adjacent next level with reason, unresolved_difficulty and required_resolution; null means stop; extra_high is terminal.'
  printf '%s\n' 'BEGIN ADVISOR PACKET'
  sed -n '1,$p' "$packet"
  printf '%s\n' 'END ADVISOR PACKET'
  if [ -n "$previous_admission" ]; then
    printf '\nVerified previous response and unresolved question:\n'
    printf '%s' "$previous_admission" | jq -c '.previous_response'
  fi
} >"$base_prompt"

plugin_dir=$(CDPATH= cd "$script_dir/.." && pwd) || fail "plugin directory unavailable"
response_schema=$plugin_dir/advisor-response.schema.json
[ -f "$response_schema" ] && [ ! -L "$response_schema" ] || fail "response schema is unavailable"
if ! generated_schema=$(python3 "$script_dir/advisor_config.py" --json _response-schema --level "$level"); then fail "response schema generation failed"; fi
response_schema=$transport_dir/response-schema.json
printf '%s' "$generated_schema" | jq -c ' .schema' >"$response_schema" || fail "response schema generation failed"
validation_class='' validation_field=''

validate_response() {
  candidate=$1 normalized=$2 rendered=$3
  if ! validated=$(python3 "$script_dir/advisor_config.py" --json _validate-response --level "$level" --file "$candidate"); then
    progress "response rejected ($(printf '%s' "$validated" | jq -r ' .error // "invalid response"'))"
    validation_class=invalid-response
    validation_field=response
    return 1
  fi
  printf '%s' "$validated" | jq -c '.response' >"$normalized" || return 1
  jq -r '
    def clean: gsub("\\s+"; " ") | sub("^ "; "") | sub(" $"; "");
    "ADVISOR RESPONSE",
    "RECOMMENDATION: \(.recommendation | clean)",
    "WHY: \(.why | clean)",
    "STRONGEST OBJECTION: \(.strongest_objection | clean)",
    "CHANGE MY MIND: \(.change_my_mind | clean)",
    "ACCEPTANCE CHECKS: \(.acceptance_checks | map(clean) | join("; "))",
    "RISKS: \(.risks | clean)",
    "FOLLOW-UP AREAS: \(.follow_up_areas | clean)"
  ' "$normalized" >"$rendered" || return 1
  [ "$(wc -l <"$rendered" | tr -d ' ')" -eq 8 ]
}

attempt=1
response_verified=false
prompt=$base_prompt
  deadline_ok || fail "consultation deadline exceeded"
  events=$transport_dir/events.$attempt.jsonl
  response=$transport_dir/response.$attempt.json
  evidence=$transport_dir/evidence.$attempt.json
  normalized=$transport_dir/normalized.$attempt.json
  rendered=$transport_dir/rendered.$attempt.txt
  workdir=$transport_dir/workdir.$attempt
  mkdir "$workdir" || fail "isolated work directory creation failed"

  if ! reservation=$(ledger reserve --level "$level" --execution "$consultation_id" --packet "$packet" --parent "$parent_thread_id" --policy "$(printf '%s' "$source_revision" | jq -r '.')" --source "$runtime_source" --supersedes "$supersedes" --reason "$revision_reason" --evidence "$evidence_digest" ${previous_result:+--receipt} ${previous_result:+"$previous_result"}); then
    fail "$(printf '%s' "$reservation" | jq -r '.error // "ledger admission unavailable"')"
  fi
  ledger_binding=$(printf '%s' "$reservation" | jq -c '.ledger') || fail "ledger binding unavailable"
  ledger_reserved=true
  ledger start --execution "$consultation_id" >/dev/null || fail "ledger start persistence unavailable"
  attempt_started_ms=$(now_ms) || fail "attempt timing initialization failed"
  attempt_open=true
  progress "launching $role ($model, $effort, read-only) deadline ${deadline_seconds}s, attempt $attempt of 1"
  # One attempt; selected logical extra_high serializes runtime xhigh.
  python3 "$script_dir/advisor_process.py" --deadline-at "$deadline_at" -- "$codex_bin" exec --json --ignore-user-config --ignore-rules \
    --sandbox read-only --model "$model" -c "model_reasoning_effort=\"$effort\"" \
    -C "$workdir" --skip-git-repo-check --output-schema "$response_schema" \
    --output-last-message "$response" - <"$prompt" >"$events" &
  supervisor_pid=$!
  transport_status=0
  wait "$supervisor_pid" || transport_status=$?
  supervisor_pid=''
  [ "$transport_status" -ne 124 ] || fail "consultation deadline exceeded"
  if [ "$transport_status" -ne 0 ]; then
    fail "codex exec failed"
  fi
  deadline_ok || fail "consultation deadline exceeded"
  [ -f "$events" ] && [ "$(wc -c <"$events" | tr -d ' ')" -le 1000000 ] || fail "transport events exceeded byte limit"
  attempt_finished_ms=$(now_ms) || fail "attempt timing failed"
  attempt_duration_ms=$((attempt_finished_ms - attempt_started_ms))
  attempt_usage=$(python3 "$script_dir/advisor_process.py" usage --events "$events" --duration-ms "$attempt_duration_ms" 2>/dev/null || printf '{"duration_ms":%s,"usage":{"input":null,"cached_input":null,"output":null,"reasoning":null},"availability":{"input":"unavailable","cached_input":"unavailable","output":"unavailable","reasoning":"unavailable"}}' "$attempt_duration_ms")

  child_thread_id=$(jq -r 'select(.type == "thread.started") | .thread_id' "$events" 2>/dev/null) || fail "malformed transport events"
  [ "$(printf '%s\n' "$child_thread_id" | awk 'NF { count += 1 } END { print count + 0 }')" -eq 1 ] || fail "ambiguous child thread"
  [ "$child_thread_id" != "$parent_thread_id" ] || fail "consultation reused the parent thread"
  if [ -n "$previous_admission" ]; then
    [ "$child_thread_id" != "$(printf '%s' "$previous_admission" | jq -r ' .previous_child')" ] || fail "consultation reused previous child thread"
  fi

  progress "inspecting persisted runtime evidence for attempt $attempt"
  set -- --expected-role "$role" --expected-model "$model" --expected-effort "$effort" --expected-parent "$parent_thread_id"
  [ -z "$sessions_dir" ] || set -- --sessions-dir "$sessions_dir" "$@"
  inspection_error=$transport_dir/inspection-error.$attempt
  python3 "$script_dir/advisor_process.py" --deadline-at "$deadline_at" -- sh "$script_dir/inspect-agent-runtime.sh" "$@" "$child_thread_id" >"$evidence" 2>"$inspection_error" &
  supervisor_pid=$!
  inspection_status=0
  wait "$supervisor_pid" || inspection_status=$?
  supervisor_pid=''
  [ "$inspection_status" -ne 124 ] || fail "runtime inspection deadline exceeded"
  if [ "$inspection_status" -ne 0 ]; then
    if grep -Fqx 'ERROR: runtime_provenance_mismatch' "$inspection_error"; then
      fail "runtime_provenance_mismatch"
    fi
    fail "runtime inspection failed"
  fi
  deadline_ok || fail "consultation deadline exceeded"
  [ "$(jq -r '.permission_profile_type' "$evidence")" = "$parent_permission" ] || fail "runtime managed permission provenance mismatch"

  validation_class='' validation_field=''
  if validate_response "$response" "$normalized" "$rendered"; then
    attempt_records=$(jq -cn --argjson prior "$attempt_records" --argjson usage "$attempt_usage" --argjson number "$attempt" '$prior + [{number:$number,outcome:"accepted",duration_ms:$usage.duration_ms,usage:$usage.usage,availability:$usage.availability}]') || fail "usage record construction failed"
    attempt_open=false
    response_verified=true
  else
  attempt_records=$(jq -cn --argjson prior "$attempt_records" --argjson usage "$attempt_usage" --argjson number "$attempt" '$prior + [{number:$number,outcome:"rejected_response",duration_ms:$usage.duration_ms,usage:$usage.usage,availability:$usage.availability}]') || fail "usage record construction failed"
  attempt_open=false
  progress "response validation failed (class=$validation_class field=$validation_field)"
  fail "advisor response failed validation; no corrective retry (class=$validation_class field=$validation_field)"
fi
[ "$response_verified" = true ] || fail "advisor response was not verified"
deadline_ok || fail "consultation deadline exceeded"

progress "consultation verified"
consultation_finished=$(utc_now) || fail "consultation timestamp failed"
consultation_finished_ms=$(now_ms) || fail "consultation timing failed"
total_duration_ms=$((consultation_finished_ms - consultation_started_ms))
metric_rows=$(usage_totals) || fail "usage total construction failed"
totals=$(printf '%s' "$metric_rows" | jq -c '{input:.input.value,cached_input:.cached_input.value,output:.output.value,reasoning:.reasoning.value}') || fail "usage total construction failed"
availability=$(printf '%s' "$metric_rows" | jq -c '{input:.input.availability,cached_input:.cached_input.availability,output:.output.availability,reasoning:.reasoning.availability}') || fail "usage total construction failed"
jq -cn --argjson evidence "$(cat "$evidence")" --rawfile response "$rendered" --argjson advisor_response "$(cat "$normalized")" --arg digest "$packet_digest" --argjson runtime_source "$runtime_source" --argjson ledger "$ledger_binding" \
  --arg level "$level" --arg role "$role" --arg tier "$tier" --arg model "$model" --arg effort "$effort" \
  --arg source "$selection_source" --argjson revision "$selection_revision" --argjson source_revision "$source_revision" --argjson attempts "$attempt_records" --argjson totals "$totals" --arg id "$consultation_id" \
  --argjson availability "$availability" --argjson duration "$total_duration_ms" \
  '{schema_version:4,status:"completed",outcome:"accepted",consultation_id:$id,selection:{tier:$tier,level:$level,role:$role,model:$model,effort:$effort,source:$source,revision:$revision,source_revision:$source_revision,transport_contract_version:"1.6"},attempts:$attempts,usage:{total_duration_ms:$duration,totals:$totals,availability:$availability},runtime:$evidence,response:$response,advisor_response:$advisor_response,escalation:$advisor_response.escalation,packet_identity:{sha256:$digest},runtime_source:$runtime_source,ledger:$ledger}' >"$transport_dir/accepted.json" || fail "accepted envelope construction failed"
python3 "$script_dir/advisor_acceptance.py" --seal "$transport_dir/accepted.json" >"$transport_dir/sealed.json" || fail "launcher acceptance proof unavailable"
ledger accept --execution "$consultation_id" --receipt "$transport_dir/sealed.json" >/dev/null || fail "ledger accepted persistence unavailable; no accepted result published"
ledger_reserved=false
if [ "$journal_enabled" = true ]; then
  progress "writing content-free usage journal"
  journal_record=$(jq -cn --arg id "$consultation_id" --arg started "$consultation_started" --arg finished "$consultation_finished" --arg level "$level" --arg role "$role" --arg tier "$tier" --arg model "$model" --arg effort "$effort" --argjson duration "$total_duration_ms" --argjson attempts "$attempt_records" --argjson totals "$totals" '{schema_version:1,consultation_id:$id,started_at:$started,finished_at:$finished,tier:$tier,model:$model,effort:$effort,outcome:"accepted",transport_contract_version:"1.6",total_duration_ms:$duration,attempts:[$attempts[] | {number,duration_ms,outcome,usage}],totals:$totals}') || journal_record=''
  if [ -z "$journal_record" ] || ! python3 "$script_dir/advisor_config.py" --json _journal-record "$journal_record" >/dev/null 2>&1; then
    printf '%s\n' 'ADVISOR TRANSPORT: warning (usage journal write unavailable)' >&2
  fi
fi
cat "$transport_dir/sealed.json"
