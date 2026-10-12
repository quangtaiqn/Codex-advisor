# Astra model configuration — phase A

| Logical level | Model | Runtime effort |
| --- | --- | --- |
| low | gpt-6-astra | low |
| medium | gpt-6-astra | medium |
| high | gpt-6-astra | high |
| extra_high | gpt-6-astra | xhigh |

```toml
[advisor]
model = "gpt-6-astra"
effort_ladder = ["low", "medium", "high", "xhigh"]
```

Settings, resolver and level mapping belong to advisor_settings.py. advisor_state.py owns pair/response validation and common typed errors; advisor_catalog.py owns diagnostic model/capability records. advisor_config.py is the facade/CLI. run-advisor.sh owns admission and runtime acceptance using advisor_admission.py. No monolithic policy wrapper remains.

The root owns architecture, implementation routing, verification, and acceptance. Advisors are read-only, non-authoritative, use zero tools, and never delegate, implement, deploy, or perform final review. The root performs any repository or web research and includes relevant evidence and source references in a bounded decision packet. When evidence is insufficient, the advisor may recommend only a concrete research-first next step and list missing evidence under FOLLOW-UP AREAS, outside this consultation. An unavailable result cannot be rescued by a higher level or a fallback model.

The sole supported wrapper model-output format is one JSON object. Wrapper-owned semantic validation checks exact keys, types, nonblank strings/checks, duplicate fields and structured escalation before rendering the canonical eight-line ADVISOR RESPONSE receipt. This redacted failure boundary never publishes rejected content. One command launches at most one child and one attempt; no corrective retry occurs. A chain can use at most four adjacent levels, once each, under primary control. Runtime inspection must prove a distinct Codex consultation thread, the exact selected role/model/effort, read-only isolation, managed permission provenance and zero tool calls, with allowlisted `codex_exec` or `Codex Desktop` provenance. A tool call is rejected after execution; this is not preventive tool isolation and cannot undo data already processed by a prohibited tool.

The schema passed to `codex exec --output-schema` uses the [Structured Outputs subset](https://developers.openai.com/api/docs/guides/structured-outputs), with required fields, closed objects and an explicit nullable `next_level` type. The facade narrows its enum to null or the adjacent level (null only at extra_high). It contains no allOf/if/then conditionals. String patterns and array bounds remain; redundant minLength constraints are omitted. The local validator independently rejects missing or blank escalation explanations, skipped/repeated levels and any escalation at extra_high. Schema generation and fixture checks are offline evidence; provider acceptance and live model capability remain UNVERIFIED until separately authorized testing.

Standard/Specialist and advisor-terra/advisor-sol/advisor-astra are supported wrapper entrypoints, all starting gpt-6-astra/low. Tier/role changes do not authorize a new level or reset the issue budget. Direct/native role invocation is unsupported; use the fixed launcher and its verified receipt. Model/catalog declarations are documentation, not live capability or entitlement proof. No model/effort fallback is permitted.

Each issue starts low. Higher calls require an accepted previous result, an adjacent escalation.next_level with nonblank reason, unresolved_difficulty and required_resolution, and the primary's confirmation that material uncertainty remains after cheap local evidence. Use --previous-result RECEIPT --authorize-escalation with --level medium|high|extra_high. Admission rechecks current parent, exact child/session, policy/transport revision, packet digest, persisted prompt/role/level and response, model/effort, isolation, tools and permission provenance before spawn. A Boolean --chain-authorized flag cannot grant admission. extra_high is logical terminal; runtime effort is xhigh. xhigh is a boundary alias, not a fifth budget. next_level=null stops immediately; return the best result and uncertainty at the terminal level. Transport failures, malformed responses, timeout/cancellation, provenance/model/effort mismatch and tool use are terminal; higher effort cannot repair them.

Phase A has no durable checkpoint ledger, crash-resume/reconcile, cross-session replay prevention or concurrent duplicate admission. The primary tracks level usage within the current session. A receipt is navigation evidence, not a consumed token; phase B will implement durable at-most-once admission, tombstones/retention, resume and replay protection only after separate approval. This limitation does not weaken one-attempt transport, adjacent transition checks, or ownership.

## Migration and diagnostics

Two-tier TOML [standard]/[specialist] is rejected with migration guidance; [advisor] is the only active policy. Old owner-only settings under Codex home remain preserved as diagnostic records. Valid deadline/journal preferences can be retained without promoting their saved model pair to active selection. set/reset reject, model/effort mutations and presets outside policy reject; compatibility canaries are explicit-authorized, low-only Astra and cannot authorize escalation. No global model selection is changed.

Catalog presence is documentation, not an entitlement or live proof. codex-cli 0.153.2 is historical tested provenance, not a runtime eligibility pin. Unsupported Astra/effort returns safe-unavailable; no fallback model, effort or PATH source is selected. Discovery/doctor do not trigger a consultation. The command `models test MODEL --effort EFFORT --authorize-usage --parent-thread THREAD_ID` requires explicit usage authorization and, in A, MODEL=gpt-6-astra and EFFORT=low. No inference was run during integration.

The optional content-free usage journal prunes records older than 30 days on a subsequent write, with no background deletion service. History retains old transport contract values.

The fixed launcher retains --ignore-user-config, --ignore-rules, --sandbox read-only and an isolated workdir. Python 3.11+ runtime preflight precedes helper import/provider launch; Vulture's Python 3.14 is a separate verification toolchain. Deadline, output/packet/queue bounds and child process supervision remain enabled. Startup ownership/cancel-request guards establish ownership before cleanup; an unconditional exit trap removes only the owned mode-0700 consultation directory under Codex home. Preexisting paths and unrelated processes are preserved. Uncatchable termination can leave state; do not infer that no child spawned and do not retry it.

Transport resolution is shared by launch, discovery, doctor, version probes, canary and inspectors: valid ADVISOR_CODEX_BIN, then a valid private installed WSL bridge, then PATH. Invalid explicit overrides fail without fallback. Binary/source/sessions_directory are kept together. The bridge retains checksum, owner/mode and symlink checks, bounded preflight and path conversion. Do not reinstall a bridge or modify Windows/WSL configuration to repair a test.

Envelope schema_version=3 extends the existing shape with selection.level/role, advisor_response, escalation, packet_identity and runtime_source. transport_contract_version=1.5 does not accept old receipts for admission. stdout has exactly one final JSON envelope; progress stays on stderr. Failures keep truthful outcome/attempt/usage data, with unavailable counters represented as null. A nonempty session_id is nonterminal: drain the exact handle with write_stdin before parsing exactly one schema-v3 envelope. Outer functions.wait updates are nonterminal progress, not final receipts.

The optional content-free usage journal is disabled by default, uses owner-only locked storage and enforces byte/count/30-day retention bounds. Its A writer emits contract 1.5 with advisor/compatibility-test semantics and one attempt; the reader preserves historical tiers/outcomes/contracts without relabeling them. Failure/cancellation usage is retained. Catalog or journal state cannot authorize escalation.

The 1.4.4 deployment record is historical. This candidate is not yet deployed or installed; live runtime and installed bridge end-to-end remain UNVERIFIED.
