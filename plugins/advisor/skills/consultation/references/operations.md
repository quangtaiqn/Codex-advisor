# Phase-B operations

Resolve the absolute installed plugin root from the loaded skills/consultation/SKILL.md (two directories above). Every helper must be a regular, nonsymlinked file. For real use, invoke only that fixed installed-plugin root with sandbox_permissions: require_escalated and a narrow justification for one read-only child. Nested Codex app-server initialization needs this boundary; elevation applies only to the fixed launcher. Never elevate a workspace-resolved repository-relative script or use a workspace-writable packet file. These rules do not install this repository candidate.

Prepare repository or web research and source references before consultation. Resolve source/sessions with advisor_transport.py --runtime and pass that same sessions directory to inspect-parent-runtime.sh; use CODEX_THREAD_ID, never CODEX_SESSION_ID. If parent evidence is unavailable, stop. Non-Codex surfaces use route: unavailable.

New issue:

```sh
/bin/sh <absolute-installed-plugin-root>/scripts/run-advisor.sh --ledger-dir /absolute/linux-private/ledger --project-root /absolute/project --issue-id stable-issue --level low <<'ADVISOR_PACKET'
DECISION
<one unresolved material question>
CONTEXT
<bounded evidence and source references>
OPTIONS
<competing choices>
BOUNDARIES
<ownership, safety and acceptance constraints>
REQUEST
<the difficulty to resolve>
ADVISOR_PACKET
# Supported initial aliases: --tier standard, --tier specialist,
# --role advisor-terra, --role advisor-sol, --role advisor-astra.
```

After an accepted low response requests medium, the primary verifies the material need, persists the actual envelope in a private receipt file outside the workspace, and invokes the same original packet with `--level medium --previous-result /absolute/private/low.json --authorize-escalation`. Repeat only an adjacent requested level. The receipt supplement is only the verified previous response and unresolved question; the original packet digest is unchanged. Changing a role or tier cannot authorize a skip/repeat/reset. --chain-authorized and checkpoint/qualification flags are rejected.

Use a single-quoted heredoc after proving its delimiter is absent from the packet. Never use `< packet.txt`, an unquoted heredoc, `eval` or shell-interpolated packet content for elevated inference. Do not stage the packet in a workspace-writable file. Zero-tool advisors cannot fetch missing evidence or perform follow-up work; accepting a research-first plan means accepting that plan, not a technical choice the advisor did not make.

The root owns architecture, implementation routing, verification, and acceptance. Advisors are read-only, non-authoritative, use zero tools, and never delegate, implement, deploy, or perform final review. The root performs any repository or web research and includes relevant evidence and source references in a bounded decision packet. When evidence is insufficient, the advisor may recommend only a concrete research-first next step and list missing evidence under FOLLOW-UP AREAS, outside this consultation. An unavailable result cannot be rescued by a higher level or a fallback model.

The sole supported wrapper model-output format is one JSON object. Wrapper-owned semantic validation checks exact keys, types, nonblank strings/checks, duplicate fields and structured escalation before rendering the canonical eight-line ADVISOR RESPONSE receipt. This redacted failure boundary never publishes rejected content. One command launches at most one child and one attempt; no corrective retry occurs. A chain can use at most four adjacent levels, once each, under primary control. Runtime inspection must prove a distinct Codex consultation thread, the exact selected role/model/effort, read-only isolation, managed permission provenance and zero tool calls, with allowlisted `codex_exec` or `Codex Desktop` provenance. A tool call is rejected after execution; this is not preventive tool isolation and cannot undo data already processed by a prohibited tool.

Standard/Specialist and advisor-terra/advisor-sol/advisor-astra are supported wrapper entrypoints, all starting gpt-6-astra/low. Tier/role changes do not authorize a new level or reset the issue budget. Direct/native role invocation is unsupported; use the fixed launcher and its verified receipt. Model/catalog declarations are documentation, not live capability or entitlement proof. No model/effort fallback is permitted.

