# Foreman v1: Work Orders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The unattended runner becomes Work Orders for the user (`/order`, new settings keys with the old ones still read), an order starts now by default and holds new starts at a 5-hour usage ceiling, and an approved plan becomes a Work Order that the brief, the debrief and the Foreman report.

**Architecture:** Only names the user sees change; `nightshift.py`, the `nightshift_*` modules, unit names, the `nightshift_item` schema and `raw/<p>/nightshift/` keep their names until the reorganization (#62). A `setting(d, new, old)` helper reads every renamed key with its old name as a fallback. The scheduler gains an always-open default window and a `five_hour_hold` check fed by a `usage5` reading the runner stores after each session.

**Tech Stack:** Python 3 (`vaultlib`), bash, bats 1.8.2, pytest.

**Spec:** `docs/superpowers/specs/2026-10-08-foreman-v1-work-orders-design.md`

## Global Constraints

- Work on branch `feat/foreman-v1`. Commit there; do not push or open a pull request.
- New prose follows the Writing rules in `CLAUDE.md`.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: pytest (`system/tests/python/test_nightshift_*.py`), bats (`commands.bats`, `prep.bats`, `units.bats`) and the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains. Read verdicts from exit codes.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.
- Task 1 moves a folder under `.claude/skills/`, so this plan runs in an attended session (native or subagent), not as a Work Order.

## Review Focus

- A vault that still has `nightshift_window`, `nightshift_workspace` or a codebase's `nightshift_pr` keeps working, and the new key wins when both are set: the `setting` tests.
- An item queued or running before the update still delivers its `nightshift/<id>` branch: `test_a_clone_made_before_the_rename_delivers_its_nightshift_branch`.
- The 5-hour ceiling holds only a new start, ignores a reading older than 5 hours, survives the report day's change at `brief_time`, and its Held line reaches the report file the brief and the debrief copy: the ceiling tests.
- A vault that set `nightshift_window` keeps its window for `start: window` items, while `/order add` starts now: the window tests.
- The debrief copies the report that collects everything since the morning's brief: the `prep.bats` orders test.

---

### Task 1: The rename, with the old settings keys still read

**Files:**
- Move: `.claude/skills/nightshift/` → `.claude/skills/order/`
- Modify: `CLAUDE.md`, `README.md`, `system/schemas/codebase.md`, `system/schemas/config.md`, `system/schemas/nightshift_item.md`, `system/scripts/vaultlib/nightshift_check.py`, `system/scripts/vaultlib/nightshift_deliver.py`, `system/scripts/vaultlib/nightshift_report.py`, `system/scripts/vaultlib/nightshift_run.py`, `system/systemd/foundry-nightshift.service.in`, `system/systemd/foundry-nightshift.timer.in`
- Test: `system/tests/commands.bats`, `system/tests/prep.bats`, `system/tests/units.bats`, `system/tests/python/test_nightshift_check.py`, `system/tests/python/test_nightshift_deliver.py`, `system/tests/python/test_nightshift_report.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `nightshift_check.setting(d: dict, new: str, old: str)` (the new key's value when the key is present, else the old key's); new PR branches `order/<id>`; report heading `# Work Orders: <date>`; alert tag `[orders]`.

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/commands.bats`. Find:

````text
  [[ "$sec" == *'add the line `Onboarding: [[<Name>OnboardingAssignment]]` to the body of `system/codebases/<name>.md`'* ]]
}
````

Replace with:

````text
  [[ "$sec" == *'add the line `Onboarding: [[<Name>OnboardingAssignment]]` to the body of `system/codebases/<name>.md`'* ]]
}

@test "Work Orders: the /order skill, CLAUDE.md, the README and the schemas use the new names (Foreman v1 §3.1)" {
  [ ! -e .claude/skills/nightshift ]
  f=.claude/skills/order/SKILL.md
  grep -qx 'name: order' "$f"
  grep -qF '/order add|ask|list|cancel|status' "$f"
  grep -qF 'system/scripts/nightshift.py add --kind plan' "$f"
  grep -qF 'Work Order' "$f"
  grep -qF -- '- `/order add|ask|list|cancel|status`:' CLAUDE.md
  grep -qF -- '- `raw/<partition>/nightshift/`: Work Order queue notes' CLAUDE.md
  run grep -nE '(^|[`( ])/nightshift' "$f" CLAUDE.md README.md
  [ "$status" -eq 1 ]
  grep -qF '| `/order add\|ask\|list\|cancel\|status` |' README.md
  grep -qF '.claude/skills/order/' README.md
  for k in run_window order_workspace nightshift_window nightshift_workspace; do grep -qF "\`$k\`" README.md; done
  for k in run_window order_workspace nightshift_window nightshift_workspace; do grep -q "^  $k:" system/schemas/config.md; done
  for k in order_pr order_hosts order_plugins nightshift_pr nightshift_hosts nightshift_plugins; do
    grep -q "^  $k:" system/schemas/codebase.md
  done
}
````


Edit 1 in `system/tests/prep.bats`. Find:

````text
  printf '# Nightshift: 2026-10-01\n> Health: claude ok\n\nNothing ran.\n' > system/logs/nightshift/2026-10-01.md
  run "$BP" 2026-10-01
  grep -qx '# Nightshift: 2026-10-01' "$IN/nightshift.md"
````

Replace with:

````text
  printf '# Work Orders: 2026-10-01\n> Health: claude ok\n\nNothing ran.\n' > system/logs/nightshift/2026-10-01.md
  run "$BP" 2026-10-01
  grep -qx '# Work Orders: 2026-10-01' "$IN/nightshift.md"
````


Edit 1 in `system/tests/units.bats`. Find:

````text
  grep -q 'nightshift.py' "$UD/foundry-nightshift.service"
````

Replace with:

````text
  grep -q 'nightshift.py' "$UD/foundry-nightshift.service"
  grep -qx 'Description=The Foundry: Work Orders tick' "$UD/foundry-nightshift.service"
  grep -qx 'Description=The Foundry: Work Orders tick every 15 minutes' "$UD/foundry-nightshift.timer"
````


Edit 1 in `system/tests/python/test_nightshift_check.py`. Find:

````text
    return clone


````

Replace with:

````text
    return clone


def set_codebase(vault: Path, name: str, **keys) -> None:
    """Add frontmatter keys to a registered codebase's file."""
    p = vault / "system" / "codebases" / f"{name}.md"
    head, _, rest = p.read_text().rpartition("---\n")
    p.write_text(head + "".join(f'{k}: "{v}"\n' for k, v in keys.items()) + "---\n" + rest)


def test_setting_reads_the_old_key_and_the_new_one_wins():
    assert nc.setting({"nightshift_pr": "a"}, "order_pr", "nightshift_pr") == "a"
    assert nc.setting({"nightshift_pr": "a", "order_pr": "b"}, "order_pr", "nightshift_pr") == "b"
    assert nc.setting({}, "order_pr", "nightshift_pr") is None


def test_a_codebase_plan_needs_order_pr_or_its_old_name(vault_repo, tmp_path):
    registered(vault_repo, tmp_path)
    fm = plan_fm(tasks="1-2", repo="shop", base="main")
    assert any("codebase shop has no order_pr" in e for e in nc.check(vault_repo, fm, ""))
    set_codebase(vault_repo, "shop", nightshift_pr="github:o/shop")
    assert not any("order_pr" in e for e in nc.check(vault_repo, fm, ""))


````


Edit 1 in `system/tests/python/test_nightshift_deliver.py`. Find:

````text
    assert nd.push_target(vault, {"repo": "template"}) == ("https://github.com/acme/vault-template.git", "github:acme/vault-template")


````

Replace with:

````text
    assert nd.push_target(vault, {"repo": "template"}) == ("https://github.com/acme/vault-template.git", "github:acme/vault-template")


def test_push_target_reads_order_pr_and_its_old_name(vault: Path, tmp_path):
    from test_nightshift_check import registered, set_codebase
    registered(vault, tmp_path)
    set_codebase(vault, "shop", nightshift_pr="bitbucket-link")
    assert nd.push_target(vault, {"repo": "shop"})[1] == "bitbucket-link"
    set_codebase(vault, "shop", order_pr="github:o/shop")
    assert nd.push_target(vault, {"repo": "shop"})[1] == "github:o/shop"
    assert nd.open_pr("gitlab", "order/x", "main", "T", Path("/b"), "") == (False, "unknown order_pr 'gitlab'")


````

Edit 2 in `system/tests/python/test_nightshift_deliver.py`. Find:

````text
    assert git(runner, "show", f"{new}:a.txt") == "a"
````

Replace with:

````text
    assert git(runner, "show", f"{new}:a.txt") == "a"
    assert git(runner, "log", "-1", "--format=%an <%ae>", new).strip() == "Work Orders <orders@localhost>"
````


