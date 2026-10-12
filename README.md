# Codex Advisor

Repository-only candidate `1.4.9-astra.1` integrates the fork's modules and safety fixes with the local Astra ladder. It is not installed, deployed, released or live-runtime verified.

## Install and supported surfaces

The released plugin is available in the [official Plugins Directory](https://chatgpt.com/plugins/plugins_6a984f37e9c88191a2a777998f7b0521). This candidate requires Codex CLI or Codex desktop, Python 3.11+, jq and a POSIX shell with persisted sessions. Generic ChatGPT cannot launch this local transport.

[Support](https://zerodelta.dev/advisor/support/) · [Privacy Policy](https://zerodelta.dev/advisor/privacy/) · [Terms of Service](https://zerodelta.dev/advisor/terms/) · [candidate listing](docs/public-listing.md)

## Selection

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

```sh
sh plugins/advisor/scripts/advisor-config.sh --json resolve --tier standard
sh plugins/advisor/scripts/advisor-config.sh --json resolve --tier specialist
sh plugins/advisor/scripts/advisor-config.sh --json resolve --role advisor-terra
sh plugins/advisor/scripts/advisor-config.sh --json resolve --role advisor-sol
sh plugins/advisor/scripts/advisor-config.sh --json resolve --role advisor-astra
```

Resolution computes a pair; it does not authorize a higher-level launch. The [skill](plugins/advisor/skills/consultation/SKILL.md) and [operations](plugins/advisor/skills/consultation/references/operations.md) describe primary-controlled admission.

The root owns architecture, implementation routing, verification, and acceptance. Advisors are read-only, non-authoritative, use zero tools, and never delegate, implement, deploy, or perform final review. The root performs any repository or web research and includes relevant evidence and source references in a bounded decision packet. When evidence is insufficient, the advisor may recommend only a concrete research-first next step and list missing evidence under FOLLOW-UP AREAS, outside this consultation. An unavailable result cannot be rescued by a higher level or a fallback model.

The sole supported wrapper model-output format is one JSON object. Wrapper-owned semantic validation checks exact keys, types, nonblank strings/checks, duplicate fields and structured escalation before rendering the canonical eight-line ADVISOR RESPONSE receipt. This redacted failure boundary never publishes rejected content. One command launches at most one child and one attempt; no corrective retry occurs. A chain can use at most four adjacent levels, once each, under primary control. Runtime inspection must prove a distinct Codex consultation thread, the exact selected role/model/effort, read-only isolation, managed permission provenance and zero tool calls, with allowlisted `codex_exec` or `Codex Desktop` provenance. A tool call is rejected after execution; this is not preventive tool isolation and cannot undo data already processed by a prohibited tool.

Standard/Specialist and advisor-terra/advisor-sol/advisor-astra are supported wrapper entrypoints, all starting gpt-6-astra/low. Tier/role changes do not authorize a new level or reset the issue budget. Direct/native role invocation is unsupported; use the fixed launcher and its verified receipt. Model/catalog declarations are documentation, not live capability or entitlement proof. No model/effort fallback is permitted.

Each issue starts low. Higher calls require an accepted previous result, an adjacent escalation.next_level with nonblank reason, unresolved_difficulty and required_resolution, and the primary's confirmation that material uncertainty remains after cheap local evidence. Use --previous-result RECEIPT --authorize-escalation with --level medium|high|extra_high. Admission rechecks current parent, exact child/session, policy/transport revision, packet digest, persisted prompt/role/level and response, model/effort, isolation, tools and permission provenance before spawn. A Boolean --chain-authorized flag cannot grant admission. extra_high is logical terminal; runtime effort is xhigh. xhigh is a boundary alias, not a fifth budget. next_level=null stops immediately; return the best result and uncertainty at the terminal level. Transport failures, malformed responses, timeout/cancellation, provenance/model/effort mismatch and tool use are terminal; higher effort cannot repair them.

Phase A has no durable checkpoint ledger, crash-resume/reconcile, cross-session replay prevention or concurrent duplicate admission. The primary tracks level usage within the current session. A receipt is navigation evidence, not a consumed token; phase B will implement durable at-most-once admission, tombstones/retention, resume and replay protection only after separate approval. This limitation does not weaken one-attempt transport, adjacent transition checks, or ownership.

## Safety and local state

The fixed launcher retains --ignore-user-config, --ignore-rules, --sandbox read-only and an isolated workdir. Python 3.11+ runtime preflight precedes helper import/provider launch; Vulture's Python 3.14 is a separate verification toolchain. Deadline, output/packet/queue bounds and child process supervision remain enabled. Startup ownership/cancel-request guards establish ownership before cleanup; an unconditional exit trap removes only the owned mode-0700 consultation directory under Codex home. Preexisting paths and unrelated processes are preserved. Uncatchable termination can leave state; do not infer that no child spawned and do not retry it.

Transport resolution is shared by launch, discovery, doctor, version probes, canary and inspectors: valid ADVISOR_CODEX_BIN, then a valid private installed WSL bridge, then PATH. Invalid explicit overrides fail without fallback. Binary/source/sessions_directory are kept together. The bridge retains checksum, owner/mode and symlink checks, bounded preflight and path conversion. Do not reinstall a bridge or modify Windows/WSL configuration to repair a test.

Envelope schema_version=3 extends the existing shape with selection.level/role, advisor_response, escalation, packet_identity and runtime_source. transport_contract_version=1.5 does not accept old receipts for admission. stdout has exactly one final JSON envelope; progress stays on stderr. Failures keep truthful outcome/attempt/usage data, with unavailable counters represented as null. A nonempty session_id is nonterminal: drain the exact handle with write_stdin before parsing exactly one schema-v3 envelope. Outer functions.wait updates are nonterminal progress, not final receipts.

The optional content-free usage journal is disabled by default, uses owner-only locked storage and enforces byte/count/30-day retention bounds. Its A writer emits contract 1.5 with advisor/compatibility-test semantics and one attempt; the reader preserves historical tiers/outcomes/contracts without relabeling them. Failure/cancellation usage is retained. Catalog or journal state cannot authorize escalation.

## Development

`advisor_config.py` is a facade/CLI; settings, state, catalog, journal, discovery, doctor and canary each own their module. `advisor_admission.py` verifies navigation receipts for the launcher. `advisor_transport.py` resolves one coherent executable/sessions source. The old advisor_policy.py and active advisor_chain.py are removed after their A contracts are ported; durable chain work is deferred.

Run `sh plugins/advisor/scripts/verify.sh` and the pinned hooks in `.pre-commit-config.yaml`. Ruff, Vulture, file-size, repo-tests, upload-readiness tests and full configured Playwright projects remain required. No wildcard lint/size exceptions are introduced.

Plugin LICENSE and NOTICE.md must byte-match their root copies. The [release process](docs/release-process.md) remains separate: a ZIP is only a local candidate. Historical evidence is indexed in [merge stage A](docs/merge-stage-a.md); it does not prove the current candidate.
