"""Caller scope from the working directory (spec §6.16, §6.17)."""
import os
import subprocess
from pathlib import Path

from . import frontmatter


def git_common_dir(path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return str(Path(out.stdout.strip()).resolve())


def codebases(vault) -> list:
    found = []
    for path in sorted((Path(vault) / "system" / "codebases").glob("*.md")):
        if path.name == "example.md":
            continue
        data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
        if data.get("type") != "codebase" or not isinstance(data.get("path"), str):
            continue
        found.append({"name": data.get("name") or path.stem,
                      "path": os.path.expanduser(data["path"]),
                      "partition": data.get("partition") or "work"})
    return found


def caller_scope(vault, cwd):
    vault, cwd = Path(vault).resolve(), Path(cwd).resolve()
    if cwd == vault or vault in cwd.parents:
        return ("vault", None, None)
    common = git_common_dir(cwd)
    if common:
        for cb in codebases(vault):
            if git_common_dir(cb["path"]) == common:
                return ("codebase", cb["name"], cb["partition"])
    return None


def allowed_partitions(scope_tuple):
    """None means unrestricted (vault scope)."""
    if scope_tuple and scope_tuple[0] == "codebase":
        return [scope_tuple[2], "shared"]
    return None
