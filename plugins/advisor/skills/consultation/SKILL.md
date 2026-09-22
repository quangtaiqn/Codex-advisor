---
name: consultation
description: "Use a bounded, read-only Astra consultation before an approved-plan checkpoint only when unresolved uncertainty has material impact; route Astra low -> medium -> high -> extra_high, and skip routine or already-settled work."
---

# Advisor consultation

## Active advisor-execution policy

This section is the active contract for the packaged plugin. Historical
Standard/Specialist wording below remains only as migration context; it must not
select a legacy model. The primary agent owns the plan, repository changes,
debugging, tests, verification, and acceptance. The advisor is read-only,
zero-tool, non-recursive consultation only.

During approved-plan execution, preflight each checkpoint. Consult only when
there is unresolved uncertainty that a focused read or cheap test cannot settle
and a wrong decision has material rework, compatibility, security, data,
concurrency, migration, or public-interface impact. Skip routine/factual/status
work, mechanical or formatting edits, settled-plan execution, cheap-check
resolved questions, implementation already started, completion/reassurance,
explicit no-delegation, and borderline cases. One checkpoint has one advisor
opportunity before implementation; do not reopen it after implementation.

Every issue starts at `gpt-6-astra` with `low`, then may move only through
`medium`, `high`, and `extra_high` (runtime `xhigh`). A higher level requires an
explicit `ESCALATION_REQUEST` for the immediate next level with a reason,
unresolved difficulty, and required resolution. Each level is single-pass;
there is no same-level retry, skipped level, parallel/consensus call, recursive
delegation, or completion consultation. Stop as soon as advice is sufficient.

Use the existing local `run-advisor.sh` transport with `--level` and an opaque
`--checkpoint-key` for resumable plan work. Legacy `--tier`/`--role` callers may
be compatibility aliases only if they enter the same Astra-low-first chain;
they must never select Terra or Sol. Do not add a cloud service, `mcp.json`,
database, raw model override, or new authentication path. Preserve the existing
launcher, stdin packet, private Codex-home transport, cleanup, cancellation,
runtime inspectors, usage journal, receipts, installer, marketplace, and final
review boundary.

Send a compact packet containing objective, checkpoint, intended approach, one
difficult decision, relevant evidence, material prior attempts, hypothesis, and
impact if wrong. Do not send full history/full diff or secrets. Require the
advisor to analyze only, stay read-only, avoid tools/file inspection/web/research,
and avoid implementation or delegation. Validate actual child model, effort,
read-only isolation, fresh thread, provenance, and zero tools before accepting
the response.

The response keeps the seven existing content fields and adds typed
`escalation: {next_level, reason, unresolved_difficulty, required_resolution}`.
`next_level` is null or the immediate next level; non-null escalation fields must
be nonblank. A schema/semantic failure is terminal and never launches a
corrective child. The primary agent verifies advice independently and records
accept/modify/reject; final review remains separate.

When a checkpoint key is present, reserve the level before launch and persist an
atomic owner-only state record containing packet/policy digests, reserved and
completed levels, status, implementation lock, and next action. Resume reuses a
reserved level; uncertain post-reservation state fails closed and never spends
the same level again. Clearing usage journal state never clears the safety
ledger. This bounds token burn by cheap preflight, skip rules, compact packets,
one chain/checkpoint, one pass/level, no response retry, and stop-on-sufficient;
the plugin does not claim a hard token cap.

Use one fresh, read-only, zero-tool advisor only when the task has a concrete material
decision. The root owns architecture, implementation routing, verification, and acceptance.
Before consultation, the root performs any repository or web research and supplies
enough relevant evidence and source references in the five-section decision packet for
the advisor to recommend a path.

The root may assign bounded evidence gathering to separate research workers before assembling the decision packet; the consulted advisor still uses zero tools and never delegates.

If that evidence cannot settle the question, a valid
advisor result may instead identify a concrete research-first next step, missing
evidence, research questions, or bounded brainstorming areas. The advisor does not
inspect files, call tools, fetch the web, or conduct independent research.

## Declare the route

Read-only discovery may ground the decision. For a consult candidate, inspect the
parent identity before the first implementation write and before its decision record:

```sh
sh <absolute-installed-plugin-root>/scripts/inspect-parent-runtime.sh
```

The preflight uses only `CODEX_THREAD_ID` and the caller-supplied/default sessions
root. It accepts an unambiguous persisted parent with a recognized sandbox policy;
the parent itself need not be read-only because the consultation runs in a distinct
explicitly read-only Codex process. A missing, ambiguous, malformed, or conflicting
parent runtime is unavailable. Do not use `CODEX_SESSION_ID` as a fallback. Emit
exactly one record:

```text
ADVISOR DECISION
route: consult | skip | unavailable
reason: <one task-specific sentence>
question: <bounded decision question, or none>
```

Consult when at least one positive trigger in the description applies. Skip when all
applicable work is routine, the user forbids delegation, or eligibility is borderline.
General quality is not a decision question.

There is no automatic completion consultation. Completion, reassurance, final
review, and release verification remain owned by the primary agent and the
separate `final-review` skill. A new consultation is allowed only for a
materially new approved-plan checkpoint with a fresh bounded uncertainty.

