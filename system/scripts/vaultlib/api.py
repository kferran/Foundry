"""The extension API (factory F2 §3.3): the only vaultlib module an extension script imports. It re-exports what the
template's extension scripts use, in the form they use it (a module imported whole stays whole, a name stays a name),
plus `schema` and `yamlload` for a vault's own extension. system/tests/python/test_extension_api.py holds the line:
an import of any other vaultlib module from extensions/ fails it, and so does an export no script uses."""
from . import cli, frontmatter, now, schema, triage, yamlload
from .briefings import cut
from .cli import UsageError, set_scalar
from .connector import Fail, check_stream, strip_cursor, text_json, walk
from .intake import Intake
from .meetings import open_actions, owner_names
from .notify import prefix, thread_state
from .redact import redact_credentials
from .state import append, load, records, save
from .stream import blocks, messages
from .triage import config, one_line, reply

__all__ = [
    "cli", "frontmatter", "now", "schema", "triage", "yamlload",
    "cut", "UsageError", "set_scalar", "Fail", "check_stream", "strip_cursor", "text_json", "walk", "Intake",
    "open_actions", "owner_names", "prefix", "thread_state", "redact_credentials", "append", "load", "records", "save",
    "blocks", "messages", "config", "one_line", "reply",
]
