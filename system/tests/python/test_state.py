"""The shared state-file helpers (F1 spec §3.3), ported from the watch's common.py."""
import json

from vaultlib import state


def test_save_is_atomic_and_load_falls_back(tmp_path):
    p = tmp_path / "deep" / "cursors.json"
    assert state.load(p, {"none": 1}) == {"none": 1}
    state.save(p, {"b": 1, "a": [2]})
    assert p.read_text() == '{\n "a": [\n  2\n ],\n "b": 1\n}\n'
    assert state.load(p, None) == {"a": [2], "b": 1}
    assert sorted(x.name for x in p.parent.iterdir()) == ["cursors.json"]   # no temporary file left
    p.write_text("{bad")
    assert state.load(p, []) == []


def test_records_reads_each_path_in_order_and_skips_bad_lines(tmp_path):
    a, b = tmp_path / "x" / "a.jsonl", tmp_path / "b.jsonl"
    state.append(a, {"n": 1})
    a.write_text(a.read_text() + "not json\n[1]\n")
    state.append(a, {"n": 2})
    state.append(b, {"n": 3})
    assert json.loads(a.read_text().splitlines()[0]) == {"n": 1}
    assert state.records(b, tmp_path / "missing.jsonl", a) == [{"n": 3}, {"n": 1}, {"n": 2}]
