#!/usr/bin/env python3
"""foundry-review: run the diff checks on the added lines of HEAD against a base (factory F4 §3.3).

    python3 review_diff.py [--base <ref>]

Run with the working directory inside the repository under review. Prints one `<check>: <path>:<line>: <text>` per
hit, then `<check>: pass` for each check with no hits. Exit 0 no hits, 1 hits, 2 could not run. The checks flag
candidates for a human to read; they are regexes and err toward flagging."""
import os
import re
import subprocess
import sys

RUNNERS = ("system/scripts/lib_connector.sh", "system/scripts/run_headless.sh",
           "system/scripts/vaultlib/nightshift_session.py")
VISIBLE = re.compile(r"(system/(scripts|hooks|systemd|schemas)/|\.claude/(commands|skills)/|CLAUDE\.md$|"
                     r"extensions/[^/]+/(?!tests/))")
ALLOWED = re.compile(r"(rc|n|count|total|num|status|code)\w*|\w+_(rc|n|count|status|code)|"
                     r"CONNECTOR_REASON|FETCH_REASON|reason|len\(.*\)")


class Stop(Exception):
    """The checks could not run (exit 2)."""


def git(*args, check=True):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise Stop("git is not installed")
    if check and out.returncode:
        raise Stop(out.stderr.strip() or f"git {args[0]} failed")
    return out


def added(diff_text):
    """(path, new line number, text) for each added line of a -U0 diff."""
    out, path, n = [], None, 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].removeprefix("b/") if line != "+++ /dev/null" else None
        elif m := re.match(r"@@ -\S+ \+(\d+)", line):
            n = int(m.group(1))
        elif path and line.startswith("+") and not line.startswith("+++"):
            out.append((path, n, line[1:]))
            n += 1
    return out


def code(adds):
    """The added lines that are not shell or Python comments."""
    return [a for a in adds if not a[2].lstrip().startswith("#") or a[0].endswith(".md")]


def hit(check, path, n, text):
    return f"{check}: {path}:{n}: {text.strip()}"


def head_text(path):
    return git("show", f"HEAD:{path}", check=False).stdout


def now_redaction(adds, paths):
    writer = re.compile(r"now\.add\(|now\.py add|notify\.sh|\bnotify\(")
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
    write = re.compile(r"write_text|write_bytes|open\([^)]*[\"'][wa]|(?<![-=>2&])>>?(?![&=>])|\btee\b|\bcp\b|\bmv\b|"
                       r"os\.replace")
    wiki = re.compile(r"\b(wiki|briefings)/")
    out = []
    for p, n, t in code(adds):
        if re.search(r"settings[\w.-]*\.json$", p):
            if re.search(r"(Edit|Write)\(", t) and wiki.search(t):
                out.append(hit("gate-escape", p, n, t))
        elif not p.endswith(("vaultlib/publish.py", "vaultlib/now.py")) and wiki.search(t) and write.search(t):
            out.append(hit("gate-escape", p, n, t))
    return out


def alert_text(adds, paths):
    sink = re.compile(r"\b(alert_once|alert\.py|fail\s|alerts_\w*)|raise Fail\(")
    interp = re.compile(r"\$\{?(\w+)|(?<!\$)\{([^{}]+)\}")
    out = []
    for p, n, t in code(adds):
        if sink.search(t) and any(not ALLOWED.fullmatch(a or b) for a, b in interp.findall(t)):
            out.append(hit("alert-text", p, n, t))
    return out


def sleep_race(adds, paths):
    return [hit("sleep-race", p, n, t) for p, n, t in code(adds)
            if "/tests/" in "/" + p and re.search(r"\bsleep\b|time\.sleep\(", t) and "STUB_SLEEP=" not in t]


def skip_reason(adds, paths):
    out = []
    for p, n, t in code(adds):
        bare = p.endswith((".bats", ".sh")) and re.fullmatch(r"\s*skip\s*", t)
        # ponytail: a call that continues on the next line is not judged; read it by hand.
        py = p.endswith(".py") and (re.search(r"\bskip\(\s*\)|mark\.skip\b(?!if)(?!\()", t)
                                    or re.search(r"skipif\(", t) and not t.rstrip().endswith("(") and "reason" not in t)
        if bare or py:
            out.append(hit("skip-reason", p, n, t))
    return out


def changelog_label(adds, paths):
    out = []
    root = git("rev-parse", "--show-toplevel").stdout.strip()
    if not os.path.exists(f"{root}/system/config.md") and any(VISIBLE.match(p) for p in paths):
        if not any(p == "CHANGELOG.md" and re.match(r"\s*-\s.*\(#\d+\)", t) for p, _, t in adds):
            out.append("changelog-label: a vault-visible path changed and CHANGELOG.md gains no `- ... (#N)` line")
    if git("rev-parse", "--abbrev-ref", "HEAD").stdout.startswith("fix/"):
        out.append("changelog-label: fix branch: pass one `defect:<C1 to C14>` label to gh pr create --label")
    return out


def read_source_check(adds, paths):
    out = []
    for p, status in paths.items():
        text = head_text(p)
        if status != "A" or "--check" in text or "fetch_check_arg" in text:
            continue
        out += [hit("read-source-check", p, n, t) for q, n, t in code(adds)
                if q == p and re.search(r"\bconnector_run\b", t)][:1]
    return out


def computed_session(adds, paths):
    sh = re.compile(r"(?:^|[|;&(]|\$\()\s*(?:\"\$\{?\w+\}?\"|\$\{?\w+\})\s[^#|;&]*?(?<=\s)(?:-p|--print)\b")
    py = re.compile(r"\[\s*(?![\"'])\w[\w.()]*\s*,[^\]]*[\"'](?:-p|--print)[\"']")
    out = []
    for p, n, t in code(adds):
        plain = t.replace("${CLAUDE_BIN:-claude}", "claude")
        if p not in RUNNERS and (py if p.endswith(".py") else sh).search(plain):
            out.append(hit("computed-session", p, n, t))
    return out


def computed_config(adds, paths):
    built = re.compile(r"[\"']\s*\+\s*[\"']\.md|\bf[\"'][^\"']*config|with_suffix\(\s*[\"']\.md")
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
    base = argv[argv.index("--base") + 1] if "--base" in argv[:-1] else None
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
