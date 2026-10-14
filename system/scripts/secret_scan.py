#!/usr/bin/env python3
"""Report credential shapes, never their values (secret-shape lint spec §2, #166).

secret_scan.py --staged  the staged blobs of added, copied, modified and renamed paths (the pre-commit hook)
secret_scan.py           the working copy of every tracked and untracked file (lint_vault.sh)

Prints `secret shape: <path>:<line>: <shape>` per match. Exit 0 clean, 1 findings, 2 unscanned: the shape list in
vaultlib/redact.py could not be read or is empty, or git could not list or read the files."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# .scratch/ is throwaway. The tree report also skips the template's system/tests/ and docs/superpowers/, which hold
# the redaction tests' fake tokens by design; a staged file there is still scanned.
SKIP = (".scratch/",)
TREE_SKIP = SKIP + ("system/tests/", "docs/superpowers/")


def unscanned(reason: str):
    print(f"secret shape: unscanned ({reason})")
    sys.exit(2)


def git(*args: str) -> bytes:
    try:
        res = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    except OSError as exc:
        unscanned(f"git {args[0]} failed: {exc}")
    if res.returncode != 0:
        unscanned(f"git {args[0]} failed: {res.stderr.decode(errors='replace').strip()}")
    return res.stdout


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
    staged = argv == ["--staged"]
    listing = (git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR") if staged
               else git("ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    found = 0
    for path in sorted({p for p in listing.decode("utf-8", "surrogateescape").split("\0") if p}):
        if path.startswith(SKIP if staged else TREE_SKIP):
            continue
        if staged:
            data = git("cat-file", "blob", f":{path}")
        else:
            file = ROOT / path
            if file.is_symlink() or not file.is_file():  # a link, a deleted tracked file, a directory or a fifo
                continue
            try:
                data = file.read_bytes()
            except OSError as exc:
                unscanned(f"{path}: {exc.strerror}")
        if b"\0" in data[:8192]:  # binary, by git's own test
            continue
        for n, line in enumerate(data.decode("utf-8", "surrogateescape").splitlines(), 1):
            for name, pattern in shapes:
                if pattern.search(line):
                    print(f"secret shape: {path}:{n}: {name}")
                    found = 1
    return found


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
