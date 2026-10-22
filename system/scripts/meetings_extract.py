#!/usr/bin/env python3
"""Check a meetings fetch session's stream-json and take the Drive results from it (meetings spec §2.1).

Usage: meetings_extract.py search < stream          print the listed files as a JSON list
       meetings_extract.py read <id> <listing> < stream  write raw/meetings/<id>.gdoc.md
       meetings_extract.py filter < listing         print the IDs to read, oldest first
The text comes from each result's tool_use_result.structuredContent, after vaultlib.connector.check_stream's
tool-use checks; the model's own words are never used. Exit: 0 ok, 1 claude error, 2 usage, 3 no connector,
6 connector error, 7 unexpected tool use or a read of another Doc. A non-zero exit writes one reason line to stderr.
"""
import fnmatch
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib.index import Index  # noqa: E402
from vaultlib.connector import Fail, check_stream  # noqa: E402
from vaultlib.stream import messages  # noqa: E402

PREFIX = "mcp__claude_ai_Google_Drive"
TOOLS = {"search": f"{PREFIX}__search_files", "read": f"{PREFIX}__read_file_content"}
DOC_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")
SETTLE_SECONDS = 600
MAX_FAILURES = 3


def search(stream):
    """The listed files. A result in any shape but a files list fails closed (exit 1), so a changed stream
    shows as an unavailable source instead of an empty listing that moves .since on."""
    keys, files, seen = ("id", "title", "createdTime", "modifiedTime"), [], set()
    # persisted={}: a page the model saw only as too large is still read from structuredContent, as before F1.
    # ponytail: spec §3.6 item 2 fails it (6); held until a live stream capture shows what a Drive page sends.
    got = check_stream(stream, TOOLS["search"], lambda i: "search", server="Google Drive", persisted={})[0]["search"]
    if not got:
        raise Fail(1, "the search call has no result")
    for sc in got:
        listed = sc.get("files")
        if not isinstance(listed, list):
            raise Fail(1, "the search result carries no files list")
        ok = [f for f in listed if isinstance(f, dict) and all(isinstance(f.get(k), str) for k in keys)]
        if listed and not ok:
            raise Fail(1, "no listed file has an id, title, createdTime and modifiedTime")
        for f in ok:  # several search calls (pages, retries) can list a Doc again: keep its first entry
            if f["id"] not in seen:
                seen.add(f["id"])
                files.append({k: f[k] for k in keys})
    return files


def read(stream, doc_id, listing):
    meta = next((f for f in listing if f.get("id") == doc_id), None)
    if meta is None or not DOC_ID.match(doc_id):
        raise Fail(2, f"not a listed Doc: {doc_id}")

    def accept(i):  # a read of any other Doc fails at the call
        if i.get("fileId") != doc_id:
            raise Fail(7, f"the session read a Doc that was not requested: {i.get('fileId')}")
        return "read"

    text = None
    # The model only replies "done", so a result it saw only as too large is still written from structuredContent.
    for sc in check_stream(stream, TOOLS["read"], accept, server="Google Drive", persisted={})[0]["read"]:
        if isinstance(sc.get("fileContent"), str):
            text = sc["fileContent"]
    if text is None:
        raise Fail(1, "the read result carries no fileContent")
    head = "".join(f"{key}: {json.dumps(meta[src], ensure_ascii=False)}\n" for key, src in
                   (("doc_id", "id"), ("title", "title"), ("created_time", "createdTime"), ("modified_time", "modifiedTime")))
    out = VAULT / "raw" / "meetings" / f"{doc_id}.gdoc.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{doc_id}.tmp")
    tmp.write_text(f"---\n{head}---\n{text}", encoding="utf-8")
    os.replace(tmp, out)


def fetch_log():
    """(failed read counts, skipped IDs) from this month's and last month's fetch logs."""
    failures, skipped = {}, set()
    for path in sorted((VAULT / "system" / "logs").glob("meetings_fetch-*.jsonl"))[-2:]:
        for r in messages(path.read_text(encoding="utf-8", errors="replace")):
            if r.get("skipped") is True:
                skipped.add(r.get("doc"))
            elif r.get("step") == "read" and r.get("exit") != 0:
                failures[r.get("doc")] = failures.get(r.get("doc"), 0) + 1
    return failures, skipped


def known_sources():
    idx = Index(VAULT)
    idx.refresh(timeout=60)
    conn = sqlite3.connect(idx.db_path)
    try:
        return {s for (s,) in conn.execute("SELECT source FROM v_meeting_all") if isinstance(s, str)}
    finally:
        conn.close()


def parse_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def wanted(listing):
    failures, skipped = fetch_log()
    known = known_sources()
    quarantine = VAULT / "system" / "quarantine" / "meetings"
    held = {p.name for p in quarantine.iterdir()} if quarantine.is_dir() else set()
    now = datetime.now(timezone.utc)
    keep = []
    for f in listing:
        doc_id, modified = f.get("id", ""), parse_time(f.get("modifiedTime"))
        if (not DOC_ID.match(doc_id) or not fnmatch.fnmatchcase(f.get("title", ""), "* - Notes by Gemini")
                or modified is None or (now - modified).total_seconds() <= SETTLE_SECONDS
                or f"gdoc:{doc_id}" in known or (VAULT / "raw" / "meetings" / f"{doc_id}.gdoc.md").exists()
                or any(n.startswith(f"{doc_id}.gdoc") for n in held)
                or doc_id in skipped or failures.get(doc_id, 0) >= MAX_FAILURES):
            continue
        keep.append(f)
    return [f["id"] for f in sorted(keep, key=lambda f: f["createdTime"])]


def main(argv):
    try:
        if argv[1:2] == ["search"] and len(argv) == 2:
            print(json.dumps(search(messages(sys.stdin.read()))))
        elif argv[1:2] == ["read"] and len(argv) == 4:
            read(messages(sys.stdin.read()), argv[2], json.loads(Path(argv[3]).read_text(encoding="utf-8")))
        elif argv[1:2] == ["filter"] and len(argv) == 2:
            try:
                ids = wanted(json.loads(sys.stdin.read()))
            except (sqlite3.Error, OSError, TimeoutError, ValueError) as exc:
                raise Fail(1, f"{exc.__class__.__name__}: {exc}")
            print("".join(f"{doc_id}\n" for doc_id in ids), end="")
        else:
            raise Fail(2, "usage: meetings_extract.py search | read <id> <listing> | filter")
    except Fail as f:
        print(f"meetings_extract: {f.reason}", file=sys.stderr)
        return f.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