An identified parent uses `route: consult`, including a normal `workspace-write`
root. An unavailable parent uses `route: unavailable`, emits no `ADVISOR CALL`,
starts no consultation process, and does not block the root's own work. The ordinary
`route: skip` path is unchanged.
A non-Codex surface has no supported local transport, so it takes `route: unavailable` and emits no `ADVISOR CALL` or `ADVISOR RESULT`.

## Explicit configuration is separate

The bundled installed `advisor.toml` contains one fixed Astra policy and the
ordered effort ladder. The active helper resolves only `gpt-6-astra`; legacy
catalogs, presets, and model-pinned roles are not active routing inputs. The
helper's `show` and `doctor` still report the installed path and source digest.
Plugin updates or reinstalling can replace the bundled policy.

`models test MODEL --effort EFFORT --authorize-usage --parent-thread THREAD_ID`
uses model capacity. Never infer that authorization from catalog metadata, a saved
selection, or a configuration request. CLI `0.153.2` app-server currently lacks the
isolation flags required for safe discovery, so `models refresh` safely returns
unavailable without changing state; it is not a live model canary.

## Consult exactly

1. Resolve the absolute installed plugin root from this loaded `SKILL.md` path: it is
   two directories above the directory containing this file. Verify that
   `run-advisor.sh`, `inspect-parent-runtime.sh`, and `inspect-agent-runtime.sh` are
   regular, nonsymlinked files beneath that installed root. Use those absolute paths
   for every consultation command. Never elevate a repository-relative or
   workspace-resolved `plugins/advisor` script.
2. Start every new issue at Astra `low`. Escalate only after an explicit,
   verified adjacent-level request: `low -> medium -> high -> extra_high`
   (`extra_high` maps to runtime `xhigh`). The parent model and sandbox are
   irrelevant to model selection; actual child runtime evidence remains required.
3. Resolve the selected level through the installed helper. Before invoking the
   consultation transport, emit this visible main-chat receipt using the actual resolved model and effort metadata:

```text
ADVISOR CALL
 level: low | medium | high | extra_high
model: <resolved model selector>
effort: <resolved effort>
reason: <one task-specific sentence>
question: <bounded decision question>
status: running
```

4. Send only this bounded, non-sensitive packet to the fixed transport on stdin:

```text
DECISION
<one question the root must resolve>

CONTEXT
<goal, relevant root-gathered evidence with source references, and current constraints>

OPTIONS
<known viable choices, including the tentative choice when one exists>

BOUNDARIES
<owned files, excluded scope, compatibility, security, and authority limits>

REQUEST
Challenge the tentative choice. Recommend one path when the packet supports a
decision; otherwise identify a concrete research-first next step, specific missing evidence,
research questions, or bounded brainstorming areas. Identify the strongest
counterargument, name evidence that would change the recommendation, and give
specific acceptance checks. Use zero tools: do not inspect files, call tools, fetch
the web, or conduct independent research. Do not perform or delegate the follow-up.
```

Require the model to emit exactly one object conforming to the installed
`advisor-response.schema.json`, with no prose or code fences. This JSON Schema is
the sole supported wrapper model-output format. Direct/native role invocation is unsupported and is not schema-validated. The required fields are:

```text
recommendation, why, strongest_objection, change_my_mind, risks,
follow_up_areas: required nonblank strings
acceptance_checks: required nonempty array of nonblank strings
escalation: typed immediate-next-level object
```

5. Run exactly one selected consultation. Invoke the fixed installed-plugin wrapper
   with the shell tool's `sandbox_permissions: require_escalated` boundary and a
   narrow justification for launching one read-only Advisor child. Do not first try
   the wrapper inside the parent sandbox: nested Codex app-server initialization is
   blocked there. The elevation applies only to the fixed launcher; the consultation
   process itself is forced to `--sandbox read-only` and must pass runtime inspection.
   Do not call `codex exec` directly and do not pass a model or effort override;
   `run-advisor.sh` resolves the selected Astra level once, uses its fixed policy model
   and runtime effort, forces `--sandbox read-only`, starts a fresh
   `codex exec` thread using existing Codex authentication, and never reads or copies
   authentication files:

```sh
/bin/sh <absolute-installed-plugin-root>/scripts/run-advisor.sh --level low --checkpoint-key <opaque-key> <<'ADVISOR_PACKET'
DECISION
<the complete five-section packet continues here>
ADVISOR_PACKET
# Resume an approved escalation with the same checkpoint key and the next level.
```

