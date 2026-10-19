"""The today file's writer (phase D spec §3.6; plan Task 9)."""
import json

import today_log as tl
from watchlib import route

DAY = "2026-10-19"


def item(vault, key, kind="meeting", text="Weekly Huddle cancelled today (#gstaff)", now="", link="https://x.slack.com/archives/C1/p1",
         partition="work"):
    from watchlib.common import append
    append(route.ledger_path(vault, DAY), {"key": key, "day": DAY, "time": "08:47", "kind": kind, "text": text,
                                           "link": link, "now": now, "partition": partition})


def today(vault):
    return (vault / "briefings" / f"{DAY}.today.md").read_text()


def digest(vault, name=f"{DAY}-1141-1a2b3c4d-traced.md", folder="archive", partition="work", body=None, created=f"{DAY}T11:41:00-06:00"):
    p = vault / "raw" / partition / folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'---\ntype: session_digest\npartition: {partition}\ncodebase: "shop"\nsession_id: "s"\ncreated_at: "{created}"\n---\n'
                 + (body or "## Outcome\nTraced the 404s to the partner's QA endpoint. Then more.\n\n## Delivered\n"
                            "- message — thread reply with traces — https://x\n\n## Follow-ups\n- check the fix\n"))


def test_items_digests_and_meetings_land_once_in_time_order_with_frontmatter(vault):
    item(vault, "watch:a", kind="deadline", text="QBR deck (#gstaff)", now="added")
    item(vault, "cal:x", text="1:1 Pat moved from 10:00-10:30 to 11:00-11:30", link="")
    digest(vault)
    digest(vault, "p1.md", partition="personal")
    note = vault / "wiki" / "work" / "meetings" / "2026-10-19-1400-pilot-sync.md"
    note.parent.mkdir(parents=True)
    note.write_text('---\ntype: meeting\n---\n## Decisions\n- ship it\n- wait\n\n## Action items\n- [ ] [Kyle Owner] Send the doc\n'
                    "- [ ] [Pat] Book the room\n")
    cfg = vault / "system" / "config.md"
    cfg.write_text(cfg.read_text().replace("---\ntype", '---\nowner_names: ["Kyle Owner"]\ntype', 1))
    log = vault / "system" / "logs" / f"meetings-{DAY[:7]}.jsonl"
    log.write_text(json.dumps({"time": f"{DAY}T14:40:00-06:00", "kind": "imported", "note": "wiki/work/meetings/2026-10-19-1400-pilot-sync.md"}) + "\n"
                   + json.dumps({"time": f"{DAY}T15:00:00-06:00", "kind": "imported", "note": "wiki/work/meetings/missing.md"}) + "\n")
    tl.write(vault, DAY, "15:05:00")
    assert today(vault) == (
        f'---\ntype: today\ndate: "{DAY}"\n---\n'
        "- 08:47 **deadline** QBR deck (#gstaff) → Now https://x.slack.com/archives/C1/p1\n"
        "- 08:47 **meeting** 1:1 Pat moved from 10:00-10:30 to 11:00-11:30\n"
        f"- 11:41 **session** Traced the 404s to the partner's QA endpoint. (raw/work/archive/{DAY}-1141-1a2b3c4d-traced.md)\n"
        "  - delivered: message — thread reply with traces — https://x\n"
        '- 14:40 **meeting** [[2026-10-19-1400-pilot-sync]]: 2 decisions; yours: "Send the doc"\n')
    before = today(vault)
    tl.write(vault, DAY, "15:10:00")
    assert today(vault) == before


def test_copied_text_cannot_become_a_link_a_checkbox_or_a_second_line_and_credentials_are_masked(vault):
    item(vault, "watch:b", text="[[Evil]] line one\nline two password=hunter2hunter2 " + "x" * 300)
    tl.write(vault, DAY, "09:00:00")
    line = today(vault).splitlines()[-1]
    assert "[[" not in line and "hunter2hunter2" not in line and len(line) < 300
    assert tl.clean("- [ ] fake box") == "fake box"


def test_only_work_items_reach_the_today_file(vault):
    item(vault, "watch:w", text="work item")
    item(vault, "watch:p", text="personal item", partition="personal")
    tl.write(vault, DAY, "09:00:00")
    assert "work item" in today(vault) and "personal item" not in today(vault)


def test_only_digests_named_for_the_day_are_read(vault, monkeypatch):
    digest(vault)
    digest(vault, "2026-10-18-0900-1a2b3c4d-old.md", created="2026-10-18T09:00:00-06:00")
    read = []
    monkeypatch.setattr(tl.Path, "read_text", lambda p, **kw: read.append(p.name) or "")
    tl.digests(vault, DAY)
    assert read == [f"{DAY}-1141-1a2b3c4d-traced.md"]


def test_nothing_new_writes_no_file(vault):
    tl.write(vault, DAY, "09:00:00")
    assert not (vault / "briefings" / f"{DAY}.today.md").exists()