Edit 1 in `system/tests/python/test_nightshift_report.py`. Find:

````text
    assert text.startswith("# Nightshift: 2026-10-07\n> Health: claude ok · gh ok · sandbox ok · usage 5h 12% / 7d 48% · last tick 05:00")
````

Replace with:

````text
    assert text.startswith("# Work Orders: 2026-10-07\n> Health: claude ok · gh ok · sandbox ok · usage 5h 12% / 7d 48% · last tick 05:00")
````

Edit 2 in `system/tests/python/test_nightshift_report.py`. Find:

````text
    assert nr.build(vault, "2026-10-08") == "# Nightshift: 2026-10-08\n> Health: not checked\n\nNothing ran.\n"
````

Replace with:

````text
    assert nr.build(vault, "2026-10-08") == "# Work Orders: 2026-10-08\n> Health: not checked\n\nNothing ran.\n"
````


Edit 1 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert "nightshift/" in git(tmp / "remote.git", "branch", "--list")
````

Replace with:

````text
    assert "order/" in git(tmp / "remote.git", "branch", "--list")
````

Edit 2 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert not list((tmp / "ws").glob("nightshift-2026*"))  # clone removed after delivery
````

Replace with:

````text
    assert not list((tmp / "ws").glob("nightshift-2026*"))  # clone removed after delivery
    body = (vault / "system/logs/nightshift/items" / fm["id"] / "pr_body.md").read_text()
    assert body.endswith(f"Queued as Work Order `{fm['id']}`.\n")
````

Edit 3 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert git(tmp / "remote.git", "branch", "--list", "nightshift/*").strip() == ""
````

Replace with:

````text
    assert git(tmp / "remote.git", "branch", "--list", "order/*").strip() == ""
````

Edit 4 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert only_item(vault)[1]["reason"] == "no result"
````

Replace with:

````text
    assert only_item(vault)[1]["reason"] == "no result"


def test_settings_read_the_old_keys_and_the_new_ones_win(env, tmp_path):
    vault, _ = env
    assert nr.Ctx(vault, NOW).workspace == tmp_path / "ws"   # the fixture sets only nightshift_workspace
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "UTC"\nnightshift_workspace: "/old"\n'
          'order_workspace: "/new"\nnightshift_window: "21:00-04:00"\n---\n')
    ctx = nr.Ctx(vault, NOW)
    assert ctx.workspace == Path("/new") and ctx.window == nr.ns.parse_window("21:00-04:00")
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "UTC"\nnightshift_window: "21:00-04:00"\n'
          'run_window: "23:00-02:00"\n---\n')
    assert nr.Ctx(vault, NOW).window == nr.ns.parse_window("23:00-02:00")


def test_alerts_carry_the_orders_tag(env):
    vault, _ = env
    ctx = nr.Ctx(vault, NOW)
    ctx.alert("k", "something broke")
    text = "".join(p.read_text() for p in (vault / "system" / "logs").glob("alerts_*.md"))
    assert "[orders] something broke" in text and "[nightshift]" not in text
````

Edit 5 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert git(clone, "for-each-ref", "--format=%(refname)").split() == [f"refs/heads/nightshift/{fm['id']}", "refs/remotes/base"]
````

Replace with:

````text
    assert git(clone, "for-each-ref", "--format=%(refname)").split() == [f"refs/heads/order/{fm['id']}", "refs/remotes/base"]
````

Edit 6 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert [c for c in calls if c[:3] == ["git", "-C", str(clone)]] == []


````

Replace with:

````text
    assert [c for c in calls if c[:3] == ["git", "-C", str(clone)]] == []


def test_a_clone_made_before_the_rename_delivers_its_nightshift_branch(env, monkeypatch):
    vault, tmp = env
    assert add(vault, "--now") == 0
    path, fm = only_item(vault)
    ctx = nr.Ctx(vault, NOW)
    clone = nr._clone(ctx, fm)
    git(clone, "branch", "-m", f"nightshift/{fm['id']}")   # an item already running when the vault updated
    idir = vault / "system/logs/nightshift/items" / fm["id"]
    idir.mkdir(parents=True)
    before = nr._before(ctx, fm, idir)
    (clone / "done.txt").write_text("yes")
    git(clone, "add", "done.txt")
    git(clone, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "work")
    (clone / ".nightshift").mkdir()
    (clone / ".nightshift" / "result.json").write_text(RESULT)
    monkeypatch.setattr(nr.nd, "verify_sha", lambda *a: (True, ""))
    assert nr._deliver_plan(ctx, fm, clone, idir, before)["state"] == "done"
    assert f"nightshift/{fm['id']}" in git(tmp / "remote.git", "branch", "--list")


````


- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_report.py system/tests/python/test_nightshift_run.py`
Expected: FAIL, 10 failed.

Run: `bats system/tests/commands.bats system/tests/prep.bats system/tests/units.bats`
Expected: FAIL, 2 `not ok`.

- [ ] **Step 3: Move the skill**

Run: `git mv .claude/skills/nightshift .claude/skills/order`

- [ ] **Step 4: Implement**

Edit 1 in `.claude/skills/order/SKILL.md`. Find:

````text
name: nightshift
description: |
  Queue refined work for unattended execution: an approved implementation plan (or a task range of one) that ends in
  a pull request, or a written research brief that ends in a findings note. Use for /nightshift add|ask|list|cancel|status,
  or when the user wants work run overnight, later today or in the background.
---
# Nightshift

Spec: `docs/superpowers/specs/2026-10-06-nightshift-design.md`. Everything runs through `system/scripts/nightshift.py` from the vault root.

**`/nightshift add <plan> [--tasks N-M] [--at HH:MM | --now] [--budget 4h] [--model opus]`**
````

Replace with:

````text
name: order
description: |
  Queue refined work as a Work Order for unattended execution: an approved implementation plan (or a task range of one)
  that ends in a pull request, or a written research brief that ends in a findings note. Use for
  /order add|ask|list|cancel|status, or when the user wants work run in the background, later today or overnight.
---
# Work Orders

Specs: `docs/superpowers/specs/2026-10-06-nightshift-design.md` (the runner) and `docs/superpowers/specs/2026-10-08-foreman-v1-work-orders-design.md` (Work Orders). Everything runs through `system/scripts/nightshift.py` from the vault root.

**`/order add <plan> [--tasks N-M] [--at HH:MM | --now] [--budget 4h] [--model opus]`**
````

Edit 2 in `.claude/skills/order/SKILL.md`. Find:

````text
**`/nightshift ask`**: draft the brief with the user, one question at a time, until it has `## Question`, `## Scope` (sources and any web hosts), `## Done when` and `## Output` (the findings note, a new path under `wiki/<partition>/`; research creates new notes only). When the question is about code, ask which repository (a registered codebase or `template`) and which branch or commit (a branch for `template`); the session reads a pinned copy under `code/`, at the remote's default branch when no base is named. Save the brief to a temporary file, then run `nightshift.py add --kind research --title "…" --partition <p> --brief-file <file> --output <path> --host <h> … [--repo <name> [--base <branch or commit>]] [--now | --at]`.

