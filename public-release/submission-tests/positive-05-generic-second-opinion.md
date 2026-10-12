Phase-A attended test status: PENDING, not current live proof. Initial calls use Astra/low; no corrective retry.

## Name

Generic fictional second-opinion request

## Host

Codex CLI

## Preconditions

Required host prerequisites: Codex CLI, `jq`, a POSIX shell, a persisted Codex session rollout, a resolvable `CODEX_THREAD_ID`, and the declared escalated launcher are available.

## Prompt

Use Advisor for a fresh, read-only second opinion on whether the fictional Atlas Queue should expose retries as a command option or as a configuration field.

## Expected outcome

Advisor emits `ADVISOR DECISION` with `route: consult`, followed by an Astra-low `ADVISOR CALL` and a verified `ADVISOR RESULT`.

## Why this is the expected outcome

An explicit generic advisor or second-opinion request is a Standard consultation trigger when supported-host preflight succeeds.
