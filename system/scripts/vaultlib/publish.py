"""Ultra Magnus: staged, validated, journaled publish of headless output (spec §6.20)."""
import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import frontmatter, links as linkmod, schema as schemamod
from .index import NAME_EXCLUDED, Index, wall_blocked

RUN_ID = re.compile(r"^\d{8}T\d{6}-(ingest|brief|debrief)-[0-9a-f]{4}$")
DECISION_KINDS = {"noop", "patch", "create", "deprecate", "supersede"}
SHRINK_EXEMPT = {"deprecate", "supersede"}
PROTECTED = ("accepted_at", "rejected_at")
MIN_BODY_RATIO = 0.6
RECENT_SECONDS = 60
DECISIONS = "_decisions.jsonl"
HEADING = re.compile(r"^#{1,6}\s+\S")
_rename = os.replace  # indirection so tests can inject crashes and races


class PublishError(Exception):
    pass


@dataclass
class Problem:
    path: str
    reason: str


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_run_id(run_id: str) -> str:
    match = RUN_ID.match(run_id or "")
    if not match:
        raise PublishError(f"invalid run id: {run_id!r}")
    return match.group(1)


def run_dir(vault, run_id) -> Path:
    return Path(vault) / "system" / "logs" / "runs" / run_id


def staging_dir(vault, run_id) -> Path:
    return Path(vault) / "wiki" / ".staging" / run_id


def safe_rel(rel) -> str:
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel:
        raise PublishError(f"unsafe path: {rel!r}")
    parts = Path(rel).parts
    if ".." in parts or any(p.startswith(".") for p in parts):
        raise PublishError(f"unsafe path: {rel!r}")
    return Path(rel).as_posix()


def target_matches(target: str, targets) -> bool:
    for t in targets:
        if t.endswith("/**"):
            if target.startswith(t[:-2]):
                return True
        elif target == t:
            return True
    return False


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _target_files(vault: Path, targets):
    for t in targets:
        if t.endswith("/**"):
            base = vault / t[:-3]
            if not base.is_dir():
                continue
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in files:
                    path = Path(root) / name
                    if path.is_file() and not path.is_symlink():
                        yield path.relative_to(vault).as_posix()
        else:
            path = vault / t
            if path.is_file() and not path.is_symlink():
                yield t


def snapshot(vault, run_id, targets) -> Path:
    vault = Path(vault)
    check_run_id(run_id)
    for t in targets:
        safe_rel(t[:-3] if t.endswith("/**") else t)
    rd = run_dir(vault, run_id)
    if rd.exists() or staging_dir(vault, run_id).exists():
        raise PublishError(f"run already exists: {run_id}")
    files = {rel: sha256_file(vault / rel) for rel in _target_files(vault, targets)}
    _write_json(rd / "snapshot.json", {"targets": list(targets), "files": files, "staged": {}})
    staging_dir(vault, run_id).mkdir(parents=True)
    return rd / "snapshot.json"


def load_snapshot(vault, run_id) -> dict:
    check_run_id(run_id)
    path = run_dir(vault, run_id) / "snapshot.json"
    if not path.is_file():
        raise PublishError(f"unknown run: {run_id}")
    try:
        snap = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise PublishError(f"corrupt snapshot: {exc}")
    if (not isinstance(snap, dict) or not isinstance(snap.get("targets"), list)
            or not all(isinstance(t, str) for t in snap["targets"])
            or not isinstance(snap.get("files"), dict) or not isinstance(snap.get("staged"), dict)):
        raise PublishError("corrupt snapshot: unexpected structure")
    return snap


def record_stage(vault, run_id, target) -> Path:
    vault = Path(vault)
    target = safe_rel(target)
    snap = load_snapshot(vault, run_id)
    if not staging_dir(vault, run_id).is_dir():
        raise PublishError(f"run is not open: {run_id}")
    if not target_matches(target, snap["targets"]):
        raise PublishError(f"not a publishable target for this run: {target}")
    src = vault / target
    if src.is_symlink() or not src.is_file():
        raise PublishError(f"no such note to stage: {target}")
    if target not in snap["files"]:
        raise PublishError(f"target was created during the run: {target}")
    dst = staging_dir(vault, run_id) / target
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    snap["staged"][target] = sha256_file(dst)
    _write_json(run_dir(vault, run_id) / "snapshot.json", snap)
    return dst


def staged_targets(vault, run_id):
    sd = staging_dir(vault, run_id)
    staged, problems = [], []
    if not sd.is_dir():
        return staged, problems
    for path in sorted(sd.rglob("*")):
        rel = path.relative_to(sd).as_posix()
        if path.is_symlink():
            problems.append(Problem(rel, "staged path is a symlink"))
        elif path.is_file() and rel != DECISIONS:
            staged.append(rel)
    return staged, problems


