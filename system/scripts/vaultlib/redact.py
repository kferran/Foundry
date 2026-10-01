"""Secret redaction for digests and inbox copies (spec §6.18)."""
import math
import re
from collections import Counter

PRIVATE = re.compile(r"<private>.*?</private>", re.IGNORECASE | re.DOTALL)
PATTERNS = [
    ("pem", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.DOTALL)),
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


def redact(text: str) -> tuple:
    """Return (redacted_text, redaction_count)."""
    count = 0

    def sub(pattern, replacement, value):
        nonlocal count
        new, n = pattern.subn(replacement, value)
        count += n
        return new

    text = sub(PRIVATE, "[PRIVATE]", text)
    for kind, pattern in PATTERNS:
        text = sub(pattern, f"[REDACTED:{kind}]", text)
    text = sub(BEARER, r"\1[REDACTED:bearer]", text)
    text = sub(ASSIGNMENT, r"\1\2[REDACTED:assignment]", text)
    before = text
    text = CANDIDATE.sub(_high_entropy, text)
    count += text.count("[REDACTED:high_entropy]") - before.count("[REDACTED:high_entropy]")
    return text, count
