import subprocess
import sys
import time

import pytest

from helpers import REPO
from vaultlib.redact import redact, redact_credentials

STRIPE = "sk_" + "live_" + "Fake0" * 5   # built at run time: a literal key trips the host's push protection


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


def test_ssn_shape_redacts_and_skips_invalid_areas_and_the_run():
    """(#166): an SSN shape joins the shared list; 000, 666 and 9xx areas and the 123-45-6789 run are not SSNs."""
    ssn = "219-09-" + "9999"
    assert redact(f"ssn {ssn} here") == ("ssn [REDACTED:ssn] here", 1)
    for safe in ("000-12-3456", "666-12-3456", "912-34-5678", "123-45-6789", "2026-10-14", "1219-09-99990",
                 "WO-123-45-6780", "+49-171-12-3456", "ISBN 978-1-234-56-7890", "219-09-9999-01", "123-00-4567",
                 "412-34-0000", "２１９-０９-９９９９"):
        assert redact(safe, high_entropy=False) == (safe, 0)


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


def drop(data: bytes) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "system/scripts/redact.py"), "--drop"], input=data, capture_output=True)


def test_cli_drop_decodes_as_the_import_does():
    """audit S6 spec §2: UTF-8 with or without a byte-order mark, or UTF-16 with one, all land as one redacted UTF-8 text."""
    text = "Avery: the key is AKIAIOSFODNN7EXAMPLE\ntoken = hunter2\n"
    want = b"Avery: the key is [REDACTED:aws_key]\ntoken = [REDACTED:assignment]\n"
    for data in (text.encode(), "﻿".encode() + text.encode(), text.encode("utf-16"), b"\xfe\xff" + text.encode("utf-16-be")):
        res = drop(data)
        assert res.returncode == 0
        assert res.stdout == want and res.stderr.strip() == b"redactions: 2"


def test_cli_drop_strips_drive_links_before_redacting_so_the_import_publishes_the_same_text():
    """audit S6 review: redact() alone eats part of a Drive URL, leaving a broken link the import can no longer strip."""
    from datetime import datetime, timezone

    from vaultlib import meetings
    raw = b"Avery: see [Doc](https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit) now\n"
    res = drop(raw)
    assert res.returncode == 0 and res.stdout == b"Avery: see Doc now\n"
    start = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
    published = meetings.scrub(meetings.parse_drop("notes.txt", res.stdout, timezone.utc, start)).turns
    assert published == meetings.scrub(meetings.parse_drop("notes.txt", raw, timezone.utc, start)).turns
    assert "google" not in str(published)


def test_cli_drop_refuses_what_the_import_quarantines():
    """audit S6 spec §2: a drop the decoder rejects exits 1 with the import's reason and writes nothing to stdout."""
    res = drop(b"\x00" * 8)
    assert res.returncode == 1
    assert res.stdout == b"" and b"not UTF-8 text" in res.stderr


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


LONG_NAME = "Shop.Plugins.VendorAccountSuitabilitySubmissionFetchXML"
GUID_PATH = "api/orders/3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b/credential-check"


def test_high_entropy_guess_hits_long_names_and_guid_paths_and_can_be_skipped():
    """The cause of [REDACTED:high_entropy] in telemetry notes: CANDIDATE takes / and - as token characters, so a GUID
    inside a path joins one 64-character token above ENTROPY_BITS; a long PascalCase type name clears it alone."""
    assert redact(GUID_PATH) == ("[REDACTED:high_entropy]", 1)
    assert redact(LONG_NAME) == ("Shop.Plugins.[REDACTED:high_entropy]", 1)
    assert redact("3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b")[1] == 0
    assert redact(GUID_PATH, high_entropy=False) == (GUID_PATH, 0)
    assert redact(LONG_NAME, high_entropy=False) == (LONG_NAME, 0)
    assert redact("Zq8xT2mN7vB4kL9pR3wY6cH1jF5dS0aE password=x", high_entropy=False) == (
        "Zq8xT2mN7vB4kL9pR3wY6cH1jF5dS0aE password=[REDACTED:assignment]", 1)


