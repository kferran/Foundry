# Plan 8a: Machine Roles and Debian Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each machine declares a role (`standalone`, `server`, `client`) that decides which dependencies it needs, which systemd units it installs and which `/setup` phases it runs; and the suite is proven on Debian by running it natively on a Debian host.

**Architecture:**
- Two config keys (`machine_role`, `sync_interval_minutes`), with integer bounds added to the schema engine for the second one.
- `check_deps.sh` and `install_units.sh` read the role and pick their lists from a per-role table. `check_deps.sh` also detects `pacman` or `apt-get` for install hints.
- `/setup`, `/backup` and the advisory health suite branch on the role in their prompt text.
- `system/tests/verify_on_host.sh <ssh-host>` copies `HEAD` to a temp directory on a host and runs the gate there. Running it on Debian 12 while planning found two real defects (SQLite 3.40 and jq 1.6), fixed in Task 1.

**Tech Stack:** bash 5, Python 3.11+ (`vaultlib`), jq ≥ 1.6, bats ≥ 1.8, systemd user units, Markdown prompts.

**Spec:** `docs/superpowers/specs/2026-10-03-two-machines-design.md` §3 (roles) and §6 (Debian). Plan 8b (§4) and Plan 8c (§5) follow; nothing here depends on them.

## Global Constraints

- **Template rule (spec §9):** no machine's own hostname, user path, remote URL or distro choice is committed. The Debian host used for verification is given in conversation as `<debian-host>` and never written into a committed file.
- **Tool floor (spec §6):** code and tests must pass on the oldest supported Debian release: jq 1.6, bats 1.8, SQLite 3.40, Python 3.11. No bats features newer than 1.8 (`run -N`, `bats_require_minimum_version`, `--separate-stderr`), no jq functions newer than 1.6.
- **Remote host use:** `verify_on_host.sh` writes only under the host's `/tmp` and installs nothing. Never run installers, `/setup` or headless runs on the host.
- **Never run** `/setup`, `install_units.sh` or `install_hooks.sh` against this template repo or the real `~/.claude`; tests use temp `HOME` and `SYSTEMD_USER_DIR`.
- **bats ruling R1:** no mid-test `!`, no `&&` assertion chains. Bats files stay mode 644.
- **Gate:** `system/scripts/verify_setup.sh > system/logs/gate.log 2>&1; echo "exit=$?"`, then `sed -n '/===== summary/,$p' system/logs/gate.log`. **Lint:** `system/scripts/lint_vault.sh > system/logs/lint.log 2>&1; echo "lint exit=$?"; tail -n 1 system/logs/lint.log` (`0 errors`). **Debian:** `system/tests/verify_on_host.sh <debian-host> > system/logs/host.log 2>&1; echo "host exit=$?"; grep -E 'PASS|FAIL|kept' system/logs/host.log`. It runs `HEAD`, so commit before running it. Read every verdict from an exit code, never through a pipe.
- **Patches:** each implementation and test step below is an exact patch, tested in a scratch clone. Apply one by saving the block to a file in the plan workspace and running `git apply --check <file> && git apply <file>`. A patch that does not apply means the tree differs from the plan's base. Stop and compare; never hand-merge silently.
- American English. Branch `feat/plan-8a` from `feat/plan-8` at 7efe52d (the approved spec). Commit trailers name the authoring model, after a blank line.

## Decisions made while planning

- **D1 Native Debian, no container** (user decision). `verify_on_host.sh` takes one plain host name, copies `git archive HEAD` (never the working tree), runs `verify_setup.sh` there, and keeps the copy and log only on failure.
- **D2 Two Debian defects fixed here** (found by running the gate on Debian 12 while planning; local Arch is green):
  - **The SQLite 3.40 authorizer** reports its own schema parse as an `UPDATE` of `sqlite_master` while building the FTS5 table. The guard therefore broke `vault_index.py query` for `MATCH` and `pragma_table_info`. The fix allows `UPDATE` on `sqlite_master`/`sqlite_schema` only. The connection stays `mode=ro` + `query_only`, and new tests prove `UPDATE sqlite_master` and `PRAGMA writable_schema` are still rejected. Preloading the schema before setting the authorizer was tried on the host and did not help.
  - **jq 1.6** exits 0 for `jq -e .` on empty input, so an empty install record broke `install_hooks.sh`. The fix tests for an empty value explicitly.
- **D3 Integer bounds are a schema feature.** `min`/`max` (integer strings) on `kind: int` only. The schema loader rejects non-integer bounds, bounds on other kinds, and `min > max`. `sync_interval_minutes` uses `min: "1"`, `max: "60"`. The vault's YAML loader reads every scalar as a string, so `max: 5` is valid and `max: "1.5"` is not.
- **D4 A missing `machine_role` means `standalone`** everywhere (`check_deps.sh`, `install_units.sh`, `/setup`, the health suite). Existing vaults change nothing until they choose a role.
- **D5 Role lists:**
  - client requires `claude git jq python3 pyyaml fts5`;
  - server requires today's list without `hyprctl`;
  - optional items are reported for every role;
  - `pacman` wins when both `pacman` and `apt-get` are on `PATH`;
  - with neither, the hint is `install <item>`.
- **D6 `check_deps.sh` avoids `dirname`.** Its tests run with a `PATH` holding only the tools under test, so the vault root is found with parameter expansion.
- **D7 Client units.** A client's `install_units.sh` prints `install_units: machine_role client: no units`, removes any units this vault owns (a role change), and never calls `systemctl` when it owns none. `--uninstall` runs before the role is read and is unchanged.
- **D8 `/setup` phase 0** becomes "Role and preflight". The phase numbers 1–10 and 5a stay, so existing tests and docs keep their anchors. On a client, phases 3, 5, 5a, 6 and 9 are skipped and reported. Phase 4's three server/client checks run in order and stop at the first failure.
- **D9 The README** documents roles and the client path now. It says automatic sync is Plan 8c, and that until then machines sync by hand with `/backup` and `git pull`.

## Review Focus

1. **An existing vault whose config has no `machine_role`.** Expected: behaves exactly as before. Pinned by the existing `units.bats` and `setup.bats` tests (fixture configs have no key) and Task 3's "role defaults to the config's machine_role, else standalone".
2. **Switching a machine from standalone to client or server.** Expected: unused owned units are removed; foreign units are untouched. Pinned by Task 4's role-change tests.
3. **`check_deps.sh` run with a minimal `PATH`** (no coreutils), the way `/setup` preflight may run on a bare machine. Expected: it still finds the vault and reads the role. Pinned by Task 3's default-role test, which runs with `PATH="$BIN"`.
4. **`verify_on_host.sh` against a host that lacks a dependency.** Expected: the gate's FAIL lines are printed, the exit is non-zero, and the copy is kept for inspection. Pinned by Task 1's failing-gate test (a fake gate exiting 1).
5. **A `vault_index.py query` write attempt on the relaxed authorizer.** Expected: still rejected. Pinned by Task 1's two new `test_writes_rejected` cases.

---

### Task 1: Debian verification and the two Debian fixes

**Files:**
- Create: `system/tests/verify_on_host.sh` (mode 755)
- Modify: `system/scripts/vaultlib/guard.py`, `system/scripts/install_hooks.sh`
- Test: `system/tests/setup.bats`, `system/tests/python/test_guard.py`

**Interfaces:**
- Produces: `system/tests/verify_on_host.sh <ssh-host>`. Exit codes: the host gate's, 1 when the copy fails, 2 on usage. Env `VERIFY_TMP` (default `/tmp`) is the host base directory, used by tests.

- [ ] **Step 1: Write the failing tests for `verify_on_host.sh`.**

