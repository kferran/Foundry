# Active Projects in the Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every morning brief lists each active project with its next 3 open actions and the decisions waiting on the user, read from the project's own page.

**Architecture:**
- A new deterministic script, `system/scripts/active_projects.py`, reads `wiki/<partition>/ActiveProjects.md` for `work` and `personal`.
- It resolves each `## Active` link the way Obsidian does (`vaultlib.links.Resolver`) and pulls open checkboxes from each project page.
- It prints `projects.md`. `brief_prep.sh` writes it into the day's prep inputs.
- The briefing template gains a `## 🎯 Active Projects` section, and `.claude/commands/brief.md` tells the Foreman to copy the blocks as plain bullets.

**Tech Stack:** Python 3 stdlib plus the repository's `vaultlib`; bash; pytest; bats.

**Spec:** `docs/superpowers/specs/2026-10-07-active-projects-design.md` (issue #65)

## Global Constraints

- Partitions read: `work` and `personal` only. `wiki/shared/` has no list.
- List file: `wiki/<partition>/ActiveProjects.md`. Only `## Active` is read; its order is the priority order.
- Caps: 3 next actions per project (`MAX_NEXT = 3`); 10 active entries per partition (`MAX_ACTIVE = 10`).
- Open checkbox: a line matching `^\s*- \[ \] (.+)$`. `- [x]` and `- [-]` never count. Lines inside fenced code blocks never count. Item text is kept verbatim (inline code included).
- "Decisions" section: any heading whose text, after the `#` marks and one space, starts with "Decisions" (case-insensitive). It ends at the next heading of the same or a higher level.
- Exit codes: 0 on success (notices included), 2 on a bad date, 1 on any other failure.
- The brief copies project items as plain `- ` bullets, never `- [ ] `.
- The `### 1.` and `### 2. Unavailable Sources` headings of the briefing template stay unchanged.
- Run tests from the worktree root. Never read a test result through a pipe: run the command bare and read its own exit status.
- American English in code, comments and docs.

**One deviation from spec §3:** the spec names `vaultlib.links.code_free_lines` for skipping fenced code. That helper also strips inline code from every line, which would change item text the spec says is kept verbatim. The script skips fences with `vaultlib.links.FENCE` and keeps lines whole.

## Review Focus

Each of these failure modes is pinned by a test in the task named in brackets.

1. **CRLF line endings** in a list or page written on Windows or by a sync tool. Entries and checkboxes must still be found. (Task 1)
2. **An aliased entry** such as `- [[Page|Short name]]: focus`. It must resolve `Page`, and the heading keeps the link as written. (Task 2)
3. **A capital `[X]`** written by a mobile editor. It must not be read as open. (Task 1)
4. **Trailing spaces on the `## Active` heading.** The list must still be read. (Task 1)
5. **A project page with no frontmatter.** Its checkboxes must still be read. (Task 1)

---

### Task 1: Parse the list and the project page

**Files:**
- Create: `system/scripts/active_projects.py`
- Create: `system/tests/python/test_active_projects.py`

**Interfaces:**
- Produces:
  - `active_entries(text: str) -> list[tuple[str, str]]`: `(raw link text inside [[ ]], focus text or "")` for each entry under `## Active`, in order.
  - `page_items(text: str) -> tuple[list[str], list[str]]`: `(next_actions, decisions)`, each a list of item texts without the `- [ ] ` prefix.
  - Constants `MAX_NEXT = 3`, `MAX_ACTIVE = 10`, `PARTITIONS = ("work", "personal")`, `LIST_NAME = "ActiveProjects.md"`.

- [ ] **Step 1: Write the failing tests**

Create `system/tests/python/test_active_projects.py`:

```python
"""active_projects.py: active projects with their next actions and decisions for the brief (issue #65)."""
import importlib.util
import subprocess
import sys

from helpers import REPO, write

SCRIPT = REPO / "system" / "scripts" / "active_projects.py"
_spec = importlib.util.spec_from_file_location("active_projects", SCRIPT)
ap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ap)


def listing(active: str, paused: str = "", done: str = "", partition: str = "work") -> str:
    return (f"---\ntype: concept\ntags: [\"active-projects\"]\ncompiled_at: 2026-10-07\npartition: {partition}\n---\n\n"
            f"# Active Projects\n\n## Active\n{active}\n## Paused\n{paused}\n## Done\n{done}")


def page(body: str, partition: str = "work") -> str:
    return f"---\ntype: concept\ntags: []\ncompiled_at: 2026-10-07\npartition: {partition}\n---\n\n# Project\n\n{body}"


def run(vault, date="2026-10-07"):
    return subprocess.run([sys.executable, str(SCRIPT), date], cwd=vault, capture_output=True, text=True)


# --- the list ---

def test_active_entries_keep_order_and_focus_and_ignore_paused_and_done():
    text = listing("- [[Alpha]]: main focus\n- [[Beta]]\nSome prose.\n  - [[Nested]]\n",
                   paused="- [[Gamma]]\n", done="- [[Delta]]: closed\n")
    assert ap.active_entries(text) == [("Alpha", "main focus"), ("Beta", "")]


def test_active_entries_survive_crlf_and_trailing_spaces_on_the_heading():
    text = listing("- [[Alpha]]: focus\n").replace("## Active\n", "## Active   \n").replace("\n", "\r\n")
    assert ap.active_entries(text) == [("Alpha", "focus")]


def test_active_entries_keep_an_alias_as_written():
    assert ap.active_entries(listing("- [[Alpha|Short]]: f\n")) == [("Alpha|Short", "f")]


# --- the page ---

def test_page_items_take_the_first_three_open_checkboxes_in_order():
    body = ("## Work\n- [x] done\n- [ ] one\n- [-] dropped\n- [X] capital is not open\n"
            "- [ ] two\n  - [ ] nested three\n- [ ] four\n")
    assert ap.page_items(page(body)) == (["one", "two", "nested three"], [])


def test_page_items_split_out_decisions_until_the_next_same_or_higher_heading():
    body = ("### Decisions waiting on me\n- [ ] pick a vendor\n#### Detail\n- [ ] still a decision\n"
            "### Questions\n- [ ] back to next\n")
    assert ap.page_items(page(body)) == (["back to next"], ["pick a vendor", "still a decision"])


def test_page_items_decisions_heading_is_case_insensitive_and_uncapped():
    body = "## DECISIONS\n" + "".join(f"- [ ] d{i}\n" for i in range(5))
    assert ap.page_items(page(body)) == ([], [f"d{i}" for i in range(5)])


def test_page_items_skip_fenced_code_and_keep_inline_code_verbatim():
    body = "```\n- [ ] in a fence\n```\n- [ ] Send the `105` message with **bold** and [[Link]]\n"
    assert ap.page_items(page(body)) == (["Send the `105` message with **bold** and [[Link]]"], [])


def test_page_items_read_a_page_without_frontmatter_and_with_crlf():
    assert ap.page_items("# P\r\n- [ ] one\r\n") == (["one"], [])
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m pytest system/tests/python/test_active_projects.py -v`
Expected: collection ERROR, because `system/scripts/active_projects.py` does not exist (`FileNotFoundError` from `exec_module`).

- [ ] **Step 3: Write the parsing half of the script**

Create `system/scripts/active_projects.py` and make it executable (`chmod +x system/scripts/active_projects.py`):

```python
#!/usr/bin/env python3
"""Active projects for the brief (active projects spec, issue #65).

Usage: active_projects.py YYYY-MM-DD   prints projects.md: for wiki/<partition>/ActiveProjects.md in work and
personal, the "## Active" entries in order, each with its first 3 open checkboxes and the open checkboxes under
its "Decisions…" headings. Run from the vault root. Exit 0, 2 on a bad date, 1 on any other failure.
"""
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib import frontmatter  # noqa: E402
from vaultlib.links import FENCE, Resolver, wiki_target  # noqa: E402

PARTITIONS = ("work", "personal")
LIST_NAME = "ActiveProjects.md"
MAX_ACTIVE = 10
MAX_NEXT = 3
ENTRY = re.compile(r"^- \[\[([^\[\]\n]+?)\]\](?::\s*(.*\S))?\s*$")
OPEN = re.compile(r"^\s*- \[ \] (.+)$")
HEADING = re.compile(r"^(#{1,6}) (.*)$")


def active_entries(text: str) -> list[tuple[str, str]]:
    """(raw link text, focus) for each entry under "## Active", in order."""
    out, on = [], False
    for line in frontmatter.parse(text).body.split("\n"):
        if line.startswith("## "):
            on = line.strip() == "## Active"
            continue
        match = ENTRY.match(line) if on else None
        if match:
            out.append((match.group(1), match.group(2) or ""))
    return out


def page_items(text: str) -> tuple[list[str], list[str]]:
    """(first MAX_NEXT open checkboxes outside Decisions sections, every open checkbox inside them)."""
    nxt, decisions = [], []
    fence, decisions_level = None, None
    for line in frontmatter.parse(text).body.split("\n"):
        fenced = FENCE.match(line)
        if fenced:
            if fence is None:
                fence = fenced.group(1)
            elif fenced.group(1) == fence:
                fence = None
            continue
        if fence is not None:
            continue
        heading = HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            if decisions_level is not None and level <= decisions_level:
                decisions_level = None
            if decisions_level is None and heading.group(2).strip().lower().startswith("decisions"):
                decisions_level = level
            continue
        item = OPEN.match(line)
        if not item:
            continue
        if decisions_level is not None:
            decisions.append(item.group(1).strip())
        elif len(nxt) < MAX_NEXT:
            nxt.append(item.group(1).strip())
    return nxt, decisions


def main(argv) -> int:
    print("usage: active_projects.py YYYY-MM-DD", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m pytest system/tests/python/test_active_projects.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/active_projects.py system/tests/python/test_active_projects.py
git commit -m "feat(brief): parse ActiveProjects lists and project pages (#65)"
```

---

### Task 2: Resolve entries, add notices, print `projects.md`

**Files:**
- Modify: `system/scripts/active_projects.py` (replace the stub `main`)
- Modify: `system/tests/python/test_active_projects.py` (append tests)

**Interfaces:**
- Consumes: `active_entries`, `page_items`, `MAX_ACTIVE`, `PARTITIONS`, `LIST_NAME` from Task 1.
- Produces: the CLI `active_projects.py YYYY-MM-DD`, run from the vault root, printing the `projects.md` format of spec §4.2 to stdout.

- [ ] **Step 1: Append the failing CLI tests**

Append to `system/tests/python/test_active_projects.py`:

```python
# --- the CLI ---

def test_cli_prints_blocks_per_partition_in_order(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Alpha]]: main focus\n- [[Beta]]\n"))
    write(vault, "wiki/work/concepts/Alpha.md", page("## Next\n- [ ] a1\n## Decisions\n- [ ] d1\n"))
    write(vault, "wiki/work/concepts/Beta.md", page("- [x] all done\n"))
    write(vault, "wiki/personal/ActiveProjects.md", listing("- [[Garden]]\n", partition="personal"))
    write(vault, "wiki/personal/concepts/Garden.md", page("- [ ] plant\n", partition="personal"))
    out = run(vault)
    assert out.returncode == 0, out.stderr
    assert out.stdout == (
        "# Active projects for 2026-10-07\n\n"
        "## work\n\n"
        "### [[Alpha]]: main focus\nNext:\n- a1\nDecisions waiting:\n- d1\n\n"
        "### [[Beta]]\nNext:\n- None open.\n\n"
        "## personal\n\n"
        "### [[Garden]]\nNext:\n- plant\n")


def test_cli_resolves_an_alias_and_keeps_the_link_as_written(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Alpha|Short]]: f\n"))
    write(vault, "wiki/work/concepts/Alpha.md", page("- [ ] a1\n"))
    assert "### [[Alpha|Short]]: f\nNext:\n- a1\n" in run(vault).stdout


def test_cli_with_no_lists_prints_none(vault):
    out = run(vault)
    assert out.returncode == 0
    assert out.stdout == "# Active projects for 2026-10-07\n\nNone.\n"


def test_cli_notices_for_missing_ambiguous_and_cross_partition_targets(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Missing]]\n- [[Twin]]\n- [[Garden]]\n- [[Alpha]]\n"))
    write(vault, "wiki/work/concepts/Twin.md", page("- [ ] x\n"))
    write(vault, "wiki/work/entities/Twin.md", page("- [ ] y\n"))
    write(vault, "wiki/personal/concepts/Garden.md", page("- [ ] plant\n", partition="personal"))
    write(vault, "wiki/work/concepts/Alpha.md", page("- [ ] a1\n"))
    out = run(vault)
    assert out.returncode == 0, out.stderr
    assert "### [[Alpha]]\nNext:\n- a1\n" in out.stdout
    assert "Twin]]\nNext" not in out.stdout and "Garden]]\nNext" not in out.stdout
    assert out.stdout.endswith(
        "## Notices\n"
        "- work: [[Missing]] in ActiveProjects does not resolve to a note.\n"
        "- work: [[Twin]] in ActiveProjects matches more than one note; use a path link.\n"
        "- work: [[Garden]] is in personal; list it in that partition's ActiveProjects.\n")


def test_cli_notice_for_an_unreadable_page(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Broken]]\n"))
    (vault / "wiki/work/concepts").mkdir(parents=True, exist_ok=True)
    (vault / "wiki/work/concepts/Broken.md").write_bytes(b"\xff\xfe\x00bad")
    out = run(vault)
    assert out.returncode == 0
    assert "- work: [[Broken]] could not be read.\n" in out.stdout


def test_cli_caps_active_projects_at_ten(vault):
    names = [f"P{i:02d}" for i in range(12)]
    write(vault, "wiki/work/ActiveProjects.md", listing("".join(f"- [[{n}]]\n" for n in names)))
    for n in names:
        write(vault, f"wiki/work/concepts/{n}.md", page("- [ ] go\n"))
    out = run(vault).stdout
    assert out.count("### [[P") == 10 and "[[P10]]" not in out
    assert "- work: only the first 10 active projects are shown.\n" in out


def test_cli_only_notices_still_prints_none_first(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Missing]]\n"))
    assert run(vault).stdout == ("# Active projects for 2026-10-07\n\nNone.\n\n## Notices\n"
                                 "- work: [[Missing]] in ActiveProjects does not resolve to a note.\n")


def test_cli_bad_date_exits_2(vault):
    assert run(vault, "yesterday").returncode == 2
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run: `python3 -m pytest system/tests/python/test_active_projects.py -v -k cli`
Expected: `test_cli_bad_date_exits_2` passes (the stub already exits 2). Every other `test_cli_*` fails, because the stub prints only usage.

- [ ] **Step 3: Replace the stub `main`**

In `system/scripts/active_projects.py`, replace the whole `def main(argv) -> int:` function with:

```python
def project_block(raw: str, focus: str, text: str) -> list[str]:
    nxt, decisions = page_items(text)
    lines = ["", f"### [[{raw}]]" + (f": {focus}" if focus else ""), "Next:"]
    lines += [f"- {t}" for t in nxt] or ["- None open."]
    if decisions:
        lines += ["Decisions waiting:", *[f"- {t}" for t in decisions]]
    return lines


def partition_blocks(part: str, resolver: Resolver, notices: list[str]) -> list[str]:
    listing = Path("wiki") / part / LIST_NAME
    if not listing.is_file():
        return []
    entries = active_entries(listing.read_text(encoding="utf-8"))
    if len(entries) > MAX_ACTIVE:
        notices.append(f"- {part}: only the first {MAX_ACTIVE} active projects are shown.")
        entries = entries[:MAX_ACTIVE]
    lines = []
    for raw, focus in entries:
        link = f"[[{raw}]]"
        path, ambiguous = resolver.resolve(wiki_target(raw), listing.as_posix(), "link", len)
        if path is None:
            notices.append(f"- {part}: {link} in ActiveProjects does not resolve to a note.")
            continue
        if ambiguous:
            notices.append(f"- {part}: {link} in ActiveProjects matches more than one note; use a path link.")
            continue
        other = path.split("/")[1]
        if other != part:
            notices.append(f"- {part}: {link} is in {other}; list it in that partition's ActiveProjects.")
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            notices.append(f"- {part}: {link} could not be read.")
            continue
        lines += project_block(raw, focus, text)
    return ["", f"## {part}", *lines] if lines else []


def main(argv) -> int:
    try:
        day = date.fromisoformat(argv[1]) if len(argv) == 2 else None
    except ValueError:
        day = None
    if day is None:
        print("usage: active_projects.py YYYY-MM-DD", file=sys.stderr)
        return 2
    files = [p.as_posix() for p in Path("wiki").rglob("*.md")] if Path("wiki").is_dir() else []
    resolver = Resolver(files, name_exclude=("wiki/.staging/",))
    notices, blocks = [], []
    for part in PARTITIONS:
        blocks += partition_blocks(part, resolver, notices)
    print(f"# Active projects for {day}")
    print("\n".join(blocks) if blocks else "\nNone.")
    if notices:
        print("\n## Notices\n" + "\n".join(notices))
    return 0
```

- [ ] **Step 4: Run the whole test file and confirm it passes**

Run: `python3 -m pytest system/tests/python/test_active_projects.py -v`
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/active_projects.py system/tests/python/test_active_projects.py
git commit -m "feat(brief): active_projects.py prints projects.md with notices (#65)"
```

---

### Task 3: Write `projects.md` during brief prep

**Files:**
- Modify: `system/scripts/brief_prep.sh:32-34` (after the `actions.md` step)
- Modify: `system/tests/prep.bats` (append two tests)

**Interfaces:**
- Consumes: the `active_projects.py YYYY-MM-DD` CLI from Task 2 (exit 0 or 1; output on stdout).
- Produces: `system/logs/inputs/<date>/projects.md`; on failure, the line `- brief_prep: projects: active_projects.py failed (see system/logs/inputs/<date>/prep_errors.log)` in `unavailable.md`.

- [ ] **Step 1: Append the failing bats tests**

Append to `system/tests/prep.bats`:

```bash
@test "brief_prep: projects.md lists active projects with their next actions" {
  mkdir -p wiki/work/concepts
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: 2026-10-01\npartition: work\n---\n# Active Projects\n## Active\n- [[Alpha]]: focus\n' > wiki/work/ActiveProjects.md
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: 2026-10-01\npartition: work\n---\n# Alpha\n- [ ] first step\n' > wiki/work/concepts/Alpha.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '### \[\[Alpha\]\]: focus' "$IN/projects.md"
  grep -qx -- '- first step' "$IN/projects.md"
  run grep -c 'projects' "$IN/unavailable.md"
  [ "$output" = "0" ]
}

@test "brief_prep: a failing active_projects.py is recorded and leaves no projects.md" {
  printf '#!/bin/bash\necho boom >&2\nexit 1\n' > "$V/system/scripts/active_projects.py"
  chmod +x "$V/system/scripts/active_projects.py"
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/projects.md" ]
  grep -qxF -- '- brief_prep: projects: active_projects.py failed (see system/logs/inputs/2026-10-01/prep_errors.log)' "$IN/unavailable.md"
}
```

`run grep -c` is used deliberately: `! grep -q` cannot fail a bats test.

- [ ] **Step 2: Run the bats file and confirm the two new tests fail**

Run: `bats system/tests/prep.bats`
Expected: the two new tests fail. The first fails because `projects.md` does not exist (grep: no such file). The second fails because the unavailable line is absent. All earlier tests still pass.

- [ ] **Step 3: Add the prep step**

In `system/scripts/brief_prep.sh`, directly after these lines:

```bash
prep_write actions.md system/scripts/meeting_actions.py "$PREP_DATE" \
  || prep_unavailable "actions: meeting_actions.py failed (see $PREP_DIR/prep_errors.log)"
```

insert:

```bash
# Active projects with their next actions and decisions waiting (active projects spec §4, issue #65).
prep_write projects.md system/scripts/active_projects.py "$PREP_DATE" \
  || prep_unavailable "projects: active_projects.py failed (see $PREP_DIR/prep_errors.log)"
```

Also extend the header comment on line 2 to read `# Calendar, meeting actions, active projects and yesterday's focus stats into system/logs/inputs/<date>/ (spec §6.5; calendar`.

- [ ] **Step 4: Run the bats file and confirm everything passes**

Run: `bats system/tests/prep.bats`
Expected: all tests pass. That includes `brief_prep: calendar and yesterday's focus are written`, which asserts that `unavailable.md` does not exist, so a vault with no lists must add no line.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/brief_prep.sh system/tests/prep.bats
git commit -m "feat(brief): brief_prep writes projects.md (#65)"
```

---

### Task 4: Briefing template and `/brief` command

**Files:**
- Modify: `system/templates/daily-briefing.md` (between `### 2. Unavailable Sources` and `## 🛑 Real-Time Workflow Friction Matrix`)
- Modify: `.claude/commands/brief.md` (Inputs list; Write the briefing list)
- Modify: `system/tests/commands.bats` (the `brief:` test)
- Modify: `system/tests/python/test_carry_forward.py` (one guard test)

**Interfaces:**
- Consumes: the `projects.md` format from Task 2 (spec §4.2).
- Produces: the `## 🎯 Active Projects` heading in new briefings.

- [ ] **Step 1: Write the failing assertions**

In `system/tests/commands.bats`, inside `@test "brief: headless contract, allowlisted index calls, template sections"`, after the line `grep -qx '### 2. Unavailable Sources' system/templates/daily-briefing.md`, add:

```bash
  t=system/templates/daily-briefing.md
  grep -qx '## 🎯 Active Projects' "$t"
  unavailable_line="$(grep -nx '### 2. Unavailable Sources' "$t" | cut -d: -f1)"
  projects_line="$(grep -nx '## 🎯 Active Projects' "$t" | cut -d: -f1)"
  friction_line="$(grep -n '^## 🛑 ' "$t" | cut -d: -f1)"
  [ "$unavailable_line" -lt "$projects_line" ]
  [ "$projects_line" -lt "$friction_line" ]
  grep -qF 'system/logs/inputs/<date>/projects.md' "$f"
  grep -qF 'plain `- ` bullets, never `- [ ] `' "$f"
```

Each `[ … ]` sits on its own line: in bats only the last command of an `&&` list can fail a test.

In `system/tests/python/test_carry_forward.py`, append:

```python
def test_active_projects_section_never_carries(vault):
    write(vault, "briefings/2026-10-06.md", briefing(
        "- [ ] **Real**\n", extra="\n## 🎯 Active Projects\n\n### [[Alpha]]\nNext:\n- [ ] a project checkbox\n"))
    assert run(vault, "2026-10-07").stdout.splitlines() == ["- [ ] **Real** _(open since 2026-10-06)_"]
```

- [ ] **Step 2: Run them and confirm the bats test fails and the guard can fail**

Run: `bats system/tests/commands.bats`
Expected: `brief: headless contract, allowlisted index calls, template sections` fails on `grep -qx '## 🎯 Active Projects'`.

Run: `python3 -m pytest system/tests/python/test_carry_forward.py -v`
Expected: the new test **passes already**. It is a guard on today's behavior, not new code. Prove it can fail: temporarily change its `extra=` so the section comes before `### 2.`, by passing the objectives argument `"- [ ] **Real**\n## 🎯 Active Projects\n- [ ] a project checkbox\n"` and `extra=""`. Re-run and confirm it fails with two carried lines. Then restore the code above and confirm it passes again.

- [ ] **Step 3: Add the template section**

In `system/templates/daily-briefing.md`, replace:

```markdown
### 2. Unavailable Sources

## 🛑 Real-Time Workflow Friction Matrix
```

with:

```markdown
### 2. Unavailable Sources

## 🎯 Active Projects

<!-- From projects.md. Tick items on each project's own page; this section is rewritten every brief. -->

## 🛑 Real-Time Workflow Friction Matrix
```

- [ ] **Step 4: Update `.claude/commands/brief.md`**

In the `## Inputs` list, after the `actions.md` bullet, add:

```markdown
- `system/logs/inputs/<date>/projects.md`: active projects from `wiki/<partition>/ActiveProjects.md`, in priority order, each with its next open actions (**Next:**) and the open decisions waiting on the user (**Decisions waiting:**), plus **Notices** for list entries that could not be read. Headless runs read this file and never open project pages.
```

In `## Write the briefing`, after the `**🌅 Morning Alignment → Unavailable Sources:**` bullet, add:

```markdown
- **🎯 Active Projects:** copy each project block from `projects.md` in its order: the project heading with its link and focus, then its `Next:` and `Decisions waiting:` items as plain `- ` bullets, never `- [ ] ` (the user ticks them on the project page). Write "None." when `projects.md` says None. When an existing briefing has no 🎯 Active Projects section, add it before the Friction Matrix. A new objective may name a project action and link the project page, but never repeats the action's text as its own checkbox.
```

In the `**🛑 Real-Time Workflow Friction Matrix:**` bullet, after `its Notices go under Systemic Blockers too)`, add the sentence: ` The lines under "## Notices" in `projects.md` go under Systemic Blockers too.`

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `bats system/tests/commands.bats`
Expected: all tests pass.

Run: `python3 -m pytest system/tests/python/test_carry_forward.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add system/templates/daily-briefing.md .claude/commands/brief.md system/tests/commands.bats system/tests/python/test_carry_forward.py
git commit -m "feat(brief): 🎯 Active Projects section in the briefing (#65)"
```

---

### Task 5: Full suite, push, pull request

**Files:** none changed.

- [ ] **Step 1: Run the full suites**

Run: `python3 -m pytest system/tests/python`
Expected: all pass. Record the pass count.

Run: `bats system/tests/prep.bats system/tests/commands.bats system/tests/scripts.bats system/tests/vault_integrity.bats`
Expected: all pass.

Run: `shellcheck system/scripts/brief_prep.sh`
Expected: no output, exit 0.

- [ ] **Step 2: Lint check of a sample list note**

In a throwaway copy of the repository, create `wiki/work/ActiveProjects.md` with the frontmatter from spec §2. Run `system/scripts/vault_index.py validate wiki/work/ActiveProjects.md`.
Expected: `0 errors`. The concept schema's `folders` admits the partition root; this confirms it. Delete the throwaway copy afterwards.

- [ ] **Step 3: Push and open the pull request**

```bash
git push -u template feat/active-projects
gh pr create --repo kferran/Foundry --base master --head feat/active-projects \
  --title "Brief: Active Projects section (#65)" \
  --body "Closes #65. Spec: docs/superpowers/specs/2026-10-07-active-projects-design.md. Plan: docs/superpowers/plans/2026-10-07-active-projects.md. Tests: pytest test_active_projects.py (16), prep.bats (+2), commands.bats (brief), test_carry_forward.py (+1 guard)."
```

Do not merge. The owner reviews and merges.
