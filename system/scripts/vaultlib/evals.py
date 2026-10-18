"""Ingest evals (ingest evals spec §3.3): deterministic checks over one intake tick's runs. No model is called.

A check reads the run directories the tick added (system/logs/runs/<run_id>/: publish.json, _decisions.jsonl,
claude.json), a rejected run's held files (system/quarantine/<run_id>/staged/) and the published vault. A path in
`creates`, `patches`, `body_contains`, `body_lacks` and a target in `decisions` may be a glob (fnmatch): the check
then holds when some published path matching it does.
"""
import json
from fnmatch import fnmatch
from pathlib import Path

from . import frontmatter, links as linkmod, publish, schema as schemamod
from .index import NAME_EXCLUDED, Index

KEYS = ("min_pass_rate", "publish", "decisions", "creates", "patches", "untouched", "walls", "absent",
        "body_contains", "body_lacks", "archived")


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _runs(vault: Path, run_ids: list) -> list:
    return [publish.run_dir(vault, r) for r in run_ids]


def published(vault: Path, run_ids: list) -> list:
    return [p for rd in _runs(vault, run_ids) for p in _json(rd / "publish.json", {}).get("published", [])]


def cost(vault: Path, run_ids: list) -> float:
    total = 0.0
    for rd in _runs(vault, run_ids):
        result = _json(rd / "claude.json", {})
        value = result.get("total_cost_usd") if isinstance(result, dict) else 0
        total += value if isinstance(value, (int, float)) else 0
    return round(total, 4)


def _matching(paths: list, pattern: str) -> list:
    return [p for p in paths if p == pattern or fnmatch(p, pattern)]


def _body(vault: Path, rel: str) -> str:
    try:
        return frontmatter.parse((vault / rel).read_text(encoding="utf-8")).body
    except (OSError, UnicodeDecodeError):
        return ""


def _publish(vault, run_ids, want, _overlay) -> list:
    allowed = want if isinstance(want, list) else [want]
    out = []
    for rd in _runs(vault, run_ids):
        status = _json(rd / "publish.json", {}).get("status", "missing")
        if status not in allowed:
            out.append(f"publish: {rd.name} is {status}, want {' or '.join(allowed)}")
    return out


def _decisions(vault, run_ids, want, _overlay) -> list:
    actual = []
    for rd in _runs(vault, run_ids):
        try:
            lines = (rd / publish.DECISIONS).read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                actual.append((str(d.get("decision")), str(d.get("target"))))
    left, out = list(actual), []
    for decision, target in want:
        hit = next((a for a in left if a[0] == decision and fnmatch(a[1], target)), None)
        if hit is None:
            out.append(f"decisions: no {decision} on {target}")
        else:
            left.remove(hit)
    out += [f"decisions: unexpected {d} on {t}" for d, t in left]
    return out


def _creates(vault, run_ids, want, _overlay) -> list:
    out, pub = [], published(vault, run_ids)
    for pattern, values in want.items():
        hits = _matching(pub, pattern)
        good = []
        for rel in hits:
            try:
                data = frontmatter.parse((vault / rel).read_text(encoding="utf-8")).data or {}
            except (OSError, UnicodeDecodeError):
                continue
            tags = data.get("tags") if isinstance(data.get("tags"), list) else []
            if all((k == "tags" and all(t in tags for t in (v if isinstance(v, list) else [v])))
                   or (k != "tags" and str(data.get(k)) == str(v)) for k, v in (values or {}).items()):
                good.append(rel)
        if not good:
            out.append(f"creates: no published {pattern}" + (f" with {values}" if hits else ""))
    return out


def _patches(vault, run_ids, want, _overlay) -> list:
    out, pub = [], published(vault, run_ids)
    for pattern, spec in want.items():
        hits = _matching(pub, pattern)
        if not hits:
            out.append(f"patches: {pattern} was not published")
            continue
        for key in ("contains", "still_contains"):
            for text in (spec or {}).get(key, []):
                if not any(text in (vault / h).read_text(encoding="utf-8", errors="replace") for h in hits):
                    out.append(f"patches: {pattern} lacks {text!r} ({key})")
    return out