```diff
diff --git a/system/tests/setup.bats b/system/tests/setup.bats
index 6e932a6..04f9c3c 100644
--- a/system/tests/setup.bats
+++ b/system/tests/setup.bats
@@ -136,3 +136,55 @@ failing_bats() { printf '#!/usr/bin/env bats\n@test "no" { false; }\n' > "$M/sys
   run "$VS" --bogus
   [ "$status" -eq 2 ]
 }
+
+# A fake host: an ssh stub that drops its options and host and runs the command here, with the
+# "remote" /tmp redirected to the test's tmpdir.
+host_repo() {
+  H="$BATS_TEST_TMPDIR/hostrepo"
+  mkdir -p "$H/system/scripts" "$H/system/tests" "$BATS_TEST_TMPDIR/remote-tmp" "$BATS_TEST_TMPDIR/sbin"
+  cp "$REPO/system/tests/verify_on_host.sh" "$H/system/tests/"
+  printf '#!/bin/bash\necho "===== summary"\necho "PASS fake"\nexit "${FAKE_GATE_RC:-0}"\n' > "$H/system/scripts/verify_setup.sh"
+  chmod +x "$H/system/scripts/verify_setup.sh"
+  git -C "$H" init -q
+  git -C "$H" add -A
+  git -C "$H" -c user.name=t -c user.email=t@e commit -qm init
+  cat > "$BATS_TEST_TMPDIR/sbin/ssh" <<'STUB'
+#!/bin/bash
+while [[ "$1" == -o ]]; do shift 2; done
+shift
+exec bash -c "$*"
+STUB
+  chmod +x "$BATS_TEST_TMPDIR/sbin/ssh"
+  export PATH="$BATS_TEST_TMPDIR/sbin:$PATH" VERIFY_TMP="$BATS_TEST_TMPDIR/remote-tmp"
+}
+
+@test "verify_on_host: a passing gate on the host exits 0, prints the summary and leaves nothing behind" {
+  host_repo
+  run "$H/system/tests/verify_on_host.sh" somehost
+  [ "$status" -eq 0 ]
+  grep -qx 'PASS fake' <<< "$output"
+  [ -z "$(ls -A "$VERIFY_TMP")" ]
+}
+
+@test "verify_on_host: a failing gate exits with its code and keeps the copy and log" {
+  host_repo
+  run env FAKE_GATE_RC=1 "$H/system/tests/verify_on_host.sh" somehost
+  [ "$status" -eq 1 ]
+  grep -q '^kept: somehost:' <<< "$output"
+  [ "$(ls "$VERIFY_TMP" | wc -l)" -eq 2 ]
+}
+
+@test "verify_on_host: copies HEAD, not uncommitted changes" {
+  host_repo
+  printf '#!/bin/bash\nexit 7\n' > "$H/system/scripts/verify_setup.sh"
+  run "$H/system/tests/verify_on_host.sh" somehost
+  [ "$status" -eq 0 ]
+}
+
+@test "verify_on_host: needs exactly one plain host argument" {
+  host_repo
+  run "$H/system/tests/verify_on_host.sh"
+  [ "$status" -eq 2 ]
+  run "$H/system/tests/verify_on_host.sh" 'h; rm -rf /'
+  [ "$status" -eq 2 ]
+}
```

- [ ] **Step 2: Run them and watch them fail.** `bats -f verify_on_host system/tests/setup.bats > system/logs/t1.log 2>&1; echo "exit=$?"; grep -c '^not ok' system/logs/t1.log`. Expected: `exit=1`, `4` (the script does not exist).

- [ ] **Step 3: Create `system/tests/verify_on_host.sh`** and `chmod 755` it:

```diff
diff --git a/system/tests/verify_on_host.sh b/system/tests/verify_on_host.sh
new file mode 100755
index 0000000..e043796
--- /dev/null
+++ b/system/tests/verify_on_host.sh
@@ -0,0 +1,24 @@
+#!/bin/bash
+# Run the gate natively on another machine over ssh (two-machine spec §6). Copies HEAD, never the
+# working tree, into a new directory under the host's /tmp; installs nothing there.
+set -euo pipefail
+REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
+cd "$REPO"
+
+die() { echo "verify_on_host: $2" >&2; exit "$1"; }
+(( $# == 1 )) || die 2 "usage: verify_on_host.sh <ssh-host>"
+host="$1"
+[[ "$host" =~ ^[A-Za-z0-9._@-]+$ ]] || die 2 "not a plain ssh host name: $host"
+
+dir="${VERIFY_TMP:-/tmp}/jarvis-verify-$(date +%Y%m%dT%H%M%S)-$$"
+ssh_opts=(-o BatchMode=yes -o ConnectTimeout=15)
+
+git archive --format=tar HEAD \
+  | ssh "${ssh_opts[@]}" "$host" "mkdir -- '$dir' && tar -x -C '$dir' && cd '$dir' && git init -q && git add -A && git -c user.name=verify -c user.email=verify@localhost commit -qm verify" \
+  || die 1 "could not copy HEAD to $host:$dir"
+
+set +e
+ssh "${ssh_opts[@]}" "$host" "cd '$dir' && system/scripts/verify_setup.sh > '$dir.log' 2>&1; rc=\$?; sed -n '/===== summary/,\$p' '$dir.log'; if [ \$rc -eq 0 ]; then rm -rf -- '$dir' '$dir.log'; else echo 'kept: $host:$dir and $dir.log'; fi; exit \$rc"
+rc=$?
+set -e
+exit "$rc"
```

- [ ] **Step 4: Run them and watch them pass.** Same command. Expected: `exit=0`. Commit: `git add system/tests/setup.bats system/tests/verify_on_host.sh && git commit -m "test: verify_on_host.sh runs the gate on another machine over ssh"`.

- [ ] **Step 5: Watch Debian fail.** Run the Debian command from Global Constraints. Expected: `host exit=1`, with `FAIL system/tests/hooks_install.bats` and `FAIL pytest system/tests/python`. In the kept log, `test_guard.py::test_fts_match_works` and `test_recursive_cte_and_table_info` fail with `vtable constructor failed` / `not authorized`, and `hooks_install.bats` "an empty or multi-document install record falls back" fails. Remove the kept copy and log: `ssh <debian-host> 'rm -rf -- /tmp/jarvis-verify-*'`.

- [ ] **Step 6: Add the write-rejection cases**, which must keep passing after the authorizer change:

```diff
diff --git a/system/tests/python/test_guard.py b/system/tests/python/test_guard.py
index ee9ba47..6d9e799 100644
--- a/system/tests/python/test_guard.py
+++ b/system/tests/python/test_guard.py
@@ -43,6 +43,8 @@ def test_views_work(db):
     "ATTACH DATABASE '/tmp/x.db' AS y",
     "PRAGMA journal_mode=DELETE",
     "DROP VIEW v_concept",
+    "UPDATE sqlite_master SET sql = ''",
+    "PRAGMA writable_schema = ON",
 ])
 def test_writes_rejected(db, sql):
     with pytest.raises(sqlite3.DatabaseError):
```

  `python3 -m pytest system/tests/python/test_guard.py -q`. Expected: all pass (the guard already rejects these; they pin it).

- [ ] **Step 7: Apply the fixes:**

```diff
diff --git a/system/scripts/install_hooks.sh b/system/scripts/install_hooks.sh
index e9f3bee..508030a 100755
--- a/system/scripts/install_hooks.sh
+++ b/system/scripts/install_hooks.sh
@@ -99,7 +99,8 @@ if [[ -f "$RECORD" ]]; then
     | if ($c | type) == "array" and all($c[]; type == "array" and all(.[]; type == "string")) then $c else null end' \
     "$RECORD" 2> /dev/null)" || created=null
   # An empty record prints nothing and a multi-document one prints several lines: accept exactly one value.
-  [[ "$created" != *$'\n'* ]] && jq -e . <<< "$created" > /dev/null 2>&1 || created=null
+  # Test for empty explicitly: jq 1.6 exits 0 for `jq -e .` on empty input (newer jq exits 4).
+  [[ -n "$created" && "$created" != *$'\n'* ]] && jq -e . <<< "$created" > /dev/null 2>&1 || created=null
 fi
 
 stripped="$(jq --argjson created "$created" "$LIB $STRIP" <<< "$current" 2> /dev/null)" \
diff --git a/system/scripts/vaultlib/guard.py b/system/scripts/vaultlib/guard.py
index 95538fe..5e62310 100644
--- a/system/scripts/vaultlib/guard.py
+++ b/system/scripts/vaultlib/guard.py
@@ -11,6 +11,10 @@ MAX_RESULT_BYTES = 16 * 1024 * 1024
 def _authorizer(action, arg1, arg2, _db, _source):
     if action in ALLOWED_ACTIONS:
         return sqlite3.SQLITE_OK
+    # SQLite 3.40 (Debian 12) reports its own schema parse as an UPDATE of sqlite_master while it builds
+    # a virtual table (FTS5). The connection is read-only (mode=ro, query_only), so no write can follow.
+    if action == sqlite3.SQLITE_UPDATE and arg1 in ("sqlite_master", "sqlite_schema"):
+        return sqlite3.SQLITE_OK
     if action == sqlite3.SQLITE_PRAGMA:
         if arg1 in READ_ONLY_PRAGMAS:
             return sqlite3.SQLITE_OK
```

