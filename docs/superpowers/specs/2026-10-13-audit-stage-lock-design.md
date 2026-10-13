# Staging lock and partial publish: no stage entry is lost, a held-back note is not a failed run

**Date:** 2026-10-13
**Status:** Draft for the owner's review.
**Issue:** #136 (C1, C2). From the 2026-10-13 audit (`docs/superpowers/2026-10-13-audit.md` on the audit branch).

## 1. Problem

C1: `publish.record_stage` loads `snapshot.json`, adds one `staged` entry and writes it back through `_write_json`, whose temporary file is always `snapshot.json.tmp`. Claude Code runs independent Bash calls concurrently, so two `vault_index.py stage` calls in one headless run interleave: one `staged` entry is lost and `_check` rejects the whole run with "existing note was not staged with vault_index.py stage". The input then counts a failed attempt for a race inside the gate.

C2: `_apply` holds back a target that changed between validation and the rename, publishes the rest and reports `status: conflict`. `publish_cli.OK_STATUSES` is `published`, `noop`, `aborted`, so the commit exits 5; `run_headless.sh` makes that `rc=5` and alerts "publish rejected or empty"; `intake.py` counts an attempt (5 is not in `NOT_INPUT_FAULT`) and three such runs poison an input whose notes did publish. `commit_runs.py` already commits a `conflict` run's published notes and the meeting import already treats `conflict` as a retry, so half the system reads it as a publish.

## 2. Decisions

- **`record_stage` holds an exclusive `fcntl.flock` on `<run dir>/stage.lock`** from the snapshot load to the write. The holder copies one file and writes one JSON document, so the lock blocks with no timeout. Under it the shared `.tmp` name is harmless, so no per-process name. `record_stage` is the only writer of `snapshot.json` after `snapshot()`. Not `system/run.lock`: `run_headless.sh` holds it for the whole run. Not `Intake.lock`: `intake` imports `publish`, and the lock is four lines.
- **`conflict` is a successful publish with held-back notes.** `publish_cli.OK_STATUSES` gains `conflict` (exit 0). `run_headless.sh` reads `.status` and `.conflicts` from the `publish.json` it already summarises and alerts `<cmd> <run_id>: published; held back <paths> (changed during the run; staged copies in system/quarantine/<run_id>/staged/)`. The ledger line already carries `publish.conflicts`. Why this over a partial-publish exit code: a new code would have to join the three exclusion lists (`write_ledger`'s jq, `runs_today`, `NOT_INPUT_FAULT`) and the daemon's branches; the status is already in `publish.json` and the ledger for anyone who needs to tell the two apart.
- **A held-back note is not retried.** The input is archived with its run (`rc == 0`); the staged copy waits in quarantine, where the alert points. The owner edited that note during the run and that edit stands. **Owner decision:** this, or re-run the input (today's behaviour minus the poisoning), which replays every note of the input against a note still being edited. Recommendation: no retry.

## 3. Changes

- `vaultlib/publish.py`: the lock in `record_stage`.
- `vaultlib/publish_cli.py`: `OK_STATUSES`.
- `system/scripts/run_headless.sh`: the held-back alert after `publish_staged.py commit`.
- `FOUNDRY.md`, Publish step: after "your edit is kept", one sentence: a note you edited while the gate was renaming is held back, the rest publishes, and the alert names the staged copy under `system/quarantine/`.
- `nightshift_deliver.publish_research` still treats `conflict` as a failure: a findings note is one target, so a conflict there is the whole result, and the item is better queued again. Unchanged.

**Existing vault:** no config or unit change. A poisoned input whose only failures were partial publishes is restored with `intake.py --retry` by hand.

## 4. Tests

pytest `test_publish.py`: while `record_stage` writes (patched `_write_json`), a non-blocking flock on `stage.lock` from a fresh descriptor raises `BlockingIOError`. `test_stage_cli.py`: 20 `vault_index.py stage` subprocesses for 20 targets started together leave 20 `staged` entries (fails on most runs before the change, on none after); a `conflict` report exits 0 while `rejected` and `empty` stay 5. bats `headless.bats`: with `publish_staged.py` replaced by a stub whose `commit` reports `conflict` with one held-back path, the run exits 0, the ledger line carries the path under `publish.conflicts`, the alert names it and the stream file is removed as for a success. Each fails before the change. Bound tools: pytest, bats and the gate.

## 5. Out of scope

- `recover` writing `publish.json` for a committed journal (C10).
- A conflict found at validation ("target changed during the run" in `_check`): still a rejection, since nothing published.
- The research publish path.
