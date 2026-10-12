# Slack Notices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A model-free collector gathers new brief, debrief, Work Order and alert events every 5 minutes, and one confined Slack connector session posts them as one message.

**Architecture:**
- `vaultlib/notify.py`: the cursor, the events, the message and the session check.
- `system/scripts/notify.py`: the CLI.
- `system/scripts/notify.sh`: the confined session, on the `triage_fetch.sh` pattern.
- A service and timer pair, installed when `slack_notify_channel` is set.

**Tech Stack:** Python 3 standard library, bash, jq, systemd, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-10-11-slack-notices-design.md`

## Global Constraints

- Branch `feat/slack-notices`. Each task commits; no task pushes.
- Run suites from the repository root: `bats system/tests/<suite>.bats`, `python3 -m pytest -q system/tests/python/<file>`; the gate is `system/scripts/verify_setup.sh`.
- Template rule: no channel or user ID, hostname, user path or remote URL in committed files. Fixtures use `C0EXAMPLE` and `git@github.com:owner/vault.git`.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.

---

### Task 1: The collector and the message (`vaultlib/notify.py`, `notify.py collect|commit`)

**Files:** Create `system/scripts/vaultlib/notify.py`, `system/scripts/notify.py`, `system/tests/python/test_notify.py`.

- [ ] Tests first:
  - First run sets the cursor and sends nothing.
  - Brief exit 0 gives the counts line and the GitHub link.
  - Brief exit 4 gives the failed line.
  - Debrief exit 0 gives the debrief link.
  - Alerts arrive in order, `[notify]` lines skipped, redacted, cut at 200 characters.
  - An outcome is sent once.
  - The message is cut at 4,000 characters with "+N more".
  - Links from SSH and HTTPS GitHub remotes; none for another host.
  - The prefix comes from both connector names.
- [ ] Implement `collect(vault, now) -> (events, cursor)`, `message(vault, events) -> str`, `prefix(name)`, `link(vault, path)`. Wire up `notify.py collect`, which prints JSON with `message`, `lines` and `cursor`, or nothing, and `notify.py commit <cursor file>`.
- [ ] Commit: `feat(notify): collect new brief, debrief, Work Order and alert events into one message (#28)`.

### Task 2: The session check (`notify.py check`)

**Files:** Modify `system/scripts/vaultlib/notify.py`, `system/scripts/notify.py`, `system/tests/python/test_notify.py`.

- [ ] Tests first. It passes the call with whitespace and bullet drift. It refuses:
  - another tool (the draft tool),
  - another channel,
  - an extra argument,
  - a missing event line,
  - a second call,
  - an error result.
  It is exit 3 when the connector was never reached.
- [ ] Implement `check(stream, channel, lines)` (exit codes as `rca.extract`) and `notify.py check <collected json>`.
- [ ] Commit: `feat(notify): the session check, exact on the tool and channel, every event line in the text (#28)`.

### Task 3: `notify.sh`, its units and the installer

**Files:**
- Create: `system/scripts/notify.sh`, `system/systemd/foundry-notify.service.in`, `system/systemd/foundry-notify.timer.in`, `system/tests/notify.bats`.
- Modify: `system/scripts/install_units.sh`, `system/tests/units.bats`, `system/tests/vault_integrity.bats` (executables).

- [ ] Tests first (stub claude). Covers:
  - nothing new, no session
  - a good post moves the cursor
  - a refused post exits 7, keeps the cursor and alerts once a day
  - an empty channel exits 0
  - `--check` posts the test text
  - the units only with a channel set, never on a client
- [ ] Implement on the `triage_fetch.sh` pattern: lock, `collect`, `confine_settings`, `confine_deny --strict` with the plugin's tool list, one session, `check`, `commit`, the log and `[notify]` alerts.
- [ ] Commit: `feat(notify): notify.sh posts through one confined Slack session every 5 minutes (#28)`.

### Task 4: Config, setup and manual

**Files:** Modify `system/config.example.md`, `system/schemas/config.md`, `.claude/commands/setup.md` (phase 6d), `FOUNDRY.md`, `system/tests/commands.bats`.

- [ ] Tests first: `commands.bats` pins phase 6d (the yes, the channel, the connector listing, `--check` only on yes) and the manual paragraph; the config example validates.
- [ ] Write the keys, the phase and the paragraph.
- [ ] Run the gate. Commit: `docs(notify): config keys, /setup phase 6d and the manual (#28)`.