Each issue starts low. Higher calls require an accepted previous result, an adjacent escalation.next_level with nonblank reason, unresolved_difficulty and required_resolution, and the primary's confirmation that material uncertainty remains after cheap local evidence. Use --previous-result RECEIPT --authorize-escalation with --level medium|high|extra_high. Admission rechecks current parent, exact child/session, policy/transport revision, packet digest, persisted prompt/role/level and response, model/effort, isolation, tools and permission provenance before spawn. A Boolean --chain-authorized flag cannot grant admission. extra_high is logical terminal; runtime effort is xhigh. xhigh is a boundary alias, not a fifth budget. next_level=null stops immediately; return the best result and uncertainty at the terminal level. Transport failures, malformed responses, timeout/cancellation, provenance/model/effort mismatch and tool use are terminal; higher effort cannot repair them.

Phase B uses a durable owner-private ledger for cross-session at-most-once admission, concurrent reservation, receipt consumption and canonical-packet deduplication. Every launch requires a provisioned --ledger-dir, stable --issue-id and Git --project-root. Reservation commits before spawn; crash, failure or unknown consumes the level permanently. Explicit reconcile never spawns a replacement; transfer requires old/new parent proof. Retention preserves consumed tombstones. The trusted owner can alter all state; filesystem rollback across every marker is outside this guarantee. See docs/stage-b-ledger-contract.md and the packaged operations reference for identity, storage, migration and recovery.

The fixed launcher retains --ignore-user-config, --ignore-rules, --sandbox read-only and an isolated workdir. Python 3.11+ runtime preflight precedes helper import/provider launch; Vulture's Python 3.14 is a separate verification toolchain. Deadline, output/packet/queue bounds and child process supervision remain enabled. Startup ownership/cancel-request guards establish ownership before cleanup; an unconditional exit trap removes only the owned mode-0700 consultation directory under Codex home. Preexisting paths and unrelated processes are preserved. Uncatchable termination can leave state; do not infer that no child spawned and do not retry it.

Transport resolution is shared by launch, discovery, doctor, version probes, canary and inspectors: valid ADVISOR_CODEX_BIN, then a valid private installed WSL bridge, then PATH. Invalid explicit overrides fail without fallback. Binary/source/sessions_directory are kept together. The bridge retains checksum, owner/mode and symlink checks, bounded preflight and path conversion. Do not reinstall a bridge or modify Windows/WSL configuration to repair a test.

Envelope schema_version=4 extends the existing shape with selection.level/role, advisor_response, escalation, packet_identity and runtime_source. transport_contract_version=1.6 does not accept old receipts for admission. stdout has exactly one final JSON envelope; progress stays on stderr. Failures keep truthful outcome/attempt/usage data, with unavailable counters represented as null. A nonempty session_id is nonterminal: drain the exact handle with write_stdin before parsing exactly one schema-v4 envelope. Outer functions.wait updates are nonterminal progress, not final receipts.

The optional content-free usage journal is disabled by default, uses owner-only locked storage and enforces byte/count/30-day retention bounds. Its B writer emits contract 1.6 with advisor/compatibility-test semantics and one attempt; the reader preserves historical tiers/outcomes/contracts without relabeling them. Failure/cancellation usage is retained. Catalog or journal state cannot authorize escalation.

## Drain the shell handoff

```javascript
let process = await tools.exec_command({cmd: transportCommand});
let combinedOutput = process.output ?? "";
while (process.session_id) {
  process = await tools.write_stdin({
    session_id: process.session_id,
    chars: "",
    yield_time_ms: 5000,
    max_output_tokens: 20000,
  });
  combinedOutput += process.output ?? "";
}
if (process.session_id || process.exit_code == null) {
  throw new Error("Advisor transport did not reach a terminal result");
}
if (process.exit_code !== 0) {
  throw new Error("Advisor transport failed");
}
const candidates = combinedOutput.split(/\r?\n/).flatMap((line) => {
  try { return [JSON.parse(line)]; } catch { return []; }
}).filter((value) => value && value.schema_version === 4);
if (candidates.length !== 1) {
  throw new Error("Advisor transport did not return exactly one schema-v4 envelope");
}
const verifiedEnvelope = candidates[0];
text(JSON.stringify(verifiedEnvelope));
```

