# Plan 1: Foundation (Baseline, Schemas, Index, Lint) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the repo into the committed vault baseline and build "The Ark": a string-safe frontmatter parser, schema notes with validation, a SQLite FTS5 index with link resolution, partition walls and lifecycle checks, a guarded read-only query path, caller-scope enforcement, the `vault_index.py` CLI, and the deterministic linter and pre-commit hook.

**Architecture:** Markdown notes are the source of truth. `system/scripts/vaultlib/` is a small Python package (stdlib + PyYAML) with one responsibility per module; `system/scripts/vault_index.py` is its CLI entry point. The index (`system/index.db`, gitignored) is derived and incrementally refreshed under an `fcntl` lock before every read command. `lint_vault.sh` and `.githooks/pre-commit` are thin shell wrappers over `vault_index.py issues`.

**Tech Stack:** Python 3.14 (stdlib `sqlite3` with FTS5, `fcntl`, `argparse`), PyYAML 6, pytest, bats, bash, git.

**Spec:** `docs/superpowers/specs/2026-09-30-vault-template-design.md` — this plan implements §4 steps 1–2, §6 (Python conventions, invocation form, argument validation), §6.8, §6.9, §6.15, §6.16 (all subcommands except `stage` and `recall`, which Plans 2 and 3 add), §10 (`.gitignore`), and the §12 test groups for those components. Read the spec sections before each task.

## Global Constraints

- Python: `#!/usr/bin/env python3`, stdlib plus PyYAML only, no network. Never crash on bad input notes: parse failures become `issues` rows (§6).
- Vault root: `VAULT_ROOT` env override for tests, otherwise derived from the file's location (`system/scripts/…` → two levels up for scripts, three for `vaultlib/` modules) (§6).
- Invocation form: scripts are executable and invoked as `system/scripts/<name> …` from the vault root (§6).
- YAML: every scalar loads as a string (`17:00`, `no`, `0123`, `2026-09-30` stay strings); schema kinds do all typing (§6.15).
- Dead links, ambiguous links, unknown fields, orphans and `link-to-inactive` are **warnings**; schema violations, partition-wall violations, supersession errors and `unique_true` violations are **errors** (§6.8, §6.15).
- Partitions are exactly `work`, `personal`, `shared`; walls: `work`↔`personal` forbidden, `shared`→`work|personal` forbidden; `wiki/Index.md`, `index` notes and `briefings/` exempt (§6.15).
- Query guard: `mode=ro` URI + `PRAGMA query_only = 1` + `SQLITE_LIMIT_ATTACHED = 0` + authorizer allowing only `SELECT`, `READ`, `FUNCTION`, `RECURSIVE` and pragmas `data_version`, `table_info`, `table_xinfo`; 2 s progress-handler timeout; 200-row cap (§6.16).
- Caller scope comes from `$PWD`, never from arguments or environment; `VAULT_ROOT` overrides do not bypass it (§6.16).
- Index excludes dot-directories, `.git/`, `.obsidian/`, and does not index notes under `system/logs/`, `system/quarantine/`, `system/fleet/`, `system/templates/`, `system/tests/`, `docs/`, `raw/inbox/`, `raw/archive/` (those files still count for link resolution).
- Commit after every task; end commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Work on branch `feat/vault-template`.

## Review Focus

1. **A note with Windows line endings or a UTF-8 BOM.** Users who sync from other machines will have them; frontmatter must still parse. Pinned in Task 4 (`test_crlf_and_bom`).
2. **A note edited twice within the same second with the same size.** mtime+size can collide; the sha256 check must still pick up the change when mtime differs by sub-second. Pinned in Task 8 (`test_refresh_detects_same_size_edit`).
3. **A wikilink with different capitalisation than the file (`[[kafka]]` for `Kafka.md`).** Obsidian resolves it; so must we. Pinned in Task 7 (`test_case_insensitive_basename`).
4. **Running `vault_index.py` from a subdirectory of the vault** (e.g. `cd wiki && ../system/scripts/vault_index.py issues`). Scope must still be `vault` and relative file arguments must resolve from the caller's cwd. Pinned in Task 12 (`test_cli_from_subdirectory`).
5. **A user-authored note that is just plain markdown with no frontmatter in `wiki/work/`.** It is a schema error (missing frontmatter), not a crash, and other notes still index. Pinned in Task 8 (`test_plain_markdown_note_is_an_error_not_a_crash`).

---

## File Structure

| File | Responsibility |
|---|---|
| `system/scripts/vaultlib/__init__.py` | Package marker |
| `system/scripts/vaultlib/yamlload.py` | String-only YAML loader |
| `system/scripts/vaultlib/frontmatter.py` | Split note into frontmatter/body, parse, error positions, key lines |
| `system/scripts/vaultlib/schema.py` | Load schema notes, field kinds, routing, per-note validation, partition helpers |
| `system/scripts/vaultlib/links.py` | Extract wikilinks, markdown links, tags (code-aware); resolve targets |
| `system/scripts/vaultlib/index.py` | SQLite schema, locked incremental refresh, global issues, generated views |
| `system/scripts/vaultlib/guard.py` | Read-only guarded SQL execution |
| `system/scripts/vaultlib/scope.py` | Caller scope from cwd; codebase registry; git common dir |
| `system/scripts/vaultlib/retrieve.py` | `related`, `backlinks`, `orphans`, note lookup |
| `system/scripts/vaultlib/cli.py` | Argument parsing, path validation, output formatting, `field`/`set` |
| `system/scripts/vault_index.py` | Entry point |
| `system/scripts/lint_vault.sh` | Linter wrapper |
| `.githooks/pre-commit` | Pre-commit gate |
| `system/schemas/*.md` | 11 schema notes |
| `system/templates/{wiki-concept,daily-briefing,daily-debrief,intent-shaper}.md` | Templates matching their schemas |
| `wiki/Index.md`, `wiki/{work,personal,shared}/…/.gitkeep` | Committed vault skeleton |
| `system/tests/python/{conftest,helpers}.py`, `test_*.py` | pytest suite |
| `system/tests/fixtures/vault/` | Minimal fixture vault |
| `system/tests/scripts.bats`, `system/tests/vault_integrity.bats` | Shell-level suites |

---

### Task 1: Baseline commit and generator removal

**Files:**
- Generated by `scaffold.sh` at repo root (many files)
- Delete: `.git/hooks/pre-commit`, `scaffold.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: the baseline tree later tasks modify (`system/templates/`, `system/tests/vault_integrity.bats`, `.gitignore`, `CLAUDE.md`, `.claude/commands/`).

- [ ] **Step 1: Confirm a clean tree on the feature branch**

Run: `git status --short && git branch --show-current`
Expected: no output from status; branch `feat/vault-template`.

- [ ] **Step 2: Run the generator**

Run: `bash scaffold.sh`
Expected: ends with `✅ Scaffolding complete in /home/…/Jarvis`. A "Missing tools" warning is fine.

- [ ] **Step 3: Remove the generated LLM pre-commit hook (spec §4 step 1)**

Run: `rm -f .git/hooks/pre-commit && test ! -e .git/hooks/pre-commit && echo removed`
Expected: `removed`.

- [ ] **Step 4: Commit the baseline**

```bash
git add -A
git commit -m "chore: generate vault structure from scaffold.sh

Baseline output of scaffold.sh. Units contain this machine's absolute
path; later commits convert them to templates.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Remove the generator**

