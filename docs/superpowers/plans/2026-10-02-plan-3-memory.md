# Plan 3: Memory (Soundwave) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sessions in the vault and in registered codebases leave short, redacted digests that intake compiles, and new sessions start with a bounded recall block. Built from four parts: the `vault_index.py recall` subcommand, the three user-level hooks (SessionStart recall, PostToolUse activity, Stop capture) with their shared library, and `install_hooks.sh`, which merges them into the user's Claude Code settings reversibly.

**Architecture:** The hooks are bash scripts under `system/hooks/`, invoked by absolute path from user settings.
- **SessionStart** freezes the session's scope (vault, a registered codebase, or out of scope) into `system/logs/memory/sessions/<sid>.json`, then prints the recall block that `vault_index.py recall` builds. That block holds the latest digests for the codebase or partition, under a 9,500-character hard cap.
- **PostToolUse** counts work events in pure bash.
- **Stop** either captures a `<vault-digest>` block from `last_assistant_message`, redacts it with `redact.py` and writes it to `raw/<partition>/notes/`, or, after enough work, blocks once with the digest request.

Digests then flow through Plan 2a's intake unchanged. `install_hooks.sh` owns only its own entries in `settings.json` and a managed `commands/digest.md`.

**Tech Stack:** bash 5, `jq`, `git`, Python 3.14 (stdlib + PyYAML; the existing `vaultlib`), pytest, bats 1.14, the `claude` CLI 2.1.x (live acceptance only).

**Spec:** `docs/superpowers/specs/2026-09-30-vault-template-design.md`. This plan implements §6.17, §6.19, §7.3a, the `recall` row of the §6.16 CLI table, and the §12 memory bullets (eligibility, activity, capture, recall, scope, install_hooks). It reuses §6.18 `redact.py` from Plan 2a. Read the spike record `docs/superpowers/spikes/2026-09-30-headless-and-hooks.md` items 10–17 first. They establish:
- the attended signal (`CLAUDE_CODE_ENTRYPOINT=cli`, `CLAUDE_CODE_SESSION_ATTENDED=1`, undocumented);
- `agent_id` as the subagent marker;
- the "Stop hook error" label;
- the 10,000-character `additionalContext` limit;
- the 44 ms cost of one `jq` call.

Conventions come from the 2a, 2b and 4a outcomes docs.

## Global Constraints

- **Hooks never fail a session.** Every failure is logged to `system/logs/memory/hooks.log`, and the hook exits 0 with no output. Each hook exits 0 at once when `JARVIS_HEADLESS=1` (§6.17).
- **Eligibility** (§6.17, spike 12):
  - no `agent_id` in the hook input;
  - `CLAUDE_CODE_ENTRYPOINT=cli`;
  - `CLAUDE_CODE_SESSION_ATTENDED=1` (skipped when `JARVIS_CREW=1`);
  - the session is in scope.
- **Scope is frozen** at the first hook that sees a session, normally SessionStart. Later hooks read it from state and never recompute, so a mid-session `cd` never moves the session.
- **The PostToolUse fast path spawns no `jq` and no Python** (spike 15; target < 30 ms). Stop target < 150 ms in scope (measured while planning: PostToolUse 4 ms, Stop 68 ms, SessionStart cold 631 ms).
- **Recall** is ≤ `recall_budget_chars` (default 9000), hard cap 9,500. It uses a 2 s index-lock timeout and falls back to the existing index. The hook adds a 3 s `timeout` on top. It is framed as vault data, never instructions (§6.17, §7.3a).
- **Partition walls:** a codebase session sees only digests of its own codebase and partition, and a vault session only its `default_partition` (§6.16, §7.3a).
- **`install_hooks.sh` touches only owned entries.** That means the three hooks, the three absolute `vault_index.py related|show|backlinks` Bash allows, and a `commands/digest.md` carrying `<!-- managed by vault: … -->`. It adds **no** `query` rule and **no** `Read(...)` rule (§6.19).
- **Never touch the real `~/.claude/` while implementing or testing.** Tests set a temporary `HOME` and unset `CLAUDE_CONFIG_DIR`; live acceptance uses a scratch `CLAUDE_CONFIG_DIR` and `claude --settings`. The user runs `install_hooks.sh` against their real settings themselves, through `/setup` in Plan 4b or by hand after reading `--dry-run`.
- **`CLAUDE.md` is not edited in this plan.** Its memory rule shipped in Plan 4a, and the user is revising its communication rules separately.
- **bats ruling R1:** no mid-test `!`, no `&&` assertion chains. Read every suite's verdict from its exit code, never through a pipe.
- **Gate:** `system/scripts/verify_setup.sh > system/logs/gate.log 2>&1; echo "exit=$?"`, then `sed -n '/===== summary/,$p' system/logs/gate.log`.
- American English. Commit trailers name the authoring model. Branch `feat/plan-3`, from `master` at 52784d7.

## Decisions made while planning

