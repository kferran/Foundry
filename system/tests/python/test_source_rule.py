"""The Source rule (factory F3 §3.1): a script that runs a connector session (`connector_run`) is a Source and carries
the shared parts, and no script starts a claude session outside the three runners."""
import ast
import re
import shutil
import subprocess

import pytest

from helpers import REPO
from vaultlib import frontmatter

# The rule guards the template; tree() copies the whole checkout, so in a vault every test would see its own scripts.
pytestmark = pytest.mark.skipif(
    (REPO / "system/config.md").exists(),
    reason="this checkout is a vault (system/config.md exists); the rule guards the template")

# Core Sources: their smoke rows (or the reason they have none), then their alert tag when the script sets no FETCH_TAG.
CORE = {
    "calendar_fetch.sh": (("calendar",), "calendar"),
    "meetings_fetch.sh": (("meetings",), None),
    "triage_fetch.sh": (("triage", "triage_chat"), None),
    "notify.sh": ("its --check posts a message to the channel", None),
}


def tree(tmp_path):
    """A copy of the tracked files, modes kept, in a fresh git repository."""
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, text=True, check=True)
    for rel in filter(None, out.stdout.split("\0")):
        src = REPO / rel
        if src.is_file():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, tmp_path / rel)
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    return tmp_path


# The three runners start sessions. lib_confine.sh (`claude mcp list`), smoke_check.sh (`--version`) and
# vaultlib/nightshift_run.py (`auth status`) call the binary for no session, so the patterns pass them.
RUNNERS = {"system/scripts/lib_connector.sh", "system/scripts/run_headless.sh",
           "system/scripts/vaultlib/nightshift_session.py"}
SESSION_SH = re.compile(r"(\bclaude\b|\$\{?(CLAUDE_BIN|claude_bin)\b)[^#|;&]*\s(-p|--print)\b")
SESSION_PY = re.compile(r"""(["']claude["']|claude_bin\(|CLAUDE_BIN).*["'](-p|--print)["']""")
NEVER_FEATURE = {"vaultlib.api", "vaultlib.connector"}   # every extension imports the API; the walker's own home
WALKERS = {"walk", "check_stream"}
SMOKE_ROW = r"^\s*connector (\w+) .*system/scripts/{} --check"


