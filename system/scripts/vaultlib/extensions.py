"""Extensions (extensions spec §3): read extensions/<name>/extension.md manifests for the shared scripts."""
import json
import os
import re
import subprocess
from pathlib import Path

from . import frontmatter

CONTRACT = 1
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
FIELDS = {"name", "contract", "description", "requires", "config_keys", "sources", "smoke", "brief", "debrief",
          "units", "alert_tags", "allow", "deps", "index_ignore", "importer"}


def _strs(value) -> list:
    return [str(v) for v in value] if isinstance(value, list) else []


def listed(vault: Path) -> list:
    path = vault / "system" / "config.md"
    if not path.is_file():
        return []
    try:
        cfg = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return []
    return _strs(cfg.get("extensions"))


def manifest(vault: Path, name: str):
    """(data, None) or (None, reason)."""
    if not NAME.fullmatch(name):
        return None, f"{name}: not an extension name (lower-case letters, digits, - and _)"
    p = vault / "extensions" / name / "extension.md"
    if not p.is_file():
        return None, f"{name}: listed in extensions but extensions/{name}/ does not exist"
    note = frontmatter.parse(p.read_text(encoding="utf-8"))
    if note.error:
        return None, f"{name}: extension.md is not readable: {note.error}"
    data = note.data or {}
    unknown = sorted(set(data) - FIELDS)
    if data.get("name") != name:
        return None, f"{name}: extension.md names {data.get('name')!r}, not {name!r}"
    if data.get("contract") != str(CONTRACT):
        return None, f"{name}: contract {data.get('contract')!r}; this core reads contract {CONTRACT}"
    if unknown:
        return None, f"{name}: unknown manifest field(s) {', '.join(unknown)}"
    return data, None


def _resolve(vault: Path):
    """(loaded {name: data} in dependency order, reasons)."""
    names = listed(vault)
    loadable, reasons = {}, []
    for name in names:
        data, why = manifest(vault, name)
        if why:
            reasons.append(why)
        else:
            loadable[name] = data
    # A requires entry that is not listed, or that cannot load, takes its dependents out; repeat to a fixed point.
    changed = True
    while changed:
        changed = False
        for name in list(loadable):
            gone = [r for r in _strs(loadable[name].get("requires")) if r not in loadable]
            if gone:
                reasons.append(f"{name}: requires {', '.join(gone)}, which is missing or not loadable")
                del loadable[name]
                changed = True
    order, done = [], set()

    def visit(name, trail):
        if name in done:
            return
        if name in trail:
            raise ValueError(name)
        for r in _strs(loadable[name].get("requires")):
            visit(r, trail | {name})
        done.add(name)
        order.append(name)

    for name in names:
        if name in loadable and name not in done:
            try:
                visit(name, frozenset())
            except ValueError:
                reasons.append(f"{name}: requires form a cycle")
                loadable.pop(name, None)
    return {n: loadable[n] for n in order if n in loadable}, reasons


def check(vault: Path) -> list:
    """One reason per listed extension that cannot load (missing folder, bad manifest, missing requires)."""
    return _resolve(vault)[1]


def enabled(vault: Path) -> list:
    """(name, data) of the listed extensions that load, requires first (a stable topological order)."""
    return list(_resolve(vault)[0].items())


def ignore(vault: Path) -> list:
    return [p for _, d in enabled(vault) for p in _strs(d.get("index_ignore"))]


# Turning an extension on (extensions spec §4). config.md is edited as text: only the `extensions:` line changes, or
# one is added before the frontmatter's closing line, so the owner's comments and order stay as they are.
def enable(vault: Path, name: str) -> bool:
    """Add `name` to the extensions list. Returns False when it is already listed or config.md has no frontmatter."""
    path = Path(vault) / "system" / "config.md"
    names = listed(Path(vault))
    if name in names or not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").split("\n")
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return False
    end = lines.index("---", 1)
    new = "extensions: [" + ", ".join(json.dumps(n) for n in [*names, name]) + "]"
    at = next((i for i in range(1, end) if lines[i].startswith("extensions:")), None)
    if at is None:
        lines.insert(end, new)
    else:
        lines[at] = new
    _save(path, "\n".join(lines))
    return True


# One rule per feature that moved out of core: the old switch that means the owner used it. Each runs once per vault
# (system/logs/extensions-migrated), so an extension the owner turns off later stays off.
MIGRATIONS = {
    "handoffs": lambda vault, cfg: bool(cfg.get("handoffs_projects")),
    "dtcc": lambda vault, cfg: (vault / "system" / "dtcc" / "map.yaml").is_file(),
}
MIGRATED = Path("system/logs/extensions-migrated")


def migrate(vault: Path) -> list:
    """Enable each moved feature whose old switch is set and that was never migrated. Returns the names enabled."""
    vault = Path(vault)
    path = vault / "system" / "config.md"
    try:
        cfg = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return []
    log = vault / MIGRATED
    done = set(log.read_text(encoding="utf-8").split()) if log.is_file() else set()
    out = []
    for name, used in MIGRATIONS.items():
        if name in done or not used(vault, cfg):
            continue
        if enable(vault, name):
            out.append(name)
        done.add(name)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("".join(f"{n}\n" for n in sorted(done)), encoding="utf-8")
    return out


# The allow rules (extensions spec §3). The settings file is edited as text, whole lines only: a rule goes right
# after the `"allow": [` line, written as `      "<rule>",`. Rewriting the file with a JSON tool would reformat it and
# break every later template merge. system/logs/extensions-allow.json maps each rule written to its extension, so a
# removal needs no manifest and never touches a rule the owner wrote by hand.
ALLOW_ANCHOR = '    "allow": ['
ALLOW_LOG = Path("system/logs/extensions-allow.json")


