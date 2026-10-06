import subprocess
import sys
import time

import pytest

from helpers import REPO
from vaultlib.redact import named_kinds, redact


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


def test_cli_non_utf8_round_trip():
    res = subprocess.run([sys.executable, str(REPO / "system/scripts/redact.py")],
                         input=b"\xff\xfe bad \x80 password=abc\n", capture_output=True)
    assert res.returncode == 0
    assert res.stdout == b"\xff\xfe bad \x80 password=[REDACTED:assignment]\n" and res.stderr.strip() == b"redactions: 1"


def test_pem_many_unterminated_headers_is_linear():
    text = "-----BEGIN RSA PRIVATE KEY-----\n" * 20000
    start = time.perf_counter()
    result_text, count = redact(text)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"Took {elapsed:.2f}s, expected < 1.0s (quadratic blowup detected)"
    assert count == 0
    assert result_text == text


def test_pem_two_blocks():
    pem1 = "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"
    pem2 = "-----BEGIN EC PRIVATE KEY-----\nxyz\n-----END EC PRIVATE KEY-----"
    text = f"prefix {pem1} middle {pem2} suffix"
    result_text, count = redact(text)
    assert count == 2
    assert result_text == "prefix [REDACTED:pem] middle [REDACTED:pem] suffix"
    assert pem1 not in result_text and pem2 not in result_text


def test_private_scan_is_linear():
    start = time.perf_counter()
    text, count = redact("<private>x" * 40000)
    assert time.perf_counter() - start < 1.0
    assert text == "[PRIVATE]" and count == 1


def test_unterminated_private_redacts_to_end():
    assert redact("a <private>secret") == ("a [PRIVATE]", 1)


def test_named_kinds_lists_the_named_detectors_that_fire():
    text = "<private>x</private> AKIAIOSFODNN7EXAMPLE Authorization: Bearer abc\ntoken = hunter2\n"
    assert named_kinds(text) == ["assignment", "aws_key", "bearer", "private"]
    assert named_kinds("-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n") == ["pem"]


def test_named_kinds_ignores_high_entropy_cue_ids():
    cue = "9f8Qz2LmX4vB7nR1tY6wK3pJ5sD0hG8cE2aZ/17-1"
    assert redact(cue)[1] == 1
    assert named_kinds(f"WEBVTT\n\n{cue}\n00:00:01.000 --> 00:00:02.000\n<v Avery Sample>Hello.</v>\n") == []


def test_cli_kinds():
    res = subprocess.run([sys.executable, str(REPO / "system/scripts/redact.py"), "--kinds"],
                         input="AKIAIOSFODNN7EXAMPLE\npassword=abc\n", capture_output=True, text=True)
    assert res.returncode == 0 and res.stdout == "assignment\naws_key\n"


def test_named_kinds_takes_only_the_key_equals_value_form():
    assert named_kinds("Avery: reset your password: it expired\n") == []
    assert redact("reset your password: it expired")[1] == 1
    assert named_kinds("api_key = sk_live_example\n") == ["assignment"]
