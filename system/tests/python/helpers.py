"""Shared helpers for the vaultlib test suite."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def write(root: Path, rel: str, text: str) -> Path:
    """Write text to root/rel, creating parent directories."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def concept(partition: str, title: str, body: str = "", **extra: str) -> str:
    """Return a valid concept note. extra values are raw YAML snippets."""
    fm = {
        "type": "concept",
        "tags": "[]",
        "compiled_at": '"2026-09-01"',
        "partition": partition,
    }
    fm.update(extra)
    lines = ["---", *[f"{k}: {v}" for k, v in fm.items()], "---", f"# {title}", body, ""]
    return "\n".join(lines)


def meeting(partition: str, name: str, title: str = "Weekly sync", body: str = "", **extra: str) -> str:
    """Return a valid meeting note for <name> (YYYY-MM-DD-HHMM-slug). extra values are raw YAML snippets."""
    fm = {"type": "meeting", "title": json.dumps(title), "date": f'"{name[:10]}"',
          "start": f'"{name[:10]}T{name[11:13]}:{name[13:15]}:00-06:00"', "partition": partition,
          "source": f'"gdoc:FAKE-{name}"', "transcript": f'"[[{name}.transcript]]"'}
    fm.update(extra)
    return "\n".join(["---", *[f"{k}: {v}" for k, v in fm.items()], "---", f"# {title}", body, ""])


def transcript(partition: str, name: str, body: str = "") -> str:
    """Return a valid meeting_transcript note beside meeting(<partition>, <name>)."""
    return (f'---\ntype: meeting_transcript\nmeeting: "[[{name}]]"\npartition: {partition}\n'
            f'source: "gdoc:FAKE-{name}"\ncomplete: true\n---\n# Transcript\n{body}\n')


def call(input: dict = None, text="…", sc: dict = None, error: bool = False) -> dict:
    """One call of the session's tool for stream(): its input, its result's content (text), the result's
    tool_use_result.structuredContent (sc) and is_error."""
    return {"input": input or {}, "text": text, "sc": sc, "error": error}


def stream(tool: str, calls=(), reply: str = None, result: str = "success", named: bool = True, **result_fields) -> list:
    """A connector session's stream-json (F1 spec §3.4): a ToolSearch call whose result names `tool` in a
    tool_reference block (or, with named=False, only in free text, as a "not found" reply can, #38); then per call a
    tool_use (ids t1, t2, …) and its tool_result; then the result message (reply, default {"items": []})."""
    found = ([{"type": "tool_reference", "tool_name": tool}] if named
             else [{"type": "text", "text": f"No matching deferred tools found for select:{tool}"}])
    s = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t0", "name": "ToolSearch", "input": {}}]}},
         {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t0", "content": found}]}}]
    for n, c in enumerate(calls, 1):
        s.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": f"t{n}", "name": tool, "input": c["input"]}]}})
        m = {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"t{n}", "is_error": c["error"], "content": c["text"]}]}}
        if c["sc"] is not None:
            m["tool_use_result"] = {"structuredContent": c["sc"]}
        s.append(m)
    s.append({"type": "result", "subtype": result, "is_error": result != "success",
              "result": reply if reply is not None else json.dumps({"items": []}), **result_fields})
    return s