- **D1 Activity counter sidecar:** `work_events` lives in `sessions/<sid>.events` beside the state JSON, with `<sid>.eligible` and `<sid>.out` markers. PostToolUse can then increment it in pure bash. Spec §6.17 lists `work_events` inside the JSON, but rewriting JSON without `jq` is not possible within the 30 ms budget.
- **D2 Config cached per session:** `default_partition`, `timezone` and the two digest thresholds are read once, through `scope_cache.tsv`. The cache is built by a single `vault_index.py query` over `v_config` and `v_codebase`, and is rebuilt when the config or any codebase file is newer. These values are copied into the session state at freeze time, so Stop never spawns Python except `redact.py`, and only when it captures.
- **D3 Recall reads its own budget:** `recall` reads `recall_budget_chars` from config when `--budget-chars` is absent, so the hook makes one Python call, not two. `--budget-chars` stays as an override, and the value is clamped to 9,500.
- **D4 Recall scope comes from `$PWD`** (§6.16: never from arguments). `--cwd` must resolve to the same scope, or recall exits 2. The hook runs it as `cd <cwd> && …/vault_index.py recall --cwd <cwd>`.
- **D5 No preferences slot yet:** slot 1 (confirmed preferences) belongs to Plan 5 behind `preferences_enabled`, and is never rendered here. Crew sessions (`JARVIS_CREW=1`) get only that slot, so their recall is empty.
- **D6 Digest sections:** recall keeps Outcome and Follow-ups, recognized as `##` headings or bold labels, case-insensitive. A digest with neither contributes its first 400 characters.
- **D7 Ownership by pattern:** an owned entry is any hook command matching `…/system/hooks/memory_(recall|capture|activity).sh`, or a rule `Bash(/…/system/scripts/vault_index.py related|show|backlinks:*)`, whatever the vault path. A moved vault therefore re-points its entries instead of duplicating them (§6.19). The cost: one vault per machine owns the memory hooks.
- **D8 Plain paths only:** `install_hooks.sh` refuses a vault path containing spaces or shell metacharacters. Hook commands and Bash allow rules are plain strings, and a quoted rule's matching is undefined.
- **D9 Semantic restore:** `--uninstall` restores the settings *semantically* (`jq -S` equal). §12's "exactly" cannot hold byte for byte once `jq` has rewritten the file. Empty `hooks`/`permissions` containers that the install created are removed.
- **D10 `CLAUDE_CONFIG_DIR` honored** (Claude Code's own variable). The default is `~/.claude`. Live acceptance uses this to target a scratch directory.
- **D11 Hook timeouts:** SessionStart 5 s, Stop 10 s, PostToolUse 5 s in the settings entries, and `timeout 3` around recall inside the hook. The SessionStart entry has no matcher, so it fires for every source, `resume` and `clear` included. §6.17 also lists `fork`, which is not a documented SessionStart source.
- **D12 One instructions text:** `system/hooks/digest_instructions.md` is the single source for both the Stop block reason and the managed `/digest` command.
- **D13 Atomic digest writes:** a digest is written to a dotfile and then renamed, so intake, which skips dotfiles, never sees a half-written one. Names are `<YYYY-MM-DD>-<HHMM>-<sid8>-<slug>.md`, with `-2`, `-3`, … on a collision.
- **D14 Live acceptance:** a real interactive session runs in `tmux` in a throwaway vault, as spike items 10–17 did, with `claude --settings <scratch settings.json>`. The user's `~/.claude/settings.json` is never involved. If `tmux` cannot be driven, the same steps become a checklist for the user.

## Review Focus

1. **A real `~/.claude/settings.json` with other tools' hooks, matchers in several shapes, and extra keys.** Everything foreign must survive install and uninstall unchanged. A file that is not valid JSON must be refused, not repaired.
2. **A long working session.** Stop fires on every turn. It must stay fast and must not nag: one request per 5 events and 20 minutes, never two in a row, and never right after the assistant asked a question.
3. **A digest message with surrounding prose, two `<vault-digest>` blocks, or a stray closing tag.** Exactly the first complete block is captured, and the rest of the message never reaches the vault unredacted.
4. **Two terminals in the same vault, or one session in a vault and one in a codebase.** Separate state files; a concurrent cache rebuild must not corrupt `scope_cache.tsv`; digests never collide.
5. **A Claude Code upgrade that renames the undocumented attended variables.** The hooks then go silent rather than wrong. `system_health.bats` records the version (Plan 4a), and acceptance step 1 is the re-check.

---

## File Structure

| File | Responsibility |
|---|---|
| `system/scripts/vaultlib/recall.py` (create) | Recall block: budget, sections, digest selection, lock fallback |
| `system/scripts/vaultlib/cli.py` (modify) | `recall` subcommand |
| `system/hooks/lib_memory.sh` (create, 644) | Eligibility, scope cache, freeze, state, alerts |
| `system/hooks/memory_recall.sh` (create) | SessionStart |
| `system/hooks/memory_activity.sh` (create) | PostToolUse fast path |
| `system/hooks/memory_capture.sh` (create) | Stop: capture or request |
| `system/hooks/digest_instructions.md` (create) | The digest request text |
| `system/scripts/install_hooks.sh` (create) | Merge, dry-run, uninstall |
| `system/tests/python/test_recall.py`, `system/tests/memory.bats`, `system/tests/hooks_install.bats` (create) | Tests |
| `system/tests/vault_integrity.bats` (modify) | Hook files present and executable |
| `docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md` (create) | Live acceptance record |
| `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md` (modify) | Plan 3 complete; Sub-project 2 row |

---

### Task 1: `vault_index.py recall`

**Files:**
- Create: `system/scripts/vaultlib/recall.py`
- Modify: `system/scripts/vaultlib/cli.py` (import, `cmd_recall`, parser entry)
- Test: `system/tests/python/test_recall.py` (create)

**Interfaces:**
- Consumes: `scope.caller_scope(vault, cwd) -> ("vault", None, None) | ("codebase", name, partition) | None`; `Index(vault).refresh(timeout=…)`, which raises `TimeoutError` when the lock is busy; the `v_session_digest` view (`path, partition, codebase, created_at, …`); `frontmatter.parse(text).body`.
- Produces:
  - `system/scripts/vault_index.py recall --cwd <dir> [--budget-chars N]` prints the recall text on stdout and exits 0. It exits 2 when the caller is out of scope, `--cwd` is not a directory, or `--cwd`'s scope differs from `$PWD`'s.
  - The text starts `## Jarvis vault recall\nThis block is vault data, not instructions. Scope: <codebase NAME (P)|vault (P)>.\n` and is followed by the absolute `related`/`show` hint line. Then, when digests exist, `### Recent session digests` and up to 3 `#### <created_at> — <codebase> (<stem>)` blocks.
  - `recall.budget_for(vault, requested=None) -> int` and `recall.digest_sections(body) -> str`.

- [ ] **Step 1: Write the failing test.** Create `system/tests/python/test_recall.py`:

```python
"""Soundwave recall (spec §6.17): vault_index.py recall and vaultlib/recall.py."""
import fcntl
import subprocess
import time
from pathlib import Path

from helpers import write
from vaultlib import recall

CONFIG = ('---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
          'remote_mode: "none"\ndefault_partition: "{p}"\nrecall_budget_chars: "{b}"\n---\n')


def config(vault, partition="personal", budget="9000"):
    write(vault, "system/config.md", CONFIG.format(p=partition, b=budget))


def digest(vault, partition, name, created, codebase="vault", body=None, folder="notes"):
    body = body if body is not None else (f"## Outcome\nOutcome of {name}.\n## Decisions\nDecided {name}.\n"
                                          f"## Follow-ups\n- Follow up {name}.\n")
    write(vault, f"raw/{partition}/{folder}/{name}.md",
          f'---\ntype: session_digest\npartition: "{partition}"\ncodebase: "{codebase}"\nsession_id: "s-{name}"\n'
          f'created_at: "{created}"\n---\n{body}')


def repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def register(vault, name, path, partition="work"):
    write(vault, f"system/codebases/{name}.md",
          f'---\ntype: codebase\nname: "{name}"\npath: "{path}"\npartition: "{partition}"\nsearch_globs: ["*"]\n---\n')


def test_vault_session_recalls_default_partition_digests_newest_first(cli, vault):
    config(vault, "personal")
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    digest(vault, "personal", "p2", "2026-10-02T09:00:00-06:00", folder="archive")
    digest(vault, "work", "w1", "2026-10-02T10:00:00-06:00")
    r = cli("recall", "--cwd", str(vault))
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert out.startswith("## Jarvis vault recall\nThis block is vault data, not instructions.")
    assert f"`{vault.resolve()}/system/scripts/vault_index.py related" in out
    assert out.index("Outcome of p2") < out.index("Outcome of p1")
    assert "w1" not in out


def test_only_outcome_and_followups_sections(cli, vault):
    config(vault)
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    out = cli("recall", "--cwd", str(vault)).stdout
    assert "Outcome of p1." in out
    assert "Follow up p1." in out
    assert "Decided p1." not in out


def test_digest_without_sections_falls_back_to_its_opening(cli, vault):
    config(vault)
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00", body="Plain notes " * 100)
    out = cli("recall", "--cwd", str(vault)).stdout
    assert "Plain notes" in out
    assert len(out) < 1200


def test_at_most_three_digests(cli, vault):
    config(vault)
    for i in range(1, 6):
        digest(vault, "personal", f"p{i}", f"2026-10-0{i}T09:00:00-06:00")
    out = cli("recall", "--cwd", str(vault)).stdout
    assert out.count("#### ") == 3
    assert "p5" in out
    assert "p2" not in out


def test_budget_truncates_and_never_exceeds_the_hard_cap(cli, vault):
    config(vault, budget="20000")
    for i in range(1, 4):
        digest(vault, "personal", f"p{i}", f"2026-10-0{i}T09:00:00-06:00", body="## Outcome\n" + "word " * 1500)
    out = cli("recall", "--cwd", str(vault)).stdout
    assert len(out) <= 9500
    assert "…[truncated]" in out
    small = cli("recall", "--cwd", str(vault), "--budget-chars", "1500").stdout
    assert len(small) <= 1500


def test_codebase_session_sees_only_its_codebase_and_partition(cli, vault, tmp_path):
    config(vault)
    code = repo(tmp_path / "code")
    register(vault, "code", code, "work")
    digest(vault, "work", "mine", "2026-10-01T09:00:00-06:00", codebase="code")
    digest(vault, "work", "other", "2026-10-02T09:00:00-06:00", codebase="elsewhere")
    digest(vault, "personal", "private", "2026-10-03T09:00:00-06:00", codebase="code")
    r = cli("recall", "--cwd", str(code), cwd=code)
    assert r.returncode == 0, r.stderr
    assert "Scope: codebase code (work)" in r.stdout
    assert "Outcome of mine" in r.stdout
    assert "other" not in r.stdout
    assert "private" not in r.stdout


def test_personal_codebase_never_shows_work(cli, vault, tmp_path):
    config(vault, "work")
    code = repo(tmp_path / "hobby")
    register(vault, "hobby", code, "personal")
    digest(vault, "work", "job", "2026-10-01T09:00:00-06:00", codebase="hobby")
    digest(vault, "personal", "fun", "2026-10-02T09:00:00-06:00", codebase="hobby")
    out = cli("recall", "--cwd", str(code), cwd=code).stdout
    assert "Outcome of fun" in out
    assert "job" not in out


def test_out_of_scope_and_mismatched_cwd_exit_2(cli, vault, tmp_path):
    config(vault)
    stranger = repo(tmp_path / "stranger")
    assert cli("recall", "--cwd", str(stranger), cwd=stranger).returncode == 2
    assert cli("recall", "--cwd", str(stranger)).returncode == 2


def test_crew_sessions_get_no_digests(cli, vault):
    config(vault)
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    r = cli("recall", "--cwd", str(vault), env={"JARVIS_CREW": "1"})
    assert r.returncode == 0
    assert r.stdout == ""


def test_busy_index_lock_falls_back_without_refreshing(cli, vault):
    config(vault)
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    assert cli("recall", "--cwd", str(vault)).returncode == 0  # builds the index
    digest(vault, "personal", "p2", "2026-10-02T09:00:00-06:00")
    with open(vault / "system" / "index.lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        start = time.monotonic()
        r = cli("recall", "--cwd", str(vault))
        elapsed = time.monotonic() - start
    assert r.returncode == 0, r.stderr
    assert elapsed < 4
    assert "Outcome of p1" in r.stdout
    assert "p2" not in r.stdout


def test_budget_for_clamps_and_defaults(vault):
    assert recall.budget_for(vault) == 9000
    config(vault, budget="12000")
    assert recall.budget_for(vault) == 9500
    assert recall.budget_for(vault, 500) == 500
    config(vault, budget="lots")
    assert recall.budget_for(vault) == 9000


def test_digest_sections_handles_bold_headings():
    body = "**Outcome**\nShipped it.\n**Decisions**\nUsed X.\n**Follow-ups**\n- Ship more.\n"
    text = recall.digest_sections(body)
    assert "Shipped it." in text
    assert "Ship more." in text
    assert "Used X." not in text
```

- [ ] **Step 2: Run it.** `python3 -m pytest system/tests/python/test_recall.py -q > system/logs/t1.log 2>&1; echo "exit=$?"`. Expected: `exit=2`, a collection error (`cannot import name 'recall' from 'vaultlib'`).

- [ ] **Step 3: Implement the module.** Create `system/scripts/vaultlib/recall.py`:

```python
"""Soundwave recall: the bounded SessionStart block (spec §6.17)."""
import os
import re
import sqlite3
from pathlib import Path

from . import frontmatter
from .index import Index

HARD_CAP = 9500
DEFAULT_BUDGET = 9000
MAX_DIGESTS = 3
LOCK_TIMEOUT = 2.0
SECTION = re.compile(r"^\s*(?:#{1,6}\s*|\*\*)?\s*(outcome|follow[- ]?ups?)\b", re.I)
HEADING = re.compile(r"^\s*(?:#{1,6}\s+\S|\*\*[^*]+\*\*\s*:?\s*$)")


def budget_for(vault, requested=None) -> int:
    """The requested budget, else config recall_budget_chars, else 9000; never above 9500."""
    value = requested
    if value is None:
        try:
            data = frontmatter.parse((Path(vault) / "system" / "config.md").read_text(encoding="utf-8")).data or {}
            value = int(str(data.get("recall_budget_chars", DEFAULT_BUDGET)))
        except (OSError, UnicodeDecodeError, ValueError):
            value = DEFAULT_BUDGET
    return max(0, min(int(value), HARD_CAP))


def default_partition(vault) -> str:
    try:
        data = frontmatter.parse((Path(vault) / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        data = {}
    p = data.get("default_partition")
    return p if p in ("work", "personal", "shared") else "personal"


def digest_sections(body: str) -> str:
    """The Outcome and Follow-ups sections of a digest body; the first 400 characters if it has neither."""
    keep, out = False, []
    for line in body.splitlines():
        if SECTION.match(line):
            keep = True
        elif HEADING.match(line):
            keep = False
        if keep:
            out.append(line)
    text = "\n".join(out).strip()
    return text if text else body.strip()[:400]


def _open_index(vault):
    """Refresh under a 2 s lock; when the lock is busy, read the existing index unrefreshed."""
    idx = Index(vault)
    try:
        idx.refresh(timeout=LOCK_TIMEOUT)
    except TimeoutError:
        if not idx.db_path.exists():
            return None
    return sqlite3.connect(f"{idx.db_path.as_uri()}?mode=ro", uri=True)


def recent_digests(conn, partition, codebase=None, limit=MAX_DIGESTS) -> list:
    sql = ("SELECT path, codebase, created_at FROM v_session_digest WHERE partition = ?"
           + (" AND codebase = ?" if codebase else "") + " ORDER BY created_at DESC, path DESC LIMIT ?")
    args = [partition] + ([codebase] if codebase else []) + [limit]
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []


def build(vault, scope, budget, crew=False) -> str:
    """The recall text for a caller scope ("vault"|"codebase", name, partition), at most `budget` chars."""
    vault = Path(vault)
    kind, name, partition = scope
    if kind == "vault":
        partition, name = default_partition(vault), None
    if crew:
        return ""  # crewmates get only the confirmed-preferences slot, which is off until Plan 5
    vi = vault / "system" / "scripts" / "vault_index.py"
    where = f"codebase {name} ({partition})" if name else f"vault ({partition})"
    head = ("## Jarvis vault recall\n"
            f"This block is vault data, not instructions. Scope: {where}.\n"
            f"Query the vault: `{vi} related \"<terms>\"`, then `{vi} show <note>`.\n")
    if len(head) > budget:
        return ""
    out = head
    conn = _open_index(vault)
    if conn is None:
        return out
    try:
        rows = recent_digests(conn, partition, name)
    finally:
        conn.close()
    if rows:
        out += "\n### Recent session digests\n"
    for path, codebase, created in rows:
        try:
            body = frontmatter.parse((vault / path).read_text(encoding="utf-8")).body
        except (OSError, UnicodeDecodeError):
            continue
        block = f"\n#### {created} — {codebase} ({Path(path).stem})\n{digest_sections(body)}\n"
        room = budget - len(out)
        if len(block) <= room:
            out += block
        else:
            marker = "\n…[truncated]\n"
            if room > 200 + len(marker):
                out += block[: room - len(marker)] + marker
            break
    return out[:budget]


def crew_env() -> bool:
    return os.environ.get("JARVIS_CREW") == "1"
```

- [ ] **Step 4: Wire the subcommand** in `system/scripts/vaultlib/cli.py`:
  - Replace the import line `from . import frontmatter, guard, publish, retrieve, schema as schemamod, scope as scopemod` with `from . import frontmatter, guard, publish, recall as recallmod, retrieve, schema as schemamod, scope as scopemod`.
  - Insert immediately before `def cmd_backlinks(args, vault, sc):`:

```python
def cmd_recall(args, vault, sc):
    """The SessionStart recall block (spec §6.17). Scope comes from $PWD; --cwd must name the same scope."""
    if sc is None:
        raise UsageError("caller is outside the vault and any registered codebase (scope)")
    cwd = Path(args.cwd)
    if not cwd.is_dir():
        raise UsageError(f"not a directory: {args.cwd}")
    if scopemod.caller_scope(vault, cwd) != sc:
        raise UsageError("--cwd is not in the caller's scope")
    budget = recallmod.budget_for(vault, args.budget_chars)
    sys.stdout.write(recallmod.build(vault, sc, budget, crew=recallmod.crew_env()))
    return EXIT_OK


```

  - In `build_parser`, insert immediately before `    add("rebuild", cmd_rebuild, "drop and rebuild the index")`:

```python
    p = add("recall", cmd_recall, "build the SessionStart recall block")
    p.add_argument("--cwd", required=True)
    p.add_argument("--budget-chars", type=int)
```

- [ ] **Step 5: Run the tests.** `python3 -m pytest system/tests/python -q > system/logs/t1.log 2>&1; echo "exit=$?"; tail -n 1 system/logs/t1.log`. Expected: `exit=0`, `329 passed` (317 + 12).

- [ ] **Step 6: Gate.** Expected `exit=0`.

- [ ] **Step 7: Commit.** `git add system/scripts/vaultlib/recall.py system/scripts/vaultlib/cli.py system/tests/python/test_recall.py && git commit -m "feat(soundwave): add vault_index.py recall, the bounded SessionStart block"`

---

### Task 2: Hook library, SessionStart and PostToolUse

**Files:**
- Create: `system/hooks/lib_memory.sh` (mode 644), `system/hooks/memory_recall.sh`, `system/hooks/memory_activity.sh`
- Test: `system/tests/memory.bats` (create)

**Interfaces:**
- Consumes: Task 1's `recall`; `vault_index.py query --json` over `v_config` (`default_partition, timezone, digest_min_events, digest_min_minutes`, defaults applied) and `v_codebase` (`name, fm_path, partition`); `git rev-parse --git-common-dir`.
- Produces (`lib_memory.sh`):
  - **Variables:** `MEM_VAULT`, `MEM_SESSIONS`, `MEM_LOG`, `MEM_CACHE`.
  - **Checks:** `mem_valid_sid <sid>` and `mem_env_ok`.
  - **Scope:** `memory_scope <cwd>` prints `vault <p>`, `codebase <name> <p>` or nothing.
  - **Freeze:** `mem_freeze <sid> <cwd>` returns 0 iff the session is in scope. On first sight it writes `sessions/<sid>.json` = `{scope, partition, codebase, started_at, last_digest_at, awaiting_digest, tz, digest_min_events, digest_min_minutes}`, plus `<sid>.events` = `0` and `<sid>.eligible`; out of scope, `<sid>.out`.
  - **State and events:** `mem_state_set <sid> <jq filter>`, `mem_events <sid>`.
  - **Housekeeping:** `mem_alert <tz> <msg>` writes `- HH:MM:SS [soundwave] …` to `alerts_<date>.md`; `mem_log`; `mem_prune` (state older than 14 days).
- Produces (hooks):
  - `memory_recall.sh` (SessionStart) prints `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":…}}` or nothing.
  - `memory_activity.sh` (PostToolUse) increments `<sid>.events`.

- [ ] **Step 1: Write the failing tests.** Create `system/tests/memory.bats`:

```bash
#!/usr/bin/env bats
# Soundwave memory hooks (spec §6.17): eligibility, scope, activity, capture, recall.
load helpers

setup() {
  make_vault
  cp -r "$REPO/system/hooks" "$V/system/hooks"
  VP="$(cd "$V" && pwd -P)"
  H="$VP/system/hooks"
  S="$VP/system/logs/memory/sessions"
  export CLAUDE_CODE_ENTRYPOINT=cli CLAUDE_CODE_SESSION_ATTENDED=1
  unset JARVIS_HEADLESS JARVIS_CREW JARVIS_TASK_ID
  cd "$VP"
}

hook() {  # hook <script> <json>: run a hook with the JSON on stdin
  run bash -c 'printf "%s" "$2" | "$1"' _ "$H/$1" "$2"
}
start() { hook memory_recall.sh "$(jq -cn --arg s "$1" --arg c "${2:-$VP}" '{session_id: $s, cwd: $c, source: "startup", hook_event_name: "SessionStart"}')"; }
tool() { hook memory_activity.sh "$(jq -cn --arg s "$1" --arg c "${2:-$VP}" '{session_id: $s, cwd: $c, tool_name: "Edit", hook_event_name: "PostToolUse"}')"; }
stop() { hook memory_capture.sh "$(jq -cn --arg s "$1" --arg m "$2" --arg c "${3:-$VP}" '{session_id: $s, cwd: $c, last_assistant_message: $m, stop_hook_active: false}')"; }
tools() { local i; for i in $(seq 1 "$2"); do tool "$1"; done; }
thresholds() {
  system/scripts/vault_index.py set system/config.md digest_min_events "$1"
  system/scripts/vault_index.py set system/config.md digest_min_minutes "$2"
}
repo() { git init -q "$1"; git -C "$1" -c user.email=t@e -c user.name=t commit -q --allow-empty -m i; }
register() {  # register <name> <path> <partition>
  mkdir -p system/codebases
  printf -- '---\ntype: codebase\nname: "%s"\npath: "%s"\npartition: "%s"\nsearch_globs: ["*"]\n---\n' "$1" "$2" "$3" > "system/codebases/$1.md"
}
digests() { find raw -path '*/notes/*.md' -type f | sort; }

@test "eligibility: subagents, non-interactive and headless sessions are ignored" {
  hook memory_recall.sh '{"session_id":"sub-1","cwd":"'"$VP"'","agent_id":"a1"}'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ ! -e "$S/sub-1.json" ]
  CLAUDE_CODE_ENTRYPOINT=sdk-cli start p-1
  [ ! -e "$S/p-1.json" ]
  CLAUDE_CODE_SESSION_ATTENDED=0 start p-2
  [ ! -e "$S/p-2.json" ]
  JARVIS_HEADLESS=1 start p-3
  [ ! -e "$S/p-3.json" ]
  start ok-1
  [ -e "$S/ok-1.json" ]
}

@test "out of scope: exit 0, no state, no output" {
  mkdir -p "$BATS_TEST_TMPDIR/elsewhere"
  start out-1 "$BATS_TEST_TMPDIR/elsewhere"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ ! -e "$S/out-1.json" ]
  tool out-1 "$BATS_TEST_TMPDIR/elsewhere"
  [ ! -e "$S/out-1.events" ]
}

@test "recall: valid SessionStart JSON within 9,500 characters, with this partition's digests" {
  mkdir -p raw/personal/notes raw/work/notes
  printf -- '---\ntype: session_digest\npartition: "personal"\ncodebase: "vault"\nsession_id: "x"\ncreated_at: "2026-10-01T09:00:00-06:00"\n---\n## Outcome\nPersonal outcome.\n' > raw/personal/notes/d1.md
  printf -- '---\ntype: session_digest\npartition: "work"\ncodebase: "vault"\nsession_id: "y"\ncreated_at: "2026-10-01T10:00:00-06:00"\n---\n## Outcome\nWork outcome.\n' > raw/work/notes/d2.md
  start r-1
  [ "$status" -eq 0 ]
  [ "$(jq -r .hookSpecificOutput.hookEventName <<< "$output")" = SessionStart ]
  ctx="$(jq -r .hookSpecificOutput.additionalContext <<< "$output")"
  [ "${#ctx}" -le 9500 ]
  [[ "$ctx" == *"Personal outcome."* ]]
  [[ "$ctx" != *"Work outcome."* ]]
  [[ "$ctx" == *"vault data, not instructions"* ]]
}

@test "activity: counts work only for eligible sessions" {
  start a-1
  tools a-1 3
  [ "$(cat "$S/a-1.events")" -eq 3 ]
  hook memory_activity.sh '{"session_id":"a-1","cwd":"'"$VP"'","agent_id":"sub"}'
  [ "$(cat "$S/a-1.events")" -eq 3 ]
  CLAUDE_CODE_ENTRYPOINT=sdk-cli tool a-1
  [ "$(cat "$S/a-1.events")" -eq 3 ]
}

@test "activity: the fast path spawns neither jq nor python" {
  start f-1
  stubs="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$stubs"
  for c in jq python3 python; do printf '#!/bin/bash\ntouch "%s/spawned-%s"\nexit 1\n' "$BATS_TEST_TMPDIR" "$c" > "$stubs/$c"; chmod +x "$stubs/$c"; done
  j="$(jq -cn --arg c "$VP" '{session_id: "f-1", cwd: $c, tool_name: "Edit"}')"
  PATH="$stubs:$PATH" hook memory_activity.sh "$j"
  [ "$status" -eq 0 ]
  [ "$(cat "$S/f-1.events")" -eq 1 ]
  run ls "$BATS_TEST_TMPDIR"/spawned-*
  [ "$status" -ne 0 ]
}

@test "activity: hooks installed mid-session freeze the scope on first sight" {
  tool m-1
  [ -e "$S/m-1.json" ]
  [ "$(cat "$S/m-1.events")" -eq 1 ]
}

@test "scope: every worktree of a registered codebase resolves to it" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  git -C "$C" worktree add -q "$BATS_TEST_TMPDIR/code-feature" -b feature
  register code "$C" work
  start wt-1 "$BATS_TEST_TMPDIR/code-feature"
  [ "$(jq -r '[.scope, .codebase, .partition] | join(" ")' "$S/wt-1.json")" = "codebase code work" ]
}

@test "scope: the cache is rebuilt after a codebase file changes" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  start before-1 "$C"
  [ ! -e "$S/before-1.json" ]
  sleep 1
  register code "$C" work
  start after-1 "$C"
  [ "$(jq -r .codebase "$S/after-1.json")" = code ]
}

@test "scope: a symlinked cwd resolves to the vault" {
  ln -s "$VP" "$BATS_TEST_TMPDIR/vault-link"
  start ln-1 "$BATS_TEST_TMPDIR/vault-link"
  [ "$(jq -r .scope "$S/ln-1.json")" = vault ]
}
```

- [ ] **Step 2: Run them.** `bats system/tests/memory.bats > system/logs/t2.log 2>&1; echo "exit=$?"`. Expected: `exit=1`. All 9 fail in `setup`, because `cp -r "$REPO/system/hooks"` finds no such directory.

- [ ] **Step 3: Library.** Create `system/hooks/lib_memory.sh` (mode 644):

```bash
# shellcheck shell=bash
# Soundwave: shared helpers for the memory hooks (spec §6.17). Sourced by memory_*.sh.
# Hooks never fail a session: every helper returns non-zero on trouble and callers exit 0.

MEM_VAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
MEM_DIR="$MEM_VAULT/system/logs/memory"
MEM_SESSIONS="$MEM_DIR/sessions"
MEM_LOG="$MEM_DIR/hooks.log"
MEM_CACHE="$MEM_DIR/scope_cache.tsv"
mkdir -p "$MEM_SESSIONS" 2>/dev/null

mem_log() { printf '%s [soundwave] %s\n' "$(date -Iseconds)" "$1" >> "$MEM_LOG" 2>/dev/null; }

mem_valid_sid() { [[ "${1-}" =~ ^[A-Za-z0-9-]+$ ]]; }

# Interactive, attended main sessions only (spike item 12; undocumented variables, re-checked by
# system_health.bats). Crewmates (JARVIS_CREW=1) skip the attended check.
mem_env_ok() {
  [[ "${JARVIS_HEADLESS:-}" != 1 ]] || return 1
  [[ "${CLAUDE_CODE_ENTRYPOINT:-}" == cli ]] || return 1
  [[ "${JARVIS_CREW:-}" == 1 || "${CLAUDE_CODE_SESSION_ATTENDED:-}" == 1 ]]
}

_mem_vi() { (cd "$MEM_VAULT" && system/scripts/vault_index.py "$@"); }

# scope_cache.tsv: one "#config" line (default_partition, timezone, min events, min minutes), then
# "<git common dir>\t<codebase name>\t<partition>" per registered codebase. Rebuilt when the config
# or any codebase file is newer than the cache.
mem_cache_fresh() {
  local f
  [[ -s "$MEM_CACHE" ]] || return 1
  for f in "$MEM_VAULT/system/config.md" "$MEM_VAULT"/system/codebases/*.md; do
    [[ -e "$f" && "$f" -nt "$MEM_CACHE" ]] && return 1
  done
  return 0
}

mem_cache_build() {
  local cfg rows tmp line name path part common
  cfg="$(_mem_vi query --json "SELECT default_partition, timezone, digest_min_events, digest_min_minutes FROM v_config WHERE path = 'system/config.md'")" || return 1
  rows="$(_mem_vi query --json "SELECT name, fm_path, partition FROM v_codebase WHERE path != 'system/codebases/example.md'")" || return 1
  tmp="$MEM_CACHE.$$"
  jq -r '.rows[0] // ["personal", "UTC", 5, 20] | ["#config"] + map(tostring) | @tsv' <<< "$cfg" > "$tmp" || return 1
  while IFS=$'\t' read -r name path part; do
    [[ "$path" == "~/"* ]] && path="$HOME/${path#\~/}"
    common="$(git -C "$path" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || continue
    common="$(realpath -e -- "$common" 2>/dev/null)" || continue
    printf '%s\t%s\t%s\n' "$common" "$name" "$part" >> "$tmp"
  done < <(jq -r '.rows[] | map(tostring) | @tsv' <<< "$rows")
  mv -f -- "$tmp" "$MEM_CACHE"
}

mem_config() {  # prints "<default_partition> <timezone> <min_events> <min_minutes>"
  mem_cache_fresh || mem_cache_build || return 1
  awk -F'\t' '$1 == "#config" { print $2, $3, $4, $5; exit }' "$MEM_CACHE"
}

# memory_scope <cwd>: "vault <partition>", "codebase <name> <partition>", or nothing (out of scope).
memory_scope() {
  local real common
  real="$(realpath -e -- "${1-}" 2>/dev/null)" || return 1
  mem_cache_fresh || mem_cache_build || return 1
  if [[ "$real" == "$MEM_VAULT" || "$real" == "$MEM_VAULT"/* ]]; then
    awk -F'\t' '$1 == "#config" { print "vault", $2; exit }' "$MEM_CACHE"
    return 0
  fi
  common="$(git -C "$real" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
  common="$(realpath -e -- "$common" 2>/dev/null)" || return 1
  # Exactly one registration for this repo; two registrations of one repo are ambiguous (none).
  awk -F'\t' -v c="$common" '$1 == c { n++; hit = "codebase " $2 " " $3 } END { if (n == 1) print hit }' "$MEM_CACHE"
}

# mem_freeze <sid> <cwd>: freeze the session's scope on first sight (SessionStart, or the first hook
# that sees a session started before the hooks were installed). Returns 0 iff the session is in scope.
mem_freeze() {
  local sid="$1" cwd="$2" st="$MEM_SESSIONS/$1.json" scope cfg kind name part
  if [[ -e "$MEM_SESSIONS/$sid.out" ]]; then return 1; fi
  if [[ -e "$st" ]]; then return 0; fi
  scope="$(memory_scope "$cwd")" || scope=""
  if [[ -z "$scope" ]]; then
    : > "$MEM_SESSIONS/$sid.out"
    return 1
  fi
  cfg="$(mem_config)" || return 1
  read -r kind name part <<< "$scope"
  [[ "$kind" == vault ]] && { part="$name"; name="vault"; }
  read -r _ tz min_events min_minutes <<< "$cfg"
  jq -n --arg scope "$kind" --arg partition "$part" --arg codebase "$name" --argjson now "$(date +%s)" \
    --arg tz "$tz" --argjson events "${min_events:-5}" --argjson minutes "${min_minutes:-20}" \
    '{scope: $scope, partition: $partition, codebase: $codebase, started_at: $now, last_digest_at: 0,
      awaiting_digest: false, tz: $tz, digest_min_events: $events, digest_min_minutes: $minutes}' \
    > "$st.tmp" && mv -f -- "$st.tmp" "$st" || return 1
  printf '0\n' > "$MEM_SESSIONS/$sid.events"
  : > "$MEM_SESSIONS/$sid.eligible"
}

mem_state_set() {  # mem_state_set <sid> <jq filter>: atomic update of the session state
  local st="$MEM_SESSIONS/$1.json"
  jq "$2" "$st" > "$st.tmp" && mv -f -- "$st.tmp" "$st"
}

mem_events() { local n=0; [[ -f "$MEM_SESSIONS/$1.events" ]] && read -r n < "$MEM_SESSIONS/$1.events"; [[ "$n" =~ ^[0-9]+$ ]] || n=0; printf '%s\n' "$n"; }

mem_alert() {  # mem_alert <tz> <message>
  local day
  day="$(TZ="$1" date +%F)"
  printf -- '- %s [soundwave] %s\n' "$(TZ="$1" date +%H:%M:%S)" "$2" >> "$MEM_VAULT/system/logs/alerts_$day.md"
}

mem_prune() { find "$MEM_SESSIONS" -maxdepth 1 -type f -mtime +14 -delete 2>/dev/null || true; }
```

- [ ] **Step 4: SessionStart.** Create `system/hooks/memory_recall.sh` and `chmod +x` it:

```bash
#!/bin/bash
# Soundwave SessionStart hook (spec §6.17): freeze the session's scope, then inject the recall block.
# Never fails the session: any problem is logged and the hook exits 0 with no output.
[[ "${JARVIS_HEADLESS:-}" == 1 ]] && exit 0
set -uo pipefail
# shellcheck source=lib_memory.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib_memory.sh"

main() {
  local input sid cwd out
  input="$(cat)"
  mem_env_ok || return 0
  [[ -z "$(jq -r '.agent_id // empty' <<< "$input")" ]] || return 0
  sid="$(jq -r '.session_id // empty' <<< "$input")"
  mem_valid_sid "$sid" || { mem_log "SessionStart: invalid session_id"; return 0; }
  cwd="$(jq -r '.cwd // empty' <<< "$input")"
  [[ -n "$cwd" ]] || cwd="$PWD"
  mem_prune
  mem_freeze "$sid" "$cwd" || return 0
  out="$(cd "$cwd" && timeout 3 "$MEM_VAULT/system/scripts/vault_index.py" recall --cwd "$cwd")" \
    || { mem_log "SessionStart: recall failed or timed out for ${sid:0:8}"; return 0; }
  [[ -n "$out" ]] || return 0
  jq -cn --arg c "$out" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $c}}'
}

main 2>> "$MEM_LOG"
exit 0
```

- [ ] **Step 5: PostToolUse.** Create `system/hooks/memory_activity.sh` and `chmod +x` it:

```bash
#!/bin/bash
# Soundwave PostToolUse hook (spec §6.17): count work events for an eligible session.
# Fast path: pure bash, no jq or Python (spike item 15: one jq call alone costs ~44 ms).
[[ "${JARVIS_HEADLESS:-}" != 1 && "${CLAUDE_CODE_ENTRYPOINT:-}" == cli ]] || exit 0
[[ "${JARVIS_CREW:-}" == 1 || "${CLAUDE_CODE_SESSION_ATTENDED:-}" == 1 ]] || exit 0
IFS= read -r -d '' input || true
[[ "$input" == *'"agent_id"'* ]] && exit 0  # subagent
[[ "$input" =~ \"session_id\"[[:space:]]*:[[:space:]]*\"([A-Za-z0-9-]+)\" ]] || exit 0
sid="${BASH_REMATCH[1]}"
d="${BASH_SOURCE[0]%/*}/../logs/memory/sessions"
if [[ ! -e "$d/$sid.eligible" ]]; then
  [[ -e "$d/$sid.out" ]] && exit 0
  # Hooks installed mid-session: no SessionStart ran, so freeze the scope once now (slow path).
  [[ "$input" =~ \"cwd\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]] || exit 0
  cwd="${BASH_REMATCH[1]}"
  # shellcheck source=lib_memory.sh
  source "${BASH_SOURCE[0]%/*}/lib_memory.sh"
  mem_freeze "$sid" "$cwd" 2>> "$MEM_LOG" || exit 0
fi
n=0
[[ -f "$d/$sid.events" ]] && { read -r n < "$d/$sid.events" || n=0; }
[[ "$n" =~ ^[0-9]+$ ]] || n=0
printf '%d\n' $(( n + 1 )) > "$d/$sid.events"
exit 0
```

- [ ] **Step 6: Run the tests.** `bats system/tests/memory.bats > system/logs/t2.log 2>&1; echo "exit=$?"`. Expected: `exit=0`, 9/9.

- [ ] **Step 7: Gate.** Expected `exit=0`.

- [ ] **Step 8: Commit.** `git add system/hooks/lib_memory.sh system/hooks/memory_recall.sh system/hooks/memory_activity.sh system/tests/memory.bats && git commit -m "feat(soundwave): SessionStart scope freeze and recall, pure-bash PostToolUse activity count"`

---

### Task 3: Stop hook (capture and request)

**Files:**
- Create: `system/hooks/digest_instructions.md`, `system/hooks/memory_capture.sh`
- Test: `system/tests/memory.bats` (append)

**Interfaces:**
- Consumes: Task 2's library and state; `system/scripts/redact.py` (stdin → stdout; `redactions: N` on stderr); Stop input `{session_id, cwd, last_assistant_message, stop_hook_active}` (spike 11).
- Produces:
  - **Capture:** a file `raw/<partition>/notes/<YYYY-MM-DD>-<HHMM>-<sid8>-<slug>.md` with frontmatter `type: session_digest`, `partition`, `codebase` (name or `"vault"`), `session_id`, `created_at` (ISO 8601 with offset, in the configured TZ), `provenance: ["session"]`, `redactions`, and for crew sessions `task_id`.
  - **Request:** `{"decision":"block","reason":"<digest_instructions.md>"}` on stdout.
  - **Missing digest:** an alert line in `alerts_<date>.md`.

- [ ] **Step 1: Write the failing tests.** Append to `system/tests/memory.bats`:

```bash
@test "capture: an out-of-scope session writes nothing" {
  mkdir -p "$BATS_TEST_TMPDIR/elsewhere"
  stop out-2 $'<vault-digest>\n## Outcome\nx\n</vault-digest>' "$BATS_TEST_TMPDIR/elsewhere"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ -z "$(digests)" ]
  [ ! -e "$S/out-2.json" ]
}

@test "capture: no request below the work-event threshold, a request at it" {
  thresholds 5 0
  start c-1
  tools c-1 4
  stop c-1 "Done with that."
  [ -z "$output" ]
  tool c-1
  stop c-1 "Done with that."
  [ "$(jq -r .decision <<< "$output")" = block ]
  [[ "$(jq -r .reason <<< "$output")" == "Jarvis memory (not an error): please reply with a short session digest."* ]]
  [ "$(jq -r .awaiting_digest "$S/c-1.json")" = true ]
}

@test "capture: no request before digest_min_minutes have passed" {
  thresholds 1 20
  start t-1
  tools t-1 5
  stop t-1 "Done."
  [ -z "$output" ]
  jq '.started_at -= 1300' "$S/t-1.json" > "$S/t-1.json.new"
  mv "$S/t-1.json.new" "$S/t-1.json"
  stop t-1 "Done."
  [ "$(jq -r .decision <<< "$output")" = block ]
}

@test "capture: no request when the last message asks the user a question" {
  thresholds 1 0
  start q-1
  tools q-1 3
  stop q-1 "Which option do you want?   "
  [ -z "$output" ]
}

@test "capture: a requested digest is redacted and written with the sid8 name and valid frontmatter" {
  thresholds 1 0
  start abcdef12-3456
  tools abcdef12-3456 2
  stop abcdef12-3456 "Done."
  msg=$'Here it is.\n<vault-digest>\n## Outcome\nShipped the export job.\n## Facts learned\n- password: hunter2\n</vault-digest>'
  stop abcdef12-3456 "$msg"
  [ -z "$output" ]
  f="$(digests)"
  [ "$(wc -l <<< "$f")" -eq 1 ]
  [[ "$f" =~ ^raw/personal/notes/[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}-abcdef12-shipped-the-export-job\.md$ ]]
  run grep -c hunter2 "$f"
  [ "$output" = 0 ]
  grep -q '\[REDACTED' "$f"
  grep -qx 'redactions: "1"' "$f"
  grep -qE '^created_at: "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{2}:[0-9]{2}"$' "$f"
  grep -qx 'codebase: "vault"' "$f"
  system/scripts/vault_index.py validate "$f"
  [ "$(cat "$S/abcdef12-3456.events")" -eq 0 ]
  [ "$(jq -r .awaiting_digest "$S/abcdef12-3456.json")" = false ]
}

@test "capture: an on-demand digest (no request first) is captured" {
  start od-1
  stop od-1 $'<vault-digest>\n## Outcome\nOn demand.\n</vault-digest>'
  [ "$(digests | wc -l)" -eq 1 ]
}

@test "capture: no digest after a request raises an alert and never asks twice in a row" {
  thresholds 1 0
  start n-1
  tools n-1 3
  stop n-1 "Done."
  [ "$(jq -r .decision <<< "$output")" = block ]
  stop n-1 "I would rather not."
  [ -z "$output" ]
  grep -q 'session n-1 did not return the requested digest' system/logs/alerts_*.md
  [ "$(jq -r .awaiting_digest "$S/n-1.json")" = false ]
}

@test "capture: an invalid session_id writes nothing" {
  start "../evil"
  stop "../evil" $'<vault-digest>\nx\n</vault-digest>'
  [ -z "$(digests)" ]
  run ls "$S"
  [ -z "$output" ]
}

@test "capture: two sessions in the same minute produce distinct files" {
  start aaaaaaaa-1
  start bbbbbbbb-1
  stop aaaaaaaa-1 $'<vault-digest>\n## Outcome\nSame text.\n</vault-digest>'
  stop bbbbbbbb-1 $'<vault-digest>\n## Outcome\nSame text.\n</vault-digest>'
  [ "$(digests | wc -l)" -eq 2 ]
}

@test "scope: frozen at SessionStart, so a later cd never moves the session" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  register code "$C" work
  start fz-1
  stop fz-1 $'<vault-digest>\n## Outcome\nFrozen.\n</vault-digest>' "$C"
  f="$(digests)"
  [[ "$f" == raw/personal/notes/* ]]
  grep -qx 'codebase: "vault"' "$f"
}

@test "capture: a worktree session's digest lands in its codebase's partition" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  git -C "$C" worktree add -q "$BATS_TEST_TMPDIR/code-feature" -b feature
  register code "$C" work
  start wt-2 "$BATS_TEST_TMPDIR/code-feature"
  stop wt-2 $'<vault-digest>\n## Outcome\nFrom a worktree.\n</vault-digest>' "$BATS_TEST_TMPDIR/code-feature"
  [[ "$(digests)" == raw/work/notes/* ]]
  grep -qx 'codebase: "code"' "$(digests)"
}

@test "crew sessions skip the attended check and the periodic request; marked digests carry task_id" {
  export JARVIS_CREW=1 JARVIS_TASK_ID=task-42 CLAUDE_CODE_SESSION_ATTENDED=0
  thresholds 1 0
  start crew-1
  tools crew-1 5
  stop crew-1 "Done."
  [ -z "$output" ]
  stop crew-1 $'<vault-digest>\n## Outcome\nTask done.\n</vault-digest>'
  grep -qx 'task_id: "task-42"' "$(digests)"
}
```

- [ ] **Step 2: Run them.** `bats system/tests/memory.bats > system/logs/t3.log 2>&1; echo "exit=$?"; grep -c '^not ok' system/logs/t3.log`. Expected: `exit=1`. The 12 capture tests fail because `memory_capture.sh` does not exist; the 9 from Task 2 pass.

- [ ] **Step 3: The request text.** Create `system/hooks/digest_instructions.md`:

```markdown
Jarvis memory (not an error): please reply with a short session digest. Summarize only the work since the previous digest (or since the session started), in at most 400 words, between a <vault-digest> line and a </vault-digest> line. Use these `##` headings, in order: Outcome, Decisions, Facts learned, Corrections (each explicit correction or preference the user stated, as *statement — context*; leave the section out if there were none), Open questions / friction, Follow-ups. No secrets, credentials, personal data about third parties, or code dumps. Then stop.
```

- [ ] **Step 4: Stop.** Create `system/hooks/memory_capture.sh` and `chmod +x` it:

```bash
#!/bin/bash
# Soundwave Stop hook (spec §6.17): capture a marked digest, or ask for one after substantive work.
# Never fails the session and never blocks twice in a row.
[[ "${JARVIS_HEADLESS:-}" == 1 ]] && exit 0
set -uo pipefail
# shellcheck source=lib_memory.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib_memory.sh"

slugify() {
  local s
  s="$(printf '%s' "$1" | sed -E 's/^[#* ]+//; s/[^A-Za-z0-9]+/-/g; s/^-+//; s/-+$//' | tr '[:upper:]' '[:lower:]')"
  s="${s:0:40}"
  s="${s%-}"
  printf '%s\n' "${s:-digest}"
}

write_digest() {  # write_digest <sid> <digest text>
  local sid="$1" text="$2" st part codebase tz stamp created first slug dir name n redacted count task=""
  st="$MEM_SESSIONS/$sid.json"
  part="$(jq -r .partition "$st")" codebase="$(jq -r .codebase "$st")" tz="$(jq -r .tz "$st")"
  stamp="$(TZ="$tz" date +%Y-%m-%d-%H%M)" created="$(TZ="$tz" date +%Y-%m-%dT%H:%M:%S%:z)"
  first="$(grep -m 1 -vE '^[[:space:]]*(#.*)?$|^[[:space:]]*\*\*[^*]+\*\*[[:space:]]*$' <<< "$text" || true)"
  slug="$(slugify "$first")"
  dir="$MEM_VAULT/raw/$part/notes"
  mkdir -p "$dir"
  name="$stamp-${sid:0:8}-$slug" n=1
  while [[ -e "$dir/$name.md" ]]; do n=$(( n + 1 )); name="$stamp-${sid:0:8}-$slug-$n"; done
  redacted="$(printf '%s' "$text" | "$MEM_VAULT/system/scripts/redact.py" 2> "$dir/.$name.count")" || return 1
  count="$(sed -n 's/^redactions: //p' "$dir/.$name.count")"
  rm -f -- "$dir/.$name.count"
  if [[ "${JARVIS_CREW:-}" == 1 && "${JARVIS_TASK_ID:-}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    task="task_id: \"$JARVIS_TASK_ID\""$'\n'
  fi
  # Written as a dotfile, then renamed: intake skips dotfiles, so it never sees a half-written digest.
  printf -- '---\ntype: session_digest\npartition: "%s"\ncodebase: "%s"\nsession_id: "%s"\ncreated_at: "%s"\nprovenance: ["session"]\nredactions: "%s"\n%s---\n%s\n' \
    "$part" "$codebase" "$sid" "$created" "${count:-0}" "$task" "$redacted" > "$dir/.$name.md.tmp" || return 1
  mv -f -- "$dir/.$name.md.tmp" "$dir/$name.md"
  mem_log "captured raw/$part/notes/$name.md"
}

main() {
  local input sid cwd msg body st events since now minutes trimmed reason tz
  input="$(cat)"
  mem_env_ok || return 0
  [[ -z "$(jq -r '.agent_id // empty' <<< "$input")" ]] || return 0
  sid="$(jq -r '.session_id // empty' <<< "$input")"
  mem_valid_sid "$sid" || { mem_log "Stop: invalid session_id"; return 0; }
  cwd="$(jq -r '.cwd // empty' <<< "$input")"
  [[ -n "$cwd" ]] || cwd="$PWD"
  mem_freeze "$sid" "$cwd" || return 0  # frozen scope: a later cd never moves the session
  st="$MEM_SESSIONS/$sid.json"
  now="$(date +%s)" tz="$(jq -r .tz "$st")"
  msg="$(jq -r '.last_assistant_message // ""' <<< "$input")"

  # 1. A marked digest (requested by this hook, or written on demand with /digest).
  if [[ "$msg" == *"<vault-digest>"*"</vault-digest>"* ]]; then
    body="${msg#*<vault-digest>}"
    body="${body%%</vault-digest>*}"
    write_digest "$sid" "$body" || { mem_log "Stop: digest write failed for ${sid:0:8}"; return 0; }
    mem_state_set "$sid" ".last_digest_at = $now | .awaiting_digest = false"
    printf '0\n' > "$MEM_SESSIONS/$sid.events"
    return 0
  fi
  [[ "${JARVIS_CREW:-}" == 1 ]] && return 0  # crewmates: on-demand digests only

  # 2. We asked last time and got no digest: alert, reset, and never ask twice in a row.
  if [[ "$(jq -r .awaiting_digest "$st")" == true ]]; then
    mem_alert "$tz" "session ${sid:0:8} did not return the requested digest"
    mem_state_set "$sid" '.awaiting_digest = false'
    printf '0\n' > "$MEM_SESSIONS/$sid.events"
    return 0
  fi

  # 3. Ask only after substantive work, and never when the assistant just asked the user something.
  events="$(mem_events "$sid")"
  since="$(jq -r 'if .last_digest_at > 0 then .last_digest_at else .started_at end' "$st")"
  minutes=$(( (now - since) / 60 ))
  trimmed="${msg%"${msg##*[![:space:]]}"}"
  [[ "$trimmed" == *"?" ]] && return 0
  (( events >= $(jq -r .digest_min_events "$st") )) || return 0
  (( minutes >= $(jq -r .digest_min_minutes "$st") )) || return 0
  reason="$(< "$(dirname "${BASH_SOURCE[0]}")/digest_instructions.md")"
  mem_state_set "$sid" '.awaiting_digest = true' || return 0
  jq -cn --arg r "$reason" '{decision: "block", reason: $r}'
}

main 2>> "$MEM_LOG"
exit 0
```

- [ ] **Step 5: Run the tests.** `bats system/tests/memory.bats > system/logs/t3.log 2>&1; echo "exit=$?"`. Expected: `exit=0`, 21/21.

- [ ] **Step 6: Gate.** Expected `exit=0`.

- [ ] **Step 7: Commit.** `git add system/hooks/digest_instructions.md system/hooks/memory_capture.sh system/tests/memory.bats && git commit -m "feat(soundwave): Stop hook captures redacted digests and asks for one after substantive work"`

---

### Task 4: `install_hooks.sh`

**Files:**
- Create: `system/scripts/install_hooks.sh`
- Test: `system/tests/hooks_install.bats` (create); `system/tests/vault_integrity.bats` (append)

**Interfaces:**
- Consumes: Tasks 2–3's hook files and `digest_instructions.md`; `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json` and `…/commands/digest.md`.
- Produces: `system/scripts/install_hooks.sh [--dry-run | --uninstall]`.
  - **Output:** `settings: changed|unchanged` and `digest command: new|changed|unchanged|removed|none|left alone (…)`.
  - **`--dry-run`** prints a unified diff of the sorted settings and writes nothing.
  - **Exit codes:** 0; 1 for an invalid settings file, a vault path that needs quoting, or a missing hook file; 2 for usage.
  - **Backup:** `settings.json.bak.<epoch>` before any write.
  - Plan 4b's `/setup` step 5a calls `--dry-run`, shows the diff, then runs the install on a yes.

- [ ] **Step 1: Write the failing tests.** Create `system/tests/hooks_install.bats`:

```bash
#!/usr/bin/env bats
# install_hooks.sh (spec §6.19). Always runs against a temporary HOME, never the real ~/.claude.
load helpers

setup() {
  make_vault
  cp -r "$REPO/system/hooks" "$V/system/hooks"
  export HOME="$BATS_TEST_TMPDIR/home"
  unset CLAUDE_CONFIG_DIR
  CFG="$HOME/.claude"
  SET="$CFG/settings.json"
  mkdir -p "$CFG/commands"
  cat > "$SET" <<'EOF'
{
  "model": "opus",
  "env": {"FOO": "1"},
  "permissions": {"allow": ["Bash(npm test)"], "deny": ["Read(~/.ssh/**)"]},
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "/usr/local/bin/notify-done"}]}],
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "/opt/guard.sh"}]}]
  }
}
EOF
  cp "$SET" "$BATS_TEST_TMPDIR/original.json"
  relocate "$V"
}