**`/nightshift list`**, **`cancel <id>`**, **`status`** (`nightshift.py report` for the coming morning's report).

Queuing is the user's approval for that item to push a branch and open a pull request. Never queue on the user's behalf without an explicit yes in this conversation. Exit codes: 0 ok, 1 an item failed, 2 not ready or bad arguments, 4 a run is in progress.
````

Replace with:

````text
**`/order ask`**: draft the brief with the user, one question at a time, until it has `## Question`, `## Scope` (sources and any web hosts), `## Done when` and `## Output` (the findings note, a new path under `wiki/<partition>/`; research creates new notes only). When the question is about code, ask which repository (a registered codebase or `template`) and which branch or commit (a branch for `template`); the session reads a pinned copy under `code/`, at the remote's default branch when no base is named. Save the brief to a temporary file, then run `nightshift.py add --kind research --title "…" --partition <p> --brief-file <file> --output <path> --host <h> … [--repo <name> [--base <branch or commit>]] [--now | --at]`.

**`/order list`**, **`cancel <id>`**, **`status`** (`nightshift.py report` for the open report: everything since this morning's brief).

Queuing is the user's approval for that Work Order to push a branch and open a pull request. Never queue on the user's behalf without an explicit yes in this conversation. Exit codes: 0 ok, 1 an item failed, 2 not ready or bad arguments, 4 a run is in progress.
````


Edit 1 in `CLAUDE.md`. Find:

````text
- `raw/<partition>/nightshift/`: Nightshift queue notes (tracked; never ingested).
````

Replace with:

````text
- `raw/<partition>/nightshift/`: Work Order queue notes (tracked; never ingested).
````

Edit 2 in `CLAUDE.md`. Find:

````text
- `/nightshift add|ask|list|cancel|status`: queue refined work for unattended runs (a plan's task range to a pull request, or a research brief to a findings note).
````

Replace with:

````text
- `/order add|ask|list|cancel|status`: queue refined work as Work Orders for unattended runs (a plan's task range to a pull request, or a research brief to a findings note).
````


Edit 1 in `README.md`. Find:

````text
- The Nightshift: queued plans and research briefs run unattended overnight
````

Replace with:

````text
- Work Orders: queued plans and research briefs run unattended
````

Edit 2 in `README.md`. Find:

````text
| `/nightshift add\|ask\|list\|cancel\|status` | Queues an approved plan (or a task range of one) or a research brief for an unattended run; lists, cancels and reports on queued items |
````

Replace with:

````text
| `/order add\|ask\|list\|cancel\|status` | Queues an approved plan (or a task range of one) or a research brief as a Work Order for an unattended run; lists, cancels and reports on queued Work Orders |
````

Edit 3 in `README.md`. Find:

````text
**The Nightshift.** `/nightshift` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time: in the nightly window (`nightshift_window`, default `22:00-05:00`), at a set time, or now. A plan item runs in a private clone under `nightshift_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The morning report, `system/logs/nightshift/<date>.md`, starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server. A plan item for this template is read from `template_remote`: push its branch there before queuing it, and queuing checks the remote, which needs the network and the remote's credentials.
````

Replace with:

````text
**Work Orders.** `/order` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time: in the run window (`run_window`, default `22:00-05:00`), at a set time, or now. A plan item runs in a private clone under `order_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The report, `system/logs/nightshift/<date>.md` (heading `# Work Orders: <date>`), starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server. A plan item for this template is read from `template_remote`: push its branch there before queuing it, and queuing checks the remote, which needs the network and the remote's credentials. Settings renamed with Work Orders: `run_window` was `nightshift_window`, `order_workspace` was `nightshift_workspace`, and a codebase's `order_pr`, `order_hosts` and `order_plugins` were `nightshift_pr`, `nightshift_hosts` and `nightshift_plugins`. The old names still work; rename them when convenient. The command, the skill and printed text say Work Orders; files, units, the queue folders and `nightshift.py` keep their names.
````

Edit 4 in `README.md`. Find:

````text
.claude/skills/nightshift/    /nightshift: queue plans and research briefs for unattended runs
````

Replace with:

````text
.claude/skills/order/         /order: queue plans and research briefs as Work Orders
````

Edit 5 in `README.md`. Find:

````text
  nightshift/                 session profiles for Nightshift plan and research runs
````

Replace with:

````text
  nightshift/                 session profiles for Work Order plan and research runs
````

Edit 6 in `README.md`. Find:

````text
- **Tracked in your vault, never in the template.** `system/codebases/*.md`, `system/telemetry/*.md`, `system/dtcc/map.yaml` and `raw/<partition>/nightshift/*.md` (Nightshift queue notes): your vault's own configuration and queue, committed to your private repository so a client's changes reach the server. The template ships only the `example` files. Credentials stay outside the vault (`~/.config/foundry/`, the Azure CLI).
````

Replace with:

````text
- **Tracked in your vault, never in the template.** `system/codebases/*.md`, `system/telemetry/*.md`, `system/dtcc/map.yaml` and `raw/<partition>/nightshift/*.md` (Work Order queue notes): your vault's own configuration and queue, committed to your private repository so a client's changes reach the server. The template ships only the `example` files. Credentials stay outside the vault (`~/.config/foundry/`, the Azure CLI).
````


Edit 1 in `system/schemas/codebase.md`. Find:

````text
  layers: {kind: map, of: string}
````

Replace with:

````text
  layers: {kind: map, of: string}
  order_hosts: {kind: list, of: string}
  order_plugins: {kind: list, of: string}
  order_pr: {kind: string}
````

Edit 2 in `system/schemas/codebase.md`. Find:

````text
One registered codebase, produced by `/setup` discovery and inspection. The body holds free-form notes for agents.
````

Replace with:

````text
One registered codebase, produced by `/setup` discovery and inspection. The body holds free-form notes for agents.

`nightshift_hosts`, `nightshift_plugins` and `nightshift_pr` are the old names of `order_hosts`, `order_plugins` and `order_pr`. They are still read when the new key is absent; the new key wins when both are set.
````


Edit 1 in `system/schemas/config.md`. Find:

````text
  nightshift_workspace: {kind: string}
  nightshift_window: {kind: string, default: "22:00-05:00"}
````

Replace with:

````text
  order_workspace: {kind: string}
  run_window: {kind: string, default: "22:00-05:00"}
  nightshift_workspace: {kind: string}
  nightshift_window: {kind: string}
````

Edit 2 in `system/schemas/config.md`. Find:

````text
The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.
````

Replace with:

````text
The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.

`nightshift_workspace` and `nightshift_window` are the old names of `order_workspace` and `run_window`. They are still read when the new key is absent; the new key wins when both are set.
````


Edit 1 in `system/schemas/nightshift_item.md`. Find:

````text
One unit of unattended work (Nightshift spec §4), written by `/nightshift` and updated by `system/scripts/nightshift.py`. The body is the research brief (`kind: research`) or a free note. The runner writes only `state` and the runner fields, and never changes an item the user cancelled.
````

Replace with:

````text
One Work Order, a unit of unattended work (Nightshift spec §4), written by `/order` and updated by `system/scripts/nightshift.py`. The body is the research brief (`kind: research`) or a free note. The runner writes only `state` and the runner fields, and never changes an item the user cancelled.
````


Edit 1 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
    return (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}) if path.is_file() else {}
````

Replace with:

````text
    return (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}) if path.is_file() else {}


def setting(d: dict, new: str, old: str):
    """A Work Orders setting under its new key, else its old nightshift_* key (Foreman v1 §3.1)."""
    return d[new] if new in d else d.get(old)
````

Edit 2 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
    if not (codebase(vault, repo) or {}).get("nightshift_pr"):
        errs.append(f"codebase {repo} has no nightshift_pr (github:<owner>/<repo> or bitbucket-link)")
````

Replace with:

````text
    if not setting(codebase(vault, repo) or {}, "order_pr", "nightshift_pr"):
        errs.append(f"codebase {repo} has no order_pr (github:<owner>/<repo> or bitbucket-link)")
````


Edit 1 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
    return url, str((nc.codebase(vault, fm["repo"]) or {}).get("nightshift_pr") or "")
````

Replace with:

````text
    return url, str(nc.setting(nc.codebase(vault, fm["repo"]) or {}, "order_pr", "nightshift_pr") or "")
````

Edit 2 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
    env = dict(_git_env(), GIT_INDEX_FILE=str(Path(workdir) / "protected.index"), GIT_AUTHOR_NAME="Nightshift",
               GIT_AUTHOR_EMAIL="nightshift@localhost", GIT_COMMITTER_NAME="Nightshift",
               GIT_COMMITTER_EMAIL="nightshift@localhost")
````

Replace with:

````text
    env = dict(_git_env(), GIT_INDEX_FILE=str(Path(workdir) / "protected.index"), GIT_AUTHOR_NAME="Work Orders",
               GIT_AUTHOR_EMAIL="orders@localhost", GIT_COMMITTER_NAME="Work Orders",
               GIT_COMMITTER_EMAIL="orders@localhost")
````

Edit 3 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
    return False, f"unknown nightshift_pr {pr!r}"
````

Replace with:

````text
    return False, f"unknown order_pr {pr!r}"
````


Edit 1 in `system/scripts/vaultlib/nightshift_report.py`. Find:

````text
    lines = [f"# Nightshift: {date}", "> Health: " + (" · ".join(parts) if parts else "not checked"), ""]
````

Replace with:

````text
    lines = [f"# Work Orders: {date}", "> Health: " + (" · ".join(parts) if parts else "not checked"), ""]
````


Edit 1 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        self.window = ns.parse_window(cfg.get("nightshift_window"))
        self.workspace = Path(str(cfg.get("nightshift_workspace") or "~/code/worktrees")).expanduser()
````

Replace with:

````text
        self.window = ns.parse_window(nc.setting(cfg, "run_window", "nightshift_window"))
        self.workspace = Path(str(nc.setting(cfg, "order_workspace", "nightshift_workspace") or "~/code/worktrees")).expanduser()
````

Edit 2 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
            f.write(f"- {self.local.strftime('%H:%M:%S')} [nightshift] {msg}\n")
````

Replace with:

````text
            f.write(f"- {self.local.strftime('%H:%M:%S')} [orders] {msg}\n")
````

Edit 3 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    branch = f"nightshift/{fm['id']}"
````

Replace with:

````text
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    branch = f"order/{fm['id']}"
````

Edit 4 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    hosts = list(cb.get("nightshift_hosts") or [])
````

Replace with:

````text
    hosts = list(nc.setting(cb, "order_hosts", "nightshift_hosts") or [])
````

Edit 5 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    plugins = [p for p in [ss.superpowers_dir()] if p] + [Path(str(p)).expanduser() for p in cb.get("nightshift_plugins") or []]
````

Replace with:

````text
    plugins = [p for p in [ss.superpowers_dir()] if p] + [Path(str(p)).expanduser() for p in nc.setting(cb, "order_plugins", "nightshift_plugins") or []]
````

Edit 6 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    branch = f"nightshift/{fm['id']}"
    runner = ctx.workspace / "nightshift-runner.git"
    ok, sha = nd.fetch_branch(runner, clone, branch)
````

Replace with:

````text
    branch = f"order/{fm['id']}"
    runner = ctx.workspace / "nightshift-runner.git"
    ok, sha = nd.fetch_branch(runner, clone, branch)
    if not ok:   # a clone made before the rename to Work Orders holds nightshift/<id>
        old = f"nightshift/{fm['id']}"
        ok, old_sha = nd.fetch_branch(runner, clone, old)
        branch, sha = (old, old_sha) if ok else (branch, sha)
````

Edit 7 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        body.write_text(f"{d['body']}\n\nQueued as Nightshift item `{fm['id']}`.\n")
````

Replace with:

````text
        body.write_text(f"{d['body']}\n\nQueued as Work Order `{fm['id']}`.\n")
````


Edit 1 in `system/systemd/foundry-nightshift.service.in`. Find:

````text
Description=The Foundry: Nightshift tick
````

Replace with:

````text
Description=The Foundry: Work Orders tick
````


Edit 1 in `system/systemd/foundry-nightshift.timer.in`. Find:

````text
Description=The Foundry: Nightshift tick every 15 minutes
````

Replace with:

````text
Description=The Foundry: Work Orders tick every 15 minutes
````


- [ ] **Step 5: Run the tests to verify they pass**

Run: the two commands from Step 2.
Expected: PASS, 0 failed and no `not ok`.

- [ ] **Step 6: Commit**

Write `.scratch/msg-1.txt`:

```text
feat(orders): rename the Nightshift to Work Orders for the user

/nightshift becomes /order (the skill moves to .claude/skills/order/) and
printed text says Work Orders: the report heading, the PR body line, the
protected-files commit author, the [orders] alert tag, the order_pr
messages and the unit descriptions. New PR branches are order/<id>; a
clone made before the rename still delivers its nightshift/<id> branch.

New settings keys run_window, order_workspace, order_pr, order_hosts and
order_plugins are read through nc.setting(), which falls back to the old
nightshift_* key; the new key wins when both are set. Files, units, the
schema type, the queue folders and nightshift.py keep their names.
```

Run: `git add -A .claude/skills CLAUDE.md README.md system/schemas system/scripts/vaultlib system/systemd system/tests`

Run: `git commit -q -F .scratch/msg-1.txt`

### Task 2: Start now, and the 5-hour ceiling

**Files:**
- Modify: `.claude/skills/order/SKILL.md`, `README.md`, `system/schemas/config.md`, `system/scripts/vaultlib/nightshift_report.py`, `system/scripts/vaultlib/nightshift_run.py`, `system/scripts/vaultlib/nightshift_sched.py`
- Test: `system/tests/commands.bats`, `system/tests/python/test_nightshift_run.py`, `system/tests/python/test_nightshift_sched.py`

**Interfaces:**
- Consumes: `setting` from Task 1.
- Produces: `nightshift_sched.five_hour_hold(health: dict, now: datetime, ceiling: float) -> str` (the hold reason, or `""`); `parse_window` returns an always-open window for an empty value or `00:00-24:00`; health files carry `usage5` and `usage5_at`; `add` accepts `--window`.

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/commands.bats`. Find:

````text
    grep -q "^  $k:" system/schemas/codebase.md
  done
}
````

Replace with:

````text
    grep -q "^  $k:" system/schemas/codebase.md
  done
}

@test "Work Orders start now by default; tonight, hold, the window and the 5-hour ceiling are documented (Foreman v1 §3.2)" {
  f=.claude/skills/order/SKILL.md
  grep -qF 'With no start flag a Work Order starts now.' "$f"
  grep -qF '"tonight" means `--at 22:00`' "$f"
  grep -qF '"hold" means do not queue' "$f"
  grep -qF -- '`--window`' "$f"
  grep -q '^  order_max_five_hour: {kind: string, default: "0.6"}$' system/schemas/config.md
  grep -q '^  run_window: {kind: string}$' system/schemas/config.md
  grep -qF '`order_max_five_hour`' README.md
  grep -qF 'By default `run_window` is empty and the window is always open' README.md
}
````


Edit 1 in `system/tests/python/test_nightshift_run.py`. Find:

````text
from datetime import datetime, timezone
````

Replace with:

````text
from datetime import datetime, timedelta, timezone
````

Edit 2 in `system/tests/python/test_nightshift_run.py`. Find:

````text
          f"template_remote: \"{remote}\"\nnightshift_workspace: \"{tmp_path / 'ws'}\"\n---\n")
````

Replace with:

````text
          f"template_remote: \"{remote}\"\nnightshift_workspace: \"{tmp_path / 'ws'}\"\nrun_window: \"22:00-05:00\"\n---\n")
````

Edit 3 in `system/tests/python/test_nightshift_run.py`. Find:

````text
def test_window_item_waits_in_daytime(env):
    vault, _ = env
    assert add(vault) == 0
````

Replace with:

````text
def test_window_item_waits_in_daytime(env):
    vault, _ = env
    assert add(vault, "--window") == 0
````

Edit 4 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert "[orders] something broke" in text and "[nightshift]" not in text
````

Replace with:

````text
    assert "[orders] something broke" in text and "[nightshift]" not in text


def test_add_starts_now_unless_told_otherwise(env):
    vault, _ = env
    assert add(vault) == 0
    path, fm = only_item(vault)
    assert fm["start"] == "now"
    path.unlink()
    assert add(vault, "--window") == 0
    assert only_item(vault)[1]["start"] == "window"


def test_a_finished_session_stores_the_five_hour_usage(env, monkeypatch, tmp_path):
    vault, _ = env
    empty = tmp_path / "none.txt"
    empty.write_text("")
    monkeypatch.setenv("NIGHTSHIFT_STUB_WRITE", str(empty))
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", "true")
    assert add(vault) == 0
    nr.main(["tick"], vault, NOW)
    h = json.loads((vault / "system/logs/nightshift/health-2026-10-07.json").read_text())
    assert (h["usage5"], h["usage7"]) == (0.12, 0.48)
    assert NOW <= datetime.fromisoformat(h["usage5_at"]) < NOW + timedelta(minutes=5)


def health_at(vault, usage5, age_hours, date="2026-10-07"):
    nr.rep.write_health(vault, date, {"claude": "ok", "sandbox": "ok", "usage5": usage5,
                                      "usage5_at": (NOW - timedelta(hours=age_hours)).isoformat()})


def test_a_hold_reaches_the_report_file_the_brief_copies(env):
    vault, _ = env
    assert add(vault) == 0
    health_at(vault, 0.7, 1)
    nr.main(["tick"], vault, NOW)
    assert "> Held: 5-hour usage 70% at or above 60%" in (vault / nr.rep.DIR / "2026-10-07.md").read_text()


def test_a_new_report_day_keeps_the_last_five_hour_reading(env):
    vault, _ = env
    assert add(vault) == 0
    health_at(vault, 0.7, 1, date="2026-10-06")   # read by the last session before the brief
    nr.main(["tick"], vault, NOW)
    assert only_item(vault)[1]["state"] == "queued"
    assert "> Held: 5-hour usage 70%" in (vault / nr.rep.DIR / "2026-10-07.md").read_text()


def test_the_five_hour_ceiling_holds_a_new_item_and_says_why(env, capsys):
    vault, _ = env
    assert add(vault) == 0
    health_at(vault, 0.7, 1)
    assert nr.main(["tick"], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "queued"
    nr.main(["report"], vault, NOW)
    assert "> Held: 5-hour usage 70% at or above 60%" in capsys.readouterr().out


@pytest.mark.parametrize("age,config", [(6, ""), (1, 'order_max_five_hour: "0.8"\n')])
def test_an_old_reading_or_a_higher_ceiling_lets_it_start(env, monkeypatch, capsys, age, config):
    vault, _ = env
    if config:
        cfg = vault / "system/config.md"
        cfg.write_text(cfg.read_text().rsplit("---\n", 1)[0] + config + "---\n")
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(FX / "limited.jsonl"))
    assert add(vault) == 0
    health_at(vault, 0.7, age)
    nr.main(["tick"], vault, NOW)
    assert only_item(vault)[1]["state"] == "waiting_reset"
    nr.main(["report"], vault, NOW)
    assert "Held" not in capsys.readouterr().out


@pytest.mark.parametrize("state", ["running", "waiting_reset"])
def test_the_five_hour_ceiling_never_stops_an_item_already_started(env, monkeypatch, state):
    vault, _ = env
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(FX / "limited.jsonl"))
    assert add(vault) == 0
    path, _ = only_item(vault)
    ni.update(path, state=state, attempts="1", session_id="old", reset_at=(NOW - timedelta(hours=1)).isoformat())
    health_at(vault, 0.9, 1)
    nr.main(["tick"], vault, NOW)
    assert only_item(vault)[1]["attempts"] == "2"
````


Edit 1 in `system/tests/python/test_nightshift_sched.py`. Find:

````text
    assert not hasattr(ns, "idle_seconds")
````

Replace with:

````text
    assert not hasattr(ns, "idle_seconds")


def test_an_empty_or_full_day_run_window_is_always_open():
    for text in (None, "", "00:00-24:00"):
        w = ns.parse_window(text)
        assert ns.due(item(), at(12), w, 0.4) == (True, "")
        assert ns.due(item(budget="20h"), at(4), w, 0.4) == (True, "")
        assert ns.due(item(), at(12), w, 0.9) == (False, "7-day usage above 80%")
    assert ns.due(item(), at(12), W, 0.4) == (False, "outside the window")   # a set window is kept


def test_five_hour_hold():
    h = {"usage5": 0.7, "usage5_at": at(11).isoformat()}
    assert ns.five_hour_hold(h, at(12), 0.6) == "5-hour usage 70% at or above 60%"
    assert ns.five_hour_hold({**h, "usage5": 0.6}, at(12), 0.6) == "5-hour usage 60% at or above 60%"
    assert ns.five_hour_hold({**h, "usage5": 0.59}, at(12), 0.6) == ""
    assert ns.five_hour_hold({**h, "usage5_at": at(6, 59).isoformat()}, at(12), 0.6) == ""   # the window has reset
    assert ns.five_hour_hold(h, at(12), 0.8) == ""
    assert ns.five_hour_hold({}, at(12), 0.6) == ""
````


- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_nightshift_run.py system/tests/python/test_nightshift_sched.py`
Expected: FAIL, 11 failed. (The `[running]` case of `test_the_five_hour_ceiling_never_stops_an_item_already_started` passes already: it guards today's behavior.)

Run: `bats system/tests/commands.bats`
Expected: FAIL, 1 `not ok`.

- [ ] **Step 3: Implement**

Edit 1 in `.claude/skills/order/SKILL.md`. Find:

````text
**`/order add <plan> [--tasks N-M] [--at HH:MM | --now] [--budget 4h] [--model opus]`**
1. Find the plan's repository: a registered codebase (`system/codebases/*.md`) or `template` (this repository's template remote). Ask if unclear. For `template`, the branch that holds the plan must be pushed to the template remote first: the check and the run read it from there, never from the vault, and `--base` is that branch's name.
2. Read the plan (for `template`: `git fetch -q template <branch>`, then `git show FETCH_HEAD:<plan path>`). Propose `--verify` commands from its test lines (its Global Constraints or the last task's suite run) and a `--tasks` range that leaves out any task on the vault's `master`, a deploy, or a step needing the user. Show both and get the user's yes.
3. Run `system/scripts/nightshift.py add --kind plan --title "<plan title>" --partition <partition> --repo <repo> --base <branch holding the plan> --pr-base <target branch> --plan <path> --tasks <range> --verify "<cmd>" … [--now | --at HH:MM] [--budget] [--model]`. Exit 2 lists what is not ready: report it and stop.

**`/order ask`**: draft the brief with the user, one question at a time, until it has `## Question`, `## Scope` (sources and any web hosts), `## Done when` and `## Output` (the findings note, a new path under `wiki/<partition>/`; research creates new notes only). When the question is about code, ask which repository (a registered codebase or `template`) and which branch or commit (a branch for `template`); the session reads a pinned copy under `code/`, at the remote's default branch when no base is named. Save the brief to a temporary file, then run `nightshift.py add --kind research --title "…" --partition <p> --brief-file <file> --output <path> --host <h> … [--repo <name> [--base <branch or commit>]] [--now | --at]`.
````

Replace with:

````text
**`/order add <plan> [--tasks N-M] [--at HH:MM | --window] [--budget 4h] [--model opus]`**

With no start flag a Work Order starts now. "tonight" means `--at 22:00`; "hold" means do not queue (tell the user the plan is not queued); `--window` waits for the vault's `run_window`. A new Work Order also waits while the last session's 5-hour usage is at or above `order_max_five_hour` (default 0.6); `status` shows that hold.

1. Find the plan's repository: a registered codebase (`system/codebases/*.md`) or `template` (this repository's template remote). Ask if unclear. For `template`, the branch that holds the plan must be pushed to the template remote first: the check and the run read it from there, never from the vault, and `--base` is that branch's name.
2. Read the plan (for `template`: `git fetch -q template <branch>`, then `git show FETCH_HEAD:<plan path>`). Propose `--verify` commands from its test lines (its Global Constraints or the last task's suite run) and a `--tasks` range that leaves out any task on the vault's `master`, a deploy, or a step needing the user. Show both and get the user's yes.
3. Run `system/scripts/nightshift.py add --kind plan --title "<plan title>" --partition <partition> --repo <repo> --base <branch holding the plan> --pr-base <target branch> --plan <path> --tasks <range> --verify "<cmd>" … [--at HH:MM | --window] [--budget] [--model]`. Exit 2 lists what is not ready: report it and stop.

**`/order ask`**: draft the brief with the user, one question at a time, until it has `## Question`, `## Scope` (sources and any web hosts), `## Done when` and `## Output` (the findings note, a new path under `wiki/<partition>/`; research creates new notes only). When the question is about code, ask which repository (a registered codebase or `template`) and which branch or commit (a branch for `template`); the session reads a pinned copy under `code/`, at the remote's default branch when no base is named. Save the brief to a temporary file, then run `nightshift.py add --kind research --title "…" --partition <p> --brief-file <file> --output <path> --host <h> … [--repo <name> [--base <branch or commit>]] [--at HH:MM | --window]`.
````


Edit 1 in `README.md`. Find:

````text
**Work Orders.** `/order` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time: in the run window (`run_window`, default `22:00-05:00`), at a set time, or now. A plan item runs in a private clone under `order_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The report, `system/logs/nightshift/<date>.md` (heading `# Work Orders: <date>`), starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server. A plan item for this template is read from `template_remote`: push its branch there before queuing it, and queuing checks the remote, which needs the network and the remote's credentials. Settings renamed with Work Orders: `run_window` was `nightshift_window`, `order_workspace` was `nightshift_workspace`, and a codebase's `order_pr`, `order_hosts` and `order_plugins` were `nightshift_pr`, `nightshift_hosts` and `nightshift_plugins`. The old names still work; rename them when convenient. The command, the skill and printed text say Work Orders; files, units, the queue folders and `nightshift.py` keep their names.
````

Replace with:

````text
**Work Orders.** `/order` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time. A Work Order starts now unless it was queued for a set time (`--at`) or for the run window (`--window`, the `run_window` setting). By default `run_window` is empty and the window is always open; a vault that sets one, such as `22:00-05:00`, keeps it. No new Work Order starts while the last session's 5-hour usage is at or above `order_max_five_hour` (default `0.6`) and that reading is under 5 hours old; a running one carries on, and `/order status` shows the hold. A plan item runs in a private clone under `order_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The report, `system/logs/nightshift/<date>.md` (heading `# Work Orders: <date>`), starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server. A plan item for this template is read from `template_remote`: push its branch there before queuing it, and queuing checks the remote, which needs the network and the remote's credentials. Settings renamed with Work Orders: `run_window` was `nightshift_window`, `order_workspace` was `nightshift_workspace`, and a codebase's `order_pr`, `order_hosts` and `order_plugins` were `nightshift_pr`, `nightshift_hosts` and `nightshift_plugins`. The old names still work; rename them when convenient. The command, the skill and printed text say Work Orders; files, units, the queue folders and `nightshift.py` keep their names.
````


Edit 1 in `system/schemas/config.md`. Find:

````text
  run_window: {kind: string, default: "22:00-05:00"}
````

Replace with:

````text
  run_window: {kind: string}
  order_max_five_hour: {kind: string, default: "0.6"}
````

Edit 2 in `system/schemas/config.md`. Find:

````text
The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.

````

Replace with:

````text
The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.

`run_window` is the window for Work Orders queued with `--window`, as `HH:MM-HH:MM`; empty (the default) or `00:00-24:00` means always. `order_max_five_hour` is the 5-hour usage fraction at or above which no new Work Order starts.

````


Edit 1 in `system/scripts/vaultlib/nightshift_report.py`. Find:

````text
    lines = [f"# Work Orders: {date}", "> Health: " + (" · ".join(parts) if parts else "not checked"), ""]
````

Replace with:

````text
    lines = [f"# Work Orders: {date}", "> Health: " + (" · ".join(parts) if parts else "not checked"),
             *([f"> Held: {health['held']}"] if health.get("held") else []), ""]
````


Edit 1 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
from datetime import datetime, timedelta, timezone
````

Replace with:

````text
from datetime import date, datetime, timedelta, timezone
````

Edit 2 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    g.add_argument("--at", metavar="HH:MM")
````

Replace with:

````text
    g.add_argument("--at", metavar="HH:MM")
    g.add_argument("--window", action="store_true")
````

Edit 3 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        self.workspace = Path(str(nc.setting(cfg, "order_workspace", "nightshift_workspace") or "~/code/worktrees")).expanduser()
````

Replace with:

````text
        self.workspace = Path(str(nc.setting(cfg, "order_workspace", "nightshift_workspace") or "~/code/worktrees")).expanduser()
        try:
            self.max_five_hour = float(cfg.get("order_max_five_hour") or 0.6)
        except (TypeError, ValueError):
            self.max_five_hour = 0.6
````

Edit 4 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
                f"Make {fm.get('base') or 'the default branch'} of {fm['repo']} readable, then queue {fm['id']} again ({exc})"]})
