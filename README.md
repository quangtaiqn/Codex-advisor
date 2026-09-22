# Codex Advisor

Codex Advisor automatically adds a fresh, read-only second opinion when Codex
identifies a material technical decision. It cannot change files, run commands,
browse the web, implement work, deploy, or make the final decision.

## Install

Install [**Codex Advisor** from the official Plugins Directory](https://chatgpt.com/plugins/plugins_6a984f37e9c88191a2a777998f7b0521). It requires
**Codex CLI** or **Codex desktop**; generic ChatGPT is not a supported runtime.

Advisor uses one fixed Astra route for every eligible checkpoint. It starts at
`gpt-6-astra` / `low` and can move only through `medium`, `high`, and
`extra_high` (runtime `xhigh`) after an explicit adjacent escalation request.
It leaves factual, mechanical, cheap/resolved, completion/reassurance, and explicitly
no-delegation work alone. Existing Standard/Specialist names remain compatibility
labels only and cannot select Terra or Sol.

## Links

- [Support](https://zerodelta.dev/advisor/support/)
- [Privacy Policy](https://zerodelta.dev/advisor/privacy/)
- [Terms of Service](https://zerodelta.dev/advisor/terms/)
- [Public listing draft](docs/public-listing.md) and [1.4.5 site walkthrough](docs/site-walkthrough-1.4.5.md)

## Development

```sh
sh plugins/advisor/scripts/verify.sh --static
```

The implementation contract is in the [plugin skill](plugins/advisor/skills/consultation/SKILL.md),
[SPEC.md](SPEC.md), and [INVARIANTS.md](INVARIANTS.md).

Before releasing a version, follow [the release process](docs/release-process.md):
update descriptions and deploy and verify the reviewed website, then commit and push
the exact source. Create or update the matching GitHub `vVERSION` release with the
exact marketplace ZIP, verify its tag/source and downloaded asset SHA-256 separately,
then run `public-release/verify-upload-ready.sh` immediately before the owner uploads.
Completion requires the website, descriptions, GitHub release, and owner-confirmed
marketplace publication; a ZIP alone is only a candidate.

## Selection and discovery

New consultations use `--level low|medium|high|extra_high` and an opaque
`--checkpoint-key`. The installed live file `advisor.toml`, beside the loaded skill,
is authoritative and contains one fixed Astra policy plus the ordered ladder. Low is
the only direct entry; higher levels require the verified adjacent response from the
same checkpoint chain. The launcher freezes model, effort, policy digest, transport
contract, and deadline before launch. A durable ledger reserves a level before the
child starts, so a restart never silently spends the same level twice. Legacy
`--tier`/`--role` names are aliases into the same Astra-low-first route. No catalog,
preset, discovery result, or old saved selection can override it.

The installed copy includes `scripts/advisor-config.sh`. `show` and `doctor` display
the actual `advisor.toml` pairs, path, and source revision. Its catalog, preset, and
canary commands are retained advanced tools under Codex home; they do not select a
normal `--tier` consultation. `set` and `reset` reject with that guidance, while
`restore` reports that it restores legacy local state only.

The catalog records `codex-cli 0.153.2` only as tested provenance; it is not an
eligibility pin. A CLI update does not invalidate a canary receipt or the built-in
defaults. The transport's runtime identity, effort, read-only, zero-tool, and schema
checks remain the acceptance boundary. That observed CLI's app-server rejects the
isolation flags discovery requires, so refresh safely returns unavailable and leaves
state unchanged; adding a selector is the manual path. It does not establish that a
real model inference has passed. Actual model canaries require explicit usage
authorization and remain pending for this candidate.

The optional content-free usage journal is disabled by default. `journal enable`,
`journal status`, `journal disable`, and `journal clear` control it. On a later journal
write, Advisor prunes records older than 30 days and keeps the bounded local count; it
does not run a background deletion service.

## Response contract

The wrapper accepts model output only as one object matching its installed JSON Schema,
the sole supported wrapper model-output format. Direct/native role invocation is
unsupported and is not schema-validated. After runtime inspection, wrapper-owned
semantic validation renders the accepted object as the canonical eight-line
`ADVISOR RESPONSE` receipt. Each level is one pass: response/schema/runtime failures
are terminal, never corrected by a retry, and never reopen a consumed checkpoint.
Rejected content remains private to the mode-0700 consultation directory and is
removed by unconditional cleanup.

When the Codex shell tool returns a nonempty `session_id`, that is nonterminal
progress, not an Advisor result. The caller drains that exact handle with
`write_stdin`, accumulates all returned tool output, waits for terminal exit, and
then extracts exactly one schema-v3 envelope and explicitly emits it from the
enclosing call before rendering a receipt. Outer waits and heartbeats are not result
evidence.
