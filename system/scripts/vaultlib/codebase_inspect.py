"""Codebase evidence for /setup (spec §6.13): manifests, layer candidates, extensions, logging hints, git."""
from __future__ import annotations

import json
import re
import subprocess
import tomllib
from collections import Counter
from pathlib import Path, PurePosixPath

NOTABLE_JS = ("vue", "react", "next", "angular", "svelte")
LOGGING_HINTS = {  # name -> (git grep flag, pattern)
    "EventId": ("-F", "EventId"),
    "LoggerMessage": ("-F", "LoggerMessage"),
    "ILogger": ("-F", "ILogger"),
    "logger.": ("-E", r"(^|[^A-Za-z0-9_])logger\."),
    "log.": ("-E", r"(^|[^A-Za-z0-9_])log\."),
}
MAX_MANIFEST_BYTES = 1_000_000


class NotARepo(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    """git's stdout, or "" when git fails. Paths are printed unquoted, so non-ASCII names stay readable."""
    r = subprocess.run(["git", "-c", "core.quotePath=false", "-C", str(repo), *args], capture_output=True)
    if r.returncode != 0:
        return ""
    return r.stdout.decode("utf-8", errors="replace")


def manifest_kind(name: str) -> str | None:
    if name == "package.json":
        return "npm"
    if name.endswith(".csproj"):
        return "dotnet"
    if name.endswith(".sln"):
        return "dotnet-solution"
    return {"go.mod": "go", "pyproject.toml": "python", "Cargo.toml": "rust",
            "pom.xml": "maven", "Gemfile": "ruby"}.get(name)


def _xml_tag(text: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>\s*([^<]*?)\s*</{tag}>", text)
    return m.group(1) if m else None


def manifest_details(kind: str, text: str) -> dict:
    """Never raises: an unparseable manifest reports {"error": ...}."""
    try:
        if kind == "npm":
            data = json.loads(text)
            if not isinstance(data, dict):
                return {"error": "not a JSON object"}
            deps: set[str] = set()
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                if isinstance(data.get(key), dict):
                    deps.update(data[key])
            notable = sorted({"angular" if d.startswith("@angular/") else d
                              for d in deps if d in NOTABLE_JS or d.startswith("@angular/")})
            name = data.get("name")
            return {"name": name if isinstance(name, str) else None, "notable": notable}
        if kind == "dotnet":
            tf = _xml_tag(text, "TargetFramework") or _xml_tag(text, "TargetFrameworks")
            return {"TargetFramework": tf, "RootNamespace": _xml_tag(text, "RootNamespace")}
        if kind == "go":
            m = re.search(r"^module\s+(\S+)", text, re.M)
            return {"module": m.group(1) if m else None}
        if kind in ("python", "rust"):
            data = tomllib.loads(text)
            section = "project" if kind == "python" else "package"
            name = (data.get(section) or {}).get("name")
            if kind == "python" and not name:
                name = ((data.get("tool") or {}).get("poetry") or {}).get("name")
            return {"name": name if isinstance(name, str) else None}
        if kind == "maven":
            own = re.sub(r"<parent>.*?</parent>", "", text, flags=re.S)  # the parent's artifactId is not ours
            m = re.search(r"<artifactId>\s*([^<]*?)\s*</artifactId>", own)
            return {"artifactId": m.group(1) if m else None}
    except (ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError) as exc:
        return {"error": f"unparseable: {type(exc).__name__}"}
    return {}


def logging_hints(repo: Path) -> dict:
    out = {}
    for name, (flag, pattern) in LOGGING_HINTS.items():
        per_file = []
        for line in _git(repo, "grep", "-I", "-c", flag, "-e", pattern, "--").splitlines():
            path, _, count = line.rpartition(":")
            if path and count.isdigit():
                per_file.append((int(count), path))
        per_file.sort(key=lambda t: (-t[0], t[1]))
        out[name] = {"count": sum(c for c, _ in per_file), "examples": [p for _, p in per_file[:10]]}
    return out


def inspect_repo(path: Path, per_kind: int | None = None) -> dict:
    """per_kind: keep at most that many manifests of each kind, the shallowest first; manifest_counts and
    notable still cover every manifest (a large monorepo lists hundreds of .csproj files, #18)."""
    top = _git(path, "rev-parse", "--show-toplevel").strip()
    if not top:
        raise NotARepo(str(path))
    repo = Path(top)
    files = [f for f in _git(repo, "ls-files", "-z").split("\0") if f]
    manifests, layers = [], set()
    exts: Counter[str] = Counter()
    for f in files:
        p = PurePosixPath(f)
        exts[p.suffix[1:].lower() if p.suffix else "(none)"] += 1
        kind = manifest_kind(p.name)
        if kind is None:
            continue
        full = repo / f
        try:
            if full.stat().st_size > MAX_MANIFEST_BYTES:
                details = {"error": "too large"}
            else:
                details = manifest_details(kind, full.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            details = {"error": f"unreadable: {exc.strerror or type(exc).__name__}"}
        d = str(p.parent)
        manifests.append({"file": f, "dir": d, "kind": kind, "details": details})
        if len(p.parts) == 2:
            layers.add(p.parts[0] + "/")
    counts = Counter(m["kind"] for m in manifests)
    notable = sorted({n for m in manifests for n in m["details"].get("notable", [])})
    if per_kind is not None:
        keep = set()
        for kind in counts:
            same = sorted((m for m in manifests if m["kind"] == kind), key=lambda m: (m["file"].count("/"), m["file"]))
            keep.update(m["file"] for m in same[:per_kind])
        manifests = [m for m in manifests if m["file"] in keep]
    branch = _git(repo, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD").strip().removeprefix("origin/")
    if not branch:
        branch = _git(repo, "branch", "--show-current").strip()
    remote = _git(repo, "remote", "get-url", "origin").strip()
    return {
        "path": str(repo),
        "manifests": manifests,
        "manifest_counts": dict(sorted(counts.items())),
        "notable": notable,
        "layer_candidates": sorted(layers),
        "extensions": dict(sorted(exts.items())),
        "logging_hints": logging_hints(repo),
        "git": {"default_branch": branch or None, "remote": remote or None},
    }
