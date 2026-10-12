# Advisor phase-A implementation contract

The root owns architecture, implementation routing, verification, and acceptance. Advisors are read-only, non-authoritative, use zero tools, and never delegate, implement, deploy, or perform final review. The root performs any repository or web research and includes relevant evidence and source references in a bounded decision packet. When evidence is insufficient, the advisor may recommend only a concrete research-first next step and list missing evidence under FOLLOW-UP AREAS, outside this consultation. An unavailable result cannot be rescued by a higher level or a fallback model.

The sole supported wrapper model-output format is one JSON object. Wrapper-owned semantic validation checks exact keys, types, nonblank strings/checks, duplicate fields and structured escalation before rendering the canonical eight-line ADVISOR RESPONSE receipt. This redacted failure boundary never publishes rejected content. One command launches at most one child and one attempt; no corrective retry occurs. A chain can use at most four adjacent levels, once each, under primary control. Runtime inspection must prove a distinct Codex consultation thread, the exact selected role/model/effort, read-only isolation, managed permission provenance and zero tool calls, with allowlisted `codex_exec` or `Codex Desktop` provenance. A tool call is rejected after execution; this is not preventive tool isolation and cannot undo data already processed by a prohibited tool.

Standard/Specialist and advisor-terra/advisor-sol/advisor-astra are supported wrapper entrypoints, all starting gpt-6-astra/low. Tier/role changes do not authorize a new level or reset the issue budget. Direct/native role invocation is unsupported; use the fixed launcher and its verified receipt. Model/catalog declarations are documentation, not live capability or entitlement proof. No model/effort fallback is permitted.

Each issue starts low. Higher calls require an accepted previous result, an adjacent escalation.next_level with nonblank reason, unresolved_difficulty and required_resolution, and the primary's confirmation that material uncertainty remains after cheap local evidence. Use --previous-result RECEIPT --authorize-escalation with --level medium|high|extra_high. Admission rechecks current parent, exact child/session, policy/transport revision, packet digest, persisted prompt/role/level and response, model/effort, isolation, tools and permission provenance before spawn. A Boolean --chain-authorized flag cannot grant admission. extra_high is logical terminal; runtime effort is xhigh. xhigh is a boundary alias, not a fifth budget. next_level=null stops immediately; return the best result and uncertainty at the terminal level. Transport failures, malformed responses, timeout/cancellation, provenance/model/effort mismatch and tool use are terminal; higher effort cannot repair them.

Phase A has no durable checkpoint ledger, crash-resume/reconcile, cross-session replay prevention or concurrent duplicate admission. The primary tracks level usage within the current session. A receipt is navigation evidence, not a consumed token; phase B will implement durable at-most-once admission, tombstones/retention, resume and replay protection only after separate approval. This limitation does not weaken one-attempt transport, adjacent transition checks, or ownership.

## Selection, schema and admission

| Logical level | Model | Runtime effort |
| --- | --- | --- |
| low | gpt-6-astra | low |
| medium | gpt-6-astra | medium |
| high | gpt-6-astra | high |
| extra_high | gpt-6-astra | xhigh |

The installed advisor.toml must contain exactly this fixed policy:

```toml
[advisor]
model = "gpt-6-astra"
effort_ladder = ["low", "medium", "high", "xhigh"]
```

The fixed launcher retains --ignore-user-config, --ignore-rules, --sandbox read-only and an isolated workdir. Python 3.11+ runtime preflight precedes helper import/provider launch; Vulture's Python 3.14 is a separate verification toolchain. Deadline, output/packet/queue bounds and child process supervision remain enabled. Startup ownership/cancel-request guards establish ownership before cleanup; an unconditional exit trap removes only the owned mode-0700 consultation directory under Codex home. Preexisting paths and unrelated processes are preserved. Uncatchable termination can leave state; do not infer that no child spawned and do not retry it.

Transport resolution is shared by launch, discovery, doctor, version probes, canary and inspectors: valid ADVISOR_CODEX_BIN, then a valid private installed WSL bridge, then PATH. Invalid explicit overrides fail without fallback. Binary/source/sessions_directory are kept together. The bridge retains checksum, owner/mode and symlink checks, bounded preflight and path conversion. Do not reinstall a bridge or modify Windows/WSL configuration to repair a test.

Envelope schema_version=3 extends the existing shape with selection.level/role, advisor_response, escalation, packet_identity and runtime_source. transport_contract_version=1.5 does not accept old receipts for admission. stdout has exactly one final JSON envelope; progress stays on stderr. Failures keep truthful outcome/attempt/usage data, with unavailable counters represented as null. A nonempty session_id is nonterminal: drain the exact handle with write_stdin before parsing exactly one schema-v3 envelope. Outer functions.wait updates are nonterminal progress, not final receipts.

The optional content-free usage journal is disabled by default, uses owner-only locked storage and enforces byte/count/30-day retention bounds. Its A writer emits contract 1.5 with advisor/compatibility-test semantics and one attempt; the reader preserves historical tiers/outcomes/contracts without relabeling them. Failure/cancellation usage is retained. Catalog or journal state cannot authorize escalation.

## Consultation routing

During an approved-plan checkpoint, consult only before implementation when cheap local evidence leaves unresolved uncertainty with material impact. Standalone work requires explicit advisor invocation. Skip routine, factual/status/summarization, mechanical, formatting/renaming/docs synchronization, settled-plan execution, completion and final-review work, already-consulted checkpoints and no-delegation requests. Security adjacency, project importance, and reassurance are not sufficient. A compatibility or concurrency boundary or competing diagnosis can qualify only while material uncertainty remains. No completion consultation is added.

## Delivery

Emit ADVISOR DECISION before any child, ADVISOR CALL only for an admitted running call, and ADVISOR RESULT only after terminal exit and runtime acceptance. Invalid or unavailable outcomes are blocked; never present their content as advice. The primary verifies advice and decides accept/modify/reject. Final review is owned by the external Final-Review protocol, not this advisor.

Acceptance proof (A): successful launcher envelopes include `acceptance_proof`
(`hmac-sha256-v1`) covering the complete envelope. The launcher creates a random,
owner-only key at `$CODEX_HOME/.tmp/advisor-acceptance/key` only after acceptance;
admission requires the existing safe key and a matching proof, plus current
parent/source/policy/packet and persisted runtime/response checks. Missing,
changed, linked or broadly readable keys fail closed; they are never recreated
by admission. Do not print, package or share that key. Repository helpers and the
Codex-home filesystem owner are trusted; this does not defend against that owner
rewriting the key/code/sessions. The key stores no packet, response, receipt list,
quota, reservation, consumed token or resume state. A valid receipt can still be
replayed within the permitted session; durable prevention remains phase B.
