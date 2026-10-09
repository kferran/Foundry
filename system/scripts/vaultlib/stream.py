"""Reading a `claude -p --output-format stream-json` session: shared by the connector fetches' checkers."""
import json


def messages(text: str) -> list:
    """The stream's JSON objects, one per line; other lines are skipped."""
    out = []
    for line in text.splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if isinstance(m, dict):
            out.append(m)
    return out


def blocks(m: dict, kind: str) -> list:
    """The content blocks of one message of type <kind> (tool_use, tool_result, text)."""
    content = (m.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict) and b.get("type") == kind] if isinstance(content, list) else []
