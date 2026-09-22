# Advisor model configuration

Advisor's normal consultation configuration is the live `advisor.toml` bundled beside
the installed skill. Repository-root documentation is not part of the ZIP.

## Defaults and evidence

`advisor.toml` has exactly one `[advisor]` table with the fixed model
`gpt-6-astra` and `effort_ladder = ["low", "medium", "high", "xhigh"]`.
`extra_high` is the skill label for runtime `xhigh`. Low is the direct entry point;
the other levels require an adjacent escalation recorded by the checkpoint ledger.
The helper freezes the policy digest for each pass. Local state, discovery, catalog,
canary, preset, and legacy saved selections cannot change active routing. Plugin
updates or reinstalling can replace the bundled policy.

This grants only permission to attempt the real consultation: the child must still
pass exact runtime model, effort, read-only, zero-tool, and response-schema checks.
Catalog presence is documentation, not an entitlement.

```sh
sh scripts/advisor-config.sh show
sh scripts/advisor-config.sh doctor
```

The helper reports the active path and digest. It never automatically upgrades or
falls back. The old `--role advisor-terra`, `--role advisor-sol`, and
`--role advisor-astra` names are compatibility aliases that all enter Astra/low;
they are not separate model routes.

The eligibility decision is checkpoint-based: consult only when unresolved uncertainty
has material impact after cheap checks. Routine, settled, implementation-started,
completion/reassurance, and no-delegation work is skipped.

## Advanced legacy tools

`models refresh`, `models add`, named presets, and synthetic canaries remain isolated
advanced tools. They do not choose normal `--level` consultations. `set` and `reset`
reject rather than claim to change the active tier; `restore` can restore legacy local
state but explicitly reports that `advisor.toml` remains authoritative.

Only this command uses model capacity:

```sh
sh scripts/advisor-config.sh models test MODEL --effort EFFORT --authorize-usage --parent-thread THREAD_ID
```

`--authorize-usage` is explicit consent for the fixed content-free synthetic canary.
It does not trigger a consultation, and a failed probe remains safe-unavailable.
The catalog, an account's model list, and a saved selection are not consent. Success
records the actual local CLI version (baseline `0.153.2`) as provenance plus the
transport contract, but leaves the active Astra policy unchanged. CLI updates do not
stale the receipt; only its exact model, effort, or transport contract can do so.
Local tests mock the synthetic canary path. Historical catalog and canary records are
diagnostic-only and never establish active routing or entitlement.

## Local state and privacy

Legacy settings, catalog, canary receipts, and the optional journal live under the
Codex home directory, outside the plugin cache. They do not override the live file.

The content-free usage journal is off by default. `journal enable`, `journal status`,
`journal disable`, and `journal clear` control it. A later journal write prunes records older than 30 days and enforces the bounded count. There is no background deletion service. The journal contains operational metadata and aggregate usage counters, not
decision packets or response content; unavailable counters remain null and aggregate
coverage can be partial.

## Published privacy disclosure

> Codex Advisor stores local configuration and model-catalog evidence under the Codex
> home directory. Its optional content-free usage journal is disabled by default; when
> enabled, it records bounded operational metadata and aggregate usage counters, prunes
> records during later journal writes after 30 days, and can be disabled or cleared by
> the user. Advisor uses configurable OpenAI models in the local Codex runtime and
> does not operate a Zero Delta relay.

The 1.4.4 deployment record says the then-live privacy page byte-matched its repository
candidate. This 1.4.5 candidate updates that copy for the same local configuration/catalog
state, content-free journal, and the Astra low-first policy; it is not yet deployed.
