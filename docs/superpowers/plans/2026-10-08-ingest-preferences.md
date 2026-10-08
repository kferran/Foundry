# Ingest Preference Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/ingest` turns each Corrections bullet of a `work` or `personal` session digest into a `preference` note under `wiki/<p>/preferences/` (base spec §6.21, Compile).

**Architecture:** A new **Preferences** step in `.claude/commands/ingest.md` gives the exact rules: the statement copied verbatim, a match looked up in `v_preference`, evidence or counter-evidence appended, a replacement superseding the old note, a repeated digest left as a noop. A bats test pins the rule text; pytest tests prove the publish gate accepts the note shape the step asks for.

**Tech Stack:** Markdown command prompt, bats 1.8.2, pytest.

**Spec:** `docs/superpowers/specs/2026-10-08-ingest-preferences-design.md`

## Global Constraints

- Work on the branch this session starts on and commit there. Never push and never open a pull request: the runner does both.
- New prose follows the Writing rules in `CLAUDE.md`. Nothing names a specific vault, organization or person.
- Run the suites from the repository root: `bats system/tests/commands.bats` and `python3 -m pytest -q system/tests/python/test_publish.py`. The gate is `system/scripts/verify_setup.sh`.
- Bound tools: bats (`commands.bats`), pytest (`test_publish.py`) and the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains. Read verdicts from exit codes.
- Commits use `git commit -F .nightshift/msg-1.txt`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- A digest compiled a second time adds nothing: the noop rule (the bats test pins its text).
- A `shared` digest never yields a preference note, and the gate rejects one under `wiki/shared/preferences/`: the bats test and `test_a_shared_preference_is_rejected`.
- The statement stays verbatim through the self-edit step: the bats test checks the Self-edit line.
- The note shape the step asks for publishes, and so does a patch that appends a second evidence link: the two pytest tests.
- After the merge, the live headless ingest acceptance is re-run outside this plan (spec §5).

---

### Task 1: The Preferences step in `/ingest`

**Files:**
- Modify: `.claude/commands/ingest.md`
- Test: `system/tests/commands.bats`, `system/tests/python/test_publish.py`

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'Where the skill says to cut a sentence, keep any fact it carries.' "$1"
````

Replace with:

````text
  grep -qF 'Where the skill says to cut a sentence, keep any fact it carries.' "$1"
}

@test "ingest: digest Corrections become preference notes (spec §6.21)" {
  f=.claude/commands/ingest.md
  grep -qF '**Preferences.**' "$f"
  grep -qF 'wiki/<p>/preferences/<PascalCaseName>.md' "$f"
  grep -qF 'before the first ` — `' "$f"
  grep -qF 'Copy it verbatim into `statement`' "$f"
  grep -qF "vault_index.py query \"SELECT path, statement, evidence FROM v_preference WHERE partition = '<p>'\"" "$f"
  grep -qF 'already lists this digest in `evidence`' "$f"
  grep -qF 'append `"[[<digest stem>]]"` to its `counter_evidence`' "$f"
  grep -qF 'stage the old one with `superseded_by: "[[<New>]]"`' "$f"
  grep -qF 'a `shared` digest gets no preference note' "$f"
  grep -qF 'link only to `session_digest` inputs of this run' "$f"
  grep -qF 'A preference'"'"'s `statement` stays verbatim' <(grep -F '**Self-edit.**' "$f")
  run grep -F 'Treat Corrections as facts about how the user wants things done and patch the note they concern' "$f"
  [ "$status" -eq 1 ]
  digest="$(grep -nF '**Digest sections.**' "$f" | cut -d: -f1)"
  pref="$(grep -nF '**Preferences.**' "$f" | cut -d: -f1)"
  edit="$(grep -nF '**Self-edit.**' "$f" | cut -d: -f1)"
  [ -n "$pref" ]
  [ "$digest" -lt "$pref" ]
  [ "$pref" -lt "$edit" ]
````


Edit 1 in `system/tests/python/test_publish.py`. Find:

````text
    assert any("protected field accepted_at" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))
````

Replace with:

````text
    assert any("protected field accepted_at" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


DIGEST = ('---\ntype: session_digest\npartition: work\ncodebase: "vault"\nsession_id: "s-1"\n'
          'created_at: "2026-10-01T11:00:00Z"\nprovenance: ["session"]\n---\n'
          '## Corrections\n- Always run the gate before a push — after a red pull request\n')
PREFERENCE = ('---\ntype: preference\nstatement: "Always run the gate before a push"\npartition: work\n'
              'codebase: "vault"\nevidence: ["[[2026-10-01-s-1]]"]\ncreated_at: "2026-10-01"\n---\n'
              '# Gate Before Push\n\nAfter a red pull request.\n')


def test_a_preference_written_as_ingest_says_publishes(run):
    """The note shape .claude/commands/ingest.md asks for (step Preferences) passes the gate."""
    write(run, "raw/work/notes/2026-10-01-s-1.md", DIGEST)
    stage_new(run, "wiki/work/preferences/GateBeforePush.md", PREFERENCE)
    decide(run, rec("wiki/work/preferences/GateBeforePush.md"))
    assert publish.validate_run(run, RID, now=LATER)[2] == []


def test_a_shared_preference_is_rejected(run):
    write(run, "raw/work/notes/2026-10-01-s-1.md", DIGEST)
    stage_new(run, "wiki/shared/preferences/GateBeforePush.md", PREFERENCE.replace("partition: work", "partition: shared"))
    decide(run, rec("wiki/shared/preferences/GateBeforePush.md"))
    assert "schema: type 'preference' is not allowed in this folder" in reasons(publish.validate_run(run, RID, now=LATER)[2])


def test_a_second_digest_appended_to_evidence_publishes(vault):
    write(vault, "raw/work/notes/2026-10-01-s-1.md", DIGEST)
    write(vault, "raw/work/notes/2026-10-02-s-2.md", DIGEST.replace('"s-1"', '"s-2"'))
    old = write(vault, "wiki/work/preferences/GateBeforePush.md", PREFERENCE)
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    publish.snapshot(vault, RID, ["wiki/work/**", "wiki/shared/**"])
    dst = publish.record_stage(vault, RID, "wiki/work/preferences/GateBeforePush.md")
    dst.write_text(dst.read_text().replace('["[[2026-10-01-s-1]]"]', '["[[2026-10-01-s-1]]", "[[2026-10-02-s-2]]"]'))
    decide(vault, rec("wiki/work/preferences/GateBeforePush.md", "patch"))
    assert publish.validate_run(vault, RID, now=LATER)[2] == []
````


- [ ] **Step 2: Run them**

Run: `bats system/tests/commands.bats`
Expected: FAIL, exactly 1 `not ok`: `ingest: digest Corrections become preference notes (spec §6.21)` (no Preferences step yet).

Run: `python3 -m pytest -q system/tests/python/test_publish.py`
Expected: PASS. The three new gate tests pass already: the gate accepts preference notes today, and these tests pin the exact shape the new step asks for.

- [ ] **Step 3: Implement**

Edit 1 in `.claude/commands/ingest.md`. Find:

````text
   - **create**: headless, write the complete file at `wiki/.staging/<run_id>/<target>`; interactive, at `<target>`. Put it in `wiki/<p>/concepts/`, `wiki/<p>/entities/` or `wiki/<p>/summaries/` (or the same folders under `wiki/shared/` for partition-neutral knowledge), named `PascalCaseName.md`. Follow `system/templates/wiki-concept.md`:
````

Replace with:

````text
   - **create**: headless, write the complete file at `wiki/.staging/<run_id>/<target>`; interactive, at `<target>`. A preference note follows step 9; any other note goes in `wiki/<p>/concepts/`, `wiki/<p>/entities/` or `wiki/<p>/summaries/` (or the same folders under `wiki/shared/` for partition-neutral knowledge), named `PascalCaseName.md`. Follow `system/templates/wiki-concept.md`:
````

Edit 2 in `.claude/commands/ingest.md`. Find:

````text
8. **Digest sections.** Compile Outcome, Decisions and Facts learned as facts. Treat Corrections as facts about how the user wants things done and patch the note they concern. Open questions / friction become friction facts.
9. **Meeting inputs.** An input with `type: meeting_input` holds one meeting's summary, decisions and details; its `meeting` field links the meeting note. Merge its facts and decisions into concept notes, and in each one put the meeting note (its `meeting` field) in `sources` and leave the input out, so the meeting note lists those concepts as backlinks. Read the transcript (`system/scripts/vault_index.py show <meeting note name>.transcript`) only when the summary and details leave a fact unclear. Set `capability` only on a note for work the meeting assigns. Never stage anything under `wiki/<p>/meetings/`: the gate rejects the whole run. Meetings are `work` or `personal`, so a `wiki/shared/` note never cites a meeting (the partition wall).
10. **Self-edit.** Read `.claude/skills/humanizer/SKILL.md` once, then edit the prose of every note you created or changed against its sections A, B, C and E (wording). Skip section D (formatting). Keep every fact, name, number, date and link, and leave frontmatter, code, paths and `_decisions.jsonl` unchanged. Where the skill says to cut a sentence, keep any fact it carries. On a patched note, edit only the text this run wrote. Headless, edit only the staged copies under `wiki/.staging/<run_id>/`.
11. **Finish** with a short summary: one line per decision (decision, target).
````

Replace with:

````text
8. **Digest sections.** Compile Outcome, Decisions and Facts learned as facts. A Correction that fixes a fact in an existing note also patches that note, and every Correction of a `work` or `personal` digest goes to a preference note (step 9). Open questions / friction become friction facts.
9. **Preferences.** For each bullet in the `## Corrections` section of a `session_digest` input whose partition `<p>` is `work` or `personal` (a `shared` digest gets no preference note: there are no shared preferences):
   - **Statement:** the bullet's text before the first ` — ` (space, em dash, space), or the whole bullet when it has none, without the leading `- ` and the spaces around it. Copy it verbatim into `statement`: no rewording, no added or dropped words, the same case and punctuation. A preference counts the digest as evidence only when the digest holds the exact statement.
   - **Find a match:** run `system/scripts/vault_index.py query "SELECT path, statement, evidence FROM v_preference WHERE partition = '<p>'"`, then read the candidates it returns.
   - **Decide**, one decision per bullet:
     - **noop** when a preference with the same meaning already lists this digest in `evidence` (the digest was compiled before). Target: that note.
     - **patch** when a preference with the same meaning exists: stage it and append `"[[<digest stem>]]"` to its `evidence`.
     - **patch** when the bullet contradicts a preference without replacing it: stage it and append `"[[<digest stem>]]"` to its `counter_evidence`.
     - **create** and **supersede** when the bullet replaces a preference: create the new one with `supersedes: ["[[<Old>]]"]` and stage the old one with `superseded_by: "[[<New>]]"`.
     - **create** when nothing matches.
   - **A new note** is `wiki/<p>/preferences/<PascalCaseName>.md`, named for the statement's subject, with exactly this frontmatter: `type: preference`, `statement` (verbatim), `partition: <p>`, `codebase` (the digest's value, when it has one), `evidence: ["[[<digest stem>]]"]` and `created_at` (today; headless: the run id's date). The body is a `# <Title>` heading and one line with the bullet's context.
   - `evidence` and `counter_evidence` link only to `session_digest` inputs of this run.
10. **Meeting inputs.** An input with `type: meeting_input` holds one meeting's summary, decisions and details; its `meeting` field links the meeting note. Merge its facts and decisions into concept notes, and in each one put the meeting note (its `meeting` field) in `sources` and leave the input out, so the meeting note lists those concepts as backlinks. Read the transcript (`system/scripts/vault_index.py show <meeting note name>.transcript`) only when the summary and details leave a fact unclear. Set `capability` only on a note for work the meeting assigns. Never stage anything under `wiki/<p>/meetings/`: the gate rejects the whole run. Meetings are `work` or `personal`, so a `wiki/shared/` note never cites a meeting (the partition wall).
11. **Self-edit.** Read `.claude/skills/humanizer/SKILL.md` once, then edit the prose of every note you created or changed against its sections A, B, C and E (wording). Skip section D (formatting). Keep every fact, name, number, date and link, and leave frontmatter, code, paths and `_decisions.jsonl` unchanged. A preference's `statement` stays verbatim. Where the skill says to cut a sentence, keep any fact it carries. On a patched note, edit only the text this run wrote. Headless, edit only the staged copies under `wiki/.staging/<run_id>/`.
12. **Finish** with a short summary: one line per decision (decision, target).
````


- [ ] **Step 4: Run the tests to verify they pass**

Run: `bats system/tests/commands.bats`
Expected: PASS, no `not ok`.

Run: `python3 -m pytest -q system/tests/python/test_publish.py`
Expected: PASS.

- [ ] **Step 5: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 6: Commit**

Write `.nightshift/msg-1.txt`:

```text
feat(ingest): digest Corrections become preference notes

A new Preferences step in /ingest turns each Corrections bullet of a work
or personal digest into a preference note (spec §6.21, Compile): the
statement copied verbatim, a match looked up in v_preference, evidence or
counter_evidence appended, a replacement superseding the old note, and a
digest compiled twice left as a noop. Shared digests get none. A gate test
proves the note shape the step asks for publishes.
```

Run: `git add .claude/commands/ingest.md system/tests/commands.bats system/tests/python/test_publish.py`

Run: `git commit -q -F .nightshift/msg-1.txt`
