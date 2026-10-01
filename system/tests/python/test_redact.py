import subprocess
import sys

import pytest

from helpers import REPO
from vaultlib.redact import redact


@pytest.mark.parametrize("secret, kind", [
    ("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\ndef\n-----END OPENSSH PRIVATE KEY-----", "pem"),
    ("AKIAIOSFODNN7EXAMPLE", "aws_key"),
    ("ghp_" + "a1B2c3D4" * 5, "github_token"),
    ("github_pat_" + "A1b2" * 15, "github_token"),
    ("glpat-" + "x1Y2z3" * 4, "gitlab_token"),
    ("xoxb-1234567890-abcdefghij", "slack_token"),
    ("sk-ant-api03-" + "Ab1" * 10, "anthropic_key"),
    ("sk-proj-" + "Ab1" * 10, "openai_key"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U", "jwt"),
])
def test_known_patterns(secret, kind):
    text, count = redact(f"before {secret} after")
    assert secret not in text and f"[REDACTED:{kind}]" in text and count == 1
    assert text.startswith("before ") and text.endswith(" after")


def test_bearer_keeps_prefix():
    text, count = redact("Authorization: Bearer abc.def.ghi")
    assert text == "Authorization: Bearer [REDACTED:bearer]" and count == 1


def test_assignment_keeps_key():
    text, count = redact("password = hunter2 and api_key: XYZ123")
    assert text == "password = [REDACTED:assignment] and api_key: [REDACTED:assignment]" and count == 2


def test_high_entropy_string():
    blob = "Zq8xT2mN7vB4kL9pR3wY6cH1jF5dS0aE"
    text, count = redact(f"token {blob}")
    assert "[REDACTED:high_entropy]" in text and count == 1


@pytest.mark.parametrize("safe", [
    "a" * 40, "0123456789abcdef" * 4, "9fceb02d0ae598e95dc970b74767f19372d61af8",
    "550e8400-e29b-41d4-a716-446655440000", "The quick brown fox jumps over the lazy dog",
    "deadbeef", "d41d8cd98f00b204e9800998ecf8427e",
])
def test_safe_text_untouched(safe):
    assert redact(safe) == (safe, 0)


def test_private_spans():
    text, count = redact("keep <private>my\nsecret</private> keep <PRIVATE>x</Private>")
    assert text == "keep [PRIVATE] keep [PRIVATE]" and count == 2


def test_cli_round_trip():
    res = subprocess.run([sys.executable, str(REPO / "system/scripts/redact.py")],
                         input="password=abc\n", capture_output=True, text=True)
    assert res.returncode == 0
    assert res.stdout == "password=[REDACTED:assignment]\n" and res.stderr.strip() == "redactions: 1"
