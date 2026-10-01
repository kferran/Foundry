"""Load schema notes and validate note frontmatter against them (spec §6.15)."""
import datetime
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter

PARTITIONS = ("work", "personal", "shared")
KINDS = {"const", "string", "text", "int", "bool", "date", "datetime", "time", "timezone",
         "enum", "list", "map", "link", "path", "fieldspecs"}
IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
INT = re.compile(r"^-?\d+$")
TZ = re.compile(r"^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+)*$")
WIKILINK = re.compile(r"\s*\[\[([^\[\]]+)\]\]\s*")


@dataclass
class Issue:
    path: str
    line: int
    severity: str
    code: str
    message: str


@dataclass
class FieldSpec:
    kind: str
    required: bool = False
    default: str | None = None
    value: str | None = None
    values: list = field(default_factory=list)
    of: "FieldSpec | None" = None
    fields: dict = field(default_factory=dict)
    must_exist: str | None = None
    unique_true: bool = False
    matches_folder: bool = False


@dataclass
class Schema:
    name: str
    folders: list
    fields: dict
    source: str


class SchemaError(Exception):
    pass


@dataclass
class Context:
    vault: Path
    zoneinfo: Path = Path("/usr/share/zoneinfo")


def _flag(raw: dict, key: str) -> bool:
    return str(raw.get(key, "false")).lower() == "true"


def parse_fieldspec(raw, where: str) -> FieldSpec:
    if isinstance(raw, str):
        raw = {"kind": raw}
    if not isinstance(raw, dict) or "kind" not in raw:
        raise SchemaError(f"{where}: field spec needs a kind")
    kind = raw["kind"]
    if not isinstance(kind, str):
        raise SchemaError(f"{where}: kind must be a string")
    if kind not in KINDS:
        raise SchemaError(f"{where}: unknown kind {kind!r}")
    if "values" in raw and not isinstance(raw["values"], list):
        raise SchemaError(f"{where}: values must be a list")
    if "must_exist" in raw and raw["must_exist"] not in ("warn", "error"):
        raise SchemaError(f"{where}: must_exist must be 'warn' or 'error'")
    if "default" in raw and not isinstance(raw["default"], str):
        raise SchemaError(f"{where}: default must be a string")
    if kind == "const" and "value" in raw and not isinstance(raw["value"], str):
        raise SchemaError(f"{where}: const value must be a string")
    spec = FieldSpec(
        kind=kind, required=_flag(raw, "required"), default=raw.get("default"),
        value=raw.get("value"), values=list(raw.get("values") or []),
        must_exist=raw.get("must_exist"), unique_true=_flag(raw, "unique_true"),
        matches_folder=_flag(raw, "matches_folder"),
    )
    if kind == "list":
        spec.of = parse_fieldspec(raw.get("of", "string"), f"{where}.of")
    if kind == "map":
        if "fields" in raw:
            if not isinstance(raw["fields"], dict):
                raise SchemaError(f"{where}: map fields must be a mapping")
            spec.fields = {k: parse_fieldspec(v, f"{where}.{k}") for k, v in raw["fields"].items()}
        else:
            spec.of = parse_fieldspec(raw.get("of", "string"), f"{where}.of")
    if kind == "enum" and not spec.values:
        raise SchemaError(f"{where}: enum needs values")
    if kind == "const" and spec.value is None:
        raise SchemaError(f"{where}: const needs a value")
    return spec


def load_schemas(vault: Path) -> dict:
    """Load every system/schemas/*.md. Raises SchemaError on an invalid schema note."""
    schemas = {}
    for path in sorted((Path(vault) / "system" / "schemas").glob("*.md")):
        rel = path.relative_to(vault).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            raise SchemaError(f"{rel}: cannot read: {exc}")
        note = frontmatter.parse(text)
        if note.data is None:
            raise SchemaError(f"{rel}: {note.error or 'no frontmatter'}")
        data = note.data
        name = data.get("schema_for")
        if not isinstance(name, str) or not IDENT.match(name):
            raise SchemaError(f"{rel}: schema_for must be an identifier")
        folders = data.get("folders")
        if not isinstance(folders, list) or not all(isinstance(f, str) for f in folders):
            raise SchemaError(f"{rel}: folders must be a list of strings")
        raw_fields = data.get("fields")
        if not isinstance(raw_fields, dict):
            raise SchemaError(f"{rel}: fields must be a mapping")
        fields = {}
        for key, raw in raw_fields.items():
            if not IDENT.match(str(key)):
                raise SchemaError(f"{rel}: field name {key!r} is not an identifier")
            fields[key] = parse_fieldspec(raw, f"{rel}:{key}")
        if name in schemas:
            raise SchemaError(f"{rel}: duplicate schema {name!r}")
        schemas[name] = Schema(name, folders, fields, rel)
    return schemas


def covers(folder: str, path: str) -> bool:
    return path == folder or (folder.endswith("/") and path.startswith(folder))


def schemas_covering(schemas: dict, path: str) -> list:
    return [s for s in schemas.values() if any(covers(f, path) for f in s.folders)]


def path_partition(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) > 2 and parts[0] in ("wiki", "raw") and parts[1] in PARTITIONS:
        return parts[1]
    return None


