#!/usr/bin/env python3
"""foundry-review: run the diff checks on the added lines of HEAD against a base (factory F4 §3.3).

    python3 review_diff.py [--base <ref>]

Run with the working directory inside the repository under review. Prints one `<check>: <path>:<line>: <text>` per
hit, then `<check>: pass` for each check with no hits. Exit 0 no hits, 1 hits, 2 could not run. The checks flag
candidates for a human to read; they are regexes and err toward flagging."""
import argparse
import os
import re
import subprocess
import sys

RUNNERS = ("system/scripts/lib_connector.sh", "system/scripts/run_headless.sh",
           "system/scripts/vaultlib/nightshift_session.py")
VISIBLE = re.compile(r"(system/(scripts|hooks|systemd|schemas)/|\.claude/(commands|skills)/|CLAUDE\.md$|"
                     r"extensions/[^/]+/(?!tests/))")
ALLOWED = re.compile(r"(rc|n|code|status)(_\w+)?|\w*rc|\w+_EXIT|(count|total|num)\w*|\w+_(rc|n|count|status|code)|"
                     r"CONNECTOR_REASON|FETCH_REASON|reason|len\(.*\)")


class Stop(Exception):
    """The checks could not run (exit 2)."""


def git(*args, check=True):
    try:
        out = subprocess.run(["git", "-c", "core.quotePath=false", *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise Stop("git is not installed")
    if check and out.returncode:
        raise Stop(out.stderr.strip() or f"git {args[0]} failed")
    return out


def added(diff_text):
    """(path, new line number, text) for each added line of a -U0 diff."""
    out, path, n, in_hunk = [], None, 0, False
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
        elif m := re.match(r"@@ -\S+ \+(\d+)", line):
            n, in_hunk = int(m.group(1)), True
        elif not in_hunk and line.startswith("+++ "):
            path = line[4:].removeprefix("b/") if line != "+++ /dev/null" else None
        elif in_hunk and path and line.startswith("+"):
            out.append((path, n, line[1:]))
            n += 1
    return out


def code(adds):
    """The added lines that can run: not prose in a .md file (a command or skill file holds shell), not a comment."""
    return [a for a in adds if (a[0].startswith(".claude/") if a[0].endswith(".md") else not a[2].lstrip().startswith("#"))]


def hit(check, path, n, text):
    return f"{check}: {path}:{n}: {text.strip()}"


def head_text(path):
    return git("show", f"HEAD:{path}", check=False).stdout


def now_redaction(adds, paths):
    writer = re.compile(r"notify\.sh|\bnotify\(")   # a Now write redacts inside now.py (factory F5 spec §4.1)
    redacted = {}
    out = []
    for p, n, t in code(adds):
        if writer.search(t):
            if p not in redacted:
                text = head_text(p)
                redacted[p] = "redact_credentials(" in text or "redact(" in text
            if not redacted[p]:
                out.append(hit("now-redaction", p, n, t))
    return out


def gate_escape(adds, paths):
    write = re.compile(r"write_text|write_bytes|open\(\s*(?:[^)]*,\s*)?[\"'][wa][bt+]*[\"']|os\.replace")
    shell = re.compile(r"(?<![-=>2&])>>?(?![&=>])|\btee\b|\bcp\b|\bmv\b")   # a > in Python is a comparison
    wiki = re.compile(r"\b(wiki|briefings)[\"']?\s*/")
    out = []
    for p, n, t in code(adds):
        if re.search(r"settings[\w.-]*\.json$", p):
            if re.search(r"(Edit|Write)\(", t) and wiki.search(t):
                out.append(hit("gate-escape", p, n, t))
        elif (not p.endswith(("vaultlib/publish.py", "vaultlib/now.py")) and wiki.search(t)
              and (write.search(t) or not p.endswith(".py") and shell.search(t))):
            out.append(hit("gate-escape", p, n, t))
    return out


def alert_text(adds, paths):
    sink = re.compile(r"\b(alert_once|alert\.py|fail\s)|raise Fail\(|\balerts_\w*(?=.*(>>|[\"']a[\"']))")
    interp = re.compile(r"\$\{?(\w+)|(?<!\$)\{([^{}]+)\}")
    out = []
    for p, n, t in code(adds):
        m = sink.search(t)
        # only what follows the sink is its text; a brace group's format spec ({n:>3}) is not a value
        if m and any(not ALLOWED.fullmatch(a or b.split(":")[0].strip()) for a, b in interp.findall(t[m.start():])):
            out.append(hit("alert-text", p, n, t))
    return out


def sleep_race(adds, paths):
    return [hit("sleep-race", p, n, t) for p, n, t in code(adds)
            if "/tests/" in "/" + p and re.search(r"\bsleep\b|time\.sleep\(", t) and "STUB_SLEEP=" not in t]


def skip_reason(adds, paths):
    out = []
    for p, n, t in code(adds):
        bare = p.endswith((".bats", ".sh")) and re.search(r"(^|\|\||&&|;)\s*skip\s*$", t)
        # ponytail: a call that continues on the next line is not judged; read it by hand.
        py = p.endswith(".py") and (re.search(r"\bskip\(\s*\)|mark\.skip\b(?!if)(?!\()", t)
                                    or re.search(r"skipif\(", t) and not t.rstrip().endswith(("(", ",")) and "reason" not in t)
        if bare or py:
            out.append(hit("skip-reason", p, n, t))
    return out


def changelog_label(adds, paths):
    out = []
    root = git("rev-parse", "--show-toplevel").stdout.strip()
    if not os.path.exists(os.path.join(root, "system", "config.md")) and any(VISIBLE.match(p) for p in paths):
        if not any(p.startswith("changes/") and p != "changes/CHANGELOG.md" and re.match(r"-\s.*\(#\d+", t)
                   for p, _, t in adds):
            out.append("changelog-label: a vault-visible path changed and no changes/ file adds a `- ... (#N)` line")
    if git("rev-parse", "--abbrev-ref", "HEAD").stdout.startswith("fix/"):
        out.append("changelog-label: fix branch: pass one `defect:<C1 to C14>` label to gh pr create --label")
    return out


def read_source_check(adds, paths):
    out = []
    for p, status in paths.items():
        if status != "A":
            continue
        text = head_text(p)
        if "--check" in text or "fetch_check_arg" in text:
            continue
        out += [hit("read-source-check", p, n, t) for q, n, t in code(adds)
                if q == p and re.search(r"\bconnector_run\b", t)][:1]
    return out


def computed_session(adds, paths):
    sh = re.compile(r"(?:^|[|;&(]|\$\()\s*(?:(?:exec|nohup|env|time)\s+|timeout\s+\S+\s+)*"
                    r"\"?\$(?:\{[^}]*\}|\w+)\"?\s[^#|;&]*?(?<=\s)(?:-p|--print)\b")
    py = re.compile(r"\[\s*(?![\"'])\w[\w.()]*\s*,[^\]]*[\"'](?:-p|--print)[\"']")
    out = []
    for p, n, t in code(adds):
        plain = t.replace("${CLAUDE_BIN:-claude}", "claude")
        if p not in RUNNERS and (py if p.endswith(".py") else sh).search(plain):
            out.append(hit("computed-session", p, n, t))
    return out


def computed_config(adds, paths):
    built = re.compile(r"[\"']\s*\+\s*[\"']\.md|\bf[\"'][^\"']*config[^\"']*\.md|with_suffix\(\s*[\"']\.md")
    return [hit("computed-config", p, n, t) for p, n, t in code(adds)
            if p.endswith(".py") and not p.endswith("vaultlib/config.py") and "config" in t and built.search(t)]


CHECKS = {"now-redaction": now_redaction, "gate-escape": gate_escape, "alert-text": alert_text,
          "sleep-race": sleep_race, "skip-reason": skip_reason, "changelog-label": changelog_label,
          "read-source-check": read_source_check, "computed-session": computed_session,
          "computed-config": computed_config}


def merge_base(base):
    refs = [base] if base else ["origin/master", "master"]
    for ref in refs:
        if git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).returncode == 0:
            return git("merge-base", ref, "HEAD").stdout.strip()
    raise Stop(f"unknown base: {', '.join(refs)}")


def main(argv):
    parser = argparse.ArgumentParser(description="Run the foundry-review diff checks on HEAD against a base.")
    parser.add_argument("--base", help="the base ref (default origin/master, then master)")
    base = parser.parse_args(argv).base   # a bad argument exits 2
    git("rev-parse", "--git-dir")         # outside a repository: exit 2 with git's own message
    mb = merge_base(base)
    diff = git("diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames", f"{mb}..HEAD").stdout
    status = {}
    for line in git("diff", "--name-status", "--no-renames", f"{mb}..HEAD").stdout.splitlines():
        s, _, path = line.partition("\t")
        status[path] = s
    adds, bad = added(diff), 0
    for name, check in CHECKS.items():
        hits = check(adds, status)
        bad += bool(hits)
        print("\n".join(hits) if hits else f"{name}: pass")
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Stop as e:
        print(f"review_diff: {e}", file=sys.stderr)
        sys.exit(2)