def tracked(root):
    """Tracked paths under system/scripts and extensions/*/scripts."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "system/scripts", "extensions"],
                         capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split("\0") if re.match(r"(system/scripts|extensions/[^/]+/scripts)/", p)]


def code(root, rel):
    """(line number, line) for each line that is not a comment."""
    lines = (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    return [(n, line) for n, line in enumerate(lines, 1) if not line.lstrip().startswith("#")]


def session_problems(root):
    out = []
    for rel in tracked(root):
        if rel not in RUNNERS:
            pattern = SESSION_PY if rel.endswith(".py") else SESSION_SH
            out += [f"{rel}:{n}: starts a claude session outside a runner" for n, line in code(root, rel)
                    if pattern.search(line)]
    return out


def sources(root):
    return [rel for rel in tracked(root) if not rel.endswith(".py") and rel != "system/scripts/lib_connector.sh"
            and any(re.search(r"\bconnector_run\b", line) for _, line in code(root, rel))]


def calls_walker(path):
    """A call to walk( or check_stream( by the name it was imported under from the shared parts, or as
    connector.<x>/api.<x> (os.walk(, self.walk( and a walk( defined or imported elsewhere are not it)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
             and (n.module in NEVER_FEATURE or n.level == 1 and n.module == "connector")   # vaultlib's own `.connector`
             for a in n.names if a.name in WALKERS}
    return any(isinstance(n, ast.Call) and (
        isinstance(n.func, ast.Name) and n.func.id in names
        or isinstance(n.func, ast.Attribute) and n.func.attr in WALKERS
        and isinstance(n.func.value, ast.Name) and n.func.value.id in {"connector", "api"})
        for n in ast.walk(tree))


def feature_modules(path, base):
    """The modules under base (a scripts folder) that path imports directly, as pkg.mod or from pkg import mod."""
    names = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            names += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            names += [n.module] + [f"{n.module}.{a.name}" for a in n.names]
    paths = [base / (m.replace(".", "/") + ".py") for m in names if m not in NEVER_FEATURE]
    return [p for p in paths if p.is_file()]


def checkers(lines):
    """The programs fed the session's stream: a *.py path, or "$VAR" set to one."""
    out = []
    for _, line in lines:
        if '< "$work/out.jsonl"' not in line or '2> "$work/check.err"' not in line:
            continue
        m = re.search(r"[\w./-]+\.py\b", line)
        prog = m and m.group(0)
        if not m and (var := re.search(r'"\$(\w+)"', line)):
            prog = next((a.group(1) for _, x in lines if (a := re.match(rf"\s*{var.group(1)}=[\"']?([\w./-]+)", x))),
                        None)
        if prog and prog not in out:
            out.append(prog)
    return out


def manifest(root, ext):
    path = root / "extensions" / ext / "extension.md"
    return (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}) if path.is_file() else {}


def alert_tags(root):
    body = ast.parse((root / "system/scripts/vaultlib/alerts.py").read_text(encoding="utf-8")).body
    return next(ast.literal_eval(n.value) for n in body
                if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "TAGS" for t in n.targets))


def source_problems(root, table=CORE):
    out, found = [], set()
    smoke = (root / "system/scripts/smoke_check.sh").read_text(encoding="utf-8").splitlines()
    for rel in sources(root):
        lines = code(root, rel)
        core = rel.startswith("system/scripts/")
        name, ext = rel.rsplit("/", 1)[1], None if core else rel.split("/")[1]
        base = root / ("system/scripts" if core else f"extensions/{ext}/scripts")
        # 1: lib_fetch.sh after lib_connector.sh
        conn = next((n for n, line in lines if re.match(r"\s*source\s+\S*lib_connector\.sh", line)), None)
        if conn is None or not any(n > conn and re.match(r"\s*source\s+\S*lib_fetch\.sh", line) for n, line in lines):
            out.append(f"{rel}: does not source lib_fetch.sh after lib_connector.sh")
        # 2: a checker that, or whose own feature module, calls the shared walker
        progs = checkers(lines)
        if not progs:
            out.append(f"{rel}: no checker reads $work/out.jsonl")
        for prog in progs:
            path = root / prog
            if not (path.is_file() and any(map(calls_walker, [path, *feature_modules(path, base)]))):
                out.append(f"{rel}: its checker {prog} calls neither walk( nor check_stream(")
        if core and name not in table:
            out.append(f"{rel}: a core Source missing from the table")
            continue
        if core:
            found.add(name)
        # 3: a smoke row when the script accepts --check
        if any("--check" in line or "fetch_check_arg" in line for _, line in lines):
            if core:
                rows, want = tuple(m.group(1) for line in smoke
                                   if (m := re.match(SMOKE_ROW.format(re.escape(name)), line))), table[name][0]
                if want == () and not rows:
                    out.append(f"{rel}: accepts --check and has no smoke row and no reason in the table")
                elif isinstance(want, str) and rows:
                    out.append(f"{rel}: has smoke rows {rows} but the table gives a reason")
                elif not isinstance(want, str) and rows != want:
                    out.append(f"{rel}: smoke rows {rows} differ from the table's {want}")
            elif not any(isinstance(s, dict) and s.get("connector") == "true"
                         and str(s.get("run", "")).split()[:2] == [rel.split("/", 2)[2], "--check"]
                         for s in manifest(root, ext).get("smoke") or []):
                out.append(f"{rel}: accepts --check and has no connector smoke row in its manifest")
        # 4: its alert tag
        tag = next((m.group(1) for _, line in lines if (m := re.search(r"\bFETCH_TAG=(\w+)", line))), None)
        if tag is None and not (core and table[name][1]):
            out.append(f"{rel}: sets no FETCH_TAG")
        elif tag is None and table[name][1] not in alert_tags(root):
            out.append(f"{rel}: the table's tag {table[name][1]} is not a key of alerts.TAGS")
        elif tag and core and tag not in alert_tags(root):
            out.append(f"{rel}: FETCH_TAG {tag} is not a key of alerts.TAGS")
        elif tag and not core and tag not in {t if isinstance(t, str) else t.get("tag")
                                              for t in manifest(root, ext).get("alert_tags") or []}:
            out.append(f"{rel}: FETCH_TAG {tag} is not in its manifest's alert_tags")
    out += [f"{name}: a table row with no script" for name in table if name not in found]
    return out


def smoke_name_problems(root):
    """An extension's smoke row named like a core row or another extension's row shares its log lines and streaks."""
    text = (root / "system/scripts/smoke_check.sh").read_text(encoding="utf-8")
    seen = {n: "core" for n in re.findall(r'^\s*(?:check|connector|report|smoke_logline) "?(\w+)', text, re.M)}
    out = []
    for path in sorted((root / "extensions").glob("*/extension.md")):
        ext = path.parent.name
        for s in manifest(root, ext).get("smoke") or []:
            name = str(s.get("source") or ext) if isinstance(s, dict) else ext
            if name in seen:
                out.append(f"extensions/{ext}: smoke row {name} is also a {seen[name]} row")
            seen.setdefault(name, f"{ext} extension")
    return out


def test_no_extension_smoke_row_shares_a_name():
    assert smoke_name_problems(REPO) == []


def test_a_shared_smoke_row_name_is_caught(tmp_path):
    root = tree(tmp_path)
    path = root / "extensions/handoffs/extension.md"
    path.write_text(path.read_text().replace("{source: handoffs,", "{source: calendar,"))
    assert smoke_name_problems(root) == ["extensions/handoffs: smoke row calendar is also a core row"]


def test_no_script_starts_a_session_outside_a_runner():
    assert session_problems(REPO) == []


def test_every_source_carries_its_parts():
    assert source_problems(REPO) == []


def test_the_known_sources_are_still_found():
    # A detection guard: a new Source adds to the set without editing this test.
    assert {
        "extensions/handoffs/scripts/jira_fetch.sh", "extensions/intraday/scripts/watch_fetch.sh",
        "extensions/telemetry/scripts/rca_file.sh", "system/scripts/calendar_fetch.sh",
        "system/scripts/meetings_fetch.sh", "system/scripts/notify.sh",
        "system/scripts/triage_fetch.sh"} <= set(sources(REPO))


JIRA = "extensions/handoffs/scripts/jira_fetch.sh"
CHECKS = "calls neither walk( nor check_stream("


@pytest.mark.parametrize("rel,edit,want", [
    ("extensions/handoffs/scripts/x.sh", lambda t: 'claude -p "$p"\n',
     "extensions/handoffs/scripts/x.sh:1: starts a claude session outside a runner"),
    ("system/scripts/x.sh", lambda t: '"${CLAUDE_BIN:-claude}" -p "$p"\n',
     "system/scripts/x.sh:1: starts a claude session outside a runner"),
    ("system/scripts/x.py", lambda t: 'import subprocess\nsubprocess.run([claude_bin(), "-p", p])\n',
     "system/scripts/x.py:2: starts a claude session outside a runner"),
    ("system/scripts/y.sh", lambda t: '# a comment: claude -p\nclaude --output-format stream-json -p "$p"\n',
     "system/scripts/y.sh:2: starts a claude session outside a runner"),
    ("extensions/handoffs/scripts/y.py",
     lambda t: 'import subprocess\nsubprocess.run(["claude", "--model", m, "--print", p])\n',
     "extensions/handoffs/scripts/y.py:2: starts a claude session outside a runner"),
])
def test_a_session_outside_a_runner_is_caught(tmp_path, rel, edit, want):
    root = tree(tmp_path)
    (root / rel).write_text(edit(""))
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    assert session_problems(root) == [want]


@pytest.mark.parametrize("rel,edit,want", [
    (JIRA, lambda t: t.replace("source system/scripts/lib_fetch.sh\n", ""),
     f"{JIRA}: does not source lib_fetch.sh after lib_connector.sh"),
    (JIRA, lambda t: t.replace(' < "$work/out.jsonl"', ""), f"{JIRA}: no checker reads $work/out.jsonl"),
    ("extensions/handoffs/scripts/jira_handoffs.py", lambda t: t.replace("check_stream(", "check_other("),
     f"{JIRA}: its checker extensions/handoffs/scripts/jira_handoffs.py {CHECKS}"),
    # vaultlib/index.py, which it imports, calls os.walk( and self.walk(: neither is the walker.
    ("system/scripts/meetings_extract.py", lambda t: t.replace("check_stream(", "check_other("),
     f"system/scripts/meetings_fetch.sh: its checker system/scripts/meetings_extract.py {CHECKS}"),
    ("system/scripts/calendar_tsv.py",
     lambda t: t.replace("too_large, walk\n", "too_large\nfrom os import walk\n"),
     f"system/scripts/calendar_fetch.sh: its checker system/scripts/calendar_tsv.py {CHECKS}"),
    ("extensions/handoffs/extension.md", lambda t: re.sub(r"smoke:\n  - \{source: handoffs, .*\}\n", "", t),
     f"{JIRA}: accepts --check and has no connector smoke row in its manifest"),
    (JIRA, lambda t: t.replace("FETCH_TAG=handoffs", "FETCH_TAG=handoff"),
     f"{JIRA}: FETCH_TAG handoff is not in its manifest's alert_tags"),
    ("system/scripts/meetings_fetch.sh", lambda t: t.replace("FETCH_TAG=meetings", "FETCH_TAG=meeting"),
     "system/scripts/meetings_fetch.sh: FETCH_TAG meeting is not a key of alerts.TAGS"),
])
def test_a_source_missing_a_part_is_caught(tmp_path, rel, edit, want):
    root = tree(tmp_path)
    before = (root / rel).read_text()
    (root / rel).write_text(edit(before))
    assert (root / rel).read_text() != before, "the seed changed nothing"
    assert source_problems(root) == [want]


@pytest.mark.parametrize("table,want", [
    ({k: v for k, v in CORE.items() if k != "notify.sh"},
     "system/scripts/notify.sh: a core Source missing from the table"),
    ({**CORE, "gone_fetch.sh": ((), None)}, "gone_fetch.sh: a table row with no script"),
    ({**CORE, "notify.sh": ((), None)},
     "system/scripts/notify.sh: accepts --check and has no smoke row and no reason in the table"),
    ({**CORE, "triage_fetch.sh": (("triage",), None)},
     "system/scripts/triage_fetch.sh: smoke rows ('triage', 'triage_chat') differ from the table's ('triage',)"),
    ({**CORE, "calendar_fetch.sh": (("calendar",), None)}, "system/scripts/calendar_fetch.sh: sets no FETCH_TAG"),
    ({**CORE, "meetings_fetch.sh": ((), None)},
     "system/scripts/meetings_fetch.sh: smoke rows ('meetings',) differ from the table's ()"),
    ({**CORE, "calendar_fetch.sh": ("a reason", "calendar")},
     "system/scripts/calendar_fetch.sh: has smoke rows ('calendar',) but the table gives a reason"),
    ({**CORE, "calendar_fetch.sh": (("calendar",), "calender")},
     "system/scripts/calendar_fetch.sh: the table's tag calender is not a key of alerts.TAGS"),
])
def test_a_table_out_of_step_is_caught(table, want):
    assert source_problems(REPO, table) == [want]
