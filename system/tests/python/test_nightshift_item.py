# system/tests/python/test_nightshift_item.py
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vaultlib import frontmatter, nightshift_item as ni, publish, schema

NOW = datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)


def plan_fm(**extra):
    fm = {"type": "nightshift_item", "id": "2026-10-06-dtcc-watcher", "partition": "work", "kind": "plan",
          "state": "queued", "queued_at": NOW.isoformat(), "start": "window", "budget": "4h", "model": "sonnet",
          "repo": "template", "base": "feat/x", "pr_base": "master", "plan": "docs/p.md", "tasks": "1-8",
          "verify": ["python3 -m pytest -q"]}
    fm.update(extra)
    return fm


def test_ids_and_budgets():
    assert ni.new_id("DTCC watcher (phase 1)", NOW) == "2026-10-06-dtcc-watcher-phase-1"
    assert ni.budget_seconds("4h") == 14400 and ni.budget_seconds("90m") == 5400
    with pytest.raises(ValueError):
        ni.budget_seconds("4 hours")


def test_render_validates_and_round_trips(vault: Path):
    path = ni.note_path(vault, "work", "2026-10-06-dtcc-watcher")
    ni.save(path, plan_fm(), "free note\n")
    schemas = schema.load_schemas(vault)
    rel = path.relative_to(vault).as_posix()
    ntype, issues = schema.validate_note(schemas, rel, frontmatter.parse(path.read_text()), schema.Context(vault))
    assert ntype == "nightshift_item" and [i.message for i in issues if i.severity == "error"] == []
    fm, body = ni.load(path)
    assert fm["verify"] == ["python3 -m pytest -q"] and body.strip() == "free note"
    assert [p for p, _, _ in ni.items(vault)] == [path]


def test_update_never_overwrites_cancelled(vault: Path):
    path = ni.note_path(vault, "work", "a")
    ni.save(path, plan_fm(id="a", state="cancelled"), "")
    ni.update(path, state="running", session_id="s")
    fm, _ = ni.load(path)
    assert fm["state"] == "cancelled" and "session_id" not in fm
    ni.update(path, reason="cancelled by user")
    assert ni.load(path)[0]["reason"] == "cancelled by user"


def test_update_removes_none(vault: Path):
    path = ni.note_path(vault, "work", "b")
    ni.save(path, plan_fm(id="b", reset_at="2026-10-07T01:00:00+00:00"), "")
    ni.update(path, reset_at=None, state="running")
    fm, _ = ni.load(path)
    assert "reset_at" not in fm and fm["state"] == "running"


def test_publish_accepts_nightshift_run_ids():
    assert publish.check_run_id("20261006T210000-nightshift-ab12") == "nightshift"
