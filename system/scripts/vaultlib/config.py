"""The one reader of system/config.md: its frontmatter, {} when the file cannot be read."""
from pathlib import Path

from . import frontmatter


def config(vault) -> dict:
    try:
        return frontmatter.parse((Path(vault) / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return {}


def text(vault, key: str, default: str) -> str:
    """The value of key when it is a non-empty string, else default."""
    value = config(vault).get(key)
    return value if isinstance(value, str) and value else default
