#!/usr/bin/env python3
"""Fill a test vault to the live vault's size on 2026-10-17 (phase A spec §3.7), for a brief dated 2026-10-01.

Usage: brief_size.py <vault>
8 active work projects with 5 next actions and 6 decisions each, one meeting with 12 other owners, a work Now page
with 95 open lines (10 overdue) and 200 closed lines with a note each. Every third item runs past the 160-character cut.
"""
import sys
from pathlib import Path

V = Path(sys.argv[1])
LONG = "and the follow-up the team asked for in the review, with the numbers from last week attached to it " * 2
SHORT = "for the export"


def item(i):
    """Every third item long (over the 160-character cut), the rest short."""
    return LONG if i % 3 == 0 else SHORT


def write(rel, text):
    path = V / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def head(tags):
    return f'---\ntype: concept\ntags: [{tags}]\ncompiled_at: "2026-09-01"\npartition: work\n---\n'


projects = [f"Project {n}" for n in range(1, 9)]
write("wiki/work/ActiveProjects.md", head("active-projects") + "# Active Projects\n\n## Active\n"
      + "".join(f"- [[{p}]]: focus on the {p.lower()} launch\n" for p in projects) + "\n## Paused\n\n## Done\n")
for p in projects:
    write(f"wiki/work/concepts/{p}.md", head("") + f"# {p}\n\n## Next\n"
          + "".join(f"- [ ] Next {i} {item(i)}\n" for i in range(5)) + "\n## Decisions waiting\n"
          + "".join(f"- [ ] Decide {i} {item(i)}\n" for i in range(6)))

name = "2026-09-30-1500-planning"
actions = "".join(f"- [ ] [Owner {o}] Item {o}-{i}: {item(i)}\n" for o in range(1, 13) for i in range(1 + o % 3))
write(f"wiki/work/meetings/{name}.md",
      f'---\ntype: meeting\ntitle: "Planning"\ndate: "2026-09-30"\nstart: "2026-09-30T15:00:00-06:00"\n'
      f'partition: work\nsource: "gdoc:FAKE-{name}"\ntranscript: "[[{name}.transcript]]"\n---\n# Planning\n'
      f"## Summary\nNone.\n\n## Action items\n{actions}")
write(f"wiki/work/meetings/{name}.transcript.md",
      f'---\ntype: meeting_transcript\nmeeting: "[[{name}]]"\npartition: work\nsource: "gdoc:FAKE-{name}"\n'
      "complete: true\n---\n# Transcript\n")

open_lines = [f"- [ ] owed: Open {i} send the summary to the vendor about the export [due:: "
              f"{'2026-09-25' if i < 10 else '2026-10-20'}] (Blake Sample, since 2026-09-20, EX-{i})" for i in range(95)]
closed = [f"- [x] owed: Closed {i} {LONG[:150]} (since 2026-09-01, EX-{i}) _(closed: ticked 2026-09-{1 + i % 28:02d})_\n"
          f"  - 2026-09-02: {LONG[:120]}" for i in range(200)]
write("wiki/work/Now.md", head("now") + "# Now\n\n## Needs you\n" + "\n".join(open_lines + closed) + "\n\n## Waiting\n")