def _settings(vault: Path) -> Path:
    return vault / ".claude" / "settings.json"


def _allow_log(vault: Path) -> dict:
    try:
        data = json.loads((vault / ALLOW_LOG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _save(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _rule_line(rule: str, comma: bool = True) -> str:
    return f"      {json.dumps(rule)}{',' if comma else ''}"


def write_allow(vault: Path):
    """Insert every enabled extension's rules that are not already allowed. Returns (added rules, error or None);
    nothing is written when the result would not be valid JSON."""
    vault = Path(vault)
    path = _settings(vault)
    if not path.is_file():
        return [], f"{path.relative_to(vault)} does not exist"
    text = path.read_text(encoding="utf-8")
    try:
        have = set(json.loads(text).get("permissions", {}).get("allow", []))
    except (ValueError, AttributeError):
        return [], f"{path.relative_to(vault)} is not valid JSON"
    lines = text.split("\n")
    if ALLOW_ANCHOR not in lines:
        return [], f'{path.relative_to(vault)} has no line {ALLOW_ANCHOR.strip()!r} to insert after'
    wanted = []
    for name, data in enabled(vault):
        for rule in _strs(data.get("allow")):
            if rule not in have and rule not in [r for r, _ in wanted]:
                wanted.append((rule, name))
    if not wanted:
        return [], None
    at = lines.index(ALLOW_ANCHOR) + 1
    # An empty list closes on the next line: the last inserted rule then takes no comma.
    last_comma = not lines[at].strip().startswith("]")
    new = [_rule_line(r, last_comma or i < len(wanted) - 1) for i, (r, _) in enumerate(wanted)]
    out = "\n".join(lines[:at] + new + lines[at:])
    try:
        json.loads(out)
    except ValueError:
        return [], f"{path.relative_to(vault)} would not stay valid JSON; nothing was written"
    _save(path, out)
    log = _allow_log(vault)
    log.update({r: n for r, n in wanted})
    (vault / ALLOW_LOG).parent.mkdir(parents=True, exist_ok=True)
    _save(vault / ALLOW_LOG, json.dumps(log, indent=2, sort_keys=True) + "\n")
    return [r for r, _ in wanted], None


def remove_allow(vault: Path, name: str):
    """Delete the lines this module wrote for `name`. Returns (removed rules, error or None)."""
    vault = Path(vault)
    path = _settings(vault)
    log = _allow_log(vault)
    mine = [r for r, n in log.items() if n == name]
    if not mine:
        return [], None
    if not path.is_file():
        return [], f"{path.relative_to(vault)} does not exist"
    lines = path.read_text(encoding="utf-8").split("\n")
    gone, keep = [], []
    drop = {_rule_line(r, True): r for r in mine} | {_rule_line(r, False): r for r in mine}
    for line in lines:
        if line in drop:
            gone.append(drop[line])
        else:
            keep.append(line)
    out = "\n".join(keep)
    try:
        json.loads(out)
    except ValueError:
        return [], f"{path.relative_to(vault)} would not stay valid JSON; nothing was removed"
    if gone:
        _save(path, out)
    for r in mine:
        log.pop(r, None)
    _save(vault / ALLOW_LOG, json.dumps(log, indent=2, sort_keys=True) + "\n")
    return gone, None


# Skills (extensions spec §3): each enabled extension's skills/<skill>/ is linked into .claude/skills/. The links
# are machine state: they are added to .git/info/exclude, so the tracked .gitignore stays template-owned.
SKILLS = Path(".claude") / "skills"
LINK_PREFIX = "../../extensions/"


def _exclude_file(vault: Path):
    try:
        out = subprocess.run(["git", "-C", str(vault), "rev-parse", "--git-path", "info/exclude"],
                             capture_output=True, text=True)
    except OSError:
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    p = Path(out.stdout.strip())
    return p if p.is_absolute() else vault / p


def link(vault: Path) -> list:
    """Make .claude/skills/ match the enabled extensions. Returns "linked <skill>" / "unlinked <skill>" lines.
    A real file or folder, or a link that points anywhere but into extensions/, is never touched."""
    vault = Path(vault)
    skills = vault / SKILLS
    want = {}
    for name, _ in enabled(vault):
        for d in sorted((vault / "extensions" / name / "skills").glob("*/")):
            if d.is_dir() and not d.name.startswith("."):
                want.setdefault(d.name, f"{LINK_PREFIX}{name}/skills/{d.name}")
    out = []
    if skills.is_dir():
        for p in sorted(skills.iterdir()):
            if p.is_symlink() and os.readlink(p).startswith(LINK_PREFIX) and want.get(p.name) != os.readlink(p):
                p.unlink()
                out.append(f"unlinked {p.name}")
    added = []
    for skill, target in want.items():
        p = skills / skill
        if p.is_symlink():
            if os.readlink(p) == target:
                added.append(skill)
            continue
        if p.exists():
            continue
        skills.mkdir(parents=True, exist_ok=True)
        os.symlink(target, p)
        added.append(skill)
        out.append(f"linked {skill}")
    exclude = _exclude_file(vault)
    if exclude is not None and added:
        have = exclude.read_text(encoding="utf-8").split("\n") if exclude.is_file() else []
        new = [f"/{(SKILLS / s).as_posix()}" for s in added if f"/{(SKILLS / s).as_posix()}" not in have]
        if new:
            exclude.parent.mkdir(parents=True, exist_ok=True)
            with exclude.open("a", encoding="utf-8") as f:
                if have and have[-1] != "":
                    f.write("\n")
                f.write("\n".join(new) + "\n")
    return out