- [ ] **Step 8: Watch Debian pass.** Gate locally (exit 0), commit (`git add system/scripts/vaultlib/guard.py system/scripts/install_hooks.sh system/tests/python/test_guard.py && git commit -m "fix: query guard on SQLite 3.40 and empty install record on jq 1.6"`), then the Debian command. Expected: `host exit=0`, 14 `PASS` lines, no `kept:` line.

### Task 2: `machine_role` and `sync_interval_minutes` config keys

**Files:**
- Modify: `system/scripts/vaultlib/schema.py` (`FieldSpec.min`/`max`, parse and check), `system/schemas/config.md`, `system/config.example.md`
- Test: `system/tests/python/test_schema.py`, `system/tests/commands.bats`

**Interfaces:**
- Produces: config keys `machine_role` (`standalone|server|client`, default `standalone`) and `sync_interval_minutes` (int 1–60, default 5). Read them with `system/scripts/vault_index.py field system/config.md <key>`, which prints nothing when the key is absent; callers default to `standalone`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/system/tests/commands.bats b/system/tests/commands.bats
index 1c07a49..c742709 100644
--- a/system/tests/commands.bats
+++ b/system/tests/commands.bats
@@ -262,3 +262,21 @@ self_edit_contract() {
     grep -qF 'keep everything the user wrote' <(awk '$0 == "## Self-edit" { on = 1 } on' "$f")
   done
 }
+
+@test "config: machine_role and sync_interval_minutes are in the example and bounded by the schema" {
+  [ "$(system/scripts/vault_index.py field system/config.example.md machine_role)" = standalone ]
+  [ "$(system/scripts/vault_index.py field system/config.example.md sync_interval_minutes)" = 5 ]
+  load helpers
+  make_vault
+  cd "$V"
+  for bad in 'machine_role: "laptop"' 'sync_interval_minutes: "0"' 'sync_interval_minutes: "61"'; do
+    sed -e "s/^${bad%%:*}: .*/$bad/" "$REPO/system/config.example.md" > "$V/system/config.md"
+    grep -qxF "$bad" "$V/system/config.md"
+    run system/scripts/vault_index.py validate system/config.md
+    [ "$status" -ne 0 ]
+    [[ "$output" == *"${bad%%:*}"* ]]
+  done
+  cp "$REPO/system/config.example.md" "$V/system/config.md"
+  run system/scripts/vault_index.py validate system/config.md
+  [ "$status" -eq 0 ]
+}
diff --git a/system/tests/python/test_schema.py b/system/tests/python/test_schema.py
index 539c937..5936bd9 100644
--- a/system/tests/python/test_schema.py
+++ b/system/tests/python/test_schema.py
@@ -11,6 +11,7 @@ fields:
   type: {kind: const, value: thing, required: true}
   name: {kind: string, required: true}
   count: {kind: int}
+  minutes: {kind: int, min: "1", max: "60"}
   flag: {kind: bool, default: "false"}
   day: {kind: date}
   at: {kind: datetime}
@@ -82,6 +83,8 @@ def test_plain_markdown_in_covered_folder(schemas):
     ("items", "[a, b]", "notalist"),
     ("layers", "{ui: web/}", "[a]"),
     ("ref", '"[[Index]]"', "Index"),
+    ("minutes", '"60"', '"61"'),
+    ("minutes", '"1"', '"0"'),
 ])
 def test_kinds(schemas, field, good, bad):
     base = "type: thing\nname: A\n"
@@ -173,3 +176,16 @@ def test_const_value_not_string_raises(tmp_path):
     write(tmp_path, "system/schemas/bad.md", "---\ntype: schema\nschema_for: bad\nfolders: [\"x/\"]\nfields:\n  a: {kind: const, value: [a]}\n---\n")
     with pytest.raises(schema.SchemaError):
         schema.load_schemas(tmp_path)
+
+
+@pytest.mark.parametrize("spec, message", [
+    ('{kind: int, min: "x"}', "min must be an integer string"),
+    ('{kind: int, max: "1.5"}', "max must be an integer string"),
+    ('{kind: string, min: "1"}', "min and max apply to int fields only"),
+    ('{kind: int, min: "5", max: "1"}', "min is greater than max"),
+])
+def test_int_bounds_spec_errors(tmp_path, spec, message):
+    write(tmp_path, "system/schemas/thing.md",
+          f"---\ntype: schema\nschema_for: thing\nfolders: [things/]\nfields:\n  n: {spec}\n---\n")
+    with pytest.raises(schema.SchemaError, match=message):
+        schema.load_schemas(tmp_path)
```

- [ ] **Step 2: Run them and watch them fail.** `python3 -m pytest system/tests/python/test_schema.py -q > system/logs/t2.log 2>&1; echo "rc=$?"; tail -n 1 system/logs/t2.log`. Expected: `rc=1`, 6 failed. Then `bats -f 'machine_role and sync' system/tests/commands.bats > system/logs/t2b.log 2>&1; echo "exit=$?"`. Expected: `exit=1`, failing on the first `field … machine_role` line.

- [ ] **Step 3: Apply the implementation:**

```diff
diff --git a/system/config.example.md b/system/config.example.md
index 8e2ac14..4799dc5 100644
--- a/system/config.example.md
+++ b/system/config.example.md
@@ -10,6 +10,8 @@ digest_min_minutes: "20"        # minimum minutes between digests
 preferences_enabled: "false"    # preference derivation, /brief acceptance and recall slot (a later phase)
 recall_budget_chars: "9000"     # SessionStart recall size cap (hard max 9500)
 template_remote: ""             # set by setup_remote.sh
+machine_role: "standalone"      # standalone | server | client; what this machine does (see README)
+sync_interval_minutes: "5"      # server only: minutes between vault syncs (1-60)
 superpowers:
   - "<strategic anchor>"
 ---
diff --git a/system/schemas/config.md b/system/schemas/config.md
index aaeb627..605b99e 100644
--- a/system/schemas/config.md
+++ b/system/schemas/config.md
@@ -15,6 +15,8 @@ fields:
   recall_budget_chars: {kind: int, default: "9000"}
   preferences_enabled: {kind: bool, default: "false"}
   superpowers: {kind: list, of: string}
+  machine_role: {kind: enum, values: [standalone, server, client], default: "standalone"}
+  sync_interval_minutes: {kind: int, min: "1", max: "60", default: "5"}
 ---
 # Config
 The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.
diff --git a/system/scripts/vaultlib/schema.py b/system/scripts/vaultlib/schema.py
index 383e8d8..5554423 100644
--- a/system/scripts/vaultlib/schema.py
+++ b/system/scripts/vaultlib/schema.py
@@ -39,6 +39,8 @@ class FieldSpec:
     must_exist: str | None = None
     unique_true: bool = False
     matches_folder: bool = False
+    min: int | None = None
+    max: int | None = None
 
 
 @dataclass
@@ -81,11 +83,21 @@ def parse_fieldspec(raw, where: str) -> FieldSpec:
         raise SchemaError(f"{where}: default must be a string")
     if kind == "const" and "value" in raw and not isinstance(raw["value"], str):
         raise SchemaError(f"{where}: const value must be a string")
+    bounds = {}
+    for key in ("min", "max"):
+        if key in raw:
+            if not isinstance(raw[key], str) or not INT.match(raw[key]):
+                raise SchemaError(f"{where}: {key} must be an integer string")
+            bounds[key] = int(raw[key])
+    if bounds and kind != "int":
+        raise SchemaError(f"{where}: min and max apply to int fields only")
+    if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
+        raise SchemaError(f"{where}: min is greater than max")
     spec = FieldSpec(
         kind=kind, required=_flag(raw, "required"), default=raw.get("default"),
         value=raw.get("value"), values=list(raw.get("values") or []),
         must_exist=raw.get("must_exist"), unique_true=_flag(raw, "unique_true"),
-        matches_folder=_flag(raw, "matches_folder"),
+        matches_folder=_flag(raw, "matches_folder"), min=bounds.get("min"), max=bounds.get("max"),
     )
     if kind == "list":
         spec.of = parse_fieldspec(raw.get("of", "string"), f"{where}.of")
@@ -211,7 +223,13 @@ def check_value(spec: FieldSpec, value, ctx: Context, where: str) -> list:
     if kind in ("string", "text"):
         return []
     if kind == "int":
-        return [] if INT.match(value) else err("expected an integer")
+        if not INT.match(value):
+            return err("expected an integer")
+        if spec.min is not None and int(value) < spec.min:
+            return err(f"must be at least {spec.min}")
+        if spec.max is not None and int(value) > spec.max:
+            return err(f"must be at most {spec.max}")
+        return []
     if kind == "bool":
         return [] if value.lower() in ("true", "false") else err("expected true or false")
     if kind == "date":