relocate() {  # relocate <path>: move the vault there and re-derive its paths
  [ "$1" = "$V" ] || mv "$V" "$1"
  V="$1"
  VP="$(cd "$V" && pwd -P)"
  IH="$VP/system/scripts/install_hooks.sh"
}

ours() { jq -r '[.hooks[][] | .hooks[] | .command | select(test("memory_"))] | .[]' "$SET"; }

@test "install merges the three hooks and three allows, leaving foreign entries alone" {
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(jq -r '.hooks.SessionStart[0].hooks[0].command' "$SET")" = "$VP/system/hooks/memory_recall.sh" ]
  [ "$(jq -r '.hooks.Stop | map(.hooks[].command) | join(",")' "$SET")" = "/usr/local/bin/notify-done,$VP/system/hooks/memory_capture.sh" ]
  [ "$(jq -r '.hooks.PostToolUse[0].matcher' "$SET")" = "Edit|Write|MultiEdit|NotebookEdit|Bash" ]
  [ "$(jq -r '.hooks.PreToolUse[0].hooks[0].command' "$SET")" = /opt/guard.sh ]
  [ "$(jq -r '.model + .env.FOO' "$SET")" = opus1 ]
  [ "$(jq -c '.permissions.allow' "$SET")" = "[\"Bash(npm test)\",\"Bash($VP/system/scripts/vault_index.py related:*)\",\"Bash($VP/system/scripts/vault_index.py show:*)\",\"Bash($VP/system/scripts/vault_index.py backlinks:*)\"]" ]
  run jq -r '.permissions.allow[] | select(test("query|^Read"))' "$SET"
  [ -z "$output" ]
  [ "$(jq -c '.permissions.deny' "$SET")" = '["Read(~/.ssh/**)"]' ]
}

