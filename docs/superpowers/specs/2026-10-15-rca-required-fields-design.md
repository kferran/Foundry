# RCA filer: required custom fields, and a rejected create that does not stick

**Date:** 2026-10-15
**Status:** Merged by the owner 2026-10-15 (PR #198); built with three corrections from the build, marked "Build:" below.
**Issue:** #175. Phase 1 of `docs/superpowers/2026-10-15-next-phase-plan.md`.

## 1. Problem

On 2026-10-14 the owner approved an RCA draft. The filer's create call returned `400 Bad Request: "<custom select field> is required"`, because the project's Bug type has a required single-select field. Two things went wrong:

1. **No way to send a required field.** `rca.arguments()` builds `additional_fields` from `rca_labels` only. A project with a required custom field can never be filed to.
2. **A rejected create sticks.** `rca_file.sh` keeps the `.attempt` marker whenever `rca.py called` finds a create call in the stream, and a rejected call still counts as called. Every later tick then exits 5 ("an earlier session called the create tool and saved no key"). The exit-6 alert went out once; the exit-5 alerts that followed said to look in Jira for a ticket that never existed. The ticket was created by hand.

## 2. Decisions

- **`rca_extra_fields`**: a config map of Jira field id to value, merged into `additional_fields` next to `labels`. Build: the schema's `map` takes one value kind, so the values are strings; a value that parses as JSON is sent as that JSON (a select is `'{"id": "10042"}'`), any other as text. A key named `labels` is refused (2, "use rca_labels"), so the two settings never fight. `extract()` already compares the session's arguments with `arguments()` exactly, so the new fields are covered by the existing check.
- **A rejected create clears the marker.** A create call whose tool result has `is_error: true` and whose text matches a client rejection (`400`, `401`, `403`, `404`, `422`, `Bad Request`, `is required`, `is not valid`, `does not exist`) proves Jira created nothing. `rca.py` gets `rejected_create(stream)`, which returns the first such error line. When it does, `rca_file.sh` deletes `.attempt` and fails with exit 6 and that line. Any other error (a timeout, a 5xx, a dropped stream, a result with no key) keeps today's rule: the marker stays, because a ticket may exist.
- **The Now line reopens with the reason.** On a rejected create, `rca.py reopen <partition> <stem> <reason>` unticks the line whose evidence is `rca:<stem>` and puts `: not filed <date>, <reason>` at the end of its statement, so the owner sees why on the Now page (Build: a suffix after the evidence would stop `now.LINE` from parsing the line). The note goes back to `draft` (Build: an `approved` note is pending on every tick, so it would retry and fail every 5 minutes); ticking the line again approves and files it after the owner fixes the setting. A later rejection replaces the earlier reason. The existing `alert_once` line reaches Slack as it does today.
- **The assignee override in the approval text is left out.** The filer always uses `rca_assignee`; `FOUNDRY.md` says so.
- **Setup-time validation is left out of this spec.** Checking `rca_extra_fields` against `getJiraIssueTypeMetaWithFields` needs a second confined connector session with its own allow rule. The rejected-create path now names the missing field on the first filing, which covers the same failure. It can follow as a `rca_file.sh --check` for the smoke check if a second project needs it.

## 3. Changes

- `system/schemas/config.md`: `rca_extra_fields: {kind: map, of: string}`; `system/config.example.md`: the line, commented with an example.
- `system/scripts/vaultlib/rca.py`: `arguments()` merges `rca_extra_fields`; `rejected_create(stream)`; `reopen(vault, partition, stem, reason, today)`; the CLI gains `rejected` (reads the stream, prints the line, exits 0 when rejected and 1 otherwise) and `reopen`.
- `system/scripts/rca_file.sh`: on a failed session, `rca.py rejected` runs before `rca.py called`; when it matches, the script deletes `.attempt`, runs `rca.py reopen`, and fails 6 with the Jira error line.
- `FOUNDRY.md` RCA paragraph: `rca_extra_fields`, the rejected-create rule, the fixed assignee.

## 4. Tests

- pytest (`test_rca.py`): `arguments()` puts `rca_extra_fields` beside `labels` in `additional_fields`; a `labels` key in it is refused; `rejected_create` matches the 2026-10-14 required-field 400 and a 403, and does not match a timeout, a 500, or a success with no key; `reopen` unticks the `rca:<stem>` line and stamps the reason, and leaves other lines alone.
- bats (`rca.bats`): with a stub `claude` whose create call returns the required-field 400, `rca_file.sh` exits 6, leaves no `.attempt`, and the Now line is open with the reason; the next tick, with `rca_extra_fields` set and a stub that returns a key, files. With a stub whose create call returns a 500, `.attempt` stays (today's rule).

Each fails before the change. Bound tools: pytest, bats, the gate. No change to `run_headless.sh`, a settings file or the ingest, brief or debrief commands, so no live acceptance run; the owner's live check is one approved draft filed into the project that rejected it.

## 5. Out of scope

The deferred `/rca` entries and phase 2 on #106; the review minors from #120 listed there.
