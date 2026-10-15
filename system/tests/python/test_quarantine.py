"""One reader for quarantine (quarantine-in-brief spec §2): one row per held thing, never a sidecar."""
import json
import os
from datetime import date

from helpers import write
from vaultlib import quarantine

TODAY = date(2026, 10, 15)


def stamp(path, day):
    t = int(__import__("datetime").datetime(2026, 10, day, 12).timestamp())
    os.utime(path, (t, t))


def held(vault):
    q = vault / "system/quarantine"
    write(vault, "system/quarantine/poisoned/digest-1.md", "x")
    (q / "poisoned/digest-1.md.origin.json").write_text(json.dumps(
        {"origin": "raw/work/notes/digest-1.md", "sha256": "ab", "poisoned_at": "2026-10-08T05:00:00-06:00"}))
    write(vault, "system/quarantine/meetings/standup.vtt", "x")
    (q / "meetings/standup.vtt.reason.txt").write_text("no transcript text\n")
    stamp(q / "meetings/standup.vtt", 14)
    write(vault, "system/quarantine/20261012T050000-ingest/staged/wiki/work/concepts/X.md", "x")
    write(vault, "system/quarantine/telemetry_state-20261013T010000.json", "{")
    stamp(q / "telemetry_state-20261013T010000.json", 13)


def test_each_held_thing_is_one_row_oldest_first_and_sidecars_are_never_rows(vault):
    held(vault)
    rows = quarantine.items(vault, TODAY)
    assert [(r.kind, r.since.isoformat()) for r in rows] == [
        ("poisoned", "2026-10-08"), ("run", "2026-10-12"), ("telemetry_state", "2026-10-13"), ("meeting", "2026-10-14")]
    poisoned = rows[0]
    assert poisoned.origin == "raw/work/notes/digest-1.md" and poisoned.days == 7
    assert poisoned.way_out == "system/scripts/intake.py --retry-input digest-1.md"
    assert rows[3].reason == "no transcript text"
    assert not any(r.path.endswith((".origin.json", ".reason.txt")) for r in rows)


def test_render_gives_one_line_per_row_and_none_when_empty(vault):
    assert quarantine.render([]) == "none\n"
    held(vault)
    lines = quarantine.render(quarantine.items(vault, TODAY)).splitlines()
    assert len(lines) == 4
    assert lines[0] == ("- poisoned raw/work/notes/digest-1.md, since 2026-10-08 (7 days). "
                        "system/scripts/intake.py --retry-input digest-1.md")
    assert lines[1].startswith("- run system/quarantine/20261012T050000-ingest, since 2026-10-12 (3 days)")
