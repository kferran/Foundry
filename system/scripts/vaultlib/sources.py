"""Source health for the smoke check and the brief (connector health spec §2).

Every fetch's failure reason starts with its class: auth, network, timeout, connector, claude or other. An auth
failure names the credential to renew and how; a source's failed readings in system/logs/smoke-<YYYY-MM>.jsonl give
the date it has been failing since.
"""
import json
import subprocess
from pathlib import Path

from . import extensions, frontmatter

CLASSES = ("auth", "network", "timeout", "connector", "claude", "other")
CONNECT = "reconnect it at claude.ai, Settings, Connectors"
# source -> (credential, renewal); an extension's sources come from its manifest.
CREDENTIALS = {
    "calendar": ("Google connector", CONNECT),
    "meetings": ("Google connector", CONNECT),
    "triage": ("Google connector", CONNECT),
    "notify": ("Slack connector", CONNECT),
}
CLAUDE = ("claude login", "claude, then /login, on the server")


def classed(reason: str) -> str:
    """The reason with a class in front: one without a known class is other."""
    reason = (reason or "").strip()
    return reason if reason.split(":", 1)[0] in CLASSES and ":" in reason else f"other: {reason or 'no reason given'}"


def _config(vault: Path) -> dict:
    try:
        return frontmatter.parse((vault / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return {}


def _extension_sources(vault: Path) -> dict:
    """source name -> (credential, renewal) from each enabled extension's manifest, read at call time."""
    out = {}
    for _, data in extensions.enabled(vault):
        for row in data.get("sources") or []:
            if isinstance(row, dict) and row.get("name"):
                out[str(row["name"])] = (str(row.get("credential", "")), str(row.get("renew", "")))
    return out


def _each(vault: Path) -> dict:
    """source -> [(source/item, credential, renewal)] for each smoke row an enabled extension checks per item (its
    `each` list command prints "item[<tab>credential<tab>renewal]" lines), or None when the list did not run."""
    out = {}
    for name, data in extensions.enabled(vault):
        for s in data.get("smoke") or []:
            if not isinstance(s, dict) or not s.get("each"):
                continue
            source, words = str(s.get("source") or name), str(s["each"]).split()
            try:
                r = subprocess.run([str(vault / "extensions" / name / words[0]), *words[1:]], cwd=vault,
                                   capture_output=True, text=True, timeout=60)
            except (OSError, subprocess.TimeoutExpired):
                out[source] = None
                continue
            rows = [(line.split("\t") + ["", ""])[:3] for line in r.stdout.splitlines() if line.strip()]
            out[source] = None if r.returncode else [(f"{source}/{a}", b, c) for a, b, c in rows]
    return out


def credential(vault: Path, source: str, reason: str):
    """(credential, renewal) for a failure that needs the owner's login, else None. A claude that is missing is
    not a login to renew."""
    cls = classed(reason).split(":", 1)[0]
    if cls == "claude" and "not found" not in reason:
        return CLAUDE
    if cls != "auth":
        return None
    found = CREDENTIALS.get(source) or _extension_sources(vault).get(source)
    if found is None and "/" in source:
        rows = _each(vault).get(source.split("/", 1)[0]) or []
        found = next(((c, r) for n, c, r in rows if n == source and c), None)
    return found or None


def _records(paths):
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                yield r


def streak(vault: Path, source: str, cls: str = "", until: str = ""):
    """(count, since date, last reason) of the source's trailing failed smoke readings up to the date `until`
    (inclusive; all when empty), counting only reasons of class `cls` when given. A held reading is no reading."""
    if source == "notify":
        paths = sorted((vault / "system" / "logs").glob("notify-*.jsonl"))
        rows = [r for r in _records(paths) if r.get("exit") != 4]   # 4 is a busy tick, no reading
    else:
        paths = sorted((vault / "system" / "logs").glob("smoke-*.jsonl"))
        rows = [r for r in _records(paths) if r.get("source") == source
                and not str(r.get("reason", "")).startswith("held: ")]
    if until:
        rows = [r for r in rows if str(r.get("time", ""))[:10] <= until]
    n, since, last = 0, "", ""
    for r in reversed(rows):
        reason = classed(str(r.get("reason", "")))
        if r.get("exit") in (0, None) or (cls and not reason.startswith(cls + ":")):
            break
        n, since, last = n + 1, str(r.get("time", ""))[:10], last or reason
    return n, since, last


def _reading(vault: Path, source: str, day: str):
    """The source's last smoke reading on `day` as ("ok"|"failed", reason), or None."""
    paths = sorted((vault / "system" / "logs").glob(f"smoke-{day[:7]}.jsonl"))
    rows = [r for r in _records(paths) if r.get("source") == source and str(r.get("time", ""))[:10] == day
            and not str(r.get("reason", "")).startswith("held: ")]
    if not rows:
        return None
    return ("ok", "") if rows[-1].get("exit") == 0 else ("failed", str(rows[-1].get("reason", "")))


def report(vault: Path, day: str, given: dict) -> list:
    """sources.md lines: one per source, ok, off, unknown or failed with its class, since date and renewal.
    `given` holds what the brief read itself (source -> (state, reason)); the rest come from that morning's smoke
    check, and notify from its own log."""
    vault, config = Path(vault), _config(Path(vault))
    order = ["calendar", "meetings", "triage"]
    ext = list(_extension_sources(vault))
    # A per-item source lists its items; with none it reads off, and a list that did not run is one line read from
    # the smoke check.
    each = _each(vault)
    for source, rows in each.items():
        ext += [n for n, _, _ in rows] if rows else [source]
    # A listed extension with no folder reads as failed, once per name (its sources are not known without it).
    loaded = {n for n, _ in extensions.enabled(vault)}
    missing = [n for n in extensions.listed(vault)
               if n not in loaded and not (vault / "extensions" / n / "extension.md").is_file()]
    order += ext + [n for n in missing if n not in ext]
    order += ["notify"]
    off = {
        "meetings": str(config.get("meetings_enabled", "false")).lower() != "true",
        "triage": str(config.get("triage_enabled", "false")).lower() != "true",
        **{source: True for source, rows in each.items() if rows == []},
        "notify": not config.get("slack_notify_channel"),
    }
    out = []
    for s in order:
        if s in missing and s not in ext:
            state, reason = "failed", f"other: extensions/{s}/ is missing"
        elif s in given:
            state, reason = given[s]
        elif off.get(s):
            state, reason = "off", ""
        elif s == "notify":
            n, _, last = streak(vault, s, until=day)
            state, reason = ("failed", last) if n else ("ok", "")
        else:
            state, reason = _reading(vault, s, day) or ("unknown", "")
        if state != "failed":
            out.append(f"- {s}: {state}" + (" (no smoke check reading today)" if state == "unknown" else ""))
            continue
        reason = classed(reason)
        _, since, _ = streak(vault, s, until=day)
        line = f"- {s}: failed: {reason} (since {since or day})"
        cred = credential(vault, s, reason)
        out.append(line + (f"; expired: {cred[0]}; renew: {cred[1]}" if cred else ""))
    return out