```

- [ ] **Step 4: Run them and watch them pass.** Same two commands. Expected: `rc=0` (36 passed) and `exit=0`. Then the gate (exit 0) and lint. Commit: `git add -A system/scripts/vaultlib/schema.py system/schemas/config.md system/config.example.md system/tests/python/test_schema.py system/tests/commands.bats && git commit -m "feat(config): machine_role and sync_interval_minutes, with int bounds in schemas"`.

### Task 3: `check_deps.sh --role` and package-manager hints

**Files:**
- Modify: `system/scripts/check_deps.sh` (rewritten)
- Test: `system/tests/setup.bats` (the setup stubs `pacman`; five new tests)

**Interfaces:**
- Consumes: `machine_role` (Task 2).
- Produces: `check_deps.sh [--strict] [--role standalone|server|client]`. Output lines `ok|missing|optional <item> [hint]`. Exit 2 on a bad argument or role.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/system/tests/setup.bats b/system/tests/setup.bats
index 04f9c3c..e5c506a 100644
--- a/system/tests/setup.bats
+++ b/system/tests/setup.bats
@@ -10,7 +10,7 @@ setup() {
   for c in git jq bats systemctl python3 flock timeout systemd-analyze; do
     ln -s "$(command -v "$c")" "$BIN/$c"
   done
-  for c in claude gcalcli hyprctl; do
+  for c in claude gcalcli hyprctl pacman; do
     printf '#!/bin/bash\n' > "$BIN/$c"
     chmod +x "$BIN/$c"
   done
@@ -63,6 +63,62 @@ setup() {
   done
 }
 
+@test "check_deps: --role client requires only what a client runs" {
+  rm "$BIN/gcalcli" "$BIN/hyprctl" "$BIN/bats" "$BIN/systemctl" "$BIN/systemd-analyze" "$BIN/flock"
+  run env PATH="$BIN" "$CD" --role client --strict
+  [ "$status" -eq 0 ]
+  for item in claude git jq python3 pyyaml fts5; do
+    grep -qx "ok $item" <<< "$output"
+  done
+  run grep -E '^(ok|missing) (gcalcli|hyprctl|bats|systemctl|systemd-analyze|flock|timeout|pytest) ' <<< "$output"
+  [ "$status" -eq 1 ]
+}
+
+@test "check_deps: --role server needs everything except hyprctl" {
+  rm "$BIN/hyprctl"
+  run env PATH="$BIN" "$CD" --strict --role server
+  [ "$status" -eq 0 ]
+  run grep hyprctl <<< "$output"
+  [ "$status" -eq 1 ]
+  rm "$BIN/gcalcli"
+  run env PATH="$BIN" "$CD" --role server --strict
+  [ "$status" -eq 1 ]
+}
+
+@test "check_deps: install hints follow the package manager on PATH" {
+  rm "$BIN/bats"
+  run env PATH="$BIN" "$CD"
+  grep -qx 'missing bats sudo pacman -S bash-bats' <<< "$output"
+  rm "$BIN/pacman"
+  printf '#!/bin/bash\n' > "$BIN/apt-get"
+  chmod +x "$BIN/apt-get"
+  run env PATH="$BIN" "$CD"
+  grep -qx 'missing bats sudo apt install bats' <<< "$output"
+  rm "$BIN/apt-get"
+  run env PATH="$BIN" "$CD"
+  grep -qx 'missing bats install bats' <<< "$output"
+}
+
+@test "check_deps: the role defaults to the config's machine_role, else standalone" {
+  load helpers
+  make_vault
+  rm "$BIN/hyprctl"
+  run env PATH="$BIN" "$V/system/scripts/check_deps.sh" --strict
+  [ "$status" -eq 1 ]
+  grep -q '^missing hyprctl ' <<< "$output"
+  printf 'machine_role: "server"\n' > "$BATS_TEST_TMPDIR/role"
+  sed -i '/^default_partition:/r '"$BATS_TEST_TMPDIR/role" "$V/system/config.md"
+  run env PATH="$BIN" "$V/system/scripts/check_deps.sh" --strict
+  [ "$status" -eq 0 ]
+}
+
+@test "check_deps: an unknown or missing role exits 2" {
+  run "$CD" --role laptop
+  [ "$status" -eq 2 ]
+  run "$CD" --role
+  [ "$status" -eq 2 ]
+}
+
 @test "check_deps: an unknown argument exits 2" {
   run "$CD" --bogus
   [ "$status" -eq 2 ]
```

- [ ] **Step 2: Run them and watch them fail.** `bats -f check_deps system/tests/setup.bats > system/logs/t3.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t3.log`. Expected: `exit=1`, failing on the role tests 6–9 (`--role` is an unknown argument today). The unknown-role test already passes and stays as a pin.

- [ ] **Step 3: Apply the implementation:**

```diff
diff --git a/system/scripts/check_deps.sh b/system/scripts/check_deps.sh
index 181ca30..76f3253 100755
--- a/system/scripts/check_deps.sh
+++ b/system/scripts/check_deps.sh
@@ -1,52 +1,84 @@
 #!/bin/bash
 # The single dependency list (spec §6.2): one "ok|missing|optional <item> [hint]" line per item.
-# Exit 0 always; --strict exits 1 if a required item is missing. Optional items never fail --strict.
+# Which items are required depends on the machine role (two-machine spec §3.4). Exit 0 always;
+# --strict exits 1 if a required item is missing. Optional items never fail --strict.
 set -euo pipefail
+# No dirname: this script must run with a PATH that lacks coreutils.
+src="${BASH_SOURCE[0]}"
+[[ "$src" == */* ]] || src="./$src"
+VAULT_ROOT="$(cd "${src%/*}/../.." && pwd -P)"
 
-strict=0
-case "${1:-}" in
-  "") ;;
-  --strict) strict=1 ;;
-  *) echo "usage: check_deps.sh [--strict]" >&2; exit 2 ;;
+usage() { echo "usage: check_deps.sh [--strict] [--role standalone|server|client]" >&2; exit 2; }
+strict=0 role=""
+while (( $# )); do
+  case "$1" in
+    --strict) strict=1; shift ;;
+    --role) (( $# >= 2 )) || usage; role="$2"; shift 2 ;;
+    *) usage ;;
+  esac
+done
+if [[ -z "$role" ]]; then
+  role="$(cd "$VAULT_ROOT" && system/scripts/vault_index.py field system/config.md machine_role 2>/dev/null || true)"
+  role="${role:-standalone}"
+fi
+case "$role" in
+  standalone) REQUIRED=(claude git jq bats gcalcli systemctl hyprctl python3 flock timeout pyyaml pytest fts5 systemd-analyze) ;;
+  server) REQUIRED=(claude git jq bats gcalcli systemctl python3 flock timeout pyyaml pytest fts5 systemd-analyze) ;;
+  client) REQUIRED=(claude git jq python3 pyyaml fts5) ;;
+  *) usage ;;
 esac
 
-declare -A HINT=(
-  [claude]="install Claude Code: https://docs.claude.com/en/docs/claude-code/setup"
-  [git]="sudo pacman -S git"
-  [jq]="sudo pacman -S jq"
-  [bats]="sudo pacman -S bash-bats"
-  [gcalcli]="pipx install gcalcli"
-  [systemctl]="systemd is required (user services)"
-  [hyprctl]="sudo pacman -S hyprland"
-  [python3]="sudo pacman -S python"
-  [flock]="sudo pacman -S util-linux"
-  [timeout]="sudo pacman -S coreutils"
-  [pyyaml]="sudo pacman -S python-yaml"
-  [pytest]="sudo pacman -S python-pytest"
-  [fts5]="python's sqlite3 lacks FTS5: sudo pacman -S sqlite python"
-  [systemd-analyze]="systemd is required (unit verification)"
-  [herdr]="optional session backend for sub-project 2; see README"
-  [tmux]="optional session backend for sub-project 2: sudo pacman -S tmux"
-)
+has() { command -v "$1" >/dev/null 2>&1 && echo 1 || echo 0; }
+py() { command -v python3 >/dev/null 2>&1 && python3 "$@" >/dev/null 2>&1 && echo 1 || echo 0; }
+
+if (( $(has pacman) )); then pm=pacman; elif (( $(has apt-get) )); then pm=apt; else pm=other; fi
+# hint <item>: the install hint for this package manager.
+hint() {
+  local pkg_pacman pkg_apt
+  case "$1" in
+    claude) echo "install Claude Code: https://docs.claude.com/en/docs/claude-code/setup"; return ;;
+    gcalcli) echo "pipx install gcalcli"; return ;;
+    systemctl) echo "systemd is required (user services)"; return ;;
+    systemd-analyze) echo "systemd is required (unit verification)"; return ;;
+    herdr) echo "optional session backend for sub-project 2; see README"; return ;;
+    fts5) pkg_pacman="sqlite python" pkg_apt="libsqlite3-0 python3"; printf "python's sqlite3 lacks FTS5: " ;;
+    git|jq|tmux) pkg_pacman="$1" pkg_apt="$1" ;;
+    bats) pkg_pacman=bash-bats pkg_apt=bats ;;
+    hyprctl) pkg_pacman=hyprland pkg_apt=hyprland ;;
+    python3) pkg_pacman=python pkg_apt=python3 ;;
+    flock) pkg_pacman=util-linux pkg_apt=util-linux ;;
+    timeout) pkg_pacman=coreutils pkg_apt=coreutils ;;
+    pyyaml) pkg_pacman=python-yaml pkg_apt=python3-yaml ;;
+    pytest) pkg_pacman=python-pytest pkg_apt=python3-pytest ;;
+  esac
+  case "$pm" in
+    pacman) echo "sudo pacman -S $pkg_pacman" ;;
+    apt) echo "sudo apt install $pkg_apt" ;;
+    *) echo "install $1" ;;
+  esac
+}
+
 missing=0
 report() {  # <item> <present 0|1> [optional]
   if (( $2 )); then
     echo "ok $1"
   elif [[ "${3:-}" == optional ]]; then
-    echo "optional $1 ${HINT[$1]}"
+    echo "optional $1 $(hint "$1")"
   else
-    echo "missing $1 ${HINT[$1]}"
+    echo "missing $1 $(hint "$1")"
     missing=1
   fi
 }
-has() { command -v "$1" >/dev/null 2>&1 && echo 1 || echo 0; }
-py() { command -v python3 >/dev/null 2>&1 && python3 "$@" >/dev/null 2>&1 && echo 1 || echo 0; }
+present() {  # <item>: 1 when the item is available
+  case "$1" in
+    pyyaml) py -c 'import yaml' ;;
+    pytest) py -m pytest --version ;;
+    fts5) py -c 'import sqlite3; sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")' ;;
+    *) has "$1" ;;
+  esac
+}
 
-for c in claude git jq bats gcalcli systemctl hyprctl python3 flock timeout; do report "$c" "$(has "$c")"; done
-report pyyaml "$(py -c 'import yaml')"
-report pytest "$(py -m pytest --version)"
-report fts5 "$(py -c 'import sqlite3; sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")')"
-report systemd-analyze "$(has systemd-analyze)"
+for item in "${REQUIRED[@]}"; do report "$item" "$(present "$item")"; done
 for c in herdr tmux; do report "$c" "$(has "$c")" optional; done
 
 (( strict && missing )) && exit 1
```

