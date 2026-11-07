# Plan 4a outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-02 (plan: `2026-10-02-plan-4a-commands-setup.md`, commits 1d53b17..8a690bf, executed inline with one final whole-branch review). Live acceptance: `docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md`.

Final verification at 8a690bf: `system/scripts/verify_setup.sh` exit 0 (11 bats suites, pytest 317 passed); `lint_vault.sh` 0 errors.

**Gate:** lifted. Units may be installed with `/setup`; re-run the acceptance steps after any change to `run_headless.sh`, `system/headless.settings.json` or the ingest/brief/debrief commands. `/setup` itself has not yet run end to end.

## Rulings
- Task 9: Ruling: step 6 (second brief) failed exit 5/empty — the model chained 'cd …; for …; do vault_index.py field …; done' in one Bash call, was denied, concluded Bash was unavailable and wrote nothing; it also read 'never set provenance' as 'remove the existing provenance'. Fix (attempt 1/3): add explicit headless tool rules to ingest/brief/debrief (one vault_index.py call per Bash call, no cd/loops/;/&&/pipes; files via Write/Edit; on a denial carry on and still write output) and reword to 'never add, change or remove provenance'; same text also removes the Bash-heredoc denial seen in steps 4-5. Re-run acceptance steps 2-7 on a fresh clone — cost if wrong: ~6 more headless runs.
- Task 9: Ruling: step 5 (digest batch) rejected on the re-run — schema: agent_owner 'Wheeljack' (the model filled the template's {{agent_name}} with its own persona). Fix (step-5 attempt 1/3): ingest names the allowed values and says to leave agent_owner out unless a note assigns work — cost if wrong: one more ingest run.
- Final: Ruling: re-graded Minor 2 (ingest compiled_at "first 8 digits" may yield 20261002, failing the date schema) to Important — same class as the agent_owner rejection seen live: a batch rejected three times is poisoned — cost if wrong: one wording change.
- Final: Ruling: re-graded Minor 10 (README says /setup and the units run; neither has run end to end) to Important — a user would trust an unproven setup path — cost if wrong: one sentence.
- Final: Ruling: Important 1 fixed in the prompt, not the gate — spec §6.15 makes shared→work an error and a sources link to a work digest is a frontmatter link; ingest now never adds a work/personal input to a wiki/shared/ note's sources — cost if wrong: shared notes compiled from work digests carry no source link.
- Final: Ruling: Important 3 fixed by scoping the stack-name check to the template (remote_mode keep or no config); the CLAUDE.md rules check stays gating because it pins safety rules (data-not-instructions, index-first) a user should be told they removed — cost if wrong: a user who rewrites CLAUDE.md must keep those sentences or /backup refuses.

## Final-review fixes
- fixed shared note citing a work digest rejected the whole batch — commands.bats "ingest:" (sources rule) RED→GREEN; live re-run step 5 with a neutral fact: exit 0, shared note without sources (8a690bf).
- fixed /setup jq merge could empty settings.local.json — "/setup's additionalDirectories merge keeps every other key" (executes the command from setup.md) RED→GREEN.
- fixed /backup never pushed pending commits on a clean tree — commands.bats backup check RED→GREEN.
- fixed interactive /ingest double-compiled queued inputs without redaction — commands.bats "ingest:" (refusal rule) RED→GREEN.
- fixed ambiguous compiled_at — commands.bats "ingest:" RED→GREEN; live runs wrote "2026-10-02".
- fixed stack-name check blocked /backup in user vaults — temp-copy run: old test fails with remote_mode private + a persona naming Vue, new test skips; still enforced under remote_mode keep.
- fixed README overclaim — status now says /setup and the units have not run end to end (docs; no test).

## Deferred minors
- commands.bats checks keywords, not behavior (a direct-write instruction in headless mode would pass); pin exact staged paths.
- ingest doesn't say which codebase tag a merged note gets when a batch's digests name different codebases.
- debrief names ledger fields published/rejected/conflicts at top level; they sit under .publish.
- brief always sets status: active, reopening a briefing the user closed.
- /setup copies the example config's body text into the user's config.
- /setup re-run doesn't show the current remote_mode as the default.
- /backup compares origin to template_source by eye; reuse git_url_same or drop (setup_remote already refuses).
- system_health's claude-version alarm clears itself after one run.