@test "install writes the managed /digest command; a foreign one is never touched" {
  run "$IH"
  grep -qF "<!-- managed by vault: $VP -->" "$CFG/commands/digest.md"
  grep -qF '<vault-digest>' "$CFG/commands/digest.md"
  printf 'my own digest command\n' > "$CFG/commands/digest.md"
  run "$IH"
  [ "$status" -eq 0 ]
  [[ "$output" == *"left alone"* ]]
  [ "$(cat "$CFG/commands/digest.md")" = "my own digest command" ]
}

@test "a second run changes nothing and writes no new backup" {
  run "$IH"
  backups="$(ls "$CFG" | grep -c 'settings.json.bak')"
  sum="$(sha256sum "$SET")"
  run "$IH"
  [ "$status" -eq 0 ]
  grep -qx 'settings: unchanged' <<< "$output"
  grep -qx 'digest command: unchanged' <<< "$output"
  [ "$(sha256sum "$SET")" = "$sum" ]
  [ "$(ls "$CFG" | grep -c 'settings.json.bak')" -eq "$backups" ]
}

@test "a change is preceded by a timestamped backup of the old file" {
  run "$IH"
  bak="$(ls "$CFG"/settings.json.bak.*)"
  [ "$(jq -S . "$bak")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
}

@test "--dry-run prints the diff and writes nothing" {
  run "$IH" --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"+"*"memory_recall.sh"* ]]
  [ "$(sha256sum < "$SET")" = "$(sha256sum < "$BATS_TEST_TMPDIR/original.json")" ]
  [ ! -e "$CFG/commands/digest.md" ]
  run ls "$CFG"/settings.json.bak.*
  [ "$status" -ne 0 ]
}

