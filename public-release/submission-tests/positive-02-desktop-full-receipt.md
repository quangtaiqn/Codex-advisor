## Name

Fictional desktop compatibility consultation with full receipt

## Host

Codex desktop

## Preconditions

Required host prerequisites: Codex desktop, `jq`, a POSIX shell, a persisted Codex Desktop rollout, a resolvable `CODEX_THREAD_ID`, and the declared escalated launcher are available.

## Prompt

For the fictional Beacon Archive, should the import format remain backward compatible with version-one archives or require migration? Ask Advisor for a second opinion before deciding.

## Expected outcome

Advisor emits `ADVISOR DECISION` with `route: consult`; `ADVISOR CALL` records `level: low`, `role: advisor-astra`, and `status: running`; and a verified `ADVISOR RESULT` records `status: completed`, `model: gpt-6-astra`, `effort: low`, `isolation: read-only`, and the root's disposition.

## Why this is the expected outcome

Codex desktop is supported when preflight succeeds, and a compatibility decision uses the active Astra low-first advisor and its visible receipts.
