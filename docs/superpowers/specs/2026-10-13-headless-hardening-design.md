# Headless hardening: three gate and settings gaps from the audit

**Date:** 2026-10-13
**Status:** Built in PR #141 (2026-10-13).
**Issue:** Part of #136 (audit S2, S4, S5; `docs/superpowers/2026-10-13-audit.md`).

## 1. Problem

The audit found three places where a rule the system relies on is enforced only by prompt text or by a missing list entry. Each lets a poisoned input, compiled by a headless ingest, do something the security model says it cannot:

- **S2.** `publish._walls` skips the partition-wall check for any note of `type: index`, and the index schema's `folders` is all of `wiki/`. An ingest can stage `wiki/personal/concepts/X.md` with `type: index` and links into `work`, and it publishes.
- **S5.** Ingest may publish anywhere under `wiki/<partition>/`. "Never stage or edit `wiki/<p>/Now.md`" is a sentence in `ingest.md`; the gate refuses only `meetings/`. A poisoned digest can add fake owed lines the brief and recall then carry.
- **S4.** `system/headless.settings.json` denies reads of `~/.ssh`, `~/.gnupg`, the Claude credentials and `.env` files, but not `~/.config/foundry` (the Sentry token), `~/.config/gh`, `~/.git-credentials`, `~/.netrc`, `~/.azure`, `~/.aws` or `~/.claude/projects` (session transcripts), and it has no sandbox `denyRead` list. The Work Order profile (`system/nightshift/plan.settings.json`) already denies most of these.

## 2. Decisions

- **One index note.** The index schema covers `wiki/Index.md` only, and `_walls` skips only that path. Nothing else in the template or a vault has `type: index`.
- **Ingest never publishes a Now page.** `_check` refuses `wiki/<partition>/Now.md` for the `ingest` command, as it refuses meeting notes, with the message "the Now page is written only by now.py and the brief". The brief keeps writing it. Preference notes stay publishable by ingest: creating them is ingest's step 9, and a preference is data that never authorizes an action (`CLAUDE.md`, Lifecycle).
- **The headless Read denies match the Work Order profile.** `permissions.deny` gains `Read(~/.config/foundry/**)`, `Read(~/.config/gh/**)`, `Read(~/.git-credentials)`, `Read(~/.netrc)`, `Read(~/.azure/**)`, `Read(~/.aws/**)` and `Read(~/.claude/projects/**)`; `sandbox.filesystem.denyRead` lists the same paths plus the existing credential paths, so Bash under the sandbox is fenced too.

## 3. Changes

- `system/schemas/index.md`: `folders: ["wiki/Index.md"]`.
- `system/scripts/vaultlib/publish.py`: `_walls` returns early only for `wiki/Index.md`; `_check` refuses an ingest's `Now.md`.
- `system/headless.settings.json`: the denies above.

**Existing vault:** nothing changes for notes the system writes today. A vault's own note of `type: index` outside `wiki/Index.md` would fail schema validation; none is known. After the settings change, the live acceptance steps run once (brief, debrief, ingest in a throwaway clone), as `FOUNDRY.md` Development asks for any settings change.

## 4. Tests

- pytest (`test_publish.py`): a staged `wiki/personal/concepts/X.md` with `type: index` linking a `work` note is refused (schema and wall); `wiki/Index.md` still publishes with cross-partition links; an ingest that stages `wiki/work/Now.md` is refused; a brief that stages it publishes.
- bats (`vault_integrity.bats`): the headless settings deny each path above in `permissions.deny` and in `sandbox.filesystem.denyRead`.

Each fails before the change. Bound tools: pytest, bats, the gate, the live acceptance steps.

## 5. Out of scope

S1 (the signed or opt-in update), S3 and S7 (the Work Order session profile and environment), S6 (transcript drops) and S10 (per-run partition read fences) are their own specs on #136.
