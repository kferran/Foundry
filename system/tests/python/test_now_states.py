"""The Now line's state table (factory F7 spec §3): vaultlib/now_states.py."""
import json

from vaultlib import now_states as ns

BODY = "owed: Pick the export format [due:: 2026-11-08] (since 2026-10-09)"
STAMPED = " _(closed: ticked 2026-10-10)_"
LINES = {"open": f"- [ ] {BODY}", "open stamped": f"- [ ] {BODY}{STAMPED}", "done": f"- [x] {BODY}",
         "done stamped": f"- [x] {BODY}{STAMPED}", "dropped": f"- [-] {BODY}",
         "dropped stamped": f"- [-] {BODY}{STAMPED}", "unknown": f"- [/] {BODY}"}
# The spec §3 table, as (writer, from, to): every other triple is refused.
TABLE = {("brief", None, "open"),
         ("check", "open", "done stamped"), ("check", "open", "dropped stamped"),
         ("stamp", "done", "done stamped"), ("stamp", "dropped", "dropped stamped"), ("stamp", "open stamped", "open"),
         ("rca", "done", "done stamped"), ("rca", "done stamped", "done stamped"),
         ("rca", "done", "open"), ("rca", "done stamped", "open"), ("rca", "dropped", "open"),
         ("rca", "dropped stamped", "open")}
WRITERS = ("brief", "check", "stamp", "rca", "merge", "session")


def test_state_reads_the_mark_and_the_stamp():
    assert {s: ns.state(line) for s, line in LINES.items()} == {s: s for s in LINES}
    assert ns.state(f"- [X] {BODY}") == "done"
    assert ns.state(f"- [X] {BODY}{STAMPED}") == "done stamped"
    assert ns.state(f"- [/] {BODY}{STAMPED}") == "unknown"
    assert ns.STATE == {" ": "open", "x": "done", "X": "done", "-": "dropped"}
    assert [ns.state(x) for x in (None, "", "## Needs you", "  - 2026-10-09: a note", "- plain")] == [None] * 5


def test_every_writer_from_every_state_to_every_state_changes_only_the_tables_pairs(vault):
    log = vault / "system/logs/now-2026-10.jsonl"
    for writer in WRITERS:
        for frm in (None, *ns.STATES):
            for to in ns.STATES:
                assert ns.allowed(writer, frm, to) == ((writer, frm, to) in TABLE), (writer, frm, to)
                if frm is None:
                    continue
                out = ns.transition(LINES[frm], writer, to, "PR merged", "2026-10-11", vault)
                if (writer, frm, to) in TABLE:
                    assert ns.state(out) == to, (writer, frm, to)
                else:
                    assert out is None, (writer, frm, to)
    refused = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(refused) == sum(1 for w in WRITERS for f in ns.STATES for t in ns.STATES if (w, f, t) not in TABLE)
    assert set(refused[0]) == {"ts", "writer", "from", "to", "statement_hash"}
    assert "Pick" not in log.read_text()


def test_transition_builds_the_mark_and_stamp_and_keeps_the_rest():
    assert ns.transition(LINES["open"], "check", "done stamped", "PR merged", "2026-10-11") == (
        f"- [x] {BODY} _(closed: PR merged 2026-10-11)_")
    assert ns.transition(LINES["open"] + "  ", "check", "dropped stamped", "expired", "2026-10-11") == (
        f"- [-] {BODY} _(closed: expired 2026-10-11)_")
    assert ns.transition(f"- [X] {BODY}", "stamp", "done stamped", "ticked", "2026-10-11") == (
        f"- [X] {BODY} _(closed: ticked 2026-10-11)_")
    assert ns.transition(LINES["open stamped"], "stamp", "open") == LINES["open"]
    assert ns.transition(LINES["done stamped"], "rca", "done stamped", "filed EX-7", "2026-10-11") == (
        f"- [x] {BODY} _(closed: filed EX-7 2026-10-11)_")
    assert ns.transition(LINES["dropped stamped"], "rca", "open") == LINES["open"]


def test_a_refusal_without_a_vault_logs_nothing_and_never_raises(tmp_path):
    assert ns.transition(LINES["open"], "rca", "open") is None
    assert ns.transition(None, "brief", "done", vault=tmp_path / "missing" / "\0bad") is None
