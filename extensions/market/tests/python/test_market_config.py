"""The market extension's manifest and config keys (market watch spec §3.1, amended M1, M2, M9, M10, M12)."""
from conftest import EXT, write_config
from vaultlib import extensions


def example_keys() -> str:
    text = (EXT / "templates" / "config.example.md").read_text(encoding="utf-8")
    front = text.split("---\n")[1]
    return "".join(line + "\n" for line in front.splitlines() if not line.startswith("type:"))


def test_the_manifest_loads_with_no_reasons(vault):
    assert extensions.check(vault) == []
    assert "market" in [n for n, _ in extensions.enabled(vault)]


def test_the_example_config_validates(vault, cli):
    write_config(vault, example_keys())
    r = cli("validate", "system/config.md")
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_watch_entry_needs_a_name_and_group(vault, cli):
    write_config(vault, 'market_watch: [{newsroom: "https://example.com/news"}]\n')
    r = cli("validate", "system/config.md")
    assert r.returncode != 0
    assert "name" in r.stdout + r.stderr