The initial yielded result is nonterminal progress; an outer functions.wait update is nonterminal too. Drain the same session_id with write_stdin, retain all chunks, then parse and deliver exactly one schema-v4 envelope. No receipt is accepted before terminal exit.

## Visible lifecycle

```text
ADVISOR DECISION
route: consult | skip | unavailable
reason: <material uncertainty or skip reason>

ADVISOR CALL
status: running
role: <resolved supported role>
level: <admitted level>
model: gpt-6-astra
effort: <resolved runtime effort>
isolation: read-only

ADVISOR RESULT
status: completed | unavailable
recommendation: <accepted recommendation or unavailable>
decision: accept | modify | reject | blocked
```

For skip/unavailable emit only ADVISOR DECISION unless a child was actually launched. A distinct Codex consultation thread remains the inspectable detailed record. Do not route completion or final review to an advisor. Recovery after an unknown/timeout/cancel outcome is a safe stop, not a retry. Durable reservation/reconcile and cross-session replay protection are implemented by the B ledger; unknown never releases quota.

Installer retirement paths such as `.retired-v1.3.0-zero-tool` preserve known historical roles; unknown content, symlinks and collision states fail before mutation. User settings, bridge configuration, installed plugin and session model are not altered by this repository integration.

## Attended evaluator and evidence limits

The optional evaluate-triggers.sh evaluator compares the multi_agent_v2 disabled/enabled paths with isolated projects and the same fixed Astra/low role pairs. Its ephemeral root has no persisted parent rollout, so preflight returns route: unavailable with no `ADVISOR CALL` or child spawn. That unavailable result must not count as successful consultation qualification. Deterministic parsing and persisted fixtures test role/model/effort, lifecycle, redaction and accounting; they are fixture proof, not live reasoning proof.

Live --run use requires separate user authorization, subscription-only confirmation and disabled overage. Do not handle auth files, override parent credentials, enable paid overage or modify the installed plugin. The pooled evaluation budget is 40 root sessions across feature paths; only eligible boundary mismatches have bounded reruns, which do not authorize a consultation retry. Progress goes to stderr; result JSON is file-only. Scoped before/after digests cover config.toml, agents, skills, plugins and marketplace metadata, excluding auth/session/cache data. Snapshot traversal reports progress before reading and every 100 files. An unavailable result preserves paired nonmutation evidence. Attended evaluation is a separate authorization; a bounded technical smoke permission does not authorize the evaluator or retries.

Acceptance proof (A): successful launcher envelopes include `acceptance_proof`
(`hmac-sha256-v1`) covering the complete envelope. The launcher creates a random,
owner-only key at `$CODEX_HOME/.tmp/advisor-acceptance/key` only after acceptance;
admission requires the existing safe key and a matching proof, plus current
parent/source/policy/packet and persisted runtime/response checks. Missing,
changed, linked or broadly readable keys fail closed; they are never recreated
by admission. Do not print, package or share that key. Repository helpers and the
Codex-home filesystem owner are trusted; this does not defend against that owner
rewriting the key/code/sessions. The key stores no packet, response, receipt list,
quota, reservation, consumed token or resume state. B additionally binds this authenticated receipt to its persisted ledger execution; consuming it and reserving the next level are one durable transaction. Replaying, cloning or renaming it never restores quota.

## Durable ledger operations (B)

Before the first B launch, the primary provisions one stable owner namespace on a persistent Linux filesystem, outside the checkout. Parent directories must already be trusted, nonsymlinked, not group/world writable (a sticky ancestor is allowed, but fixture state also uses persistent Linux storage). Do not use DrvFS or use init to recover missing state. Example:

```sh
python3 <absolute-fixed-plugin-root>/scripts/advisor_ledger.py --ledger-dir /home/owner/advisor-ledger init
python3 <absolute-fixed-plugin-root>/scripts/advisor_ledger.py --ledger-dir /home/owner/advisor-ledger status
```

