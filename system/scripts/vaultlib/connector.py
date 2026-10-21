"""The check of a confined connector session's stream-json (F1 spec §3.1), shared by every connector fetch.

A session may call only ToolSearch and its one connector tool (and StructuredOutput, for a --json-schema session),
each input one that accept(input) names; a result over the model's token limit is caught where claude puts its
stand-in, so mail, chat or event text cannot fake one.
"""
import json
from typing import NamedTuple

from .stream import blocks


class Fail(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code, self.reason = code, reason


def too_large(content) -> bool:
    """True when the model saw claude's stand-in for a result over its token limit instead of the result: a
    <persisted-output> preview, a cut ending "[OUTPUT TRUNCATED - exceeded …", the MCP note ("Error: result (…)
    exceeds maximum allowed tokens", "MCP tool response (N tokens) exceeds …") or "Output too large". A JSON result
    starts with { or [ and holds no raw newline, so its text cannot be read as any of them."""
    text = ("".join(c.get("text", "") for c in content if isinstance(c, dict)) if isinstance(content, list)
            else str(content or "")).strip()
    return (text.startswith("<persisted-output>") or "\n\n[OUTPUT TRUNCATED - exceeded " in text
            or (not text.startswith(("{", "[")) and ("exceeds maximum allowed tokens" in text[:200]
                                                     or text.startswith("Output too large"))))


def structured(block: dict, message: dict) -> dict:
    """The result's tool_use_result.structuredContent, else {}."""
    tur = message.get("tool_use_result")
    sc = tur.get("structuredContent") if isinstance(tur, dict) else None
    return sc if isinstance(sc, dict) else {}


def text_json(block: dict, message: dict) -> dict:
    """The result's text parsed as one JSON object (the Slack search answers in text only), else {}."""
    content = block.get("content")
    text = "".join(c.get("text", "") for c in content if isinstance(c, dict)) if isinstance(content, list) else str(content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    return data if isinstance(data, dict) else {}


def strip_cursor(i: dict) -> dict:
    """The input less its "cursor" key: a later page of a search adds only that."""
    return {k: v for k, v in i.items() if k != "cursor"}


class Walk(NamedTuple):
    calls: list          # (name, tool_use block) for each call of `tool`, in stream order
    results: list        # (name, tool_result block, user message) for each result of `tool`
    named: bool          # a ToolSearch result held a tool_reference block naming `tool`
    result: dict | None  # the last message of type "result"


def walk(stream: list, tool: str, accept, max_calls: int | None = None, structured: bool = False) -> Walk:
    """The tool and input guard, in stream order. accept(input) names the built call an input runs, or returns None
    to refuse it (it may raise its own Fail 7). A call past max_calls for its name fails at the call. Only a
    tool_reference block naming the tool counts as found: a "not found" reply can repeat the name in its text (#38)."""
    allowed = ("ToolSearch", tool, "StructuredOutput") if structured else ("ToolSearch", tool)
    ids, calls, results, counts, named = {}, [], [], {}, False
    for m in stream:
        if m.get("type") == "assistant":
            for b in blocks(m, "tool_use"):
                if b.get("name") not in allowed:
                    raise Fail(7, f"the session used an unexpected tool: {b.get('name')}")
                name = b.get("name")
                if name == tool:
                    name = accept(b.get("input") if isinstance(b.get("input"), dict) else {})
                    if name is None:
                        raise Fail(7, f"the session called {tool} with other arguments than the ones built for this run")
                    counts[name] = counts.get(name, 0) + 1
                    if max_calls is not None and counts[name] > max_calls:
                        raise Fail(7, f"the session made {counts[name]} {name} calls; the limit is {max_calls}")
                    calls.append((name, b))
                ids[b.get("id")] = (b.get("name"), name)
        if m.get("type") == "user":
            for b in blocks(m, "tool_result"):
                called, name = ids.get(b.get("tool_use_id"), ("", ""))
                content = b.get("content")
                if called == "ToolSearch" and isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("type") == "tool_reference" and c.get("tool_name") == tool
                        for c in content):
                    named = True
                if called == tool:
                    results.append((name, b, m))
    return Walk(calls, results, named, next((m for m in reversed(stream) if m.get("type") == "result"), None))


def check_stream(stream: list, tool: str, accept, max_pages: int | None = None, server: str = "",
                 persisted: dict | None = None, take=structured, need_result: bool = True) -> tuple:
    """({name: [page payloads]}, the result message) for a read session, after walk and the end rules in order: a
    result the model saw only as too large (fails 6, or with a `persisted` dict is counted there by name and still
    taken: the stream's structuredContent holds the whole result), no result message, an error result, no call, an
    error result message. need_result=False (a write the tool result proves) skips the two result-message rules."""
    w = walk(stream, tool, accept, max_pages)
    pages, errors = {name: [] for name, _ in w.calls}, []
    for name, b, m in w.results:
        if too_large(b.get("content")):
            if persisted is None:
                raise Fail(6, f"a {name} result was too large for the model to read")
            persisted[name] = persisted.get(name, 0) + 1
        elif b.get("is_error"):
            errors.append(json.dumps(b.get("content"))[:200])
            continue
        pages[name].append(take(b, m))
    if need_result and w.result is None:
        raise Fail(1, "claude produced no result")
    if errors:
        raise Fail(6, f"the connector returned an error: {errors[0]}")
    if not w.calls:
        raise Fail(1 if w.named else 3, f"the session never called {tool}" if w.named else f"no {server} connector reachable")
    if need_result and (w.result.get("is_error") or w.result.get("subtype") != "success"):
        raise Fail(1, f"claude returned an error result ({w.result.get('subtype')})")
    return pages, w.result
