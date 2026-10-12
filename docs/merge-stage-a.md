# Merge stage A — local candidate

Candidate version: `1.4.9-astra.1`. Local source: `5c2e73694c94f37dcd97c955a2a3c82a8684625a`; fork source: `38bbafc91ba5cf55d204614c0e5c4d766a4b66d8`. Candidate implementation evidence lives outside the checkout at `D:\Program\Codex-Advisor-merge-evidence\implementation-handoff.md`. That report records exact final tree/checks and independent Final-Review status.

Active contract: [SPEC](../SPEC.md), [invariants](../INVARIANTS.md), [model configuration](model-configuration.md), and [consultation operations](../plugins/advisor/skills/consultation/references/operations.md). All aliases start Astra/low, local adjacent escalation is preserved, and one attempt per level is terminal on failure.

`Advisor_New_Plan.md`, advisor-execution-migration-plans.md, advisor-runtime-escalation-verification-plan.md and docs/routing-checkpoints/CP0–CP6 are retained historical records for local source or earlier SHA. Old release/site walkthroughs document the fork releases and historical deployments. Their commands/receipts are not current instructions or evidence of this candidate.

Phase B is DEFERRED in full: durable issue/checkpoint identity and ledger; reservation/started/terminal atomic ownership; consumed levels and tombstone/retention migration; cross-session/restart/concurrent replay prevention; crash/timeout/cancel resume and reconcile; old ledger preservation/migration; matching schema/CLI/tests/docs; negative/regression proof and its separate Final-Review. No B work or live inference/canary, global configuration, installed-plugin update, main update, push, PR, deployment or publication is authorized here.

Live runtime, desktop activation and installed bridge end-to-end are UNVERIFIED. Fixtures prove wiring and acceptance only. A local ZIP is not publication readiness.

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
