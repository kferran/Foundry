"""vaultlib/meeting_prep.py: Before today's meetings (one-screen brief spec §3.6)."""
import shutil
import subprocess
import sys

from helpers import REPO, concept, meeting, write
from vaultlib import meeting_prep

NOW = ("---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n---\n# Now\n\n## Needs you\n"
       "- [ ] owed: Send the capability doc (Avery Sample, since 2026-10-03)\n"
       "- [ ] draft: Reply to [[Avery Sample]] on the pilot (since 2026-10-04)\n"
       "- [ ] owed: Unrelated line (since 2026-10-04)\n\n## Waiting\n"
       "- [ ] waiting: Lincoln contact name (Avery Sample, since 2026-10-05)\n")
ACTIONS = "## Action items\n- [ ] [Avery Sample] Draft plan: Send the draft.\n- [ ] [Blake Sample] Deck: Make it.\n"


def calendar(vault, *rows):
    text = "".join("\t".join(r) + "\n" for r in rows)
    return write(vault, "system/logs/inputs/2026-10-06/calendar.tsv", text)


def setup(vault):
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\ndefault_partition: "work"\n'
          'owner_names: ["Casey Owner"]\n---\n')
    write(vault, "wiki/work/entities/AverySample.md", concept("work", "Avery Sample", aliases='["Avery", "A. Sample"]'))
    write(vault, "wiki/work/entities/Acme.md", concept("work", "Acme"))
    write(vault, "wiki/personal/entities/BlakeSample.md", concept("personal", "Blake Sample"))
    write(vault, "wiki/work/Now.md", NOW)
    name = "2026-10-05-1500-weekly-sync"
    write(vault, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))


def test_an_event_naming_an_entity_prints_its_block_in_calendar_order(vault):
    setup(vault)
    cal = calendar(vault, ("2026-10-06", "10:00", "2026-10-06", "10:30", "Acme / Porch sync"),
                   ("2026-10-06", "09:00", "2026-10-06", "09:30", "Avery Sync"))
    assert meeting_prep.render(vault, "2026-10-06", cal) == (
        "### [[AverySample|Avery Sample]] (09:00 Avery Sync)\n"
        "- owed: Send the capability doc (Avery Sample, since 2026-10-03)\n"
        "- waiting: Lincoln contact name (Avery Sample, since 2026-10-05)\n"
        "- draft: Reply to [[Avery Sample]] on the pilot (since 2026-10-04)\n"
        "- action: Draft plan: Send the draft. ([[2026-10-05-1500-weekly-sync]])\n\n"
        "### [[Acme]] (10:00 Acme / Porch sync)\n")


def test_whole_word_match_only():
    assert meeting_prep.matches("Alexandria sync", "Alex") is False
    assert meeting_prep.matches("acme / porch SYNC", "Acme") is True
    assert meeting_prep.matches("1:1 with A. Sample", "A. Sample") is True
    assert meeting_prep.matches("Sample review", "Avery Sample") is False


def test_now_lines_match_by_who_or_by_name_in_the_statement(vault):
    setup(vault)
    cal = calendar(vault, ("2026-10-06", "09:00", "2026-10-06", "09:30", "Avery Sync"))
    out = meeting_prep.render(vault, "2026-10-06", cal)
    assert "Reply to [[Avery Sample]]" in out and "Unrelated line" not in out


def test_five_entities_and_five_lines_at_most_and_each_entity_once(vault):
    setup(vault)
    for i in range(7):
        write(vault, f"wiki/work/entities/Person{i}.md", concept("work", f"Person{i}"))
    rows = [("2026-10-06", f"{9 + i:02d}:00", "2026-10-06", f"{9 + i:02d}:30", f"Person{i} sync") for i in range(7)]
    rows.append(("2026-10-06", "17:00", "2026-10-06", "17:30", "Person0 again"))
    out = meeting_prep.render(vault, "2026-10-06", calendar(vault, *rows))
    assert out.count("### ") == 5 and out.count("[[Person0]]") == 1
    lines = ["- [ ] owed: Item %d (Person1, since 2026-10-01)" % i for i in range(8)]
    write(vault, "wiki/work/Now.md", NOW + "\n".join(lines) + "\n")
    block = meeting_prep.render(vault, "2026-10-06", calendar(vault, *rows[:2])).split("\n\n")[1]
    assert block.count("\n- ") == 5


def test_a_personal_entity_never_appears_in_a_work_brief_and_no_match_is_empty(vault):
    setup(vault)
    cal = calendar(vault, ("2026-10-06", "09:00", "2026-10-06", "09:30", "Blake Sample 1:1"))
    assert meeting_prep.render(vault, "2026-10-06", cal) == ""


def test_the_script_reads_the_days_calendar_and_is_empty_without_one(vault):
    setup(vault)
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    p = subprocess.run([sys.executable, str(vault / "system/scripts/meeting_prep.py"), "2026-10-06"],
                       capture_output=True, text=True)
    assert (p.returncode, p.stdout) == (0, "")
    calendar(vault, ("2026-10-06", "09:00", "2026-10-06", "09:30", "Avery Sync"))
    p = subprocess.run([sys.executable, str(vault / "system/scripts/meeting_prep.py"), "2026-10-06"],
                       capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout.startswith("### [[AverySample|Avery Sample]] (09:00 Avery Sync)\n")
    assert subprocess.run([sys.executable, str(vault / "system/scripts/meeting_prep.py"), "bad"],
                          capture_output=True).returncode == 2