```bash
git rm -q scaffold.sh
git commit -m "chore: remove scaffold.sh; the repo is now the template

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Test tooling, fixture vault and .gitignore

**Files:**
- Modify: `.gitignore` (replace contents)
- Create: `system/scripts/vaultlib/__init__.py`, `system/tests/python/conftest.py`, `system/tests/python/helpers.py`, `system/tests/python/test_smoke.py`
- Create: `system/tests/fixtures/vault/wiki/Index.md`, `system/tests/fixtures/vault/wiki/work/concepts/Kafka.md`, `system/tests/fixtures/vault/wiki/shared/concepts/Git.md`, `system/tests/fixtures/vault/wiki/personal/concepts/Gardening.md`

**Interfaces:**
- Produces: pytest fixtures `vault` (a `Path` to a temp copy of the fixture vault plus the repo's real `system/schemas/`) and `cli` (callable `cli(*args, cwd=None) -> CompletedProcess`); `helpers.write(root, rel, text) -> Path`; `helpers.concept(partition, title, body="", **extra) -> str`; constants `helpers.REPO`.

- [ ] **Step 1: Install pytest and bats (user action)**

Ask the user to run: `! sudo pacman -S --needed python-pytest bash-bats`
Then verify: `python3 -m pytest --version && bats --version`
Expected: both print versions.

- [ ] **Step 2: Replace .gitignore with the spec §10 version**

`.gitignore`:
```
.obsidian/workspace*.json
.obsidian/graph.json
.claude/settings.local.json
system/config.md
system/codebases/*.md
!system/codebases/example.md
system/logs/*
!system/logs/.gitkeep
system/quarantine/*
!system/quarantine/.gitkeep
raw/**
!raw/
!raw/inbox/
!raw/archive/
!raw/telemetry/
!raw/*/.gitkeep
system/index.db
wiki/.staging/
system/index.db-wal
system/index.db-shm
system/*.lock
system/fleet/
__pycache__/
.pytest_cache/
```

- [ ] **Step 3: Create the package marker and test helpers**

`system/scripts/vaultlib/__init__.py`:
```python
"""Jarvis vault library: schemas, index and CLI (spec §6.15–§6.16)."""
```

`system/tests/python/helpers.py`:
```python
"""Shared helpers for the vaultlib test suite."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def write(root: Path, rel: str, text: str) -> Path:
    """Write text to root/rel, creating parent directories."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def concept(partition: str, title: str, body: str = "", **extra: str) -> str:
    """Return a valid concept note. extra values are raw YAML snippets."""
    fm = {
        "type": "concept",
        "tags": "[]",
        "compiled_at": '"2026-09-01"',
        "partition": partition,
    }
    fm.update(extra)
    lines = ["---", *[f"{k}: {v}" for k, v in fm.items()], "---", f"# {title}", body, ""]
    return "\n".join(lines)
```

`system/tests/python/conftest.py`:
```python
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from helpers import REPO  # noqa: E402

sys.path.insert(0, str(REPO / "system" / "scripts"))
FIXTURE = REPO / "system" / "tests" / "fixtures" / "vault"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    shutil.copytree(FIXTURE, root)
    schemas = REPO / "system" / "schemas"
    if schemas.exists():
        shutil.copytree(schemas, root / "system" / "schemas")
    else:
        (root / "system" / "schemas").mkdir(parents=True)
    return root


@pytest.fixture
def cli(vault: Path):
    script = REPO / "system" / "scripts" / "vault_index.py"

    def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ, VAULT_ROOT=str(vault))
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=cwd or vault, env=env, capture_output=True, text=True,
        )

    return run
```

- [ ] **Step 4: Create the fixture vault**

`system/tests/fixtures/vault/wiki/Index.md`:
```markdown
---
type: index
tags: []
---
# Index
- [[Kafka]]
- [[Git]]
- [[Gardening]]
```

`system/tests/fixtures/vault/wiki/work/concepts/Kafka.md`:
```markdown
---
type: concept
tags: [streaming]
compiled_at: "2026-09-01"
partition: work
---
# Kafka
Kafka is a distributed commit log used for event streaming. Version control lives in [[Git]].
```

`system/tests/fixtures/vault/wiki/shared/concepts/Git.md`:
```markdown
---
type: concept
tags: [tooling]
compiled_at: "2026-09-01"
partition: shared
---
# Git
Git is a distributed version control system.
```

`system/tests/fixtures/vault/wiki/personal/concepts/Gardening.md`:
```markdown
---
type: concept
tags: [hobby]
compiled_at: "2026-09-01"
partition: personal
---
# Gardening
Tomatoes need full sun and regular watering.
```

- [ ] **Step 5: Write the smoke test**

`system/tests/python/test_smoke.py`:
```python
def test_fixture_vault_has_notes(vault):
    assert (vault / "wiki" / "Index.md").is_file()
    assert (vault / "wiki" / "work" / "concepts" / "Kafka.md").is_file()


def test_vaultlib_importable():
    import vaultlib  # noqa: F401
```

- [ ] **Step 6: Run it**

Run: `python3 -m pytest system/tests/python -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add .gitignore system/scripts/vaultlib/__init__.py system/tests/python system/tests/fixtures
git commit -m "test: add pytest harness, fixture vault and spec gitignore

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: String-only YAML loader

**Files:**
- Create: `system/scripts/vaultlib/yamlload.py`
- Test: `system/tests/python/test_yamlload.py`

**Interfaces:**
- Produces: `yamlload.load(text: str) -> Any` (dict/list/str; never bool/int/float/None/date for scalars; `None` only for an empty document).

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_yamlload.py`:
```python
import pytest

from vaultlib import yamlload


@pytest.mark.parametrize("raw, expected", [
    ("17:00", "17:00"),
    ("06:00", "06:00"),
    ("no", "no"),
    ("yes", "yes"),
    ("on", "on"),
    ("0123", "0123"),
    ("1e3", "1e3"),
    ("2026-09-30", "2026-09-30"),
    ("~", "~"),
    ("null", "null"),
    ("true", "true"),
])
def test_scalars_stay_strings(raw, expected):
    assert yamlload.load(f"a: {raw}") == {"a": expected}


def test_empty_value_is_empty_string():
    assert yamlload.load("a:") == {"a": ""}


def test_keys_stay_strings():
    assert yamlload.load("no: x") == {"no": "x"}


def test_lists_and_maps_preserved():
    assert yamlload.load("a: [x, 2]\nb:\n  c: 3") == {"a": ["x", "2"], "b": {"c": "3"}}


def test_unquoted_wikilink_is_nested_list():
    assert yamlload.load("source: [[Index]]") == {"source": [["Index"]]}


def test_empty_document_is_none():
    assert yamlload.load("") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_yamlload.py -q`
Expected: FAIL with `ImportError: cannot import name 'yamlload'`.

- [ ] **Step 3: Implement**

`system/scripts/vaultlib/yamlload.py`:
```python
"""YAML loading that keeps every scalar a string (spec §6.15)."""
import yaml

_DROP = {
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:timestamp",
}


class StringLoader(yaml.SafeLoader):
    """SafeLoader whose implicit resolvers never produce non-string scalars."""


StringLoader.yaml_implicit_resolvers = {
    first: [(tag, rx) for tag, rx in resolvers if tag not in _DROP]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load(text: str):
    """Parse YAML text. Scalars are always str; an empty document returns None."""
    return yaml.load(text, Loader=StringLoader)
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_yamlload.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/yamlload.py system/tests/python/test_yamlload.py
git commit -m "feat(ark): add string-only YAML loader

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Frontmatter parsing

**Files:**
- Create: `system/scripts/vaultlib/frontmatter.py`
- Test: `system/tests/python/test_frontmatter.py`

**Interfaces:**
- Consumes: `yamlload.load`.
- Produces: `@dataclass Note(data: dict | None, fm_text: str | None, body: str, body_line: int, error: str | None = None, error_line: int | None = None)`; `frontmatter.parse(text: str) -> Note`; `frontmatter.key_line(note: Note, key: str) -> int`.

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_frontmatter.py`:
```python
from vaultlib import frontmatter


def test_no_frontmatter():
    note = frontmatter.parse("# Title\nbody")
    assert note.data is None and note.error is None
    assert note.body == "# Title\nbody" and note.body_line == 1


def test_basic_frontmatter():
    note = frontmatter.parse("---\ntype: concept\ntags: [a]\n---\n# T\nbody")
    assert note.data == {"type": "concept", "tags": ["a"]}
    assert note.body == "# T\nbody"
    assert note.body_line == 5


def test_empty_frontmatter_is_empty_dict():
    assert frontmatter.parse("---\n---\nbody").data == {}


def test_malformed_yaml_reports_line():
    note = frontmatter.parse("---\ntype: concept\ntags: [a\n---\nbody")
    assert note.data is None
    assert note.error.startswith("malformed frontmatter")
    assert note.error_line >= 2


def test_non_mapping_frontmatter():
    note = frontmatter.parse("---\n- a\n- b\n---\nbody")
    assert note.data is None and note.error == "frontmatter is not a mapping"


def test_unterminated():
    note = frontmatter.parse("---\ntype: concept\nbody")
    assert note.error == "unterminated frontmatter"


def test_dashes_inside_body_ignored():
    note = frontmatter.parse("---\ntype: a\n---\ntext\n---\nmore")
    assert note.data == {"type": "a"} and note.body == "text\n---\nmore"


def test_crlf_and_bom():
    note = frontmatter.parse("﻿---\r\ntype: concept\r\n---\r\nbody")
    assert note.data == {"type": "concept"}


def test_key_line():
    note = frontmatter.parse("---\ntype: concept\ntags: []\n---\n")
    assert frontmatter.key_line(note, "tags") == 3
    assert frontmatter.key_line(note, "missing") == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_frontmatter.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

`system/scripts/vaultlib/frontmatter.py`:
```python
"""Split and parse note frontmatter (spec §6.15)."""
from dataclasses import dataclass

import yaml

from . import yamlload


@dataclass
class Note:
    data: dict | None
    fm_text: str | None
    body: str
    body_line: int
    error: str | None = None
    error_line: int | None = None


def parse(text: str) -> Note:
    """Parse a note. Never raises on bad input; problems are reported in error/error_line."""
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return Note(None, None, text, 1)
    for i in range(1, len(lines)):
        if lines[i] in ("---", "..."):
            fm_text = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            body_line = i + 2
            try:
                data = yamlload.load(fm_text)
            except yaml.YAMLError as exc:
                mark = getattr(exc, "problem_mark", None)
                line = mark.line + 2 if mark is not None else 1
                problem = getattr(exc, "problem", None) or str(exc)
                return Note(None, fm_text, body, body_line, f"malformed frontmatter: {problem}", line)
            if data is None:
                data = {}
            if not isinstance(data, dict):
                return Note(None, fm_text, body, body_line, "frontmatter is not a mapping", 2)
            return Note(data, fm_text, body, body_line)
    return Note(None, None, text, 1, "unterminated frontmatter", 1)


def key_line(note: Note, key: str) -> int:
    """Best-effort 1-based line number of a top-level key (2 if not found)."""
    if note.fm_text is None:
        return 1
    for i, line in enumerate(note.fm_text.split("\n")):
        if line.startswith(f"{key}:"):
            return i + 2
    return 2
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_frontmatter.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/frontmatter.py system/tests/python/test_frontmatter.py
git commit -m "feat(ark): add frontmatter parser with error positions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Schema loading and per-note validation

**Files:**
- Create: `system/scripts/vaultlib/schema.py`
- Test: `system/tests/python/test_schema.py`

**Interfaces:**
- Consumes: `frontmatter.parse`, `frontmatter.key_line`, `Note`.
- Produces:
  - `PARTITIONS = ("work", "personal", "shared")`
  - `@dataclass Issue(path: str, line: int, severity: str, code: str, message: str)`
  - `@dataclass FieldSpec(kind, required=False, default=None, value=None, values=[], of=None, fields={}, must_exist=None, unique_true=False, matches_folder=False)`
  - `@dataclass Schema(name: str, folders: list[str], fields: dict[str, FieldSpec], source: str)`
  - `class SchemaError(Exception)`
  - `@dataclass Context(vault: Path, zoneinfo: Path = Path("/usr/share/zoneinfo"))`
  - `load_schemas(vault: Path) -> dict[str, Schema]`
  - `covers(folder: str, path: str) -> bool`, `schemas_covering(schemas, path) -> list[Schema]`
  - `path_partition(path: str) -> str | None`
  - `link_target(value) -> str | None`
  - `validate_note(schemas, rel: str, note: Note, ctx: Context) -> tuple[str | None, list[Issue]]`

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_schema.py`:
```python
import pytest

from helpers import write
from vaultlib import frontmatter, schema

TEST_SCHEMA = """---
type: schema
schema_for: thing
folders: ["things/", "single.md"]
fields:
  type: {kind: const, value: thing, required: true}
  name: {kind: string, required: true}
  count: {kind: int}
  flag: {kind: bool, default: "false"}
  day: {kind: date}
  at: {kind: datetime}
  hhmm: {kind: time}
  tz: {kind: timezone}
  color: {kind: enum, values: [red, blue]}
  items: {kind: list, of: string}
  layers: {kind: map, of: string}
  ref: {kind: link}
  where: {kind: path, must_exist: warn}
  partition: {kind: enum, values: [work, personal, shared], matches_folder: true}
---
# Thing
"""


@pytest.fixture
def schemas(tmp_path):
    write(tmp_path, "system/schemas/thing.md", TEST_SCHEMA)
    return schema.load_schemas(tmp_path), schema.Context(tmp_path)


def check(schemas_ctx, rel, fm):
    schemas, ctx = schemas_ctx
    note = frontmatter.parse(f"---\n{fm}\n---\nbody")
    return schema.validate_note(schemas, rel, note, ctx)


def codes(issues, severity=None):
    return [i.code for i in issues if severity is None or i.severity == severity]


def test_valid_minimal(schemas):
    t, issues = check(schemas, "things/a.md", "type: thing\nname: A")
    assert t == "thing" and issues == []


def test_uncovered_path_is_ignored(schemas):
    assert check(schemas, "elsewhere/a.md", "nothing: here") == (None, [])


def test_exact_file_folder(schemas):
    assert check(schemas, "single.md", "type: thing\nname: A")[1] == []


def test_missing_required(schemas):
    assert codes(check(schemas, "things/a.md", "type: thing")[1]) == ["required"]


def test_missing_type_and_unknown_type(schemas):
    assert codes(check(schemas, "things/a.md", "name: A")[1]) == ["missing-type"]
    assert codes(check(schemas, "things/a.md", "type: other\nname: A")[1]) == ["unknown-type"]


def test_plain_markdown_in_covered_folder(schemas):
    s, ctx = schemas
    _, issues = schema.validate_note(s, "things/a.md", frontmatter.parse("# just text"), ctx)
    assert codes(issues) == ["frontmatter"]


@pytest.mark.parametrize("field, good, bad", [
    ("count", '"0123"', "1.5"),
    ("flag", "TRUE", "yes"),
    ("day", '"2026-09-30"', '"2026-13-01"'),
    ("at", '"2026-09-30T06:00:00-06:00"', "tomorrow"),
    ("hhmm", "17:00", "25:00"),
    ("tz", "America/Denver", "Mars/Olympus"),
    ("color", "red", "green"),
    ("items", "[a, b]", "notalist"),
    ("layers", "{ui: web/}", "[a]"),
    ("ref", '"[[Index]]"', "Index"),
])
def test_kinds(schemas, field, good, bad):
    base = "type: thing\nname: A\n"
    assert codes(check(schemas, "things/a.md", base + f"{field}: {good}")[1], "error") == []
    assert codes(check(schemas, "things/a.md", base + f"{field}: {bad}")[1], "error") == ["field"]


def test_link_accepts_unquoted_nested_list(schemas):
    assert codes(check(schemas, "things/a.md", "type: thing\nname: A\nref: [[Index]]")[1]) == []


def test_path_must_exist_warns(schemas):
    _, issues = check(schemas, "things/a.md", "type: thing\nname: A\nwhere: /no/such/path")
    assert [(i.severity, i.code) for i in issues] == [("warning", "field")]


def test_unknown_field_warns(schemas):
    _, issues = check(schemas, "things/a.md", "type: thing\nname: A\nextra: 1")
    assert [(i.severity, i.code) for i in issues] == [("warning", "unknown-field")]


def test_matches_folder(schemas):
    s, ctx = schemas
    s["thing"].folders.append("wiki/")
    ok = schema.validate_note(s, "wiki/work/a.md", frontmatter.parse("---\ntype: thing\nname: A\npartition: work\n---\n"), ctx)
    bad = schema.validate_note(s, "wiki/work/a.md", frontmatter.parse("---\ntype: thing\nname: A\npartition: personal\n---\n"), ctx)
    assert codes(ok[1]) == [] and codes(bad[1]) == ["partition-folder"]


def test_type_folder_mismatch(tmp_path):
    write(tmp_path, "system/schemas/a.md", "---\ntype: schema\nschema_for: a\nfolders: [\"x/\"]\nfields:\n  type: {kind: const, value: a}\n---\n")
    write(tmp_path, "system/schemas/b.md", "---\ntype: schema\nschema_for: b\nfolders: [\"y/\"]\nfields:\n  type: {kind: const, value: b}\n---\n")
    s = schema.load_schemas(tmp_path)
    _, issues = schema.validate_note(s, "x/n.md", frontmatter.parse("---\ntype: b\n---\n"), schema.Context(tmp_path))
    assert codes(issues) == ["type-folder-mismatch"]


def test_bad_schema_raises(tmp_path):
    write(tmp_path, "system/schemas/bad.md", "---\ntype: schema\nschema_for: bad\nfolders: [\"x/\"]\nfields:\n  a: {kind: nope}\n---\n")
    with pytest.raises(schema.SchemaError):
        schema.load_schemas(tmp_path)


def test_path_partition():
    assert schema.path_partition("wiki/work/concepts/A.md") == "work"
    assert schema.path_partition("raw/personal/notes/d.md") == "personal"
    assert schema.path_partition("wiki/Index.md") is None
    assert schema.path_partition("briefings/2026-09-30.md") is None


def test_link_target():
    assert schema.link_target("[[A|alias]]") == "A|alias"
    assert schema.link_target([["A"]]) == "A"
    assert schema.link_target("A") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_schema.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

`system/scripts/vaultlib/schema.py`:
```python
"""Load schema notes and validate note frontmatter against them (spec §6.15)."""
import datetime
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter

PARTITIONS = ("work", "personal", "shared")
KINDS = {"const", "string", "text", "int", "bool", "date", "datetime", "time", "timezone",
         "enum", "list", "map", "link", "path", "fieldspecs"}
IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
INT = re.compile(r"^-?\d+$")
TZ = re.compile(r"^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+)*$")
WIKILINK = re.compile(r"\s*\[\[([^\[\]]+)\]\]\s*")


@dataclass
class Issue:
    path: str
    line: int
    severity: str
    code: str
    message: str


@dataclass
class FieldSpec:
    kind: str
    required: bool = False
    default: str | None = None
    value: str | None = None
    values: list = field(default_factory=list)
    of: "FieldSpec | None" = None
    fields: dict = field(default_factory=dict)
    must_exist: str | None = None
    unique_true: bool = False
    matches_folder: bool = False


@dataclass
class Schema:
    name: str
    folders: list
    fields: dict
    source: str


class SchemaError(Exception):
    pass


@dataclass
class Context:
    vault: Path
    zoneinfo: Path = Path("/usr/share/zoneinfo")


def _flag(raw: dict, key: str) -> bool:
    return str(raw.get(key, "false")).lower() == "true"


def parse_fieldspec(raw, where: str) -> FieldSpec:
    if isinstance(raw, str):
        raw = {"kind": raw}
    if not isinstance(raw, dict) or "kind" not in raw:
        raise SchemaError(f"{where}: field spec needs a kind")
    kind = raw["kind"]
    if kind not in KINDS:
        raise SchemaError(f"{where}: unknown kind {kind!r}")
    spec = FieldSpec(
        kind=kind, required=_flag(raw, "required"), default=raw.get("default"),
        value=raw.get("value"), values=list(raw.get("values") or []),
        must_exist=raw.get("must_exist"), unique_true=_flag(raw, "unique_true"),
        matches_folder=_flag(raw, "matches_folder"),
    )
    if kind == "list":
        spec.of = parse_fieldspec(raw.get("of", "string"), f"{where}.of")
    if kind == "map":
        if "fields" in raw:
            if not isinstance(raw["fields"], dict):
                raise SchemaError(f"{where}: map fields must be a mapping")
            spec.fields = {k: parse_fieldspec(v, f"{where}.{k}") for k, v in raw["fields"].items()}
        else:
            spec.of = parse_fieldspec(raw.get("of", "string"), f"{where}.of")
    if kind == "enum" and not spec.values:
        raise SchemaError(f"{where}: enum needs values")
    if kind == "const" and spec.value is None:
        raise SchemaError(f"{where}: const needs a value")
    return spec


def load_schemas(vault: Path) -> dict:
    """Load every system/schemas/*.md. Raises SchemaError on an invalid schema note."""
    schemas = {}
    for path in sorted((Path(vault) / "system" / "schemas").glob("*.md")):
        rel = path.relative_to(vault).as_posix()
        note = frontmatter.parse(path.read_text(encoding="utf-8"))
        if note.data is None:
            raise SchemaError(f"{rel}: {note.error or 'no frontmatter'}")
        data = note.data
        name = data.get("schema_for")
        if not isinstance(name, str) or not IDENT.match(name):
            raise SchemaError(f"{rel}: schema_for must be an identifier")
        folders = data.get("folders")
        if not isinstance(folders, list) or not all(isinstance(f, str) for f in folders):
            raise SchemaError(f"{rel}: folders must be a list of strings")
        raw_fields = data.get("fields")
        if not isinstance(raw_fields, dict):
            raise SchemaError(f"{rel}: fields must be a mapping")
        fields = {}
        for key, raw in raw_fields.items():
            if not IDENT.match(str(key)):
                raise SchemaError(f"{rel}: field name {key!r} is not an identifier")
            fields[key] = parse_fieldspec(raw, f"{rel}:{key}")
        if name in schemas:
            raise SchemaError(f"{rel}: duplicate schema {name!r}")
        schemas[name] = Schema(name, folders, fields, rel)
    return schemas


def covers(folder: str, path: str) -> bool:
    return path == folder or (folder.endswith("/") and path.startswith(folder))


def schemas_covering(schemas: dict, path: str) -> list:
    return [s for s in schemas.values() if any(covers(f, path) for f in s.folders)]


def path_partition(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) > 2 and parts[0] in ("wiki", "raw") and parts[1] in PARTITIONS:
        return parts[1]
    return None


def link_target(value) -> str | None:
    """Normalize a link value: '[[T]]' or the nested list [['T']] -> 'T'."""
    if isinstance(value, str):
        match = WIKILINK.fullmatch(value)
        return match.group(1) if match else None
    if (isinstance(value, list) and len(value) == 1 and isinstance(value[0], list)
            and len(value[0]) == 1 and isinstance(value[0][0], str)):
        return value[0][0]
    return None


def check_value(spec: FieldSpec, value, ctx: Context, where: str) -> list:
    """Return [(severity, message)] for one value."""
    kind = spec.kind

    def err(msg):
        return [("error", f"{where}: {msg}")]

    if kind == "list":
        if not isinstance(value, list):
            return err("expected a list")
        out = []
        for i, item in enumerate(value):
            out += check_value(spec.of, item, ctx, f"{where}[{i}]")
        return out
    if kind == "map":
        if not isinstance(value, dict):
            return err("expected a mapping")
        out = []
        for key, item in value.items():
            if spec.fields:
                if key not in spec.fields:
                    out.append(("warning", f"{where}.{key}: unknown key"))
                    continue
                out += check_value(spec.fields[key], item, ctx, f"{where}.{key}")
            else:
                out += check_value(spec.of, item, ctx, f"{where}.{key}")
        for key, sub in spec.fields.items():
            if sub.required and key not in value:
                out += err(f"missing required key {key}")
        return out
    if kind == "fieldspecs":
        if not isinstance(value, dict):
            return err("expected a mapping of field specs")
        out = []
        for key, raw in value.items():
            try:
                parse_fieldspec(raw, f"{where}.{key}")
            except SchemaError as exc:
                out.append(("error", str(exc)))
        return out
    if kind == "link":
        return [] if link_target(value) is not None else err('expected a wikilink like "[[Note]]"')
    if not isinstance(value, str):
        return err(f"expected a {kind} scalar")
    if kind == "const":
        return [] if value == spec.value else err(f"must be {spec.value!r}")
    if kind in ("string", "text"):
        return []
    if kind == "int":
        return [] if INT.match(value) else err("expected an integer")
    if kind == "bool":
        return [] if value.lower() in ("true", "false") else err("expected true or false")
    if kind == "date":
        if DATE.match(value):
            try:
                datetime.date.fromisoformat(value)
                return []
            except ValueError:
                pass
        return err("expected a date YYYY-MM-DD")
    if kind == "datetime":
        try:
            datetime.datetime.fromisoformat(value)
            return []
        except ValueError:
            return err("expected an ISO 8601 datetime")
    if kind == "time":
        return [] if TIME.match(value) else err("expected HH:MM")
    if kind == "timezone":
        ok = bool(TZ.match(value)) and ".." not in value and (ctx.zoneinfo / value).is_file()
        return [] if ok else err(f"unknown timezone {value!r}")
    if kind == "enum":
        allowed = [str(v) for v in spec.values]
        return [] if value in allowed else err(f"must be one of {', '.join(allowed)}")
    if kind == "path":
        if spec.must_exist in ("warn", "error") and not Path(os.path.expanduser(value)).exists():
            severity = "error" if spec.must_exist == "error" else "warning"
            return [(severity, f"{where}: path does not exist: {value}")]
        return []
    return err(f"unsupported kind {kind}")


def validate_note(schemas: dict, rel: str, note, ctx: Context) -> tuple:
    """Validate one parsed note. Returns (type or None, issues). Uncovered paths return (None, [])."""
    covering = schemas_covering(schemas, rel)
    if not covering:
        return None, []
    if note.data is None:
        return None, [Issue(rel, note.error_line or 1, "error", "frontmatter", note.error or "missing frontmatter")]
    ntype = note.data.get("type")
    type_line = frontmatter.key_line(note, "type")
    if not isinstance(ntype, str) or not ntype:
        return None, [Issue(rel, type_line, "error", "missing-type", "frontmatter has no type")]
    sch = schemas.get(ntype)
    if sch is None:
        return None, [Issue(rel, type_line, "error", "unknown-type", f"no schema for type {ntype!r}")]
    if sch not in covering:
        return ntype, [Issue(rel, type_line, "error", "type-folder-mismatch", f"type {ntype!r} is not allowed in this folder")]
    issues = []
    for name, spec in sch.fields.items():
        line = frontmatter.key_line(note, name)
        value = note.data.get(name)
        if name not in note.data or value == "":
            if spec.required:
                issues.append(Issue(rel, line, "error", "required", f"missing required field {name}"))
            continue
        for severity, message in check_value(spec, value, ctx, name):
            issues.append(Issue(rel, line, severity, "field", message))
        if spec.matches_folder and isinstance(value, str) and value != path_partition(rel):
            issues.append(Issue(rel, line, "error", "partition-folder",
                                f"{name} {value!r} does not match folder partition {path_partition(rel)!r}"))
    for name in note.data:
        if name not in sch.fields:
            issues.append(Issue(rel, frontmatter.key_line(note, str(name)), "warning", "unknown-field", f"unknown field {name}"))
    return ntype, issues
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_schema.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/schema.py system/tests/python/test_schema.py
git commit -m "feat(ark): add schema loading and per-note validation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Schema notes and templates (drift guard)

**Files:**
- Create: `system/schemas/{schema,concept,index,briefing,debrief,plan_gate,production_error,config,codebase,session_digest,preference}.md`
- Modify: `system/templates/wiki-concept.md`, `system/templates/daily-briefing.md`, `system/templates/intent-shaper.md` (replace contents)
- Create: `system/templates/daily-debrief.md`
- Test: `system/tests/python/test_schema_notes.py`

**Interfaces:**
- Consumes: `schema.load_schemas`, `schema.validate_note`, `frontmatter.parse`.
- Produces: the shipped schemas (type names: `schema concept index briefing debrief plan_gate production_error config codebase session_digest preference`); `TEMPLATE_TARGETS` mapping used again by `vault_integrity.bats` (Task 14).

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_schema_notes.py`:
```python
import re

from helpers import REPO
from vaultlib import frontmatter, schema

SAMPLE = {
    "date": "2026-09-30", "partition": "work", "codebase": "ultron", "agent_name": "CodingAgent",
    "source_stem": "SampleSource", "title": "Sample", "status": "active", "brief_time": "06:00",
    "debrief_time": "17:00", "branch_name": "fm/sample", "strategic_focus": "Stability",
    "short_feature_description": "Sample", "strategic_planning_note": "SamplePlan",
}
TEMPLATE_TARGETS = {
    "wiki-concept.md": "wiki/work/concepts/Sample.md",
    "daily-briefing.md": "briefings/2026-09-30.md",
    "daily-debrief.md": "briefings/2026-09-30.debrief.md",
    "intent-shaper.md": "wiki/work/plans/Sample.md",
}
EXPECTED = {"schema", "concept", "index", "briefing", "debrief", "plan_gate",
            "production_error", "config", "codebase", "session_digest", "preference"}


def load():
    return schema.load_schemas(REPO), schema.Context(REPO)


def test_all_schemas_load():
    schemas, _ = load()
    assert set(schemas) == EXPECTED


def test_schema_notes_validate_against_schema_schema():
    schemas, ctx = load()
    for path in (REPO / "system" / "schemas").glob("*.md"):
        note = frontmatter.parse(path.read_text(encoding="utf-8"))
        ntype, issues = schema.validate_note(schemas, f"system/schemas/{path.name}", note, ctx)
        assert ntype == "schema"
        assert [i for i in issues if i.severity == "error"] == [], path.name


def render(text):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: SAMPLE[m.group(1)], text)


def test_every_template_is_mapped():
    names = {p.name for p in (REPO / "system" / "templates").glob("*.md")}
    assert names == set(TEMPLATE_TARGETS)


def test_templates_validate_against_their_schema():
    schemas, ctx = load()
    for name, target in TEMPLATE_TARGETS.items():
        text = render((REPO / "system" / "templates" / name).read_text(encoding="utf-8"))
        ntype, issues = schema.validate_note(schemas, target, frontmatter.parse(text), ctx)
        assert ntype is not None, name
        assert [i.message for i in issues if i.severity == "error"] == [], name


def test_config_sample_validates():
    schemas, ctx = load()
    text = ('---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
            'remote_mode: "none"\ntemplate_remote: ""\ndefault_partition: "personal"\n---\n')
    _, issues = schema.validate_note(schemas, "system/config.md", frontmatter.parse(text), ctx)
    assert [i.message for i in issues if i.severity == "error"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_schema_notes.py -q`
Expected: FAIL (`set()` != EXPECTED, templates not mapped).

- [ ] **Step 3: Create the schema notes**

`system/schemas/schema.md`:
```markdown
---
type: schema
schema_for: schema
folders: ["system/schemas/"]
fields:
  type: {kind: const, value: schema, required: true}
  schema_for: {kind: string, required: true}
  folders: {kind: list, of: string, required: true}
  fields: {kind: fieldspecs, required: true}
---
# Schema
Defines a note type. `folders` lists vault-relative folders (ending in `/`, matching all subfolders) or exact file paths where the type may live. `fields` maps each frontmatter key to a field spec with `kind` and optional `required`, `default`, `values`, `value`, `of`, `fields`, `must_exist`, `unique_true`, `matches_folder`. Adding a note type means adding a schema note. Spec §6.15.
```

`system/schemas/concept.md`:
```markdown
---
type: schema
schema_for: concept
folders: ["wiki/work/", "wiki/personal/", "wiki/shared/"]
fields:
  type: {kind: const, value: concept, required: true}
  tags: {kind: list, of: string, required: true}
  compiled_at: {kind: date, required: true}
  partition: {kind: enum, values: [work, personal, shared], required: true, matches_folder: true}
  codebase: {kind: string}
  agent_owner: {kind: enum, values: [CodingAgent, SystemMaintenance, Optimus]}
  is_friction: {kind: bool, default: "false"}
  status: {kind: enum, values: [canonical, draft, deprecated], default: canonical}
  supersedes: {kind: list, of: link}
  superseded_by: {kind: link}
  aliases: {kind: list, of: string}
  sources: {kind: list, of: link}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Concept
An evergreen, atomic knowledge node compiled from raw inputs and session digests. Retire with `status: deprecated` or supersession; never delete.
```

`system/schemas/index.md`:
```markdown
---
type: schema
schema_for: index
folders: ["wiki/"]
fields:
  type: {kind: const, value: index, required: true}
  tags: {kind: list, of: string}
---
# Index
Cross-partition entry points and dashboards (e.g. `wiki/Index.md`). Exempt from partition link walls.
```

`system/schemas/briefing.md`:
```markdown
---
type: schema
schema_for: briefing
folders: ["briefings/"]
fields:
  type: {kind: const, value: briefing, required: true}
  date: {kind: date, required: true}
  status: {kind: enum, values: [active, closed], default: active}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Briefing
The daily ledger `briefings/<date>.md`, written by `/brief`. The evening section embeds `<date>.debrief`.
```

`system/schemas/debrief.md`:
```markdown
---
type: schema
schema_for: debrief
folders: ["briefings/"]
fields:
  type: {kind: const, value: debrief, required: true}
  date: {kind: date, required: true}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Debrief
The evening debrief `briefings/<date>.debrief.md`, written by `/debrief` and embedded in the day's briefing.
```

`system/schemas/plan_gate.md`:
```markdown
---
type: schema
schema_for: plan_gate
folders: ["wiki/"]
fields:
  type: {kind: const, value: plan_gate, required: true}
  target_branch: {kind: string, required: true}
  status: {kind: enum, values: [PENDING_REVIEW, APPROVED, REJECTED], required: true}
  created_at: {kind: date, required: true}
  superpower_alignment: {kind: string}
  partition: {kind: enum, values: [work, personal, shared]}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Plan gate
An intent proposal created from `system/templates/intent-shaper.md`.
```

`system/schemas/production_error.md`:
```markdown
---
type: schema
schema_for: production_error
folders: ["raw/telemetry/"]
fields:
  type: {kind: const, value: production_error, required: true}
  service: {kind: string, required: true}
  exception: {kind: string, required: true}
  operation_id: {kind: string, required: true}
  detected_at: {kind: datetime, required: true}
  is_friction: {kind: bool, default: "false"}
  assigned_agent: {kind: enum, values: [CodingAgent, SystemMaintenance, Optimus]}
  codebase: {kind: string}
  partition: {kind: enum, values: [work, personal, shared]}
  mock: {kind: bool, default: "false"}
---
# Production error
A production exception note dropped into `raw/telemetry/`. Routed to SystemMaintenance; never ingested.
```

`system/schemas/config.md`:
```markdown
---
type: schema
schema_for: config
folders: ["system/config.md", "system/config.example.md"]
fields:
  type: {kind: const, value: config, required: true}
  timezone: {kind: timezone, required: true}
  brief_time: {kind: time, required: true}
  debrief_time: {kind: time, required: true}
  remote_mode: {kind: enum, values: [private, none, keep], required: true}
  template_remote: {kind: string}
  default_partition: {kind: enum, values: [work, personal, shared], required: true}
  digest_min_events: {kind: int, default: "5"}
  digest_min_minutes: {kind: int, default: "20"}
  recall_budget_chars: {kind: int, default: "9000"}
  preferences_enabled: {kind: bool, default: "false"}
  superpowers: {kind: list, of: string}
---
# Config
The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.
```

`system/schemas/codebase.md`:
```markdown
---
type: schema
schema_for: codebase
folders: ["system/codebases/"]
fields:
  type: {kind: const, value: codebase, required: true}
  name: {kind: string, required: true}
  path: {kind: path, required: true, must_exist: warn}
  partition: {kind: enum, values: [work, personal, shared], required: true}
  default: {kind: bool, default: "false", unique_true: true}
  stack: {kind: list, of: string}
  search_globs: {kind: list, of: string, required: true}
  layers: {kind: map, of: string}
---
# Codebase
One registered codebase, produced by `/setup` discovery and inspection. The body holds free-form notes for agents.
```

`system/schemas/session_digest.md`:
```markdown
---
type: schema
schema_for: session_digest
folders: ["raw/work/notes/", "raw/personal/notes/", "raw/shared/notes/", "raw/work/archive/", "raw/personal/archive/", "raw/shared/archive/"]
fields:
  type: {kind: const, value: session_digest, required: true}
  partition: {kind: enum, values: [work, personal, shared], required: true, matches_folder: true}
  codebase: {kind: string, required: true}
  session_id: {kind: string, required: true}
  created_at: {kind: datetime, required: true}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
  redactions: {kind: int, default: "0"}
  task_id: {kind: string}
---
# Session digest
A Soundwave digest written by the Stop hook from `last_assistant_message`. Compiled into the wiki by Wheeljack.
```

`system/schemas/preference.md`:
```markdown
---
type: schema
schema_for: preference
folders: ["wiki/work/preferences/", "wiki/personal/preferences/"]
fields:
  type: {kind: const, value: preference, required: true}
  statement: {kind: string, required: true}
  partition: {kind: enum, values: [work, personal], required: true, matches_folder: true}
  codebase: {kind: string}
  evidence: {kind: list, of: link}
  counter_evidence: {kind: list, of: link}
  supersedes: {kind: list, of: link}
  superseded_by: {kind: link}
  accepted_at: {kind: date}
  rejected_at: {kind: date}
  created_at: {kind: date}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Preference
A user correction or stated preference. Status (unconfirmed, candidate, confirmed, retired) is derived in the index, never stored. Spec §6.21.
```

- [ ] **Step 4: Rewrite the templates**

`system/templates/wiki-concept.md`:
```markdown
---
type: concept
tags: []
compiled_at: "{{date}}"
partition: "{{partition}}"
codebase: "{{codebase}}"
agent_owner: "{{agent_name}}"
status: draft
sources:
  - "[[{{source_stem}}]]"
---

# {{title}}

## Executive Summary

## Core Architecture & Context

## Interlinked Concepts
- [[Index]]

## Audit Trail
- Source Material: [[{{source_stem}}]]
```

`system/templates/daily-briefing.md`:
```markdown
---
type: briefing
date: "{{date}}"
status: "{{status}}"
---

# Daily Briefing & Operational Ledger: {{date}}

## 🌅 Morning Alignment ({{brief_time}})

### 1. Active Objectives & Context Boundaries

## 🛑 Real-Time Workflow Friction Matrix
- **Systemic Blockers**:
- **Focus Drift Analysis**:
- **Communication Debt**:

## 🌌 Evening Debriefing ({{debrief_time}})

![[{{date}}.debrief]]
```

`system/templates/daily-debrief.md`:
```markdown
---
type: debrief
date: "{{date}}"
---

# Evening Debrief: {{date}}

### 1. Execution Logs & Results

### 2. System State Deltas
```

`system/templates/intent-shaper.md`:
```markdown
---
type: plan_gate
target_branch: "{{branch_name}}"
status: PENDING_REVIEW
created_at: "{{date}}"
superpower_alignment: "{{strategic_focus}}"
partition: "{{partition}}"
---

# Intent Proposal: {{short_feature_description}}

## ⚡ Superpowers & Strategic Framework Alignment
- **Core Alignment**:
- **Business Value Anchor**:

## 🧠 Brainstorming Architecture & Written Plans
- **Upstream Strategy Node**: [[{{strategic_planning_note}}]]
- **Architectural Constraints**:

## 🛠️ Proposed File Mutations & Execution Tools

| File Path | Action (Modify/Create/Delete) | Reason for Change |
|-----------|-------------------------------|-------------------|

## 🧪 Verification Strategy
- **Vault checks**: `system/scripts/lint_vault.sh`
- **Planned Coverage Target**:

## 🛑 Downstream Impact & Risk Radii
```

- [ ] **Step 5: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_schema_notes.py -q`
Expected: all tests pass.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest system/tests/python -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add system/schemas system/templates system/tests/python/test_schema_notes.py
git commit -m "feat(ark): add schema notes and schema-valid templates

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Link and tag extraction and resolution

**Files:**
- Create: `system/scripts/vaultlib/links.py`
- Test: `system/tests/python/test_links.py`

**Interfaces:**
- Produces:
  - `@dataclass Link(target_raw: str, target: str | None, line: int, kind: str)` — `kind` is `link`, `embed`, `md` or `frontmatter:<field>`; `target` is `None` for a self link.
  - `wiki_target(raw: str) -> str | None`
  - `extract(body: str, body_line: int) -> tuple[list[Link], set[str]]`
  - `class Resolver(files: Iterable[str])` with `resolve(target: str | None, src: str, kind: str, prefer: Callable[[str], tuple]) -> tuple[str | None, bool]` (`kind` is `"md"` or `"wiki"`; returns `(path, ambiguous)`).

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_links.py`:
```python
from vaultlib import links


def ex(body):
    found, tags = links.extract(body, 10)
    return [(l.target, l.kind, l.line) for l in found], tags


def test_wikilink_forms():
    found, _ = ex("[[A]] [[B|alias]] [[C#Heading]] [[D#^block]] ![[E]] [[#Local]]")
    assert found == [("A", "link", 10), ("B", "link", 10), ("C", "link", 10),
                     ("D", "link", 10), ("E", "embed", 10), (None, "link", 10)]


def test_markdown_links_skip_urls_and_anchors():
    found, _ = ex("[x](notes/a.md) [y](https://example.com) [z](#top) [w](mailto:a@b)")
    assert found == [("notes/a.md", "md", 10)]


def test_code_is_ignored():
    body = "```\n[[InFence]]\n```\n`[[Inline]]` [[Real]]\n~~~\n#notatag\n~~~"
    found, tags = ex(body)
    assert found == [("Real", "link", 13)]
    assert tags == set()


def test_tags():
    _, tags = ex("Some #alpha and #beta/gamma, not a#b or # heading or url#frag")
    assert tags == {"alpha", "beta/gamma"}


def prefer_none(path):
    return (len(path), path)


def test_case_insensitive_basename():
    r = links.Resolver(["wiki/work/concepts/Kafka.md"])
    assert r.resolve("kafka", "wiki/Index.md", "wiki", prefer_none) == ("wiki/work/concepts/Kafka.md", False)


def test_path_target_and_extension():
    r = links.Resolver(["wiki/work/A.md", "raw/archive/report.pdf"])
    assert r.resolve("wiki/work/A", "x.md", "wiki", prefer_none)[0] == "wiki/work/A.md"
    assert r.resolve("report.pdf", "x.md", "wiki", prefer_none)[0] == "raw/archive/report.pdf"
    assert r.resolve("Missing", "x.md", "wiki", prefer_none) == (None, False)


def test_dotted_basename():
    r = links.Resolver(["briefings/2026-09-30.debrief.md"])
    assert r.resolve("2026-09-30.debrief", "briefings/2026-09-30.md", "wiki", prefer_none)[0] == "briefings/2026-09-30.debrief.md"


def test_markdown_relative_resolution():
    r = links.Resolver(["wiki/work/b/B.md"])
    assert r.resolve("b/B.md", "wiki/work/A.md", "md", prefer_none)[0] == "wiki/work/b/B.md"
    assert r.resolve("../nope.md", "wiki/work/A.md", "md", prefer_none)[0] is None


def test_self_link():
    r = links.Resolver([])
    assert r.resolve(None, "wiki/A.md", "wiki", prefer_none) == ("wiki/A.md", False)


def test_ambiguity_uses_prefer():
    r = links.Resolver(["wiki/work/X.md", "wiki/personal/X.md"])
    hit, amb = r.resolve("X", "wiki/personal/Y.md", "wiki", lambda p: (0 if "/personal/" in p else 1, p))
    assert (hit, amb) == ("wiki/personal/X.md", True)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_links.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

`system/scripts/vaultlib/links.py`:
```python
"""Wikilink, markdown-link and tag extraction and resolution (spec §6.16)."""
import posixpath
import re
from dataclasses import dataclass

WIKI = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
MD = re.compile(r"(?<![!\]])\[[^\]\n]*\]\(([^)\s]+)\)")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
TAG = re.compile(r"(?<![\w/&#\]])#([A-Za-z][\w/-]*)")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE = re.compile(r"`[^`\n]*`")


@dataclass
class Link:
    target_raw: str
    target: str | None
    line: int
    kind: str


def code_free_lines(body: str, body_line: int):
    """Yield (line_number, text) with fenced blocks dropped and inline code removed."""
    fence = None
    for i, line in enumerate(body.split("\n")):
        match = FENCE.match(line)
        if match:
            if fence is None:
                fence = match.group(1)
            elif match.group(1) == fence:
                fence = None
            continue
        if fence is None:
            yield body_line + i, INLINE.sub("", line)


def wiki_target(raw: str) -> str | None:
    """'A|alias' -> 'A'; 'A#h' -> 'A'; '#h' -> None (self link)."""
    name = raw.split("|", 1)[0].split("#", 1)[0].strip()
    return name or None


def extract(body: str, body_line: int):
    """Return (links, tags) from a note body, ignoring code."""
    found, tags = [], set()
    for lineno, line in code_free_lines(body, body_line):
        for m in WIKI.finditer(line):
            found.append(Link(m.group(2), wiki_target(m.group(2)), lineno, "embed" if m.group(1) else "link"))
        for m in MD.finditer(line):
            href = m.group(1)
            if SCHEME.match(href) or href.startswith("#"):
                continue
            found.append(Link(href, href.split("#", 1)[0] or None, lineno, "md"))
        for m in TAG.finditer(line):
            tags.add(m.group(1))
    return found, tags


class Resolver:
    """Resolve link targets against the set of vault files, Obsidian-style."""

    def __init__(self, files):
        self.by_lower = {}
        self.by_name = {}
        for path in files:
            self.by_lower.setdefault(path.lower(), path)
            base = posixpath.basename(path).lower()
            self.by_name.setdefault(base, []).append(path)
            if base.endswith(".md"):
                self.by_name.setdefault(base[:-3], []).append(path)

    def resolve(self, target, src, kind, prefer):
        if target is None:
            return src, False
        if kind == "md":
            joined = posixpath.normpath(posixpath.join(posixpath.dirname(src), target))
            return self.by_lower.get(joined.lower()), False
        name = target.strip().lstrip("/")
        if "/" in name:
            candidates = [name] if posixpath.splitext(name)[1] else [name + ".md", name]
            for candidate in candidates:
                hit = self.by_lower.get(candidate.lower())
                if hit:
                    return hit, False
            return None, False
        options = sorted(set(self.by_name.get(name.lower(), [])))
        if not options:
            return None, False
        if len(options) == 1:
            return options[0], False
        options.sort(key=prefer)
        return options[0], True
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_links.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/links.py system/tests/python/test_links.py
git commit -m "feat(ark): add code-aware link and tag extraction and resolver

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Index core — tables, locked incremental refresh, link resolution

**Files:**
- Create: `system/scripts/vaultlib/index.py`
- Test: `system/tests/python/test_index.py`

**Interfaces:**
- Consumes: `frontmatter.parse/key_line`, `schema.load_schemas/validate_note/path_partition/link_target/Context`, `links.extract/Resolver/Link/wiki_target`.
- Produces: `class Index(vault: Path, db_path: Path | None = None)` with `refresh(timeout: float | None = None, full: bool = False) -> None`, `connect() -> sqlite3.Connection`, `locked(timeout)` context manager, attributes `db_path`, `vault`. Tables per spec §6.16 plus `files` and column `issues.scope` (`note`|`global`); `links.target` (normalized name) and `links.kind` values `link|embed|md|frontmatter:<field>`. Module function `first_heading(body) -> str | None`. Task 9 adds `_global_issues` and `_views` as methods on the same class.

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_index.py`:
```python
import os
import sqlite3
import threading
import time

import pytest

from helpers import concept, write
from vaultlib.index import Index


def rows(idx, sql, *args):
    conn = sqlite3.connect(idx.db_path)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def test_first_build_populates_tables(vault):
    idx = Index(vault)
    idx.refresh()
    paths = {p for (p,) in rows(idx, "SELECT path FROM notes")}
    assert "wiki/work/concepts/Kafka.md" in paths and "wiki/Index.md" in paths
    assert rows(idx, "SELECT title, partition, type FROM notes WHERE path='wiki/work/concepts/Kafka.md'") == [("Kafka", "work", "concept")]
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/Kafka.md'") == [("wiki/shared/concepts/Git.md",)]
    assert ("streaming",) in rows(idx, "SELECT tag FROM tags WHERE path='wiki/work/concepts/Kafka.md'")
    assert rows(idx, "SELECT path FROM notes_fts WHERE notes_fts MATCH 'commit'") == [("wiki/work/concepts/Kafka.md",)]


def test_unchanged_refresh_parses_nothing(vault, monkeypatch):
    idx = Index(vault)
    idx.refresh()
    calls = []
    original = Index._index_note
    monkeypatch.setattr(Index, "_index_note", lambda self, *a: calls.append(a) or original(self, *a))
    idx.refresh()
    assert calls == []


def test_edit_reparses_only_that_note(vault, monkeypatch):
    idx = Index(vault)
    idx.refresh()
    calls = []
    original = Index._index_note
    monkeypatch.setattr(Index, "_index_note", lambda self, conn, schemas, rel, *a: calls.append(rel) or original(self, conn, schemas, rel, *a))
    write(vault, "wiki/work/concepts/Kafka.md", concept("work", "Kafka", "rewritten body"))
    idx.refresh()
    assert calls == ["wiki/work/concepts/Kafka.md"]
    assert rows(idx, "SELECT path FROM notes_fts WHERE notes_fts MATCH 'rewritten'") == [("wiki/work/concepts/Kafka.md",)]


def test_refresh_detects_same_size_edit(vault):
    idx = Index(vault)
    path = write(vault, "wiki/work/concepts/Same.md", concept("work", "Same", "aaaa"))
    idx.refresh()
    path.write_text(concept("work", "Same", "bbbb"), encoding="utf-8")
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1000))
    idx.refresh()
    assert rows(idx, "SELECT path FROM notes_fts WHERE notes_fts MATCH 'bbbb'") == [("wiki/work/concepts/Same.md",)]


def test_delete_removes_rows_and_kills_inbound_links(vault):
    idx = Index(vault)
    idx.refresh()
    (vault / "wiki/shared/concepts/Git.md").unlink()
    idx.refresh()
    assert rows(idx, "SELECT count(*) FROM notes WHERE path='wiki/shared/concepts/Git.md'") == [(0,)]
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/Kafka.md'") == [(None,)]


def test_new_file_resolves_previously_dead_link(vault):
    idx = Index(vault)
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", "see [[Later]]"))
    idx.refresh()
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/A.md'") == [(None,)]
    write(vault, "wiki/work/concepts/Later.md", concept("work", "Later"))
    idx.refresh()
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/A.md'") == [("wiki/work/concepts/Later.md",)]


def test_schema_change_triggers_full_rebuild(vault):
    idx = Index(vault)
    idx.refresh()
    schema_file = vault / "system/schemas/index.md"
    schema_file.write_text(schema_file.read_text() + "\nedited\n")
    idx.refresh()
    assert rows(idx, "SELECT count(*) FROM notes")[0][0] >= 4


def test_corrupt_db_is_rebuilt(vault):
    idx = Index(vault)
    idx.refresh()
    idx.db_path.write_bytes(b"not a database at all" * 100)
    for suffix in ("-wal", "-shm"):
        p = idx.db_path.with_name(idx.db_path.name + suffix)
        if p.exists():
            p.unlink()
    idx.refresh()
    assert rows(idx, "SELECT count(*) FROM notes")[0][0] >= 4


def test_plain_markdown_note_is_an_error_not_a_crash(vault):
    write(vault, "wiki/work/concepts/Plain.md", "# Plain\njust text")
    idx = Index(vault)
    idx.refresh()
    assert rows(idx, "SELECT code FROM issues WHERE path='wiki/work/concepts/Plain.md' AND severity='error'") == [("frontmatter",)]
    assert rows(idx, "SELECT count(*) FROM notes WHERE path='wiki/work/concepts/Kafka.md'") == [(1,)]


def test_excluded_folders_not_indexed_but_resolvable(vault):
    write(vault, "raw/archive/source-note.md", "raw text")
    write(vault, "system/logs/alerts_2026-09-30.md", "# alert")
    write(vault, "wiki/work/concepts/B.md", concept("work", "B", "from [[source-note]]"))
    idx = Index(vault)
    idx.refresh()
    indexed = {p for (p,) in rows(idx, "SELECT path FROM notes")}
    assert "raw/archive/source-note.md" not in indexed and "system/logs/alerts_2026-09-30.md" not in indexed
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/B.md'") == [("raw/archive/source-note.md",)]


def test_dot_directories_pruned(vault):
    write(vault, "wiki/.staging/run1/wiki/work/concepts/S.md", concept("work", "S"))
    idx = Index(vault)
    idx.refresh()
    assert rows(idx, "SELECT count(*) FROM notes WHERE path LIKE 'wiki/.staging/%'") == [(0,)]


def test_concurrent_refresh_serializes(vault):
    idx = Index(vault)
    errors = []

    def worker():
        try:
            Index(vault).refresh(timeout=10)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert rows(idx, "SELECT count(*) FROM notes WHERE path='wiki/Index.md'") == [(1,)]


def test_lock_timeout(vault):
    idx = Index(vault)
    with idx.locked():
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            Index(vault).refresh(timeout=0.2)
        assert time.monotonic() - start < 2
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_index.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

`system/scripts/vaultlib/index.py`:
```python
"""SQLite index over the vault (spec §6.16): locked incremental refresh, issues, views."""
import contextlib
import fcntl
import hashlib
import json
import os
import posixpath
import sqlite3
import time
from pathlib import Path

from . import frontmatter, links as linkmod, schema as schemamod

INDEX_VERSION = "1"
PRUNE = {".git", ".obsidian"}
NOT_INDEXED = ("system/logs/", "system/quarantine/", "system/fleet/", "system/templates/",
               "system/tests/", "docs/", "raw/inbox/", "raw/archive/")
SKIP_FILES = ("system/index.db", "system/index.lock")
TABLES = ("files", "notes", "fields", "links", "tags", "issues", "notes_fts")

DDL = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime REAL, size INTEGER);
CREATE TABLE IF NOT EXISTS notes(path TEXT PRIMARY KEY, type TEXT, title TEXT, folder TEXT,
  partition TEXT, mtime REAL, size INTEGER, sha256 TEXT, valid INTEGER, active INTEGER, body_line INTEGER);
CREATE TABLE IF NOT EXISTS fields(path TEXT, key TEXT, value TEXT);
CREATE INDEX IF NOT EXISTS fields_path ON fields(path);
CREATE INDEX IF NOT EXISTS fields_key ON fields(key, value);
CREATE TABLE IF NOT EXISTS links(src TEXT, target_raw TEXT, target TEXT, target_path TEXT,
  line INTEGER, kind TEXT, ambiguous INTEGER);
CREATE INDEX IF NOT EXISTS links_src ON links(src);
CREATE INDEX IF NOT EXISTS links_target ON links(target_path);
CREATE TABLE IF NOT EXISTS tags(path TEXT, tag TEXT);
CREATE TABLE IF NOT EXISTS issues(path TEXT, line INTEGER, severity TEXT, code TEXT, message TEXT, scope TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(path UNINDEXED, title, aliases, body);
"""


def first_heading(body: str) -> str | None:
    for line in body.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return None


class Index:
    def __init__(self, vault, db_path=None):
        self.vault = Path(vault)
        self.db_path = Path(db_path) if db_path else self.vault / "system" / "index.db"
        self.lock_path = self.vault / "system" / "index.lock"
        self.ctx = schemamod.Context(self.vault)

    @contextlib.contextmanager
    def locked(self, timeout=None):
        """Exclusive fcntl lock on system/index.lock (released by the kernel on crash)."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a") as handle:
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TimeoutError("index lock busy")
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(DDL)
        return conn

    def _open_or_rebuild(self) -> sqlite3.Connection:
        try:
            conn = self.connect()
            conn.execute("SELECT count(*) FROM meta").fetchone()
            return conn
        except sqlite3.DatabaseError:
            for suffix in ("", "-wal", "-shm"):
                with contextlib.suppress(FileNotFoundError):
                    os.remove(f"{self.db_path}{suffix}")
            return self.connect()

    def schema_hash(self) -> str:
        digest = hashlib.sha256(INDEX_VERSION.encode())
        for path in sorted((self.vault / "system" / "schemas").glob("*.md")):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def walk(self):
        """Yield (rel, abs_path, stat) for every vault file, pruning dot-directories."""
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in PRUNE]
            for name in files:
                if name.startswith("."):
                    continue
                path = Path(root) / name
                rel = path.relative_to(self.vault).as_posix()
                if rel.startswith(SKIP_FILES):
                    continue
                try:
                    yield rel, path, path.stat()
                except FileNotFoundError:
                    continue

    def refresh(self, timeout=None, full=False) -> None:
        with self.locked(timeout):
            conn = self._open_or_rebuild()
            try:
                with conn:
                    self._refresh(conn, full)
            finally:
                conn.close()

    def _refresh(self, conn, full):
        schemas = schemamod.load_schemas(self.vault)
        shash = self.schema_hash()
        row = conn.execute("SELECT value FROM meta WHERE key='schema_hash'").fetchone()
        rebuild = full or row is None or row[0] != shash
        if rebuild:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
        old = {p: (m, s) for p, m, s in conn.execute("SELECT path, mtime, size FROM files")}
        seen = {}
        changed = rebuild
        for rel, path, st in self.walk():
            seen[rel] = (st.st_mtime, st.st_size)
            if old.get(rel) != seen[rel]:
                changed = True
                if rel.endswith(".md") and not rel.startswith(NOT_INDEXED):
                    self._index_note(conn, schemas, rel, path, st)
        for rel in set(old) - set(seen):
            changed = True
            self._drop_note(conn, rel)
        if not changed:
            return
        conn.execute("DELETE FROM files")
        conn.executemany("INSERT INTO files VALUES(?,?,?)", [(p, m, s) for p, (m, s) in seen.items()])
        self._resolve_links(conn, set(seen))
        self._global_issues(conn, schemas)
        self._views(conn, schemas)
        conn.execute("INSERT OR REPLACE INTO meta VALUES('schema_hash', ?)", (shash,))
        conn.execute("INSERT OR REPLACE INTO meta VALUES('built_at', ?)", (str(time.time()),))

    def _drop_note(self, conn, rel):
        for sql in ("DELETE FROM notes WHERE path=?", "DELETE FROM fields WHERE path=?",
                    "DELETE FROM links WHERE src=?", "DELETE FROM tags WHERE path=?",
                    "DELETE FROM issues WHERE path=? AND scope='note'", "DELETE FROM notes_fts WHERE path=?"):
            conn.execute(sql, (rel,))

    def _index_note(self, conn, schemas, rel, path, st):
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        prev = conn.execute("SELECT sha256 FROM notes WHERE path=?", (rel,)).fetchone()
        if prev and prev[0] == sha:
            conn.execute("UPDATE notes SET mtime=?, size=? WHERE path=?", (st.st_mtime, st.st_size, rel))
            return
        self._drop_note(conn, rel)
        note = frontmatter.parse(data.decode("utf-8", errors="replace"))
        ntype, issues = schemamod.validate_note(schemas, rel, note, self.ctx)
        fm = note.data or {}
        if ntype is None and isinstance(fm.get("type"), str):
            ntype = fm["type"]
        title = first_heading(note.body) or Path(rel).stem
        inactive = (fm.get("status") == "deprecated" or schemamod.link_target(fm.get("superseded_by"))
                    or bool(fm.get("rejected_at")))
        valid = 0 if any(i.severity == "error" for i in issues) else 1
        conn.execute("INSERT INTO notes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (rel, ntype, title, posixpath.dirname(rel), schemamod.path_partition(rel),
                      st.st_mtime, st.st_size, sha, valid, 0 if inactive else 1, note.body_line))
        for key, value in fm.items():
            conn.execute("INSERT INTO fields VALUES(?,?,?)",
                         (rel, str(key), value if isinstance(value, str) else json.dumps(value)))
        body_links, tags = linkmod.extract(note.body, note.body_line)
        for link in body_links + self._frontmatter_links(schemas.get(ntype), note):
            conn.execute("INSERT INTO links VALUES(?,?,?,?,?,?,?)",
                         (rel, link.target_raw, link.target, None, link.line, link.kind, 0))
        fm_tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
        for tag in {str(t) for t in fm_tags} | tags:
            conn.execute("INSERT INTO tags VALUES(?,?)", (rel, tag))
        aliases = fm.get("aliases") if isinstance(fm.get("aliases"), list) else []
        conn.execute("INSERT INTO notes_fts(path, title, aliases, body) VALUES(?,?,?,?)",
                     (rel, title, " ".join(map(str, aliases)), note.body))
        for issue in issues:
            conn.execute("INSERT INTO issues VALUES(?,?,?,?,?,'note')",
                         (issue.path, issue.line, issue.severity, issue.code, issue.message))

    def _frontmatter_links(self, sch, note):
        out = []
        if sch is None or note.data is None:
            return out
        for name, spec in sch.fields.items():
            if name not in note.data:
                continue
            value = note.data[name]
            if spec.kind == "link":
                items = [value]
            elif spec.kind == "list" and spec.of and spec.of.kind == "link" and isinstance(value, list):
                items = value
            else:
                continue
            for item in items:
                target = schemamod.link_target(item)
                if target:
                    out.append(linkmod.Link(f"[[{target}]]", linkmod.wiki_target(target),
                                            frontmatter.key_line(note, name), f"frontmatter:{name}"))
        return out

    def _resolve_links(self, conn, files):
        meta = {p: (part, act) for p, part, act in conn.execute("SELECT path, partition, active FROM notes")}
        resolver = linkmod.Resolver(files)
        for rowid, src, target, kind in conn.execute("SELECT rowid, src, target, kind FROM links").fetchall():
            src_part = schemamod.path_partition(src)
            src_dir = posixpath.dirname(src)

            def prefer(candidate, src_part=src_part, src_dir=src_dir):
                part, active = meta.get(candidate, (schemamod.path_partition(candidate), 1))
                part_rank = 0 if part == src_part else (1 if part == "shared" else 2)
                return (0 if active else 1, part_rank, 0 if posixpath.dirname(candidate) == src_dir else 1,
                        len(candidate), candidate)

            hit, ambiguous = resolver.resolve(target, src, "md" if kind == "md" else "wiki", prefer)
            conn.execute("UPDATE links SET target_path=?, ambiguous=? WHERE rowid=?",
                         (hit, 1 if ambiguous else 0, rowid))

    def _global_issues(self, conn, schemas):
        """Implemented in Task 9."""
        conn.execute("DELETE FROM issues WHERE scope='global'")

    def _views(self, conn, schemas):
        """Implemented in Task 9."""
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_index.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/index.py system/tests/python/test_index.py
git commit -m "feat(ark): add locked incremental SQLite index with link resolution

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Global issues (walls, lifecycle, uniqueness, orphans) and views

**Files:**
- Modify: `system/scripts/vaultlib/index.py` (replace the `_global_issues` and `_views` stubs; add `wall_blocked`, `_supersession_issues`)
- Test: `system/tests/python/test_index_rules.py`

**Interfaces:**
- Consumes: Task 8 `Index`.
- Produces: issue codes `dead-link`, `ambiguous-link`, `link-to-inactive`, `partition-wall`, `unique-true`, `supersession-dangling`, `supersession-partition`, `supersession-pair`, `supersession-cycle`, `orphan` (all `scope='global'`); views `v_<type>_all` (all notes of a type, with `active`) and `v_<type>` (active only), columns `path, title, partition` + one per field (`bool` → 0/1, `int` → INTEGER, defaults applied); `wall_blocked(p: str, q: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_index_rules.py`:
```python
import sqlite3

from helpers import concept, write
from vaultlib.index import Index, wall_blocked


def build(vault):
    idx = Index(vault)
    idx.refresh()
    return idx


def issues(idx, code=None):
    conn = sqlite3.connect(idx.db_path)
    try:
        sql = "SELECT path, severity, code FROM issues"
        rows = conn.execute(sql + (" WHERE code=?" if code else ""), ((code,) if code else ())).fetchall()
        return sorted(rows)
    finally:
        conn.close()


def query(idx, sql):
    conn = sqlite3.connect(idx.db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_fixture_vault_is_clean(vault):
    assert [i for i in issues(build(vault)) if i[1] == "error"] == []


def test_dead_link_is_warning(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", "[[Nowhere]] [[Index]]"))
    assert issues(build(vault), "dead-link") == [("wiki/work/concepts/A.md", "warning", "dead-link")]


def test_wall_matrix():
    assert wall_blocked("work", "personal") and wall_blocked("personal", "work")
    assert wall_blocked("shared", "work") and wall_blocked("shared", "personal")
    assert not wall_blocked("work", "shared") and not wall_blocked("personal", "shared")
    assert not wall_blocked("work", "work")


def test_partition_walls(vault):
    write(vault, "wiki/work/concepts/W.md", concept("work", "W", "[[Gardening]]"))
    write(vault, "wiki/shared/concepts/S.md", concept("shared", "S", "[[Kafka]]"))
    write(vault, "wiki/personal/concepts/P.md", concept("personal", "P", "[[Git]]"))
    found = issues(build(vault), "partition-wall")
    assert found == [("wiki/shared/concepts/S.md", "error", "partition-wall"),
                     ("wiki/work/concepts/W.md", "error", "partition-wall")]


def test_index_and_briefings_exempt_from_walls(vault):
    write(vault, "briefings/2026-09-30.md", '---\ntype: briefing\ndate: "2026-09-30"\n---\n[[Kafka]] [[Gardening]]')
    assert issues(build(vault), "partition-wall") == []


def test_ambiguous_link_prefers_partition(vault):
    write(vault, "wiki/work/concepts/Dup.md", concept("work", "Dup"))
    write(vault, "wiki/personal/concepts/Dup.md", concept("personal", "Dup"))
    write(vault, "wiki/personal/concepts/User.md", concept("personal", "User", "[[Dup]]"))
    idx = build(vault)
    assert query(idx, "SELECT target_path, ambiguous FROM links WHERE src='wiki/personal/concepts/User.md'") == [("wiki/personal/concepts/Dup.md", 1)]
    assert issues(idx, "partition-wall") == []


def test_ambiguous_link_prefers_active(vault):
    write(vault, "wiki/work/a/Topic.md", concept("work", "Topic", status="deprecated"))
    write(vault, "wiki/work/concepts/Topic.md", concept("work", "Topic"))
    write(vault, "wiki/work/concepts/Ref.md", concept("work", "Ref", "[[Topic]]"))
    assert query(build(vault), "SELECT target_path FROM links WHERE src='wiki/work/concepts/Ref.md'") == [("wiki/work/concepts/Topic.md",)]


def test_link_to_inactive_warns(vault):
    write(vault, "wiki/work/concepts/Old.md", concept("work", "Old", status="deprecated"))
    write(vault, "wiki/work/concepts/New.md", concept("work", "New", "[[Old]]"))
    assert ("wiki/work/concepts/New.md", "warning", "link-to-inactive") in issues(build(vault))


def test_supersession_pair_ok(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[B]]"'))
    write(vault, "wiki/work/concepts/B.md", concept("work", "B", supersedes='["[[A]]"]'))
    idx = build(vault)
    assert [i for i in issues(idx) if i[2].startswith("supersession")] == []
    assert query(idx, "SELECT active FROM notes WHERE path='wiki/work/concepts/A.md'") == [(0,)]


def test_supersession_pair_missing(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[B]]"'))
    write(vault, "wiki/work/concepts/B.md", concept("work", "B"))
    assert issues(build(vault), "supersession-pair") == [("wiki/work/concepts/A.md", "error", "supersession-pair")]


def test_supersession_dangling(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[Ghost]]"'))
    assert issues(build(vault), "supersession-dangling") == [("wiki/work/concepts/A.md", "error", "supersession-dangling")]


def test_supersession_cross_partition(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[B]]"'))
    write(vault, "wiki/shared/concepts/B.md", concept("shared", "B", supersedes='["[[A]]"]'))
    assert issues(build(vault), "supersession-partition") == [("wiki/work/concepts/A.md", "error", "supersession-partition")]


def test_supersession_cycles(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[B]]"', supersedes='["[[C]]"]'))
    write(vault, "wiki/work/concepts/B.md", concept("work", "B", superseded_by='"[[C]]"', supersedes='["[[A]]"]'))
    write(vault, "wiki/work/concepts/C.md", concept("work", "C", superseded_by='"[[A]]"', supersedes='["[[B]]"]'))
    found = {p for p, _, _ in issues(build(vault), "supersession-cycle")}
    assert found == {"wiki/work/concepts/A.md", "wiki/work/concepts/B.md", "wiki/work/concepts/C.md"}


def test_unique_true(vault):
    body = '---\ntype: codebase\nname: {n}\npath: "/tmp"\npartition: work\ndefault: "true"\nsearch_globs: ["*.py"]\n---\n'
    write(vault, "system/codebases/a.md", body.format(n="a"))
    write(vault, "system/codebases/b.md", body.format(n="b"))
    assert len(issues(build(vault), "unique-true")) == 2


def test_orphans(vault):
    write(vault, "wiki/work/concepts/Lonely.md", concept("work", "Lonely"))
    assert issues(build(vault), "orphan") == [("wiki/work/concepts/Lonely.md", "warning", "orphan")]


def test_views_typed_with_defaults(vault):
    write(vault, "wiki/work/concepts/F.md", concept("work", "F", "[[Index]]", is_friction='"true"'))
    write(vault, "wiki/work/concepts/Old.md", concept("work", "Old", status="deprecated"))
    idx = build(vault)
    assert query(idx, "SELECT is_friction, status FROM v_concept WHERE path='wiki/work/concepts/F.md'") == [(1, "canonical")]
    assert query(idx, "SELECT is_friction FROM v_concept WHERE path='wiki/work/concepts/Kafka.md'") == [(0,)]
    assert query(idx, "SELECT count(*) FROM v_concept WHERE path='wiki/work/concepts/Old.md'") == [(0,)]
    assert query(idx, "SELECT active FROM v_concept_all WHERE path='wiki/work/concepts/Old.md'") == [(0,)]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_index_rules.py -q`
Expected: FAIL with `ImportError: cannot import name 'wall_blocked'`.

- [ ] **Step 3: Implement — add module function and replace the two stub methods**

Add near the top of `index.py`, after `first_heading`:
```python
WALLS = {("work", "personal"), ("personal", "work"), ("shared", "work"), ("shared", "personal")}


def wall_blocked(src_partition: str, target_partition: str) -> bool:
    return (src_partition, target_partition) in WALLS
```

Replace `_global_issues` and `_views` in `class Index` with:
```python
    def _global_issues(self, conn, schemas):
        conn.execute("DELETE FROM issues WHERE scope='global'")

        def add(path, line, severity, code, message):
            conn.execute("INSERT INTO issues VALUES(?,?,?,?,?,'global')", (path, line, severity, code, message))

        notes = {p: (t, part, act) for p, t, part, act in
                 conn.execute("SELECT path, type, partition, active FROM notes")}
        for src, raw, target_path, line, kind, ambiguous in conn.execute(
                "SELECT src, target_raw, target_path, line, kind, ambiguous FROM links").fetchall():
            if target_path is None:
                add(src, line, "warning", "dead-link", f"dead link {raw}")
                continue
            if ambiguous:
                add(src, line, "warning", "ambiguous-link", f"ambiguous link {raw} resolved to {target_path}")
            source, target = notes.get(src), notes.get(target_path)
            if source and source[2] and target and not target[2] and target_path != src:
                add(src, line, "warning", "link-to-inactive", f"links to inactive note {target_path}")
            if src.startswith("wiki/") and source and source[0] != "index":
                p, q = schemamod.path_partition(src), schemamod.path_partition(target_path)
                if p and q and wall_blocked(p, q):
                    add(src, line, "error", "partition-wall", f"{p} note links to {q} note {target_path}")
        for sch in schemas.values():
            for fname, spec in sch.fields.items():
                if not spec.unique_true:
                    continue
                hits = conn.execute(
                    "SELECT f.path FROM fields f JOIN notes n ON n.path=f.path "
                    "WHERE n.type=? AND f.key=? AND lower(f.value)='true'", (sch.name, fname)).fetchall()
                if len(hits) > 1:
                    for (path,) in hits:
                        add(path, 1, "error", "unique-true",
                            f"{fname} is true in {len(hits)} {sch.name} notes; at most one is allowed")
        self._supersession_issues(conn, add)
        for (path,) in conn.execute(
                "SELECT n.path FROM notes n WHERE n.path LIKE 'wiki/%' AND n.active=1 "
                "AND coalesce(n.type,'') != 'index' AND NOT EXISTS "
                "(SELECT 1 FROM links l WHERE l.target_path=n.path AND l.src != n.path)").fetchall():
            add(path, 1, "warning", "orphan", "no other note links here")

    def _supersession_issues(self, conn, add):
        edges = {}
        for src, target_path, line in conn.execute(
                "SELECT src, target_path, line FROM links WHERE kind='frontmatter:superseded_by'").fetchall():
            if target_path is None:
                add(src, line, "error", "supersession-dangling", "superseded_by target does not exist")
                continue
            edges[src] = (target_path, line)
            if schemamod.path_partition(src) != schemamod.path_partition(target_path):
                add(src, line, "error", "supersession-partition", "superseded_by crosses partitions")
            back = conn.execute("SELECT 1 FROM links WHERE src=? AND kind='frontmatter:supersedes' AND target_path=?",
                                (target_path, src)).fetchone()
            if not back:
                add(src, line, "error", "supersession-pair", f"{target_path} does not list this note in supersedes")
        for start, (_, line) in edges.items():
            seen, current = {start}, edges[start][0]
            while current in edges:
                if current == start:
                    add(start, line, "error", "supersession-cycle", "superseded_by forms a cycle")
                    break
                if current in seen:
                    break
                seen.add(current)
                current = edges[current][0]

    def _views(self, conn, schemas):
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall():
            conn.execute(f'DROP VIEW IF EXISTS "{name}"')
        for sch in schemas.values():
            cols = ["n.path AS path", "n.title AS title", "n.partition AS partition"]
            for fname, spec in sch.fields.items():
                if fname in ("path", "title", "partition"):
                    continue
                value = f"(SELECT value FROM fields f WHERE f.path=n.path AND f.key='{fname}')"
                if spec.default is not None:
                    default = str(spec.default).replace("'", "''")
                    value = f"COALESCE({value}, '{default}')"
                if spec.kind == "bool":
                    value = f"CASE lower({value}) WHEN 'true' THEN 1 WHEN 'false' THEN 0 END"
                elif spec.kind == "int":
                    value = f"CAST({value} AS INTEGER)"
                cols.append(f'{value} AS "{fname}"')
            conn.execute(f'CREATE VIEW "v_{sch.name}_all" AS SELECT {", ".join(cols)}, n.active AS active '
                         f"FROM notes n WHERE n.type='{sch.name}'")
            conn.execute(f'CREATE VIEW "v_{sch.name}" AS SELECT * FROM "v_{sch.name}_all" WHERE active=1')
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/index.py system/tests/python/test_index_rules.py
git commit -m "feat(ark): add partition walls, lifecycle checks, orphans and typed views

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Guarded read-only query

**Files:**
- Create: `system/scripts/vaultlib/guard.py`
- Test: `system/tests/python/test_guard.py`

**Interfaces:**
- Produces: `guard.run_query(db_path: Path, sql: str, *, limit: int = 200, timeout: float = 2.0) -> tuple[list[str], list[tuple], bool]` (columns, rows, truncated); raises `sqlite3.DatabaseError` (incl. "not authorized", "interrupted") on rejected or aborted queries.

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_guard.py`:
```python
import sqlite3

import pytest

from vaultlib import guard
from vaultlib.index import Index


@pytest.fixture
def db(vault):
    idx = Index(vault)
    idx.refresh()
    return idx.db_path


def test_select_works(db):
    cols, rows, truncated = guard.run_query(db, "SELECT path FROM notes WHERE path='wiki/Index.md'")
    assert cols == ["path"] and rows == [("wiki/Index.md",)] and truncated is False


def test_fts_match_works(db):
    _, rows, _ = guard.run_query(db, "SELECT path FROM notes_fts WHERE notes_fts MATCH 'tomatoes'")
    assert rows == [("wiki/personal/concepts/Gardening.md",)]


def test_recursive_cte_and_table_info(db):
    assert guard.run_query(db, "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r WHERE x<3) SELECT count(*) FROM r")[1] == [(3,)]
    cols, rows, _ = guard.run_query(db, "SELECT name FROM pragma_table_info('notes')")
    assert ("path",) in rows


def test_views_work(db):
    _, rows, _ = guard.run_query(db, "SELECT path FROM v_concept WHERE partition='work'")
    assert rows == [("wiki/work/concepts/Kafka.md",)]


@pytest.mark.parametrize("sql", [
    "INSERT INTO notes(path) VALUES('x')",
    "DELETE FROM notes",
    "CREATE TABLE t(a)",
    "ATTACH DATABASE '/tmp/x.db' AS y",
    "PRAGMA journal_mode=DELETE",
    "DROP VIEW v_concept",
])
def test_writes_rejected(db, sql):
    with pytest.raises(sqlite3.DatabaseError):
        guard.run_query(db, sql)


def test_multiple_statements_rejected(db):
    with pytest.raises((sqlite3.ProgrammingError, sqlite3.DatabaseError)):
        guard.run_query(db, "SELECT 1; DELETE FROM notes")


def test_runaway_query_times_out(db):
    with pytest.raises(sqlite3.OperationalError):
        guard.run_query(db, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c", timeout=0.2)


def test_row_cap(db):
    _, rows, truncated = guard.run_query(db, "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r WHERE x<500) SELECT x FROM r", limit=10)
    assert len(rows) == 10 and truncated is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_guard.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

`system/scripts/vaultlib/guard.py`:
```python
"""Read-only, guarded SQL execution for `vault_index.py query` (spec §6.16)."""
import sqlite3
import time

ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
READ_ONLY_PRAGMAS = {"table_info", "table_xinfo"}


def _authorizer(action, arg1, arg2, _db, _source):
    if action in ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA:
        if arg1 in READ_ONLY_PRAGMAS:
            return sqlite3.SQLITE_OK
        if arg1 == "data_version" and arg2 is None:
            return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def run_query(db_path, sql, *, limit=200, timeout=2.0):
    """Run one read-only statement. Returns (columns, rows, truncated)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = 1")
        conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        deadline = time.monotonic() + timeout
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
        conn.set_authorizer(_authorizer)
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchmany(limit + 1)
        return columns, rows[:limit], len(rows) > limit
    finally:
        conn.close()
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_guard.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/guard.py system/tests/python/test_guard.py
git commit -m "feat(ark): add read-only guarded query execution

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Caller scope and retrieval

**Files:**
- Create: `system/scripts/vaultlib/scope.py`, `system/scripts/vaultlib/retrieve.py`
- Test: `system/tests/python/test_scope_retrieve.py`

**Interfaces:**
- Consumes: `frontmatter.parse`, `Index`.
- Produces:
  - `scope.git_common_dir(path) -> str | None`
  - `scope.codebases(vault: Path) -> list[dict]` (keys `name`, `path`, `partition`; excludes `example.md`)
  - `scope.caller_scope(vault: Path, cwd: Path) -> tuple[str, str | None, str | None] | None` — `("vault", None, None)`, `("codebase", name, partition)` or `None`
  - `scope.allowed_partitions(scope_tuple) -> list[str] | None` (`None` = all)
  - `retrieve.terms_for_text(text) -> list[str]`, `retrieve.terms_for_note(conn, path) -> list[str]`
  - `retrieve.related(conn, terms, *, limit=10, partitions=None, codebase=None, ntype=None, per_source=2, include_inactive=False, exclude=None) -> list[dict]` (keys `path`, `title`, `partition`, `type`, `score`)
  - `retrieve.backlinks(conn, path, partitions=None) -> list[str]`
  - `retrieve.orphans(conn) -> list[str]`
  - `retrieve.find_note(conn, vault, ref) -> str | None` (path or basename → indexed path)

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_scope_retrieve.py`:
```python
import sqlite3
import subprocess

import pytest

from helpers import concept, write
from vaultlib import retrieve, scope
from vaultlib.index import Index


def git_init(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def register(vault, name, path, partition="work"):
    write(vault, f"system/codebases/{name}.md",
          f'---\ntype: codebase\nname: {name}\npath: "{path}"\npartition: {partition}\nsearch_globs: ["*"]\n---\n')


def test_scope_vault_and_subdirectory(vault):
    assert scope.caller_scope(vault, vault) == ("vault", None, None)
    assert scope.caller_scope(vault, vault / "wiki") == ("vault", None, None)


def test_scope_codebase_and_worktree(vault, tmp_path):
    repo = git_init(tmp_path / "code")
    (repo / "f").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "f"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"], check=True)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(wt)], check=True)
    register(vault, "code", repo)
    assert scope.caller_scope(vault, repo) == ("codebase", "code", "work")
    assert scope.caller_scope(vault, wt) == ("codebase", "code", "work")


def test_scope_unregistered(vault, tmp_path):
    assert scope.caller_scope(vault, git_init(tmp_path / "other")) is None
    assert scope.caller_scope(vault, tmp_path) is None


def test_example_codebase_ignored(vault, tmp_path):
    repo = git_init(tmp_path / "code")
    write(vault, "system/codebases/example.md",
          f'---\ntype: codebase\nname: example\npath: "{repo}"\npartition: work\nsearch_globs: ["*"]\n---\n')
    assert scope.codebases(vault) == []


def test_allowed_partitions():
    assert scope.allowed_partitions(("vault", None, None)) is None
    assert scope.allowed_partitions(("codebase", "x", "work")) == ["work", "shared"]


@pytest.fixture
def conn(vault):
    write(vault, "wiki/work/concepts/Streams.md", concept("work", "Streams", "Kafka streams process events. [[Kafka]]"))
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    yield c
    c.close()


def test_related_text_ranks_and_filters(conn):
    hits = retrieve.related(conn, retrieve.terms_for_text("kafka event streaming"))
    assert hits[0]["path"] in ("wiki/work/concepts/Kafka.md", "wiki/work/concepts/Streams.md")
    personal = retrieve.related(conn, retrieve.terms_for_text("tomatoes sun"), partitions=["work", "shared"])
    assert personal == []


def test_related_path_excludes_self(conn):
    terms = retrieve.terms_for_note(conn, "wiki/work/concepts/Kafka.md")
    hits = retrieve.related(conn, terms, exclude="wiki/work/concepts/Kafka.md")
    assert "wiki/work/concepts/Kafka.md" not in [h["path"] for h in hits]


def test_related_per_source_cap(vault):
    for i in range(4):
        write(vault, f"wiki/work/concepts/N{i}.md", concept("work", f"N{i}", "zebra facts [[Index]]", sources='["[[digest-one]]"]'))
    write(vault, "raw/work/archive/digest-one.md", "x")
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    assert len(retrieve.related(c, ["zebra"], per_source=2)) == 2
    assert len(retrieve.related(c, ["zebra"], per_source=10)) == 4


def test_related_excludes_inactive(vault):
    write(vault, "wiki/work/concepts/Old.md", concept("work", "Old", "quokka", status="deprecated"))
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    assert retrieve.related(c, ["quokka"]) == []
    assert len(retrieve.related(c, ["quokka"], include_inactive=True)) == 1


def test_backlinks_and_orphans(conn):
    assert "wiki/work/concepts/Kafka.md" in retrieve.backlinks(conn, "wiki/shared/concepts/Git.md")
    assert retrieve.backlinks(conn, "wiki/shared/concepts/Git.md", partitions=["personal"]) == []
    assert "wiki/work/concepts/Streams.md" in retrieve.orphans(conn)


def test_find_note(conn, vault):
    assert retrieve.find_note(conn, vault, "kafka") == "wiki/work/concepts/Kafka.md"
    assert retrieve.find_note(conn, vault, "wiki/shared/concepts/Git.md") == "wiki/shared/concepts/Git.md"
    assert retrieve.find_note(conn, vault, "nope") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_scope_retrieve.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

`system/scripts/vaultlib/scope.py`:
```python
"""Caller scope from the working directory (spec §6.16, §6.17)."""
import os
import subprocess
from pathlib import Path

from . import frontmatter


def git_common_dir(path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return str(Path(out.stdout.strip()).resolve())


def codebases(vault) -> list:
    found = []
    for path in sorted((Path(vault) / "system" / "codebases").glob("*.md")):
        if path.name == "example.md":
            continue
        data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
        if data.get("type") != "codebase" or not isinstance(data.get("path"), str):
            continue
        found.append({"name": data.get("name") or path.stem,
                      "path": os.path.expanduser(data["path"]),
                      "partition": data.get("partition") or "work"})
    return found


def caller_scope(vault, cwd):
    vault, cwd = Path(vault).resolve(), Path(cwd).resolve()
    if cwd == vault or vault in cwd.parents:
        return ("vault", None, None)
    common = git_common_dir(cwd)
    if common:
        for cb in codebases(vault):
            if git_common_dir(cb["path"]) == common:
                return ("codebase", cb["name"], cb["partition"])
    return None


def allowed_partitions(scope_tuple):
    """None means unrestricted (vault scope)."""
    if scope_tuple and scope_tuple[0] == "codebase":
        return [scope_tuple[2], "shared"]
    return None
```

`system/scripts/vaultlib/retrieve.py`:
```python
"""Read-side helpers: related, backlinks, orphans, note lookup (spec §6.16)."""
import collections
import re
from pathlib import Path

STOP = set("""the and for with that this from into have has are was were not but you your our their its what
when where which who how why can will would should could about over under than then them they there here also
just only been being does did done use used using""".split())
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}")


def terms_for_text(text: str) -> list:
    return WORD.findall(text)


def terms_for_note(conn, path: str) -> list:
    row = conn.execute("SELECT title, aliases, body FROM notes_fts WHERE path=?", (path,)).fetchone()
    if not row:
        return []
    title, aliases, body = row
    tags = [t for (t,) in conn.execute("SELECT tag FROM tags WHERE path=?", (path,))]
    counts = collections.Counter(w.lower() for w in WORD.findall(body) if w.lower() not in STOP)
    return WORD.findall(title) + WORD.findall(aliases) + tags + [w for w, _ in counts.most_common(10)]


def fts_query(terms) -> str:
    unique = []
    for term in terms:
        term = term.lower().replace('"', "")
        if term and term not in STOP and term not in unique:
            unique.append(term)
    return " OR ".join(f'"{t}"' for t in unique[:30])


def _first_source(conn, path):
    row = conn.execute("SELECT target_path FROM links WHERE src=? AND kind='frontmatter:sources' "
                       "ORDER BY rowid LIMIT 1", (path,)).fetchone()
    return row[0] if row and row[0] else None


def related(conn, terms, *, limit=10, partitions=None, codebase=None, ntype=None,
            per_source=2, include_inactive=False, exclude=None) -> list:
    query = fts_query(terms)
    if not query:
        return []
    sql = ("SELECT n.path, n.title, n.partition, n.type, bm25(notes_fts, 0.0, 5.0, 3.0, 1.0) AS score "
           "FROM notes_fts JOIN notes n ON n.path = notes_fts.path WHERE notes_fts MATCH ?")
    args = [query]
    if not include_inactive:
        sql += " AND n.active = 1"
    if partitions is not None:
        sql += f" AND n.partition IN ({','.join('?' * len(partitions))})"
        args += list(partitions)
    if ntype:
        sql += " AND n.type = ?"
        args.append(ntype)
    if codebase:
        sql += " AND EXISTS (SELECT 1 FROM fields f WHERE f.path=n.path AND f.key='codebase' AND f.value=?)"
        args.append(codebase)
    if exclude:
        sql += " AND n.path != ?"
        args.append(exclude)
    sql += " ORDER BY score LIMIT ?"
    args.append(limit * 5)
    out, per = [], collections.Counter()
    for path, title, part, ntype_, score in conn.execute(sql, args).fetchall():
        key = _first_source(conn, path) or path
        if per[key] >= per_source:
            continue
        per[key] += 1
        out.append({"path": path, "title": title, "partition": part, "type": ntype_, "score": round(score, 4)})
        if len(out) >= limit:
            break
    return out


def backlinks(conn, path, partitions=None) -> list:
    rows = conn.execute("SELECT DISTINCT l.src, n.partition FROM links l JOIN notes n ON n.path=l.src "
                        "WHERE l.target_path=? AND l.src != ? ORDER BY l.src", (path, path)).fetchall()
    return [src for src, part in rows if partitions is None or part in partitions]


def orphans(conn) -> list:
    return [p for (p,) in conn.execute("SELECT path FROM issues WHERE code='orphan' ORDER BY path")]


def find_note(conn, vault, ref: str) -> str | None:
    ref = ref.strip()
    candidate = Path(ref)
    if candidate.is_absolute():
        try:
            ref = candidate.resolve().relative_to(Path(vault).resolve()).as_posix()
        except ValueError:
            return None
    row = conn.execute("SELECT path FROM notes WHERE lower(path)=lower(?) OR lower(path)=lower(?)",
                       (ref, ref + ".md")).fetchone()
    if row:
        return row[0]
    name = ref.lower().removesuffix(".md")
    rows = conn.execute("SELECT path, active FROM notes").fetchall()
    matches = sorted((0 if act else 1, len(p), p) for p, act in rows if Path(p).stem.lower() == name)
    return matches[0][2] if matches else None
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_scope_retrieve.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/scope.py system/scripts/vaultlib/retrieve.py system/tests/python/test_scope_retrieve.py
git commit -m "feat(ark): add caller scope and retrieval helpers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: The `vault_index.py` CLI

**Files:**
- Create: `system/scripts/vaultlib/cli.py`, `system/scripts/vault_index.py`
- Test: `system/tests/python/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `vault_index.py <subcommand>` with `query`, `related`, `show`, `backlinks`, `orphans`, `issues [--staged]`, `validate`, `field`, `set`, `rebuild`; exit codes: 0 ok, 1 errors found / not found / query rejected, 2 bad arguments or caller out of scope. `cli.set_scalar(path: Path, key: str, value: str) -> None` and `cli.get_field(data: dict, key: str)`. Later plans add `stage` and `recall` to the same subparser table.

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_cli.py`:
```python
import json
import subprocess

from helpers import concept, write


def test_issues_clean_fixture(cli):
    res = cli("issues")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "0 errors" in res.stdout


def test_issues_reports_errors(cli, vault):
    write(vault, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad")
    res = cli("issues")
    assert res.returncode == 1
    assert "wiki/work/concepts/Bad.md:2: error: missing required field tags" in res.stdout


def test_issues_json(cli):
    data = json.loads(cli("issues", "--json").stdout)
    assert data["errors"] == 0 and isinstance(data["issues"], list)


def test_issues_staged(cli, vault):
    subprocess.run(["git", "init", "-q", str(vault)], check=True)
    write(vault, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad")
    assert cli("issues", "--staged").returncode == 0
    subprocess.run(["git", "-C", str(vault), "add", "wiki/work/concepts/Bad.md"], check=True)
    assert cli("issues", "--staged").returncode == 1


def test_query_and_rejection(cli):
    res = cli("query", "SELECT path FROM notes WHERE type='index'")
    assert res.returncode == 0 and "wiki/Index.md" in res.stdout
    bad = cli("query", "DELETE FROM notes")
    assert bad.returncode == 1 and "not authorized" in bad.stderr


def test_related_text_and_json(cli):
    res = cli("related", "distributed commit log", "--json")
    hits = json.loads(res.stdout)
    assert hits[0]["path"] == "wiki/work/concepts/Kafka.md"


def test_show_and_backlinks(cli):
    assert "# Git" in cli("show", "Git").stdout
    assert "wiki/work/concepts/Kafka.md" in cli("backlinks", "Git").stdout
    assert cli("show", "Nope").returncode == 1


def test_validate(cli, vault):
    write(vault, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad")
    assert cli("validate", "wiki/work/concepts/Kafka.md").returncode == 0
    assert cli("validate", "wiki/work/concepts/Bad.md").returncode == 1


def test_field(cli, vault):
    assert cli("field", "wiki/work/concepts/Kafka.md", "partition").stdout.strip() == "work"
    assert cli("field", "wiki/work/concepts/Kafka.md", "tags").stdout.strip() == "streaming"
    assert cli("field", "wiki/work/concepts/Kafka.md", "missing").returncode == 1


def test_set_replaces_inserts_and_quotes(cli, vault):
    path = write(vault, "system/config.md",
                 '---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
                 'remote_mode: "none"   # set by setup_remote.sh\ndefault_partition: personal\n---\nbody\n')
    assert cli("set", "system/config.md", "remote_mode", "private").returncode == 0
    assert cli("set", "system/config.md", "template_remote", 'git@x:y "z".git').returncode == 0
    text = path.read_text()
    assert 'remote_mode: "private"  # set by setup_remote.sh' in text
    assert 'template_remote: "git@x:y \\"z\\".git"' in text
    assert text.endswith("---\nbody\n")


def test_set_refuses_non_scalar_and_reverts_invalid(cli, vault):
    original = (vault / "wiki/work/concepts/Kafka.md").read_text()
    assert cli("set", "wiki/work/concepts/Kafka.md", "tags", "x").returncode == 1
    assert cli("set", "wiki/work/concepts/Kafka.md", "partition", "personal").returncode == 1
    assert (vault / "wiki/work/concepts/Kafka.md").read_text() == original


def test_paths_outside_vault_rejected(cli, tmp_path):
    outside = tmp_path / "x.md"
    outside.write_text("---\na: b\n---\n")
    assert cli("field", str(outside), "a").returncode == 2


def test_cli_from_subdirectory(cli, vault):
    res = cli("field", "work/concepts/Kafka.md", "partition", cwd=vault / "wiki")
    assert res.returncode == 0 and res.stdout.strip() == "work"
    assert cli("issues", cwd=vault / "wiki").returncode == 0


def test_out_of_scope_caller(cli, tmp_path):
    res = cli("related", "kafka", cwd=tmp_path)
    assert res.returncode == 2 and "scope" in res.stderr


def test_codebase_scope_limits_partitions(cli, vault, tmp_path):
    repo = tmp_path / "code"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    write(vault, "system/codebases/code.md",
          f'---\ntype: codebase\nname: code\npath: "{repo}"\npartition: work\nsearch_globs: ["*"]\n---\n')
    assert cli("related", "tomatoes", "--json", cwd=repo).stdout.strip() == "[]"
    assert cli("show", "Gardening", cwd=repo).returncode == 1
    assert "# Git" in cli("show", "Git", cwd=repo).stdout
    assert cli("query", "SELECT 1", cwd=repo).returncode == 2
    assert cli("issues", cwd=repo).returncode == 2


def test_rebuild(cli):
    assert cli("rebuild").returncode == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_cli.py -q`
Expected: FAIL (script does not exist; non-zero exit codes).

- [ ] **Step 3: Implement the entry point**

`system/scripts/vault_index.py`:
```python
#!/usr/bin/env python3
"""The Ark: schema validation and index CLI for the Jarvis vault (spec §6.16)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.cli import main  # noqa: E402

sys.exit(main())
```
Run: `chmod +x system/scripts/vault_index.py`

- [ ] **Step 4: Implement the CLI**

`system/scripts/vaultlib/cli.py`:
```python
"""Command-line interface for vault_index.py (spec §6.16)."""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from . import frontmatter, guard, retrieve, schema as schemamod, scope as scopemod
from .index import Index

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


class UsageError(Exception):
    pass


def vault_root() -> Path:
    env = os.environ.get("VAULT_ROOT")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[3]


def inside_vault(vault: Path, arg: str) -> Path:
    path = Path(arg)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if path != vault and vault not in path.parents:
        raise UsageError(f"path is outside the vault: {arg}")
    return path


def rel(vault: Path, path: Path) -> str:
    return path.relative_to(vault).as_posix()


def require_vault_scope(sc):
    if not sc or sc[0] != "vault":
        raise UsageError("this command is only available from inside the vault (caller scope)")


def get_field(data, key):
    current = data
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def format_value(value) -> str:
    if isinstance(value, list):
        return ",".join(v if isinstance(v, str) else json.dumps(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def _trailing_comment(rest: str) -> str:
    text = rest.strip()
    if text[:1] in ('"', "'"):
        quote, i = text[0], 1
        while i < len(text):
            if quote == '"' and text[i] == "\\":
                i += 2
                continue
            if quote == "'" and text[i:i + 2] == "''":
                i += 2
                continue
            if text[i] == quote:
                break
            i += 1
        tail = text[i + 1:]
    else:
        idx = text.find(" #")
        tail = text[idx:] if idx >= 0 else ""
    tail = tail.strip()
    return f"  {tail}" if tail.startswith("#") else ""


def set_scalar(path: Path, key: str, value: str) -> None:
    """Replace or insert a top-level scalar, double-quoted; preserves comments and order."""
    lines = path.read_text(encoding="utf-8").split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        raise UsageError("file has no frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip("\r") in ("---", "...")), None)
    if end is None:
        raise UsageError("unterminated frontmatter")
    quoted = json.dumps(value, ensure_ascii=False)
    pattern = re.compile(rf"^{re.escape(key)}:(.*)$")
    for i in range(1, end):
        match = pattern.match(lines[i])
        if not match:
            continue
        rest = match.group(1)
        following = lines[i + 1] if i + 1 < end else ""
        if (rest.strip() == "" and following[:1] in (" ", "\t", "-")) or rest.strip()[:1] in ("[", "{", "|", ">"):
            raise UsageError(f"{key} is not a scalar")
        lines[i] = f"{key}: {quoted}{_trailing_comment(rest)}"
        break
    else:
        lines.insert(end, f"{key}: {quoted}")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, path)


def print_issues(rows, as_json):
    errors = sum(1 for r in rows if r[2] == "error")
    warnings = sum(1 for r in rows if r[2] == "warning")
    if as_json:
        print(json.dumps({"errors": errors, "warnings": warnings,
                          "issues": [dict(zip(("path", "line", "severity", "code", "message"), r)) for r in rows]}))
    else:
        for path, line, severity, _code, message in rows:
            print(f"{path}:{line}: {severity}: {message}")
        print(f"{errors} errors, {warnings} warnings")
    return EXIT_FAIL if errors else EXIT_OK


def staged_paths(vault: Path) -> set:
    out = subprocess.run(["git", "-C", str(vault), "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         capture_output=True, text=True)
    return set(out.stdout.split()) if out.returncode == 0 else set()


def cmd_issues(args, vault, sc):
    require_vault_scope(sc)
    idx = Index(vault)
    idx.refresh()
    conn = sqlite3.connect(idx.db_path)
    rows = conn.execute("SELECT path, line, severity, code, message FROM issues "
                        "ORDER BY severity, path, line").fetchall()
    conn.close()
    if args.staged:
        keep = staged_paths(vault)
        rows = [r for r in rows if r[0] in keep]
    return print_issues(rows, args.json)


def cmd_validate(args, vault, sc):
    require_vault_scope(sc)
    targets = {rel(vault, inside_vault(vault, f)) for f in args.files}
    idx = Index(vault)
    idx.refresh()
    conn = sqlite3.connect(idx.db_path)
    rows = [r for r in conn.execute("SELECT path, line, severity, code, message FROM issues "
                                    "ORDER BY path, line").fetchall() if r[0] in targets]
    conn.close()
    return print_issues(rows, args.json)


def cmd_query(args, vault, sc):
    require_vault_scope(sc)
    idx = Index(vault)
    idx.refresh()
    try:
        cols, rows, truncated = guard.run_query(idx.db_path, args.sql, limit=args.limit)
    except (sqlite3.DatabaseError, sqlite3.ProgrammingError) as exc:
        print(f"query rejected: {exc}", file=sys.stderr)
        return EXIT_FAIL
    if args.json:
        print(json.dumps({"columns": cols, "rows": rows, "truncated": truncated}))
    else:
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for row in rows:
            print("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
        if truncated:
            print(f"(truncated at {args.limit} rows)")
    return EXIT_OK


def _open(vault):
    idx = Index(vault)
    idx.refresh()
    return sqlite3.connect(idx.db_path)


def cmd_related(args, vault, sc):
    if sc is None:
        raise UsageError("caller is outside the vault and any registered codebase (scope)")
    allowed = scopemod.allowed_partitions(sc)
    partitions = args.partition or allowed
    if allowed is not None and args.partition:
        partitions = [p for p in args.partition if p in allowed]
    conn = _open(vault)
    note = retrieve.find_note(conn, vault, args.target) if args.target.endswith(".md") or "/" in args.target else None
    terms = retrieve.terms_for_note(conn, note) if note else retrieve.terms_for_text(args.target)
    hits = retrieve.related(conn, terms, limit=args.limit, partitions=partitions, codebase=args.codebase,
                            ntype=args.type, per_source=args.per_source,
                            include_inactive=args.include_inactive, exclude=note)
    conn.close()
    if args.json:
        print(json.dumps(hits))
    else:
        for hit in hits:
            print(f"- {hit['title']} — {hit['path']} ({hit['partition']}, {hit['type']})")
    return EXIT_OK


def _resolve_scoped(conn, vault, sc, ref):
    path = retrieve.find_note(conn, vault, ref)
    allowed = scopemod.allowed_partitions(sc)
    if path is None:
        return None
    if allowed is not None:
        part = conn.execute("SELECT partition FROM notes WHERE path=?", (path,)).fetchone()[0]
        if part not in allowed:
            return None
    return path


def cmd_show(args, vault, sc):
    if sc is None:
        raise UsageError("caller is outside the vault and any registered codebase (scope)")
    conn = _open(vault)
    path = _resolve_scoped(conn, vault, sc, args.note)
    conn.close()
    if path is None:
        print(f"not found: {args.note}", file=sys.stderr)
        return EXIT_FAIL
    sys.stdout.write((vault / path).read_text(encoding="utf-8"))
    return EXIT_OK


def cmd_backlinks(args, vault, sc):
    if sc is None:
        raise UsageError("caller is outside the vault and any registered codebase (scope)")
    conn = _open(vault)
    path = _resolve_scoped(conn, vault, sc, args.note)
    if path is None:
        conn.close()
        print(f"not found: {args.note}", file=sys.stderr)
        return EXIT_FAIL
    srcs = retrieve.backlinks(conn, path, scopemod.allowed_partitions(sc))
    conn.close()
    print(json.dumps(srcs) if args.json else "\n".join(f"- {s}" for s in srcs))
    return EXIT_OK


def cmd_orphans(args, vault, sc):
    require_vault_scope(sc)
    conn = _open(vault)
    paths = retrieve.orphans(conn)
    conn.close()
    print(json.dumps(paths) if args.json else "\n".join(f"- {p}" for p in paths))
    return EXIT_OK


def cmd_field(args, vault, sc):
    require_vault_scope(sc)
    path = inside_vault(vault, args.file)
    data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
    value = get_field(data, args.key)
    if value is None:
        return EXIT_FAIL
    print(format_value(value))
    return EXIT_OK


def cmd_set(args, vault, sc):
    require_vault_scope(sc)
    path = inside_vault(vault, args.file)
    original = path.read_text(encoding="utf-8")
    try:
        set_scalar(path, args.key, args.value)
    except UsageError as exc:
        print(f"set failed: {exc}", file=sys.stderr)
        return EXIT_FAIL
    schemas = schemamod.load_schemas(vault)
    _, issues = schemamod.validate_note(schemas, rel(vault, path), frontmatter.parse(path.read_text(encoding="utf-8")),
                                        schemamod.Context(vault))
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        path.write_text(original, encoding="utf-8")
        for issue in errors:
            print(f"{issue.path}:{issue.line}: error: {issue.message}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


def cmd_rebuild(args, vault, sc):
    require_vault_scope(sc)
    Index(vault).refresh(full=True)
    print("index rebuilt")
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(prog="vault_index.py", description="The Ark: Jarvis vault index")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, func, help_text):
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=func)
        p.add_argument("--json", action="store_true")
        return p

    p = add("issues", cmd_issues, "schema and link issues")
    p.add_argument("--staged", action="store_true")
    p = add("validate", cmd_validate, "validate specific files")
    p.add_argument("files", nargs="+")
    p = add("query", cmd_query, "read-only SQL")
    p.add_argument("sql")
    p.add_argument("--limit", type=int, default=200)
    p = add("related", cmd_related, "related notes by full-text search")
    p.add_argument("target")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--partition", nargs="+", choices=schemamod.PARTITIONS)
    p.add_argument("--codebase")
    p.add_argument("--type")
    p.add_argument("--per-source", type=int, default=2)
    p.add_argument("--include-inactive", action="store_true")
    p = add("show", cmd_show, "print one note")
    p.add_argument("note")
    p = add("backlinks", cmd_backlinks, "notes linking to a note")
    p.add_argument("note")
    add("orphans", cmd_orphans, "wiki notes with no inbound links")
    p = add("field", cmd_field, "print one frontmatter value")
    p.add_argument("file")
    p.add_argument("key")
    p = add("set", cmd_set, "set a top-level scalar (scripts only)")
    p.add_argument("file")
    p.add_argument("key")
    p.add_argument("value")
    add("rebuild", cmd_rebuild, "drop and rebuild the index")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    vault = vault_root()
    sc = scopemod.caller_scope(vault, Path.cwd())
    try:
        return args.func(args, vault, sc)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except schemamod.SchemaError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return EXIT_FAIL
    except TimeoutError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAIL
```

- [ ] **Step 5: Run to verify pass**

Run: `python3 -m pytest system/tests/python -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add system/scripts/vault_index.py system/scripts/vaultlib/cli.py system/tests/python/test_cli.py
git commit -m "feat(ark): add vault_index.py CLI with caller scope enforcement

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Linter wrapper and pre-commit hook

**Files:**
- Create: `system/scripts/lint_vault.sh`, `.githooks/pre-commit`, `system/tests/scripts.bats`

**Interfaces:**
- Consumes: `vault_index.py issues [--staged]` (exit 1 on errors).
- Produces: `system/scripts/lint_vault.sh [--staged]` (exit 0/1); `.githooks/pre-commit`. Plan 2 appends further `@test` blocks to `scripts.bats` and reuses its `setup()`.

- [ ] **Step 1: Write the failing bats tests**

`system/tests/scripts.bats`:
```bash
#!/usr/bin/env bats

setup() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  V="$BATS_TEST_TMPDIR/vault"
  unset VAULT_ROOT
  cp -r "$REPO/system/tests/fixtures/vault" "$V"
  mkdir -p "$V/system/scripts" "$V/.githooks"
  cp -r "$REPO/system/schemas" "$V/system/schemas"
  cp -r "$REPO/system/scripts/vault_index.py" "$REPO/system/scripts/vaultlib" "$REPO/system/scripts/lint_vault.sh" "$V/system/scripts/"
  cp "$REPO/.githooks/pre-commit" "$V/.githooks/pre-commit"
  git -C "$V" init -q
  git -C "$V" config user.email test@example.com
  git -C "$V" config user.name test
  git -C "$V" config core.hooksPath .githooks
}

bad_note() {
  mkdir -p "$V/wiki/work/concepts"
  printf -- '---\ntype: concept\n---\n# Bad\n' > "$V/wiki/work/concepts/Bad.md"
}

@test "lint passes on the fixture vault" {
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"0 errors"* ]]
}

@test "lint fails on a schema error" {
  bad_note
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 1 ]
  [[ "$output" == *"missing required field tags"* ]]
}

@test "dead links are warnings only" {
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work\n---\n# D\n[[Nowhere]] [[Index]]\n' > "$V/wiki/work/concepts/D.md"
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"warning: dead link [[Nowhere]]"* ]]
}

@test "--staged limits scope to staged files" {
  bad_note
  echo hi > "$V/README.txt"
  git -C "$V" add README.txt
  run "$V/system/scripts/lint_vault.sh" --staged
  [ "$status" -eq 0 ]
}

@test "hook blocks a commit with a schema error" {
  bad_note
  git -C "$V" add wiki/work/concepts/Bad.md
  run git -C "$V" commit -qm bad
  [ "$status" -ne 0 ]
}

@test "hook allows a commit with nothing lintable staged" {
  echo hi > "$V/README.txt"
  git -C "$V" add README.txt
  run git -C "$V" commit -qm readme
  [ "$status" -eq 0 ]
}

@test "hook fails loudly when the linter is missing" {
  rm "$V/system/scripts/lint_vault.sh"
  git -C "$V" add wiki/Index.md
  run git -C "$V" commit -qm index
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing or not executable"* ]]
}
```

- [ ] **Step 2: Run to verify failure**

Run: `bats system/tests/scripts.bats`
Expected: FAIL (`cp: cannot stat … lint_vault.sh` / `.githooks/pre-commit`).

- [ ] **Step 3: Implement**

`system/scripts/lint_vault.sh`:
```bash
#!/bin/bash
# Deterministic vault linter: schema errors fail, dead links warn (spec §6.8).
set -euo pipefail
VAULT_ROOT="${VAULT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$VAULT_ROOT"
args=()
if [[ "${1:-}" == "--staged" ]]; then
  args+=(--staged)
fi
exec system/scripts/vault_index.py issues "${args[@]}"
```

`.githooks/pre-commit`:
```bash
#!/bin/bash
# Jarvis pre-commit: run the deterministic linter on staged vault notes (spec §6.9).
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
lint="$root/system/scripts/lint_vault.sh"
pattern='^(wiki/|briefings/|raw/telemetry/|raw/(work|personal|shared)/|system/schemas/|system/config|system/codebases/)'
if ! git diff --cached --name-only --diff-filter=ACMR | grep -qE "$pattern"; then
  exit 0
fi
if [[ ! -x "$lint" ]]; then
  echo "pre-commit: $lint is missing or not executable" >&2
  exit 1
fi
exec "$lint" --staged
```
Run: `chmod +x system/scripts/lint_vault.sh .githooks/pre-commit`

- [ ] **Step 4: Run to verify pass**

Run: `bats system/tests/scripts.bats`
Expected: `7 tests, 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/lint_vault.sh .githooks/pre-commit system/tests/scripts.bats
git commit -m "feat: add deterministic linter wrapper and pre-commit hook

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Committed vault skeleton and integrity suite

**Files:**
- Create: `wiki/Index.md`; `.gitkeep` in `wiki/work/{concepts,entities,summaries,preferences}/`, `wiki/personal/{concepts,entities,summaries,preferences}/`, `wiki/shared/{concepts,entities,summaries}/`, `raw/inbox/`, `raw/archive/`, `raw/telemetry/`, `system/logs/`, `system/quarantine/`
- Modify: `system/tests/vault_integrity.bats` (replace the scaffold's version)

**Interfaces:**
- Consumes: the schema type list from Task 6 and the template mapping (`wiki-concept.md`→concept, `daily-briefing.md`→briefing, `daily-debrief.md`→debrief, `intent-shaper.md`→plan_gate).
- Produces: `vault_integrity.bats` that Plan 2 extends (settings files, units).

- [ ] **Step 1: Write the integrity suite (replacing the scaffold version)**

`system/tests/vault_integrity.bats`:
```bash
#!/usr/bin/env bats
# Structural checks that run anywhere (spec §12). Live service checks live in system_health.bats.

setup() {
  VAULT_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  cd "$VAULT_ROOT"
}

@test "partition folders exist" {
  for p in work personal shared; do
    [ -d "wiki/$p/concepts" ]
  done
  [ -d raw/inbox ] && [ -d raw/archive ] && [ -d raw/telemetry ]
}

@test "Index note exists" {
  [ -f wiki/Index.md ]
}

@test "vault scripts and hook are executable" {
  [ -x system/scripts/vault_index.py ]
  [ -x system/scripts/lint_vault.sh ]
  [ -x .githooks/pre-commit ]
}

@test "a schema note exists for every template type" {
  for t in wiki-concept:concept daily-briefing:briefing daily-debrief:debrief intent-shaper:plan_gate; do
    file="system/templates/${t%%:*}.md"
    type="${t##*:}"
    grep -q "^type: $type\$" "$file"
    grep -q "^schema_for: $type\$" "system/schemas/$type.md"
  done
}

@test "generated and per-user files are not tracked" {
  ! git ls-files --error-unmatch system/index.db 2>/dev/null
  ! git ls-files --error-unmatch system/config.md 2>/dev/null
}

@test "generated paths are gitignored" {
  git check-ignore -q system/index.db
  git check-ignore -q wiki/.staging/run/x.md
  git check-ignore -q system/fleet/tasks/x/status.json
  git check-ignore -q raw/inbox/note.md
  git check-ignore -q system/quarantine/x.md
}
```

- [ ] **Step 2: Run to verify failure**

Run: `bats system/tests/vault_integrity.bats`
Expected: FAIL on "partition folders exist" and "Index note exists".

- [ ] **Step 3: Create the skeleton**

```bash
for d in wiki/work/{concepts,entities,summaries,preferences} wiki/personal/{concepts,entities,summaries,preferences} \
         wiki/shared/{concepts,entities,summaries} raw/inbox raw/archive raw/telemetry system/logs system/quarantine; do
  mkdir -p "$d" && touch "$d/.gitkeep"
done
```

`wiki/Index.md`:
````markdown
---
type: index
tags: []
---
# Index

Start here. Compiled knowledge lives in `wiki/work/`, `wiki/personal/` and `wiki/shared/`. Query it with `system/scripts/vault_index.py related "<topic>"`; in Obsidian the dashboards below need the Dataview plugin.

## Friction
```dataview
TABLE partition, compiled_at
FROM "wiki"
WHERE (is_friction = true OR is_friction = "true") AND status != "deprecated"
SORT compiled_at DESC
```

## Recently compiled
```dataview
TABLE partition, codebase
FROM "wiki"
WHERE type = "concept" AND status != "deprecated"
SORT compiled_at DESC
LIMIT 20
```

## By owner
```dataview
TABLE rows.file.link AS notes
FROM "wiki"
WHERE agent_owner
GROUP BY agent_owner
```

## Written by headless runs
```dataview
LIST
FROM "wiki"
WHERE contains(provenance, "headless")
```
````

- [ ] **Step 4: Run all gating suites**

Run: `bats system/tests/vault_integrity.bats system/tests/scripts.bats && python3 -m pytest system/tests/python -q && system/scripts/lint_vault.sh`
Expected: all bats tests pass; pytest all pass; lint prints `0 errors` (warnings allowed).

If `lint_vault.sh` reports errors from scaffold-era files (for example `briefings/` or `system/templates/` content), fix only by correcting frontmatter to match the schema; do not change schemas to accommodate them.

- [ ] **Step 5: Commit**

```bash
git add wiki raw system/logs/.gitkeep system/quarantine/.gitkeep system/tests/vault_integrity.bats
git commit -m "feat: add committed vault skeleton, Index dashboards and integrity suite

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Update the roadmap status**

In `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md`, change Plan 1's status to `Complete (<date>)` and commit:
```bash
git add docs/superpowers/plans/2026-09-30-jarvis-roadmap.md
git commit -m "docs: mark plan 1 complete

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
