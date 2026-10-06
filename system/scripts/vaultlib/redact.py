"""Secret redaction for digests and inbox copies (spec §6.18)."""
import math
import re
from collections import Counter

PRIVATE_OPEN = re.compile(r"<private>", re.IGNORECASE)
PRIVATE_CLOSE = re.compile(r"</private>", re.IGNORECASE)
PEM_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
PEM_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY-----")
PATTERNS = [
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]
BEARER = re.compile(r"(?i)(authorization:\s*bearer\s+)\S+")
ASSIGNMENT = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)(\s*[:=]\s*)(?!\[REDACTED)(\S+)")
CANDIDATE = re.compile(r"[A-Za-z0-9+/=_-]{32,}")
HEX = re.compile(r"[0-9a-fA-F]+")
ENTROPY_BITS = 4.0


def _entropy(s: str) -> float:
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


def _high_entropy(match: re.Match) -> str:
    s = match.group(0)
    if "REDACTED" in s or (HEX.fullmatch(s) and len(s) in (40, 64)) or _entropy(s) < ENTROPY_BITS:
        return s
    return "[REDACTED:high_entropy]"


def _scan_private(text: str) -> tuple[str, int]:
    """Replace each <private>...</private> span (any case, multi-line) with [PRIVATE], linearly.

    An unterminated <private> redacts to the end of the text: a forgotten closing tag fails closed.
    """
    result, count, pos = [], 0, 0
    while True:
        opened = PRIVATE_OPEN.search(text, pos)
        if not opened:
            result.append(text[pos:])
            break
        result.append(text[pos:opened.start()])
        result.append("[PRIVATE]")
        count += 1
        closed = PRIVATE_CLOSE.search(text, opened.end())
        if not closed:
            break
        pos = closed.end()
    return "".join(result), count


def _scan_pem(text: str) -> tuple[str, int]:
    """Scan for PEM blocks linearly: find BEGIN, search for END, replace and continue.

    Returns (redacted_text, count).
    If a BEGIN is found but no END, stop scanning (no later BEGIN can have an END).
    """
    result = []
    count = 0
    pos = 0

    while pos < len(text):
        begin_match = PEM_BEGIN.search(text, pos)
        if not begin_match:
            result.append(text[pos:])
            break

        result.append(text[pos:begin_match.start()])
        end_match = PEM_END.search(text, begin_match.end())
        if end_match:
            result.append("[REDACTED:pem]")
            count += 1
            pos = end_match.end()
        else:
            # No END found; stop scanning
            result.append(text[begin_match.start():])
            break

    return "".join(result), count


def redact(text: str) -> tuple:
    """Return (redacted_text, redaction_count)."""
    count = 0

    def sub(pattern, replacement, value):
        nonlocal count
        new, n = pattern.subn(replacement, value)
        count += n
        return new

    text, private_count = _scan_private(text)
    count += private_count
    # PEM scanning (linear, not regex)
    text, pem_count = _scan_pem(text)
    count += pem_count
    for kind, pattern in PATTERNS:
        text = sub(pattern, f"[REDACTED:{kind}]", text)
    text = sub(BEARER, r"\1[REDACTED:bearer]", text)
    text = sub(ASSIGNMENT, r"\1\2[REDACTED:assignment]", text)
    before = text
    text = CANDIDATE.sub(_high_entropy, text)
    count += text.count("[REDACTED:high_entropy]") - before.count("[REDACTED:high_entropy]")
    return text, count


ASSIGNMENT_EQUALS = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*=\s*\S")


def named_kinds(text: str) -> list:
    """The named detectors that fire on text, sorted, for the drop check (meetings spec §2.2). The generic
    high-entropy one is left out, and assignments count only as `key = value`: in speech `password: …` is common."""
    kinds = {kind for kind, pattern in PATTERNS if pattern.search(text)}
    if PRIVATE_OPEN.search(text):
        kinds.add("private")
    if _scan_pem(text)[1]:
        kinds.add("pem")
    if BEARER.search(text):
        kinds.add("bearer")
    if ASSIGNMENT_EQUALS.search(text):
        kinds.add("assignment")
    return sorted(kinds)
