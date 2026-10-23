"""RCA-to-Jira (RCA spec §3.3): pending drafts, the filer's arguments, the session check and the write-back."""
import shutil

import pytest

import helpers
from helpers import REPO, write
from telemetrylib import rca
from vaultlib import cli, connector, now

TODAY = "2026-10-11"
CONFIG = ('---\ntype: config\ntimezone: "America/Denver"\nhandoffs_site: "example.atlassian.net"\nrca_project: "EX"\n'
          'rca_labels: ["production-finding"]\n---\n')
DRAFT = ("## Ticket draft\n\n**Summary:** Orders fail when the reference is empty\n\n**Description:**\n"
         "Symptom: 409 on submit.\n\nRoot cause: `src/app/orders.py:42`.\n")


def note(vault, stem="2026-10-11-orders", partition="work", status="draft", ticket="", body=DRAFT):
    extra = f'ticket: "{ticket}"\n' if ticket else ""
    return write(vault, f"wiki/{partition}/rca/{stem}.md",
                 f'---\ntype: rca\ntitle: "Orders fail"\npartition: {partition}\ncreated_at: "{TODAY}"\n'
                 f'source: "raw/telemetry/a.md"\nrc_confidence: 4\nfix_confidence: 4\nstatus: {status}\n{extra}---\n'
                 f"# Orders fail\n\n## Root cause\n\nx\n\n{body}")


def prepare(vault, config=CONFIG):
    shutil.copytree(REPO / "system" / "templates", vault / "system" / "templates", dirs_exist_ok=True)
    write(vault, "system/config.md", config)


def line(vault, stem, mark=" ", partition="work"):
    now.add(vault, partition, "owed", f"Review RCA draft: {stem}", TODAY, evidence=f"rca:{stem}")
    path = vault / f"wiki/{partition}/Now.md"
    path.write_text(path.read_text().replace(f"- [ ] owed: Review RCA draft: {stem}", f"- [{mark}] owed: Review RCA draft: {stem}"))


def test_pending_finds_ticked_and_dropped_drafts_only(vault):
    prepare(vault)
    for stem, mark in (("a-ticked", "x"), ("b-dropped", "-"), ("c-open", " "), ("d-filed", "x")):
        note(vault, stem, status="filed" if stem == "d-filed" else "draft", ticket="EX-1" if stem == "d-filed" else "")
        line(vault, stem, mark)
    now.add(vault, "work", "owed", "Not an rca line", TODAY, evidence="EX-9")
    assert rca.pending(vault) == [("file", "work", "a-ticked"), ("reject", "work", "b-dropped")]


def test_a_dropped_draft_whose_key_is_saved_is_written_back_not_rejected(vault):
    # #106: a ticket already exists in Jira, so the drop files (rca_file.sh only writes the saved key back)
    prepare(vault)
    note(vault, "a-dropped")
    line(vault, "a-dropped", "-")
    write(vault, "system/logs/rca/work-a-dropped.key", "EX-5\n")
    assert rca.pending(vault) == [("file", "work", "a-dropped")]


def test_an_approved_draft_stays_pending_after_its_now_line_is_pruned(vault):
    prepare(vault)
    path = note(vault, "a-approved")
    line(vault, "a-approved", "x")
    rca.approve(vault, "work", "a-approved")
    assert 'status: "approved"' in path.read_text()
    (vault / "wiki/work/Now.md").write_text(now.read(vault, "work").replace("- [x] owed: Review RCA draft: a-approved", ""))
    assert rca.pending(vault) == [("file", "work", "a-approved")]


def test_a_description_keeps_its_own_headings(vault):
    prepare(vault)
    note(vault, body=DRAFT + "\n## Root cause\n\nThe reference is empty.\n")
    assert rca.arguments(vault, "work", "2026-10-11-orders")["description"].endswith(
        "## Root cause\n\nThe reference is empty.")


