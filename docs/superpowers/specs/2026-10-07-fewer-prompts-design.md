# Fewer permission prompts

**Date:** 2026-10-07
**Status:** Scope approved by the owner (2026-10-07), awaiting written-spec review

## 1. Problem and decisions

Interactive sessions in a vault stop for permission on read-only status commands they run often: the gate, the Nightshift queue list, the telemetry and DTCC checks and the timer list. Sessions also chain shell commands, loop in the shell and redirect output, which defeats allow rules (a rule matches the literal command) and draws prompts. The owner's vault fixed both locally (vault commits d349b98 and ec89abd in `kferran/PorchOS`): seven read-only allow rules in `.claude/settings.json` and a **Bash** line in `CLAUDE.md`. Both are generic, so they belong in the template, byte for byte, so the vault's next `update_template.sh` merge is clean.

| Topic | Decision |
|---|---|
| Allow rules | Seven rules appended to `permissions.allow` in `.claude/settings.json`, directly after `"Bash(system/scripts/vault_index.py recall:*)"`, in the vault's order and spelling (§2). |
| `CLAUDE.md` | The vault's **Bash** line, byte for byte, directly after the **Configuration:** line in Vault Rules (§3). |
| Vault-only rules | The vault's other rules (systemctl status, journalctl, tmux, `git -C`, tar, connector reads) stay out of the template. |
| Merge with the vault | A clean merge needs one vault-side change first (§4). |

## 2. The allow rules

The end of `permissions.allow` becomes:

```json
      "Bash(system/scripts/vault_index.py recall:*)",
      "Bash(system/scripts/verify_setup.sh)",
      "Bash(system/scripts/verify_setup.sh --health)",
      "Bash(system/scripts/nightshift.py list)",
      "Bash(system/scripts/telemetry_fetch.py --list)",
      "Bash(system/scripts/telemetry_fetch.py --check *)",
      "Bash(system/scripts/dtcc_watch.py --check)",
      "Bash(systemctl --user list-timers *)"
    ],
```

What each allows:
- `verify_setup.sh`, with or without `--health`: runs the test suites and, with `--health`, the advisory live-state checks. It writes only test temp files under `.scratch/tmp`.
- `nightshift.py list`: prints the queue.
- `telemetry_fetch.py --list`: prints the configured sources. `--check <name>` tests one source with a read-only query (Sentry or ADX); the plan confirms what, if anything, it writes.
- `dtcc_watch.py --check`: validates the map and its paths; no fetch.
- `systemctl --user list-timers <args>`: lists the user's timers.

Rules without `*` match only that exact command. These apply to interactive sessions only; headless runs ignore project settings.

## 3. The `CLAUDE.md` line

Inserted after `- **Configuration:** …` in `## Vault Rules`, exactly:

```markdown
- **Bash:** Never chain bash commands with `&&`, `;`, or `||`; run each as its own tool call. Use absolute paths instead of `cd` (a `cd` persists and breaks `system/scripts/` invocation from the vault root). No `for`/`while` loops or inline `python3` heredocs: use Read, Grep and Edit, or write one script to the scratchpad and run it once. Create files with Write, not `>` redirects (capturing a test's exit code is the exception). Pipe only into read-only filters (`grep`, `head`, `sort`, `jq`). Batch remote work into one `ssh` call per task.
```

"Scratchpad" stays as the vault wrote it. A vault's `.scratch/` and Claude Code's session scratchpad both fit it; changing the word would make the vault's merge conflict.

## 4. Merging into the vault

Simulated with `git merge-file`: the base is the template's current `master`, "ours" is the vault at ec89abd, and "theirs" is this change.
- `CLAUDE.md`: no conflict; the merged file equals the vault's.
- `.claude/settings.json`: **one conflict**, on `"Bash(systemctl --user list-timers *)"`. The vault added its 23 vault-only rules after that line, so the vault gave it a trailing comma, and the template cannot (it is the array's last element).

The fix is on the vault side, and the vault owns it: before the vault merges this change, move the rules after `list-timers` to the top of the vault's `permissions.allow`, where its other vault-only rules already sit, so the template's block ends the array in both copies. Simulated, that merge is clean and keeps all 57 vault rules. The vault session (feOS) is asked to make that move. If the vault merges first anyway, the conflict is one line: keep the vault's side.

## 5. Tests

`system/tests/vault_integrity.bats` gains one test: the last eight entries of `permissions.allow` are the recall rule followed by the seven rules of §2, in order. This pins the block a vault merges against. It fails before the rules are added.

The `CLAUDE.md` line is prose; no test reads it.

Bound tools: bats, the gate (`system/scripts/verify_setup.sh`).

## 6. Out of scope

- The vault's other allow rules.
- Any change to the headless settings (`system/headless.settings.json`).
- Enforcing the Bash line (a hook or a lint).
