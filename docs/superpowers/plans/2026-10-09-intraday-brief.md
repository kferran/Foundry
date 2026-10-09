# Intraday Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Through the day, intake appends the owner's work sessions, the meetings imported that day and (once plan 2 writes `chat.jsonl`) the chat threads the owner is in to `briefings/<date>.today.md`, which the briefing embeds under 🕑 Today so far; open lines carry into the next brief and the debrief lists them (issue #94, part B, plan 1).

**Architecture:** `vaultlib/today_log.py` is a deterministic writer with no model call. `Intake.write_today()` runs it after `process_digests()` on every tick of a server or standalone vault, under `run.lock` with timeout 0, and returns at once on a client; `system/scripts/today_log.py` runs the same step by hand. It reads today's `work` digests from the index (`v_session_digest`), today's `kind: imported` meeting records and `system/logs/inputs/<date>/chat.jsonl`, keeps a ledger in `system/logs/today_log.jsonl`, and appends entries that each end with a blank line. The file gets a schema note of its own (`type: today`), as the debrief has. `carry_forward.py` and `debrief_prep.sh` read its open `- [ ] ` lines. Chat entries are rendered now from a fixture `chat.jsonl`, so plan 2 only has to fetch and write that file.

**`chat.jsonl` contract (plan 2, `2026-10-09-chat-threads.md`, writes it):** one JSON object per line, one per thread, with the keys `link` (an `https://` permalink, no spaces or brackets), `channel` (for example `#team-x`, `DM` or `group DM`), `first_line` (the thread's first message, already masked and cut by plan 2), `last_author` (the display name of the last message's author), `last_time` (`HH:MM`, local time) and `needs_reply` (boolean). The record has no time for the first message, so an entry's time is `last_time`, and the owner is recognized by `last_author` matching `owner_names` (the spec's example `11:12 … (you replied 11:52)` needs a first-message time the contract lacks; the entry reads `11:52 … (you replied)`). A line with a missing or mistyped key is skipped with a `[today]` alert; extra keys are ignored.

**Decision D1 (needs the owner before Task 8 runs):** spec §3.4 says a client digest "syncs without a conflict", but `.gitignore` ignores `raw/**` and re-includes only `raw/inbox/`, `raw/archive/`, `raw/telemetry/` and `raw/*/nightshift/*.md`, so `raw/<p>/notes/` never syncs (`git check-ignore -v raw/work/notes/x.md` prints `.gitignore:11:raw/**`). The template design (`2026-09-30-vault-template-design.md`, "Raw inputs in git") chose that on purpose. Task 8 tracks `raw/*/notes/*.md` so client digests reach the server; pending digests (redacted) then enter the private origin's history, and a server-side digest is committed and then deleted when intake archives it. Tasks 1 to 7 do not depend on D1. Without the owner's yes, stop after Task 7.

**Tech Stack:** Python 3 (stdlib and `vaultlib`), bash, git, bats 1.8.2, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-intraday-brief-design.md` (§3.1, §3.2 including chat entries, §3.3, §3.4, §3.6, §3.7)

## Global Constraints

- Work on branch `feat/intraday-brief-94`. Commit there; do not push or open a pull request.
- Template rule: no employer, client, codebase or people names. Examples use `example.com`, `example.slack.com`, "Blake Sample", "Avery Sample" and `acme/shop`.
- New prose follows the Writing rules in `CLAUDE.md`.
- Run every command from the repository root after `mkdir -p .scratch/tmp` and `export TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch`. Never read a test result through a pipe: redirect to a file, then run `echo $?` as the next command. The gate (`system/scripts/verify_setup.sh`) and the bats suites write under `/tmp`: run them outside a sandbox. Never run two gates at once.
- Bound tools: pytest (`system/tests/python/test_recall.py`, `test_meetings.py`, `test_meeting_actions.py`, `test_today_log.py`, `test_schema_notes.py`, `test_intake.py`, `test_carry_forward.py`), bats (`system/tests/vault_integrity.bats`, `commands.bats`, `prep.bats`, `sync.bats`) and the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains. Read verdicts from exit codes or from `run` and `$status`/`$output`.
- Commits use `git commit -q -F .scratch/<file>`. Every commit message ends with a blank line and then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The plan edits `.claude/commands/brief.md`, `debrief.md` and `setup.md`: a Work Order session writes each through `.nightshift/protected/claude/commands/<name>.md`.
- Every "Find" text below occurs exactly once in its file when its step runs. A "Create" step writes the whole file; only the files a `chmod +x` step names are executable.

## Review Focus

1. **A client tick and a server append conflict.** If an entry lost its trailing blank line, the owner's tick on line N and the writer's append on line N+1 would touch adjacent lines, the sync would block and intake, brief and debrief would stop until the owner resolved it. Covered in Task 7: the `sync.bats` test runs the real writer and `vault_sync.sh` with a client clone, and is shown to fail with `BLANK = ""`.
2. **A digest written twice.** Intake moves a digest from `raw/<p>/notes/` to `raw/<p>/archive/` in the same tick, and a digest can change after it was written; keying the ledger on the path alone would write it again. Covered in Task 2 by `test_the_ledger_writes_each_source_once_even_after_it_moves_or_changes`.
3. **Personal or shared content in the work briefing.** Covered in Task 2 by `test_personal_and_shared_sources_never_reach_the_log` (a personal and a shared digest, a personal meeting note).
4. **Copied text that leaks a credential or turns into a link or a checkbox.** Masking must come before the 200-character cut, and `[[`, `]]` and a leading `- [ ]` must go. Covered in Task 2 by `test_clean_folds_masks_strips_and_cuts_after_masking` (the length check fails if the cut comes first) and `test_copied_text_is_masked_cut_and_cannot_become_a_link_or_a_checkbox`.
5. **The writer breaks or skips the tick.** It must run after the digests, also when the inbox stopped early, and an exception must become an alert. Covered in Task 3 by `test_the_today_log_runs_after_digests_every_tick_and_its_failure_is_an_alert`.

## File Structure

| File | Change |
|---|---|
| `system/scripts/vaultlib/recall.py` | `PART` regex and `digest_part(body, name)`: the Outcome, Delivered or Follow-ups lines of a digest |
| `system/scripts/vaultlib/meetings.py` | `owner_names(vault)` and `open_actions(body)`, moved from `meeting_actions.py` |
| `system/scripts/meeting_actions.py` | uses the two shared functions; behavior unchanged |
| `system/schemas/today.md` | create: schema for `type: today` in `briefings/` |
| `system/scripts/vaultlib/today_log.py` | create: the writer |
| `system/scripts/today_log.py` | create, executable: CLI `today_log.py [--date YYYY-MM-DD]` |
| `system/scripts/vaultlib/intake.py` | `write_today(day=None)`; `run()` calls it after the digests |
| `system/templates/daily-briefing.md` | `## 🕑 Today so far` and `![[{{date}}.today]]` before `## 📝 Notes` |
| `.claude/commands/brief.md` | keep or add the section; `carried.md` includes intraday lines |
| `system/schemas/briefing.md` | body names the `<date>.today` embed |
| `system/scripts/brief_prep.sh` | archive regex `(\.debrief|\.today)?` |
| `system/scripts/carry_forward.py` | reads open lines of `<day>.today.md` files |
| `system/scripts/debrief_prep.sh` | writes `today_open.md` |
| `.claude/commands/debrief.md` | **Open from today** in section 1 |
| `CLAUDE.md`, `README.md` | the intraday log in the directory map, the command table and a **Today so far** paragraph |
| `.gitignore`, `.claude/commands/setup.md`, `README.md` | Task 8 only (D1): track `raw/*/notes/*.md`; phase 5a offers hooks on a client |
| `system/tests/python/test_recall.py`, `test_meetings.py`, `test_today_log.py` (create), `test_schema_notes.py`, `test_intake.py`, `test_carry_forward.py` | tests |
| `system/tests/vault_integrity.bats`, `commands.bats`, `prep.bats`, `sync.bats` | tests |

---

### Task 1: Shared digest and meeting parsers

**Files:**
- Modify: `system/scripts/vaultlib/recall.py`, `system/scripts/vaultlib/meetings.py`, `system/scripts/meeting_actions.py`
- Test: `system/tests/python/test_recall.py`, `system/tests/python/test_meetings.py`; regression: `system/tests/python/test_meeting_actions.py`

**Interfaces:**
- Consumes: `recall.HEADING`, `recall.digest_sections(body) -> str` (unchanged); `frontmatter.parse(text).data`.
- Produces: `recall.PART` (compiled regex); `recall.digest_part(body: str, name: str) -> list[str]` with `name` in `"outcome"`, `"delivered"`, `"follow-ups"` (other names return `[]`); `meetings.OPEN_ACTION`; `meetings.owner_names(vault) -> set[str]` (stripped, case-folded); `meetings.open_actions(body: str) -> list[tuple[list[str], str | None, str]]` as `(owners, bracket text, action text)`.

- [ ] **Step 1: Write the failing tests**

Append to `system/tests/python/test_recall.py`:

````text


def test_digest_part_reads_one_section_and_text_after_a_bold_label():
    body = ("## Outcome\nTraced the 404s. Posted evidence.\n## Decisions\n- Keep it.\n"
            "## Delivered\n- message — thread reply with traces — https://example.com/t/1\n- doc — runbook\n\n"
            "## Follow-ups\n- Confirm the fix.\n")
    assert recall.digest_part(body, "outcome") == ["Traced the 404s. Posted evidence."]
    assert recall.digest_part(body, "delivered") == ["- message — thread reply with traces — https://example.com/t/1",
                                                    "- doc — runbook"]
    assert recall.digest_part(body, "follow-ups") == ["- Confirm the fix."]
    assert recall.digest_part(body, "facts") == []
    bold = "**Outcome:** Shipped it.\n**Delivered**\n- code — the fix\n"
    assert recall.digest_part(bold, "outcome") == ["Shipped it."]
    assert recall.digest_part(bold, "delivered") == ["- code — the fix"]
    assert recall.digest_part("## Outcome\nOutcome of a run.\n### Follow ups\n- Next.\n", "follow-ups") == ["- Next."]
    assert recall.digest_part("## Outcome\nOutcome of a run.\n", "outcome") == ["Outcome of a run."]
    assert "thread reply" not in recall.digest_sections(body)  # recall never shows Delivered
````

Append to `system/tests/python/test_meetings.py`:

````text