def test_arguments_come_from_the_settings_and_the_draft_only(vault):
    prepare(vault)
    note(vault)
    assert rca.arguments(vault, "work", "2026-10-11-orders") == {
        "cloudId": "example.atlassian.net", "projectKey": "EX", "issueTypeName": "Bug",
        "summary": "Orders fail when the reference is empty",
        "description": "Symptom: 409 on submit.\n\nRoot cause: `src/app/orders.py:42`.",
        "contentFormat": "markdown", "additional_fields": {"labels": ["production-finding"]}}


def test_extra_fields_go_beside_the_labels_and_json_values_are_sent_as_json(vault):
    # #175: a project whose Bug type has a required custom field
    prepare(vault, CONFIG.replace(
        "\n---\n", '\nrca_extra_fields: {customfield_10042: \'{"id": "10042"}\', customfield_10050: "Payments"}\n---\n'))
    note(vault)
    assert rca.arguments(vault, "work", "2026-10-11-orders")["additional_fields"] == {
        "labels": ["production-finding"], "customfield_10042": {"id": "10042"}, "customfield_10050": "Payments"}


def test_extra_fields_may_not_name_the_labels(vault):
    prepare(vault, CONFIG.replace("\n---\n", '\nrca_extra_fields: {labels: "x"}\n---\n'))
    note(vault)
    with pytest.raises(rca.Fail) as e:
        rca.arguments(vault, "work", "2026-10-11-orders")
    assert e.value.code == 2 and "rca_labels" in e.value.reason


@pytest.mark.parametrize("config,body,reason", [
    (CONFIG.replace('rca_project: "EX"', 'rca_project: ""'), DRAFT, "rca_project"),
    (CONFIG.replace('"example.atlassian.net"', '"https://x"'), DRAFT, "handoffs_site"),
    (CONFIG, "## Fix\n\nnone\n", "Ticket draft"),
    (CONFIG, DRAFT.replace("**Summary:** Orders fail when the reference is empty", "**Summary:**"), "Summary"),
])
def test_incomplete_settings_or_drafts_are_a_usage_error(vault, config, body, reason):
    prepare(vault, config)
    note(vault, body=body)
    with pytest.raises(rca.Fail) as e:
        rca.arguments(vault, "work", "2026-10-11-orders")
    assert e.value.code == 2 and reason in e.value.reason


def session(args, tool=rca.TOOL, calls=1, error=False, result=None, content="…"):
    sc = result if result is not None else {"key": "EX-7", "id": "1"}
    return helpers.stream(tool, [helpers.call(args, content, sc, error)] * calls)


def test_the_session_check_reads_the_key_and_refuses_anything_else(vault):
    prepare(vault)
    note(vault)
    args = rca.arguments(vault, "work", "2026-10-11-orders")
    assert rca.extract(session(args), args) == "EX-7"
    assert rca.extract(session(args, result={"issue": {"key": "EX-8"}}), args) == "EX-8"
    for s, code in ((session(args, tool="mcp__claude_ai_Atlassian__editJiraIssue"), 7),
                    (session({**args, "summary": "something else"}), 7),
                    (session(args, calls=2), 7),
                    (session(args, error=True), 6),
                    (session(args, result={"id": "1"}), 1)):
        with pytest.raises(rca.Fail) as e:
            rca.extract(s, args)
        assert e.value.code == code


def test_called_says_whether_the_session_called_the_create_tool(vault):
    prepare(vault)
    note(vault)
    args = rca.arguments(vault, "work", "2026-10-11-orders")
    assert rca.called(session({**args, "summary": "something else"})) is True
    assert rca.called(session(args, tool="mcp__claude_ai_Atlassian__editJiraIssue")) is False


REQUIRED = [{"type": "text", "text": 'Error: 400 Bad Request: {"errors":{"customfield_10042":"Team is required."}}'}]


