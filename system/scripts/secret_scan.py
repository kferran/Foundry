#!/usr/bin/env python3
"""Report credential shapes, never their values (secret-shape lint spec §2, #166).

secret_scan.py --staged  the lines a commit adds: each staged text blob's lines that are in neither the HEAD blob
                         nor, during a merge, the MERGE_HEAD blob (the pre-commit hook and the unattended sync)
secret_scan.py           the working copy of every tracked and untracked file (lint_vault.sh)

Prints `secret shape: <path>:<line>: <shape>` per match. Exit 0 clean, 1 findings, 2 unscanned: the shape list in
vaultlib/redact.py could not be read or is empty, or git could not list or read the files."""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ZERO = "0" * 40
# .scratch/ is throwaway. The tree report also skips the template's system/tests/ and docs/superpowers/, which hold
# the redaction tests' fake tokens by design; a staged file there is still scanned.
SKIP = (".scratch/",)
TREE_SKIP = SKIP + ("system/tests/", "docs/superpowers/")


def unscanned(reason: str):
    print(f"secret shape: unscanned ({reason})")
    sys.exit(2)


def git(*args: str, stdin: bytes = b"", ok: bool = False) -> bytes:
    try:
        res = subprocess.run(["git", "-C", str(ROOT), *args], input=stdin, capture_output=True)
    except OSError as exc:
        unscanned(f"git {args[0]} failed: {exc}")
    if res.returncode != 0 and not ok:
        unscanned(f"git {args[0]} failed: {res.stderr.decode(errors='replace').strip()}")
    return res.stdout if res.returncode == 0 else b""


def text(data: bytes):
    """The text of a file, or None for a binary one: UTF-16 with a byte-order mark as the drop import reads it,
    else a NUL in the first 8 KiB (git's own test) is binary, else UTF-8."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", "surrogateescape")


def blobs(shas: set) -> dict:
    """Every blob in one git cat-file --batch."""
    order = sorted(shas)
    out, pos, found = git("cat-file", "--batch", stdin="".join(f"{s}\n" for s in order).encode()), 0, {}
    for sha in order:
        eol = out.find(b"\n", pos)
        head = out[pos:eol].split()
        if eol < 0 or len(head) != 3:
            unscanned(f"git cat-file: {sha} is missing")
        size = int(head[2])
        found[sha] = out[eol + 1:eol + 1 + size]
        pos = eol + 1 + size + 1
    return found


def staged() -> list:
    """[(path, new text, Counter of lines that are not new)] for each staged text file a commit adds or changes."""
    fields = git("diff", "--cached", "--raw", "-z", "--no-abbrev", "-M", "--diff-filter=ACMRT").decode(
        "utf-8", "surrogateescape").split("\0")
    entries, i = [], 0
    while i < len(fields) and fields[i]:
        _old_mode, new_mode, old, new, status = fields[i][1:].split(" ")
        path = fields[i + 2] if status[0] in "RC" else fields[i + 1]
        i += 3 if status[0] in "RC" else 2
        if new_mode != "160000" and not path.startswith(SKIP):  # 160000: a nested repository, no blob
            entries.append((path, old, new))
    theirs = {}
    if git("rev-parse", "-q", "--verify", "MERGE_HEAD", ok=True):
        for rec in git("ls-tree", "-r", "-z", "--full-tree", "MERGE_HEAD").decode("utf-8", "surrogateescape").split("\0"):
            if rec:
                info, path = rec.split("\t", 1)
                if info.split(" ")[1] == "blob":
                    theirs[path] = info.split(" ")[2]
    data = blobs({s for p, old, new in entries for s in (old, new, theirs.get(p)) if s and s != ZERO})
    result = []
    for path, old, new in entries:
        seen = Counter()
        for sha in (old, theirs.get(path)):
            if sha and sha != ZERO and (before := text(data[sha])) is not None:
                seen.update(before.split("\n"))
        result.append((path, text(data[new]), seen))
    return result


def tree() -> list:
    listing = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    result = []
    for path in sorted({p for p in listing.decode("utf-8", "surrogateescape").split("\0") if p}):
        file = ROOT / path
        if path.startswith(TREE_SKIP) or file.is_symlink() or not file.is_file():  # a link, a deleted file, a fifo
            continue
        try:
            result.append((path, text(file.read_bytes()), Counter()))
        except OSError as exc:
            unscanned(f"{path}: {exc.strerror}")
    return result


def main(argv: list) -> int:
    if argv not in ([], ["--staged"]):
        print("usage: secret_scan.py [--staged]", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(errors="surrogateescape")
    sys.path.insert(0, str(ROOT / "system" / "scripts"))
    try:
        from vaultlib.redact import PATTERNS, PEM_BEGIN
    except Exception as exc:
        unscanned(f"shape list unreadable: {exc}")
    if not PATTERNS:
        unscanned("empty shape list")
    shapes = [*PATTERNS, ("pem", PEM_BEGIN)]
    found = 0
    for path, body, seen in (staged() if argv else tree()):
        if body is None:
            continue
        shown = json.dumps(path) if "\n" in path else path
        for n, line in enumerate(body.split("\n"), 1):
            if seen[line] > 0:
                seen[line] -= 1
                continue
            for name, pattern in shapes:
                if pattern.search(line):
                    print(f"secret shape: {shown}:{n}: {name}")
                    found = 1
    return found


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
