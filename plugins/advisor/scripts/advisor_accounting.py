"""Read-only usage correlation for current and historical transport receipts.

Journal schemas are validated by their shared owner. Accounting is diagnostic,
not an escalation admission token or a durable replay ledger.
"""
from __future__ import annotations
import json
import os
import stat
import sys
import uuid
from advisor_journal import validate_journal_record
from advisor_state import ACTIVE_MODEL, TRANSPORT_CONTRACT_VERSION, ConfigError
from advisor_settings import ROLES, RUNTIME_EFFORTS

def accounting_report(sessions_dir, journal_dir, since, until, parse_time):
    counters = ('input', 'cached_input', 'output', 'reasoning')
    totals = {name: 0 for name in counters}
    availability_rows = {name: [] for name in counters}
    attempts = 0
    correlated, uncorrelated, duplicate, conflicts = ({}, 0, 0, set())

    def depth(value, level=0):
        if level > 32:
            return False
        if isinstance(value, dict):
            return all((depth(item, level + 1) for item in value.values()))
        if isinstance(value, list):
            return all((depth(item, level + 1) for item in value))
        return True

    def valid_count(value):
        return value is None or (isinstance(value, int) and (not isinstance(value, bool)) and (value >= 0))

    def valid_envelope_usage(usage, rows):
        if not isinstance(usage, dict) or set(usage) != {'total_duration_ms', 'totals', 'availability'}:
            return False
        if not isinstance(usage['total_duration_ms'], int) or isinstance(usage['total_duration_ms'], bool) or usage['total_duration_ms'] < 0:
            return False
        if not isinstance(rows, list) or not 1 <= len(rows) <= 2:
            return False
        outcomes = {'accepted', 'rejected_response', 'launch_failed', 'runtime_failed', 'timed_out', 'cancelled'}
        for number, row in enumerate(rows, 1):
            if not isinstance(row, dict) or set(row) != {'number', 'outcome', 'duration_ms', 'usage', 'availability'}:
                return False
            if row['number'] != number or row['outcome'] not in outcomes or (not isinstance(row['duration_ms'], int)) or isinstance(row['duration_ms'], bool) or (row['duration_ms'] < 0):
                return False
            if not isinstance(row['usage'], dict) or set(row['usage']) != set(counters) or any((not valid_count(row['usage'][name]) for name in counters)):
                return False
            if not isinstance(row['availability'], dict) or set(row['availability']) != set(counters):
                return False
        if usage['total_duration_ms'] < sum((row['duration_ms'] for row in rows)):
            return False
        totals_row, available = (usage['totals'], usage['availability'])
        if not isinstance(totals_row, dict) or set(totals_row) != set(counters) or any((not valid_count(totals_row[name]) for name in counters)):
            return False
        if not isinstance(available, dict) or set(available) != set(counters):
            return False
        for name in counters:
            values = [row['usage'][name] for row in rows if row['usage'][name] is not None]
            expected = sum(values) if values else None
            state = 'unavailable' if not values else 'available' if len(values) == len(rows) else 'partial'
            if totals_row[name] != expected or available[name] != state:
                return False
        return True

    def output_text(payload):
        raw = payload.get('output') or payload.get('content')
        if isinstance(raw, list):
            results = []
            for part in raw:
                if not isinstance(part, dict) or part.get('type') not in ('input_text', 'output_text') or (not isinstance(part.get('text'), str)):
                    continue
                try:
                    wrapper = json.loads(part['text'])
                except (json.JSONDecodeError, UnicodeError, RecursionError):
                    continue
                allowed = {'chunk_id', 'exit_code', 'original_token_count', 'output', 'wall_time_seconds'}
                if isinstance(wrapper, dict) and (not set(wrapper) - allowed) and isinstance(wrapper.get('exit_code'), int) and (not isinstance(wrapper.get('exit_code'), bool)) and isinstance(wrapper.get('output'), str) and isinstance(wrapper.get('wall_time_seconds'), (int, float)) and (not isinstance(wrapper.get('wall_time_seconds'), bool)) and (len(wrapper['output'].encode('utf-8')) <= 1000000):
                    results.append((wrapper['output'], wrapper['exit_code']))
            if len(results) == 1:
                return (*results[0], False)
            return (None, None, len(results) > 1)
        return (raw, None, False) if isinstance(raw, str) else (None, None, False)

    def valid_journal(journal):
        try:
            validate_journal_record(journal)
        except ConfigError:
            return False
        return True
    files = []
    directories_seen = 0
    for root, dirs, names in os.walk(sessions_dir):
        directories_seen += 1
        if directories_seen == 1 or directories_seen % 25 == 0:
            print(f'ADVISOR AUDIT: accounting enumerated {directories_seen} directories', file=sys.stderr)
        dirs.sort()
        for name in sorted(names):
            if name.endswith('.jsonl'):
                files.append(os.path.join(root, name))
    print(f'ADVISOR AUDIT: accounting parsing {len(files)} session files', file=sys.stderr)
    sessions = []
    for index, path in enumerate(files, 1):
        if index == 1 or index == len(files) or index % 25 == 0:
            print(f'ADVISOR AUDIT: accounting parsed {index}/{len(files)} files', file=sys.stderr)
        entries = []
        try:
            with open(path, encoding='utf-8') as handle:
                for line_number, raw in enumerate(handle, 1):
                    if line_number % 1000 == 0:
                        print(f'ADVISOR AUDIT: accounting parsed {line_number} records in current file', file=sys.stderr)
                    if len(raw.encode('utf-8')) > 1000000:
                        continue
                    try:
                        entry = json.loads(raw)
                    except (json.JSONDecodeError, UnicodeError, RecursionError):
                        continue
                    if isinstance(entry, dict) and depth(entry):
                        entries.append(entry)
        except (OSError, UnicodeError, RecursionError):
            continue
        ids = {value for entry in entries if entry.get('type') == 'session_meta' and isinstance(entry.get('payload'), dict) and isinstance((value := entry['payload'].get('id')), str)}
        sessions.append((next(iter(ids)) if len(ids) == 1 else None, entries))
    child_runtime = {}
    for session_id, entries in sessions:
        metas = [e['payload'] for e in entries if e.get('type') == 'session_meta' and isinstance(e.get('payload'), dict)]
        contexts = [e['payload'] for e in entries if e.get('type') == 'turn_context' and isinstance(e.get('payload'), dict)]
        if session_id and len(metas) == 1 and contexts and (metas[0].get('source') == 'exec') and (metas[0].get('originator') in ('codex_exec', 'Codex Desktop')):
            child_runtime[session_id] = (metas[0], contexts, entries)
    candidates = []
    for parent_id, entries in sessions:
        invocation_ids = set()
        for entry in entries:
            payload = entry.get('payload')
            if entry.get('type') == 'response_item' and isinstance(payload, dict) and (payload.get('type') in ('function_call', 'custom_tool_call')):
                arguments = payload.get('arguments') or payload.get('input')
                if payload.get('name') in ('exec', 'functions.exec', 'exec_command', 'run_advisor') and isinstance(arguments, str) and ('run-advisor.sh' in arguments):
                    call_id = payload.get('call_id') or payload.get('id')
                    if isinstance(call_id, str):
                        invocation_ids.add(call_id)
        for entry in entries:
            payload = entry.get('payload')
            stamp = parse_time(entry.get('timestamp') or (payload.get('timestamp') if isinstance(payload, dict) else None))
            if stamp is None or not since <= stamp < until or entry.get('type') != 'response_item' or (not isinstance(payload, dict)) or (payload.get('type') not in ('function_call_output', 'custom_tool_call_output')):
                continue
            raw, tool_exit, ambiguous = output_text(payload)
            output_call_id = payload.get('call_id') or payload.get('id')
            invocation_proven = output_call_id in invocation_ids
            if ambiguous and invocation_proven:
                uncorrelated += 1
                continue
            if not isinstance(raw, str) or len(raw.encode()) > 1000000:
                continue
            try:
                envelope = json.loads(raw)
            except (json.JSONDecodeError, UnicodeError, RecursionError):
                continue
            if not isinstance(envelope, dict) or not depth(envelope):
                if invocation_proven:
                    uncorrelated += 1
                continue
            candidates.append((parent_id, invocation_proven, tool_exit, envelope))
    for parent_id, invocation_proven, tool_exit, envelope in candidates:
        identifier, selection, runtime = (envelope.get('consultation_id'), envelope.get('selection'), envelope.get('runtime'))
        usage, rows = (envelope.get('usage'), envelope.get('attempts'))
        try:
            identifier_valid = isinstance(identifier, str) and uuid.UUID(identifier).version == 4
        except (ValueError, AttributeError):
            identifier_valid = False
        proven = invocation_proven and tool_exit in (None, 0) and (envelope.get('schema_version') in (3, 4)) and identifier_valid and isinstance(selection, dict) and (selection.get('transport_contract_version') in ('1.4', '1.5', TRANSPORT_CONTRACT_VERSION)) and isinstance(runtime, dict) and (runtime.get('transport') == 'codex-exec') and (runtime.get('parent_thread_id') == parent_id) and (runtime.get('model') == selection.get('model')) and (runtime.get('effort') == selection.get('effort')) and valid_envelope_usage(usage, rows)
        child = child_runtime.get(runtime.get('thread_id')) if isinstance(runtime, dict) else None
        if proven and child:
            _meta, contexts, child_entries = child
            tool_events = [item for entry in child_entries for item in (entry, entry.get('payload')) if isinstance(item, dict) and item.get('type') in ('function_call', 'custom_tool_call', 'collab_tool_call', 'tool_call', 'tool_use')]
            proven = runtime.get('thread_id') != parent_id and (not tool_events) and all((c.get('model') == selection.get('model') and c.get('effort') == selection.get('effort') and isinstance(c.get('sandbox_policy'), dict) and (c['sandbox_policy'].get('type') == 'read-only') for c in contexts))
        elif proven:
            proven = False
        if proven and selection.get('transport_contract_version') == TRANSPORT_CONTRACT_VERSION:
            level, role = (selection.get('level'), selection.get('role'))
            role_allowed = role in ROLES if selection.get('tier') == 'advisor' else role == 'advisor-compatibility-test' and selection.get('tier') == 'compatibility-test'
            prompts = [''.join((item.get('text', '') for item in entry['payload'].get('content', []) if isinstance(item, dict) and item.get('type') == 'input_text')) for entry in child_entries if isinstance(entry.get('payload'), dict) and entry['payload'].get('type') == 'message' and (entry['payload'].get('role') == 'user')]
            proven = isinstance(level, str) and level in RUNTIME_EFFORTS and role_allowed and (selection.get('model') == ACTIVE_MODEL) and (selection.get('effort') == RUNTIME_EFFORTS[level]) and (runtime.get('agent_role') == role) and (len(prompts) == 1) and prompts[0].startswith(f'You are {role}, a consultation-only technical advisor.\n') and (runtime.get('sandbox_policy_type') == 'read-only') and (len(rows) == 1) and (envelope.get('outcome') == 'accepted') and (rows[0].get('outcome') == 'accepted') and all((isinstance(c.get('permission_profile'), dict) and c['permission_profile'].get('type') == runtime.get('permission_profile_type') for c in contexts))
        totals_row = usage.get('totals') if isinstance(usage, dict) else None
        if not proven or not isinstance(totals_row, dict) or set(totals_row) != set(counters) or any((not valid_count(totals_row[name]) for name in counters)):
            uncorrelated += 1
            continue
        if identifier in conflicts:
            uncorrelated += 1
            continue
        if identifier in correlated:
            if correlated[identifier] == envelope:
                duplicate += 1
            else:
                conflicts.add(identifier)
                correlated.pop(identifier)
                uncorrelated += 2
            continue
        correlated[identifier] = envelope
    journal_only = []
    if journal_dir:
        print('ADVISOR AUDIT: journal parsing started', file=sys.stderr)
        try:
            journal_names = sorted(os.listdir(journal_dir))
        except OSError:
            journal_names = []
        for index, name in enumerate(journal_names, 1):
            if index == 1 or index == len(journal_names) or index % 25 == 0:
                print(f'ADVISOR AUDIT: journal parsed {index}/{len(journal_names)} records', file=sys.stderr)
            if not name.endswith('.json'):
                continue
            path = os.path.join(journal_dir, name)
            try:
                info = os.lstat(path)
                if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_size > 1000000:
                    continue
                with open(path, encoding='utf-8') as handle:
                    journal = json.load(handle)
            except (OSError, json.JSONDecodeError, UnicodeError, RecursionError):
                continue
            if not valid_journal(journal):
                uncorrelated += 1
                continue
            identifier = journal.get('consultation_id') if isinstance(journal, dict) else None
            stamp = parse_time(journal.get('finished_at')) if isinstance(journal, dict) else None
            if stamp is None or not since <= stamp < until:
                continue
            if identifier in correlated:
                envelope = correlated[identifier]
                agrees = journal['totals'] == envelope['usage']['totals'] and journal['model'] == envelope['selection']['model'] and (journal['effort'] == envelope['selection']['effort']) and (journal['outcome'] == envelope.get('outcome'))
                if agrees:
                    duplicate += 1
                else:
                    uncorrelated += 1
            else:
                journal_only.append(journal)
                uncorrelated += 1
    for envelope in correlated.values():
        attempts += len(envelope['attempts'])
        for name in counters:
            value = envelope['usage']['totals'][name]
            availability_rows[name].append(envelope['usage']['availability'][name])
            if value is not None:
                totals[name] += value
    availability = {name: 'unavailable' if not rows or all((state == 'unavailable' for state in rows)) else 'available' if all((state == 'available' for state in rows)) else 'partial' for name, rows in availability_rows.items()}
    journal_totals = {name: sum((row['totals'][name] for row in journal_only if row['totals'][name] is not None)) for name in counters}
    journal_availability = {name: 'unavailable' if not journal_only or all((row['totals'][name] is None for row in journal_only)) else 'available' if all((row['totals'][name] is not None for row in journal_only)) else 'partial' for name in counters}
    report = {'schema_version': 2, 'mode': 'exec-accounting', 'consultations': len(correlated), 'attempts': attempts, 'usage': {'totals': {name: totals[name] if availability[name] != 'unavailable' else None for name in counters}, 'availability': availability}, 'journal_only': {'consultations': len(journal_only), 'usage': {'totals': {name: journal_totals[name] if journal_availability[name] != 'unavailable' else None for name in counters}, 'availability': journal_availability}}, 'coverage': {'correlated': len(correlated), 'uncorrelatable': uncorrelated, 'deduplicated': duplicate}}
    return report
