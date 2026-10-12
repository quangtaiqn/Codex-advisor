# shellcheck shell=sh
for phrase in 'https://github.com/DannyMac180/sol-advisor' '37b75cad535abdd46531f0227483a8842d045ab8' 'David Schmidt / Zero Delta LLC' 'Daniel McAteer'; do grep -Fq "$phrase" "$notice" || fail "NOTICE attribution missing"; done
grep -Fq 'Copyright (c) 2026 Daniel McAteer' "$license" || fail "license copyright missing"
for phrase in 'Codex CLI' 'Codex desktop' 'Privacy Policy' 'Terms of Service' 'cannot'; do grep -Fqi "$phrase" "$readme" || fail "README guidance missing $phrase"; done
for document in "$operations" "$repo_dir/SPEC.md"; do
  for phrase in 'ADVISOR DECISION' 'ADVISOR CALL' 'ADVISOR RESULT' 'unavailable' 'blocked'; do grep -Fqi "$phrase" "$document" || fail "lifecycle documentation missing $phrase"; done
done
for phrase in 'gpt-6-astra' '[advisor]' 'migration' 'Codex home' 'not an entitlement' 'not yet deployed' 'no background deletion service' '30 days'; do grep -Fqi "$phrase" "$model_doc" || fail "model/migration/privacy contract missing $phrase"; done
grep -Eq '^Candidate content digest: `[0-9a-f]{64}`\.$' "$release_notes" || fail "candidate content digest missing"
[ "$(grep -Ec '^Candidate content digest: `[0-9a-f]{64}`\.$' "$release_notes")" -eq 1 ] || fail "duplicate candidate digest"
grep -Fqi 'Repository-root documentation is not in the ZIP' "$release_notes" || fail "ZIP boundary missing"
grep -Fqi 'Mocked' "$repo_dir/docs/candidate-walkthrough.md" || fail "mocked evidence label missing"
grep -Fq 'Historical 1.3.4 acceptance record' "$repo_dir/docs/candidate-walkthrough.md" || fail "historical receipt label missing"
grep -Fq 'UNVERIFIED' "$repo_dir/docs/merge-stage-a.md" || fail "live uncertainty hidden"
pass "attribution, lifecycle, migration, privacy and historical/live evidence labels"
