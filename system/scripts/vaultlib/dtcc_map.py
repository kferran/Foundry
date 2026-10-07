"""The DTCC watcher map, system/dtcc/map.yaml (DTCC watcher spec §5)."""
import re
import subprocess
from pathlib import Path

import yaml

from . import frontmatter, schema, yamlload

MAP = "system/dtcc/map.yaml"
PIN = re.compile(r"^v\d\d-\d+$")
PARTITIONS = ("work", "personal", "shared")


def load(vault: Path) -> tuple:
    path = Path(vault) / MAP
    if not path.is_file():
        return None, None
    try:
        data = yamlload.load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        return None, f"{MAP}: {exc}".splitlines()[0]
    if not isinstance(data, dict):
        return None, f"{MAP}: not a mapping"
    return data, None


def checkout(vault: Path, codebase: str) -> Path | None:
    path = Path(vault) / "system" / "codebases" / f"{codebase}.md"
    if not path.is_file():
        return None
    data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
    return Path(str(data["path"])).expanduser() if data.get("path") else None


def ref(m: dict, codebase: str) -> str:
    return str(((m.get("codebases") or {}).get(codebase) or {}).get("ref") or "origin/HEAD")


def _git_ok(repo: Path, *args) -> bool:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True).returncode == 0


def _resolves(vault: Path, partition: str, link) -> bool:
    target = schema.link_target(link)
    return bool(target) and any((Path(vault) / "wiki" / partition).rglob(f"{target}.md"))


def validate(m: dict, vault: Path) -> list:
    errs = []
    part = m.get("partition")
    if part not in PARTITIONS:
        errs.append("partition must be work, personal or shared")
    kws = m.get("notice_keywords")
    if not isinstance(kws, list) or not kws:
        errs.append("notice_keywords must be a non-empty list")
    for k in kws if isinstance(kws, list) else []:
        try:
            re.compile(k)
        except re.error as exc:
            errs.append(f"notice_keywords {k!r}: {exc}")
    codebases = m.get("codebases") or {}
    if not isinstance(codebases, dict):
        errs.append("codebases must be a mapping")
        codebases = {}
    for name in codebases:
        repo = checkout(vault, name)
        if repo is None:
            errs.append(f"codebase {name}: not registered in system/codebases/")
        elif not _git_ok(repo, "rev-parse", "--verify", "--quiet", f"{ref(m, name)}^{{commit}}"):
            errs.append(f"codebase {name}: ref {ref(m, name)} does not resolve in {repo}")
    products = m.get("products")
    if not isinstance(products, dict) or not products:
        errs.append("products must be a non-empty mapping")
        products = {}
    links = [m["hub"]] if m.get("hub") else []
    for key, p in products.items():
        p = p or {}
        if not (p.get("page") or p.get("notice_codes") or p.get("api_assets")):
            errs.append(f"product {key}: needs page, notice_codes or api_assets")
        if p.get("codebase") and p["codebase"] not in codebases:
            errs.append(f"product {key}: codebase {p['codebase']} is not listed under codebases")
        if p.get("pin") and not PIN.match(str(p["pin"])):
            errs.append(f"product {key}: pin {p['pin']!r} must look like v25-5")
        for f in ("notice_codes", "paths", "notes", "api_assets"):
            if not isinstance(p.get(f, []), list):
                errs.append(f"product {key}: {f} must be a list")
        links += p.get("notes") or [] if isinstance(p.get("notes", []), list) else []
    if not isinstance(m.get("ignore", []), list):
        errs.append("ignore must be a list")
    if part in PARTITIONS:
        errs += [f"{link} does not resolve in wiki/{part}/" for link in links if not _resolves(vault, part, link)]
    return errs


def stale_paths(m: dict, vault: Path) -> list:
    out = []
    for key, p in (m.get("products") or {}).items():
        p = p or {}
        repo = checkout(vault, p["codebase"]) if p.get("codebase") else None
        if repo is None:
            continue
        r = ref(m, p["codebase"])
        out += [(key, path, r) for path in p.get("paths") or []
                if not _git_ok(repo, "cat-file", "-e", f"{r}:{path.rstrip('/')}")]
    return out