def _untouched(vault, _run_ids, want, overlay) -> list:
    out = []
    for rel in want:
        source = (Path(overlay) / rel) if overlay and (Path(overlay) / rel).is_file() else None
        before = source.read_bytes() if source else None
        try:
            after = (vault / rel).read_bytes()
        except OSError:
            after = None
        if before is not None and after != before:
            out.append(f"untouched: {rel} changed")
        if before is None and after is None:
            out.append(f"untouched: {rel} is in neither the overlay nor the vault")
    return out


def _walls(vault, run_ids, want, _overlay) -> list:
    if not want:
        return []
    schemas = schemamod.load_schemas(vault)
    resolver = linkmod.Resolver({rel for rel, _, _ in Index(vault).walk()}, name_exclude=NAME_EXCLUDED)
    out = []
    for rel in published(vault, run_ids):
        try:
            note = frontmatter.parse((vault / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        out += [f"walls: {rel}: {p.reason}" for p in publish._walls(vault, rel, note, schemas, resolver)]
    return out


def _absent(vault, run_ids, want, _overlay) -> list:
    pub, out = published(vault, run_ids), []
    for rel in want:
        held = any((vault / "system" / "quarantine" / r / "staged" / rel).exists() for r in run_ids)
        if rel in pub or held:
            out.append(f"absent: {rel} was {'published' if rel in pub else 'staged'}")
    return out


def _body_check(vault, run_ids, want, contains: bool) -> list:
    out, pub, key = [], published(vault, run_ids), "body_contains" if contains else "body_lacks"
    for pattern, texts in want.items():
        hits = _matching(pub, pattern)
        for text in texts:
            found = [h for h in hits if text in _body(vault, h)]
            if contains and not found:
                out.append(f"{key}: no published {pattern} holds {text!r}")
            if not contains and found:
                out.append(f"{key}: {found[0]} holds {text!r}")
    return out


def _archived(vault, _run_ids, want, _overlay) -> list:
    archive = vault / "raw" / "archive"
    return [f"archived: {name} is not in raw/archive/" for name in want
            if not (archive / name).exists() and not list(archive.glob(f"{Path(name).stem}*"))]


CHECKS = {"publish": _publish, "decisions": _decisions, "creates": _creates, "patches": _patches,
          "untouched": _untouched, "walls": _walls, "absent": _absent, "archived": _archived,
          "body_contains": lambda v, r, w, o: _body_check(v, r, w, True),
          "body_lacks": lambda v, r, w, o: _body_check(v, r, w, False)}


def check(vault, run_ids: list, expect: dict, overlay=None) -> list:
    """The failed-check lines for one tick's runs; empty when every check holds."""
    vault = Path(vault)
    unknown = sorted(set(expect) - set(KEYS))
    if unknown:
        return [f"expect: unknown keys {', '.join(unknown)}"]
    if not run_ids:
        return ["runs: the tick ran no ingest"]
    return [line for key, fn in CHECKS.items() if key in expect for line in fn(vault, run_ids, expect[key], overlay)]


def summary(records: list) -> tuple:
    """(lines, ok): one line per case in first-seen order; ok is False when a case is under its rate or skipped."""
    cases, ok = {}, True
    for r in records:
        cases.setdefault(r["case"], []).append(r)
    lines = []
    for name, runs in cases.items():
        made = [r for r in runs if not r.get("skipped")]
        rate = float(runs[0].get("min_pass_rate", 1.0))
        if not made:
            lines.append(f"{name}: skipped (budget)")
            ok = False
            continue
        passes = sum(not r.get("failed") for r in made)
        good = round(passes / len(made), 2) >= rate   # 2 of 3 meets 0.67
        ok = ok and good and len(made) == len(runs)
        mean = sum(r.get("cost", 0) for r in made) / len(made)
        skipped = f", {len(runs) - len(made)} skipped (budget)" if len(made) < len(runs) else ""
        lines.append(f"{name}: {passes}/{len(made)} (min {rate:g}) {'PASS' if good else 'FAIL'}, ${mean:.2f} a run{skipped}")
    return lines, ok