@pytest.mark.parametrize("text, secret, marker", [
    ("call failed: Bearer Zm9vYmFyYmF6cXV4MTIzNDU2 rejected", "Zm9vYmFyYmF6cXV4MTIzNDU2", "Bearer [REDACTED:bearer] rejected"),
    ("postgres://app:pgpass99@db:5432/x", "pgpass99", "postgres://app:[REDACTED:userinfo]@db"),
    ("Server=db;Pwd=s3cretPwd;Database=x", "s3cretPwd", "Pwd=[REDACTED:connection];Database=x"),
    ("AccountName=a;AccountKey=Zm9vYmFyQUNDT1VOVEtFWQ==;EndpointSuffix=core.windows.net", "Zm9vYmFyQUNDT1VOVEtFWQ",
     "AccountKey=[REDACTED:connection];EndpointSuffix"),
    ("https://a.blob.core.windows.net/c/f?sv=2022&sig=AbCdEfSAS&se=2026", "AbCdEfSAS", "sig=[REDACTED:connection]&se=2026"),
    ("Server=db;Password=hunter2;Database=x", "hunter2", "Password=[REDACTED:assignment]"),
    ('{"user":"a","password":"hunter2"}', "hunter2", '"password":"[REDACTED:json]"'),
    ('{"ticketGuid":"3f2b","apiKey": "k-123"}', "k-123", '"apiKey": "[REDACTED:json]"'),
    ("key AKIAIOSFODNN7EXAMPLE here", "AKIAIOSFODNN7EXAMPLE", "key [REDACTED:aws_key] here"),
])
def test_redact_credentials_masks_credential_shapes(text, secret, marker):
    out = redact_credentials(text)
    assert secret not in out and marker in out


def test_redact_credentials_keeps_identifiers_and_prose():
    text = (f"Ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b for A1-23B4C-D-56 in {LONG_NAME} at {GUID_PATH}; "
            'the bearer of bad news {"tokenCount":"5"}')
    assert redact_credentials(text) == text


@pytest.mark.parametrize("text, secret, marker", [
    # Audit #298 and #301 S8: shapes redact() passed with 0 redactions.
    ("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI7K7MDENG", "wJalrXUtnFEMI7K7MDENG", "AWS_SECRET_ACCESS_KEY=[REDACTED:assignment]"),
    ("DB_PASSWORD=hunter2", "hunter2", "DB_PASSWORD=[REDACTED:assignment]"),
    ("SLACK_BOT_TOKEN: abc123def", "abc123def", "SLACK_BOT_TOKEN: [REDACTED:assignment]"),
    ('{"user":"a","password":"opensesame"}', "opensesame", '"password":"[REDACTED:json]"'),
    ("-----BEGIN PGP PRIVATE KEY BLOCK-----\nlQOYBF\n-----END PGP PRIVATE KEY BLOCK-----", "lQOYBF", "[REDACTED:pem]"),
    ("key " + STRIPE, STRIPE[8:], "[REDACTED:stripe_key]"),
])
def test_redact_catches_the_audit_shapes(text, secret, marker):
    out, count = redact(text)
    assert secret not in out and marker in out and count >= 1


@pytest.mark.parametrize("text", [
    # #386: after a colon, prose stays; only a value that looks like a secret is redacted.
    "Ask Pat about the password: reset flow",
    "the token: expired again",
    "secret: sauce",
])
def test_a_colon_followed_by_ordinary_words_is_kept_in_prose_only(text):
    assert redact(text, prose=True) == (text, 0)
    assert redact_credentials(text, prose=True) == text
    # Everywhere else a spoken "password: it" is still a secret (audit S6).
    assert "[REDACTED:assignment]" in redact(text)[0]
    # In prose too, a value that looks like a secret goes.
    assert redact("the password: hunter2", prose=True) == ("the password: [REDACTED:assignment]", 1)


def test_a_now_line_keeps_prose_after_a_colon():
    from vaultlib import now
    assert now.screen_fields("Ask Pat about the password: reset flow")[0] == "Ask Pat about the password: reset flow"


def test_the_secret_scan_shapes_hold_the_new_keys():
    # secret_scan.py scans with PATTERNS and PEM_BEGIN, so the pre-commit hook sees what redact() sees.
    from vaultlib.redact import PATTERNS, PEM_BEGIN
    assert any(p.search("k = " + STRIPE) for _, p in PATTERNS)
    assert PEM_BEGIN.search("-----BEGIN PGP PRIVATE KEY BLOCK-----")