- [ ] **Step 4: Run them and watch them pass.** `bats system/tests/setup.bats > system/logs/t3.log 2>&1; echo "exit=$?"`. Expected: `exit=0`. Commit: `git add system/scripts/check_deps.sh system/tests/setup.bats && git commit -m "feat(check_deps): per-role requirements and pacman/apt install hints"`.

### Task 4: `install_units.sh` by role

**Files:**
- Modify: `system/scripts/install_units.sh`
- Test: `system/tests/units.bats`

**Interfaces:**
- Consumes: `machine_role` (Task 2) via `config_get machine_role standalone`.
- Produces: per-role `UNITS`/`ENABLE` arrays, which Plan 8c extends with `jarvis-sync.*` for `server`; `owned_units` and `remove_units <name…>` shell functions.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/system/tests/units.bats b/system/tests/units.bats
index cca9a57..1c929ff 100644
--- a/system/tests/units.bats
+++ b/system/tests/units.bats
@@ -198,3 +198,56 @@ move_vault() {  # <new path>: relocate the vault and re-derive the paths the tes
   run "$IU" --dry-run --uninstall
   [ "$status" -eq 2 ]
 }
+
+set_role() { system/scripts/vault_index.py set system/config.md machine_role "$1" > /dev/null; }
+
+@test "machine_role server installs the run units without the focus tracker" {
+  set_role server
+  run "$IU"
+  [ "$status" -eq 0 ]
+  for n in "${UNITS[@]}"; do
+    [ "$n" = jarvis-focus.service ] && continue
+    [ -f "$UD/$n" ]
+  done
+  [ ! -e "$UD/jarvis-focus.service" ]
+  grep -qx -- '--user enable --now jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer' "$STUB_SYSTEMCTL_LOG"
+}
+
+@test "machine_role client installs nothing and says so" {
+  set_role client
+  run "$IU"
+  [ "$status" -eq 0 ]
+  grep -qx 'install_units: machine_role client: no units' <<< "$output"
+  [ ! -e "$UD" ]
+  [ ! -e "$STUB_SYSTEMCTL_LOG" ]
+  run "$IU" --dry-run
+  [ "$status" -eq 0 ]
+  grep -qx 'install_units: machine_role client: no units' <<< "$output"
+}
+
+@test "a role change removes the owned units the new role does not use" {
+  run "$IU"
+  [ -f "$UD/jarvis-focus.service" ]
+  set_role server
+  run "$IU"
+  [ "$status" -eq 0 ]
+  grep -qx 'removed jarvis-focus.service' <<< "$output"
+  [ ! -e "$UD/jarvis-focus.service" ]
+  grep -qx -- '--user disable --now jarvis-focus.service' "$STUB_SYSTEMCTL_LOG"
+  set_role client
+  run "$IU"
+  [ "$status" -eq 0 ]
+  for n in "${UNITS[@]}"; do
+    [ ! -e "$UD/$n" ]
+  done
+  grep -qx 'removed jarvis-brief.timer' <<< "$output"
+}
+
+@test "a role change never removes units this vault does not own" {
+  run "$IU"
+  printf '[Unit]\nDescription=foreign\n' > "$UD/foreign.service"
+  set_role client
+  run "$IU"
+  [ "$status" -eq 0 ]
+  [ -f "$UD/foreign.service" ]
+}
```

- [ ] **Step 2: Run them and watch them fail.** `bats system/tests/units.bats > system/logs/t4.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t4.log`. Expected: `exit=1`, failing on the server, client and role-change tests. The foreign-unit test passes today and stays as a pin.

- [ ] **Step 3: Apply the implementation:**

```diff
diff --git a/system/scripts/install_units.sh b/system/scripts/install_units.sh
index e230ef1..7c6dffe 100755
--- a/system/scripts/install_units.sh
+++ b/system/scripts/install_units.sh
@@ -8,7 +8,6 @@ source system/scripts/lib_config.sh
 
 SYSTEMCTL="${SYSTEMCTL:-systemctl}"
 UNIT_DIR="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
-ENABLE=(jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer jarvis-focus.service)
 HEADER_PREFIX="# Managed by vault: "
 HEADER="$HEADER_PREFIX$VAULT_ROOT"
 
@@ -42,6 +41,53 @@ if [[ "$mode" == uninstall ]]; then
   exit 0
 fi
 
