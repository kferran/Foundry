"""The shared contract (ARCHITECTURE.md §5): today.py's real output has every key the app's fixture has, at every level,
so the Vue side never renders a shape the adapter does not produce. Lists are compared through their first item."""
import json
from pathlib import Path

from console_today_fixtures import EXT, today_json, today_vault, write

FIXTURE = EXT / "app" / "tests" / "fixtures" / "today.json"


def missing(want, have, at="") -> list:
    """Every key path in `want` that `have` lacks. A list of objects in `want` needs a non-empty list in `have`, so its
    items' keys can be checked; a list of strings carries no keys, so an empty one passes."""
    out = []
    if isinstance(want, dict):
        if not isinstance(have, dict):
            return [f"{at or '.'}: not an object"]
        for k, v in want.items():
            out += [f"{at}.{k}"] if k not in have else missing(v, have[k], f"{at}.{k}")
    elif isinstance(want, list) and want and isinstance(want[0], dict):
        if not isinstance(have, list) or not have:
            return [f"{at}[]: empty"]
        out += missing(want[0], have[0], f"{at}[0]")
    return out


def outcome(vault: Path, day: str) -> None:
    """One Work Order that ran today, so the report's items list is not empty."""
    write(vault.parent / "ws", "state/items/2026-10-22-done-one/outcome.json", json.dumps({
        "id": "2026-10-22-done-one", "kind": "plan", "state": "done", "result": "https://github.com/acme/shop/pull/9",
        "reason": "", "started_at": f"{day}T01:00:00-06:00", "finished_at": f"{day}T02:00:00-06:00",
        "report_date": day, "needs": [], "notes": "4 tasks"}))


def test_the_adapter_produces_every_key_the_app_fixture_has(vault, day):
    today_vault(vault, day)
    outcome(vault, day)
    assert missing(json.loads(FIXTURE.read_text()), today_json(vault)) == []


def test_a_key_only_the_fixture_has_is_found():
    have = {"a": 1, "rows": [{"x": 1}], "empty": [], "names": []}
    assert missing({"a": 1, "b": 2}, have) == [".b"]
    assert missing({"rows": [{"x": 1, "y": 2}]}, have) == [".rows[0].y"]
    assert missing({"empty": [{"x": 1}]}, have) == [".empty[]: empty"]
    assert missing({"names": ["Gamma"]}, have) == []
    assert missing({"a": {"deep": 1}}, have) == [".a: not an object"]
