# Advisor 1.4.4 candidate walkthrough

Date: 2026-09-13. This is a local candidate walkthrough, not publication or owner
acceptance evidence.

The Astra checkpoint is the active source/static policy: every eligible consultation
starts at `gpt-6-astra` / low and can advance only through the adjacent ladder
`medium -> high -> extra_high` (`xhigh` at runtime). Legacy role names are aliases.

The installed helper keeps its state under Codex home, outside the plugin cache.

| Surface | Expected behavior | Evidence and remaining gate |
| --- | --- | --- |
| Live configuration | The installed `advisor.toml` has one fixed Astra policy and the four-level ladder. Saved state, catalog, presets, and old model names cannot override it. | Policy tests cover fixed model, ladder, `extra_high -> xhigh`, malformed input, and source-digest revision. |
| Checkpoint consultation | `run-advisor.sh --level low` reserves a durable checkpoint before launch. Restart resumes from the recorded next action; a reserved level without terminal evidence is reconciled to `uncertain` and blocked, while a completed level can continue only through explicit adjacent escalation. No same-level replay occurs. | Chain tests cover reservation, reconciliation, replay rejection, adjacent escalation, and implementation lock. |
| Compatibility aliases | `--role advisor-terra`, `--role advisor-sol`, and `--role advisor-astra` all normalize to Astra/low and cannot bypass the active resolver. | Static and transport tests cover aliases and invalid active policy. |
| Current and legacy tools | `show` and `doctor` report actual live pairs, config path, and digest. Catalogs/presets/canaries are advanced-only; `set` and `reset` reject and `restore` labels legacy-only state recovery. | Mocked CLI diagnostics cover live values and stale saved-state precedence. |
| Deadline | `deadline` displays the total deadline; `deadline SECONDS` accepts 30–900 seconds and defaults to 300. The reserved level is one pass; validation failures do not launch a corrective retry. | CLI tests cover valid and rejected values. |
| Discovery unavailable | `models refresh` checks isolation support before starting discovery. Tested CLI provenance `0.153.2` lacks the flags, so it reports unavailable and leaves saved catalog state intact; discovery never blocks built-in defaults. | Unit coverage simulates the rejection. A manual selector is the recovery path. |
| Consent canary | `models test MODEL --effort EFFORT --authorize-usage --parent-thread THREAD_ID` refuses without the consent flag, runs only after explicit authorization, and does not select the pair. | Mocked synthetic canary coverage passed. Real canaries remain pending owner authorization. |
| Journal | Disabled by default; status, enable, disable, and clear are explicit. A subsequent journal write performs the 30-day prune; there is no background task. | Usage tests cover retention, null/partial accounting, and clear behavior. |
| Errors and recovery | Missing, malformed, duplicate, unknown-key/table, symlinked, nonregular, oversized, unsafe selector, or invalid effort live config fails before child launch with a redacted `advisor.toml` error. Runtime model/effort errors remain terminal. | Mocked error paths prove no model launch on invalid TOML. |
| Transport terminal paths | A malformed response, launch, identity, isolation, tool, timeout, or cancellation failure is terminal/unavailable. No corrective child is launched. | Mocked transport tests cover one-pass terminal behavior, timeout, cancellation, and fail-closed cases. |
| Deferred shell handoff | A nonterminal `session_id` is progress. The caller drains that exact session with `write_stdin`, accumulates output, requires terminal exit, validates exactly one schema-v3 envelope, and returns it from the enclosing call. No model fallback or routing change is involved. | The installed 1.4.4 candidate was rebuilt with this caller contract; a synthetic deferred handoff returned one terminal validated receipt. |

The canonical command `sh plugins/advisor/scripts/verify.sh --static` runs Advisor
tests plus 17 candidate packaging tests in this checkout;
`sh public-release/validate-public-artifacts.sh --candidate` checks manifest and
marketplace identity plus the skills-only contract; it does not scan all public claims.
`git diff --check` checks whitespace. The captain records actual final command output in the ignored local
verification record after the phase gate.

The package ships only `plugins/advisor`; this walkthrough and other repository-root
docs are not inside the ZIP. The exact three role files passed installed-state checks.
Config editing and malformed-file recovery remain automated-test evidence rather than
manual interaction. Live website, privacy, terms, portal URL autofill, and directory
listing remain independently unverified. Marketplace publication was owner-confirmed
on 13 September 2026. Historical 1.4.3 deployment evidence: website, privacy, and terms bytes are deployed and live-byte verified. The 1.4.4 website is deployed, and all seven public files are live-byte verified.
GitHub release `v1.4.4` resolves to
`a2f84e65bc551ea6c826baf29d8b792252ae04b0`, and its downloaded ZIP is
byte-identical to the marketplace archive. The historical GitHub release `v1.4.3`
also resolves to its exact source commit and handoff archive.