def test_owner_names_and_open_actions_are_the_shared_ownership_rule(tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system/config.md").write_text('---\ntype: config\nowner_names: ["BLAKE SAMPLE", " Blake S. "]\n---\n',
                                               encoding="utf-8")
    assert meetings.owner_names(tmp_path) == {"blake sample", "blake s."}
    assert meetings.owner_names(tmp_path / "missing") == set()
    body = ("## Decisions\n- [ ] [Blake Sample] Not an action.\n## Action items\n"
            "- [ ] [Blake Sample, Avery Sample] Send the doc\n- [x] [Blake Sample] Done already\n- [ ] Unowned item\n"
            "## Details\n- [ ] [Blake Sample] Not an action either.\n")
    assert meetings.open_actions(body) == [(["Blake Sample", "Avery Sample"], "Blake Sample, Avery Sample", "Send the doc"),
                                           ([], None, "Unowned item")]
````

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_recall.py system/tests/python/test_meetings.py system/tests/python/test_meeting_actions.py > .scratch/t1-red.out 2>&1`
Then: `echo $?`
Expected: `1`; `.scratch/t1-red.out` ends with `2 failed` (both new tests, `AttributeError`), every other test passes.

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/vaultlib/recall.py`. Find:

````text
HEADING = re.compile(r"^\s*(?:#{1,6}\s+\S|\*\*[^*]+\*\*\s*:?\s*$)")
````

Replace with:

````text
HEADING = re.compile(r"^\s*(?:#{1,6}\s+\S|\*\*[^*]+\*\*\s*:?\s*$)")
# A digest section the intraday log reads (intraday brief spec §3.3): a `#` heading or a bold label, never plain text.
PART = re.compile(r"^\s*(?:#{1,6}\s+|\*\*)\s*(outcome|delivered|follow[- ]?ups?)\b", re.I)
````

Edit 2 in `system/scripts/vaultlib/recall.py`. Find:

````text
    text = "\n".join(out).strip()
    return text if text else body.strip()[:400]
````

Replace with:

````text
    text = "\n".join(out).strip()
    return text if text else body.strip()[:400]


def digest_part(body: str, name: str) -> list:
    """The non-empty lines of one digest section, "outcome", "delivered" or "follow-ups", without its heading.
    Text after a bold label on the heading line ("**Outcome:** Shipped it.") belongs to the section."""
    out, on = [], False
    for line in body.splitlines():
        match = PART.match(line)
        if match:
            key = match.group(1).casefold()
            on = ("follow-ups" if key.startswith("follow") else key) == name
            rest = line[match.end():].lstrip("*: ").strip()
            if on and rest:
                out.append(rest)
            continue
        if HEADING.match(line):
            on = False
            continue
        if on and line.strip():
            out.append(line)
    return out
````

Edit 3 in `system/scripts/vaultlib/meetings.py`. Find:

````text
            f"## Decisions\n{m.decisions or 'None.'}\n\n## Details\n{m.details or 'None.'}\n")
````

Replace with:

````text
            f"## Decisions\n{m.decisions or 'None.'}\n\n## Details\n{m.details or 'None.'}\n")


# Ownership of a meeting's action items (meetings spec §2.5), shared by meeting_actions.py and the intraday log.
OPEN_ACTION = re.compile(r"^- \[ \] (?:\[([^\]]+)\] )?(.+)$")


