"""Caller scope from the working directory (spec §6.16, §6.17)."""
import os
import subprocess
from pathlib import Path

from . import frontmatter


def git_common_dir(path) -> str | None:
    try:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             capture_output=True, text=True, timeout=5, env=env)
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
        try:
            data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
        except (OSError, UnicodeDecodeError):
            continue
        if data.get("type") != "codebase" or not isinstance(data.get("path"), str):
            continue
        expanded_path = os.path.expanduser(data["path"])
        # Skip relative paths
        if not Path(expanded_path).is_absolute():
            continue
        # Validate partition
        partition = data.get("partition")
        if partition is None:
            partition = "work"
        elif not isinstance(partition, str) or partition not in ("work", "personal", "shared"):
            continue
        # Validate name
        name = data.get("name")
        if not isinstance(name, str):
            name = path.stem
        found.append({"name": name, "path": expanded_path, "partition": partition})
    return found


def caller_scope(vault, cwd):
    vault, cwd = Path(vault).resolve(), Path(cwd).resolve()
    if cwd == vault or vault in cwd.parents:
        return ("vault", None, None)
    common = git_common_dir(cwd)
    if common:
        matches = []
        for cb in codebases(vault):
            if git_common_dir(cb["path"]) == common:
                matches.append((cb["name"], cb["partition"]))
        if len(matches) == 1:
            return ("codebase", matches[0][0], matches[0][1])
        elif len(matches) > 1:
            # Ambiguous: multiple registrations for the same repo
            return None
    return None


def allowed_partitions(scope_tuple):
    """None means unrestricted (vault scope)."""
    if scope_tuple and scope_tuple[0] == "codebase":
        return [scope_tuple[2], "shared"]
    return None
