import pytest

from vaultlib import yamlload


@pytest.mark.parametrize("raw, expected", [
    ("17:00", "17:00"),
    ("06:00", "06:00"),
    ("no", "no"),
    ("yes", "yes"),
    ("on", "on"),
    ("0123", "0123"),
    ("1e3", "1e3"),
    ("2026-09-30", "2026-09-30"),
    ("~", "~"),
    ("null", "null"),
    ("true", "true"),
])
def test_scalars_stay_strings(raw, expected):
    assert yamlload.load(f"a: {raw}") == {"a": expected}


def test_empty_value_is_empty_string():
    assert yamlload.load("a:") == {"a": ""}


def test_keys_stay_strings():
    assert yamlload.load("no: x") == {"no": "x"}


def test_lists_and_maps_preserved():
    assert yamlload.load("a: [x, 2]\nb:\n  c: 3") == {"a": ["x", "2"], "b": {"c": "3"}}


def test_unquoted_wikilink_is_nested_list():
    assert yamlload.load("source: [[Index]]") == {"source": [["Index"]]}


def test_empty_document_is_none():
    assert yamlload.load("") is None
