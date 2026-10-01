from vaultlib import frontmatter


def test_no_frontmatter():
    note = frontmatter.parse("# Title\nbody")
    assert note.data is None and note.error is None
    assert note.body == "# Title\nbody" and note.body_line == 1


def test_basic_frontmatter():
    note = frontmatter.parse("---\ntype: concept\ntags: [a]\n---\n# T\nbody")
    assert note.data == {"type": "concept", "tags": ["a"]}
    assert note.body == "# T\nbody"
    assert note.body_line == 5


def test_empty_frontmatter_is_empty_dict():
    assert frontmatter.parse("---\n---\nbody").data == {}


def test_malformed_yaml_reports_line():
    note = frontmatter.parse("---\ntype: concept\ntags: [a\n---\nbody")
    assert note.data is None
    assert note.error.startswith("malformed frontmatter")
    assert note.error_line >= 2


def test_non_mapping_frontmatter():
    note = frontmatter.parse("---\n- a\n- b\n---\nbody")
    assert note.data is None and note.error == "frontmatter is not a mapping"


def test_unterminated():
    note = frontmatter.parse("---\ntype: concept\nbody")
    assert note.error == "unterminated frontmatter"


def test_dashes_inside_body_ignored():
    note = frontmatter.parse("---\ntype: a\n---\ntext\n---\nmore")
    assert note.data == {"type": "a"} and note.body == "text\n---\nmore"


def test_crlf_and_bom():
    note = frontmatter.parse("﻿---\r\ntype: concept\r\n---\r\nbody")
    assert note.data == {"type": "concept"}


def test_key_line():
    note = frontmatter.parse("---\ntype: concept\ntags: []\n---\n")
    assert frontmatter.key_line(note, "tags") == 3
    assert frontmatter.key_line(note, "missing") == 2