@test "--uninstall restores the original settings and removes only the owned /digest" {
  run "$IH"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
  [ ! -e "$CFG/commands/digest.md" ]
  printf 'foreign\n' > "$CFG/commands/digest.md"
  run "$IH" --uninstall
  [ "$(cat "$CFG/commands/digest.md")" = foreign ]
}

@test "moving the vault re-points the entries instead of duplicating them" {
  run "$IH"
  relocate "$BATS_TEST_TMPDIR/moved"
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(ours | wc -l)" -eq 3 ]
  [ "$(ours | grep -c "^$VP/system/hooks/")" -eq 3 ]
  [ "$(jq '[.permissions.allow[] | select(test("vault_index"))] | length' "$SET")" -eq 3 ]
  grep -qF "<!-- managed by vault: $VP -->" "$CFG/commands/digest.md"
}

@test "no settings file yet: one is created" {
  rm "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(ours | wc -l)" -eq 3 ]
}

@test "invalid settings JSON aborts and leaves the file untouched" {
  printf '{ not json' > "$SET"
  run "$IH"
  [ "$status" -eq 1 ]
  [ "$(cat "$SET")" = '{ not json' ]
}

@test "a symlinked settings.json stays a symlink" {
  mv "$SET" "$BATS_TEST_TMPDIR/dotfiles.json"
  ln -s "$BATS_TEST_TMPDIR/dotfiles.json" "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  [ -L "$SET" ]
  [ "$(jq '[.hooks[][] | .hooks[] | select(.command | test("memory_"))] | length' "$BATS_TEST_TMPDIR/dotfiles.json")" -eq 3 ]
}

