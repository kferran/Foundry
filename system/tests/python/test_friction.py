"""vaultlib/friction.py: friction notes new since the last brief (one-screen brief spec §3.3)."""
import shutil
import subprocess
import sys

from helpers import REPO, concept, write
from vaultlib import friction

NEW_STYLE = "## 🛑 Blockers\n- **Telemetry**: none.\n- **Friction**:\n  - [[Alpha]]\n  3 open friction notes\n- **Pipeline**: none.\n"
OLD_STYLE = ("## 🛑 Real-Time Workflow Friction Matrix\n- **Systemic Blockers**:\n"
             "  - **Friction notes** (2). Act on today: [[Beta]], [[Gamma]].\n    - Also flagged: [[Delta]].\n"
             "  - **Nightshift health**: ok, see [[NotFriction]].\n")


def flagged(vault, name, compiled, active=True):
    extra = {"is_friction": '"true"', "compiled_at": f'"{compiled}"'}
    if not active:
        extra["status"] = "deprecated"
    write(vault, f"wiki/work/concepts/{name}.md", concept("work", name, **extra))


def brief(vault, day, body):
    write(vault, f"briefings/{day}.md", f'---\ntype: briefing\ndate: "{day}"\nstatus: active\n---\n{body}')


def test_a_flagged_note_prints_once_and_is_counted_after(vault):
    flagged(vault, "Alpha", "2026-10-09")
    flagged(vault, "Delta", "2026-10-10")
    brief(vault, "2026-10-10", NEW_STYLE)
    assert friction.render(vault, "2026-10-11") == "- [[Delta]]\n2 open friction notes\n"


def test_names_under_the_old_friction_notes_bullet_are_not_new(vault):
    for name in ("Beta", "Gamma", "Delta", "NotFriction"):
        flagged(vault, name, "2026-10-01")
    brief(vault, "2026-10-10", OLD_STYLE)
    assert friction.listed_before(vault, "2026-10-11") == {"Beta", "Gamma", "Delta"}
    assert friction.render(vault, "2026-10-11") == "- [[NotFriction]]\n4 open friction notes\n"


def test_with_no_earlier_briefing_every_flagged_note_is_new(vault):
    flagged(vault, "Alpha", "2026-10-09")
    flagged(vault, "Delta", "2026-10-10")
    assert friction.render(vault, "2026-10-11") == "- [[Delta]]\n- [[Alpha]]\n2 open friction notes\n"


def test_an_archived_briefing_counts_and_todays_does_not(vault):
    flagged(vault, "Alpha", "2026-10-09")
    flagged(vault, "Delta", "2026-10-10")
    write(vault, "briefings/archive/2026-10/2026-10-08.md", f'---\ntype: briefing\ndate: "2026-10-08"\nstatus: active\n---\n{NEW_STYLE}')
    brief(vault, "2026-10-11", NEW_STYLE.replace("Alpha", "Delta"))
    assert friction.render(vault, "2026-10-11") == "- [[Delta]]\n2 open friction notes\n"


def test_an_inactive_flagged_note_is_neither_printed_nor_counted(vault):
    flagged(vault, "Alpha", "2026-10-09")
    flagged(vault, "Old", "2026-10-09", active=False)
    assert friction.render(vault, "2026-10-11") == "- [[Alpha]]\n1 open friction note\n"


def test_the_script_prints_the_rendering(vault):
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    flagged(vault, "Alpha", "2026-10-09")
    p = subprocess.run([sys.executable, str(vault / "system/scripts/friction_notes.py"), "2026-10-11"],
                       capture_output=True, text=True)
    assert (p.returncode, p.stdout) == (0, "- [[Alpha]]\n1 open friction note\n")
    assert subprocess.run([sys.executable, str(vault / "system/scripts/friction_notes.py"), "bad"],
                          capture_output=True).returncode == 2
