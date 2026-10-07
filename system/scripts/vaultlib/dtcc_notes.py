"""dtcc_change notes (DTCC watcher spec §4): path, render, schema-checked create-once."""
import json
import re
from pathlib import Path

from . import frontmatter, schema

FIELDS = ("type", "partition", "detected_at", "kind", "key", "product", "title", "source_url", "codebase", "paths",
          "owner", "pinned", "published", "deadlines", "impact", "capability")


def rel_path(partition: str, key: str) -> str:
    slug = re.sub(r"[^a-z0-9._]+", "-", key.lower()).strip("-")
    return f"wiki/{partition}/changes/dtcc-{slug}.md"


def clean(text) -> str:
    """External text as one inert Markdown line: no links, HTML, code or emphasis syntax."""
    return re.sub(r"\s+", " ", re.sub(r"[\[\]<>`|*_#{}]", " ", str(text or ""))).strip()[:200]


def render(fm: dict, evidence: list, paths: list, related: list) -> str:
    lines = ["---"]
    for k in FIELDS:
        v = fm.get(k)
        if v in (None, "") or (k not in ("paths", "deadlines") and v == []):
            continue
        lines.append(f"{k}: {json.dumps(v if isinstance(v, list) else str(v), ensure_ascii=False)}")
    lines += ["---", f"# {clean(fm['title'])}", "", "## Evidence"]
    lines += [f"- {clean(e)}" for e in evidence] or ["- (none)"]
    lines += ["", "## Mapped paths"] + ([f"- `{p}`" for p in paths] or ["- (none)"])
    lines += ["", "## Related"] + ([f"- {r}" for r in related] or ["- (none)"])
    lines += ["", "## Impact", ""]
    return "\n".join(lines)


def create(vault: Path, rel: str, text: str, schemas: dict) -> bool:
    path = Path(vault) / rel
    if path.exists():
        return False
    _, issues = schema.validate_note(schemas, rel, frontmatter.parse(text), schema.Context(Path(vault)))
    errors = [i.message for i in issues if i.severity == "error"]
    if errors:
        raise ValueError(f"{rel}: {'; '.join(errors)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return True
