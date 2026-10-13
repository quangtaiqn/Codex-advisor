# shellcheck shell=sh
# Sourced by plugins/advisor/scripts/verify.sh; non-networked source/contract gate.
python3 - "$plugin_dir" "$repo_dir" <<'PY'
import json,sys,tomllib
from pathlib import Path
plugin,repo=map(Path,sys.argv[1:])
schema=json.loads((plugin/'advisor-response.schema.json').read_text())
fields=['recommendation','why','strongest_objection','change_my_mind','acceptance_checks','risks','follow_up_areas','escalation']
assert schema['type']=='object' and schema['additionalProperties'] is False
assert schema['required']==fields and set(schema['properties'])==set(fields)
assert schema['properties']['acceptance_checks']['minItems']==1
esc=schema['properties']['escalation'];assert esc['additionalProperties'] is False
assert set(esc['required'])=={'next_level','reason','unresolved_difficulty','required_resolution'}
assert esc['properties']['next_level']['enum']==[None,'medium','high','extra_high']
assert tomllib.loads((plugin/'advisor.toml').read_text())=={'advisor':{'model':'gpt-6-astra','effort_ladder':['low','medium','high','xhigh']}}
for name in ('advisor-terra','advisor-sol','advisor-astra'):
    role=tomllib.loads((plugin/'agents'/f'{name}.toml').read_text())
    assert role['name']==name and role['model']=='gpt-6-astra' and role['model_reasoning_effort']=='low'
    assert role['sandbox_mode']=='read-only'
    for phrase in ('Use zero tools.','Do not call any tool or function','Do not spawn or route another agent','research-first','FOLLOW-UP AREAS'):
        assert phrase in role['developer_instructions'],(name,phrase)
manifest=json.loads((plugin/'.codex-plugin/plugin.json').read_text())
assert manifest['name']=='advisor' and manifest['version']=='1.4.9-astra.2'
assert manifest['license']=='MIT' and manifest['skills']=='./skills/'
assert not any(k in manifest for k in ('hooks','apps','mcpServers','homepage','repository'))
interface=manifest['interface'];assert interface['category']=='Developer Tools'
for key,suffix in [('websiteURL',''),('supportURL','support/'),('privacyPolicyURL','privacy/'),('termsOfServiceURL','terms/')]:
    assert interface[key]=='https://zerodelta.dev/advisor/'+suffix
assert 'does not automatically receive consultation packets or responses' in interface['longDescription']
assert 'post-execution acceptance check' in interface['longDescription']
market=json.loads((repo/'.agents/plugins/marketplace.json').read_text())
assert market['name']=='advisor' and len(market['plugins'])==1
assert market['plugins'][0]['source']=={'source':'local','path':'./plugins/advisor'}
assert market['plugins'][0]['policy']=={'installation':'AVAILABLE','authentication':'ON_INSTALL'}
assert market['plugins'][0]['category']=='Developer Tools'
models=json.loads((plugin/'models.json').read_text())
assert models['transport_contract_version']=='1.6'
assert models['defaults']=={'standard':{'model':'gpt-6-astra','effort':'low'},'specialist':{'model':'gpt-6-astra','effort':'low'}}
assert {m['model'] for m in models['models']}=={'gpt-5.6-terra','gpt-6.1-sol','gpt-6-astra'}
assert {m['model'] for m in models['models'] if m['tiers']}=={'gpt-6-astra'}
cases=json.loads((plugin/'evals/trigger-cases.json').read_text())['cases']
assert len(cases)==14 and len({c['id'] for c in cases})==14
assert {k:sum(c['class']==k for c in cases) for k in ('consult','skip','boundary')}=={'consult':5,'skip':5,'boundary':4}
assert all(c['expected'] in ('consult','skip') and c['risk'] in ('standard','specialist') and c['prompt'] for c in cases)
assert 'allow_implicit_invocation: true' in (plugin/'skills/consultation/agents/openai.yaml').read_text()
for name in ('LICENSE','NOTICE.md'):
    assert (repo/name).read_bytes()==(plugin/name).read_bytes()
for name in ('advisor_policy.py','advisor_chain.py'):
    assert not (plugin/'scripts'/name).exists()
assert not (plugin/'settings.schema.json').exists()
print('model/schema/roles, metadata/privacy/license and fixed inventory valid')
PY
pass "active structured contracts and immutable role defaults"
for document in "$skill" "$operations" "$repo_dir/SPEC.md" "$repo_dir/INVARIANTS.md" "$readme"; do
  for phrase in 'zero tools' 'research-first' 'FOLLOW-UP AREAS' 'no corrective retry' 'extra_high' 'xhigh' 'cross-session' 'nonterminal' 'schema-v4' 'allowlisted `codex_exec` or `Codex Desktop` provenance'; do
    grep -Fqi "$phrase" "$document" || fail "active contract missing $phrase: $document"
  done
done
for document in "$skill" "$operations"; do
  for phrase in '--previous-result' '--authorize-escalation' '--chain-authorized' 'sandbox_permissions: require_escalated' 'workspace-resolved' 'single-quoted heredoc' 'while (process.session_id)' 'JSON.parse(line)' 'text(JSON.stringify(verifiedEnvelope));'; do
    grep -Fq -- "$phrase" "$document" || fail "launcher/caller contract missing $phrase: $document"
  done
done
for phrase in '--ignore-user-config' '--ignore-rules' '--sandbox read-only --model "$model"' '--expected-parent "$parent_thread_id"' 'model_reasoning_effort=\"$effort\"' 'response validation failed' 'consultation reused the parent thread'; do
  grep -Fq -- "$phrase" "$transport" || fail "transport guard missing: $phrase"
done
for forbidden in hooks .mcp.json .app.json; do [ ! -e "$plugin_dir/$forbidden" ] || fail "forbidden plugin component: $forbidden"; done
if grep -Eq 'auth\.json|bws|get secret' "$transport"; then fail "transport reads credentials"; fi
pass "ownership, zero-tool, primary escalation, terminal transport and durable replay documentation"
