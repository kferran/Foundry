"""The market_page schema and the market command (market watch spec §3.3, §3.4)."""
import shutil

import pytest

from market_helpers import EXT, FIXTURES
from vaultlib import extensions

PAGE = "briefings/market/2026-11-06.md"
HEADINGS = ["## Threats", "## Openings", "## Watch", "## News", "## Proposed changes"]


def put_page(vault, text=None):
    dst = vault / PAGE
    dst.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        shutil.copy(FIXTURES / "page.md", dst)
    else:
        dst.write_text(text)


def test_the_market_command_resolves(vault):
    assert extensions.command(vault, "market") == {"ext": "market", "name": "market",
                                                   "targets": ["briefings/market/<date>.md"], "model": "sonnet",
                                                   "timeout_minutes": 20}


def test_the_fixture_page_validates(vault, cli):
    put_page(vault)
    r = cli("validate", PAGE)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("old,new", [("counts: {threat: 2, opening: 1, watch: 1, news: 1}\n", ""),
                                     ("threat: 2", "threat: -1")])
def test_a_page_without_counts_or_with_a_negative_count_fails(vault, cli, old, new):
    put_page(vault, (FIXTURES / "page.md").read_text().replace(old, new))
    r = cli("validate", PAGE)
    assert r.returncode != 0
    assert "counts" in r.stdout + r.stderr


def test_the_prompt_names_its_only_target_and_tools():
    text = (EXT / "commands" / "market.md").read_text()
    assert "wiki/.staging/<run_id>/briefings/market/<date>.md" in text
    assert "vault_index.py stage" in text
    positions = [text.index(h) for h in HEADINGS]
    assert positions == sorted(positions)
    for banned in ("WebFetch", "WebSearch", "now.py", "alert.py"):
        assert banned not in text