````

Replace with:

````text
                f"Make {fm.get('base') or 'the default branch'} of {fm['repo']} readable, then queue {fm['id']} again ({exc})"]})
    t0 = clock.monotonic()
````

Edit 5 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        h["usage7"] = u.get("seven_day")
````

Replace with:

````text
        h["usage7"] = u.get("seven_day")
        h["usage5"] = u.get("five_hour")
        h["usage5_at"] = (ctx.now + timedelta(seconds=clock.monotonic() - t0)).isoformat()
````

Edit 6 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        h = health(ctx.vault, ctx.now, entries)
````

Replace with:

````text
        h = health(ctx.vault, ctx.now, entries)
        prev = ctx.vault / rep.DIR / f"health-{(date.fromisoformat(ctx.date) - timedelta(days=1)).isoformat()}.json"
        try:   # the last 5-hour reading outlives the report day, so the ceiling holds right after the brief too
            old = json.loads(prev.read_text()) if prev.is_file() else {}
        except (OSError, ValueError):
            old = {}
        h |= {k: old[k] for k in ("usage5", "usage5_at") if k in old}
````

Edit 7 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    if not chosen:
````

Replace with:

````text
    # The 5-hour ceiling holds only a new start: running and waiting_reset items resume (pick ranks those first).
    held = ns.five_hour_hold(h, ctx.now, ctx.max_five_hour) if chosen and chosen[1].get("state") == "queued" else ""
    if h.pop("held", None) or held:   # the report's Held line shows only the latest tick's hold
        rep.write_health(ctx.vault, ctx.date, h | ({"held": held} if held else {}))
        rep.write(ctx.vault, ctx.date)   # the brief and the debrief copy this file, so the Held line must be in it
    if held or not chosen:
````

Edit 8 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
          "queued_at": ctx.local.isoformat(), "start": "now" if a.now else ("at" if a.at else "window"),
````

Replace with:

````text
          "queued_at": ctx.local.isoformat(), "start": "at" if a.at else ("window" if a.window else "now"),
````


Edit 1 in `system/scripts/vaultlib/nightshift_sched.py`. Find:

````text


def parse_window(text) -> tuple:
    a, b = str(text or "22:00-05:00").split("-")
    return time.fromisoformat(a.strip()), time.fromisoformat(b.strip())
````

Replace with:

````text
FIVE_HOURS = timedelta(hours=5)


def parse_window(text) -> tuple | None:
    """(start, end), or None for a window that is always open: empty or 00:00-24:00 (Foreman v1 §3.2)."""
    text = str(text or "").replace(" ", "")
    if text in ("", "00:00-24:00"):
        return None
    a, b = text.split("-")
    return time.fromisoformat(a), time.fromisoformat(b)
````

Edit 2 in `system/scripts/vaultlib/nightshift_sched.py`. Find:

````text
    if not in_window(now_local.time(), *window):
        return False, "outside the window"
    budget = ni.budget_seconds(fm.get("budget") or ("4h" if fm.get("kind") == "plan" else "1h"))
    if now_local + timedelta(seconds=budget) > window_end(now_local, *window):
        return False, "budget does not fit before the window ends"
