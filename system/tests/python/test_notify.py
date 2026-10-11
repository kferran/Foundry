"""Slack notices (Slack notices spec §3.1): the collector, the message, the link and the session check."""
import json
import subprocess
from datetime import datetime

import pytest

from helpers import write
from vaultlib import notify

NOW = datetime(2026, 10, 12, 6, 30)
TOOL = "mcp__plugin_slack_slack__slack_send_message"
NOW_PAGE = ("---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-12\"\npartition: work\n---\n# Now\n\n## Needs you\n"
            "- [ ] owed: Send the plan (since 2026-10-10)\n- [ ] draft: Reply to the vendor (since 2026-10-11)\n"
            "- [x] owed: Done already (since 2026-10-09) _(closed: 2026-10-11)_\n\n## Waiting\n"
            "- [ ] waiting: The quote (Avery Sample, since 2026-10-08)\n")


def prepare(vault, remote="git@github.com:owner/vault.git"):
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\nslack_notify_channel: "C0EXAMPLE"\n---\n')
    write(vault, "wiki/work/Now.md", NOW_PAGE)
    subprocess.run(["git", "init", "-q", "-b", "master", str(vault)], check=True)
    if remote:
        subprocess.run(["git", "-C", str(vault), "remote", "add", "origin", remote], check=True)
    notify.commit(vault, notify.collect(vault, NOW)[1])  # the first run: cursor only


def ledger(vault, command, rc, finished="2026-10-12T06:04:00-06:00"):
    path = vault / "system/logs/runs-2026-10.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"command": command, "exit": rc, "finished_at": finished}) + "\n")


def alert(vault, text, day="2026-10-12"):
    path = vault / f"system/logs/alerts_{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(f"- 06:10:00 {text}\n")


def lines(vault):
    events, cursor = notify.collect(vault, NOW)
    return notify.message(vault, events)[1], cursor


def test_the_first_run_sets_the_cursor_and_sends_nothing(vault):
    ledger(vault, "brief", 0)
    alert(vault, "[intake] old")
    prepare(vault)
    assert lines(vault)[0] == []


def test_a_brief_gives_counts_and_a_link_and_a_failure_its_exit(vault):
    prepare(vault)
    ledger(vault, "brief", 0)
    alert(vault, "[intake] one")
    ledger(vault, "debrief", 4, "2026-10-12T18:30:00-06:00")
    got, _ = lines(vault)
    assert got[0] == ("Brief 2026-10-12: 2 need you, 1 waiting, 1 alerts today "
                      "https://github.com/owner/vault/blob/master/briefings/2026-10-12.md")
    assert got[1] == "Debrief 2026-10-12 failed (exit 4)"


def test_a_debrief_gives_its_link(vault):
    prepare(vault)
    ledger(vault, "debrief", 0, "2026-10-12T18:30:00-06:00")
    assert lines(vault)[0] == ["Debrief 2026-10-12 is ready "
                               "https://github.com/owner/vault/blob/master/briefings/2026-10-12.debrief.md"]


def test_alerts_arrive_in_order_without_notify_lines_redacted_and_cut(vault):
    prepare(vault)
    alert(vault, "[intake] first")
    alert(vault, "[notify] Notices failed (exit 6): x")
    alert(vault, "[telemetry] key sk-ant-api03-" + "A" * 40)
    alert(vault, "[dtcc] " + "y" * 300)
    got, _ = lines(vault)
    assert got[0] == "Alert 06:10:00 [intake] first"
    assert len(got) == 3
    assert "sk-ant-api03" not in got[1]
    assert len(got[2]) == notify.LINE_MAX


def test_a_work_order_is_sent_once(vault):
    prepare(vault)
    write(vault, "system/logs/nightshift/items/2026-10-12-x/outcome.json",
          json.dumps({"id": "2026-10-12-x", "state": "done", "result": "https://github.com/owner/repo/pull/7", "needs": []}))
    got, cursor = lines(vault)
    assert got == ["Work Order 2026-10-12-x done: https://github.com/owner/repo/pull/7"]
    notify.commit(vault, cursor)
    assert lines(vault)[0] == []


def test_nothing_is_lost_while_the_cursor_is_not_committed(vault):
    prepare(vault)
    alert(vault, "[intake] first")
    lines(vault)
    alert(vault, "[intake] second")
    assert lines(vault)[0] == ["Alert 06:10:00 [intake] first", "Alert 06:10:00 [intake] second"]


def test_a_long_message_is_cut_with_a_count(vault):
    prepare(vault)
    for n in range(40):
        alert(vault, f"[intake] {n} " + "z" * 150)
    text, sent = notify.message(vault, notify.collect(vault, NOW)[0])
    assert len(text) <= notify.MESSAGE_MAX
    assert text.endswith(f"• +{40 - len(sent)} more")


@pytest.mark.parametrize("remote,url", [
    ("git@github.com:owner/vault.git", "https://github.com/owner/vault/blob/master/briefings/x.md"),
    ("https://github.com/owner/vault.git", "https://github.com/owner/vault/blob/master/briefings/x.md"),
    ("git@gitlab.example.com:owner/vault.git", ""),
    ("", ""),
])
def test_the_link_is_a_github_file_link_or_nothing(vault, remote, url):
    prepare(vault, remote)
    assert notify.link(vault, "briefings/x.md") == url


def test_the_tool_prefix_comes_from_the_connector_name():
    assert notify.prefix("plugin:slack:slack") == "mcp__plugin_slack_slack"
    assert notify.prefix("claude.ai Slack") == "mcp__claude_ai_Slack"


def session(name=TOOL, channel="C0EXAMPLE", message="• Alert one\n• Alert two", calls=1, error=False, extra=None):
    s = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t0", "name": "ToolSearch", "input": {}}]}},
         {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t0",
                                                   "content": [{"type": "tool_reference", "tool_name": TOOL}]}]}}]
    for n in range(1, calls + 1):
        args = {"channel_id": channel, "message": message, **(extra or {})}
        s.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{n}", "name": name, "input": args}]}})
        s.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{n}", "is_error": error,
                                                           "content": "ok"}]}})
    return s


def test_the_check_is_exact_on_tool_and_channel_and_needs_every_line():
    sent = ["Alert one", "Alert two"]
    notify.check(session(), TOOL, "C0EXAMPLE", sent)
    notify.check(session(message="- Alert  one\n\n-   Alert two  "), TOOL, "C0EXAMPLE", sent)
    for s, code in ((session(name="mcp__plugin_slack_slack__slack_send_message_draft"), 7),
                    (session(channel="C0OTHER"), 7),
                    (session(extra={"thread_ts": "1"}), 7),
                    (session(message="• Alert one"), 7),
                    (session(calls=2), 7),
                    (session(error=True), 6),
                    (session()[:2], 1),
                    ([], 3)):
        with pytest.raises(notify.Fail) as e:
            notify.check(s, TOOL, "C0EXAMPLE", sent)
        assert e.value.code == code