def owner_names(vault) -> set:
    """The owner's names from config `owner_names`, stripped and case-folded; empty when unset or unreadable."""
    try:
        data = frontmatter.parse((Path(vault) / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return set()
    names = data.get("owner_names")
    return {n.strip().casefold() for n in names if isinstance(n, str)} if isinstance(names, list) else set()


def open_actions(body: str) -> list:
    """(owners, bracket text, action text) for each unticked line under `## Action items` of a meeting note body."""
    out, on = [], False
    for line in body.split("\n"):
        if line.startswith("## "):
            on = line.strip() == "## Action items"
            continue
        match = OPEN_ACTION.match(line.strip()) if on else None
        if match:
            owners = [o.strip() for o in (match.group(1) or "").split(",") if o.strip()]
            out.append((owners, match.group(1), match.group(2).strip()))
    return out
````

Edit 4 in `system/scripts/meeting_actions.py`. Find:

````text
import json
import re
import sqlite3
````

Replace with:

````text
import json
import sqlite3
````

Edit 5 in `system/scripts/meeting_actions.py`. Find:

````text
from vaultlib import frontmatter  # noqa: E402
````

Replace with:

````text
from vaultlib import frontmatter, meetings  # noqa: E402
````

Edit 6 in `system/scripts/meeting_actions.py`. Find:

````text
OPEN = re.compile(r"^- \[ \] (?:\[([^\]]+)\] )?(.+)$")
OTHERS_DAYS = 14
````

Replace with:

````text
OTHERS_DAYS = 14
````

Edit 7 in `system/scripts/meeting_actions.py`. Find:

````text
def owner_names():
    try:
        data = frontmatter.parse((VAULT / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return set()
    names = data.get("owner_names")
    return {n.strip().casefold() for n in names if isinstance(n, str)} if isinstance(names, list) else set()


def open_actions(path):
    """(owners, text) for each unticked line under ## Action items."""
    try:
        body = frontmatter.parse((VAULT / path).read_text(encoding="utf-8")).body
    except (OSError, UnicodeDecodeError):
        return []
    out, on = [], False
    for line in body.split("\n"):
        if line.startswith("## "):
            on = line.strip() == "## Action items"
            continue
        match = OPEN.match(line.strip()) if on else None
        if match:
            owners = [o.strip() for o in (match.group(1) or "").split(",") if o.strip()]
            out.append((owners, match.group(1), match.group(2).strip()))
    return out
````

Replace with:

````text
def owner_names():
    return meetings.owner_names(VAULT)


def open_actions(path):
    """(owners, bracket text, text) for each unticked line under ## Action items."""
    try:
        body = frontmatter.parse((VAULT / path).read_text(encoding="utf-8")).body
    except (OSError, UnicodeDecodeError):
        return []
    return meetings.open_actions(body)
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2.
Then: `echo $?`
Expected: `0`; no `failed` in `.scratch/t1-red.out` (`test_meeting_actions.py` passes unchanged).

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
refactor(digests): shared section and meeting-ownership parsers (#94)

recall.digest_part reads one digest section (Outcome, Delivered or
Follow-ups) without its heading, including text after a bold label.
owner_names and open_actions move from meeting_actions.py to
vaultlib/meetings.py so the intraday log decides ownership with the
same rule; meeting_actions.py output is unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Run: `git add system/scripts/vaultlib/recall.py system/scripts/vaultlib/meetings.py system/scripts/meeting_actions.py system/tests/python/test_recall.py system/tests/python/test_meetings.py`
Run: `git commit -q -F .scratch/msg-1.txt`

### Task 2: The intraday log writer

**Files:**
- Create: `system/schemas/today.md`, `system/scripts/vaultlib/today_log.py`, `system/scripts/today_log.py`, `system/tests/python/test_today_log.py`
- Modify: `system/scripts/vaultlib/intake.py` (import and `write_today`), `system/tests/python/test_schema_notes.py` (`EXPECTED`), `system/tests/vault_integrity.bats` (executable list)

**Interfaces:**
- Consumes: `recall.digest_part`, `recall.HEADING`, `meetings.owner_names`, `meetings.open_actions` (Task 1); `redact.redact_credentials(text) -> str`; `Index(vault).refresh(timeout)`, view `v_session_digest(path, created_at, partition)`; `Intake.config`, `Intake.lock(name, timeout)`, `Intake.today()`, `Intake.tz`; `helpers.write`, `helpers.meeting`; the `iv` fixture from `test_intake.py`.
- Produces: `today_log.clean(text) -> str`, `today_log.norm(text) -> str`, `today_log.alert_once(vault, tz, message) -> None`, `today_log.write(vault, day: str, tz) -> int` (entries written), constants `BLANK` and `LEDGER`; `Intake.write_today(day=None) -> str`, one of `"client"`, `"busy"`, `"written"`; `system/scripts/today_log.py [--date YYYY-MM-DD]`, exit 0, 2 (bad date) or 4 (run.lock busy); ledger lines `{"kind": "session"|"meeting"|"chat"|"reply", "source", "sha256", "date", "written_at"}`; notes of `type: today` with a `date` field.

- [ ] **Step 1: Write the failing tests**

Create `system/tests/python/test_today_log.py`:

````text
"""today_log: the intraday log briefings/<date>.today.md (intraday brief spec §3.1-§3.3)."""
import fcntl
import json
import sqlite3
import subprocess
import sys
from zoneinfo import ZoneInfo

from helpers import meeting, write
from test_intake import iv  # noqa: F401  (iv is a fixture)
from vaultlib import today_log
from vaultlib.index import Index
from vaultlib.intake import Intake

TZ = ZoneInfo("America/Denver")
DAY = "2026-10-09"
LOG = f"briefings/{DAY}.today.md"
HEAD = f'---\ntype: today\ndate: "{DAY}"\n---\n'
CONFIG = ('---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
          'remote_mode: "none"\ndefault_partition: "work"\nowner_names: ["Blake Sample"]\n{extra}---\n')
BODY = ("## Outcome\nTraced the 404s to the partner's QA endpoint. Then posted evidence.\n## Decisions\n- Keep the retry.\n"
        "## Delivered\n- message — thread reply with traces and query\n"
        "## Follow-ups\n- Confirm the endpoint returns OK after the partner's fix\n- None\n")
PILOT = "2026-10-09-1009-pilot-sync"


def config(vault, extra=""):
    write(vault, "system/config.md", CONFIG.format(extra=extra))


def digest(vault, name, created, body=BODY, partition="work", folder="notes"):
    return write(vault, f"raw/{partition}/{folder}/{name}.md",
                 f'---\ntype: session_digest\npartition: "{partition}"\ncodebase: "vault"\nsession_id: "s-{name}"\n'
                 f'created_at: "{created}"\n---\n{body}')


def imported(vault, note, time=f"{DAY}T10:30:00-06:00"):
    path = vault / "system/logs" / f"meetings-{DAY[:7]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"time": time, "kind": "imported", "source": "raw/meetings/FAKE.gdoc.md",
                             "note": note, "complete": True}) + "\n")


def thread(n, needs_reply=False, last_author="Blake Sample", last_time="11:52", **kw):
    """One chat.jsonl record as plan 2 writes it; "Blake Sample" is the owner (config owner_names)."""
    t = {"link": f"https://example.slack.com/archives/C{n}/p{n}", "channel": f"#team-{n}",
         "first_line": "UAT is currently not working", "last_author": last_author, "last_time": last_time,
         "needs_reply": needs_reply}
    t.update(kw)
    return t


def chat(vault, *lines):
    path = vault / "system/logs/inputs" / DAY / "chat.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join((x if isinstance(x, str) else json.dumps(x)) + "\n" for x in lines), encoding="utf-8")


def run(vault):
    return today_log.write(vault, DAY, TZ)


def log(vault):
    return (vault / LOG).read_text(encoding="utf-8")


def alerts(vault):
    return "".join(p.read_text(encoding="utf-8") for p in (vault / "system/logs").glob("alerts_*.md"))


def test_clean_folds_masks_strips_and_cuts_after_masking():
    assert today_log.clean("- [x] Done\n  twice") == "Done twice"
    assert today_log.clean("* [ ] [[Note]] text]]") == "Note text"
    assert today_log.clean("a" * 250) == "a" * 200
    masked = today_log.clean("AKIA" + "B" * 16 + " " + "c" * 200)
    assert masked.startswith("[REDACTED:aws_key] c")
    assert len(masked) == 200  # 198 if the text were cut before masking


def test_a_session_becomes_one_entry_with_its_delivered_lines_and_one_entry_per_follow_up(vault):
    config(vault)
    digest(vault, "2026-10-09-1141-1a2b3c4d-traced-the-404s", f"{DAY}T11:41:07-06:00")
    digest(vault, "2026-10-08-1700-1a2b3c4d-yesterday", "2026-10-08T17:00:00-06:00")
    assert run(vault) == 2
    assert log(vault) == HEAD + (
        "- 11:41 **session** Traced the 404s to the partner's QA endpoint. "
        "([[2026-10-09-1141-1a2b3c4d-traced-the-404s]])\n"
        "  - delivered: message — thread reply with traces and query\n\n"
        "- [ ] Confirm the endpoint returns OK after the partner's fix _(follow-up, session 11:41)_\n\n")


def test_copied_text_is_masked_cut_and_cannot_become_a_link_or_a_checkbox(vault):
    config(vault)
    secret = "ghp_" + "A" * 36
    digest(vault, "2026-10-09-0900-aaaaaaaa-used", f"{DAY}T09:00:00-06:00",
           body=f"## Outcome\nUsed token {secret} and [[Secret Note]] then\nwrapped.\n"
                f"## Follow-ups\n- - [ ] [[Plan]] {'x' * 300}\n")
    run(vault)
    lines = log(vault).splitlines()
    assert secret not in log(vault)
    assert lines[4] == ("- 09:00 **session** Used token [REDACTED:github_token] and Secret Note then wrapped. "
                        "([[2026-10-09-0900-aaaaaaaa-used]])")
    assert lines[6] == "- [ ] Plan " + "x" * 195 + " _(follow-up, session 09:00)_"


def test_a_follow_up_already_in_the_file_is_not_written_again(vault):
    config(vault)
    digest(vault, "2026-10-09-0900-aaaaaaaa-one", f"{DAY}T09:00:00-06:00",
           body="## Outcome\nOne.\n## Follow-ups\n- Confirm the fix\n")
    run(vault)
    path = vault / LOG
    path.write_text(path.read_text(encoding="utf-8").replace("- [ ] Confirm", "- [x] Confirm"), encoding="utf-8")
    digest(vault, "2026-10-09-1000-bbbbbbbb-two", f"{DAY}T10:00:00-06:00",
           body="## Outcome\nTwo.\n## Follow-ups\n-   confirm THE   fix\n- Book the room\n")
    assert run(vault) == 2
    lines = log(vault).splitlines()
    assert [x for x in lines if "fix" in x.casefold()] == ["- [x] Confirm the fix _(follow-up, session 09:00)_"]
    assert "- [ ] Book the room _(follow-up, session 10:00)_" in lines


def test_the_ledger_writes_each_source_once_even_after_it_moves_or_changes(vault):
    config(vault)
    d = digest(vault, "2026-10-09-0900-aaaaaaaa-one", f"{DAY}T09:00:00-06:00", body="## Outcome\nOne.\n")
    assert run(vault) == 1
    assert run(vault) == 0
    (vault / "raw/work/archive").mkdir(parents=True)
    moved = d.rename(vault / "raw/work/archive" / d.name)  # intake compiled it
    assert run(vault) == 0
    moved.write_text(moved.read_text(encoding="utf-8") + "More.\n", encoding="utf-8")  # changed after it was written
    assert run(vault) == 0
    assert log(vault).count("**session**") == 1
    records = [json.loads(x) for x in (vault / "system/logs/today_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["kind"], r["source"], r["date"]) for r in records] == [
        ("session", "raw/work/notes/2026-10-09-0900-aaaaaaaa-one.md", DAY)]
    assert len(records[0]["sha256"]) == 64


def test_personal_and_shared_sources_never_reach_the_log(vault):
    config(vault)
    digest(vault, "2026-10-09-0900-aaaaaaaa-home", f"{DAY}T09:00:00-06:00", partition="personal")
    digest(vault, "2026-10-09-0901-aaaaaaaa-both", f"{DAY}T09:01:00-06:00", partition="shared")
    name = "2026-10-09-1009-family-call"
    write(vault, f"wiki/personal/meetings/{name}.md", meeting("personal", name, body="\n## Decisions\n- Go.\n"))
    imported(vault, f"wiki/personal/meetings/{name}.md")
    assert run(vault) == 0
    assert not (vault / LOG).exists()


def test_a_meeting_imported_today_counts_its_decisions_and_quotes_your_open_actions(vault):
    config(vault)
    write(vault, f"wiki/work/meetings/{PILOT}.md", meeting("work", PILOT, title="Pilot sync", body=(
        "\n## Summary\nTalked.\n\n## Decisions\n- Ship Friday.\n- Keep the flag.\n\n## Action items\n"
        "- [ ] [Blake Sample] Send the capability doc\n- [x] [Blake Sample] Done already\n"
        "- [ ] [Avery Sample] Book the room\n\n## Details\nNone.\n")))
    imported(vault, f"wiki/work/meetings/{PILOT}.md")
    imported(vault, f"wiki/work/meetings/{PILOT}.md", time="2026-10-08T16:00:00-06:00")
    assert run(vault) == 1
    assert log(vault) == HEAD + f'- 10:09 **meeting** [[{PILOT}]]: 2 decisions; yours: "Send the capability doc"\n\n'
    assert run(vault) == 0


def test_a_meeting_whose_note_is_not_there_yet_is_written_on_a_later_tick(vault):
    config(vault)
    note = f"wiki/work/meetings/{PILOT}.md"
    imported(vault, note)
    assert run(vault) == 0
    assert not (vault / LOG).exists()
    assert not (vault / "system/logs/today_log.jsonl").exists()
    write(vault, note, meeting("work", PILOT, body="\n## Decisions\nNone.\n\n## Action items\nNone.\n"))
    assert run(vault) == 1
    assert log(vault) == HEAD + f"- 10:09 **meeting** [[{PILOT}]]: 0 decisions\n\n"


def test_an_unreadable_source_is_skipped_with_one_alert_a_day(vault):
    config(vault)
    bad = digest(vault, "2026-10-09-0900-aaaaaaaa-bad", f"{DAY}T09:00:00-06:00")
    bad.write_bytes(bad.read_bytes() + b"\xff\xfe broken\n")
    digest(vault, "2026-10-09-1000-bbbbbbbb-good", f"{DAY}T10:00:00-06:00", body="## Outcome\nGood.\n")
    assert run(vault) == 1
    assert run(vault) == 0
    assert alerts(vault).count("[today]") == 1
    assert "raw/work/notes/2026-10-09-0900-aaaaaaaa-bad.md" in alerts(vault)
    assert "aaaaaaaa-bad" not in log(vault)


def test_chat_threads_are_listed_once_a_day_and_a_later_needs_reply_adds_only_the_checkbox(vault):
    config(vault)
    asked = dict(needs_reply=True, last_author="Avery Sample", first_line="Can you confirm pre-prod…")
    chat(vault, thread(1), thread(2, last_time="14:05", **asked), thread(5, last_author="Avery Sample", last_time="12:00"))
    assert run(vault) == 3
    assert log(vault) == HEAD + (
        '- 11:52 **chat** #team-1: "UAT is currently not working" (you replied) '
        'https://example.slack.com/archives/C1/p1\n\n'
        '- 12:00 **chat** #team-5: "UAT is currently not working" (last: Avery Sample) '
        'https://example.slack.com/archives/C5/p5\n\n'
        '- [ ] Reply in #team-2: "Can you confirm pre-prod…" (Avery Sample, 14:05) '
        'https://example.slack.com/archives/C2/p2 _(chat)_\n\n')
    assert run(vault) == 0
    chat(vault, thread(1, needs_reply=True, last_author="Avery Sample", last_time="15:30"),
         thread(2, last_time="16:00", **asked))
    assert run(vault) == 1
    assert log(vault).endswith('- [ ] Reply in #team-1: "UAT is currently not working" (Avery Sample, 15:30) '
                               'https://example.slack.com/archives/C1/p1 _(chat)_\n\n')


def test_a_chat_line_that_is_not_a_thread_record_is_skipped_with_one_alert(vault):
    config(vault)
    chat(vault, "not json", thread(1, link="javascript:alert(1)"), thread(3, needs_reply="yes"),
         thread(6, last_time="2026-10-09T11:52:00-06:00"), thread(4))
    assert run(vault) == 1
    assert alerts(vault).count("[today]") == 1
    assert "https://example.slack.com/archives/C4/p4" in log(vault)
    assert "javascript" not in log(vault)


def test_the_log_is_a_valid_today_note_in_place_and_archived_and_the_briefing_embed_resolves(vault):
    config(vault)
    digest(vault, "2026-10-09-0900-aaaaaaaa-one", f"{DAY}T09:00:00-06:00", body="## Outcome\nOne.\n")
    run(vault)
    archived = f"briefings/archive/2026-10/{DAY}.today.md"
    write(vault, archived, log(vault))
    write(vault, f"briefings/{DAY}.md", f'---\ntype: briefing\ndate: "{DAY}"\nstatus: active\n---\n# B\n\n'
                                       f"## 🕑 Today so far\n\n![[{DAY}.today]]\n")
    idx = Index(vault)
    idx.refresh()
    conn = sqlite3.connect(idx.db_path)
    try:
        for path in (LOG, archived):
            assert conn.execute("SELECT type, valid FROM notes WHERE path = ?", (path,)).fetchone() == ("today", 1)
            assert conn.execute("SELECT code FROM issues WHERE path = ? AND severity = 'error'", (path,)).fetchall() == []
        assert conn.execute("SELECT target_path FROM links WHERE src = ?", (f"briefings/{DAY}.md",)).fetchall() == [(LOG,)]
    finally:
        conn.close()


def test_a_client_writes_nothing_and_a_busy_run_lock_waits_for_the_next_tick(iv):
    config(iv, extra='machine_role: "client"\n')
    digest(iv, "2026-10-09-0900-aaaaaaaa-one", f"{DAY}T09:00:00-06:00")
    assert Intake(iv).write_today(DAY) == "client"
    assert not (iv / LOG).exists()
    config(iv)
    with open(iv / "system/run.lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        assert Intake(iv).write_today(DAY) == "busy"
    assert not (iv / LOG).exists()
    assert Intake(iv).write_today(DAY) == "written"
    assert "**session**" in log(iv)


def test_the_cli_writes_a_given_date_and_rejects_a_bad_one(iv):
    config(iv)
    digest(iv, "2026-10-09-0900-aaaaaaaa-one", f"{DAY}T09:00:00-06:00")
    script = str(iv / "system/scripts/today_log.py")
    p = subprocess.run([sys.executable, script, "--date", DAY], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "**session**" in log(iv)
    p = subprocess.run([sys.executable, script, "--date", "20261009"], capture_output=True, text=True)
    assert p.returncode == 2
    assert "today_log: invalid date: 20261009" in p.stderr
````

Edit 1 in `system/tests/python/test_schema_notes.py`. Find:

````text
            "meeting", "meeting_transcript", "meeting_input", "telemetry_source", "nightshift_item", "dtcc_change"}
````

Replace with:

````text
            "meeting", "meeting_transcript", "meeting_input", "telemetry_source", "nightshift_item", "dtcc_change",
            "today"}
````

Edit 2 in `system/tests/vault_integrity.bats`. Find:

````text
           discover_codebases.sh inspect_codebase.sh inspect_codebase.py; do
````

Replace with:

````text
           discover_codebases.sh inspect_codebase.sh inspect_codebase.py today_log.py; do
````

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_today_log.py > .scratch/t2-red-a.out 2>&1`
Then: `echo $?`
Expected: `2`; `.scratch/t2-red-a.out` shows `1 error` during collection (`cannot import name 'today_log' from 'vaultlib'`).

Run: `python3 -m pytest -q system/tests/python/test_schema_notes.py > .scratch/t2-red-b.out 2>&1`
Then: `echo $?`
Expected: `1`; `1 failed` (`test_all_schemas_load`).

Run: `bats system/tests/vault_integrity.bats > .scratch/t2-red-c.out 2>&1`
Then: `echo $?`
Expected: `1`; one `not ok` line, `vault scripts and hook are executable`.

- [ ] **Step 3: Implement**

Create `system/schemas/today.md`:

````text
---
type: schema
schema_for: today
folders: ["briefings/"]
fields:
  type: {kind: const, value: today, required: true}
  date: {kind: date, required: true}
---
# Intraday log
`briefings/<date>.today.md`: the day's work sessions, meetings and chat threads, appended by intake (`system/scripts/today_log.py`) and embedded in the day's briefing under 🕑 Today so far. It is append-only: tick `[x]` or drop `[-]` a line, never rewrite one.
````

Create `system/scripts/vaultlib/today_log.py`:

````text
"""The intraday log `briefings/<date>.today.md` (intraday brief spec §3.1-§3.3).

Intake appends the day's work sessions, meetings and chat threads to it on every tick, after the digests. The file
is append-only: a run adds entries at the end and never changes a line. Every entry ends with a blank line, so a
checkbox ticked on a client and an entry appended on the server merge without a conflict. No model call.
"""
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from . import frontmatter, meetings, recall
from .index import Index
from .redact import redact_credentials

PARTITION = "work"  # the brief's partition: personal and shared sources never reach the briefing
MAX_CHARS = 200
BLANK = "\n"  # the blank line that ends every entry (spec §3.1)
LEDGER = Path("system") / "logs" / "today_log.jsonl"
SPACE = re.compile(r"\s+")
SENTENCE = re.compile(r"(?<=[.!?])\s")
LEADING = re.compile(r"^(?:[-*+]\s+)*(?:\[.?\]\s*)?")  # a list marker or a checkbox at the start of copied text
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
TOP_BULLET = re.compile(r"^[-*+]\s")
CHECKBOX = re.compile(r"^- \[.\] (.*?)(?: _\((?:follow-up, session \d{2}:\d{2}|chat)\)_)?\s*$")
MEETING_NOTE = re.compile(r"^wiki/work/meetings/[^/]+\.md$")
LINK = re.compile(r"^https://[^\s\[\]]+$")
CLOCK = re.compile(r"T(\d{2}:\d{2})")
HHMM = re.compile(r"^\d{2}:\d{2}$")
EMPTY = {"none", "n/a", "nothing", "none yet"}
CHAT_TEXT = ("channel", "first_line", "last_author")


def clean(text) -> str:
    """Copied text as one safe line (spec §3.2): whitespace folded, credentials masked, `[[` and `]]` removed, no
    leading list marker or checkbox, then cut at 200 characters."""
    text = redact_credentials(SPACE.sub(" ", str(text)).strip())
    text = LEADING.sub("", text.replace("[[", "").replace("]]", "")).strip()
    return text[:MAX_CHARS].rstrip()


def norm(text: str) -> str:
    """Case-folded, whitespace-folded text for the follow-up dedupe."""
    return SPACE.sub(" ", text).strip().casefold()


def alert_once(vault, tz, message: str) -> None:
    """One `[today]` alert a day (spec §3.3); later ones that day are dropped."""
    now = datetime.now(tz)
    path = Path(vault) / "system" / "logs" / f"alerts_{now:%Y-%m-%d}.md"
    try:
        if " [today] " in path.read_text(encoding="utf-8", errors="replace"):
            return
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"- {now:%H:%M:%S} [today] {message}\n")


def _clock(value, tz) -> str:
    """HH:MM of an ISO 8601 time in the vault's timezone; the written time when it has no offset."""
    text = str(value or "")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        found = CLOCK.search(text)
        return found.group(1) if found else "00:00"
    if moment.tzinfo is not None:
        moment = moment.astimezone(tz)
    return moment.strftime("%H:%M")


def _items(lines) -> list:
    """The cleaned bullets of a section; a line that is not a bullet continues the one before. "None" is no item."""
    raw = []
    for line in lines:
        found = BULLET.match(line)
        if found:
            raw.append(found.group(1))
        elif raw:
            raw[-1] += " " + line.strip()
        else:
            raw.append(line.strip())
    out = [clean(t) for t in raw]
    return [t for t in out if t and t.casefold().rstrip(".") not in EMPTY]


def _first_sentence(body: str) -> str:
    """The first sentence of the digest's Outcome, or of its first line of text when it has no Outcome."""
    lines = recall.digest_part(body, "outcome") or [
        line for line in body.splitlines() if line.strip() and not recall.HEADING.match(line)][:1]
    text = SPACE.sub(" ", " ".join(LEADING.sub("", line.strip()) for line in lines)).strip()
    return SENTENCE.split(text, maxsplit=1)[0]


def _section(body: str, heading: str) -> list:
    out, on = [], False
    for line in body.split("\n"):
        if line.startswith("## "):
            on = line.strip() == f"## {heading}"
            continue
        if on:
            out.append(line)
    return out


def session_entry(stem: str, clock: str, body: str) -> str:
    """One digest: the first sentence of Outcome and its Delivered bullets (spec §3.2)."""
    head = f"- {clock} **session** {clean(_first_sentence(body)) or 'No outcome recorded.'} ([[{stem}]])"
    return "\n".join([head, *(f"  - delivered: {d}" for d in _items(recall.digest_part(body, "delivered")))])


def meeting_entry(stem: str, clock: str, body: str, owners: set) -> str:
    """One meeting: its link, the bullets under ## Decisions, and the owner's open actions quoted (spec §3.2)."""
    decisions = sum(1 for line in _section(body, "Decisions") if TOP_BULLET.match(line))
    yours = [clean(text) for names, _, text in meetings.open_actions(body) if any(n.casefold() in owners for n in names)]
    text = f"- {clock} **meeting** [[{stem}]]: {decisions} decision{'' if decisions == 1 else 's'}"
    return text + ("; yours: " + ", ".join(f'"{t}"' for t in yours) if yours else "")


def chat_entry(thread: dict, owners: set) -> str:
    """One thread, or a `- [ ] Reply in …` line when someone mentioned the owner after the owner's last message."""
    channel, first, link = clean(thread["channel"]), clean(thread["first_line"]), thread["link"]
    author, last = clean(thread["last_author"]), thread["last_time"]
    if thread["needs_reply"]:
        return f'- [ ] Reply in {channel}: "{first}" ({author}, {last}) {link} _(chat)_'
    who = "you replied" if author.casefold() in owners else f"last: {author}"
    return f'- {last} **chat** {channel}: "{first}" ({who}) {link}'


def _ledger(vault: Path) -> list:
    path = vault / LEDGER
    out = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                out.append(record)
    return out


def _append(path: Path, records) -> None:
    """Append JSON lines; a torn last line is ended first so it cannot swallow the next record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab+") as fh:
        fh.seek(0, 2)
        if fh.tell():
            fh.seek(-1, 2)
            if fh.read(1) != b"\n":
                fh.write(b"\n")
        fh.write("".join(json.dumps(r) + "\n" for r in records).encode("utf-8"))


def _digests(vault: Path, day: str) -> list:
    """(path, created_at, partition) of the day's digests in raw/<p>/notes/ and raw/<p>/archive/ (spec §3.3)."""
    idx = Index(vault)
    idx.refresh(timeout=30)
    conn = sqlite3.connect(idx.db_path)
    try:
        return conn.execute("SELECT path, created_at, partition FROM v_session_digest "
                            "WHERE substr(created_at, 1, 10) = ? ORDER BY created_at, path", (day,)).fetchall()
    finally:
        conn.close()


def _imported(vault: Path, day: str) -> list:
    """Meeting note paths of the day's `kind: imported` records, oldest first, once each."""
    path = vault / "system" / "logs" / f"meetings-{day[:7]}.jsonl"
    notes = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if (isinstance(record, dict) and record.get("kind") == "imported"
                    and str(record.get("time", "")).startswith(day) and isinstance(record.get("note"), str)
                    and record["note"] not in notes):
                notes.append(record["note"])
    return notes


def _threads(vault: Path, day: str, tz) -> list:
    """(thread, sha256 of its line) for each valid line of system/logs/inputs/<day>/chat.jsonl (plan 2 writes it)."""
    rel = f"system/logs/inputs/{day}/chat.jsonl"
    path = vault / rel
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        alert_once(vault, tz, f"skipped {rel} ({exc.__class__.__name__}); it is read again on the next tick")
        return []
    out = []
    for n, line in enumerate(lines, 1):
        try:
            thread = json.loads(line)
        except ValueError:
            thread = None
        if not (isinstance(thread, dict) and isinstance(thread.get("link"), str) and LINK.match(thread["link"])
                and all(isinstance(thread.get(k), str) for k in CHAT_TEXT)
                and isinstance(thread.get("last_time"), str) and HHMM.match(thread["last_time"])
                and isinstance(thread.get("needs_reply"), bool)):
            alert_once(vault, tz, f"skipped line {n} of {rel}: not a thread record")
            continue
        out.append((thread, hashlib.sha256(line.encode("utf-8")).hexdigest()))
    return out


def write(vault, day: str, tz) -> int:
    """Append the day's new work sessions, meetings and chat threads to briefings/<day>.today.md and record them in
    the ledger; returns the number of entries written. A source already in the ledger is never written again."""
    vault = Path(vault)
    target = vault / "briefings" / f"{day}.today.md"
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    listed = {norm(m.group(1)) for m in map(CHECKBOX.match, existing.splitlines()) if m}
    ledger = _ledger(vault)
    entries, records = [], []

    def add(clock: str, text: str) -> None:
        entries.append((clock, len(entries), text))

    for path, created, partition in _digests(vault, day):
        if partition != PARTITION:
            continue
        try:
            data = (vault / path).read_bytes()
            body = frontmatter.parse(data.decode("utf-8")).body
        except (OSError, UnicodeDecodeError) as exc:
            alert_once(vault, tz, f"skipped {path} ({exc.__class__.__name__}); it is read again on the next tick")
            continue
        sha, name = hashlib.sha256(data).hexdigest(), Path(path).name
        if any(r.get("kind") == "session" and (Path(str(r.get("source", ""))).name == name or r.get("sha256") == sha)
               for r in ledger):
            continue  # moved to the archive or changed since: written once
        clock = _clock(created, tz)
        add(clock, session_entry(Path(path).stem, clock, body))
        for item in _items(recall.digest_part(body, "follow-ups")):
            if norm(item) not in listed:
                listed.add(norm(item))
                add(clock, f"- [ ] {item} _(follow-up, session {clock})_")
        records.append({"kind": "session", "source": path, "sha256": sha})

    owners = meetings.owner_names(vault)
    for note in _imported(vault, day):
        if not MEETING_NOTE.match(note) or any(r.get("kind") == "meeting" and r.get("source") == note for r in ledger):
            continue
        path = vault / note
        if not path.is_file():
            continue  # the import has not published it yet: the next tick writes it
        try:
            data = path.read_bytes()
            parsed = frontmatter.parse(data.decode("utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            alert_once(vault, tz, f"skipped {note} ({exc.__class__.__name__}); it is read again on the next tick")
            continue
        clock = _clock((parsed.data or {}).get("start") or f"T{path.stem[11:13]}:{path.stem[13:15]}", tz)
        add(clock, meeting_entry(path.stem, clock, parsed.body, owners))
        records.append({"kind": "meeting", "source": note, "sha256": hashlib.sha256(data).hexdigest()})

    for thread, sha in _threads(vault, day, tz):
        link = thread["link"]
        known = [r.get("kind") for r in ledger + records if r.get("source") == link and r.get("date") == day]
        if thread["needs_reply"] and "reply" not in known:
            kind = "reply"
        elif not thread["needs_reply"] and not known:
            kind = "chat"
        else:
            continue  # each thread once a day; a later "needs reply" adds only its checkbox line
        add(thread["last_time"], chat_entry(thread, owners))
        records.append({"kind": kind, "source": link, "sha256": sha, "date": day})

    if not entries:
        return 0
    text = "".join(f"{entry}\n{BLANK}" for _, _, entry in sorted(entries))
    if not existing:
        text = f'---\ntype: today\ndate: "{day}"\n---\n' + text
    elif not existing.endswith("\n"):
        text = "\n" + text
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(text)
    written_at = datetime.now(tz).isoformat(timespec="seconds")
    _append(vault / LEDGER, [{**r, "date": day, "written_at": written_at} for r in records])
    return len(entries)
````

Create `system/scripts/today_log.py`:

````text
#!/usr/bin/env python3
"""Append the day's work sessions, meetings and chat threads to briefings/<date>.today.md (intraday brief spec §3.3).

Usage: today_log.py [--date YYYY-MM-DD] (default: today in the configured timezone). Intake runs the same step on
every tick of a server or standalone vault. Exit 0 (written, nothing new, or a client, which never writes the log),
2 on a bad date, 4 when run.lock is busy.
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.intake import Intake  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="today_log.py")
    parser.add_argument("--date")
    args = parser.parse_args(argv)
    if args.date is not None:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
                raise ValueError(args.date)
            date.fromisoformat(args.date)
        except ValueError:
            print(f"today_log: invalid date: {args.date}", file=sys.stderr)
            return 2
    status = Intake(Path(__file__).resolve().parents[2]).write_today(args.date)
    if status == "busy":
        print("today_log: run.lock is busy; the next intake tick writes the log", file=sys.stderr)
        return 4
    if status == "client":
        print("today_log: a client never writes the log; the server does", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
````

Run: `chmod +x system/scripts/today_log.py`

Edit 3 in `system/scripts/vaultlib/intake.py`. Find:

````text
from . import frontmatter, meetings, publish, redact as redactmod, schema as schemamod
````

Replace with:

````text
from . import frontmatter, meetings, publish, redact as redactmod, schema as schemamod, today_log
````

Edit 4 in `system/scripts/vaultlib/intake.py`. Find:

````text
    # -- meetings (meetings spec §2.3) -------------------------------------
    def import_meetings(self) -> None:
````

Replace with:

````text
    # -- intraday log (intraday brief spec §3.3) ---------------------------
    def write_today(self, day=None) -> str:
        """Append the day's work sessions, meetings and chat threads to briefings/<day>.today.md under run.lock (no
        wait). Returns "client" (a client never writes it), "busy" (a run holds a lock) or "written"."""
        if self.config("machine_role", "standalone") == "client":
            return "client"
        try:
            with self.lock("run.lock", timeout=0):
                today_log.write(self.vault, day or self.today(), self.tz)
        except TimeoutError:
            return "busy"  # the next tick writes
        return "written"

    # -- meetings (meetings spec §2.3) -------------------------------------
    def import_meetings(self) -> None:
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest -q system/tests/python/test_today_log.py system/tests/python/test_schema_notes.py system/tests/python/test_intake.py > .scratch/t2.out 2>&1`
Then: `echo $?`
Expected: `0`; no `failed` or `error` in `.scratch/t2.out`.

Run: `bats system/tests/vault_integrity.bats > .scratch/t2-bats.out 2>&1`
Then: `echo $?`
Expected: `0`.

- [ ] **Step 5: Commit**

Write `.scratch/msg-2.txt`:

```text
feat(today): the intraday log writer (#94)

vaultlib/today_log.py appends the day's work sessions (first sentence
of Outcome, Delivered bullets, one checkbox per follow-up), meetings
imported that day (decisions counted, the owner's open actions
quoted) and chat threads from inputs/<date>/chat.jsonl to
briefings/<date>.today.md. Copied text is folded, masked, stripped of
links and checkboxes and cut at 200 characters; every entry ends with
a blank line. A ledger writes each source once, only work sources are
read, and an unreadable source raises one [today] alert a day.
Intake.write_today runs it under run.lock and does nothing on a
client; today_log.py runs it by hand. The file has its own schema,
type: today.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Run: `git add system/schemas/today.md system/scripts/vaultlib/today_log.py system/scripts/today_log.py system/scripts/vaultlib/intake.py system/tests/python/test_today_log.py system/tests/python/test_schema_notes.py system/tests/vault_integrity.bats`
Run: `git commit -q -F .scratch/msg-2.txt`

### Task 3: Intake writes the log on every tick

**Files:**
- Modify: `system/scripts/vaultlib/intake.py` (`run`)
- Test: `system/tests/python/test_intake.py`

**Interfaces:**
- Consumes: `Intake.write_today()` (Task 2), `Intake.process_inbox() -> bool`, `Intake.process_digests() -> bool`, `Intake.alert(message)`; `today()`, `later()`, `TZ`, `write` and the `iv` fixture in `test_intake.py`.
- Produces: `run()` order: `extract_briefing`, `import_meetings` (guarded), `process_inbox`, `process_digests` when the inbox returned True, then `write_today` (guarded; an exception becomes the alert `today log failed (<Error>: <msg>); will retry`).

- [ ] **Step 1: Write the failing tests**

Append to `system/tests/python/test_intake.py`:

````text


def test_the_today_log_runs_after_digests_every_tick_and_its_failure_is_an_alert(iv, monkeypatch):
    order = []
    monkeypatch.setattr(Intake, "process_inbox", lambda self: order.append("inbox") or False)
    monkeypatch.setattr(Intake, "process_digests", lambda self: order.append("digests") or True)
    monkeypatch.setattr(Intake, "write_today", lambda self: order.append("today") or "written")
    Intake(iv, now=later()).run()
    assert order == ["inbox", "today"]  # a stopped inbox skips the digests, never the log
    monkeypatch.setattr(Intake, "process_inbox", lambda self: order.append("inbox") or True)
    order.clear()
    Intake(iv, now=later()).run()
    assert order == ["inbox", "digests", "today"]
    monkeypatch.setattr(Intake, "write_today", lambda self: 1 / 0)
    Intake(iv, now=later()).run()
    alerts = "".join(p.read_text() for p in (iv / "system/logs").glob("alerts_*.md"))
    assert "[intake] today log failed (ZeroDivisionError" in alerts


def test_a_tick_writes_todays_work_digest_to_the_today_log(iv):
    day = today()
    offset = datetime.now(TZ).isoformat()[-6:]
    write(iv, f"raw/work/notes/{day}-0900-aaaaaaaa-shipped.md",
          f'---\ntype: session_digest\npartition: work\ncodebase: "vault"\nsession_id: "s1"\n'
          f'created_at: "{day}T09:00:00{offset}"\n---\n## Outcome\nShipped it.\n')
    Intake(iv, now=later()).run()
    text = (iv / f"briefings/{day}.today.md").read_text(encoding="utf-8")
    assert f"- 09:00 **session** Shipped it. ([[{day}-0900-aaaaaaaa-shipped]])\n" in text
````

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_intake.py -k today_log > .scratch/t3-red.out 2>&1`
Then: `echo $?`
Expected: `1`; `2 failed` (the first stops at `order == ["inbox", "today"]`, the second at `FileNotFoundError`).

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/vaultlib/intake.py`. Find:

````text
                if self.process_inbox():
                    self.process_digests()
        except TimeoutError:
            pass  # another daemon is running
````

Replace with:

````text
                if self.process_inbox():
                    self.process_digests()
                try:
                    self.write_today()
                except Exception as exc:  # noqa: BLE001 - the tick still ends normally
                    self.alert(f"today log failed ({exc.__class__.__name__}: {exc}); will retry")
        except TimeoutError:
            pass  # another daemon is running
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest -q system/tests/python/test_intake.py system/tests/python/test_intake_digests.py system/tests/python/test_meetings.py system/tests/python/test_today_log.py > .scratch/t3.out 2>&1`
Then: `echo $?`
Expected: `0`; no `failed` in `.scratch/t3.out`.

- [ ] **Step 5: Commit**

Write `.scratch/msg-3.txt`:

```text
feat(intake): write the intraday log on every tick (#94)

run() calls write_today after the digests, inside intake.lock, also
when the inbox stopped early. An exception becomes an intake alert and
the tick ends normally; a busy run.lock waits for the next tick.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Run: `git add system/scripts/vaultlib/intake.py system/tests/python/test_intake.py`
Run: `git commit -q -F .scratch/msg-3.txt`

### Task 4: The briefing embeds the log, and the archive moves it

**Files:**
- Modify: `system/templates/daily-briefing.md`, `.claude/commands/brief.md`, `system/schemas/briefing.md`, `system/scripts/brief_prep.sh`, `CLAUDE.md`, `README.md`
- Test: `system/tests/commands.bats`, `system/tests/prep.bats`

**Interfaces:**
- Consumes: `briefings/<date>.today.md` (Task 2); `$BP`, `make_vault` and the calendar stub in `prep.bats`.
- Produces: the template lines `## 🕑 Today so far` and `![[{{date}}.today]]` before `## 📝 Notes`; `brief_prep.sh` moves `<day>.today.md` to `briefings/archive/<YYYY-MM>/` with its briefing.

- [ ] **Step 1: Write the failing tests**

Append to `system/tests/commands.bats`:

````text

@test "the briefing embeds the intraday log before Notes, and /brief keeps or adds it (intraday brief §3.1)" {
  t=system/templates/daily-briefing.md
  today_line="$(grep -nx '## 🕑 Today so far' "$t" | cut -d: -f1)"
  embed_line="$(grep -nxF '![[{{date}}.today]]' "$t" | cut -d: -f1)"
  notes_line="$(grep -nx '## 📝 Notes' "$t" | cut -d: -f1)"
  [ -n "$today_line" ]
  [ "$today_line" -lt "$embed_line" ]
  [ "$embed_line" -lt "$notes_line" ]
  f=.claude/commands/brief.md
  grep -qF 'Keep the `![[<date>.today]]` and `![[<date>.debrief]]` lines.' "$f"
  grep -qF 'When an existing briefing has no 🕑 Today so far section, add it before 📝 Notes' "$f"
  grep -qF 'and the open `- [ ] ` lines of the intraday logs' "$f"
  grep -qF 'It embeds `<date>.today`' system/schemas/briefing.md
  grep -qF '`<date>.today.md` (the day'"'"'s work sessions, meetings and chat threads' CLAUDE.md
  grep -qF '**Today so far.**' README.md
}
````

Append to `system/tests/prep.bats`:

````text

@test "brief_prep: a day's .today.md moves to the archive with its briefing (intraday brief §3.1)" {
  today="$(TZ=America/Denver date +%F)"
  yesterday="$(date -d "$today -1 day" +%F)"
  mkdir -p briefings
  for f in 2026-09-29.md 2026-09-29.today.md "$yesterday.today.md" "$today.today.md"; do
    printf 'x\n' > "briefings/$f"
  done
  run "$BP"
  [ "$(TZ=America/Denver date +%F)" = "$today" ] || skip "the date changed during the run"
  [ "$status" -eq 0 ]
  [ -f briefings/archive/2026-09/2026-09-29.today.md ]
  [ -f briefings/archive/2026-09/2026-09-29.md ]
  [ ! -e briefings/2026-09-29.today.md ]
  [ -f "briefings/$yesterday.today.md" ]
  [ -f "briefings/$today.today.md" ]
}
````

- [ ] **Step 2: Run them to verify they fail**

Run: `bats system/tests/commands.bats system/tests/prep.bats > .scratch/t4-red.out 2>&1`
Then: `echo $?`
Expected: `1`; two `not ok` lines, the two new tests.

- [ ] **Step 3: Implement**

Edit 1 in `system/templates/daily-briefing.md`. Find:

````text
## 📝 Notes
````

Replace with:

````text
## 🕑 Today so far

![[{{date}}.today]]

## 📝 Notes
````

Edit 2 in `.claude/commands/brief.md`. Find:

````text
Keep the `![[<date>.debrief]]` line.
````

Replace with:

````text
Keep the `![[<date>.today]]` and `![[<date>.debrief]]` lines. When an existing briefing has no 🕑 Today so far section, add it before 📝 Notes: the heading `## 🕑 Today so far`, a blank line and `![[<date>.today]]`. Never write `briefings/<date>.today.md` itself: intake appends it through the day.
````

Edit 3 in `.claude/commands/brief.md`. Find:

````text
- `system/logs/inputs/<date>/carried.md`: open objectives carried from the latest earlier briefing, one `- [ ] … _(open since YYYY-MM-DD)_` line each (empty when nothing is open).
````

Replace with:

````text
- `system/logs/inputs/<date>/carried.md`: open objectives carried from the latest earlier briefing and the open `- [ ] ` lines of the intraday logs (`briefings/<day>.today.md`) from that day on, one `- [ ] … _(open since YYYY-MM-DD)_` line each (empty when nothing is open).
````

Edit 4 in `system/schemas/briefing.md`. Find:

````text
The daily ledger `briefings/<date>.md`, written by `/brief`. The evening section embeds `<date>.debrief`.
````

Replace with:

````text
The daily ledger `briefings/<date>.md`, written by `/brief`. It embeds `<date>.today` (the intraday log, schema `today`) under 🕑 Today so far, before the Notes, and its evening section embeds `<date>.debrief`.
````

Edit 5 in `system/scripts/brief_prep.sh`. Find:

````text
      [[ "$name" =~ ^(([0-9]{4}-[0-9]{2})-[0-9]{2})(\.debrief)?\.md$ ]] || continue
````

Replace with:

````text
      [[ "$name" =~ ^(([0-9]{4}-[0-9]{2})-[0-9]{2})(\.debrief|\.today)?\.md$ ]] || continue
````

Edit 6 in `system/scripts/brief_prep.sh`. Find:

````text
# Briefings and debriefs dated before today move to briefings/archive/<YYYY-MM>/, after carried.md and
````

Replace with:

````text
# Briefings, intraday logs and debriefs dated before today move to briefings/archive/<YYYY-MM>/, after carried.md and
````

Edit 7 in `CLAUDE.md`. Find:

````text
- `briefings/`: `<date>.md` (morning briefing) and `<date>.debrief.md` (evening debrief, embedded in the briefing).
````

Replace with:

````text
- `briefings/`: `<date>.md` (morning briefing), `<date>.today.md` (the day's work sessions, meetings and chat threads, appended by intake and embedded in the briefing; tick or drop its lines, never rewrite them) and `<date>.debrief.md` (evening debrief, embedded in the briefing).
````

Edit 8 in `README.md`. Find:

````text
A 📝 Notes section holds your own notes for the day; `/brief` never edits it. Briefings and debriefs from before yesterday move to `briefings/archive/<YYYY-MM>/` |
````

Replace with:

````text
A 🕑 Today so far section embeds `briefings/<date>.today.md`, which intake appends through the day. A 📝 Notes section holds your own notes for the day; `/brief` never edits it. Briefings, intraday logs and debriefs from before yesterday move to `briefings/archive/<YYYY-MM>/` |
````

Edit 9 in `README.md`. Find:

````text
and a GitHub `template_remote`).
````

Replace with:

````text
and a GitHub `template_remote`).

**Today so far.** On a server or a standalone vault, every intake tick runs `system/scripts/today_log.py`, which appends to `briefings/<date>.today.md`: each of the day's `work` session digests (the first sentence of its Outcome, its Delivered bullets, and one `- [ ]` line per follow-up), each meeting imported that day (its decisions counted and your open action items quoted), and the chat threads in `system/logs/inputs/<date>/chat.jsonl` when a chat fetch writes that file. It makes no model call, masks credentials, copies at most 200 characters per line and never turns copied text into a link or a checkbox; personal and shared sources stay out. The briefing embeds the file under 🕑 Today so far. The file is append-only: tick `[x]` or drop `[-]` a line in Obsidian. An open line carries into the next brief, and the debrief lists it under Open from today.
````

Edit 10 in `README.md`. Find:

````text
briefings/                    today's and yesterday's briefs and debriefs; earlier days in archive/<YYYY-MM>/
````

Replace with:

````text
briefings/                    today's and yesterday's briefs, intraday logs and debriefs; earlier days in archive/<YYYY-MM>/
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2.
Then: `echo $?`
Expected: `0`; no `not ok`.

Run: `python3 -m pytest -q system/tests/python/test_schema_notes.py > .scratch/t4-py.out 2>&1`
Then: `echo $?`
Expected: `0` (the edited template still validates as a briefing).

- [ ] **Step 5: Commit**

Write `.scratch/msg-4.txt`:

```text
feat(brief): embed the intraday log in the briefing (#94)

The briefing template gains 🕑 Today so far with ![[<date>.today]]
before the Notes; /brief keeps the line and adds the section to a
briefing that lacks it. brief_prep.sh archives <date>.today.md with
its briefing. The briefing schema, CLAUDE.md and the README describe
the file.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Run: `git add system/templates/daily-briefing.md .claude/commands/brief.md system/schemas/briefing.md system/scripts/brief_prep.sh CLAUDE.md README.md system/tests/commands.bats system/tests/prep.bats`
Run: `git commit -q -F .scratch/msg-4.txt`

### Task 5: Open intraday lines carry forward

**Files:**
- Modify: `system/scripts/carry_forward.py`
- Test: `system/tests/python/test_carry_forward.py`

**Interfaces:**
- Consumes: `briefing(objectives, extra)` and `run(vault, date)` in `test_carry_forward.py`; `SINCE`, `open_items(text)` in `carry_forward.py`.
- Produces: `carry_forward.today_items(text) -> list[str]`, `carry_forward.find(day, suffix) -> Path | None`; output: the briefing's open objectives, then the open `- [ ] ` lines of every `<day>.today.md` from the briefing's day up to the day before `<date>`, oldest first, each with one `_(open since <day>)_` stamp.

- [ ] **Step 1: Write the failing tests**

Append to `system/tests/python/test_carry_forward.py`:

````text


def today_log(entries: str) -> str:
    return '---\ntype: today\ndate: "x"\n---\n' + entries


def test_open_lines_of_that_days_today_log_carry_after_the_objectives(vault):
    write(vault, "briefings/2026-10-08.md", briefing("- [ ] **Real**\n"))
    write(vault, "briefings/2026-10-08.today.md", today_log(
        "- 11:41 **session** Traced it ([[d]])\n  - delivered: message — reply\n\n"
        "- [ ] Confirm the fix _(follow-up, session 11:41)_\n\n"
        "- [x] Done one _(follow-up, session 11:41)_\n\n"
        "- [-] Dropped one _(chat)_\n\n"
        '- [ ] Reply in #team-x: "Can you confirm" (Blake Sample, 14:05) https://example.slack.com/archives/C2/p2 _(chat)_\n\n'))
    assert run(vault, "2026-10-09").stdout.splitlines() == [
        "- [ ] **Real** _(open since 2026-10-08)_",
        "- [ ] Confirm the fix _(follow-up, session 11:41)_ _(open since 2026-10-08)_",
        '- [ ] Reply in #team-x: "Can you confirm" (Blake Sample, 14:05) https://example.slack.com/archives/C2/p2 _(chat)_ '
        "_(open since 2026-10-08)_",
    ]


def test_an_archived_today_log_carries_and_a_day_without_a_briefing_keeps_its_log(vault):
    write(vault, "briefings/archive/2026-10/2026-10-06.md", briefing("- [ ] **Old**\n"))
    write(vault, "briefings/archive/2026-10/2026-10-06.today.md",
          today_log("- [ ] Archived follow-up _(follow-up, session 09:00)_\n\n"))
    write(vault, "briefings/2026-10-08.today.md", today_log("- [ ] No brief that day _(follow-up, session 10:00)_\n\n"))
    assert run(vault, "2026-10-09").stdout.splitlines() == [
        "- [ ] **Old** _(open since 2026-10-06)_",
        "- [ ] Archived follow-up _(follow-up, session 09:00)_ _(open since 2026-10-06)_",
        "- [ ] No brief that day _(follow-up, session 10:00)_ _(open since 2026-10-08)_",
    ]


def test_the_log_of_the_brief_day_itself_never_carries(vault):
    write(vault, "briefings/2026-10-08.md", briefing("- [ ] **Real**\n"))
    write(vault, "briefings/2026-10-09.today.md", today_log("- [ ] Same day _(follow-up, session 09:00)_\n\n"))
    assert run(vault, "2026-10-09").stdout.splitlines() == ["- [ ] **Real** _(open since 2026-10-08)_"]
````

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_carry_forward.py > .scratch/t5-red.out 2>&1`
Then: `echo $?`
Expected: `1`; `2 failed` (the first two new tests; the third pins today's behavior and passes).

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/carry_forward.py`. Find:

````text
That briefing already carried the older items, so one file is enough. Exit 0, or 2 on a bad date.
````

Replace with:

````text
That briefing already carried the older items, so one file is enough. Then the "- [ ] " lines of the intraday logs
(<day>.today.md, in place or archived) of that day and of every later day before <date>, oldest first, so a day
whose brief did not run keeps its log (intraday brief spec §3.6). Exit 0, or 2 on a bad date.
````

Edit 2 in `system/scripts/carry_forward.py`. Find:

````text
    return [line for line in (section.group(0) if section else "").splitlines() if line.startswith("- [ ] ")]
````

Replace with:

````text
    return [line for line in (section.group(0) if section else "").splitlines() if line.startswith("- [ ] ")]


def today_items(text: str):
    """The open lines of an intraday log: every line starting "- [ ] "."""
    return [line for line in text.splitlines() if line.startswith("- [ ] ")]


def find(day: str, suffix: str):
    """briefings/<day><suffix>, or its copy in briefings/archive/<YYYY-MM>/; None when neither exists."""
    for path in (Path("briefings") / f"{day}{suffix}", Path("briefings") / "archive" / day[:7] / f"{day}{suffix}"):
        if path.is_file():
            return path
    return None
````

Edit 3 in `system/scripts/carry_forward.py`. Find:

````text
    for back in range(1, LOOKBACK_DAYS + 1):
        day = (today - timedelta(days=back)).isoformat()
        path = Path("briefings") / f"{day}.md"
        if not path.is_file():
            path = Path("briefings") / "archive" / day[:7] / f"{day}.md"
        if not path.is_file():
            continue
        for line in open_items(path.read_text(encoding="utf-8")):
            since = min(SINCE.findall(line), default=day)
            print(f"{SINCE.sub('', line).rstrip()} _(open since {since})_")
        return 0
    return 0
````

Replace with:

````text
    items, logs = [], []
    for back in range(1, LOOKBACK_DAYS + 1):
        day = (today - timedelta(days=back)).isoformat()
        log = find(day, ".today.md")
        if log is not None:
            logs.append((day, log))
        path = find(day, ".md")
        if path is not None:
            items = [(line, day) for line in open_items(path.read_text(encoding="utf-8"))]
            break
    for day, log in reversed(logs):
        items += [(line, day) for line in today_items(log.read_text(encoding="utf-8"))]
    for line, day in items:
        since = min(SINCE.findall(line), default=day)
        print(f"{SINCE.sub('', line).rstrip()} _(open since {since})_")
    return 0
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest -q system/tests/python/test_carry_forward.py > .scratch/t5.out 2>&1`
Then: `echo $?`
Expected: `0`; the 8 existing tests pass unchanged.

Run: `bats system/tests/prep.bats > .scratch/t5-bats.out 2>&1`
Then: `echo $?`
Expected: `0` (the `carried.md` tests).

- [ ] **Step 5: Commit**

Write `.scratch/msg-5.txt`:

```text
feat(brief): carry open intraday lines forward (#94)

carry_forward.py also prints the open "- [ ] " lines of the intraday
logs from the latest earlier briefing's day up to yesterday, in place
or archived, after that briefing's objectives and with one open-since
stamp each. A day whose brief did not run still carries its log.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Run: `git add system/scripts/carry_forward.py system/tests/python/test_carry_forward.py`
Run: `git commit -q -F .scratch/msg-5.txt`

### Task 6: The debrief lists what is still open

**Files:**
- Modify: `system/scripts/debrief_prep.sh`, `.claude/commands/debrief.md`, `README.md`
- Test: `system/tests/prep.bats`, `system/tests/commands.bats`

**Interfaces:**
- Consumes: `prep_write`, `prep_unavailable`, `PREP_DATE`, `PREP_DIR` (`lib_prep.sh`); `$DP` and `$IN` in `prep.bats`.
- Produces: `system/logs/inputs/<date>/today_open.md`: the `- [ ] ` lines of `briefings/<date>.today.md` (or its archived copy), empty when there are none; `/debrief` section 1 ends with **Open from today**.

- [ ] **Step 1: Write the failing tests**

Append to `system/tests/prep.bats`:

````text

@test "debrief_prep: today_open.md holds the open lines of the day's intraday log, empty without one (intraday brief §3.7)" {
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ -e "$IN/today_open.md" ]
  [ ! -s "$IN/today_open.md" ]
  mkdir -p briefings/archive/2026-10
  printf -- '---\ntype: today\ndate: "2026-10-01"\n---\n- 09:00 **session** Shipped it ([[d]])\n\n- [ ] Open one _(follow-up, session 09:00)_\n\n- [x] Done one _(follow-up, session 09:00)_\n\n- [-] Dropped _(chat)_\n\n' > briefings/2026-10-01.today.md
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/today_open.md")" = '- [ ] Open one _(follow-up, session 09:00)_' ]
  mv briefings/2026-10-01.today.md briefings/archive/2026-10/
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/today_open.md")" = '- [ ] Open one _(follow-up, session 09:00)_' ]
  run grep -c today_open "$IN/unavailable.md"
  [ "$output" = 0 ]
}
````

Append to `system/tests/commands.bats`:

````text

@test "/debrief lists the open lines of the day's intraday log under Open from today (intraday brief §3.7)" {
  d=.claude/commands/debrief.md
  grep -qF -- '- `system/logs/inputs/<date>/today_open.md`: the open `- [ ] ` lines of `briefings/<date>.today.md`' "$d"
  grep -qF 'Then **Open from today**: every line of `today_open.md` verbatim, in its order, or "None." when it is empty.' "$d"
  [ "$(grep '^### ' system/templates/daily-debrief.md | tail -n 1)" = '### 6. Delivered Today' ]
  grep -qF 'and the items still open in the day'"'"'s intraday log |' README.md
}
````

- [ ] **Step 2: Run them to verify they fail**

Run: `bats system/tests/prep.bats system/tests/commands.bats > .scratch/t6-red.out 2>&1`
Then: `echo $?`
Expected: `1`; two `not ok` lines, the two new tests.

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/debrief_prep.sh`. Find:

````text
prep_write digests.md digests_md || prep_unavailable "digests: index query failed (see $PREP_DIR/prep_errors.log)"
````

Replace with:

````text
prep_write digests.md digests_md || prep_unavailable "digests: index query failed (see $PREP_DIR/prep_errors.log)"

# The open lines of the day's intraday log (intraday brief spec §3.7), in place or archived; empty when it has none.
today_open_md() {
  local f="briefings/$PREP_DATE.today.md"
  [[ -f "$f" ]] || f="briefings/archive/${PREP_DATE:0:7}/$PREP_DATE.today.md"
  [[ -f "$f" ]] || return 0
  grep -- '^- \[ \] ' "$f" || [[ $? -eq 1 ]]
}
prep_write today_open.md today_open_md \
  || prep_unavailable "today_open: briefings/$PREP_DATE.today.md could not be read (see $PREP_DIR/prep_errors.log)"
````

Edit 2 in `.claude/commands/debrief.md`. Find:

````text
- `briefings/<date>.md`: the lines in its 📝 Notes section that start with `delivered:`.
````

Replace with:

````text
- `briefings/<date>.md`: the lines in its 📝 Notes section that start with `delivered:`.
- `system/logs/inputs/<date>/today_open.md`: the open `- [ ] ` lines of `briefings/<date>.today.md`, the day's intraday log (empty when none are open).
````

Edit 3 in `.claude/commands/debrief.md`. Find:

````text
List today's meetings, each as a link to its meeting note.
````

Replace with:

````text
List today's meetings, each as a link to its meeting note. Then **Open from today**: every line of `today_open.md` verbatim, in its order, or "None." when it is empty.
````

Edit 4 in `README.md`. Find:

````text
agent health and what you delivered today |
````

Replace with:

````text
agent health, what you delivered today and the items still open in the day's intraday log |
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2.
Then: `echo $?`
Expected: `0`; no `not ok`.

- [ ] **Step 5: Commit**

Write `.scratch/msg-6.txt`:

```text
feat(debrief): list what is still open from today (#94)

debrief_prep.sh writes today_open.md with the open "- [ ] " lines of
the day's intraday log, in place or archived, and an empty file when
there are none. /debrief lists them under Open from today in section
1, or writes "None."; Delivered Today is unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Run: `git add system/scripts/debrief_prep.sh .claude/commands/debrief.md README.md system/tests/prep.bats system/tests/commands.bats`
Run: `git commit -q -F .scratch/msg-6.txt`

### Task 7: A client tick merges with a server append

**Files:**
- Test: `system/tests/sync.bats`
- Temporarily modify, then revert: `system/scripts/vaultlib/today_log.py` (`BLANK`)

**Interfaces:**
- Consumes: `system/scripts/today_log.py --date` (Task 2); in `sync.bats`, `setup` (server vault `$V` with `machine_role: "server"`, bare origin `$O`, client clone `$C`, branch `$B`, `$VS`).
- Produces: a test later changes must keep green.

- [ ] **Step 1: Write the test**

Append to `system/tests/sync.bats`:

````text

@test "a client's tick on an intraday entry merges with the server's next append (intraday brief §3.1)" {
  mkdir -p raw/work/notes
  printf -- '---\ntype: session_digest\npartition: "work"\ncodebase: "vault"\nsession_id: "s1"\ncreated_at: "2026-10-09T09:00:00-06:00"\n---\n## Outcome\nFirst.\n## Follow-ups\n- Confirm the fix\n' > raw/work/notes/2026-10-09-0900-aaaaaaaa-first.md
  run system/scripts/today_log.py --date 2026-10-09
  [ "$status" -eq 0 ]
  run "$VS"
  [ "$status" -eq 0 ]
  git -C "$C" pull -q
  sed -i 's/^- \[ \] Confirm the fix/- [x] Confirm the fix/' "$C/briefings/2026-10-09.today.md"
  git -C "$C" commit -q -am "client: tick"
  git -C "$C" push -q
  printf -- '---\ntype: session_digest\npartition: "work"\ncodebase: "vault"\nsession_id: "s2"\ncreated_at: "2026-10-09T10:00:00-06:00"\n---\n## Outcome\nSecond.\n' > raw/work/notes/2026-10-09-1000-bbbbbbbb-second.md
  run system/scripts/today_log.py --date 2026-10-09
  [ "$status" -eq 0 ]
  run "$VS"
  [ "$status" -eq 0 ]
  [ ! -e system/logs/sync-blocked ]
  grep -qxF -- '- [x] Confirm the fix _(follow-up, session 09:00)_' briefings/2026-10-09.today.md
  grep -qxF -- '- 10:00 **session** Second. ([[2026-10-09-1000-bbbbbbbb-second]])' briefings/2026-10-09.today.md
  [ "$(git -C "$O" rev-parse "$B")" = "$(git rev-parse HEAD)" ]
}
````

- [ ] **Step 2: Run it; it passes on the code from Task 2**

Run: `bats system/tests/sync.bats > .scratch/t7.out 2>&1`
Then: `echo $?`
Expected: `0`.

- [ ] **Step 3: Prove it can fail (red before green)**

Edit 1 in `system/scripts/vaultlib/today_log.py`. Find:

````text
BLANK = "\n"  # the blank line that ends every entry (spec §3.1)
````

Replace with:

````text
BLANK = ""  # the blank line that ends every entry (spec §3.1)
````

Run: `bats system/tests/sync.bats > .scratch/t7-red.out 2>&1`
Then: `echo $?`
Expected: `1`; one `not ok`, the new test (the second sync exits 3 on a merge conflict in `briefings/2026-10-09.today.md`).

Revert with: `git checkout -- system/scripts/vaultlib/today_log.py`
Then run: `git diff --exit-code system/scripts/vaultlib/today_log.py`
Expected: exit `0`.

- [ ] **Step 4: Run the suite and the gate**

Run: `bats system/tests/sync.bats > .scratch/t7.out 2>&1`
Then: `echo $?`
Expected: `0`.

Run: `system/scripts/verify_setup.sh > .scratch/gate-7.out 2>&1`
Then: `echo $?`
Expected: `0`; no `FAIL` line in the summary of `.scratch/gate-7.out`.

- [ ] **Step 5: Commit**

Write `.scratch/msg-7.txt`:

```text
test(sync): a client tick merges with a server append (#94)

The server writes the intraday log with today_log.py and syncs; the
client ticks the follow-up and pushes; the server appends the next
entry and syncs again. The merge is clean because every entry ends
with a blank line; the test fails when that line is dropped.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Run: `git add system/tests/sync.bats`
Run: `git commit -q -F .scratch/msg-7.txt`

### Task 8: Digests from client sessions (needs decision D1)

Run this task only after the owner approves D1 (tracking `raw/*/notes/*.md`). Without that yes, stop after Task 7.

**Files:**
- Modify: `.gitignore`, `.claude/commands/setup.md` (phase 0 note and phase 5a), `README.md`
- Test: `system/tests/commands.bats` (edit the client test), `system/tests/sync.bats`

**Interfaces:**
- Consumes: `setup_section` in `commands.bats`; the `sync.bats` setup, which copies the repository's `.gitignore` into the server vault.
- Produces: `raw/<p>/notes/*.md` is tracked and syncs both ways; `raw/<p>/archive/` stays ignored; `/setup` phase 5a offers the hooks on a client. `mem_env_ok` and the hooks are unchanged.

- [ ] **Step 1: Write the failing tests**

Edit 1 in `system/tests/commands.bats`. Find:

````text
  # A machine re-run as a client must stop running automation and memory hooks.
````

Replace with:

````text
  # A machine re-run as a client must stop running automation; the memory hooks are offered (intraday brief §3.4).
````

Edit 2 in `system/tests/commands.bats`. Find:

````text
  [[ "$hooks" == *'On a client, never install the hooks.'* ]]
  [[ "$hooks" == *'offer `system/scripts/install_hooks.sh --uninstall`'* ]]
````

Replace with:

````text
  [[ "$hooks" == *'On a client, offer the hooks as on any other machine'* ]]
  [[ "$hooks" == *'`raw/<partition>/notes/`, which sync to the server'* ]]
  run grep -c 'never install the hooks' "$f"
  [ "$output" = 0 ]
  grep -qF 'Phase 5a offers the memory hooks on a client too.' "$f"
  run grep -c 'phases 5 and 5a only remove' README.md
  [ "$output" = 0 ]
````

Append to `system/tests/sync.bats`:

````text

@test "a digest written on a client reaches the server; an archived digest stays untracked (intraday brief §3.4)" {
  mkdir -p "$C/raw/work/notes"
  printf -- '---\ntype: session_digest\npartition: "work"\ncodebase: "vault"\nsession_id: "s3"\ncreated_at: "2026-10-09T11:00:00-06:00"\n---\n## Outcome\nOn the laptop.\n' > "$C/raw/work/notes/2026-10-09-1100-cccccccc-laptop.md"
  git -C "$C" add -A
  git -C "$C" commit -q -m "client: digest"
  git -C "$C" push -q
  run "$VS"
  [ "$status" -eq 0 ]
  [ -f raw/work/notes/2026-10-09-1100-cccccccc-laptop.md ]
  mkdir -p raw/work/archive
  mv raw/work/notes/2026-10-09-1100-cccccccc-laptop.md raw/work/archive/
  run "$VS"
  [ "$status" -eq 0 ]
  [ -z "$(git -C "$O" ls-tree -r --name-only "$B" -- raw/work/notes raw/work/archive)" ]
}
````

- [ ] **Step 2: Run them to verify they fail**

Run: `bats system/tests/commands.bats system/tests/sync.bats > .scratch/t8-red.out 2>&1`
Then: `echo $?`
Expected: `1`; two `not ok` lines: `/setup on a client skips the phases a client does not use, and says so` and the new sync test (the client's `git commit` finds nothing to commit because the digest is ignored).

- [ ] **Step 3: Implement**

Edit 3 in `.gitignore`. Find:

````text
!raw/*/nightshift/*.md
````

Replace with:

````text
!raw/*/nightshift/*.md
!raw/*/notes/
!raw/*/notes/*.md
````

Edit 4 in `.claude/commands/setup.md`. Find:

````text
Phases 5 and 5a run on a client only to remove automation and memory hooks left from an earlier role.
````

Replace with:

````text
Phase 5 runs on a client only to remove automation left from an earlier role. Phase 5a offers the memory hooks on a client too.
````

Edit 5 in `.claude/commands/setup.md`. Find:

````text
On a client, never install the hooks. Run `system/scripts/install_hooks.sh --dry-run`; if it prints both `unchanged` lines (the hooks are installed from an earlier role), explain that a client runs no coding sessions for the vault, offer `system/scripts/install_hooks.sh --uninstall`, and run it only on an explicit yes. Otherwise report "not used on a client". Then go on to phase 6.
````

Replace with:

````text
On a client, offer the hooks as on any other machine, with the steps below. A session on the client then writes its digests to `raw/<partition>/notes/`, which sync to the server: the server compiles them and lists them in the day's `briefings/<date>.today.md`. Recall on a client reads only what has synced so far.
````

Edit 6 in `README.md`. Find:

````text
| `client` | nothing automated | reading and editing the vault in Obsidian on another machine |
````

Replace with:

````text
| `client` | nothing automated; memory hooks when you install them | reading and editing the vault in Obsidian on another machine |
````

Edit 7 in `README.md`. Find:

````text
- Memory hooks: <yes | no>                         (not used on a client)
````

Replace with:

````text
- Memory hooks: <yes | no>
````

Edit 8 in `README.md`. Find:

````text
on a client, phases 5 and 5a only remove units and hooks left from an earlier role.
````

Replace with:

````text
on a client, phase 5 only removes units left from an earlier role, and phase 5a offers the memory hooks.
````

Edit 9 in `README.md`. Find:

````text
Files in `raw/inbox/` on a client are not synced.
````

Replace with:

````text
Files in `raw/inbox/` on a client are not synced. Session digests are: with the memory hooks installed, a session on the client writes its digest to `raw/<partition>/notes/`, and the server compiles it and lists it in the day's intraday log.
````

Edit 10 in `README.md`. Find:

````text
and `raw/<partition>/nightshift/*.md` (Work Order queue notes):
````

Replace with:

````text
`raw/<partition>/nightshift/*.md` (Work Order queue notes) and `raw/<partition>/notes/*.md` (session digests waiting for intake; once compiled they move to the untracked `raw/<partition>/archive/`):
````

- [ ] **Step 4: Run the tests and the gate**

Run: the command from Step 2.
Then: `echo $?`
Expected: `0`; no `not ok`.

Run: `system/scripts/verify_setup.sh > .scratch/gate-8.out 2>&1`
Then: `echo $?`
Expected: `0`; no `FAIL` line in the summary of `.scratch/gate-8.out`.

- [ ] **Step 5: Commit**

Write `.scratch/msg-8.txt`:

```text
feat(memory): digests from client sessions reach the server (#94)

raw/<p>/notes/*.md is tracked, so a digest written by a session on a
client syncs to the server, which compiles it and lists it in the
intraday log; compiled digests move to the untracked archive. /setup
phase 5a offers the memory hooks on a client as on any machine, and
the README says so. The hooks themselves are unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Run: `git add .gitignore .claude/commands/setup.md README.md system/tests/commands.bats system/tests/sync.bats`
Run: `git commit -q -F .scratch/msg-8.txt`