````

Replace with:

````text
    if window is not None:
        if not in_window(now_local.time(), *window):
            return False, "outside the window"
        budget = ni.budget_seconds(fm.get("budget") or ("4h" if fm.get("kind") == "plan" else "1h"))
        if now_local + timedelta(seconds=budget) > window_end(now_local, *window):
            return False, "budget does not fit before the window ends"
````

Edit 3 in `system/scripts/vaultlib/nightshift_sched.py`. Find:

````text
    return ready[0] if ready else None


````

Replace with:

````text
    return ready[0] if ready else None


def five_hour_hold(health: dict, now: datetime, ceiling: float) -> str:
    """Why no new item may start: the last session's 5-hour usage is at or above the ceiling and under 5 hours old."""
    u, at = health.get("usage5"), health.get("usage5_at")
    try:
        recent = u is not None and now - _dt(at) < FIVE_HOURS
    except (TypeError, ValueError):
        return ""
    return f"5-hour usage {round(u * 100)}% at or above {round(ceiling * 100)}%" if recent and u >= ceiling else ""


````


- [ ] **Step 4: Run the tests to verify they pass**

Run: the two commands from Step 2.
Expected: PASS, 0 failed and no `not ok`.

- [ ] **Step 5: Commit**

Write `.scratch/msg-2.txt`:

```text
feat(orders): start Work Orders now and hold new starts at a 5-hour ceiling

/order add starts now by default; --window asks for the run window and
--at stays. run_window defaults to always open (empty or 00:00-24:00); a
vault that sets a window keeps it, and the 7-day check for window items
stays.

After each finished session the runner stores usage5 and usage5_at next
to usage7 in the health file. A tick starts no new item while usage5 is
at or above order_max_five_hour (default 0.6) and the reading is under 5
hours old. Running, waiting_reset and delivering items are not held. The
report shows the hold as a "> Held:" line, written to the report file the
brief and the debrief copy. A new report day's health file keeps the last
5-hour reading, so the ceiling also holds right after the brief.
```

Run: `git add .claude/skills/order/SKILL.md README.md system/schemas/config.md system/scripts/vaultlib system/tests`

Run: `git commit -q -F .scratch/msg-2.txt`

### Task 3: Approval queues the order; brief, debrief and the Foreman report it

**Files:**
- Modify: `.claude/commands/brief.md`, `.claude/commands/debrief.md`, `CLAUDE.md`, `README.md`, `docs/superpowers/roadmap.md`, `system/agents/foreman.md`, `system/scripts/brief_prep.sh`, `system/scripts/debrief_prep.sh`, `system/templates/daily-debrief.md`
- Test: `system/tests/commands.bats`, `system/tests/prep.bats`

**Interfaces:**
- Consumes: the report heading from Task 1 and the Held line from Task 2.
- Produces: `system/logs/inputs/<date>/orders.md` (the open report, copied by `debrief_prep.sh`).

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'By default `run_window` is empty and the window is always open' README.md
}
````

Replace with:

````text
  grep -qF 'By default `run_window` is empty and the window is always open' README.md
}

@test "the brief and the debrief report Work Orders (Foreman v1 §3.4)" {
  b=.claude/commands/brief.md
  grep -qF -- '- **🛠 Work Orders:** the `## Items` table from `nightshift.md` verbatim' "$b"
  grep -qF 'Then **Work Orders**: every `- [ ] ` line under "## Needs you" in `nightshift.md`, verbatim' "$b"
  run grep -nE 'Overnight|Nightshift' "$b"
  [ "$status" -eq 1 ]
  d=.claude/commands/debrief.md
  grep -qF 'system/logs/inputs/<date>/orders.md' "$d"
  grep -qF -- '- **5. Work Orders:** the `## Items` table and every `- [ ] ` line under "## Needs you" from `orders.md`' "$d"
  grep -qF 'No Work Orders ran today.' "$d"
  grep -qx '### 5. Work Orders' system/templates/daily-debrief.md
  [ "$(grep -n '^### ' system/templates/daily-debrief.md | tail -n 1)" = "$(grep -n '^### 5. Work Orders$' system/templates/daily-debrief.md)" ]
}

# commands_section: the body of CLAUDE.md's Commands section.
commands_section() { awk '$0 == "## Commands" { on = 1; next } /^## / { on = 0 } on' CLAUDE.md; }