+
+# The units each machine role runs (two-machine spec §3.3), and the ones it enables.
+role="$(config_get machine_role standalone)"
+case "$role" in
+  standalone)
+    UNITS=(jarvis-intake.service jarvis-intake.timer jarvis-brief.service jarvis-brief.timer
+           jarvis-debrief.service jarvis-debrief.timer jarvis-focus.service)
+    ENABLE=(jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer jarvis-focus.service) ;;
+  server)
+    UNITS=(jarvis-intake.service jarvis-intake.timer jarvis-brief.service jarvis-brief.timer
+           jarvis-debrief.service jarvis-debrief.timer)
+    ENABLE=(jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer) ;;
+  client) UNITS=() ENABLE=() ;;
+  *) die 1 "unknown machine_role in system/config.md: $role" ;;
+esac
+
+# owned_units: the unit files in UNIT_DIR whose header names this vault.
+owned_units() {
+  local f
+  for f in "$UNIT_DIR"/*.service "$UNIT_DIR"/*.timer; do
+    if [[ "$(head -n 1 -- "$f")" == "$HEADER" ]]; then printf '%s\n' "${f##*/}"; fi
+  done
+}
+
+# remove_units <name…>: disable, delete and report units this vault owns.
+remove_units() {
+  (( $# )) || return 0
+  "$SYSTEMCTL" --user disable --now "$@" || echo "install_units: warning: systemctl disable failed" >&2
+  local n
+  for n in "$@"; do
+    rm -f -- "$UNIT_DIR/$n"
+    echo "removed $n"
+  done
+}
+
+if [[ "$role" == client ]]; then
+  echo "install_units: machine_role client: no units"
+  if [[ "$mode" == install ]]; then
+    mapfile -t stale < <(owned_units)
+    if (( ${#stale[@]} )); then
+      remove_units "${stale[@]}"
+      "$SYSTEMCTL" --user daemon-reload
+    fi
+  fi
+  exit 0
+fi
+
 # Unit files split ExecStart on whitespace and expand % specifiers, so paths are quoted in the
 # templates and restricted to characters that survive both.
 SAFE='^/[A-Za-z0-9._/@+ -]+$'
@@ -60,8 +106,11 @@ unit_path="$(dirname "$claude_bin"):%h/.local/bin:/usr/local/bin:/usr/bin:/bin"
 esc() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }
 work="$(mktemp -d)"
 trap 'rm -rf -- "$work"' EXIT
-templates=(system/systemd/*.in)
-(( ${#templates[@]} )) || die 1 "no unit templates in system/systemd/"
+templates=()
+for n in "${UNITS[@]}"; do
+  [[ -f "system/systemd/$n.in" ]] || die 1 "missing unit template system/systemd/$n.in"
+  templates+=("system/systemd/$n.in")
+done
 for t in "${templates[@]}"; do
   name="$(basename "$t" .in)"
   {
@@ -117,5 +166,11 @@ for u in "${rendered[@]}"; do
   mv -f -- "$dst.tmp" "$dst"
   echo "$status $n"
 done
+# A role change leaves owned units the new role does not use: remove them.
+stale=()
+while IFS= read -r n; do
+  [[ " ${UNITS[*]} " == *" $n "* ]] || stale+=("$n")
+done < <(owned_units)
+remove_units "${stale[@]}"
 "$SYSTEMCTL" --user daemon-reload
 "$SYSTEMCTL" --user enable --now "${ENABLE[@]}"
```

- [ ] **Step 4: Run them and watch them pass.** Same command. Expected: `exit=0` (21 tests). Commit: `git add system/scripts/install_units.sh system/tests/units.bats && git commit -m "feat(units): install units by machine role and remove ones a role change drops"`.

### Task 5: `/setup`, `/backup`, the health suite and the README by role

**Files:**
- Modify: `.claude/commands/setup.md`, `.claude/commands/backup.md`, `system/tests/system_health.bats`, `README.md`
- Test: `system/tests/commands.bats`

**Interfaces:**
- Consumes: `check_deps.sh --role` (Task 3), `install_units.sh` roles (Task 4), `machine_role` (Task 2).
- Produces: `setup.md` heading `## 0. Role and preflight`; the `skip_unless_role <role…>` helper in `system_health.bats`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/system/tests/commands.bats b/system/tests/commands.bats
index c742709..ec01a85 100644
--- a/system/tests/commands.bats
+++ b/system/tests/commands.bats
@@ -280,3 +280,51 @@ self_edit_contract() {
   run system/scripts/vault_index.py validate system/config.md
   [ "$status" -eq 0 ]
 }
+
+@test "/setup asks the machine role first and checks dependencies for that role" {
+  sec="$(setup_section '0. Role and preflight')"
+  for s in 'system/scripts/vault_index.py field system/config.md machine_role' '`standalone`' '`server`' '`client`' \
+      'showing the current role as the default' 'system/scripts/check_deps.sh --role <role>'; do
+    [[ "$sec" == *"$s"* ]]
+  done
+  before_ask="${sec%%Ask which role*}"
+  before_deps="${sec%%check_deps.sh --role*}"
+  [ "${#before_ask}" -lt "${#before_deps}" ]
+  [ "$(grep -m1 -E '^## ' .claude/commands/setup.md)" = '## 0. Role and preflight' ]
+  grep -qF 'system/scripts/vault_index.py set system/config.md machine_role <role>' .claude/commands/setup.md
+}
+
+@test "/setup on a client skips the phases a client does not use, and says so" {
+  f=.claude/commands/setup.md
+  grep -qF 'On a client, skip phases 3, 5, 5a, 6 and 9' "$f"
+  grep -qF 'not used on a client' "$f"
+  grep -qF 'On a client, ask only for the timezone and the default partition.' "$f"
+  sec="$(setup_section '8. Verify')"
+  [[ "$sec" == *'On a client, run `system/scripts/lint_vault.sh` instead'* ]]
+}
+
+@test "/setup requires private remotes, working credentials and a published branch on a server or client" {
+  sec="$(setup_section '4. Remote')"
+  for s in 'On a server or a client, only `private` is allowed' 'git config user.name' 'git config user.email' \
+      'GIT_TERMINAL_PROMPT=0 timeout 30 git ls-remote origin' 'git ls-remote --heads origin' 'git push -u origin HEAD'; do
+    [[ "$sec" == *"$s"* ]]
+  done
+}
+
+@test "/setup requires linger on a server and lists the units for the role" {
+  sec="$(setup_section '5. Units')"
+  [[ "$sec" == *'On a server, linger is required'* ]]
+  [[ "$sec" == *'`jarvis-focus` (standalone only)'* ]]
+}
+
+@test "/backup lints instead of running the suites on a client" {
+  f=.claude/commands/backup.md
+  grep -qF 'On a client (`machine_role: client`), run `system/scripts/lint_vault.sh` instead' "$f"
+  grep -qF 'Skip this step on a client.' "$f"
+}
+
+@test "system_health checks each item only on the roles that run it" {
+  f=system/tests/system_health.bats
+  grep -qF 'skip_unless_role standalone server' "$f"
+  grep -qF 'skip_unless_role standalone' <(grep -A3 'focus tracker is active' "$f")
+}
```

- [ ] **Step 2: Run them and watch them fail.** `bats system/tests/commands.bats > system/logs/t5.log 2>&1; echo "exit=$?"; grep -c '^not ok' system/logs/t5.log`. Expected: `exit=1`, `6`.

- [ ] **Step 3: Apply the implementation:**

```diff
diff --git a/.claude/commands/backup.md b/.claude/commands/backup.md
index eef8123..538b4bc 100644
--- a/.claude/commands/backup.md
+++ b/.claude/commands/backup.md
@@ -4,8 +4,8 @@ description: Verifies the vault, commits everything, and pushes according to rem
 
 Back up the vault.
 
-1. **Verify.** Run `system/scripts/verify_setup.sh`. If it exits non-zero, stop: report the failing suites and do not commit.
-2. **Health (report only).** Run `bats system/tests/system_health.bats` and summarize failures as warnings. They never block the backup.
+1. **Verify.** Run `system/scripts/verify_setup.sh`. On a client (`machine_role: client`), run `system/scripts/lint_vault.sh` instead: a client has no bats or pytest. If it exits non-zero, stop: report the failures and do not commit.
+2. **Health (report only).** Run `bats system/tests/system_health.bats` and summarize failures as warnings. They never block the backup. Skip this step on a client.
 3. **Changes.** Run `git status --porcelain`. If nothing changed, check for commits not yet pushed (`git status -sb` shows `ahead`, or the branch has no upstream): if there are some, go to step 5; otherwise say the vault is up to date and stop.
 4. **Commit.** Stage everything (`git add -A`; the gitignore keeps raw inputs, logs and config out). Write one Conventional Commits message from the changed paths, and commit. The pre-commit hook lints staged notes; if it blocks the commit, report the errors and stop.
 5. **Push.** Read `system/scripts/vault_index.py field system/config.md remote_mode`:
diff --git a/.claude/commands/setup.md b/.claude/commands/setup.md
index 356de73..751a0d2 100644
--- a/.claude/commands/setup.md
+++ b/.claude/commands/setup.md
@@ -4,14 +4,21 @@ description: Interactive onboarding — config interview, codebases, remotes, sy
 
 You are running Jarvis setup. Every phase is idempotent: show what exists and edit it, never overwrite blindly. Ask one question at a time, show the default, and wait for the answer. Scripts that are not allowlisted will ask the user for permission; that is intended. Run every script as `system/scripts/<name> …` from the vault root.
 
-## 0. Preflight
-Run `system/scripts/check_deps.sh`. List every `missing` line with its install hint, and every `optional` line as optional. If `pyyaml` is missing, stop: setup cannot continue without it. Otherwise continue, noting which features are off (no `gcalcli`: no calendar in the brief; no `hyprctl`: no focus tracking).
+## 0. Role and preflight
+Read the current role with `system/scripts/vault_index.py field system/config.md machine_role` (no config, or an empty value, means `standalone`). Ask which role this machine has, showing the current role as the default:
+- `standalone`: this machine does everything (automation, coding sessions, Obsidian).
+- `server`: an always-on machine that runs the automation and the coding sessions. Other machines sync with it through the private `origin`.
+- `client`: a machine for reading and editing the vault in Obsidian. It runs no automation and syncs through git.
+
+Then run `system/scripts/check_deps.sh --role <role>`. List every `missing` line with its install hint, and every `optional` line as optional. If `pyyaml` is missing, stop: setup cannot continue without it. Otherwise continue, noting which features are off (no `gcalcli`: no calendar in the brief; no `hyprctl` on a standalone machine: no focus tracking).
+
+On a client, skip phases 3, 5, 5a, 6 and 9, and report each as "not used on a client".
 
 ## 1. Existing config
-If `system/config.md` exists, show its values and ask which to change. Otherwise create it from the example's frontmatter, without the example's body text, by running exactly this: `[ -f system/config.md ] || { awk '{ print } NR > 1 && /^---$/ { exit }' system/config.example.md; printf '# Config\n\nWritten by /setup. Re-run /setup to change it.\n'; } > system/config.md`. Use its values as the defaults below.
+If `system/config.md` exists, show its values and ask which to change. Otherwise create it from the example's frontmatter, without the example's body text, by running exactly this: `[ -f system/config.md ] || { awk '{ print } NR > 1 && /^---$/ { exit }' system/config.example.md; printf '# Config\n\nWritten by /setup. Re-run /setup to change it.\n'; } > system/config.md`. Use its values as the defaults below. Then record the role from phase 0 with `system/scripts/vault_index.py set system/config.md machine_role <role>`.
 
 ## 2. Interview
-Ask, in order: timezone (default from config; must exist under `/usr/share/zoneinfo`), brief time (`HH:MM`), debrief time (`HH:MM`), superpowers (strategic anchors, one per line), default partition for vault sessions and inbox files (`personal`, `work` or `shared`; default `personal`), digest thresholds (default 5 work events and 20 minutes), recall budget (default 9000 characters, at most 9500).
+Ask, in order: timezone (default from config; must exist under `/usr/share/zoneinfo`), brief time (`HH:MM`), debrief time (`HH:MM`), superpowers (strategic anchors, one per line), default partition for vault sessions and inbox files (`personal`, `work` or `shared`; default `personal`), digest thresholds (default 5 work events and 20 minutes), recall budget (default 9000 characters, at most 9500). On a client, ask only for the timezone and the default partition.
 
 Write each scalar with `system/scripts/vault_index.py set system/config.md <key> <value>` and the superpowers list by editing the file. Then run `system/scripts/vault_index.py validate system/config.md`; on an error, show it, ask again for that value, and re-validate.
 
@@ -28,10 +35,15 @@ Write each scalar with `system/scripts/vault_index.py set system/config.md <key>
 ## 4. Remote
 Run `system/scripts/setup_remote.sh --detect` and report what it found. Read the current mode with `system/scripts/vault_index.py field system/config.md remote_mode`. Then ask, showing the current mode as the default: a private URL for your vault (`private`), no remote (`none`), or keep the remotes as they are (`keep`, for template maintainers; choose this when `origin` is the template and you maintain it). If the current mode is `private`, show the current `origin` URL (`git remote get-url origin`) as the default URL. Run `system/scripts/setup_remote.sh <url>`, `--none` or `--keep` and report its output.
 
-## 5. Units
-Run `system/scripts/install_units.sh --dry-run` and summarize the units: `jarvis-intake` (every 5 minutes), `jarvis-brief` and `jarvis-debrief` (at the configured times), `jarvis-focus` (the focus tracker). Ask before installing; on yes run `system/scripts/install_units.sh` and report each `new|changed|unchanged` line.
+On a server or a client, only `private` is allowed: the machines share the vault through the private `origin`. Then check, in order, and stop this phase at the first failure with what the user must do:
+1. `git config user.name` and `git config user.email` both print a value. If not, ask the user to set them (`! git config user.name "…"`).
+2. `GIT_TERMINAL_PROMPT=0 timeout 30 git ls-remote origin > /dev/null` succeeds. If not, explain that automation needs credentials that work without a prompt (an SSH key without a passphrase prompt, or a credential helper), and re-check once the user has set them up.
+3. The branch is published: if `git ls-remote --heads origin "$(git branch --show-current)"` prints nothing, run `git push -u origin HEAD` and report the result.
 
-Then run `loginctl show-user "$USER" -p Linger --value`. If it prints `no`, explain that timers only run while you are logged in, and offer `loginctl enable-linger "$USER"` (the user runs it).
+## 5. Units
+Run `system/scripts/install_units.sh --dry-run` and summarize the units it prints: `jarvis-intake` (every 5 minutes), `jarvis-brief` and `jarvis-debrief` (at the configured times), `jarvis-focus` (standalone only), the focus tracker. Ask before installing; on yes run `system/scripts/install_units.sh` and report each `new|changed|unchanged` line.
+
+Then run `loginctl show-user "$USER" -p Linger --value`. If it prints `no`, explain that timers only run while you are logged in, and offer `loginctl enable-linger "$USER"` (the user runs it). On a server, linger is required: give the command, wait until the user says it is done, and re-check; do not continue past this phase until it prints `yes`.
 
 ## 5a. Memory hooks
 Memory (Soundwave) is optional and stays off until its hooks are installed in your user-level Claude Code settings. Ask nothing until you have shown the dry run.
@@ -55,10 +67,10 @@ Run `timeout 20 gcalcli list < /dev/null`. If it fails, tell the user to run `!
 Run `system/scripts/vault_index.py rebuild`, then `system/scripts/vault_index.py issues`, and report any error.
 
 ## 8. Verify
-Run `system/scripts/verify_setup.sh --health` and `systemctl --user list-timers 'jarvis-*'`. Report each suite's PASS/FAIL line and the next run time of each timer. Health failures are advisory.
+Run `system/scripts/verify_setup.sh --health` and `systemctl --user list-timers 'jarvis-*'`. Report each suite's PASS/FAIL line and the next run time of each timer. Health failures are advisory. On a client, run `system/scripts/lint_vault.sh` instead (a client has no test tools or timers) and report its last line.
 
 ## 9. Hand-off
 For each registered codebase without one, create `wiki/<partition>/concepts/<Name>OnboardingAssignment.md`, where `<partition>` is the codebase's partition and `<Name>` its name in PascalCase. Frontmatter: `type: concept`, `tags: ["onboarding"]`, `compiled_at` today, `partition`, `codebase`, `agent_owner: CodingAgent`, `status: draft`. Body: direct **CodingAgent** to map the codebase's layers and its logging and telemetry definitions (start from the `logging_hints` the inspection found) into `wiki/<partition>/entities/<Name>LogEventMap.md`; link `[[Index]]` and name each superpower the work serves. Run `system/scripts/lint_vault.sh` afterwards.
 
 ## 10. Report
-Show a table of every item set up (config, each codebase, remote mode, each unit, linger, memory hooks, calendar, index, verification) with its status. Remind the user to install the Obsidian **Dataview** plugin for the `wiki/Index.md` dashboards, and that `system/scripts/update_template.sh` pulls template updates.
+Show a table of every item set up (role, config, each codebase, remote mode, each unit, linger, memory hooks, calendar, index, verification) with its status; on a client, the skipped items say "not used on a client". Remind the user to install the Obsidian **Dataview** plugin for the `wiki/Index.md` dashboards, and that `system/scripts/update_template.sh` pulls template updates.
diff --git a/README.md b/README.md
index ab638bf..588f5e1 100644
--- a/README.md
+++ b/README.md
@@ -116,16 +116,29 @@ system/
 docs/superpowers/             specs, plans, spike results
 ```
 
+## Machine roles
+
+Each machine that holds the vault has a `machine_role` in its own `system/config.md`, chosen in `/setup`:
+
+| Role | Runs | Use it for |
+|---|---|---|
+| `standalone` (default) | intake, brief, debrief and focus units; memory hooks; codebases | one machine that does everything |
+| `server` | intake, brief and debrief units; memory hooks; codebases | an always-on machine that runs the automation and your coding sessions |
+| `client` | nothing automated | reading and editing the vault in Obsidian on another machine |
+
+A server and its clients share the vault through a private `origin` (`remote_mode: private`). Syncing them automatically is Plan 8c; until then, sync by hand with `/backup` and `git pull`.
+
 ## Requirements
 
-Jarvis targets Arch / Omarchy Linux today. Running automation on a Debian server is Plan 8. `system/scripts/check_deps.sh` checks for:
+Jarvis runs on Arch / Omarchy and on Debian. `system/scripts/check_deps.sh --role <role>` checks what that role needs and prints `pacman` or `apt` install hints:
 
 - `claude` (Claude Code), `git`, `jq`, `bats`, `flock`, `timeout`
 - `python3` with PyYAML and pytest (`sudo pacman -S python-yaml python-pytest`). Missing PyYAML blocks setup.
 - `sqlite3` built with FTS5
 - systemd user units (`systemctl --user`, `systemd-analyze`). If you want timers to run while you are logged out, enable lingering.
 - `gcalcli` for calendar input to the brief. Without it the brief lists the calendar under Unavailable Sources.
-- Hyprland (`hyprctl`) for the Obsidian focus tracker. Without it only focus stats are lost, but `check_deps.sh --strict` still counts both of these as missing until Plan 8 makes them per-machine.
+- Hyprland (`hyprctl`) for the Obsidian focus tracker, on a standalone machine only. Without it only focus stats are lost.
+- A client needs only `claude`, `git`, `jq`, `python3` with PyYAML, and SQLite with FTS5.
 - Optional: `herdr` or `tmux` as session backends for sub-project 2
 - Obsidian, with the **Dataview** plugin recommended (`wiki/Index.md` dashboards are plain code blocks without it). **[Vault Curate](https://github.com/notoriouslab/vault-curate)** is an optional plugin for link suggestions. It is not a dependency.
 
@@ -138,14 +151,23 @@ claude
 > /setup
 ```
 
+On a client, clone your private vault instead of the template, then run `/setup` and choose `client`:
+
+```sh
+git clone <private origin> my-vault
+cd my-vault
+claude
+> /setup
+```
+
 `/setup` is idempotent and can be re-run at any time. Its phases (spec §11):
 
-- **0. Preflight:** `check_deps.sh`. Missing items are listed with install hints.
+- **0. Role and preflight:** you choose the machine role, then `check_deps.sh --role <role>` lists missing items with install hints. A client skips phases 3, 5, 5a, 6 and 9.
 - **1. Existing config:** if `system/config.md` already exists, it is shown and edited, not overwritten.
 - **2. Interview:** timezone, brief and debrief times, superpowers, default partition, digest thresholds and recall budget.
 - **3. Codebases:** you choose repos from a directory scan. Each one is inspected, written to `system/codebases/<name>.md` with a partition, and confirmed with you field by field.
-- **4. Remote:** a `template` remote is added for updates, and you choose a private `origin`, no remote, or keep (maintainer mode).
-- **5. Units:** systemd timers are rendered and enabled, and you are offered linger.
+- **4. Remote:** a `template` remote is added for updates, and you choose a private `origin`, no remote, or keep (maintainer mode). A server or client must use a private `origin`; setup checks that git can reach it without a prompt and publishes the branch.
+- **5. Units:** the role's systemd units are rendered and enabled, and you are offered linger (required on a server).
 - **5a. Memory hooks** (optional): you are shown the diff to `~/.claude/settings.json` and what each hook does, and it is applied only after an explicit yes. Declining leaves memory off (see [Memory](#memory-soundwave)).
 - **6. Calendar:** `gcalcli` auth is checked.
 - **7. Index:** the index is rebuilt.
@@ -185,7 +207,7 @@ system/scripts/verify_setup.sh            # every system/tests/*.bats except sys
 system/scripts/verify_setup.sh --health   # also the advisory live-state suite
 ```
 
-`system/tests/system_health.bats` checks live service state and is advisory only. After any change to `run_headless.sh` or the settings files, re-run the spike checklist (spec §7.4) by hand. After any change to `run_headless.sh`, `system/headless.settings.json` or the `ingest`, `brief` or `debrief` commands, re-run the live acceptance steps (Plan 4a, Task 9) in a throwaway clone.
+`system/tests/system_health.bats` checks live service state and is advisory only. To prove the suite on Debian, run `system/tests/verify_on_host.sh <ssh-host>`: it copies the committed tree to a temporary directory on that host, runs the gate there, and exits with its code. The host needs the `apt` packages `check_deps.sh` lists. After any change to `run_headless.sh` or the settings files, re-run the spike checklist (spec §7.4) by hand. After any change to `run_headless.sh`, `system/headless.settings.json` or the `ingest`, `brief` or `debrief` commands, re-run the live acceptance steps (Plan 4a, Task 9) in a throwaway clone.
 
 ## Acknowledgements
 
diff --git a/system/tests/system_health.bats b/system/tests/system_health.bats
index 74749d3..90d52e2 100644
--- a/system/tests/system_health.bats
+++ b/system/tests/system_health.bats
@@ -9,6 +9,14 @@ setup() {
 
 field() { system/scripts/vault_index.py field system/config.md "$1"; }
 
+# skip_unless_role <role…>: skip this check on a machine whose role is not listed.
+skip_unless_role() {
+  local role
+  role="$(field machine_role 2>/dev/null || true)"
+  role="${role:-standalone}"
+  [[ " $* " == *" $role "* ]] || skip "not used on a $role machine"
+}
+
 @test "claude version is unchanged since the last health check (else re-run spike item 12)" {
   mkdir -p system/logs
   current="$(claude --version 2>/dev/null || echo unknown)"
@@ -30,16 +38,19 @@ field() { system/scripts/vault_index.py field system/config.md "$1"; }
 }
 
 @test "the intake, brief and debrief timers are active" {
+  skip_unless_role standalone server
   for t in jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer; do
     systemctl --user is-active --quiet "$t"
   done
 }
 
 @test "the focus tracker is active" {
+  skip_unless_role standalone
   systemctl --user is-active --quiet jarvis-focus.service
 }
 
 @test "lingering is enabled, so timers run while logged out" {
+  skip_unless_role standalone server
   [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" = yes ]
 }
 
```

- [ ] **Step 4: Run them and watch them pass.** Same command. Expected: `exit=0`. Then the gate (exit 0, 14 PASS) and lint (`0 errors`). Commit: `git add .claude/commands/setup.md .claude/commands/backup.md system/tests/system_health.bats system/tests/commands.bats README.md && git commit -m "feat(setup): machine role phase, client and server rules; backup and health by role"`.

### Task 6: Acceptance and status

**Files:**
- Create: `docs/superpowers/spikes/2026-10-03-plan-8a-acceptance.md`, `docs/superpowers/plans/2026-10-03-plan-8a-outcomes.md`
- Modify: `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md` (Plan 8 row), `README.md` (Status table)

- [ ] **Step 1: Debian.** The Debian command at the branch head. Expected: `host exit=0`, 14 PASS, no `kept:`.

- [ ] **Step 2: Role outputs on the host,** without writing anything there:

```bash
git archive --format=tar HEAD system/scripts/check_deps.sh system/scripts/vault_index.py system/scripts/vaultlib system/schemas   | ssh <debian-host> 'd=$(mktemp -d) && tar -x -C "$d" && for r in client server; do echo "== $r"; "$d/system/scripts/check_deps.sh" --role "$r"; done; rm -rf -- "$d"'
```
Expected: `client` lists only `claude git jq python3 pyyaml fts5` plus the optional items; `server` has no `hyprctl` line; every missing item has an `apt` hint.

- [ ] **Step 3: Role outputs locally** (Arch): `system/scripts/check_deps.sh --role client` and `--role server`. Expected: `pacman` hints for anything missing.

- [ ] **Step 4: Record** `docs/superpowers/spikes/2026-10-03-plan-8a-acceptance.md`. Include:
  - the date, commit, and Debian release and tool versions (`cat /etc/debian_version; jq --version; bats --version` on the host, recorded without the host name);
  - the host gate summary;
  - the role outputs from steps 2 and 3;
  - a verdict.

- [ ] **Step 5: Status.**
  - Roadmap Plan 8 row: `8a complete (<date>): 2026-10-03-plan-8a-roles-debian.md; 8b and 8c next`.
  - README Status table: a `8a. Machine roles and Debian` row marked Complete with plan and acceptance links. The `8. Two machines` row becomes `8b. Commit history` and `8c. Sync`, both Next.
  - Outcomes doc in the format of `2026-10-02-plan-6-outcomes.md`.
  - Gate, lint, commit: `docs: Plan 8a acceptance, status and outcomes`.
