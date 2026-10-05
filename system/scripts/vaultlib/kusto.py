"""Read-only ADX queries over the v2 REST API (Plan 11 spec §3)."""
import json
import subprocess

from . import http
from .http import TelemetryError

TOKEN_CMD = ["az"]


def token(cluster: str) -> str:
    cmd = TOKEN_CMD + (["account", "get-access-token", "--resource", cluster, "--query", "accessToken", "-o", "tsv"]
                       if TOKEN_CMD == ["az"] else [])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, PermissionError):
        raise TelemetryError("auth", "az is not installed; install the Azure CLI and run az login") from None
    except subprocess.TimeoutExpired:
        raise TelemetryError("transient", "az timed out") from None
    tok = out.stdout.strip()
    if out.returncode != 0 or not tok:
        raise TelemetryError("auth", "run az login")
    return tok


def query(cluster: str, database: str, kql: str, max_rows: int = 500) -> list[dict]:
    if kql.lstrip().startswith("."):
        raise TelemetryError("bad", "management commands are not allowed")
    body = json.dumps({"db": database, "csl": kql, "properties": {"Options": {
        "request_readonly": True, "servertimeout": "00:01:00", "truncationmaxrecords": max_rows}}}).encode()
    headers = {"Authorization": f"Bearer {token(cluster)}", "Content-Type": "application/json",
               "Accept": "application/json"}
    frames, _ = http.json_call("POST", cluster.rstrip("/") + "/v2/rest/query", headers, body)
    primary_rows = None
    for frame in frames if isinstance(frames, list) else []:
        if frame.get("FrameType") == "DataTable" and frame.get("TableKind") == "PrimaryResult":
            cols = [c["ColumnName"] for c in frame.get("Columns", [])]
            primary_rows = [dict(zip(cols, row)) for row in frame.get("Rows", [])][:max_rows]
        if frame.get("FrameType") == "DataSetCompletion" and frame.get("HasErrors"):
            raise TelemetryError("bad", "query reported errors")
    if primary_rows is not None:
        return primary_rows
    raise TelemetryError("bad", "no primary result")