def link_target(value) -> str | None:
    """Normalize a link value: '[[T]]' or the nested list [['T']] -> 'T'."""
    if isinstance(value, str):
        match = WIKILINK.fullmatch(value)
        return match.group(1) if match else None
    if (isinstance(value, list) and len(value) == 1 and isinstance(value[0], list)
            and len(value[0]) == 1 and isinstance(value[0][0], str)):
        return value[0][0]
    return None


def check_value(spec: FieldSpec, value, ctx: Context, where: str) -> list:
    """Return [(severity, message)] for one value."""
    kind = spec.kind

    def err(msg):
        return [("error", f"{where}: {msg}")]

    if kind == "list":
        if not isinstance(value, list):
            return err("expected a list")
        out = []
        for i, item in enumerate(value):
            out += check_value(spec.of, item, ctx, f"{where}[{i}]")
        return out
    if kind == "map":
        if not isinstance(value, dict):
            return err("expected a mapping")
        out = []
        for key, item in value.items():
            if spec.fields:
                if key not in spec.fields:
                    out.append(("warning", f"{where}.{key}: unknown key"))
                    continue
                out += check_value(spec.fields[key], item, ctx, f"{where}.{key}")
            else:
                out += check_value(spec.of, item, ctx, f"{where}.{key}")
        for key, sub in spec.fields.items():
            if sub.required and key not in value:
                out += err(f"missing required key {key}")
        return out
    if kind == "fieldspecs":
        if not isinstance(value, dict):
            return err("expected a mapping of field specs")
        out = []
        for key, raw in value.items():
            try:
                parse_fieldspec(raw, f"{where}.{key}")
            except SchemaError as exc:
                out.append(("error", str(exc)))
        return out
    if kind == "link":
        return [] if link_target(value) is not None else err('expected a wikilink like "[[Note]]"')
    if not isinstance(value, str):
        return err(f"expected a {kind} scalar")
    if kind == "const":
        return [] if value == spec.value else err(f"must be {spec.value!r}")
    if kind in ("string", "text"):
        return []
    if kind == "int":
        return [] if INT.match(value) else err("expected an integer")
    if kind == "bool":
        return [] if value.lower() in ("true", "false") else err("expected true or false")
    if kind == "date":
        if DATE.match(value):
            try:
                datetime.date.fromisoformat(value)
                return []
            except ValueError:
                pass
        return err("expected a date YYYY-MM-DD")
    if kind == "datetime":
        try:
            datetime.datetime.fromisoformat(value)
            return []
        except ValueError:
            return err("expected an ISO 8601 datetime")
    if kind == "time":
        return [] if TIME.match(value) else err("expected HH:MM")
    if kind == "timezone":
        ok = bool(TZ.match(value)) and ".." not in value and (ctx.zoneinfo / value).is_file()
        return [] if ok else err(f"unknown timezone {value!r}")
    if kind == "enum":
        allowed = [str(v) for v in spec.values]
        return [] if value in allowed else err(f"must be one of {', '.join(allowed)}")
    if kind == "path":
        if spec.must_exist in ("warn", "error") and not Path(os.path.expanduser(value)).exists():
            severity = "error" if spec.must_exist == "error" else "warning"
            return [(severity, f"{where}: path does not exist: {value}")]
        return []
    return err(f"unsupported kind {kind}")


def validate_note(schemas: dict, rel: str, note, ctx: Context) -> tuple:
    """Validate one parsed note. Returns (type or None, issues). Uncovered paths return (None, [])."""
    covering = schemas_covering(schemas, rel)
    if not covering:
        return None, []
    if note.data is None:
        return None, [Issue(rel, note.error_line or 1, "error", "frontmatter", note.error or "missing frontmatter")]
    ntype = note.data.get("type")
    type_line = frontmatter.key_line(note, "type")
    if not isinstance(ntype, str) or not ntype:
        return None, [Issue(rel, type_line, "error", "missing-type", "frontmatter has no type")]
    sch = schemas.get(ntype)
    if sch is None:
        return None, [Issue(rel, type_line, "error", "unknown-type", f"no schema for type {ntype!r}")]
    if sch not in covering:
        return ntype, [Issue(rel, type_line, "error", "type-folder-mismatch", f"type {ntype!r} is not allowed in this folder")]
    issues = []
    for name, spec in sch.fields.items():
        line = frontmatter.key_line(note, name)
        value = note.data.get(name)
        if name not in note.data or value == "":
            if spec.required:
                issues.append(Issue(rel, line, "error", "required", f"missing required field {name}"))
            continue
        for severity, message in check_value(spec, value, ctx, name):
            issues.append(Issue(rel, line, severity, "field", message))
        if spec.matches_folder and isinstance(value, str) and value != path_partition(rel):
            issues.append(Issue(rel, line, "error", "partition-folder",
                                f"{name} {value!r} does not match folder partition {path_partition(rel)!r}"))
    for name in note.data:
        if name not in sch.fields:
            issues.append(Issue(rel, frontmatter.key_line(note, str(name)), "warning", "unknown-field", f"unknown field {name}"))
    return ntype, issues