def read_decisions(vault, run_id):
    path = staging_dir(vault, run_id) / DECISIONS
    if not path.is_file() or path.is_symlink():
        return None, []
    decisions, problems = [], []
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(Problem(DECISIONS, f"line {n}: invalid JSON: {exc.msg}"))
            continue
        if (not isinstance(record, dict) or not isinstance(record.get("decision"), str)
                or record["decision"] not in DECISION_KINDS
                or any(not isinstance(record.get(k), str) for k in ("item", "source", "reason"))
                or not (record.get("target") is None or isinstance(record.get("target"), str))):
            problems.append(Problem(DECISIONS, f"line {n}: invalid decision record"))
            continue
        target = record.get("target")
        try:
            if target is not None:
                safe_rel(target)
        except PublishError as exc:
            problems.append(Problem(DECISIONS, f"line {n}: {exc}"))
            continue
        if record["decision"] == "noop":
            if not target or not (Path(vault) / target).is_file():
                problems.append(Problem(DECISIONS, f"line {n}: noop must cite an existing note"))
                continue
        elif not target:
            problems.append(Problem(DECISIONS, f"line {n}: {record['decision']} needs a target"))
            continue
        decisions.append(record)
    return decisions, problems


def _headings(body: str) -> set:
    return {text.strip() for _, text in linkmod.code_free_lines(body, 1) if HEADING.match(text)}


def _protected(old, new, target) -> list:
    out, od, nd = [], old.data or {}, new.data or {}
    for key in PROTECTED:
        if od.get(key) != nd.get(key):
            out.append(Problem(target, f"protected field {key} changed"))
    oldp = od.get("provenance") if isinstance(od.get("provenance"), list) else []
    newp = nd.get("provenance") if isinstance(nd.get("provenance"), list) else []
    if any(p not in newp for p in oldp):
        out.append(Problem(target, "provenance entries removed"))
    return out


def _shrink(old, new, target) -> list:
    out = []
    missing = set(map(str, (old.data or {}).keys())) - set(map(str, (new.data or {}).keys()))
    if missing:
        out.append(Problem(target, f"shrink guard: frontmatter keys removed: {', '.join(sorted(missing))}"))
    lost = _headings(old.body) - _headings(new.body)
    if lost:
        out.append(Problem(target, f"shrink guard: headings removed: {', '.join(sorted(lost))}"))
    old_len, new_len = len(old.body.strip()), len(new.body.strip())
    if old_len and new_len < MIN_BODY_RATIO * old_len:
        out.append(Problem(target, "shrink guard: body shrank below 60% of the original"))
    return out


def _expected(snap, target):
    return snap["staged"].get(target, snap["files"].get(target))


def _conflict(vault: Path, target, snap, now) -> list:
    path, expected = vault / target, _expected(snap, target)
    if expected is None:
        return [Problem(target, "conflict: target was created during the run")] if path.exists() else []
    if not path.is_file():
        return [Problem(target, "conflict: target was removed during the run")]
    if sha256_file(path) != expected:
        return [Problem(target, "conflict: target changed during the run")]
    if now - path.stat().st_mtime < RECENT_SECONDS:
        return [Problem(target, "conflict: target modified in the last 60 s")]
    return []


def _walls(vault, target, note, schemas, resolver) -> list:
    if not target.startswith("wiki/") or (note.data or {}).get("type") == "index":
        return []
    src_part = schemamod.path_partition(target)
    body_links, _ = linkmod.extract(note.body, note.body_line)
    ntype = (note.data or {}).get("type")
    fm_links = Index(vault)._frontmatter_links(schemas.get(ntype) if isinstance(ntype, str) else None, note)
    out = []
    for link in body_links + fm_links:
        hit, _ = resolver.resolve(link.target, target, "md" if link.kind == "md" else "wiki", lambda c: (len(c), c))
        part = schemamod.path_partition(hit) if hit else None
        if src_part and part and wall_blocked(src_part, part):
            out.append(Problem(target, f"partition wall: {src_part} note links to {hit}"))
    return out