When the shell tool is called through the Codex tool runtime, a deferred result
must be drained before it is classified. Use this caller-side pattern for every
tier and role (the wrapper's model does not change the handoff contract):

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

A nonempty `session_id` from `exec_command` is nonterminal: keep polling the
same session with `write_stdin` and preserve every returned output chunk in
`combinedOutput`. The initial yielded result is nonterminal progress, never an
Advisor envelope. Likewise, an outer `functions.wait` result or heartbeat is nonterminal progress.
Do not parse it, emit a receipt, or classify the consultation until the owning
`functions.exec` call has drained the exact process and validated its terminal
output. Parse `combinedOutput` only after the process has no `session_id` and a
terminal `exit_code`. Because the shell tool may merge stderr progress into
`output`, extract exactly one parseable `schema_version: 3` JSON object from the
complete accumulator and reject zero or multiple candidates. Only then use
`text(JSON.stringify(verifiedEnvelope))` to deliver that verified envelope from
the enclosing `functions.exec`; nested shell-tool output is not itself a result.

   Use this single-quoted heredoc form, after proving the delimiter is absent from the
   packet. Never use `< packet.txt`, an unquoted heredoc, `eval`, or shell-interpolated
   packet text at this elevated boundary. The packet exists only on the wrapper's
   stdin; do not stage it in a workspace-writable file.

   The wrapper writes progress only to stderr and emits one verified JSON object on
   stdout. It runtime-inspects every launched child before classifying that child's
   response. Wrapper-owned semantic validation rejects malformed JSON, duplicate,
   missing, extra, wrong-type, noncontiguous-array, or blank schema fields, then
   deterministically renders the accepted object as this exact canonical eight-line
   receipt:

```text
ADVISOR RESPONSE
RECOMMENDATION: <recommendation>
WHY: <why>
STRONGEST OBJECTION: <strongest_objection>
CHANGE MY MIND: <change_my_mind>
ACCEPTANCE CHECKS: <acceptance checks joined by ; >
RISKS: <risks>
FOLLOW-UP AREAS: <follow_up_areas>
```

   Mandatory post-response inspection proves the exact frozen Astra model and effort,
   read-only isolation, distinct-thread identity, `codex_exec` provenance,
   and zero tool calls before validation can succeed. A schema or response-validation
   failure emits only its redacted failure `class` and `field` on stderr and stops.
   It performs no corrective retry, launches no second child for the same level,
   or copies rejected content into a retry prompt. The durable checkpoint ledger
   consumes the reserved level even when the process is interrupted; resume reconciles
   the recorded state rather than replaying it.
   Packet, launcher, event, identity,
   same-session, runtime, wrong-model, wrong-effort, non-read-only, normalization, provenance, or tool-use failure
   is terminal and never retries. A second response-validation failure fails closed.
   Rejected content is never emitted, accepted, or merged. Every attempt artifact
   remains only in one private mode-0700 consultation directory beneath the private
   transport root; an unconditional exit trap removes
   that directory after every wrapper exit.
6. Receive the required advisor response from the verified JSON without supplying
   more context or asking it to research. A valid processed response contains either
   a recommendation grounded in the packet or a concrete research-first follow-up
   under `FOLLOW-UP AREAS`.
7. Treat a response that passed mandatory runtime inspection as evidence and verify
   its cited source references. For a research-first response, treat the concise
   research-first plan as the recommendation and its concrete inquiries as
   `FOLLOW-UP AREAS`. Then record `accept`, `modify`, or `reject` with one reason:
   `accept` means the root accepts the returned technical recommendation or
   research-first plan, never a technical choice that the advisor did not make.
   After runtime evidence and advice processing, always emit this visible
   main-chat receipt:

```text
ADVISOR RESULT
status: completed | unavailable
level: low | medium | high | extra_high
model: <verified resolved model selector>
effort: <verified resolved effort>
isolation: read-only
recommendation: <concise recommendation, or unavailable>
decision: accept | modify | reject | blocked
reason: <one sentence>
```

8. After a valid, runtime-inspected result, any identified research or brainstorming
   follow-up remains primary-agent work outside this consultation. An unavailable
   result cannot be rescued by a replacement advisor or same-checkpoint follow-up.
9. The advisor may not spawn, route, research, implement, or review final work. Do
   not independently spawn a replacement or second advisor, implementer, or final
   reviewer as part of this consultation. There is no same-effort response retry.

`completed` requires a processed advisor response with either a recommendation or a
concrete `FOLLOW-UP AREAS` entry, plus mandatory post-response runtime inspection.
Any unavailable runtime evidence, non-read-only runtime policy, tool-use evidence, or
required advice produces `status: unavailable`,
`recommendation: unavailable`, and `decision: blocked` and remains fail-closed.
These receipts summarize verified evidence; they are not runtime proof.
The distinct Codex consultation thread remains the inspectable detailed record.

If exact completed transport evidence is unavailable, report `advisor unavailable`
and block the consult route. Never continue independently, substitute another model
or effort, or add an implementer or final reviewer after choosing `consult`.

For `skip` or `unavailable`, emit only the existing `ADVISOR DECISION`; do not emit
`ADVISOR CALL` or `ADVISOR RESULT`, and do not start the transport. An unavailable parent does not
block root-owned work.

See [operations](references/operations.md) for installation, runtime evidence, and
evaluation details.

Legacy cached integrations may use `--role advisor-terra`, `--role advisor-sol`, or
`--role advisor-astra`; these names are migration aliases only and must enter the
same Astra-low-first chain. They cannot select Terra/Sol, bypass a checkpoint key,
or override the level. Raw model, effort, and preset overrides are never active
routing inputs.
