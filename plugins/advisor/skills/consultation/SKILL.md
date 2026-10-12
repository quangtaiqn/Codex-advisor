---
name: consultation
description: Use for an approved-plan checkpoint or an explicit standalone advisor, second-opinion, architecture-review or authorization challenge only when cheap local evidence leaves unresolved uncertainty with material impact. Skip routine work, final review, completion, settled decisions and no-delegation requests.
---

# Advisor consultation — Astra low-first

The root owns architecture, implementation routing, verification, and acceptance.

Preflight every approved-plan checkpoint. Do clear routine work directly. A material unresolved architecture/interface/data-model, cross-module compatibility or concurrency, competing diagnosis, security/privacy/authorization, migration/recovery or irreversible-state question can earn one bounded chain before implementation. A borderline case skips unless the need is demonstrated. Standalone consultation requires explicit advisor invocation. Factual/status/summarization, mechanical edits, formatting/renaming/docs synchronization, settled-plan execution, completion and final review owned elsewhere never earn a new consultation. A no-delegation instruction wins. Do not consult for reassurance or consensus. Once implementation begins, do not reopen the same checkpoint's chain to fix transport or implementation failures.

Standard consultation and Specialist consultation are supported entrypoint names, not model tiers or escalation budgets. Generic advisor requests start low too. Security adjacency or project importance alone is insufficient; targeted evidence must leave unresolved a material difficulty. All routes use gpt-6-astra/low initially, regardless of parent model and sandbox.

Resolve the absolute installed plugin root from the loaded skills/consultation/SKILL.md (two directories above). Every helper must be a regular, nonsymlinked file. For real use, invoke only that fixed installed-plugin root with sandbox_permissions: require_escalated and a narrow justification for one read-only child. Nested Codex app-server initialization needs this boundary; elevation applies only to the fixed launcher. Never elevate a workspace-resolved repository-relative script or use a workspace-writable packet file. These rules do not install this repository candidate.

Prepare repository or web research and source references before consultation. Resolve source/sessions with advisor_transport.py --runtime and pass that same sessions directory to inspect-parent-runtime.sh; use CODEX_THREAD_ID, never CODEX_SESSION_ID. If parent evidence is unavailable, stop. Non-Codex surfaces use route: unavailable.

New issue:

```sh
/bin/sh <absolute-installed-plugin-root>/scripts/run-advisor.sh --level low <<'ADVISOR_PACKET'
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

Phase A has no durable checkpoint ledger, crash-resume/reconcile, cross-session replay prevention or concurrent duplicate admission. The primary tracks level usage within the current session. A receipt is navigation evidence, not a consumed token; phase B will implement durable at-most-once admission, tombstones/retention, resume and replay protection only after separate approval. This limitation does not weaken one-attempt transport, adjacent transition checks, or ownership.

The fixed launcher retains --ignore-user-config, --ignore-rules, --sandbox read-only and an isolated workdir. Python 3.11+ runtime preflight precedes helper import/provider launch; Vulture's Python 3.14 is a separate verification toolchain. Deadline, output/packet/queue bounds and child process supervision remain enabled. Startup ownership/cancel-request guards establish ownership before cleanup; an unconditional exit trap removes only the owned mode-0700 consultation directory under Codex home. Preexisting paths and unrelated processes are preserved. Uncatchable termination can leave state; do not infer that no child spawned and do not retry it.

Transport resolution is shared by launch, discovery, doctor, version probes, canary and inspectors: valid ADVISOR_CODEX_BIN, then a valid private installed WSL bridge, then PATH. Invalid explicit overrides fail without fallback. Binary/source/sessions_directory are kept together. The bridge retains checksum, owner/mode and symlink checks, bounded preflight and path conversion. Do not reinstall a bridge or modify Windows/WSL configuration to repair a test.

Envelope schema_version=3 extends the existing shape with selection.level/role, advisor_response, escalation, packet_identity and runtime_source. transport_contract_version=1.5 does not accept old receipts for admission. stdout has exactly one final JSON envelope; progress stays on stderr. Failures keep truthful outcome/attempt/usage data, with unavailable counters represented as null. A nonempty session_id is nonterminal: drain the exact handle with write_stdin before parsing exactly one schema-v3 envelope. Outer functions.wait updates are nonterminal progress, not final receipts.

The optional content-free usage journal is disabled by default, uses owner-only locked storage and enforces byte/count/30-day retention bounds. Its A writer emits contract 1.5 with advisor/compatibility-test semantics and one attempt; the reader preserves historical tiers/outcomes/contracts without relabeling them. Failure/cancellation usage is retained. Catalog or journal state cannot authorize escalation.

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
}).filter((value) => value && value.schema_version === 3);
if (candidates.length !== 1) {
  throw new Error("Advisor transport did not return exactly one schema-v3 envelope");
}
const verifiedEnvelope = candidates[0];
text(JSON.stringify(verifiedEnvelope));
```

The initial yielded result is nonterminal progress; an outer functions.wait update is nonterminal too. Drain the same session_id with write_stdin, retain all chunks, then parse and deliver exactly one schema-v3 envelope. No receipt is accepted before terminal exit.

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

For skip/unavailable emit only ADVISOR DECISION unless a child was actually launched. A distinct Codex consultation thread remains the inspectable detailed record. Do not route completion or final review to an advisor. Recovery after an unknown/timeout/cancel outcome is a safe stop, not a retry. Durable checkpoint resume/reconcile and cross-session replay protection are phase B.

Installer retirement paths such as `.retired-v1.3.0-zero-tool` preserve known historical roles; unknown content, symlinks and collision states fail before mutation. User settings, bridge configuration, installed plugin and session model are not altered by this repository integration.
