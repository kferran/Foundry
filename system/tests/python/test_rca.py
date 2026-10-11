"""RCA-to-Jira (RCA spec §3.3): pending drafts, the filer's arguments, the session check and the write-back."""
import shutil

import pytest

from helpers import REPO, write
from vaultlib import now, rca

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


def test_arguments_come_from_the_settings_and_the_draft_only(vault):
    prepare(vault)
    note(vault)
    assert rca.arguments(vault, "work", "2026-10-11-orders") == {
        "cloudId": "example.atlassian.net", "projectKey": "EX", "issueTypeName": "Bug",
        "summary": "Orders fail when the reference is empty",
        "description": "Symptom: 409 on submit.\n\nRoot cause: `src/app/orders.py:42`.",
        "contentFormat": "markdown", "additional_fields": {"labels": ["production-finding"]}}


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


def stream(args, tool=rca.TOOL, calls=1, error=False, result=None):
    s = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t0", "name": "ToolSearch", "input": {}}]}},
         {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t0",
                                                   "content": [{"type": "tool_reference", "tool_name": rca.TOOL}]}]}}]
    for n in range(1, calls + 1):
        s.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{n}", "name": tool, "input": args}]}})
        s.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{n}", "is_error": error,
                                                           "content": "…"}]},
                  "tool_use_result": {"structuredContent": result if result is not None else {"key": "EX-7", "id": "1"}}})
    s.append({"type": "result", "subtype": "success", "is_error": False})
    return s


def test_the_session_check_reads_the_key_and_refuses_anything_else(vault):
    prepare(vault)
    note(vault)
    args = rca.arguments(vault, "work", "2026-10-11-orders")
    assert rca.extract(stream(args), args) == "EX-7"
    assert rca.extract(stream(args, result={"issue": {"key": "EX-8"}}), args) == "EX-8"
    for s, code in ((stream(args, tool="mcp__claude_ai_Atlassian__editJiraIssue"), 7),
                    (stream({**args, "summary": "something else"}), 7),
                    (stream(args, calls=2), 7),
                    (stream(args, error=True), 6),
                    (stream(args, result={"id": "1"}), 1)):
        with pytest.raises(rca.Fail) as e:
            rca.extract(s, args)
        assert e.value.code == code


def test_filed_writes_the_key_to_the_note_and_the_now_line(vault):
    prepare(vault)
    path = note(vault)
    line(vault, "2026-10-11-orders", "x")
    rca.filed(vault, "work", "2026-10-11-orders", "EX-7", TODAY)
    text = path.read_text()
    assert 'ticket: "EX-7"' in text and 'status: "filed"' in text
    assert "_(closed: filed EX-7 2026-10-11)_" in now.read(vault, "work")
    assert rca.pending(vault) == []


def test_rejected_sets_the_status(vault):
    prepare(vault)
    path = note(vault)
    rca.rejected(vault, "work", "2026-10-11-orders")
    assert 'status: "rejected"' in path.read_text()
