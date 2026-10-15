"""Extensions (extensions spec §3): read extensions/<name>/extension.md manifests for the shared scripts."""
import re
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