@test "CLAUDE.md Commands: an approved plan becomes a Work Order that starts now (Foreman v1 §3.3)" {
  sec="$(commands_section)"
  [[ "$sec" == *'When the user approves a plan and names no execution method, the plan runs as a Work Order that starts now.'* ]]
  [[ "$sec" == *'"native" or "subagent" runs it in the session; "tonight" queues it for 22:00; "hold" leaves it unqueued.'* ]]
  [[ "$sec" == *'In the vault, run `/order add` (the skill shows the readiness result).'* ]]
  [[ "$sec" == *"In any other repository, push the plan's branch and send the exact \`system/scripts/nightshift.py add\` command to the Foreman session by cross-session message."* ]]
}

@test "the Foreman owns the Work Order queue; the README asks for one permission mode (Foreman v1 §3.5)" {
  f=system/agents/foreman.md
  [ "$(head -n 1 "$f")" = '# The Foreman' ]
  grep -qF -- '- **Work Orders**: You own the Work Order queue.' "$f"
  grep -qF 'You take approved plans handed over by design sessions and queue them with `/order add`' "$f"
  grep -qF 'report them in the brief and the debrief' "$f"
  grep -qF 'Run the Foreman session and your design sessions in the same permission mode' README.md
}
````


Edit 1 in `system/tests/prep.bats`. Find:

````text
  grep -qx -- '- debrief_prep: focus: no focus log for 2026-10-01' "$IN/unavailable.md"
````

Replace with:

````text
  grep -qx -- '- debrief_prep: focus: no focus log for 2026-10-01' "$IN/unavailable.md"
}

@test "debrief_prep: orders.md copies the open Work Orders report, empty when there is none" {
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ -e "$IN/orders.md" ] && [ ! -s "$IN/orders.md" ]
  mkdir -p system/logs/nightshift
  # The morning's report closed at brief time; everything after it lands in the next day's report.
  printf '# Work Orders: 2026-10-01\n> Health: claude ok\n\nNothing ran.\n' > system/logs/nightshift/2026-10-01.md
  printf '# Work Orders: 2026-10-02\n> Health: claude ok\n\n## Items\n' > system/logs/nightshift/2026-10-02.md
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(head -n 1 "$IN/orders.md")" = '# Work Orders: 2026-10-02' ]
````


- [ ] **Step 2: Run them to verify they fail**

Run: `bats system/tests/commands.bats system/tests/prep.bats`
Expected: FAIL, 4 `not ok`.

- [ ] **Step 3: Implement**

Edit 1 in `.claude/commands/brief.md`. Find:

````text
- `system/logs/inputs/<date>/nightshift.md`: the Nightshift's report for this morning (empty when nothing ran).
````

Replace with:

````text
- `system/logs/inputs/<date>/nightshift.md`: the Work Orders report for this morning (empty when nothing ran).
````

Edit 2 in `.claude/commands/brief.md`. Find:

````text
- **🌅 Morning Alignment → Active Objectives:** today's fixed commitments from the calendar, then **Carried forward**: every line of `carried.md` verbatim, in its order, with its age in days after the date ("_(open since 2026-10-06, 3 days)_"), and "**stale**" before the item when it is 7 or more days old; omit the heading when `carried.md` is empty. Then **DTCC changes**: every line of `dtcc.md` verbatim, in its order; omit the heading when `dtcc.md` is empty. These lines are not among the 3–5 new objectives. Then **Nightshift**: every `- [ ] ` line under "## Needs you" in `nightshift.md`, verbatim; omit the heading when there are none. Then **New objectives**: 3–5 objectives as `- [ ] ` checkboxes, none repeating a carried item. The user ticks `[x]` when done or `[-]` to drop; ticked items do not carry. Tie each to a superpower from config where one fits, and hand each concrete slice to a capability: one of the `capability` values in `system/schemas/concept.md` (the Workcell that declares it does the work). Then list your open meeting actions from `actions.md` (**Yours**) with their meeting links and days open, and then a **Waiting on** block with everyone else's, by owner.
````

Replace with:

````text
- **🌅 Morning Alignment → Active Objectives:** today's fixed commitments from the calendar, then **Carried forward**: every line of `carried.md` verbatim, in its order, with its age in days after the date ("_(open since 2026-10-06, 3 days)_"), and "**stale**" before the item when it is 7 or more days old; omit the heading when `carried.md` is empty. Then **DTCC changes**: every line of `dtcc.md` verbatim, in its order; omit the heading when `dtcc.md` is empty. These lines are not among the 3–5 new objectives. Then **Work Orders**: every `- [ ] ` line under "## Needs you" in `nightshift.md`, verbatim; omit the heading when there are none. Then **New objectives**: 3–5 objectives as `- [ ] ` checkboxes, none repeating a carried item. The user ticks `[x]` when done or `[-]` to drop; ticked items do not carry. Tie each to a superpower from config where one fits, and hand each concrete slice to a capability: one of the `capability` values in `system/schemas/concept.md` (the Workcell that declares it does the work). Then list your open meeting actions from `actions.md` (**Yours**) with their meeting links and days open, and then a **Waiting on** block with everyone else's, by owner.
````

Edit 3 in `.claude/commands/brief.md`. Find:

````text
- **🌙 Overnight:** the `## Items` table from `nightshift.md` verbatim, or omit the section when the file is empty or says "Nothing ran."
````

Replace with:

````text
- **🛠 Work Orders:** the `## Items` table from `nightshift.md` verbatim, or omit the section when the file is empty or says "Nothing ran."
````


Edit 1 in `.claude/commands/debrief.md`. Find:

````text
- `system/logs/inputs/<date>/focus.md`: top notes and Focus Fragmentation Warnings.
````

Replace with:

````text
- `system/logs/inputs/<date>/focus.md`: top notes and Focus Fragmentation Warnings.
- `system/logs/inputs/<date>/orders.md`: the open Work Orders report, which collects everything since this morning's brief (empty when nothing ran).
````

Edit 2 in `.claude/commands/debrief.md`. Find:

````text
- **4. Unavailable Sources:** one bullet per missing source, or "None."
````

Replace with:

````text
- **4. Unavailable Sources:** one bullet per missing source, or "None."
- **5. Work Orders:** the `## Items` table and every `- [ ] ` line under "## Needs you" from `orders.md`, verbatim, and its Held line when there is one. Write "No Work Orders ran today." when the file is empty or says "Nothing ran." When an existing debrief has no 5. Work Orders section, add it at the end.
````


Edit 1 in `CLAUDE.md`. Find:

````text
- `/setup`: interactive onboarding; safe to re-run.
````

Replace with:

````text
- `/setup`: interactive onboarding; safe to re-run.
- **Approved plans:** When the user approves a plan and names no execution method, the plan runs as a Work Order that starts now. "native" or "subagent" runs it in the session; "tonight" queues it for 22:00; "hold" leaves it unqueued. In the vault, run `/order add` (the skill shows the readiness result). In any other repository, push the plan's branch and send the exact `system/scripts/nightshift.py add` command to the Foreman session by cross-session message.
````


Edit 1 in `README.md`. Find:

````text
**Work Orders.** `/order` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time. A Work Order starts now unless it was queued for a set time (`--at`) or for the run window (`--window`, the `run_window` setting). By default `run_window` is empty and the window is always open; a vault that sets one, such as `22:00-05:00`, keeps it. No new Work Order starts while the last session's 5-hour usage is at or above `order_max_five_hour` (default `0.6`) and that reading is under 5 hours old; a running one carries on, and `/order status` shows the hold. A plan item runs in a private clone under `order_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The report, `system/logs/nightshift/<date>.md` (heading `# Work Orders: <date>`), starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server. A plan item for this template is read from `template_remote`: push its branch there before queuing it, and queuing checks the remote, which needs the network and the remote's credentials. Settings renamed with Work Orders: `run_window` was `nightshift_window`, `order_workspace` was `nightshift_workspace`, and a codebase's `order_pr`, `order_hosts` and `order_plugins` were `nightshift_pr`, `nightshift_hosts` and `nightshift_plugins`. The old names still work; rename them when convenient. The command, the skill and printed text say Work Orders; files, units, the queue folders and `nightshift.py` keep their names.
````

Replace with:

````text
**Work Orders.** `/order` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time. A Work Order starts now unless it was queued for a set time (`--at`) or for the run window (`--window`, the `run_window` setting). By default `run_window` is empty and the window is always open; a vault that sets one, such as `22:00-05:00`, keeps it. No new Work Order starts while the last session's 5-hour usage is at or above `order_max_five_hour` (default `0.6`) and that reading is under 5 hours old; a running one carries on, and `/order status` shows the hold. Design sessions (brainstorm, spec, plan) hand an approved plan to the Foreman session, which queues it with `/order add`. Run the Foreman session and your design sessions in the same permission mode, so a handoff is not held for approval. A plan item runs in a private clone under `order_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The report, `system/logs/nightshift/<date>.md` (heading `# Work Orders: <date>`), starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server. A plan item for this template is read from `template_remote`: push its branch there before queuing it, and queuing checks the remote, which needs the network and the remote's credentials. Settings renamed with Work Orders: `run_window` was `nightshift_window`, `order_workspace` was `nightshift_workspace`, and a codebase's `order_pr`, `order_hosts` and `order_plugins` were `nightshift_pr`, `nightshift_hosts` and `nightshift_plugins`. The old names still work; rename them when convenient. The command, the skill and printed text say Work Orders; files, units, the queue folders and `nightshift.py` keep their names.
````

Edit 2 in `README.md`. Find:

````text
**Debrief inputs.** The prep files in `system/logs/inputs/<date>/` (git commits, session digests, focus), alerts, the run ledger `system/logs/runs-<YYYY-MM>.jsonl`, the telemetry run log `system/logs/telemetry-<YYYY-MM>.jsonl`, and agent metrics in `system/logs/metrics/*.json`. An agent whose 3 most recent metric files all show `test_suite_passed: false` is reported under Agent Health; the debrief does not act on it.
````

Replace with:

````text
**Debrief inputs.** The prep files in `system/logs/inputs/<date>/` (git commits, session digests, focus, and `orders.md`, the open Work Orders report), alerts, the run ledger `system/logs/runs-<YYYY-MM>.jsonl`, the telemetry run log `system/logs/telemetry-<YYYY-MM>.jsonl`, and agent metrics in `system/logs/metrics/*.json`. An agent whose 3 most recent metric files all show `test_suite_passed: false` is reported under Agent Health; the debrief does not act on it.
````


Edit 1 in `docs/superpowers/roadmap.md`. Find:

````text
| **Delivered work and commitments** | Issues #79, #28 (commitments) | One design (user, 2026-10-08): a delivered list in the debrief, handoffs with ticket status, a weekly rollup, and #28's commitments ledger. A handoff is a commitment owed to the user with a ticket attached | Grill first. Needs the work-data boundary decision from #28 (all partitions sync to one private origin) |
| **Delivery notifications** | Issue #28 (delivery) | A deterministic notice after the brief and the debrief (none, desktop, ntfy or Slack); today a failed brief is silent | Grill first |
| **Ingest evals** | Issue #28 (evals) | A golden set of ingest cases scored by deterministic checks; each new Workcell ships with one | Grill first |
| **RCA-to-Jira, phase 1** | Own brainstorm → spec → plan | An attended `/rca` procedure with three entries (an error-group note, an existing Jira key, a described symptom), a `jira_draft` note the user approves, and a filer that is the only Jira writer. Vault-specific values (project, assignee) are settings. Phase 2 runs investigations unattended inside Sub-project 2 | After delivered work and commitments (#79 tracks the tickets RCA files); grill first |
````

Replace with:

````text
| **Delivered work and handoffs** | Issue #79; `2026-10-08-delivered-work-design.md` | Grilled (user, 2026-10-08). Handoffs are read live from Jira (reported by the owner, assigned to someone else; the finding's source is a Jira label) through the confined connector fetch; the vault keeps keys and links only. The brief lists handoffs with no status change in 5 working days; the debrief lists what was delivered (digest "Delivered" sections, a `log:` command, pull requests and reviews from `gh`, new handoffs); Friday's debrief adds a weekly rollup. Cut: #28's commitments ledger and the after-fix error count (it goes with RCA-to-Jira) | Spec approved (2026-10-08); plan after Foreman v1 |
| **Delivery notifications** | Issue #28 (delivery) | A deterministic notice after the brief and the debrief (none, desktop, ntfy or Slack); today a failed brief is silent | Grill first |
| **Ingest evals** | Issue #28 (evals) | A golden set of ingest cases scored by deterministic checks; each new Workcell ships with one | Grill first |
| **RCA-to-Jira, phase 1** | Own brainstorm → spec → plan | An attended `/rca` procedure with three entries (an error-group note, an existing Jira key, a described symptom), a `jira_draft` note the user approves, and a filer that is the only Jira writer. Vault-specific values (project, assignee) are settings. Phase 2 runs investigations unattended inside Sub-project 2 | After delivered work and handoffs (#79 tracks the tickets RCA files; RCA reuses its Jira fetch); grill first |
````

Edit 2 in `docs/superpowers/roadmap.md`. Find:

````text
**Next, in order of value** (user, 2026-10-08): Foreman v1 (Work Orders); delivered work and commitments (#79, #28); RCA-to-Jira phase 1; delivery notifications; ingest evals; then the reorganization (#62). In parallel as unattended runs: the `/ingest` preference notes (queued) and Notes to the wiki (#61). A new idea, or a row not yet specified, gets a grilling session (is it worth building, and what is its smallest version) before its brainstorm. Plans 5 and 7 wait for a few weeks of real use; Plan 5 also needs the preference notes. Plan 12 runs in its own session. Require-plan stays parked.
````

Replace with:

````text
**Next, in order of value** (user, 2026-10-08): Foreman v1 (Work Orders); delivered work and handoffs (#79); RCA-to-Jira phase 1; delivery notifications; ingest evals; then the reorganization (#62). In parallel as unattended runs: the `/ingest` preference notes (queued) and Notes to the wiki (#61). A new idea, or a row not yet specified, gets a grilling session (is it worth building, and what is its smallest version) before its brainstorm. Plans 5 and 7 wait for a few weeks of real use; Plan 5 also needs the preference notes. Plan 12 runs in its own session. Require-plan stays parked.
````


Edit 1 in `system/agents/foreman.md`. Find:

````text
- **Core Domain**: You own `briefings/`: the morning briefing (`/brief`), the evening debrief (`/debrief`) and the agenda. You hand concrete work to the Workcell whose `capabilities` include the one the work needs (read `system/agents/workcells/*.md`).
````

Replace with:

````text
- **Core Domain**: You own `briefings/`: the morning briefing (`/brief`), the evening debrief (`/debrief`) and the agenda. You hand concrete work to the Workcell whose `capabilities` include the one the work needs (read `system/agents/workcells/*.md`).
- **Work Orders**: You own the Work Order queue. You take approved plans handed over by design sessions and queue them with `/order add`; the readiness check refuses a plan that is not ready. You report them in the brief and the debrief, and `/order status` shows the queue at any time.
````


Edit 1 in `system/scripts/brief_prep.sh`. Find:

````text
# The Nightshift's report for this morning (Nightshift spec §6); empty when nothing ran.
````

Replace with:

````text
# The Work Orders report for this morning (Nightshift spec §6); empty when nothing ran.
````


Edit 1 in `system/scripts/debrief_prep.sh`. Find:

````text
prep_write digests.md digests_md || prep_unavailable "digests: index query failed (see $PREP_DIR/prep_errors.log)"

````

Replace with:

````text
prep_write digests.md digests_md || prep_unavailable "digests: index query failed (see $PREP_DIR/prep_errors.log)"

# The open Work Orders report (Foreman v1 §3.4): everything after this morning's brief lands in the next day's
# report, so the debrief for a date reads the report dated one day later. Empty when nothing ran.
open_report="system/logs/nightshift/$(date -d "$PREP_DATE +1 day" +%F).md"
if [[ -f "$open_report" ]]; then
  prep_write orders.md cat "$open_report" || prep_unavailable "orders: report unreadable"
else
  : > "$PREP_DIR/orders.md"
fi

````


Edit 1 in `system/templates/daily-debrief.md`. Find:

````text
### 4. Unavailable Sources
````

Replace with:

````text
### 4. Unavailable Sources

### 5. Work Orders
````


- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2.
Expected: PASS, no `not ok`.

- [ ] **Step 5: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 6: Commit**

Write `.scratch/msg-3.txt`:

```text
feat(orders): approved plans become Work Orders; brief, debrief and Foreman report them

CLAUDE.md gains the approval rule: a plan approved with no execution
method runs as a Work Order that starts now; native or subagent runs in
the session, tonight queues for 22:00, hold leaves it unqueued. Outside
the vault a session pushes the plan's branch and sends the nightshift.py
add command to the Foreman session.

The brief's Overnight section becomes Work Orders. debrief_prep.sh copies
the open report (the next day's file) to orders.md, and /debrief writes a
5. Work Orders section or "No Work Orders ran today." The Foreman persona
owns the queue, and the README asks for one permission mode across the
Foreman and design sessions. The roadmap's #79 row reflects its approved
spec.
```

Run: `git add .claude/commands CLAUDE.md README.md docs/superpowers/roadmap.md system/agents/foreman.md system/scripts/brief_prep.sh system/scripts/debrief_prep.sh system/templates/daily-debrief.md system/tests`

Run: `git commit -q -F .scratch/msg-3.txt`
