import pytest

from helpers import write
from vaultlib import frontmatter, schema

TEST_SCHEMA = """---
type: schema
schema_for: thing
folders: ["things/", "single.md"]
fields:
  type: {kind: const, value: thing, required: true}
  name: {kind: string, required: true}
  count: {kind: int}
  minutes: {kind: int, min: "1", max: "60"}
  flag: {kind: bool, default: "false"}
  day: {kind: date}
  at: {kind: datetime}
  hhmm: {kind: time}
  tz: {kind: timezone}
  color: {kind: enum, values: [red, blue]}
  items: {kind: list, of: string}
  layers: {kind: map, of: string}
  ref: {kind: link}
  where: {kind: path, must_exist: warn}
  partition: {kind: enum, values: [work, personal, shared], matches_folder: true}
---
# Thing
"""


@pytest.fixture
def schemas(tmp_path):
    write(tmp_path, "system/schemas/thing.md", TEST_SCHEMA)
    return schema.load_schemas(tmp_path), schema.Context(tmp_path)


def check(schemas_ctx, rel, fm):
    schemas, ctx = schemas_ctx
    note = frontmatter.parse(f"---\n{fm}\n---\nbody")
    return schema.validate_note(schemas, rel, note, ctx)


def codes(issues, severity=None):
    return [i.code for i in issues if severity is None or i.severity == severity]


def test_valid_minimal(schemas):
    t, issues = check(schemas, "things/a.md", "type: thing\nname: A")
    assert t == "thing" and issues == []


def test_uncovered_path_is_ignored(schemas):
    assert check(schemas, "elsewhere/a.md", "nothing: here") == (None, [])


def test_exact_file_folder(schemas):
    assert check(schemas, "single.md", "type: thing\nname: A")[1] == []


def test_missing_required(schemas):
    assert codes(check(schemas, "things/a.md", "type: thing")[1]) == ["required"]


def test_missing_type_and_unknown_type(schemas):
    assert codes(check(schemas, "things/a.md", "name: A")[1]) == ["missing-type"]
    assert codes(check(schemas, "things/a.md", "type: other\nname: A")[1]) == ["unknown-type"]


def test_plain_markdown_in_covered_folder(schemas):
    s, ctx = schemas
    _, issues = schema.validate_note(s, "things/a.md", frontmatter.parse("# just text"), ctx)
    assert codes(issues) == ["frontmatter"]


@pytest.mark.parametrize("field, good, bad", [
    ("count", '"0123"', "1.5"),
    ("flag", "TRUE", "yes"),
    ("day", '"2026-09-30"', '"2026-13-01"'),
    ("at", '"2026-09-30T06:00:00-06:00"', "tomorrow"),
    ("hhmm", "17:00", "25:00"),
    ("tz", "America/Denver", "Mars/Olympus"),
    ("color", "red", "green"),
    ("items", "[a, b]", "notalist"),
    ("layers", "{ui: web/}", "[a]"),
    ("ref", '"[[Index]]"', "Index"),
    ("minutes", '"60"', '"61"'),
    ("minutes", '"1"', '"0"'),
])
def test_kinds(schemas, field, good, bad):
    base = "type: thing\nname: A\n"
    assert codes(check(schemas, "things/a.md", base + f"{field}: {good}")[1], "error") == []
    assert codes(check(schemas, "things/a.md", base + f"{field}: {bad}")[1], "error") == ["field"]


def test_link_accepts_unquoted_nested_list(schemas):
    assert codes(check(schemas, "things/a.md", "type: thing\nname: A\nref: [[Index]]")[1]) == []


def test_path_must_exist_warns(schemas):
    _, issues = check(schemas, "things/a.md", "type: thing\nname: A\nwhere: /no/such/path")
    assert [(i.severity, i.code) for i in issues] == [("warning", "field")]


def test_unknown_field_warns(schemas):
    _, issues = check(schemas, "things/a.md", "type: thing\nname: A\nextra: 1")
    assert [(i.severity, i.code) for i in issues] == [("warning", "unknown-field")]


def test_matches_folder(schemas):
    s, ctx = schemas
    s["thing"].folders.append("wiki/")
    ok = schema.validate_note(s, "wiki/work/a.md", frontmatter.parse("---\ntype: thing\nname: A\npartition: work\n---\n"), ctx)
    bad = schema.validate_note(s, "wiki/work/a.md", frontmatter.parse("---\ntype: thing\nname: A\npartition: personal\n---\n"), ctx)
    assert codes(ok[1]) == [] and codes(bad[1]) == ["partition-folder"]


