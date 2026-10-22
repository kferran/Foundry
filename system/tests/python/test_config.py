"""The one reader of system/config.md (factory F3 spec §3.3)."""
import pytest

from vaultlib import config as cfg


def put(vault, data):
    path = vault / "system" / "config.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


@pytest.mark.parametrize("data", [None, b"\xff", "---\n: [\n---\n", "no frontmatter\n"])
def test_unreadable_or_empty_config_is_an_empty_dict(tmp_path, data):
    if data is not None:
        put(tmp_path, data)
    assert cfg.config(tmp_path) == {}


def test_good_config_reads(tmp_path):
    put(tmp_path, '---\ntimezone: "UTC"\n---\n')
    assert cfg.config(tmp_path)["timezone"] == "UTC"
    assert cfg.text(tmp_path, "timezone", "d") == "UTC"


@pytest.mark.parametrize("body", ['k: ""', "k: [a]", "other: x"])
def test_text_falls_back_to_the_default(tmp_path, body):
    put(tmp_path, f"---\n{body}\n---\n")
    assert cfg.text(tmp_path, "k", "d") == "d"


def test_text_default_without_a_file(tmp_path):
    assert cfg.text(tmp_path, "k", "d") == "d"