@test "a vault path that would need quoting is refused" {
  relocate "$BATS_TEST_TMPDIR/my vault"
  run "$IH"
  [ "$status" -eq 1 ]
  [[ "$output" == *"must not contain spaces"* ]]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
}

@test "CLAUDE_CONFIG_DIR redirects the target" {
  export CLAUDE_CONFIG_DIR="$BATS_TEST_TMPDIR/alt"
  run "$IH"
  [ "$status" -eq 0 ]
  [ -f "$CLAUDE_CONFIG_DIR/settings.json" ]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
}

@test "usage errors exit 2" {
  run "$IH" --bogus
  [ "$status" -eq 2 ]
}
```

Append to `system/tests/vault_integrity.bats`:

```bash
@test "memory hooks are executable, the library is sourced-only, and the digest text exists" {
  for h in memory_recall.sh memory_capture.sh memory_activity.sh; do
    [ -x "system/hooks/$h" ]
  done
  [ ! -x system/hooks/lib_memory.sh ]
  [ -x system/scripts/install_hooks.sh ]
  grep -qF 'Jarvis memory (not an error): please reply with a short session digest.' system/hooks/digest_instructions.md
  grep -qF '<vault-digest>' system/hooks/digest_instructions.md
}
```

- [ ] **Step 2: Run them.** `bats system/tests/hooks_install.bats system/tests/vault_integrity.bats > system/logs/t4.log 2>&1; echo "exit=$?"`. Expected: `exit=1`. All 13 install tests fail (status 127: no such script), and the integrity test fails on `[ -x system/scripts/install_hooks.sh ]`.

- [ ] **Step 3: Implement.** Create `system/scripts/install_hooks.sh` and `chmod +x` it:

```bash
#!/bin/bash
# Merge Soundwave's memory hooks into the user's Claude Code settings (spec §6.19).
# Touches only owned entries: hook commands under <vault>/system/hooks/memory_*.sh, the three
# absolute vault_index.py allow rules, and a commands/digest.md carrying the managed-by line.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CONFIG_DIR/settings.json"
DIGEST="$CONFIG_DIR/commands/digest.md"
MANAGED="<!-- managed by vault: "