def test_type_folder_mismatch(tmp_path):
    write(tmp_path, "system/schemas/a.md", "---\ntype: schema\nschema_for: a\nfolders: [\"x/\"]\nfields:\n  type: {kind: const, value: a}\n---\n")
    write(tmp_path, "system/schemas/b.md", "---\ntype: schema\nschema_for: b\nfolders: [\"y/\"]\nfields:\n  type: {kind: const, value: b}\n---\n")
    s = schema.load_schemas(tmp_path)
    _, issues = schema.validate_note(s, "x/n.md", frontmatter.parse("---\ntype: b\n---\n"), schema.Context(tmp_path))
    assert codes(issues) == ["type-folder-mismatch"]


def test_bad_schema_raises(tmp_path):
    write(tmp_path, "system/schemas/bad.md", "---\ntype: schema\nschema_for: bad\nfolders: [\"x/\"]\nfields:\n  a: {kind: nope}\n---\n")
    with pytest.raises(schema.SchemaError):
        schema.load_schemas(tmp_path)


def test_path_partition():
    assert schema.path_partition("wiki/work/concepts/A.md") == "work"
    assert schema.path_partition("raw/personal/notes/d.md") == "personal"
    assert schema.path_partition("wiki/Index.md") is None
    assert schema.path_partition("briefings/2026-09-30.md") is None


def test_link_target():
    assert schema.link_target("[[A|alias]]") == "A|alias"
    assert schema.link_target([["A"]]) == "A"
    assert schema.link_target("A") is None


def test_unhashable_kind_raises(tmp_path):
    write(tmp_path, "system/schemas/bad.md", "---\ntype: schema\nschema_for: bad\nfolders: [\"x/\"]\nfields:\n  a: {kind: [x]}\n---\n")
    with pytest.raises(schema.SchemaError):
        schema.load_schemas(tmp_path)


def test_unhashable_kind_in_list_raises(tmp_path):
    write(tmp_path, "system/schemas/bad.md", "---\ntype: schema\nschema_for: bad\nfolders: [\"x/\"]\nfields:\n  a: {kind: list, of: {kind: [x]}}\n---\n")
    with pytest.raises(schema.SchemaError):
        schema.load_schemas(tmp_path)


def test_non_utf8_schema_raises(tmp_path):
    (tmp_path / "system" / "schemas").mkdir(parents=True, exist_ok=True)
    (tmp_path / "system" / "schemas" / "bad.md").write_bytes(b"---\xff\xfe\n")
    with pytest.raises(schema.SchemaError):
        schema.load_schemas(tmp_path)


def test_values_not_list_raises(tmp_path):
    write(tmp_path, "system/schemas/bad.md", "---\ntype: schema\nschema_for: bad\nfolders: [\"x/\"]\nfields:\n  a: {kind: enum, values: abc}\n---\n")
    with pytest.raises(schema.SchemaError):
        schema.load_schemas(tmp_path)


def test_must_exist_invalid_raises(tmp_path):
    write(tmp_path, "system/schemas/bad.md", "---\ntype: schema\nschema_for: bad\nfolders: [\"x/\"]\nfields:\n  a: {kind: path, must_exist: bogus}\n---\n")
    with pytest.raises(schema.SchemaError):
        schema.load_schemas(tmp_path)


def test_const_value_not_string_raises(tmp_path):
    write(tmp_path, "system/schemas/bad.md", "---\ntype: schema\nschema_for: bad\nfolders: [\"x/\"]\nfields:\n  a: {kind: const, value: [a]}\n---\n")
    with pytest.raises(schema.SchemaError):
        schema.load_schemas(tmp_path)


@pytest.mark.parametrize("spec, message", [
    ('{kind: int, min: "x"}', "min must be an integer string"),
    ('{kind: int, max: "1.5"}', "max must be an integer string"),
    ('{kind: string, min: "1"}', "min and max apply to int fields only"),
    ('{kind: int, min: "5", max: "1"}', "min is greater than max"),
])
def test_int_bounds_spec_errors(tmp_path, spec, message):
    write(tmp_path, "system/schemas/thing.md",
          f"---\ntype: schema\nschema_for: thing\nfolders: [things/]\nfields:\n  n: {spec}\n---\n")
    with pytest.raises(schema.SchemaError, match=message):
        schema.load_schemas(tmp_path)
