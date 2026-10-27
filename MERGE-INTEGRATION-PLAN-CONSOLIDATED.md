# Integration status

Updated on 27 October 2026. Accepted runtime revision: `63e73afc07a24b46d0f042b7959d37bc4aefdc40`.
This document records the accepted private scope. It does not authorize new runtime calls or public release.

## Accepted scope

The private CLI work for Goal A and Goal B is complete. R4 passed within the installed CLI scope at revision `5cf441a4d22393601d4ac19ac0025d959676c937`.
The subsequent Desktop compatibility repair passed at the accepted runtime revision above. The repair was merged into local main and pushed to GitHub.
The approved clean Desktop chat called `gpt-6-astra/low` and received a response. The installed driver verified the complete envelope HMAC in memory, and the ledger accepted it. The wrapper exited with code 0 and cleaned up its child and token.

The Desktop final review found no BLOCKER, MAJOR or new MINOR. The installed cache and Git blobs matched the 51-file inventory. Existing unrelated work was preserved through the merge.
The temporary Desktop repair worktree was removed after delivery. The retained `codex/advisor-durable-ledger` worktree was then aligned with main.

## Verification limits

The final focused run passed 23 cases, including 19 parent cases. The 15-case ledger run preceded the final cleanup, and affected cases ran again in the final focused group.
The broader 137-case evidence combines 112 completed cases and 25 resumed cases after a timeout. It is not a single full-wrapper PASS.
The Desktop proof covers the approved clean chat. It does not establish a new CLI live run or an original-chat live run on the final build. The stored redacted result cannot reproduce the complete envelope HMAC.

The existing reserved-marker MINOR remains nonblocking. Public release, marketplace submission and a standalone advisor-execution migration are outside this accepted scope.
The automatic Desktop allowance stopped after the verified response. Historical budgets and seals remain unchanged. Another live call requires new authorization.

## Source and local history

Use the [workflow map](docs/repo-workflow-map.md), [runtime contract](plugins/advisor/skills/consultation/references/operations.md) and [release process](docs/release-process.md) for source navigation.
Historical reports, snapshots, test copies and execution evidence remain on the original machine outside source Git. They are not required to clone or build the repository.
The local history is under `D:/Program/Codex-Advisor/merge-completion-evidence/` and the dated report files beside it. Cleanup records and preserved index preimages are under `D:/Program/Codex-Advisor-merge-evidence/local-main-compact-20261027-1/`.
These local paths are archival references, not links available in a GitHub clone. Existing tracked tests remain in source Git. Generated caches and local history are ignored.