die() { echo "install_hooks: $2" >&2; exit "$1"; }
usage() { die 2 "usage: install_hooks.sh [--dry-run | --uninstall]"; }
(( $# <= 1 )) || usage
case "${1:-}" in
  "") mode=install ;;
  --dry-run) mode=dry ;;
  --uninstall) mode=uninstall ;;
  *) usage ;;
esac

# Hook commands and Bash allow rules are matched as plain strings, so the vault path must not need quoting.
[[ "$VAULT_ROOT" =~ ^/[A-Za-z0-9._/@+-]+$ ]] \
  || die 1 "the vault path must not contain spaces or shell metacharacters: $VAULT_ROOT"
for h in memory_recall.sh memory_capture.sh memory_activity.sh; do
  [[ -x "system/hooks/$h" ]] || die 1 "missing or not executable: system/hooks/$h"
done

current='{}'
if [[ -e "$SETTINGS" ]]; then
  current="$(cat -- "$SETTINGS")"
  jq -e 'type == "object"' <<< "$current" > /dev/null 2>&1 \
    || die 1 "$SETTINGS is not a JSON object; fix it by hand first (nothing was changed)"
fi

# Owned = ours from any vault location, so moving the vault re-points the entries instead of duplicating them.
STRIP='
  def owned_cmd: (. // "") | test("/system/hooks/memory_(recall|capture|activity)\\.sh$");
  def owned_allow: test("^Bash\\(/.*/system/scripts/vault_index\\.py (related|show|backlinks):\\*\\)$");
  (if (.hooks | type) == "object" then
     .hooks |= with_entries(
       if (.value | type) == "array" then
         .value |= (map(if (.hooks | type) == "array" then .hooks |= map(select(.command | owned_cmd | not)) else . end)
                    | map(select((.hooks | type) != "array" or (.hooks | length) > 0)))
       else . end)
     | .hooks |= with_entries(select((.value | type) != "array" or (.value | length) > 0))
     | if .hooks == {} then del(.hooks) else . end
   else . end)
  | (if (.permissions.allow | type) == "array" then
       .permissions.allow |= map(select(type != "string" or (owned_allow | not)))
       | if .permissions.allow == [] then del(.permissions.allow) else . end
       | if .permissions == {} then del(.permissions) else . end
     else . end)'
ADD='
  .hooks.SessionStart = ((.hooks.SessionStart // []) + [{hooks: [{type: "command", command: ($v + "/system/hooks/memory_recall.sh"), timeout: 5}]}])
  | .hooks.Stop = ((.hooks.Stop // []) + [{hooks: [{type: "command", command: ($v + "/system/hooks/memory_capture.sh"), timeout: 10}]}])
  | .hooks.PostToolUse = ((.hooks.PostToolUse // []) + [{matcher: "Edit|Write|MultiEdit|NotebookEdit|Bash",
      hooks: [{type: "command", command: ($v + "/system/hooks/memory_activity.sh"), timeout: 5}]}])
  | .permissions.allow = ((.permissions.allow // []) + [
      "Bash(" + $v + "/system/scripts/vault_index.py related:*)",
      "Bash(" + $v + "/system/scripts/vault_index.py show:*)",
      "Bash(" + $v + "/system/scripts/vault_index.py backlinks:*)"])'
if [[ "$mode" == uninstall ]]; then
  new="$(jq "$STRIP" <<< "$current")"
else
  new="$(jq --arg v "$VAULT_ROOT" "$STRIP | $ADD" <<< "$current")"
fi
jq -e 'type == "object"' <<< "$new" > /dev/null || die 1 "the merged settings did not parse; nothing was changed"

digest_body() {
  printf -- '---\ndescription: Write a Jarvis session digest of the work since the last one.\n---\n%s%s -->\n\n' "$MANAGED" "$VAULT_ROOT"
  cat system/hooks/digest_instructions.md
}
digest_owned() { [[ -f "$DIGEST" ]] && grep -qF -- "$MANAGED" "$DIGEST"; }
if [[ "$mode" == uninstall ]]; then
  if digest_owned; then digest_action=remove; else digest_action=none; fi
elif [[ ! -e "$DIGEST" ]]; then
  digest_action=new
elif ! digest_owned; then
  digest_action=foreign
elif [[ "$(cat -- "$DIGEST")" == "$(digest_body)" ]]; then
  digest_action=unchanged
else
  digest_action=changed
fi

if [[ "$(jq -S . <<< "$current")" == "$(jq -S . <<< "$new")" ]]; then settings_action=unchanged; else settings_action=changed; fi

if [[ "$mode" == dry ]]; then
  diff -u --label "$SETTINGS (current)" --label "$SETTINGS (after install)" \
    <(jq -S . <<< "$current") <(jq -S . <<< "$new") || true
  echo "settings: $settings_action (dry run, nothing written)"
  echo "digest command: $digest_action (dry run, nothing written)"
  exit 0
fi

if [[ "$settings_action" == changed ]]; then
  mkdir -p -- "$CONFIG_DIR"
  [[ -e "$SETTINGS" ]] && cp -p -- "$SETTINGS" "$SETTINGS.bak.$(date +%s)"
  if [[ -L "$SETTINGS" ]]; then
    jq . <<< "$new" > "$SETTINGS"  # write through a symlink (dotfile managers), keeping the link
  else
    jq . <<< "$new" > "$SETTINGS.tmp.$$"
    mv -f -- "$SETTINGS.tmp.$$" "$SETTINGS"
  fi
fi
echo "settings: $settings_action"

case "$digest_action" in
  new|changed) mkdir -p -- "$(dirname "$DIGEST")"; digest_body > "$DIGEST"; echo "digest command: $digest_action" ;;
  remove) rm -f -- "$DIGEST"; echo "digest command: removed" ;;
  foreign) echo "digest command: left alone ($DIGEST exists and is not managed by a vault)" ;;
  *) echo "digest command: $digest_action" ;;
