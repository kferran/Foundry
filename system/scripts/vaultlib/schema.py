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
NOW_TAG = "now"   # a tag the Now page script writes (note tags spec §2); a schema reserves its own with reserved_tag
TAG_FORM = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*")


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
    min: int | None = None
    max: int | None = None


@dataclass
class Schema:
    name: str
    folders: list
    fields: dict
    source: str
    reserved_tag: bool = False   # its type's name is a tag written only on its notes (factory F2 §3.1)


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
    bounds = {}
    for key in ("min", "max"):
        if key in raw:
            if not isinstance(raw[key], str) or not INT.match(raw[key]):
                raise SchemaError(f"{where}: {key} must be an integer string")
            bounds[key] = int(raw[key])
    if bounds and kind != "int":
        raise SchemaError(f"{where}: min and max apply to int fields only")
    if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
        raise SchemaError(f"{where}: min is greater than max")
    spec = FieldSpec(
        kind=kind, required=_flag(raw, "required"), default=raw.get("default"),
        value=raw.get("value"), values=list(raw.get("values") or []),
        must_exist=raw.get("must_exist"), unique_true=_flag(raw, "unique_true"),
        matches_folder=_flag(raw, "matches_folder"), min=bounds.get("min"), max=bounds.get("max"),
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


def _read_schema(path: Path, vault: Path):
    """(rel, schema_for, folders, fields, reserved_tag) of one schema note. Raises SchemaError."""
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
    # An extension's config fragment names no folders: it adds fields to core's config schema.
    if folders is None and name == "config" and "/extensions/" in f"/{rel}":
        folders = []
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
    return rel, name, folders, fields, _flag(data, "reserved_tag")


def extension_schema_paths(vault: Path) -> list:
    """The schema notes of every present extensions/<name>/ folder, so a key an owner turned off still validates."""
    return sorted((Path(vault) / "extensions").glob("*/schemas/*.md"))


def load_schemas(vault: Path) -> dict:
    """Load every system/schemas/*.md, then each present extension's schemas. Raises SchemaError on an invalid
    schema note. An extension's `schema_for: config` note merges its fields into the core config schema."""
    vault = Path(vault)
    schemas = {}
    for path in sorted((vault / "system" / "schemas").glob("*.md")):
        rel, name, folders, fields, reserved = _read_schema(path, vault)
        if name in schemas:
            raise SchemaError(f"{rel}: duplicate schema {name!r}")
        schemas[name] = Schema(name, folders, fields, rel, reserved)
    for path in extension_schema_paths(vault):
        rel, name, folders, fields, reserved = _read_schema(path, vault)
        if name == "config" and "config" in schemas:
            for key, spec in fields.items():
                if key in schemas["config"].fields:
                    raise SchemaError(f"{rel}: config field {key!r} is already defined")
                schemas["config"].fields[key] = spec
            continue
        if name in schemas:
            raise SchemaError(f"{rel}: duplicate schema {name!r}")
        schemas[name] = Schema(name, folders, fields, rel, reserved)
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
        if not INT.match(value):
            return err("expected an integer")
        if spec.min is not None and int(value) < spec.min:
            return err(f"must be at least {spec.min}")
        if spec.max is not None and int(value) > spec.max:
            return err(f"must be at most {spec.max}")
        return []
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


def reserved_tags(schemas: dict) -> dict:
    """{tag: the notes it is written on}: the Now page's tag, and each schema's type name that sets reserved_tag."""
    return {NOW_TAG: "the Now page", **{n: f"{n} notes" for n, s in schemas.items() if s.reserved_tag}}


def tag_issues(rel: str, ntype, note, values, schemas: dict) -> list:
    """Warnings on frontmatter tags: one form (lowercase kebab-case, / between nested parts, not digits only) and the
    system tags kept to the notes their scripts write (note tags spec §2)."""
    line, out, reserved = frontmatter.key_line(note, "tags"), [], reserved_tags(schemas)
    for tag in map(str, values):
        if not TAG_FORM.fullmatch(tag):
            out.append(Issue(rel, line, "warning", "tag-form",
                             f'tag "{tag}" is not lowercase kebab-case (a-z, 0-9 and -, / between nested parts)'))
        elif tag.replace("/", "").isdigit():
            out.append(Issue(rel, line, "warning", "tag-form", f'tag "{tag}" is only digits, which Obsidian ignores'))
        elif tag in reserved and (not re.fullmatch(r"wiki/[^/]+/Now\.md", rel) if tag == NOW_TAG else ntype != tag):
            out.append(Issue(rel, line, "warning", "tag-reserved",
                             f'tag "{tag}" is a system tag, written only on {reserved[tag]}'))
    return out


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
        if spec.kind == "path" and rel.endswith("/example.md"):
            continue  # a shipped example (system/codebases/example.md) names a path no vault has (#19)
        for severity, message in check_value(spec, value, ctx, name):
            issues.append(Issue(rel, line, severity, "field", message))
        if spec.matches_folder and isinstance(value, str) and value != path_partition(rel):
            issues.append(Issue(rel, line, "error", "partition-folder",
                                f"{name} {value!r} does not match folder partition {path_partition(rel)!r}"))
    for name in note.data:
        if name not in sch.fields:
            issues.append(Issue(rel, frontmatter.key_line(note, str(name)), "warning", "unknown-field", f"unknown field {name}"))
    return ntype, issues