def _check(vault: Path, run_id, target, snap, decided, command, schemas, ctx, resolver, now) -> list:
    try:
        safe_rel(target)
    except PublishError as exc:
        return [Problem(target, str(exc))]
    if not target_matches(target, snap["targets"]):
        return [Problem(target, "not a publishable target")]
    try:
        new_text = (staging_dir(vault, run_id) / target).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Problem(target, f"unreadable staged file: {exc}")]
    new = frontmatter.parse(new_text)
    out = [Problem(target, f"schema: {i.message}") for i in schemamod.validate_note(schemas, target, new, ctx)[1]
           if i.severity == "error"]
    out += _walls(vault, target, new, schemas, resolver)
    decision = decided.get(target)
    if command == "ingest" and decision is None:
        out.append(Problem(target, "no decision recorded for this file"))
    existed = target in snap["files"]
    if existed and target not in snap["staged"]:
        out.append(Problem(target, "existing note was not staged with vault_index.py stage"))
    target_path = vault / target
    if existed and target_path.is_file():
        try:
            old = frontmatter.parse(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            old = None
        if old is not None:
            out += _protected(old, new, target)
            if decision not in SHRINK_EXEMPT:
                out += _shrink(old, new, target)
    else:
        for key in PROTECTED:
            if key in (new.data or {}):
                out.append(Problem(target, f"protected field {key} cannot be set by a headless run"))
    out += _conflict(vault, target, snap, now)
    return out


def validate_run(vault, run_id, now=None):
    vault, now = Path(vault), time.time() if now is None else now
    command = check_run_id(run_id)
    snap = load_snapshot(vault, run_id)
    staged, problems = staged_targets(vault, run_id)
    decisions, decision_problems = read_decisions(vault, run_id)
    problems += decision_problems
    if command == "ingest" and decisions is None:
        problems.append(Problem(DECISIONS, "ingest runs must write _decisions.jsonl"))
    for record in decisions or []:
        target = record.get("target")
        if record["decision"] != "noop" and target and target not in staged:
            if not target_matches(target, snap["targets"]):
                problems.append(Problem(target, "not a publishable target"))
    decided = {r["target"]: r["decision"] for r in decisions or [] if r["decision"] != "noop" and r.get("target")}
    schemas, ctx = schemamod.load_schemas(vault), schemamod.Context(vault)
    files = {rel for rel, _, _ in Index(vault).walk()} | set(staged)
    resolver = linkmod.Resolver(files, name_exclude=NAME_EXCLUDED)
    for target in staged:
        try:
            problems += _check(vault, run_id, target, snap, decided, command, schemas, ctx, resolver, now)
        except Exception as exc:  # model-written input must never crash validation
            problems.append(Problem(target, f"internal error: {exc!r}"))
    return staged, decisions or [], problems


def _set_provenance(text: str, values) -> str:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    lines = text.split("\n")
    new_line = "provenance: " + json.dumps(values, ensure_ascii=False)
    if not lines or lines[0] != "---":
        return f"---\n{new_line}\n---\n{text}"
    end = next((i for i in range(1, len(lines)) if lines[i] in ("---", "...")), None)
    if end is None:
        return text
    for i in range(1, end):
        if lines[i].startswith("provenance:"):
            j = i + 1
            while j < end and lines[j][:1] in (" ", "\t", "-"):
                j += 1
            lines[i:j] = [new_line]
            break
    else:
        lines.insert(end, new_line)
    return "\n".join(lines)


def _report(vault, run_id, status, problems=(), published=(), conflicts=()) -> dict:
    report = {"run_id": run_id, "status": status, "published": list(published), "conflicts": list(conflicts),
              "problems": [asdict(p) for p in problems]}
    _write_json(run_dir(vault, run_id) / "publish.json", report)
    return report


def _quarantine(vault: Path, run_id) -> None:
    src = staging_dir(vault, run_id)
    if not src.exists():
        return
    dst = vault / "system" / "quarantine" / run_id / "staged"
    if dst.exists():
        dst = dst.with_name(f"staged-{int(time.time())}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _read_journal(journal: Path) -> list:
    """Parse every journal line; raise ValueError on any torn or malformed entry."""
    try:
        entries = [json.loads(ln) for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ValueError(str(exc))
    for entry in entries:
        if entry == {"committed": True}:
            continue
        if (not isinstance(entry, dict) or not isinstance(entry.get("staged"), str)
                or not isinstance(entry.get("target"), str)
                or not (entry.get("expected") is None or isinstance(entry.get("expected"), str))):
            raise ValueError(f"malformed journal entry: {entry!r}")
    return entries


def _committed(journal: Path) -> bool:
    entries = _read_journal(journal)
    return bool(entries) and entries[-1] == {"committed": True}


def _hold_back(vault: Path, run_id, staged: Path, target: str) -> None:
    dst = vault / "system" / "quarantine" / run_id / "staged" / target
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged), str(dst))


def _apply(vault: Path, journal: Path):
    published, conflicts = [], []
    entries = _read_journal(journal)
    run_id = journal.parent.name
    for entry in entries:
        if "target" not in entry:
            continue
        staged, target = vault / entry["staged"], vault / entry["target"]
        if not staged.exists():
            held = vault / "system" / "quarantine" / run_id / "staged" / entry["target"]
            if held.exists():
                conflicts.append(entry["target"])  # held back before a crash
            else:
                published.append(entry["target"])  # renamed before a crash
            continue
        current = sha256_file(target) if target.is_file() else None
        if current != entry["expected"]:
            conflicts.append(entry["target"])
            _hold_back(vault, run_id, staged, entry["target"])
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        _rename(str(staged), str(target))
        published.append(entry["target"])
    with open(journal, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"committed": True}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return published, conflicts


def _refresh_index(vault) -> None:
    try:
        Index(vault).refresh(timeout=60)
    except TimeoutError:
        pass  # the next index read refreshes


def commit_run(vault, run_id, now=None) -> dict:
    vault = Path(vault)
    command = check_run_id(run_id)
    rd, sd = run_dir(vault, run_id), staging_dir(vault, run_id)
    staged, decisions, problems = validate_run(vault, run_id, now)
    decisions_file = sd / DECISIONS
    if decisions_file.is_file() and not decisions_file.is_symlink():
        shutil.copyfile(decisions_file, rd / DECISIONS)
    if problems:
        _quarantine(vault, run_id)
        return _report(vault, run_id, "rejected", problems=problems)
    if not staged:
        noop = command == "ingest" and decisions and all(d["decision"] == "noop" for d in decisions)
        shutil.rmtree(sd, ignore_errors=True)
        return _report(vault, run_id, "noop" if noop else "empty")
    snap = load_snapshot(vault, run_id)
    entries = []
    for target in staged:
        path = sd / target
        text = path.read_text(encoding="utf-8")
        data = frontmatter.parse(text).data or {}
        prov = [v for v in data.get("provenance", []) if isinstance(v, str)] \
            if isinstance(data.get("provenance"), list) else []
        if "headless" not in prov:
            prov.append("headless")
        path.write_text(_set_provenance(text, prov), encoding="utf-8")
        entries.append({"staged": path.relative_to(vault).as_posix(), "target": target,
                        "expected": _expected(snap, target)})
    journal = rd / "publish.journal"
    tmp_journal = rd / "publish.journal.tmp"
    with open(tmp_journal, "w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_journal, journal)
    dir_fd = os.open(rd, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    published, conflicts = _apply(vault, journal)
    shutil.rmtree(sd, ignore_errors=True)
    _refresh_index(vault)
    status = "conflict" if conflicts else "published"
    return _report(vault, run_id, status, published=published, conflicts=conflicts)


def abort_run(vault, run_id) -> dict:
    vault = Path(vault)
    check_run_id(run_id)
    _quarantine(vault, run_id)
    return _report(vault, run_id, "aborted")


def recover(vault) -> dict:
    """Roll forward interrupted publishes; quarantine aborted staging trees. Caller holds run.lock."""
    vault = Path(vault)
    recovered, aborted, failed = [], [], []
    runs = vault / "system" / "logs" / "runs"
    if runs.is_dir():
        for rd in sorted(runs.iterdir()):
            journal = rd / "publish.journal"
            if not (RUN_ID.match(rd.name) and journal.is_file()):
                continue
            try:
                if _committed(journal):
                    continue
                published, conflicts = _apply(vault, journal)
            except ValueError as exc:
                _quarantine(vault, rd.name)
                _report(vault, rd.name, "recovery_failed",
                        problems=[Problem("publish.journal", f"unreadable journal: {exc}")])
                failed.append(rd.name)
                continue
            shutil.rmtree(staging_dir(vault, rd.name), ignore_errors=True)
            _report(vault, rd.name, "conflict" if conflicts else "recovered",
                    published=published, conflicts=conflicts)
            recovered.append(rd.name)
    root = vault / "wiki" / ".staging"
    if root.is_dir():
        for sd in sorted(root.iterdir()):
            if not sd.is_dir() or not RUN_ID.match(sd.name):
                continue
            if (run_dir(vault, sd.name) / "publish.journal").is_file():
                shutil.rmtree(sd, ignore_errors=True)
                continue
            _quarantine(vault, sd.name)
            _report(vault, sd.name, "aborted")
            aborted.append(sd.name)
    if recovered:
        _refresh_index(vault)
    return {"recovered": recovered, "aborted": aborted, "failed": failed}