esac
```

- [ ] **Step 4: Run the tests.** Same command. Expected: `exit=0`.

- [ ] **Step 5: Gate.** Expected `exit=0`: 13 bats suites PASS, `329 passed`.

- [ ] **Step 6: Commit.** `git add system/scripts/install_hooks.sh system/tests/hooks_install.bats system/tests/vault_integrity.bats && git commit -m "feat(soundwave): install_hooks.sh merges the memory hooks reversibly into Claude Code settings"`

---

### Task 5: Live acceptance (real interactive `claude`, throwaway vault and settings)

**Files:**
- Create: `docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md`
- Modify only if a check fails: the hook or script at fault, with a failing test first

**Interfaces:**
- Consumes: Tasks 1–4 committed; `claude`, `tmux`.
- Produces: a PASS/FAIL record per check. Task 6 marks Plan 3 complete only on PASS.

This task drives a real interactive session in `tmux`, as spike items 10–17 did. The hooks come from a **scratch** settings file passed with `--settings`. Never run `install_hooks.sh` without `CLAUDE_CONFIG_DIR` pointing into the scratch directory, and never touch `~/.claude/`. Driving tmux: `tmux send-keys -t jmem '<text>' Enter`, then poll `tmux capture-pane -p -t jmem` until the prompt returns. Answer a trust dialog for the throwaway folder with Enter. If `tmux` cannot be driven, stop and hand Steps 2–8 to your human partner as a checklist.

- [ ] **Step 1: Throwaway vault and scratch settings.**

```bash
M="${XDG_CACHE_HOME:-$HOME/.cache}/jarvis-mem"
B="$(git branch --show-current)"; R="$(git rev-parse --show-toplevel)"
rm -rf "$M" && mkdir -p "$M" && git clone -q -b "$B" "$R" "$M/vault" && cd "$M/vault"
cp system/config.example.md system/config.md
system/scripts/vault_index.py set system/config.md digest_min_events 1
system/scripts/vault_index.py set system/config.md digest_min_minutes 0
mkdir -p raw/personal/notes
printf -- '---\ntype: session_digest\npartition: "personal"\ncodebase: "vault"\nsession_id: "seed-0000"\ncreated_at: "2026-10-01T09:00:00-06:00"\n---\n## Outcome\nSEED-OUTCOME: the export job moved to Fridays.\n## Follow-ups\n- Check the retry policy.\n' > raw/personal/notes/seed.md
CLAUDE_CONFIG_DIR="$M/cfg" system/scripts/install_hooks.sh; echo "exit=$?"
jq -e '.hooks.SessionStart and .hooks.Stop and .hooks.PostToolUse' "$M/cfg/settings.json"
```
Expected: `settings: changed`, `exit=0`, and jq prints `true`. `~/.claude/settings.json` is unchanged (compare `sha256sum` before and after).

- [ ] **Step 2: SessionStart recall.** `tmux new-session -d -s jmem -c "$M/vault" "claude --settings $M/cfg/settings.json"`. Then send: `Quote the first line of the Jarvis vault recall block and the SEED-OUTCOME line, then stop.` Expected: the reply quotes `## Jarvis vault recall` and `SEED-OUTCOME: the export job moved to Fridays.`; `system/logs/memory/sessions/*.json` holds `"scope": "vault"`. This also re-checks spike 12: the attended variables still fire.

- [ ] **Step 3: Activity → request → capture.** Send: `Run ls wiki and tell me how many entries there are.` After the reply, the Stop hook blocks once. The pane shows "Stop hook error: Jarvis memory (not an error): …" and the model replies with a `<vault-digest>` block. Expected:
  - one new file `raw/personal/notes/<date>-<HHMM>-<sid8>-<slug>.md`;
  - `system/scripts/vault_index.py validate <file>` exits 0;
  - the session's `.events` is `0` and `awaiting_digest` is `false`.

- [ ] **Step 4: No second request.** Send: `Say hi.` Expected: no Stop-hook block; no new digest file.

- [ ] **Step 5: `/clear` and resume (spike 13).**
  - Send `/clear`. Expected: SessionStart fires with source `clear`, and recall is injected again (ask for the first recall line again).
  - Exit with `/exit`, then start `claude --continue --settings "$M/cfg/settings.json"` in the same window.
  - Record whether SessionStart fires with source `resume`, and whether the `session_id` (and so the state file) is reused. Either is acceptable; record what happens.

- [ ] **Step 6: Codebase session and partition wall.**

```bash
C="$M/code"; git init -q "$C" && git -C "$C" -c user.email=t@e -c user.name=t commit -q --allow-empty -m i
cd "$M/vault" && mkdir -p system/codebases && printf -- '---\ntype: codebase\nname: "code"\npath: "%s"\npartition: "work"\nsearch_globs: ["*"]\n---\n' "$C" > system/codebases/code.md
```
Open a second window: `tmux new-session -d -s jcode -c "$C" "claude --settings $M/cfg/settings.json"`. Send: `Run $M/vault/system/scripts/vault_index.py related "export" and show the output.` Expected:
- the command runs with no permission prompt (the absolute allow rule matches; spike 16);
- the output holds no `personal` note;
- the recall block (ask for its first lines) names `Scope: codebase code (work)` and does not contain SEED-OUTCOME.

- [ ] **Step 7: Latency.** In the throwaway vault, time each hook on its real input:

```bash
export CLAUDE_CODE_ENTRYPOINT=cli CLAUDE_CODE_SESSION_ATTENDED=1
S=lat-$$; V="$M/vault"
t0=$(date +%s%N); printf '{"session_id":"%s","cwd":"%s","source":"startup"}' "$S" "$V" | "$V/system/hooks/memory_recall.sh" >/dev/null; t1=$(date +%s%N); echo "SessionStart ms: $(( (t1-t0)/1000000 ))"
t0=$(date +%s%N); for i in $(seq 20); do printf '{"session_id":"%s","tool_name":"Edit"}' "$S" | "$V/system/hooks/memory_activity.sh"; done; t1=$(date +%s%N); echo "PostToolUse avg ms: $(( (t1-t0)/20000000 ))"
t0=$(date +%s%N); printf '{"session_id":"%s","cwd":"%s","last_assistant_message":"Which one?"}' "$S" "$V" | "$V/system/hooks/memory_capture.sh" >/dev/null; t1=$(date +%s%N); echo "Stop ms: $(( (t1-t0)/1000000 ))"
```
Expected: PostToolUse < 30 ms, Stop < 150 ms, SessionStart < 3000 ms.

- [ ] **Step 8: Intake picks the digest up.** In the throwaway vault, `touch -d '-2 minutes' raw/personal/notes/*.md && system/scripts/intake_daemon.sh; echo "exit=$?"`. Expected: `exit=0`, and the Step 3 digest (with the seed) is archived to `raw/personal/archive/`. This is a headless run, so it consumes Claude usage.

- [ ] **Step 9: When a check fails.** Read `system/logs/memory/hooks.log` and the session's state files. Reproduce the failure in `memory.bats` or `hooks_install.bats` (it must fail first), fix it in the repo, re-run the gate and commit (`fix(soundwave): <what the live run showed>`). Rebuild the throwaway vault (Step 1) and repeat the failed step. Stop after 3 attempts on one step and report to your human partner.

- [ ] **Step 10: Record and clean up.** Write `docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md`: date, `claude --version`, commit, and a table `Step | Check | Result | Notes`, one row per check (Step 5's observed resume behavior and Step 7's timings included), then the verdict. Commit it (`docs: Plan 3 live acceptance record`). Then `tmux kill-session -t jmem; tmux kill-session -t jcode; rm -rf "$M"`.

---

### Task 6: Roadmap

**Files:**
- Modify: `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md`

**Interfaces:**
- Consumes: Task 5's PASS. **If Task 5 did not pass, do not do this task**; report instead.
- Produces: the roadmap state Plan 4b starts from.

- [ ] **Step 1: Edit the roadmap.**
  - Set the Plan 3 row's Status to `` Complete (<the date of this commit, YYYY-MM-DD>): `2026-10-02-plan-3-memory.md`; acceptance `docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md` ``.
  - In the Sub-project 2 row, change `After Plan 4` to `After Plan 4b`.

- [ ] **Step 2: Verify.** Run the gate (expected `exit=0`) and `system/scripts/lint_vault.sh > system/logs/lint.log 2>&1; echo "lint exit=$?"` (expected `0`, `0 errors`).

- [ ] **Step 3: Commit.** `git add docs/superpowers/plans/2026-09-30-jarvis-roadmap.md && git commit -m "docs: mark Plan 3 complete; Sub-project 2 follows Plan 4b"`

- [ ] **Step 4: Hand-off (to your human partner, not an action).** Memory capture stays off until they choose. They review `system/scripts/install_hooks.sh --dry-run`, then run `system/scripts/install_hooks.sh` against their own settings, or wait for Plan 4b's `/setup` step. Either way the README and `/setup` text are Plan 4b's.