def test_a_client_rejection_proves_nothing_was_created(vault):
    # #175: the 2026-10-14 required-field 400 left a marker that blocked every later tick
    prepare(vault)
    note(vault)
    args = rca.arguments(vault, "work", "2026-10-11-orders")
    assert rca.rejected_create(session(args, error=True, content=REQUIRED)) == (
        'Error: 400 Bad Request: {"errors":{"customfield_10042":"Team is required."}}')
    assert rca.rejected_create(session(args, error=True, content="403 Forbidden")) is not None
    for s in (session(args, error=True, content="Request timed out"),
              session(args, error=True, content="500 Internal Server Error"),
              session(args),
              session(args, result={"id": "1"}),
              session(args, tool="mcp__claude_ai_Atlassian__editJiraIssue", error=True, content=REQUIRED)):
        assert rca.rejected_create(s) is None
    created_then_rejected = session(args) + session(args, error=True, content=REQUIRED)[2:]
    assert rca.rejected_create(created_then_rejected) is None   # a ticket may exist


def test_rca_fails_with_the_shared_fail():
    assert rca.Fail is connector.Fail


def test_a_create_with_no_result_message_still_returns_its_key(vault):
    # #122: a session killed after the create returned keeps its key
    prepare(vault)
    note(vault)
    args = rca.arguments(vault, "work", "2026-10-11-orders")
    assert rca.extract(session(args)[:-1], args) == "EX-7"


def test_a_second_create_call_fails_7_even_after_an_error(vault):
    prepare(vault)
    note(vault)
    args = rca.arguments(vault, "work", "2026-10-11-orders")
    s = helpers.stream(rca.TOOL, [helpers.call(args, "500 Internal Server Error", error=True),
                                  helpers.call(args, sc={"key": "EX-7"})])
    with pytest.raises(rca.Fail) as e:
        rca.extract(s, args)
    assert e.value.code == 7


def test_a_create_result_too_large_for_the_model_fails_6(vault):
    prepare(vault)
    note(vault)
    args = rca.arguments(vault, "work", "2026-10-11-orders")
    big = "Error: result (40,000 characters) exceeds maximum allowed tokens. Output has been saved to /x/1.txt"
    with pytest.raises(rca.Fail) as e:
        rca.extract(session(args, content=big), args)
    assert e.value.code == 6


def test_a_session_that_used_another_tool_is_never_a_clean_rejection(vault):
    prepare(vault)
    note(vault)
    args = rca.arguments(vault, "work", "2026-10-11-orders")
    s = session(args, error=True, content=REQUIRED)
    s.insert(-1, {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t9", "name": "Bash",
                                                                "input": {"command": "true"}}]}})
    assert rca.rejected_create(s) is None


def test_reopen_unticks_the_line_with_the_reason_and_returns_the_draft(vault):
    prepare(vault)
    path = note(vault)
    line(vault, "2026-10-11-orders", "x")
    now.add(vault, "work", "owed", "Another line", TODAY)
    rca.approve(vault, "work", "2026-10-11-orders")
    rca.reopen(vault, "work", "2026-10-11-orders", 'Jira: "Team is required." (customfield_10042)', TODAY)
    page = now.read(vault, "work")
    # The reason joins the bare statement; the line keeps its Now clock field after it (Now clock spec §3).
    reopened = next(l for l in page.split("\n") if "rca:2026-10-11-orders" in l)
    assert reopened.startswith("- [ ] owed: Review RCA draft: 2026-10-11-orders: not filed 2026-10-11, "
                               "Jira: \"Team is required.\" customfield_10042 [due:: ")
    assert reopened.endswith("] (since 2026-10-11, rca:2026-10-11-orders)")
    assert "- [ ] owed: Another line [due:: 2026-11-10] (since 2026-10-11)" in page
    assert 'status: "draft"' in path.read_text()
    assert rca.pending(vault) == []   # nothing retries until the line is ticked again
    rca.reopen(vault, "work", "2026-10-11-orders", "403 Forbidden", "2026-10-12")
    page = now.read(vault, "work")
    assert page.count("not filed") == 1 and "not filed 2026-10-12, 403 Forbidden [due:: " in page


def test_filed_writes_the_key_to_the_note_and_the_now_line(vault):
    prepare(vault)
    path = note(vault)
    line(vault, "2026-10-11-orders", "x")
    rca.filed(vault, "work", "2026-10-11-orders", "EX-7", TODAY)
    text = path.read_text()
    assert 'ticket: "EX-7"' in text and 'status: "filed"' in text
    assert "_(closed: filed EX-7 2026-10-11)_" in now.read(vault, "work")
    assert rca.pending(vault) == []