Every launcher call includes `--ledger-dir /home/owner/advisor-ledger --project-root /absolute/git/project --issue-id stable-issue`. A shared project identity uses its real Git common directory across worktrees. Changing project checkout, role, tier, parent, issue name, receipt path or whitespace does not create another quota for the canonical packet in this namespace. Canonicalization uses UTF-8/NFC, collapsed per-line whitespace, empty-line removal and normalized ISO date/datetime tokens; order and other content remain significant. It does not detect every semantic paraphrase. Primary chooses a materially new issue honestly; an explicit revision uses `--supersedes old-id --revision-reason 'new material evidence' --evidence-digest SHA256`, a new ID and a different canonical packet. A timestamp-only edit cannot justify another Low.

Reservation is linearized under a bounded exclusive flock on a permanent owner-only lock inode. Registry writes use complete-write loops, file fsync, atomic replace through a no-follow directory descriptor and directory fsync. Only then can the launcher mark started and spawn. One reservation has one launcher PID/starttime/boot identity. Crashes before/after spawn, failure, timeout and cancellation consume quota. Persistence failure never publishes accepted, even when provider output was valid. No reset, quota release or corrective retry exists.

State files have strict UID/mode (directory0700/files0600), no-follow/nlink1, checksum/version/epoch checks and bounded size. An explicit init writes the epoch marker; missing registry after init is an error. The registry is capped at1024 issues/8MiB and stops safely when full. Prune retains all issue/canonical/execution/level/receipt tombstones. Plaintext packets and session logs are not stored in the ledger; IDs, digests, source paths and process/provenance metadata remain local and can still reveal associations. The optional usage journal is separate and never grants launch authority.

Diagnostics are read-only. With a known dead launcher, reconcile never spawns a replacement:

```sh
python3 <absolute-fixed-plugin-root>/scripts/advisor_ledger.py --ledger-dir /home/owner/advisor-ledger --project-root /absolute/git/project --issue-id stable-issue reconcile --execution EXECUTION_ID
# Complete proof permits finalizing the SAME execution:
python3 <absolute-fixed-plugin-root>/scripts/advisor_ledger.py --ledger-dir /home/owner/advisor-ledger --project-root /absolute/git/project --issue-id stable-issue reconcile --execution EXECUTION_ID --receipt /absolute/private/receipt.json --packet /absolute/private/original.txt --sessions-dir /absolute/sessions
```

The receipt remains authenticated against persisted runtime and the recorded parent/source/raw packet/policy. Missing proof stays unknown and blocks all reuse. PID reuse does not grant ownership. Reconcile performs no process cleanup. A terminal accepted execution can be inspected idempotently; without its receipt, status does not reconstruct a receipt or grant escalation.

Resume on a new parent requires `transfer --receipt /absolute/private/receipt.json --packet /absolute/private/original.txt --parent NEW_PARENT --sessions-dir /absolute/sessions` with the common ledger/project/issue options and real CODEX_THREAD_ID of the new parent. Old receipt/runtime guards are checked with old parent proof, new parent is independently inspected, and an inactive accepted chain is required. Transfer does not reset levels or change packet/policy. CLI packet files here are private LOCAL diagnostics, not files for an elevated inference call; live launcher packets still use the single-quoted heredoc rule above.

A envelope3/transport1.5 history is readable but cannot authorize B. Before adopting a known pending A chain, import its authenticated receipt and original private packet using `import-a --receipt PATH --packet PATH --sessions-dir DIR` with the common ledger/project/issue options. Import re-inspects A runtime and writes a closed tombstone, never a B continuation. Unknown legacy registries are preserved for backup/quarantine and explicit migration review; no automatic rewrite/reset occurs. Errors leave the original legacy receipt/state untouched. No database can infer all prior A activity when the owner does not supply its history.

`prune` removes optional runtime detail only on closed issues; consumed identity indices are permanent. Deleting details, uninstalling, reinstalling, journal clear or moving sessions is not permission to start again. The trusted owner can delete/rollback every marker, state and key or provision another namespace; this system has no external monotonic authority to detect that. Preserve a complete namespace backup when moving machines; independent-owner or independently provisioned namespaces are outside the replay guarantee. Do not log the acceptance key, authentication material or raw sessions.
