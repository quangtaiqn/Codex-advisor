#!/bin/sh
# Emit only allowlisted identity/isolation evidence for one exact, zero-tool advisor rollout.

set -eu
fail() { printf '%s\n' "ERROR: $*" >&2; exit 1; }

sessions_dir='' expected_role='' expected_model='' expected_effort='' expected_parent='' thread_id=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --sessions-dir) [ "$#" -ge 2 ] || fail "--sessions-dir requires DIR"; sessions_dir=$2; shift 2 ;;
    --expected-role) [ "$#" -ge 2 ] || fail "--expected-role requires ROLE"; expected_role=$2; shift 2 ;;
    --expected-model) [ "$#" -ge 2 ] || fail "--expected-model requires MODEL"; expected_model=$2; shift 2 ;;
    --expected-effort) [ "$#" -ge 2 ] || fail "--expected-effort requires EFFORT"; expected_effort=$2; shift 2 ;;
    --expected-parent) [ "$#" -ge 2 ] || fail "--expected-parent requires THREAD_ID"; expected_parent=$2; shift 2 ;;
    --*) fail "unknown argument: $1" ;;
    *) [ -z "$thread_id" ] || fail "only one THREAD_ID is allowed"; thread_id=$1; shift ;;
  esac
done
[ -n "$expected_effort" ] || expected_effort=low
[ -n "$thread_id" ] && [ -n "$expected_role" ] && [ -n "$expected_model" ] && [ -n "$expected_parent" ] || fail "usage: inspect-agent-runtime.sh [--sessions-dir DIR] --expected-role ROLE --expected-model MODEL [--expected-effort EFFORT] --expected-parent THREAD_ID THREAD_ID"
printf '%s\n' "$expected_model" | LC_ALL=C grep -Eq '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$' || fail "unsafe expected model"
case "$expected_effort" in none|minimal|low|medium|high|xhigh|max|ultra) ;; *) fail "unsupported expected effort" ;; esac
printf '%s\n' "$thread_id" | LC_ALL=C grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' || fail "THREAD_ID must be a lowercase UUID"
printf '%s\n' "$expected_parent" | LC_ALL=C grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' || fail "expected parent must be a lowercase UUID"
[ "$thread_id" != "$expected_parent" ] || fail "advisor thread must differ from parent"
if [ -z "$sessions_dir" ]; then
  if [ -n "${CODEX_HOME-}" ]; then sessions_dir=$CODEX_HOME/sessions
  else [ -n "${HOME-}" ] || fail "HOME is unset"; sessions_dir=$HOME/.codex/sessions
  fi
fi
[ -d "$sessions_dir" ] || fail "sessions directory unavailable"

matches=$(find "$sessions_dir" -type f -name "rollout-*-$thread_id.jsonl" -print) || fail "rollout enumeration failed"
[ "$(printf '%s\n' "$matches" | awk 'NF {count++} END {print count+0}')" -eq 1 ] || fail "expected exactly one rollout match"
rollout=$matches

