# Carry Forward Stamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A carried objective keeps one `_(open since …)_` stamp with its first date, also after the brief added an age to it (#84).

**Architecture:** `carry_forward.py`'s stamp pattern accepts an optional `, N day(s)` age and is no longer anchored to the line's end; the script removes every stamp from the item's text and writes one stamp with the earliest date found.

**Tech Stack:** Python 3, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-carry-forward-stamp-design.md`

## Global Constraints

- Work on branch `fix/carry-forward-stamp`. Commit there; do not push or open a pull request.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh`; run it outside a sandbox. Never run two gates at once.
- Bound tools: pytest (`system/tests/python/test_carry_forward.py`) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- An item with no stamp still gets the briefing's date: `test_open_items_carry_with_their_first_date`.
- An item stamped twice heals to one stamp with the earlier date, so the 16 items already doubled in a vault fix themselves on the next brief.
- The text before the stamp keeps its words; only trailing whitespace is trimmed.

---

### Task 1: One stamp, earliest date

**Files:**
- Modify: `system/scripts/carry_forward.py`
- Test: `system/tests/python/test_carry_forward.py`

**Interfaces:**
- Produces: the same output format, `<item> _(open since YYYY-MM-DD)_`, one stamp per line.

- [ ] **Step 1: Write the test**

Edit 1 in `system/tests/python/test_carry_forward.py`. Find:

````text
        "- [ ] **Old item** _(open since 2026-10-01)_",
````

Replace with:

````text
        "- [ ] **Old item** _(open since 2026-10-01)_",
    ]


def test_a_stamp_with_an_age_keeps_its_date_and_two_stamps_keep_the_earlier(vault):
    write(vault, "briefings/2026-10-08.md", briefing(   # the brief adds the age; #84
        "- [ ] **Aged** _(open since 2026-10-06, 2 days)_\n"
        "- [ ] **Doubled** _(open since 2026-10-06, 1 day)_ _(open since 2026-10-07)_\n"))
    assert run(vault, "2026-10-09").stdout.splitlines() == [
        "- [ ] **Aged** _(open since 2026-10-06)_",
        "- [ ] **Doubled** _(open since 2026-10-06)_",
````


- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest -q system/tests/python/test_carry_forward.py`
Expected: FAIL, 1 failed.

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/carry_forward.py`. Find:

````text
SINCE = re.compile(r"\s*_\(open since (\d{4}-\d{2}-\d{2})\)_\s*$")
````

Replace with:

````text
# The brief adds an age ("_(open since 2026-10-06, 3 days)_"); an item stamped twice keeps its earliest date (#84).
SINCE = re.compile(r"\s*_\(open since (\d{4}-\d{2}-\d{2})(?:, \d+ days?)?\)_")
````

Edit 2 in `system/scripts/carry_forward.py`. Find:

````text
            m = SINCE.search(line)
            print(f"{SINCE.sub('', line)} _(open since {m.group(1) if m else day})_")
````

Replace with:

````text
            since = min(SINCE.findall(line), default=day)
            print(f"{SINCE.sub('', line).rstrip()} _(open since {since})_")
````


- [ ] **Step 4: Run the tests and the gate**

Run: the command from Step 2.
Expected: PASS, 0 failed.

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
fix(brief): carry forward keeps one open-since stamp (#84)

The brief rewrites a carried item's stamp with an age ("_(open since
2026-10-06, 3 days)_"), which the stamp pattern did not match, so each
carry appended a second, newer stamp and later briefs counted the age
from it. The pattern now accepts the age, every stamp is removed from
the text, and the item keeps its earliest date, so items already
stamped twice heal on their next carry.

Closes #84
```

Run: `git add system/scripts/carry_forward.py system/tests/python/test_carry_forward.py`

Run: `git commit -q -F .scratch/msg-1.txt`