def test_filed_writes_the_ticket_and_the_status_in_one_write(vault, monkeypatch):
    # #106: a crash between two writes would leave a ticket on a note still marked approved
    prepare(vault)
    path = note(vault, status="approved")
    writes, real = [], cli.write_atomic
    monkeypatch.setattr(cli, "write_atomic", lambda p, t: (writes.append(p), real(p, t)))
    rca.filed(vault, "work", "2026-10-11-orders", "EX-7", TODAY)
    assert writes.count(path) == 1


def test_rejected_sets_the_status(vault):
    prepare(vault)
    path = note(vault)
    rca.rejected(vault, "work", "2026-10-11-orders")
    assert 'status: "rejected"' in path.read_text()


# -- the intake tick (extensions spec §3, `tick`) -------------------------------
def tick_draft(vault, stem, mark):
    write(vault, f"wiki/work/rca/{stem}.md", '---\ntype: rca\ntitle: "T"\npartition: work\ncreated_at: "2026-10-11"\n'
          'source: "raw/telemetry/a.md"\nrc_confidence: 3\nfix_confidence: 3\nstatus: draft\n---\n# T\n')
    page = vault / "wiki/work/Now.md"
    old = page.read_text() if page.exists() else ('---\ntype: concept\ntags: [now]\ncompiled_at: "2026-10-11"\n'
                                                  'partition: work\n---\n# Now\n\n## Needs you\n\n## Waiting\n')
    page.write_text(old.replace("## Needs you\n", f"## Needs you\n- [{mark}] owed: Review RCA draft: {stem} "
                                                  f"(since 2026-10-11, rca:{stem})\n"))


def test_the_tick_is_off_without_rca_project(vault):
    prepare(vault, CONFIG.replace('rca_project: "EX"\n', ""))
    tick_draft(vault, "a", "-")
    rca.tick(vault)
    assert "status: draft" in (vault / "wiki/work/rca/a.md").read_text()


def test_the_tick_rejects_dropped_drafts_and_files_ticked_ones_up_to_the_cap(vault):
    prepare(vault)
    stub = vault / "extensions/telemetry/scripts/rca_file.sh"
    stub.write_text(f'#!/bin/bash\necho "$*" >> {vault}/filer.calls\n')
    stub.chmod(0o755)
    tick_draft(vault, "dropped", "-")
    for n in range(4):
        tick_draft(vault, f"ticked{n}", "x")
    rca.tick(vault)
    assert 'status: "rejected"' in (vault / "wiki/work/rca/dropped.md").read_text()
    calls = (vault / "filer.calls").read_text().splitlines()
    assert len(calls) == rca.PER_TICK == 3
    for call in calls:
        assert 'status: "approved"' in (vault / f"wiki/work/rca/{call.split()[1]}.md").read_text()


def test_a_busy_run_lock_ends_the_tick_with_nothing_changed(vault):
    import fcntl
    prepare(vault)
    tick_draft(vault, "dropped", "-")
    with open(vault / "system" / "run.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        rca.tick(vault)
    assert "status: draft" in (vault / "wiki/work/rca/dropped.md").read_text()


def test_reopen_cuts_a_long_jira_reason_and_redacts_it(vault):
    prepare(vault)
    stem = "2026-10-11-" + "o" * 90
    note(vault, stem)
    line(vault, stem, "x")
    key = "ghp_" + "a" * 36
    rca.reopen(vault, "work", stem, f"password={key} " + "r" * 200, TODAY)
    reopened = next(l for l in now.read(vault, "work").split("\n") if f"rca:{stem}" in l)
    assert reopened.startswith("- [ ] owed: Review RCA draft: ")
    assert len(reopened) <= now.MAX_LINE
    assert key not in reopened
    assert reopened.endswith(f"(since {TODAY}, rca:{stem})")
