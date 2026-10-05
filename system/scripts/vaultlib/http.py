"""HTTP for the telemetry clients (Plan 11 spec §3): one seam, stub-able by FOUNDRY_TELEMETRY_STUB."""
import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT = 60


class TelemetryError(Exception):
    def __init__(self, kind: str, reason: str):
        super().__init__(f"{kind}: {reason}")
        self.kind, self.reason = kind, reason


def _route(url: str, body: bytes | None) -> str:
    """Stub route for a request: kusto-logs|kusto-spans|kusto-count|kusto-check|sentry-projects|sentry-issues|sentry-issue|sentry-trace."""
    if "/v2/rest/query" in url:
        csl = json.loads(body or b"{}").get("csl", "").lstrip()
        if csl.startswith("print"):
            return "kusto-check"
        if "| count" in csl:
            return "kusto-count"
        return "kusto-logs" if csl.startswith("Logs") else "kusto-spans"
    if "/events/" in url:
        return "sentry-trace"
    if "/projects/" in url:
        return "sentry-projects"
    if url.rstrip("/").split("?")[0].split("/")[-1].isdigit():
        return "sentry-issue"
    return "sentry-issues"


def _stub(stub_dir: str, url: str, body: bytes | None) -> tuple[int, bytes]:
    route = _route(url, body)
    d = Path(stub_dir)
    with open(d / "requests.log", "a", encoding="utf-8") as log:
        log.write(f"{route} {url}\n")
    status = int((d / f"{route}.status").read_text().strip()) if (d / f"{route}.status").exists() else 200
    data = (d / f"{route}.json").read_bytes() if (d / f"{route}.json").exists() else b"[]"
    return status, data


def request(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, bytes]:
    request.last_headers = {}
    stub = os.environ.get("FOUNDRY_TELEMETRY_STUB")
    if stub:
        return _stub(stub, url, body)
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            request.last_headers = dict(resp.headers)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        request.last_headers = dict(exc.headers or {})
        return exc.code, b""
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
        raise TelemetryError("transient", f"network: {type(exc).__name__}") from None


request.last_headers = {}


def json_call(method: str, url: str, headers: dict, body: bytes | None = None):
    status, data = request(method, url, headers, body)
    if status in (401, 403):
        raise TelemetryError("auth", f"HTTP {status}")
    if status == 429 or status >= 500:
        raise TelemetryError("transient", f"HTTP {status}")
    if status >= 400:
        raise TelemetryError("bad", f"HTTP {status}")
    try:
        return json.loads(data or b"null"), getattr(request, "last_headers", {})
    except ValueError:
        raise TelemetryError("bad", "response is not JSON") from None