if jq -e -s '
  [ .[] | select(.type=="session_meta") | .payload ] as $s |
  ($s|length)==1 and ($s[0]|type)=="object" and
  (($s[0].originator // null) != "codex_exec" and ($s[0].originator // null) != "Codex Desktop")
' "$rollout" >/dev/null 2>&1; then
  fail "runtime_provenance_mismatch"
fi

jq -ce -s --arg id "$thread_id" --arg expected_parent "$expected_parent" --arg expected_role "$expected_role" --arg expected_model "$expected_model" --arg expected_effort "$expected_effort" '
  # CLI bootstrap context is persisted as user content, distinct from user.text.
  # Only known typed content in the same isolated cwd/turn may be excluded.
  def native_turn($turns; $cwd):
    . as $meta |
    ($cwd|type)=="string" and ($meta|type)=="object" and
    ($meta.turn_id|type)=="string" and ($meta.turn_id|length)>0 and
    any($turns[]; .turn_id==$meta.turn_id and .cwd==$cwd);
  def environment($cwd):
    [capture("\\A<environment_context>\\s*<cwd>(?<cwd>[^<>]*)</cwd>(?:(?!</?(?:environment_context|cwd)\\b|<!--|-->).)*</environment_context>\\s*\\z";"m")] as $matches |
    ($matches|length)==1 and $matches[0].cwd==$cwd;
  def prompt_content:
    .content as $c |
    ($c|type)=="array" and ($c|length)==1 and ($c[0]|type)=="object" and
    $c[0].type=="input_text" and ($c[0].text|type)=="string";
  def consultation($turns; $cwd):
    prompt_content and
    (if has("internal_chat_message_metadata_passthrough") then
       .internal_chat_message_metadata_passthrough as $meta |
       ($meta|native_turn($turns; $cwd)) and $meta.content_item_kinds==["user.text"]
     else true end);
  def bootstrap($turns; $cwd):
    .internal_chat_message_metadata_passthrough as $meta | .content as $c |
    ($meta|native_turn($turns; $cwd)) and ($c|type)=="array" and
    (($meta.content_item_kinds==["environments.environment_context"] and ($c|length)==1) or
     ($meta.content_item_kinds==["agents_md.instructions","environments.environment_context"] and ($c|length)==2 and
      ($c[0].text|test("\\A# AGENTS[.]md instructions\\n\\n<INSTRUCTIONS>\\n(?:(?!</?INSTRUCTIONS\\b).)*\\n</INSTRUCTIONS>\\s*\\z";"m")))) and
    all($c[]; .type=="input_text" and (.text|type)=="string" and
        (.text|contains("BEGIN ADVISOR PACKET")|not) and (.text|contains("END ADVISOR PACKET")|not)) and
    ($c[-1].text|environment($cwd));
  [ .[] | select(.type=="session_meta") | .payload ] as $s |
  [ .[] | select(.type=="turn_context") | .payload ] as $t |
  if ($s|length)!=1 or ($t|length)==0 then error("missing metadata") else
    [$t[].model] as $m | [$t[].effort] as $e |
    [$t[].sandbox_policy.type] as $b | [$t[].permission_profile.type] as $p |
    [ .[] | select(.type=="response_item" and .payload.type=="message" and .payload.role=="user") | .payload ] as $users |
    [range(0; $users|length) | select($users[.]|bootstrap($t; $s[0].cwd))] as $bootstrap_indices |
    [$users[] | select((bootstrap($t; $s[0].cwd) or consultation($t; $s[0].cwd))|not)] as $invalid_users |
    [$users[] | select(consultation($t; $s[0].cwd)) | .content[0].text] as $prompts |
    [ .[] | .. | objects | .type? |
      select(. == "function_call" or . == "custom_tool_call" or . == "collab_tool_call" or . == "tool_call" or . == "tool_use") ] as $tool_events |
    [ .[] | .. | objects |
      select((((.type? | type) == "string") and (.type | test("reroute|migration"; "i"))) or has("rerouted_model") or has("model_migration")) ] as $reroute_events |
    if $s[0].id!=$id or $s[0].source!="exec" or
       ($s[0].originator!="codex_exec" and $s[0].originator!="Codex Desktop") or
       ($s[0].agent_role // null)!=null or ($s[0].parent_thread_id // null)!=null or
       ($bootstrap_indices!=[] and $bootstrap_indices!=[0]) or
       ($invalid_users|length)!=0 or
       ($prompts|length)!=1 or ($prompts[0] | startswith("You are " + $expected_role + ", a consultation-only technical advisor.\n") | not) or
       ($m|unique)!=[$expected_model] or ($e|unique)!=[$expected_effort] or
       ($b|unique)!=["read-only"] or ($p|unique|length)!=1 or
       any($p[]; type!="string" or length==0) or ($tool_events|length)!=0 or ($reroute_events|length)!=0
    then error("unexpected, non-read-only, or tool-using advisor evidence")
    else {
      thread_id:$s[0].id,
      parent_thread_id:$expected_parent,
      agent_role:$expected_role,
      transport:"codex-exec",
      model:$m[0], effort:$e[0],
      sandbox_policy_type:$b[0], permission_profile_type:$p[0]
    } end
  end
' "$rollout" 2>/dev/null || fail "rollout lacks exact allowlisted advisor evidence"
